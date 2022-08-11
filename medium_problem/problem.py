import numpy as np
from autotune import TuningProblem
from autotune.space import *
import os, sys, time, json, math
import ConfigSpace as CS
import ConfigSpace.hyperparameters as CSH
from skopt.space import Real, Integer, Categorical

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(1, os.path.dirname(HERE)+ '/plopper')
from plopper import Plopper

# create an object of ConfigSpace
cs = CS.ConfigurationSpace(seed=1234)
# number of MPI ranks per GPU or Tile
p0= CSH.UniformIntegerHyperparameter(name='p0', lower=1, upper=4, default_value=1)
# max number of particles in-flight
p1= CSH.UniformIntegerHyperparameter(name='p1', lower=100000, upper=8000000, default_value=1000000, q=10000)
# number of logarithmic hash grid bins
p2 = CSH.UniformIntegerHyperparameter(name='p2', lower=100, upper=100000, default_value=4000, q=100)
# minimum sorting threshold
p3 = CSH.UniformIntegerHyperparameter(name='p3', lower=0, upper=100000, default_value=20000, q=1000) # Can I use inf as upper?
# queuing logic type
p4 = CSH.CategoricalHyperparameter(name='p4', choices=[" -Dqueueless=on ", " -Dqueueless=off "], default_value=" -Dqueueless=on ")
cs.add_hyperparameters([p0, p1, p2, p3, p4])

# problem space
task_space = None
input_space = cs
output_space = Space([
     Real(0.0, 6000000, name="performance")
])

dir_path = os.path.dirname(os.path.realpath(__file__))
obj = Plopper(dir_path)

x1=['p0','p1','p2','p3','p4']
def myobj(point: dict):
    def plopper_func(x):
        x = np.asarray_chkfinite(x)  # ValueError if any NaN or Inf
        value = [point[x1[0]],point[x1[1]],point[x1[2]],point[x1[3]],point[x1[4]]]
        print('CONFIG:',point)
        params = ['n','i','b','m','q']
        result = obj.findPerformance(value, params)
        return result

    x = np.array([point[f'p{i}'] for i in range(len(point))])
    results = plopper_func(x)
    print('OUTPUT:%f',results)
    return -results

Problem = TuningProblem(
    task_space=None,
    input_space=input_space,
    output_space=output_space,
    objective=myobj,
    constraints=None,
    model=None
    )
