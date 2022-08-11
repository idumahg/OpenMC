import os, sys, subprocess, random, uuid

class Plopper:
    def __init__(self, outputdir):

        # Initilizing global variables
        self.outputdir = outputdir

  #      if not os.path.exists(self.outputdir):
   #         os.makedirs(self.outputdir)

    # Creating a dictionary using parameter label and value
    def createDict(self, x, params):
        dictVal = {}
        for p, v in zip(params, x):
            dictVal[p] = v
        return(dictVal)


    # Function to find the performance of the interim file, and return the rate cost to the search module
    def findPerformance(self, x, params):
        
        # Generate intermediate file
        dictVal = self.createDict(x, params)

        #compile and find the performance  
        if str(dictVal['q']) == " -Dqueueless=on ":
            run_cmd = ["sh", "queue_on.sh", str(dictVal['n']), str(dictVal['i']), str(dictVal['b']), str(dictVal['m'])]
        elif str(dictVal['q']) == " -Dqueueless=off ":
            run_cmd = ["sh", "queue_off.sh", str(dictVal['n']), str(dictVal['i']), str(dictVal['b'])]

        try:
            execution_status = subprocess.run(run_cmd, capture_output=True, text=True)
        except ValueError:
            print("There is a Value error")
        except:
            print('Something else went wrong')

        # print('execution_status: ', execution_status.stderr)
        rate = execution_status.stdout.split("\n")[-2].split(" ")[0]
        print('rate: ', rate)
        return float(rate) #return performance 

