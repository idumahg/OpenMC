import subprocess

execution_status = subprocess.run([ "sh", "queue_on.sh", str(1), str(1000000), str(4000), str(20000)], capture_output=True, text=True)
print('status:', execution_status.stderr)
rate = execution_status.stdout.split("\n")[-2].split(" ")[0]
#rate = execution_status.stdout.split("\n")[-2]
print('rate', rate)
