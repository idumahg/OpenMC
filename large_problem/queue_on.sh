#!/bin/bash

# source /home/gidumah/miniconda/bin/activate ytune
# load necessarily modules
module use /soft/modulefiles
module load spack
module load cmake
module load hdf5
module load llvm/main-20220708
module load openmpi/2.1.6-llvm

# Set data files 
export OPENMC_CROSS_SECTIONS=/home/gidumah/nndc_hdf5/cross_sections.xml

#rm -r /home/gidumah/openmc/build/*
#cd /home/gidumah/openmc/build
#cmake --preset=llvm_a100_mpi -DCMAKE_UNITY_BUILD=ON -DCMAKE_UNITY_BUILD_MODE=BATCH -DCMAKE_UNITY_BUILD_BATCH_SIZE=1000 -DCMAKE_INSTALL_PREFIX=./install -Doptimize=on -Ddevice_printf=off -Dcuda_thrust_sort=on + $5 + ..

# Build and install
#cd llvm_a100
#make install 


# Adjust environment to point to OpenMC install
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/home/gidumah/openmc/build_on/install/lib64
export PATH=$PATH:/home/gidumah/openmc/build_on/install/bin

# Running OpenMC
cd /home/gidumah/openmc_offloading_benchmarks/progression_tests/large

nvidia-cuda-mps-control -d

echo $1
echo $2
echo $3
echo $4


mpirun -n $1 openmc --event -i $2 -b $3 -m $4 > ~/ytopt/ytopt/ytopt/benchmark/OpenMC/large_problem/output.txt
output=$(cat ~/ytopt/ytopt/ytopt/benchmark/OpenMC/large_problem/output.txt  | grep particles/second | awk -F' ' '{print $5}')

echo $output

# python -m ytopt.search.ambs --evaluator ray --problem problem.Problem --max-evals=10 --learner RF


