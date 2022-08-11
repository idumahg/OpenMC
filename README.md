# OpenMC

To run OpenMC baseline:
__________________________________________________________________________________________________________
Go to the folder for the problem size you want to run, and run "sh baseline.sh". This will run the file "baseline.py" which contains the baseline parameters.

Some background:
_____________________________________________________________________________________________________________
Navigate to the folder for the problem size, and run "main.sh". There are two files "queue_on.sh" and "queue_off.sh" in each of the problem sizes.

One of the parameters to be optimized for openmc is a "queued mode", which is set during compilation. Because this will add addition time complexity to the
code, I already pre-compiled openmc using the two modes, "Dqueueless=off" and "Dqueueless=on". 

These compiled files are saved in the "build_on" and "build_off" directory in the openmc source file (which can be found in the zip filed in google drive)

In summary "queue_on.sh" uses a "build_off" directory. which contains the pre-compiled build files when "Dqueueless=on", 
while "queue_off" uses the pre-compiled files when "Dqueueless=off"

To run OpenMC for any of the problem size
____________________________________________________________________________________________________________
Navigate to the problem size directory and run "main.sh".
