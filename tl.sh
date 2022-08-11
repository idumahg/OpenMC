#!/bin/bash

source /home/gidumah/miniconda/bin/activate ytune
python base_online_tl.py --inputs small_problem.csv medium_problem.csv large_problem.csv --targets XXL_problem.py --unique
