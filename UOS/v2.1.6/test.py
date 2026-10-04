import psutil
import time

def get_proc_count(exe_path):
    num = 0
    for p in psutil.process_iter():
        try:
            if p.exe() == exe_path:
                num += 1
        except:
            continue
    return num

path = "/home/ljm/Documents/课程表进度条/课程表进度条"
while True:
    print(get_proc_count(path))
    time.sleep(2)