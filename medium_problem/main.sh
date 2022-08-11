#!/bin/bash

source /home/gidumah/miniconda/bin/activate ytune
python -m ytopt.search.ambs --evaluator subprocess --problem problem.Problem --max-evals=500 --learner RF
