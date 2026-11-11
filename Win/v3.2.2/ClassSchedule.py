import psutil
import time
import os
import json

root_path = os.path.expanduser("~\\AppData\\Local\\Programs")
main_dir = f"{root_path}\\ClassSchedule\\课程表进度条"

PROTECTED_PROCESSES = {
    f"{main_dir}\\课程表进度条.exe": None,
    f"{main_dir}\\座位表.exe": os.path.join(main_dir, "Plugins", "seat_table", "process_lock.lock"),
}
need_protect = list(PROTECTED_PROCESSES.keys())
exist_protect = [exe for exe in need_protect if os.path.exists(exe)]
print(exist_protect)

def get_proc_count(exe_path):
    num = 0
    for p in psutil.process_iter():
        try:
            if p.exe() == exe_path:
                num += 1
        except:
            continue
    return num

def get_lock_file(exe_path):
    lock_path = PROTECTED_PROCESSES.get(exe_path)
    if lock_path is None:
        return os.path.join(os.path.dirname(exe_path), "process_lock.lock")
    return lock_path


for exe in exist_protect:
    lock_file = get_lock_file(exe)
    if os.path.exists(lock_file):
        try:
            os.remove(lock_file)
        except:
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

if get_proc_count(f"{main_dir}\\ClassSchedule.exe") > 1:
    os._exit(0)

try:
    json_data = json.load(open(f"{root_path}//ClassSchedule//课程表进度条//settings.json", "r"))
    sleep_time = min(max(json_data.get("protector_start_delay", 0), 0), 10)
except:
    sleep_time = 5

time.sleep(sleep_time)

while True:
    run_status = get_all_running()
    for exe, count in run_status.items():
        lock_file = get_lock_file(exe)
        if os.path.exists(lock_file):
            continue
        if count == 0:
            try:
                os.startfile(exe)
                print(f"程序未运行，已启动：{os.path.basename(exe)}")
            except Exception as e:
                print(f"启动失败 {exe}：{e}")
    time.sleep(2)