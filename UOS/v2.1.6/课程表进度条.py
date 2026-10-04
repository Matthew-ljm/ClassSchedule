import pygame
import requests
import os
from datetime import datetime
import time
import threading
import sys
import re
import psutil
import subprocess
import ntplib
from datetime import datetime, timedelta, timezone

client = ntplib.NTPClient()
os.environ["SDL_MOUSE_TOUCH_EVENTS"] = "1"
os.environ["SDL_TOUCH_MOUSE_EVENTS"] = "1"
os.environ["SDL_VIDEODRIVER"] = "x11"
os.environ["SDL_WINDOW_TYPE"] = "tooltip"
os.environ["SDL_ALWAYS_ON_TOP"] = "1"
timestamp_now = time.time()
dt_now = datetime.now()
time_lock = threading.Lock()
doc_path = os.path.expanduser("~/Documents")
def get_proc_count(exe_path):
    num = 0
    for p in psutil.process_iter():
        try:
            if p.exe() == exe_path:
                num += 1
        except:
            continue
    return num
count = get_proc_count(f"{doc_path}/课程表进度条/课程表进度条")
if count > 1:
    os._exit(0)
count2 = get_proc_count(f"{doc_path}/ClassSchedule-UOS/ClassSchedule-UOS")
if count2 == 0:
    try:
        subprocess.Popen([f"{doc_path}/ClassSchedule-UOS/ClassSchedule-UOS"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
    except Exception:
        pass
def get_resource_path(rel_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, rel_path)
    return os.path.abspath(rel_path)

def get_resource_path2(rel_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, rel_path)
    return os.path.abspath(rel_path)

def get_resource_path3(rel_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, rel_path)
    return os.path.abspath(rel_path)
def kill_all_same_process(exe_path):
    for proc in psutil.process_iter(["pid", "exe"]):
        try:
            proc_exe = proc.info["exe"]
            if proc_exe == exe_path:
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
def get_ntp_time():
    try:
        resp = client.request("ntp.aliyun.com", timeout=10)
        utc_stamp = resp.tx_time
        utc_now = datetime.fromtimestamp(utc_stamp, timezone.utc)
        bj_now = utc_now + timedelta(hours=8)
        return bj_now.replace(tzinfo=None)
    except Exception:
        return None

def get_network_time_background():
    global timestamp_now, dt_now
    fail_count = 0
    while True:
        try:
            bj_now = get_ntp_time()
            if bj_now is not None:
                fail_count = 0
                with time_lock:
                    timestamp_now = bj_now.timestamp()
                    dt_now = bj_now
            else:
                raise Exception("Failed to get NTP time")
        except Exception as e:
            fail_count += 1
            if fail_count > 5:
                with time_lock:
                    timestamp_now = time.time()
                    dt_now = datetime.now()
        time.sleep(60)

def auto_time_update():
    global timestamp_now, dt_now
    while True:
        with time_lock:
            timestamp_now += 1
            dt_now += timedelta(seconds=1)
        time.sleep(1)
def init_program():
    try:
        pass
    except Exception:
        pass
    try:
        p = psutil.Process(os.getpid())
        if sys.platform != "win32":
            try:
                p.nice(0)
            except Exception:
                pass
    except Exception:
        pass
init_program()
WMCTRL_BIN = get_resource_path("wmctrl")
XPROP_BIN = get_resource_path2("xprop")
XDOTOOL_BIN = get_resource_path3("xdotool")
if os.path.exists(WMCTRL_BIN):
    os.chmod(WMCTRL_BIN, 0o755)
if os.path.exists(XPROP_BIN):
    os.chmod(XPROP_BIN, 0o755)
if os.path.exists(XDOTOOL_BIN):
    os.chmod(XDOTOOL_BIN, 0o755)
os.environ["PYTHONIOENCODING"] = "utf-8"
pygame.init()
MAIN_EXE_PATH = os.path.abspath(sys.executable)
class ScheduleDisplay:
    def __init__(self):
        info = pygame.display.Info()
        self.screen_w = info.current_w
        self.screen_h = info.current_h
        self.win_w = int(self.screen_w * 0.9)
        self.win_h = 50
        self.move_step = 6
        self.key_delay = 0.15
        self.last_key_time = 0
        self.window_x = (self.screen_w - self.win_w) // 2
        self.window_y = 0
        os.environ['SDL_VIDEO_WINDOW_POS'] = f"{self.window_x},{self.window_y}"
        self.screen = pygame.display.set_mode((self.win_w, self.win_h), pygame.NOFRAME)
        self.win_title = "课表进度条"
        pygame.display.set_caption(self.win_title)
        self.win_id_dec = pygame.display.get_wm_info()["window"]
        self.win_id_hex = hex(self.win_id_dec)
        print(self.win_id_hex)
        threading.Thread(target=self.top_daemon, daemon=True).start()
        threading.Thread(target=self.minimize_restart_daemon, daemon=True).start()
        self.dragging = False
        self.drag_rel_x = 0
        self.drag_rel_y = 0
        self.touch_dragging = False
        self.touch_finger_id = -1
        self.clock = pygame.time.Clock()
        self.api_url = "https://test.m-code.top/api/class-schedule/"
        self.local_schedule = {
            "day1": [
                {"name":"早餐","start":"07:00","end":"07:30"},
                {"name":"晨检晨读","start":"07:30","end":"07:55"},
                {"name":"课间","start":"07:55","end":"08:00"},
                {"name":"数学","start":"08:00","end":"08:45"},
                {"name":"课间操","start":"08:45","end":"09:15"},
                {"name":"眼操","start":"09:15","end":"09:20"},
                {"name":"语文","start":"09:20","end":"10:05"},
                {"name":"课间","start":"10:05","end":"10:15"},
                {"name":"英语","start":"10:15","end":"11:00"},
                {"name":"课间","start":"11:00","end":"11:10"},
                {"name":"体育","start":"11:10","end":"11:55"},
                {"name":"午餐自由活动","start":"11:55","end":"13:00"},
                {"name":"午休","start":"13:00","end":"13:25"},
                {"name":"课间","start":"13:25","end":"13:30"},
                {"name":"化学","start":"13:30","end":"14:15"},
                {"name":"课间","start":"14:15","end":"14:25"},
                {"name":"艺术课","start":"14:25","end":"15:10"},
                {"name":"课间","start":"15:10","end":"15:20"},
                {"name":"眼操","start":"15:20","end":"15:25"},
                {"name":"班会","start":"15:25","end":"16:10"},
                {"name":"课间","start":"16:10","end":"16:20"},
                {"name":"地理","start":"16:20","end":"17:05"},
                {"name":"课间","start":"17:05","end":"17:15"},
                {"name":"语文课后服务","start":"17:15","end":"18:15"}
            ],
            "day2": [
                {"name":"早餐","start":"07:00","end":"07:30"},
                {"name":"晨检晨读","start":"07:30","end":"07:55"},
                {"name":"课间","start":"07:55","end":"08:00"},
                {"name":"物理","start":"08:00","end":"08:45"},
                {"name":"课间操","start":"08:45","end":"09:15"},
                {"name":"眼操","start":"09:15","end":"09:20"},
                {"name":"数学","start":"09:20","end":"10:05"},
                {"name":"课间","start":"10:05","end":"10:15"},
                {"name":"体育","start":"10:15","end":"11:00"},
                {"name":"课间","start":"11:00","end":"11:10"},
                {"name":"化学","start":"11:10","end":"11:55"},
                {"name":"午餐自由活动","start":"11:55","end":"13:00"},
                {"name":"午休","start":"13:00","end":"13:25"},
                {"name":"课间","start":"13:25","end":"13:30"},
                {"name":"历史","start":"13:30","end":"14:15"},
                {"name":"课间","start":"14:15","end":"14:25"},
                {"name":"语文","start":"14:25","end":"15:10"},
                {"name":"课间","start":"15:10","end":"15:20"},
                {"name":"眼操","start":"15:20","end":"15:25"},
                {"name":"道德与法治","start":"15:25","end":"16:10"},
                {"name":"课间","start":"16:10","end":"16:20"},
                {"name":"英语","start":"16:20","end":"17:05"},
                {"name":"课间","start":"17:05","end":"17:15"},
                {"name":"英语课后服务","start":"17:15","end":"18:15"}
            ],
            "day3": [
                {"name":"早餐","start":"07:00","end":"07:30"},
                {"name":"晨检晨读","start":"07:30","end":"07:55"},
                {"name":"课间","start":"07:55","end":"08:00"},
                {"name":"语文","start":"08:00","end":"08:45"},
                {"name":"课间操","start":"08:45","end":"09:15"},
                {"name":"眼操","start":"09:15","end":"09:20"},
                {"name":"语文","start":"09:20","end":"10:05"},
                {"name":"课间","start":"10:05","end":"10:15"},
                {"name":"物理","start":"10:15","end":"11:00"},
                {"name":"课间","start":"11:00","end":"11:10"},
                {"name":"英语","start":"11:10","end":"11:55"},
                {"name":"午餐自由活动","start":"11:55","end":"13:00"},
                {"name":"午休","start":"13:00","end":"13:25"},
                {"name":"课间","start":"13:25","end":"13:30"},
                {"name":"数学","start":"13:30","end":"14:15"},
                {"name":"课间","start":"14:15","end":"14:25"},
                {"name":"道德与法治","start":"14:25","end":"15:10"},
                {"name":"课间","start":"15:10","end":"15:20"},
                {"name":"眼操","start":"15:20","end":"15:25"},
                {"name":"体育","start":"15:25","end":"16:10"},
                {"name":"课间","start":"16:10","end":"16:20"},
                {"name":"地理","start":"16:20","end":"17:05"},
                {"name":"课间","start":"17:05","end":"17:15"},
                {"name":"数学课后服务","start":"17:15","end":"18:15"}
            ],
            "day4": [
                {"name":"早餐","start":"07:00","end":"07:30"},
                {"name":"晨检晨读","start":"07:30","end":"07:55"},
                {"name":"课间","start":"07:55","end":"08:00"},
                {"name":"英语","start":"08:00","end":"08:45"},
                {"name":"课间操","start":"08:45","end":"09:15"},
                {"name":"眼操","start":"09:15","end":"09:20"},
                {"name":"语文","start":"09:20","end":"10:05"},
                {"name":"课间","start":"10:05","end":"10:15"},
                {"name":"生物","start":"10:15","end":"11:00"},
                {"name":"课间","start":"11:00","end":"11:10"},
                {"name":"数学","start":"11:10","end":"11:55"},
                {"name":"午餐自由活动","start":"11:55","end":"13:00"},
                {"name":"午休","start":"13:00","end":"13:25"},
                {"name":"课间","start":"13:25","end":"13:30"},
                {"name":"历史","start":"13:30","end":"14:15"},
                {"name":"课间","start":"14:15","end":"14:25"},
                {"name":"物理","start":"14:25","end":"15:10"},
                {"name":"课间","start":"15:10","end":"15:20"},
                {"name":"眼操","start":"15:20","end":"15:25"},
                {"name":"体育","start":"15:25","end":"16:10"},
                {"name":"课间","start":"16:10","end":"16:20"},
                {"name":"化学","start":"16:20","end":"17:05"},
                {"name":"课间","start":"17:05","end":"17:15"},
                {"name":"物理课后服务","start":"17:15","end":"18:15"}
            ],
            "day5": [
                {"name":"早餐","start":"07:00","end":"07:30"},
                {"name":"晨检晨读","start":"07:30","end":"07:55"},
                {"name":"课间","start":"07:55","end":"08:00"},
                {"name":"英语","start":"08:00","end":"08:45"},
                {"name":"课间操","start":"08:45","end":"09:15"},
                {"name":"眼操","start":"09:15","end":"09:20"},
                {"name":"道德与法治","start":"09:20","end":"10:05"},
                {"name":"课间","start":"10:05","end":"10:15"},
                {"name":"数学","start":"10:15","end":"11:00"},
                {"name":"课间","start":"11:00","end":"11:10"},
                {"name":"数学","start":"11:10","end":"11:55"},
                {"name":"午餐自由活动","start":"11:55","end":"13:00"},
                {"name":"午休","start":"13:00","end":"13:25"},
                {"name":"课间","start":"13:25","end":"13:30"},
                {"name":"语文","start":"13:30","end":"14:15"},
                {"name":"课间","start":"14:15","end":"14:25"},
                {"name":"化学","start":"14:25","end":"15:10"},
                {"name":"课间","start":"15:10","end":"15:20"},
                {"name":"眼操","start":"15:20","end":"15:25"},
                {"name":"物理","start":"15:25","end":"16:10"},
                {"name":"课间","start":"16:10","end":"16:20"},
                {"name":"生物","start":"16:20","end":"17:05"},
                {"name":"课间","start":"17:05","end":"17:15"},
                {"name":"年级统测","start":"17:15","end":"18:15"}
            ],
            "day6": [{"name":"休息日 🎉","start":"00:00","end":"23:59"}],
            "day7": [{"name":"休息日 🎉","start":"00:00","end":"23:59"}]
        }
        self.course_colors = {
            "语文": (231, 76, 60), "数学": (52, 152, 219), "英语": (46, 204, 113),
            "物理": (230, 126, 34), "化学": (155, 89, 182), "历史": (192, 57, 43),
            "地理": (41, 128, 185), "政治": (142, 68, 173), "体育": (241, 196, 15),
            "自习": (149, 165, 166), "早读": (241, 148, 138), "生物": (39, 174, 96),
            "课间": (189, 195, 199), "课间操": (26, 188, 156), "午休": (127, 140, 141),
            "休息日": (46, 204, 113),"早餐":(250,180,80),"晨检晨读":(255,160,120),
            "眼操":(100,200,180),"班会":(180,100,220),"夕检":(160,160,160),
            "午餐自由活动":(120,210,160),"选修":(90,170,230),"信息技术":(70,190,210),
            "社团":(220,130,180),"课后服务":(130,210,190),"道德与法治":(142,68,173)
        }
        self.default_color = (162, 155, 254)
        self.schedule_data = None
        self.data_source = "本地"
        self.is_single_week = False
        self.main_subject = ["语文","数学","英语","物理","地理","道德与法治","生物","历史"]
        self.trigger_next_list = ["课间", "休息", "课间操", "眼操", "午饭", "午餐", "午餐自由活动", "午休", "夕检", "社团"]
        self.run_wait_time = 30
        self.already_run = False
        self.use_local_schedule()
        self.running = True
        threading.Thread(target=self.auto_fetch_schedule, daemon=True).start()
        self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.update_thread.start()
        self.main_loop()
    def auto_fetch_schedule(self):
        while self.running:
            retry_max = 3
            retry_count = 0
            success = False
            while retry_count < retry_max and not success and self.running:
                try:
                    res = requests.get(self.api_url + "?class_num=1", timeout=10, verify=True)
                    if res.status_code == 200:
                        d = res.json()
                        if d.get("status") == "success":
                            self.is_single_week = d.get("is_single_week", False)
                            lst = []
                            for i in d["data"]["courses"]:
                                lst.append({"name": i["course_name"], "start": i["start_time"][:5], "end": i["end_time"][:5]})
                            self.schedule_data = lst
                            self.data_source = "网络"
                            success = True
                            break
                except:
                    try:
                        res = requests.get(self.api_url + "?class_num=1", timeout=10, verify=False)
                        if res.status_code == 200:
                            d = res.json()
                            if d.get("status") == "success":
                                self.is_single_week = d.get("is_single_week", False)
                                lst = []
                                for i in d["data"]["courses"]:
                                    lst.append({"name": i["course_name"], "start": i["start_time"][:5], "end": i["end_time"][:5]})
                                self.schedule_data = lst
                                self.data_source = "网络"
                                success = True
                                break
                    except:
                        retry_count += 1
                time.sleep(1)
            if success:
                break
            time.sleep(30)
    def minimize_restart_daemon(self):
        while True:
            time.sleep(2)
            if self.is_window_minimized():
                try:
                    subprocess.Popen([XDOTOOL_BIN, "windowactivate", self.win_id_hex])
                except:
                    continue
    def is_window_minimized(self):
        try:
            cmd = [XPROP_BIN, "-id", self.win_id_hex, "_NET_WM_STATE"]
            out = subprocess.check_output(cmd, encoding="utf-8", timeout=2)
            return "_NET_WM_STATE_HIDDEN" in out
        except:
            return False
    def top_daemon(self):
        time.sleep(1.5)
        while True:
            try:
                if self.dragging or self.touch_dragging:
                    time.sleep(2)
                    continue
                os.system(f"{WMCTRL_BIN} -i -r {self.win_id_hex} -b add,above,sticky,skip_taskbar")
            except Exception:
                pass
            time.sleep(2)
    def get_local_week_state(self):
        week_num = datetime.now().isocalendar()[1]
        return (week_num - 1) % 2 == 1
    def move_window(self, x, y):
        x = max(0, min(x, self.screen_w - self.win_w))
        y = max(0, min(y, self.screen_h - self.win_h))
        self.window_x = x
        self.window_y = y
        try:
            os.system(f"{WMCTRL_BIN} -i -r {self.win_id_hex} -e 0,{x},{y},{self.win_w},{self.win_h}")
        except:
            pass
    def use_local_schedule(self):
        wd = datetime.now().isoweekday()
        self.schedule_data = self.local_schedule.get(f"day{wd}", self.local_schedule["day1"])
        self.data_source = "本地备用"
        self.is_single_week = self.get_local_week_state()
    def time_to_minutes(self, s):
        try:
            h, m = map(int, s.split(":"))
            return h * 60 + m
        except:
            return 0
    def get_course_color(self, n):
        cl = n
        for p in ["第1节 ", "第2节 ", "第3节 ", "第4节 ", "第5节 ", "第6节 ", "第7节 ", "第8节 "]:
            cl = cl.replace(p, "")
        for k, v in self.course_colors.items():
            if k in cl or cl in k:
                return v
        return self.default_color
    def parse_course_name(self, n):
        if "/" not in n:
            return n
        m = re.match(r"^(.+?)\((单|双)\)/(.+?)\((单|双)\)$", n)
        if m:
            n1, t1, n2, t2 = m.groups()
            if self.is_single_week:
                return n1 if t1 == "单" else n2
            else:
                return n1 if t1 == "双" else n2
        return n
    def is_dark_color(self, c):
        r, g, b = c
        return (r * 299 + g * 587 + b * 114) / 1000 < 128
    def draw_schedule(self, surf):
        surf.fill((236, 240, 241))
        if not self.schedule_data:
            return (0, 0, 0, 0)
        info_w = 150
        ax = info_w + 5
        aw = self.win_w - ax - 5
        ah = self.win_h - 10
        ay = 5
        now = datetime.now()
        dt = now.strftime("%m/%d")
        wk = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.isoweekday()]
        tm = dt_now.strftime("%H:%M")
        txt = f"{dt} {wk} {tm}"
        ts = pygame.font.SysFont("Noto Sans CJK SC",18).render(txt, True, (44, 62, 80))
        surf.blit(ts, (10, (self.win_h - ts.get_height()) // 2))
        st = [self.time_to_minutes(c["start"]) for c in self.schedule_data]
        ed = [self.time_to_minutes(c["end"]) for c in self.schedule_data]
        mn_s = min(st)
        mx_e = max(ed)
        total = mx_e - mn_s
        if total <= 0:
            total = 1
        for cur in self.schedule_data:
            s = self.time_to_minutes(cur["start"])
            e = self.time_to_minutes(cur["end"])
            x1 = ax + (s - mn_s) / total * aw
            x2 = ax + (e - mn_s) / total * aw
            if x2 - x1 < 2:
                x2 = x1 + 2
            name = self.parse_course_name(cur["name"])
            col = self.get_course_color(name)
            pygame.draw.rect(surf, col, (x1, ay, x2 - x1, ah))
            tc = (255,255,255) if self.is_dark_color(col) else (44,62,80)
            if x2 - x1 > 30:
                t = pygame.font.SysFont("Noto Sans CJK SC",18).render(name, True, tc)
            else:
                char_list = list(name)
                text_surfs = []
                for char in char_list:
                    text_surfs.append(pygame.font.SysFont("Noto Sans CJK SC",14).render(char, True, tc))
                total_h = sum(s.get_height() for s in text_surfs)
                max_w = max(s.get_width() for s in text_surfs)
                t = pygame.Surface((max_w, total_h), pygame.SRCALPHA)
                y_off = 0
                for sf in text_surfs:
                    t.blit(sf, ((max_w - sf.get_width())//2, y_off))
                    y_off += sf.get_height()
            surf.blit(t, t.get_rect(center=((x1+x2)//2, ay+ah//2)))
        return (ax, ay, aw, ah)
    def draw_progress(self, surf, para):
        if not para or not self.schedule_data:
            return
        ax, ay, aw, ah = para
        st = [self.time_to_minutes(c["start"]) for c in self.schedule_data]
        ed = [self.time_to_minutes(c["end"]) for c in self.schedule_data]
        mn_s = min(st)
        mx_e = max(ed)
        total = mx_e - mn_s
        if total <= 0:
            return
        now = dt_now
        cur = now.hour * 60 + now.minute
        if cur < mn_s:
            px = ax
        elif cur > mx_e:
            px = ax + aw
        else:
            px = ax + (cur - mn_s) / total * aw
        w = max(0, px - ax)
        if w > 0:
            ps = pygame.Surface((w, ah), pygame.SRCALPHA)
            ps.fill((200, 200, 200, 200))
            surf.blit(ps, (ax, ay))
    def check_course_trigger(self):
        try:
            if self.already_run or not self.schedule_data:
                return
            now = dt_now
            now_time_min = now.hour * 60 + now.minute
            now_sec = now.second
            data = self.schedule_data
            for idx in range(len(data)):
                end_min = self.time_to_minutes(data[idx]["end"])
                if now_time_min == end_min and 0 <= now_sec <= 10:
                    curr_name = self.parse_course_name(data[idx]["name"])
                    if curr_name in self.main_subject:
                        if idx + 1 < len(data):
                            next_name = self.parse_course_name(data[idx+1]["name"])
                            if next_name in self.trigger_next_list:
                                self.already_run = True
                                def delay_exe():
                                    try:
                                        time.sleep(self.run_wait_time)
                                        exe_path = os.path.join(doc_path,"class-over","class-over")
                                        subprocess.Popen([exe_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
                                    except Exception:
                                        pass
                                threading.Thread(target=delay_exe,daemon=True).start()
                    break
        except Exception:
            pass
    def update_loop(self):
        while self.running:
            time.sleep(1)
            pygame.event.post(pygame.event.Event(pygame.USEREVENT))
    def main_loop(self):
        axis = self.draw_schedule(self.screen)
        self.draw_progress(self.screen, axis)
        pygame.display.flip()
        while self.running:
            refresh = False
            now_t = timestamp_now
            keys = pygame.key.get_pressed()
            ctrl_press = keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]
            q_press = keys[pygame.K_q]
            if ctrl_press and q_press:
                self.running = False
                kill_all_same_process(f"{doc_path}/ClassSchedule-UOS/ClassSchedule-UOS")
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    continue
                elif e.type == pygame.USEREVENT:
                    refresh = True
                elif e.type == pygame.MOUSEBUTTONDOWN:
                    if e.button == 1:
                        self.dragging = True
                        mx, my = pygame.mouse.get_pos()
                        self.drag_rel_x = mx - self.window_x
                        self.drag_rel_y = my - self.window_y
                elif e.type == pygame.MOUSEBUTTONUP:
                    self.dragging = False
                elif e.type == pygame.MOUSEMOTION:
                    if self.dragging:
                        mx, my = pygame.mouse.get_pos()
                        nx = mx - self.drag_rel_x
                        ny = my - self.drag_rel_y
                        self.move_window(nx, ny)
                elif e.type == pygame.FINGERDOWN:
                    tx = e.x * self.win_w
                    ty = e.y * self.win_h
                    self.touch_dragging = True
                    self.touch_finger_id = e.finger_id
                    self.drag_rel_x = tx - self.window_x
                    self.drag_rel_y = ty - self.window_y
                elif e.type == pygame.FINGERUP:
                    if e.finger_id == self.touch_finger_id:
                        self.touch_dragging = False
                        self.touch_finger_id = -1
                elif e.type == pygame.FINGERMOTION:
                    if self.touch_dragging and e.finger_id == self.touch_finger_id:
                        tx = e.x * self.win_w
                        ty = e.y * self.win_h
                        nx = tx - self.drag_rel_x
                        ny = ty - self.drag_rel_y
                        self.move_window(nx, ny)
            if now_t - self.last_key_time > self.key_delay:
                flag = False
                nx = self.window_x
                ny = self.window_y
                if keys[pygame.K_LEFT]:
                    nx -= self.move_step
                    flag = True
                if keys[pygame.K_RIGHT]:
                    nx += self.move_step
                    flag = True
                if keys[pygame.K_UP]:
                    ny -= self.move_step
                    flag = True
                if keys[pygame.K_DOWN]:
                    ny += self.move_step
                    flag = True
                if flag:
                    self.move_window(nx, ny)
                    self.last_key_time = now_t
            if refresh:
                self.check_course_trigger()
                axis = self.draw_schedule(self.screen)
                self.draw_progress(self.screen, axis)
                pygame.display.flip()
            self.clock.tick(60)
        pygame.quit()
        sys.exit()
if __name__ == "__main__":
    threading.Thread(target=get_network_time_background,daemon=True).start()
    threading.Thread(target=auto_time_update,daemon=True).start()
    app = ScheduleDisplay()