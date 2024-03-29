import numpy as np, pandas as pd
#from autotune.space import *
import os, time, argparse
import inspect
from csv import writer
from sdv.tabular import GaussianCopula, CopulaGAN, CTGAN, TVAE
# Will only use one of these, make a selection dictionary
sdv_models = {'GaussianCopula': GaussianCopula,
              'CopulaGAN': CopulaGAN,
              'CTGAN': CTGAN,
              'TVAE': TVAE,
              'random': None}
def check_conditional_sampling(objectlike):
    # Check source code on the _sample() method for the NotImplementedError
    # Not very robust, but relatively lightweight check that should be good enough
    # to find SDV's usual pattern for models that do not have conditional sampling yet
    try:
        source = inspect.getsource(objectlike._sample)
    except AttributeError:
        if objectlike is not None:
            print(f"WARNING: {objectlike} could not determine conditional sampling status")
        return False
    return not("raise NotImplementedError" in source and
               "doesn't support conditional sampling" in source)
conditional_sampling_support = dict((k,check_conditional_sampling(v)) for (k,v) in sdv_models.items())

from sdv.constraints import CustomConstraint, Between
from sdv.sampling.tabular import Condition
from ytopt.search.util import load_from_file


def build():
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-evals', type=int, default=10,
                        help='maximum number of evaluations')
    parser.add_argument('--n-refit', type=int, default=0,
                        help='refit the model')
    parser.add_argument('--seed', type=int, default=1234,
                        help='set seed')
    parser.add_argument('--top', type=float, default=0.1,
                        help='how much to train')
    parser.add_argument('--inputs', type=str, nargs='+', required=True,
                        help='problems to use as input')
    parser.add_argument('--targets', type=str, nargs='+', required=True,
                        help='problems to use as target tasks')
    parser.add_argument('--model', choices=list(sdv_models.keys()),
                        default='GaussianCopula', help='SDV model')
    parser.add_argument('--single-target', action='store_true',
                        help='Treat each target as a unique problem (default: solve all targets at once)')
    parser.add_argument('--unique', action='store_true',
                        help='Do not re-evaluate points seen since the last dataset generation')
    parser.add_argument('--output-prefix', type=str, default='results_sdv',
                        help='Output files are created using this prefix (default: [results_sdv]*.csv)')
    parser.add_argument('--no-log-objective', action='store_true',
                        help="Avoid using logarithm on objective values")
    parser.add_argument('--load-log', action='store_true',
                        help="Apply logarithm to loaded TL data")
    parser.add_argument('--speedup', default=None, type=str,
                        help="File to refer to for base speed value")
    return parser

def parse(prs, args=None):
    if args is None:
        args = prs.parse_args()
    return args

def param_type(k, problem):
    v = problem.problem_params[k]
    if v == 'categorical':
        if hasattr(problem, 'categorical_cast'):
            v = problem.categorical_cast[k]
        else:
            v = 'str'
    if v == 'integer':
        v = 'int64'
    return v

def close_enough(frame, rows, column, target, criterion):
    out = []
    # Eliminate rows that are too far from EVER being selected
    if target > criterion[-1]:
        possible = frame[frame[column] > criterion[-1]]
    elif target < criterion[0]:
        possible = frame[frame[column] < criterion[0]]
    else:
        # Find target in the middle using sign change detection in difference
        sign_index = list(np.sign(pd.Series(criterion)-target).diff()[1:].ne(0)).index(True)
        lower, upper = criterion[sign_index:sign_index+2]
        possible = frame[(frame[column] > lower) & (frame[column] < upper)]
    # Prioritize closest rows first
    dists = (possible[column]-target).abs().sort_values().index[:rows]
    return possible.loc[dists].reset_index(drop=True)

def sample_approximate_conditions(sdv_model, model, conditions, criterion, param_names):
    # If model supports conditional sampling, just utilize that
    if conditional_sampling_support[sdv_model]:
        return model.sample_conditions(conditions)
    # Otherwise, it can be hard to conditionally sample using reject sampling.
    # As such, we do our own reject strategy
    criterion = sorted(criterion)
    requested_rows = sum([_.get_num_rows() for _ in conditions])
    selected = []
    prev_len = -1
    cur_len = 0
    # Use lack of change as indication that no additional rows could be found
    while prev_len < requested_rows and cur_len != prev_len:
        prev_len = cur_len
        samples = model.sample(num_rows=requested_rows, randomize_samples=False)
        candidate = []
        for cond in conditions:
            n_rows = cond.get_num_rows()
            for (col, target) in cond.get_column_values().items():
                candidate.append(close_enough(samples, n_rows, col, target, criterion))
        candidate = pd.concat(candidate).drop_duplicates(subset=param_names)
        selected.append(candidate)
        cur_len = sum(map(len, selected))
    selected = pd.concat(selected).drop_duplicates(subset=param_names)
    # FORCE conditions to be held in this data
    for cond in conditions:
        for (col, target) in cond.get_column_values().items():
            selected[col] = target
    return selected


def online(targets, data, inputs, args, fname, speed = None):
    global time_start

    # All problems (input and target alike) must utilize the same parameters or this is not going to work
    param_names = set(targets[0].params)
    for target_problem in targets[1:]:
        other_names = set(target_problem.params)
        if len(param_names.difference(other_names)) > 0:
            raise ValueError(f"Targets {targets[0].name} and "
                             f"{target_problem.name} utilize different parameters")
    criterion = []
    for input_problem in inputs:
        criterion.append(input_problem.problem_class)
        other_names = set(input_problem.params)
        if len(param_names.difference(other_names)) > 0:
            raise ValueError(f"Target {targets[0].name} and "
                             f"{input_problem.name} utilize different parameters")
    param_names = sorted(param_names)
    n_params = len(param_names)

    # Gather all constraints from all target problems
    constraints = []
    for target in targets:
        constraints.extend(target.constraints)
    if args.model != 'random':
        field_names = ['input']+param_names+['runtime']
        field_transformers = targets[0].problem_params
        model = sdv_models[args.model](field_names=field_names, field_transformers=field_transformers,
                  constraints=constraints, min_value=None, max_value=None)
    else:
        model = None
    csv_fields = param_names+['objective','predicted','elapsed_sec']
    for i in range(len(targets)-1):
        csv_fields.extend([f'objective_{i}',f'predicted_{i}',f'elapsed_sec_{i}'])

    # writing to csv file
    with open(fname, 'w') as csvfile:
        # creating a csv writer object
        csvwriter = writer(csvfile)
        # writing the fields
        csvwriter.writerow(csv_fields)

        # Make conditions for each target
        conditions = []
        for target_problem in targets:
            conditions.append(Condition({'input': target_problem.problem_class},
                                        num_rows=max(100, args.max_evals)))
        evals_infer = []
        eval_master = 0
        # Initial fit
        if model is not None:
            print(f"Fitting with {len(data)} rows")
            import warnings
            warnings.simplefilter("ignore")
            model.fit(data)
            warnings.simplefilter('default')
        time_start = time.time()
        while eval_master < args.max_evals:
            # Generate prospective points
            if args.model != 'random':
                # Some SDV models don't realllllly support the kind of conditional sampling we need
                # So this call will bend the condition rules a bit to help them produce usable data
                # until SDV fully supports conditional sampling for those models
                # For any model where SDV has conditional sampling support, this SHOULD utilize SDV's
                # real conditional sampling and bypass the approximation entirely
                ss1 = sample_approximate_conditions(args.model, model, conditions,
                                                    sorted(criterion), param_names)
                for col in param_names:
                    ss1[col] = ss1[col].astype(str)
            else:
                # random model is achieved by sampling configurations from the target problem's input space
                columns = ['input']+param_names+['runtime']
                dtypes = [(k,param_type(k, targets[0])) for k in columns]
                random_data = []
                for idx, cond in enumerate(conditions):
                    for _ in range(cond.num_rows):
                        # Generate a random valid sample in the parameter space
                        random_params = targets[idx].input_space.sample_configuration().get_dictionary()
                        random_params = [random_params[k] for k in param_names]
                        # Generate the runtime estimate
                        inference = 1.0
                        random_data.append(tuple([cond.column_values['input']]+random_params+[inference]))
                ss1 = np.array(random_data, dtype=dtypes)
                ss1 = pd.DataFrame(ss1, columns=columns)
                for col, dtype in zip(ss1.columns, dtypes):
                    if dtype[1] == 'str':
                        ss1[col] = ss1[col].astype('string')
            # Don't evaluate the exact same parameter configuration multiple times in a fitting round
            ss1 = ss1.drop_duplicates(subset=param_names, keep="first")
            ss = ss1.sort_values(by='runtime')#, ascending=False)
            new_sdv = ss[:args.max_evals]
            eval_update = 0
            stop = False
            while not stop:
                for row in new_sdv.iterrows():
                    sample_point_val = row[1].values[1:]
                    sample_point = dict((pp,vv) for (pp,vv) in zip(param_names, sample_point_val))
                    # Search to see if this combination of parameter values AND
                    # problem class already exist in the data frame.
                    # If we're unique, skip it, otherwise we will replace it with new value
                    problem_tuple = tuple(param_names+['input'])
                    search_equals = tuple(row[1].values[1:1+n_params].tolist()+[row[1].values[0]])
                    n_matching_columns = (data[list(problem_tuple)] == search_equals).sum(1)
                    full_match_idx = np.where(n_matching_columns == n_params+1)[0]
                    matching_data = data.iloc[full_match_idx]
                    if matching_data.empty or not args.unique:
                        ss = []
                        for target_problem in targets:
                            # Use the target problem's .objective() call to generate an evaluation
                            print(f"Eval {eval_master+1}/{args.max_evals}")
                            if speed is None:
                                evals_infer.append(target_problem.objective(sample_point))
                            else:
                                evals_infer.append(speed / target_problem.objective(sample_point))
                            #print(target_problem.name, sample_point, evals_infer[-1])
                            now = time.time()
                            elapsed = now - time_start
                            if ss == []:
                                ss = [sample_point[k] for k in param_names]
                                ss += [evals_infer[-1]]+[sample_point_val[-1]]
                                ss += [elapsed]
                            else:
                                # Append new target data to the CSV row
                                ss2 = [evals_infer[-1]]+[sample_point_val[-1]]
                                ss2 += [elapsed]
                                ss.extend(ss2)
                            # Basically: problem parameters, np.log(time), problem_class
                            evaluated = list(search_equals)
                            # Insert runtime before the problem class size
                            if args.no_log_objective:
                                evaluated.append(float(evals_infer[-1]))
                            else:
                                evaluated.append(float(np.log(evals_infer[-1])))
                            # For each problem we want to denote the actual result in
                            # our dataset to improve future data generation
                            if matching_data.empty:
                                data.loc[max(data.index)+1] = evaluated
                            else:
                                # Replace results -- should be mostly the same
                                # Have to wrap `evaluated` in a list for pandas to be
                                # happy with the overwrite
                                data.loc[matching_data.index] = [evaluated]
                        # Record in CSV and update iteration
                        csvwriter.writerow(ss)
                        csvfile.flush()
                        eval_update += 1
                        eval_master += 1
                    # Important to run refit AFTER at least one evaluation is done, else we
                    # infinite loop when args.n_refit=0 (never)
                    if eval_update == args.n_refit:
                        # update model
                        if model is not None:
                            model.fit(data)
                        stop = True
                        break
                    if eval_master >= args.max_evals:
                        stop = True
                        break
                if args.unique or args.n_refit == 0:
                    stop = True
    csvfile.close()

def main(args=None):
    args = parse(build(), args)
    output_prefix = args.output_prefix
    print(f"USING {args.model} for constraints")
    print('max_evals', args.max_evals, 'number of refit', args.n_refit, 'how much to train', args.top,
          'seed', args.seed)
    # Seed control
    np.random.seed(args.seed)
    # SDV MAY USE TORCH IN LOWER-LEVEL MODULES. CONTROL ITS RNG
    import torch
    torch.manual_seed(args.seed)

    X_opt = []
    print ('----------------------------- how much data to use?', args.top)

    # Different objective for speedup
    if args.speedup is not None:
        speed = pd.read_csv(args.speedup)['objective'][0]
    else:
        speed = None

    # Load the input and target problems
    inputs, targets, frames = [], [], []
    # Fetch the target problem(s)'s plopper
    for idx, problemName in enumerate(args.inputs):
        # NOTE: When specified as 'filename.attribute', the second argument 'Problem'
        # is effectively ignored. If only the filename is given (ie: 'filename.py'),
        # defaults to finding the 'Problem' attribute in that file
        if problemName.endswith('.py'):
            attr = 'Problem'
        else:
            pName, attr = problemName.split('.')
            pName += '.py'
        inputs.append(load_from_file(pName, attr))
        # Load the best top x%
        last_in = inputs[-1]
        results_file = last_in.plopper.kernel_dir+"/results_rf_"
        results_file += last_in.dataset_lookup[last_in.problem_class][0].lower()+"_"
        last_in = last_in.__class__.__name__
        results_file += last_in[:last_in.rindex('_')].lower()+".csv"
        if not os.path.exists(results_file):
            # First try backup
            backup_results_file = results_file.rsplit('/',1)
            backup_results_file.insert(1, 'data')
            backup_results_file = "/".join(backup_results_file)
            if not os.path.exists(backup_results_file):
                # Next try replacing '-' with '_'
                dash_results_file = "_".join(results_file.split('-'))
                if not os.path.exists(dash_results_file):
                    dash_backup_results_file = "_".join(backup_results_file.split('-'))
                    if not os.path.exists(dash_backup_results_file):
                        # Execute the input problem and move its results files to the above directory
                        raise ValueError(f"Could not find {results_file} for '{problemName}' "
                                         f"[{inputs[-1].name}] and no backup at {backup_results_file}"
                                         "\nYou may need to run this problem or rename its output "
                                         "as above for the script to locate it")
                    else:
                        print(f"WARNING! {problemName} [{inputs[-1].name}] is using backup data rather "
                                "than original data (Dash-to-Underscore Replacement ON)")
                        results_file = dash_backup_results_file
                else:
                    print("Dash-to-Underscore Replacement ON")
                    results_file = dash_results_file
            else:
                print(f"WARNING! {problemName} [{inputs[-1].name}] is using backup data rather "
                        "than original data")
                results_file = backup_results_file
        dataframe = pd.read_csv(results_file)
        dataframe['input'] = pd.Series(int(inputs[-1].problem_class) for _ in range(len(dataframe.index)))
        dataframe['runtime'] = dataframe['objective']
        if args.load_log:
            dataframe['runtime'] = np.log(dataframe['runtime'])
            if args.speedup is not None:
                speed = np.log(speed)
        q_10_s = np.quantile(dataframe.runtime.values, args.top)
        real_df = dataframe.loc[dataframe['runtime'] <= q_10_s]
        if args.speedup is not None:
            real_df['speedup'] = speed / real_df['runtime']
        real_data = real_df.drop(columns=['elapsed_sec', 'objective'])
        frames.append(real_data)
    # Have to reset the index in case included frames have same index from their original frames
    # Drop the legacy index column as we will not care to recover it and it bothers the shape when
    # recording new evaluations
    real_data = pd.concat(frames).reset_index().drop(columns='index')

    for problemName in args.targets:
        if problemName.endswith('.py'):
            attr = 'Problem'
        else:
            pName, attr = problemName.split('.')
            pName += '.py'
        targets.append(load_from_file(pName, attr))
        # make target evaluations silent as we'll report them on our own
        #targets[-1].silent = True
        # Seed control
        targets[-1].seed(args.seed)
        # Single-target mode
        if args.single_target:
            online([targets[-1]], real_data, inputs, args, f"{output_prefix}_{targets[-1].name}.csv", speed)
    if not args.single_target:
        online(targets, real_data, inputs, args, f"{output_prefix}_ALL.csv", speed)

if __name__ == '__main__':
    main()
