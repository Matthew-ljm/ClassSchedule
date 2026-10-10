import psutil
import time
import os
import json

root_path = os.path.expanduser("~\\AppData\\Local\\Programs")
need_protect = [f"{root_path}\\ClassSchedule\\课程表进度条\\课程表进度条.exe", f"{root_path}\\座位表\\座位表.exe", f"{root_path}\\ClassSchedule\\座位表\\座位表.exe"]
exist_protect = [exe for exe in need_protect if os.path.exists(exe)]
print(exist_protect)

for exe in exist_protect:
    try:
        dir_path = os.path.dirname(exe)
        lock_file = os.path.join(dir_path, "process_lock.lock")
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
            except:
                pass
    except Exception as e:
        pass

def get_all_running():
    running_counts = {exe: 0 for exe in exist_protect}
    for p in psutil.process_iter():
        try:
            proc_exe = p.exe()
            if proc_exe in running_counts:
                running_counts[proc_exe] += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    return running_counts

try:
    json_data = json.load(open(f"{root_path}//ClassSchedule//课程表进度条//settings.json", "r"))
    sleep_time = min(max(json_data.get("protector_start_delay", 0), 0), 10)
except:
    sleep_time = 5

time.sleep(sleep_time)

while True:
    run_status = get_all_running()
    for exe, count in run_status.items():
        dir_path = os.path.dirname(exe)
        lock_file = os.path.join(dir_path, "process_lock.lock")
        if os.path.exists(lock_file):
            continue
        if count == 0:
            try:
                os.startfile(exe)
                print(f"程序未运行，已启动：{os.path.basename(exe)}")
            except Exception as e:
                print(f"启动失败 {exe}：{e}")
    time.sleep(2)