import psutil
import subprocess
import time
import os

def get_proc_count(exe_path):
    num = 0
    for p in psutil.process_iter():
        try:
            if p.exe() == exe_path:
                num += 1
        except:
            continue
    return num

time.sleep(10)

while True:
    doc_path = os.path.expanduser("~/Documents")
    exe_path = f"{doc_path}/课程表进度条/课程表进度条"
    num = get_proc_count(exe_path)
    if num == 0:
        doc_path = os.path.expanduser("~/Documents")
        try:
            subprocess.Popen(f"{doc_path}/课程表进度条/课程表进度条", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
        except Exception as e:
            print(f"Error occurred while trying to open the application: {e}")
    time.sleep(5)