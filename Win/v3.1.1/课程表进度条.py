import sys
import os
import re
import time
import ctypes
import threading
import subprocess
from datetime import datetime
from ctypes import wintypes
import ntplib
import psutil
import requests
from pynput.mouse import Controller, Listener
from datetime import datetime, timedelta, timezone
import json

from PyQt6.QtWidgets import (QApplication, QWidget, QDialog, QFormLayout,
                             QSpinBox, QLineEdit, QCheckBox, QDialogButtonBox,
                             QPushButton, QMessageBox, QTabWidget, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QHBoxLayout, QLabel,
                             QHeaderView, QAbstractItemView)
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import (QPainter, QColor, QFont, QFontMetrics, QPainterPath,
                         QPixmap, QFontDatabase, QCursor, QScreen)

VK_LBUTTON = 0x01  # 左键
VK_RBUTTON = 0x02  # 右键
VK_MBUTTON = 0x04  # 中键
mouse_controller = Controller()
client = ntplib.NTPClient()
timestamp_now = time.time()
dt_now = datetime.now()
time_lock = threading.Lock()
root_path = os.path.expanduser("~\\AppData\\Local\\Programs\\ClassSchedule")
FONT_CACHE = {}
EMOJI_FONT_CACHE = {}
_font_family_cn = None
_font_family_emj = None
base_dir = None
try:
    os.unlink(f"{root_path}\\课程表进度条\\process_lock.lock")
except:
    pass
user32 = ctypes.WinDLL("user32")
user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND,
    wintypes.INT, wintypes.INT,
    wintypes.INT, wintypes.INT,
    wintypes.UINT
]
user32.SetWindowPos.restype = wintypes.BOOL

def res_path(filename):
    global base_dir
    if getattr(sys, 'frozen', False) or hasattr(sys, '_MEIPASS'):
        exe_path = sys.executable
        base_dir = os.path.dirname(exe_path)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, filename)

font_path = res_path("NotoSansCJKsc-Black.otf")
emj_font_path = res_path("seguiemj-1.45-3d.ttf")
print(font_path)
print(emj_font_path)

try:
    settings = json.load(open(f"{base_dir}/settings.json", "r", encoding="utf-8"))
except Exception as e:
    print(e)
    settings = {}

current_class = 4
try:
    current_class = settings["class"]
except Exception as e:
    print(e)
current_class = max(1, min(6, current_class))

DEFAULT_SETTINGS = {
    "class": 4,
    "class_over_wait_time": 30,
    "class_over_countdown": 10,
    "local_schedule_file": "schedule.json",
    "absolute_path": False,
    "api_url": "https://test.m-code.top/api/class-schedule/",
    "protector_start_delay": 0,
    "class_over_status": True,
}

CLASS_OVER_DIR = os.path.join(root_path, "课程表进度条")
CLASS_OVER_EXE = os.path.join(CLASS_OVER_DIR, "class-over.exe")
CLASS_OVER_LOCK = os.path.join(CLASS_OVER_DIR, "class-over.lock")
SETTINGS_FILE = f"{base_dir}/settings.json"


def detect_class_over_state():
    exe_exists = os.path.exists(CLASS_OVER_EXE)
    lock_exists = os.path.exists(CLASS_OVER_LOCK)
    if exe_exists and not lock_exists:
        return True
    if lock_exists and not exe_exists:
        return False
    return None


def set_class_over_state(enabled):
    exe_exists = os.path.exists(CLASS_OVER_EXE)
    lock_exists = os.path.exists(CLASS_OVER_LOCK)
    if exe_exists == lock_exists:
        return False, "corrupted"
    try:
        if enabled:
            if exe_exists:
                return True, None
            os.rename(CLASS_OVER_LOCK, CLASS_OVER_EXE)
        else:
            if lock_exists:
                return True, None
            os.rename(CLASS_OVER_EXE, CLASS_OVER_LOCK)
    except OSError as e:
        return False, str(e)
    return True, None


def class_over_problem_message(reason, enabled):
    action = "启用" if enabled else "禁用"
    if reason == "corrupted":
        return (
            "自动下课组件状态异常：class-over.exe 与 class-over.lock "
            "缺失或同时存在。\n"
            f"目录：{CLASS_OVER_DIR}"
        )
    return (
        f"无法将自动下课组件重命名为{action}状态：\n{reason}\n"
        f"目录：{CLASS_OVER_DIR}"
    )


def write_settings_file(data):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def sync_class_over_on_startup(parent=None):
    target = bool(settings.get("class_over_status", False))
    ok, reason = set_class_over_state(target)
    if ok:
        return
    QMessageBox.warning(parent, "自动下课组件", class_over_problem_message(reason, target))


def _ensure_font_families():
    global _font_family_cn, _font_family_emj
    if _font_family_cn is None:
        fid = QFontDatabase.addApplicationFont(font_path)
        _font_family_cn = QFontDatabase.applicationFontFamilies(fid)[0] if fid >= 0 else ""
    if _font_family_emj is None:
        fid = QFontDatabase.addApplicationFont(emj_font_path)
        _font_family_emj = QFontDatabase.applicationFontFamilies(fid)[0] if fid >= 0 else ""


def _get_font(size, emoji):
    _ensure_font_families()
    cache = EMOJI_FONT_CACHE if emoji else FONT_CACHE
    if size not in cache:
        f = QFont(_font_family_emj if emoji else _font_family_cn)
        f.setPixelSize(size)
        cache[size] = f
    return cache[size]


def render_mixed(text, size, color, max_width=None):
    if not text:
        return None
    MIN_FONT_SIZE = 10
    base_size = int(size)

    def is_emoji_char(ch):
        code = ord(ch)
        return (0x1F300 <= code <= 0x1F9FF) or (0x2600 <= code <= 0x27BF) or (0xFE00 <= code <= 0xFEFF) or code in [0x203C, 0x2049, 0x2122, 0x2139, 0x2194, 0x2195,0x2196, 0x2197, 0x2198, 0x2199, 0x21A9, 0x21AA,0x231A, 0x231B, 0x2328, 0x23CF, 0x23E9, 0x23EA,0x23EB, 0x23EC, 0x23ED, 0x23EE, 0x23EF, 0x23F0,0x23F1, 0x23F2, 0x23F3, 0x25AA, 0x25AB, 0x25B6,0x25C0, 0x25FB, 0x25FC, 0x25FD, 0x25FE, 0x2600,0x2601, 0x260E, 0x2611, 0x2614, 0x2615, 0x261D,0x263A, 0x2648, 0x2649, 0x264A, 0x264B, 0x264C,0x264D, 0x264E, 0x264F, 0x2650, 0x2651, 0x2652,0x2653, 0x2660, 0x2663, 0x2665, 0x2666, 0x2668,0x267B, 0x267F, 0x2693, 0x26A0, 0x26A1, 0x26AA,0x26AB, 0x26BD, 0x26BE, 0x26C4, 0x26C5, 0x26CE,0x26D4, 0x26EA, 0x26F2, 0x26F3, 0x26F5, 0x26FA,0x26FD, 0x2702, 0x2705, 0x2708, 0x2709, 0x270A,0x270B, 0x270C, 0x270D, 0x270F, 0x2712, 0x2714,0x2716, 0x271D, 0x2721, 0x2728, 0x2733, 0x2734,0x2744, 0x2747, 0x274C, 0x274E, 0x2753, 0x2754,0x2755, 0x2757, 0x2763, 0x2764, 0x2795, 0x2796,0x2797, 0x2934, 0x2935, 0x2B05, 0x2B06, 0x2B07,0x2B1B, 0x2B1C, 0x2B50, 0x2B55, 0x3030, 0x303D,0x3297, 0x3299]

    def measure_width(test_size):
        c_font = _get_font(test_size, False)
        e_font = _get_font(test_size, True)
        w = 0
        for ch in text:
            f = e_font if is_emoji_char(ch) else c_font
            w += QFontMetrics(f).horizontalAdvance(ch)
        return w

    use_size = base_size
    if max_width is not None:
        while measure_width(use_size) > max_width and use_size > MIN_FONT_SIZE:
            use_size -= 1

    cn_font = _get_font(use_size, False)
    emj_font = _get_font(use_size, True)

    total_w = 0
    max_h = 0
    for ch in text:
        f = emj_font if is_emoji_char(ch) else cn_font
        fm = QFontMetrics(f)
        total_w += fm.horizontalAdvance(ch)
        ch_h = fm.ascent() + fm.descent()
        if ch_h > max_h:
            max_h = ch_h

    if total_w <= 0 or max_h <= 0:
        return None

    result = QPixmap(total_w, max_h)
    result.fill(Qt.GlobalColor.transparent)
    p = QPainter(result)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    x = 0
    for ch in text:
        f = emj_font if is_emoji_char(ch) else cn_font
        fm = QFontMetrics(f)
        p.setFont(f)
        p.setPen(QColor(*color))
        y = (max_h - (fm.ascent() + fm.descent())) // 2
        p.drawText(x, y + fm.ascent(), ch)
        x += fm.horizontalAdvance(ch)
    p.end()
    return result


def get_proc_count(exe_path):
    num = 0
    for p in psutil.process_iter():
        try:
            if p.exe() == exe_path:
                num += 1
        except:
            continue
    return num


count = get_proc_count(f"{root_path}\\课程表进度条\\课程表进度条.exe")
if count > 1:
    os._exit(0)
count2 = get_proc_count(f"{root_path}\\课程表进度条\\ClassSchedule.exe")
if count2 == 0:
    try:
        os.startfile(f"{root_path}\\课程表进度条\\ClassSchedule.exe")
    except Exception:
        pass


def kill_all_same_process(exe_path):
    for proc in psutil.process_iter(["pid", "exe"]):
        try:
            proc_exe = proc.info["exe"]
            if proc_exe == exe_path:
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def is_mouse_down():
    # 检测左键/右键/中键任意一个按下
    left = user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000
    right = user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000
    mid = user32.GetAsyncKeyState(VK_MBUTTON) & 0x8000
    return bool(left or right or mid)


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
    except Exception:
        pass


init_program()
os.environ["PYTHONIOENCODING"] = "utf-8"
MAIN_EXE_PATH = os.path.abspath(sys.executable)

try:
    exe_path = f"{root_path}\\ClassScheduleUpdater.exe"
    work_dir = root_path
    creationflags = 0
    for flag in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP",
                    "CREATE_BREAKAWAY_FROM_JOB"):
        creationflags |= getattr(subprocess, flag, 0)
    subprocess.Popen(
        [exe_path],
        cwd=work_dir,
        close_fds=True,
        creationflags=creationflags)
except Exception:
    pass


class SettingsDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        form = QFormLayout(self)
        self.class_box = QSpinBox()
        self.class_box.setRange(1, 6)
        self.class_box.setValue(int(data.get("class", 4)))
        self.wait_box = QSpinBox()
        self.wait_box.setRange(0, 60)
        self.wait_box.setSuffix(" 秒")
        self.wait_box.setValue(int(data.get("class_over_wait_time", 30)))
        self.wait_box_countdown = QSpinBox()
        self.wait_box_countdown.setRange(1, 60)
        self.wait_box_countdown.setSuffix(" 秒")
        self.wait_box_countdown.setValue(int(data.get("class_over_countdown", 10)))
        self.file_edit = QLineEdit(str(data.get("local_schedule_file", "schedule.json")))
        self.class_over_status = QCheckBox("启用")
        actual_class_over_state = detect_class_over_state()
        if actual_class_over_state is None:
            QMessageBox.warning(
                self,
                "自动下课组件",
                class_over_problem_message("corrupted", False)
                + "\n\n已将“自动下课状态”设为关闭并尝试写入 settings.json。",
            )
            data["class_over_status"] = False
            try:
                write_settings_file(data)
            except Exception as e:
                QMessageBox.critical(
                    self, "自动下课组件", f"settings.json 写入失败：\n{e}"
                )
            self.class_over_status.setChecked(False)
        else:
            self.class_over_status.setChecked(actual_class_over_state)
        self.api_edit = QLineEdit(str(data.get("api_url", "")))
        self.protector_start_delay = QSpinBox()
        self.protector_start_delay.setRange(0, 10)
        self.protector_start_delay.setSuffix(" 秒")
        self.protector_start_delay.setValue(int(data.get("protector_start_delay", 0)))
        self.reset_btn = QPushButton("恢复默认")
        self.reset_btn.clicked.connect(self.reset_values)
        self.edit_schedule_btn = QPushButton("编辑本地课表")
        self.edit_schedule_btn.clicked.connect(self.edit_schedule)
        form.addRow("班级", self.class_box)
        form.addRow("自动下课触发延迟", self.wait_box)
        form.addRow("自动下课倒计时", self.wait_box_countdown)
        form.addRow("本地课表文件", self.file_edit)
        form.addRow("自动下课状态", self.class_over_status)
        form.addRow("本地课表", self.edit_schedule_btn)
        form.addRow("API 地址", self.api_edit)
        form.addRow("保护器延迟", self.protector_start_delay)
        form.addRow(self.reset_btn)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        assert isinstance(buttons, QDialogButtonBox)

        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        assert save_btn is not None
        assert cancel_btn is not None
        save_btn.setText("保存")
        cancel_btn.setText("取消")

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def accept(self):
        enabled = self.class_over_status.isChecked()
        ok, reason = set_class_over_state(enabled)
        if not ok:
            if enabled:
                QMessageBox.warning(
                    self,
                    "自动下课组件",
                    class_over_problem_message(reason, enabled)
                    + "\n\n无法启用自动下课组件，本次设置不会保存，请修复后重试。",
                )
                return
            QMessageBox.warning(
                self,
                "自动下课组件",
                class_over_problem_message(reason, enabled)
                + "\n\n仍将保存设置（自动下课状态：关闭）。",
            )
        super().accept()

    def get_values(self):
        filename = self.file_edit.text().strip()
        return {
            "class": self.class_box.value(),
            "class_over_wait_time": self.wait_box.value(),
            "class_over_countdown": self.wait_box_countdown.value(),
            "local_schedule_file": filename,
            "class_over_status": self.class_over_status.isChecked(),
            "api_url": self.api_edit.text().strip(),
            "protector_start_delay": self.protector_start_delay.value(),
            "absolute_path": os.path.isabs(filename),
        }

    def reset_values(self):
        reply = QMessageBox.warning(
            self,
            "恢复默认",
            "确定要恢复默认设置吗？\n\n当前所有设置将被默认内容覆盖，此操作无法撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.class_box.setValue(int(DEFAULT_SETTINGS["class"]))
        self.wait_box.setValue(int(DEFAULT_SETTINGS["class_over_wait_time"]))
        self.wait_box_countdown.setValue(int(DEFAULT_SETTINGS["class_over_countdown"]))
        self.file_edit.setText(DEFAULT_SETTINGS["local_schedule_file"])
        self.class_over_status.setChecked(bool(DEFAULT_SETTINGS["class_over_status"]))
        self.api_edit.setText(DEFAULT_SETTINGS["api_url"])
        self.protector_start_delay.setValue(int(DEFAULT_SETTINGS["protector_start_delay"]))
        self.accept()

    def edit_schedule(self):
        filename = self.file_edit.text().strip()
        if not filename:
            QMessageBox.warning(self, "编辑本地课表", "请先填写本地课表文件路径。")
            return
        if os.path.isabs(filename):
            schedule_path = filename
        else:
            schedule_path = f"{base_dir}/{filename}"
        schedule_path = os.path.abspath(schedule_path)

        schedule_data = None
        if os.path.exists(schedule_path):
            try:
                with open(schedule_path, "r", encoding="utf-8") as f:
                    schedule_data = json.load(f)
            except Exception as e:
                QMessageBox.critical(self, "编辑本地课表", f"课表文件解析失败：\n{e}")
                return
        else:
            reply = QMessageBox.question(
                self,
                "编辑本地课表",
                f"课表文件不存在：\n{schedule_path}\n\n是否以空白课表新建？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            schedule_data = {}

        editor = ScheduleEditorDialog(schedule_path, schedule_data, self)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            new_data = editor.get_data()
        except ValueError as e:
            QMessageBox.critical(self, "编辑本地课表", str(e))
            return
        try:
            parent_dir = os.path.dirname(schedule_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(schedule_path, "w", encoding="utf-8") as f:
                json.dump(new_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            QMessageBox.critical(self, "编辑本地课表", f"课表保存失败：\n{e}")
            return
        QMessageBox.information(
            self, "编辑本地课表", "课表已保存。\n点击设置窗口的“保存”后生效。"
        )


WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
SCHEDULE_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class ScheduleEditorDialog(QDialog):
    def __init__(self, file_path, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑本地课表")
        self.resize(720, 580)
        self.file_path = file_path
        self.tables = {}

        layout = QVBoxLayout(self)
        path_label = QLabel(f"文件：{file_path}")
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(path_label)

        self.tabs = QTabWidget()
        for day_idx in range(1, 8):
            table = QTableWidget(0, 3)
            table.setHorizontalHeaderLabels(["课程名称", "开始时间", "结束时间"])
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            header = table.horizontalHeader()
            assert header is not None
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            courses = []
            if isinstance(data, dict):
                courses = data.get(f"day{day_idx}", []) or []
            for course in courses:
                if not isinstance(course, dict):
                    continue
                self._add_row(
                    table,
                    str(course.get("name", "")),
                    str(course.get("start", "")),
                    str(course.get("end", "")),
                )
            tab_widget = QWidget()
            tab_layout = QVBoxLayout(tab_widget)
            tab_layout.addWidget(table)
            btn_row = QHBoxLayout()
            add_btn = QPushButton("添加课程")
            del_btn = QPushButton("删除选中课程")
            add_btn.clicked.connect(lambda _, t=table: self._add_row(t))
            del_btn.clicked.connect(lambda _, t=table: self._delete_rows(t))
            btn_row.addWidget(add_btn)
            btn_row.addWidget(del_btn)
            btn_row.addStretch()
            tab_layout.addLayout(btn_row)
            self.tabs.addTab(tab_widget, WEEKDAY_NAMES[day_idx - 1])
            self.tables[day_idx] = table
        layout.addWidget(self.tabs)

        bottom_row = QHBoxLayout()
        self.reveal_btn = QPushButton("在文件夹中显示")
        self.reveal_btn.clicked.connect(self.reveal_in_explorer)
        bottom_row.addWidget(self.reveal_btn)
        bottom_row.addStretch()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        assert save_btn is not None
        assert cancel_btn is not None
        save_btn.setText("保存")
        cancel_btn.setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        bottom_row.addWidget(buttons)
        layout.addLayout(bottom_row)

    @staticmethod
    def _add_row(table, name="", start="08:00", end="08:45"):
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem(name))
        table.setItem(row, 1, QTableWidgetItem(start))
        table.setItem(row, 2, QTableWidgetItem(end))

    @staticmethod
    def _delete_rows(table):
        rows = sorted({idx.row() for idx in table.selectedIndexes()}, reverse=True)
        for row in rows:
            table.removeRow(row)

    def get_data(self):
        result = {}
        for day_idx in range(1, 8):
            table = self.tables[day_idx]
            weekday = WEEKDAY_NAMES[day_idx - 1]
            courses = []
            for row in range(table.rowCount()):
                name_item = table.item(row, 0)
                start_item = table.item(row, 1)
                end_item = table.item(row, 2)
                name = name_item.text().strip() if name_item else ""
                start = start_item.text().strip() if start_item else ""
                end = end_item.text().strip() if end_item else ""
                if not name and not start and not end:
                    continue
                if not name:
                    self.tabs.setCurrentIndex(day_idx - 1)
                    table.setCurrentCell(row, 0)
                    raise ValueError(f"{weekday} 第 {row + 1} 行课程名称为空。")
                try:
                    start_norm = self._normalize_time(start)
                    end_norm = self._normalize_time(end)
                except ValueError as e:
                    self.tabs.setCurrentIndex(day_idx - 1)
                    table.setCurrentCell(row, 1)
                    raise ValueError(
                        f"{weekday} 第 {row + 1} 行时间格式不正确：{e}\n应为 HH:MM（24 小时制）。"
                    )
                courses.append({"name": name, "start": start_norm, "end": end_norm})
            result[f"day{day_idx}"] = courses
        return result

    @staticmethod
    def _normalize_time(value):
        match = SCHEDULE_TIME_RE.match(value)
        if not match:
            raise ValueError(value)
        return f"{int(match.group(1)):02d}:{match.group(2)}"

    def accept(self):
        try:
            self.get_data()
        except ValueError as e:
            QMessageBox.critical(self, "编辑本地课表", str(e))
            return
        super().accept()

    def reveal_in_explorer(self):
        try:
            path = os.path.normpath(self.file_path)
            if os.path.exists(path):
                subprocess.Popen(f'explorer /select,"{path}"')
                return
            parent = os.path.dirname(path)
            if parent and os.path.isdir(parent):
                os.startfile(parent)
            else:
                QMessageBox.warning(
                    self, "在文件夹中显示", f"文件所在文件夹不存在：\n{parent}"
                )
        except Exception as e:
            QMessageBox.critical(self, "在文件夹中显示", f"无法打开文件资源管理器：\n{e}")


class ScheduleDisplay(QWidget):
    def __init__(self):
        super().__init__()
        app = QApplication.instance()
        assert isinstance(app, QApplication)
        screen = app.primaryScreen()
        assert isinstance(screen, QScreen)
        geo = screen.geometry()
        self.screen_w = geo.width()
        self.screen_h = geo.height()
        self.win_w = int(self.screen_w * 0.9)
        self.win_h = 50
        self.corner_radius = 12
        print(f"Screen size: {self.screen_w}x{self.screen_h}, Window size: {self.win_w}x{self.win_h}")
        self.move_step = 6
        self.is_onclick_event_run = False
        self.mode = "normal"
        # self.key_delay = 0.01
        # self.last_key_time = 0
        self.window_x = (self.screen_w - self.win_w) // 2
        self.window_y = 0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setGeometry(self.window_x, self.window_y, self.win_w, self.win_h)

        self.win_title = "课表进度条"
        self.setWindowTitle(self.win_title)

        self.win_id_dec = int(self.winId())
        self.win_id_hex = hex(self.win_id_dec)
        print(self.win_id_hex)
        self._setup_windows_layered()

        self._keys_pressed = set()
        self._need_refresh = False
        self._drag_mx = 0
        self._drag_my = 0

        threading.Thread(target=self.top_daemon, daemon=True).start()
        threading.Thread(target=self.minimize_restart_daemon, daemon=True).start()
        self.need_hide = False
        self.need_show = False
        self.need_change_opacity = False
        self.target_opacity = 1.0
        self.now_opacity = 1.0
        self.click_to_hide = False
        self.teaching = False
        self.gradient_count = 0
        self.gradient_hide_stuck = False
        self.after_second_click_running = False
        self.hiding = False
        self.fetching_schedule = False
        self._hover_hide_inside_since = None
        self._hover_hide_outside_since = None
        listener = Listener(on_click=self.on_click)
        listener.start()
        self.dragging = False
        self._drag_press_time = 0.0
        self._settings_open = False

        try:
            self.api_url = settings["api_url"]
        except Exception as e:
            self.api_url = "https://test.m-code.top/api/class-schedule/"
        try:
            if settings["absolute_path"]:
                if os.path.exists(settings["local_schedule_file"]):
                    self.local_schedule = json.load(open(settings["local_schedule_file"], "r", encoding="utf-8"))
                else:
                    self.local_schedule = {"day1": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day2": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day3": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day4": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day5": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day6": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day7": [{"name":"暂无课程","start":"00:00","end":"23:59"}]}
            else:
                if os.path.exists(f"{base_dir}/{settings['local_schedule_file']}"):
                    self.local_schedule = json.load(open(f"{base_dir}/{settings['local_schedule_file']}", "r", encoding="utf-8"))
                else:
                    self.local_schedule = {"day1": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day2": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day3": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day4": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day5": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day6": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day7": [{"name":"暂无课程","start":"00:00","end":"23:59"}]}
        except Exception as e:
            print(e)
            self.local_schedule = {"day1": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day2": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day3": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day4": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day5": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day6": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day7": [{"name":"暂无课程","start":"00:00","end":"23:59"}]}
        self.course_colors = {
            "语文": (231, 76, 60), "数学": (52, 152, 219), "英语": (46, 204, 113),
            "物理": (230, 126, 34), "化学": (155, 89, 182), "历史": (192, 57, 43),
            "地理": (41, 128, 185), "政治": (142, 68, 173), "体育": (241, 196, 15),
            "自习": (149, 165, 166), "早读": (241, 148, 138), "生物": (39, 174, 96),
            "课间": (250, 250, 200), "课间操": (26, 188, 156), "午休": (127, 140, 141),
            "休息日": (46, 204, 113),"早餐":(250,180,80),"晨检晨读":(255,160,120),
            "眼操":(100,200,200),"班会":(180,100,220),"夕检":(160,160,160),
            "午餐自由活动":(120,210,160),"选修":(90,170,230),"信息技术":(70,190,210),
            "社团":(220,130,180),"课后服务":(130,210,190),"道德与法治":(142,68,173),"道法":(142,68,173),
            "艺术课":(255,140,190),"年级统测":(180,120,90),"晚餐":(255,180,80),"晚自习":(149,110,166)
        }
        self.default_color = (162, 155, 254)
        self.schedule_data = None
        self.data_source = "本地"
        self.is_single_week = False
        self.main_subject = ["语文","数学","英语","物理","地理","道德与法治","生物","化学","历史","政治","道法","语文晚补","数学晚补","英语晚补","物理晚补"]
        self.trigger_next_list = ["课间", "休息", "课间操", "眼操", "午饭", "午餐", "午餐自由活动", "午休", "夕检", "社团","晚餐"]
        try:
            self.run_wait_time = settings["class_over_wait_time"]
        except Exception as e:
            self.run_wait_time = 30
        self.class_over_running = False
        self.use_local_schedule()
        self.running = True
        threading.Thread(target=self.auto_fetch_schedule, daemon=True).start()
        threading.Thread(target=self.keep_protect_process, daemon=True).start()
        threading.Thread(target=self.background_listener, daemon=True).start()
        self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.update_thread.start()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

        self.update()

    def _setup_windows_layered(self):
        if sys.platform != "win32":
            return
        try:
            user32_l = ctypes.windll.user32
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x80
            WS_EX_APPWINDOW = 0x4000
            style = user32_l.GetWindowLongPtrW(self.win_id_dec, GWL_EXSTYLE)
            style |= WS_EX_TOOLWINDOW
            style &= ~WS_EX_APPWINDOW
            user32_l.SetWindowLongPtrW(self.win_id_dec, GWL_EXSTYLE, style)
        except Exception:
            pass

    def auto_fetch_schedule(self):
        self.fetching_schedule = True
        while self.running:
            retry_max = 3
            retry_count = 0
            success = False
            while retry_count < retry_max and not success and self.running:
                try:
                    res = requests.get(self.api_url + f"?class_num={current_class}", timeout=10, verify=True)
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
                        res = requests.get(self.api_url + f"?class_num={current_class}", timeout=10, verify=False)
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
                self.fetching_schedule = False
                break
            time.sleep(30)

    def minimize_restart_daemon(self):
        while True:
            time.sleep(2)
            if self._settings_open:
                continue
            if self.is_window_minimized():
                try:
                    ctypes.windll.user32.ShowWindow(self.win_id_dec, 9)
                    ctypes.windll.user32.SetForegroundWindow(self.win_id_dec)
                except:
                    continue
            if not is_mouse_down() and not user32.GetForegroundWindow() == self.win_id_dec and not self.hiding:
                ctypes.windll.user32.SetForegroundWindow(self.win_id_dec)

    def is_window_minimized(self):
        try:
            return ctypes.windll.user32.IsIconic(self.win_id_dec) != 0
        except:
            return False

    def top_daemon(self):
        time.sleep(1.5)
        while True:
            try:
                if not self.dragging:
                    HWND_TOPMOST = -1
                    SWP_NOSIZE   = 0x0001
                    SWP_NOMOVE   = 0x0002
                    SWP_NOACTIVATE = 0x0010
                    user32.SetWindowPos(
                        self.win_id_dec,
                        HWND_TOPMOST,
                        0, 0, 0, 0,
                        SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE   # = 0x0013
                    )
            except Exception:
                pass
            time.sleep(2)

    def get_local_week_state(self):
        week_num = datetime.now().isocalendar()[1]
        return (week_num - 1) % 2 == 1

    def move_window(self, x, y, mx, my):
        target_x = x - mx
        target_y = y - my

        if target_x < 0:
            self.window_x = 0
        elif target_x > self.screen_w - self.win_w:
            self.window_x = self.screen_w - self.win_w
        else:
            self.window_x = target_x

        if target_y < 0:
            self.window_y = 0
        elif target_y > self.screen_h - self.win_h:
            self.window_y = self.screen_h - self.win_h
        else:
            self.window_y = target_y

        self.move(self.window_x, self.window_y)

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

    def draw_schedule(self, painter):
        painter.fillRect(0, 0, self.win_w, self.win_h, QColor(236, 240, 241, 255))
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
        ts = render_mixed(txt, 18, (44, 62, 80))
        if ts is None:
            ts = None
        if ts is not None:
            painter.drawPixmap(7, (self.win_h - ts.height()) // 2, ts)
        st = [self.time_to_minutes(c["start"]) for c in self.schedule_data]
        ed = [self.time_to_minutes(c["end"]) for c in self.schedule_data]
        mn_s = min(st)
        mx_e = max(ed)
        total = mx_e - mn_s
        if total <= 0:
            total = 1
        drawn_items = []
        for cur in self.schedule_data:
            s = self.time_to_minutes(cur["start"])
            e = self.time_to_minutes(cur["end"])
            x1 = ax + (s - mn_s) / total * aw
            x2 = ax + (e - mn_s) / total * aw
            if x2 - x1 < 2:
                x2 = x1 + 2
            name = self.parse_course_name(cur["name"])
            col = self.get_course_color(name)
            painter.fillRect(int(x1), int(ay), int(x2 - x1), int(ah), QColor(col[0], col[1], col[2]))
            tc = (255,255,255) if self.is_dark_color(col) else (44,62,80)
            item_texts = []
            if x2 - x1 > 30 and name != "晨检晨读":
                max_w = int(x2 - x1 - 4)
                t = render_mixed(name, 18, tc, max_w)
                if t is None:
                    t = render_mixed(name, 18, tc)
                if t is not None:
                    tx = int((x1 + x2) // 2 - t.width() // 2)
                    ty = int(ay + ah // 2 - t.height() // 2)
                    painter.drawPixmap(tx, ty, t)
                    item_texts.append({"text": name, "size": 18, "max_w": max_w, "x": tx, "y": ty})
            else:
                half = (len(name) + 1) // 2
                lines = [name[:half], name[half:]]
                line_pixmaps = []
                line_texts = [ln for ln in lines if ln]
                for line in line_texts:
                    ls = render_mixed(line, 14, tc)
                    if ls is None:
                        ls = render_mixed(line, 14, tc)
                    if ls is not None:
                        line_pixmaps.append(ls)
                if line_pixmaps:
                    total_h = sum(p.height() for p in line_pixmaps)
                    max_w = max(p.width() for p in line_pixmaps)
                    y_off = 0
                    cx_center = (x1 + x2) // 2
                    cy_center = ay + ah // 2
                    for ln, sf in zip(line_texts, line_pixmaps):
                        sx = int(cx_center - max_w // 2 + (max_w - sf.width()) // 2)
                        sy = int(cy_center - total_h // 2 + y_off)
                        painter.drawPixmap(sx, sy, sf)
                        item_texts.append({"text": ln, "size": 14, "max_w": None, "x": sx, "y": sy})
                        y_off += sf.height()
            drawn_items.append({"start": s, "end": e, "color": col, "texts": item_texts})
        self._drawn_items = drawn_items
        return (ax, ay, aw, ah)

    def draw_progress(self, painter, para):
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
            painter.fillRect(int(ax), int(ay), int(w), int(ah), QColor(200, 200, 200, 200))
            cur_item = None
            for it in getattr(self, "_drawn_items", []):
                if it["start"] <= cur < it["end"]:
                    cur_item = it
                    break
            if cur_item is not None and cur_item["texts"]:
                tc = (255, 255, 255) if self.is_dark_color(cur_item["color"]) else (44, 62, 80)
                for d in cur_item["texts"]:
                    if d["max_w"] is not None:
                        t = render_mixed(d["text"], d["size"], tc, d["max_w"])
                        if t is None:
                            t = render_mixed(d["text"], d["size"], tc)
                    else:
                        t = render_mixed(d["text"], d["size"], tc)
                    if t is not None:
                        painter.drawPixmap(d["x"], d["y"], t)

    def draw_schedule_simple(self, painter):
        painter.fillRect(0, 0, self.win_w, self.win_h, QColor(236, 240, 241, 255))
        if not self.schedule_data:
            return (0, 0, 0, 0)
        info_w = 150
        ax = info_w + 5
        ay = 5
        aw = self.win_w - ax - 5
        ah = self.win_h - 10
        now = dt_now
        now_seconds = now.hour * 3600 + now.minute * 60 + now.second
        tick = int(now.timestamp()) // 5
        if getattr(self, "simple_tick", None) != tick:
            current = None
            for course in self.schedule_data:
                start = self.time_to_minutes(course["start"]) * 60
                end = self.time_to_minutes(course["end"]) * 60
                if start <= now_seconds < end:
                    current = course
                    break
            self.simple_tick = tick
            self.simple_course = current
            if current is None:
                self.simple_progress = 0
            else:
                start = self.time_to_minutes(current["start"]) * 60
                end = self.time_to_minutes(current["end"]) * 60
                duration = max(1, end - start)
                self.simple_progress = max(0, min(1, (now_seconds - start) / duration))
        current = getattr(self, "simple_course", None)
        if current is None:
            name = "暂无课程"
            color = (189, 195, 199)
            self.simple_progress = 0
            self._simple_elapsed = 0
            self._simple_remaining = 0
        else:
            name = self.parse_course_name(current["name"])
            color = self.get_course_color(name)
            cs = self.time_to_minutes(current["start"]) * 60
            ce = self.time_to_minutes(current["end"]) * 60
            dur = max(1, ce - cs)
            self.simple_progress = max(0, min(1, (now_seconds - cs) / dur))
            self._simple_elapsed = max(0, now_seconds - cs)
            self._simple_remaining = max(0, ce - now_seconds)
        self._simple_color = color
        painter.fillRect(int(ax), int(ay), int(aw), int(ah), QColor(color[0], color[1], color[2]))
        text_color = (255, 255, 255) if self.is_dark_color(color) else (44, 62, 80)
        dt_str = now.strftime("%m/%d")
        wk = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.isoweekday()]
        tm_str = now.strftime("%H:%M")
        time_txt = f"{dt_str} {wk} {tm_str}"
        time_surf = render_mixed(time_txt, 18, (44, 62, 80))
        if time_surf is None:
            time_surf = render_mixed(time_txt, 18, (44, 62, 80))
        if time_surf is not None:
            painter.drawPixmap(7, (self.win_h - time_surf.height()) // 2, time_surf)
        text = render_mixed(name, 24, text_color, int(aw - 8))
        self._simple_name_pixmap = None
        if text is not None:
            tx = int(ax + aw // 2 - text.width() // 2)
            ty = int(ay + ah // 2 - text.height() // 2)
            painter.drawPixmap(tx, ty, text)
            self._simple_name_pixmap = (text, tx, ty)
        return (ax, ay, aw, ah)

    def draw_progress_simple(self, painter, para):
        if not para or not self.schedule_data:
            return
        ax, ay, aw, ah = para
        progress = getattr(self, "simple_progress", 0)
        width = int(aw * progress)
        if width > 0:
            painter.fillRect(int(ax), int(ay), int(width), int(ah), QColor(200, 200, 200, 250))

    def draw_simple_name_on_top(self, painter):
        name_pixmap = getattr(self, "_simple_name_pixmap", None)
        if name_pixmap is not None:
            pixmap, tx, ty = name_pixmap
            painter.drawPixmap(tx, ty, pixmap)

    def format_simple_time(self, sec):
        sec = int(max(0, sec))
        m, s = divmod(sec, 60)
        if m > 0:
            return f"{m}m{s:02d}s"
        return f"{s:02d}s"

    def draw_simple_time(self, painter, para):
        if not para or getattr(self, "simple_course", None) is None:
            return
        ax, ay, aw, ah = para
        progress = getattr(self, "simple_progress", 0)
        head_x = ax + aw * progress
        if head_x <= ax:
            return
        name_info = getattr(self, "_simple_name_pixmap", None)
        name_left = name_info[1] if name_info is not None else ax + aw
        size = 16
        pad = 4
        dark = (44, 62, 80)
        color = getattr(self, "_simple_color", (128, 128, 128))

        def put(pix, x):
            y = int(ay + (ah - pix.height()) / 2)
            painter.drawPixmap(int(x), y, pix)

        if head_x < name_left - 2:
            pix = render_mixed(self.format_simple_time(self._simple_elapsed), size, dark)
            if pix is None:
                return
            x = head_x - pix.width() - pad
            if x < ax + pad:
                x = ax + pad
            put(pix, x)
        else:
            txt = self.format_simple_time(self._simple_remaining)
            probe = render_mixed(txt, size, dark)
            if probe is None:
                return
            x = ax + aw - probe.width() - pad
            if head_x >= x:
                pix = probe
            else:
                tc = (255, 255, 255) if self.is_dark_color(color) else dark
                pix = render_mixed(txt, size, tc)
                if pix is None:
                    pix = probe
            put(pix, x)

    def check_course_trigger(self):
        try:
            if self.class_over_running or not self.schedule_data:
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
                                self.class_over_running = True
                                def delay_start():
                                    try:
                                        time.sleep(self.run_wait_time)
                                        exe_path = os.path.join(root_path,"课程表进度条","class-over.exe")
                                        os.startfile(exe_path)
                                        time.sleep(max(0, min(80, 80 - self.run_wait_time)))
                                    except Exception:
                                        pass
                                    self.class_over_running = False
                                threading.Thread(target=delay_start,daemon=True).start()
                    break
        except Exception:
            pass

    def after_second_click(self):
        time.sleep(2)
        try:
            self.need_show = True
        except Exception:
            pass
        self.click_to_hide = False
        self.after_second_click_running = False

    def on_click(self, x, y, button, pressed):
        if pressed and not self.after_second_click_running and self.hiding:
            self.after_second_click_running = True
            threading.Thread(target=self.after_second_click,daemon=True).start()

    def keep_protect_process(self):
        while self.running:
            count = get_proc_count(f"{root_path}\\课程表进度条\\ClassSchedule.exe")
            if count == 0:
                try:
                    os.startfile(f"{root_path}\\课程表进度条\\ClassSchedule.exe")
                except Exception:
                    pass
            time.sleep(2)

    def is_wps_presenting(self) -> bool:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindow.restype = wintypes.BOOL
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        user32.GetMonitorInfoW.restype = wintypes.BOOL

        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        EXCLUDE_CLASSES = {
            "IME", "MSCTFIME UI", "CiceroUIWndFrame",
            "Chrome_SystemMessageWindow", "Chrome_WidgetWin_0",
        }

        TITLE_KEYWORDS = ("WPS Presentation Slide Show", "幻灯片放映")

        _pname_cache = {}

        def _get_text(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            return buf.value

        def _get_class(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buf, 256)
            return buf.value

        def _get_pname(hwnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            pid = pid.value
            if pid in _pname_cache:
                return _pname_cache[pid]

            h = kernel32.OpenProcess(0x1000, False, pid)
            name = ""
            if h:
                try:
                    size = wintypes.DWORD(1024)
                    buf = ctypes.create_unicode_buffer(size.value)
                    if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                        name = buf.value.rsplit("\\", 1)[-1]
                finally:
                    kernel32.CloseHandle(h)

            _pname_cache[pid] = name
            return name

        def _is_fullscreen_on_its_monitor(hwnd):
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return False

            hmon = user32.MonitorFromWindow(hwnd, 2)
            if not hmon:
                return False

            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                return False

            mon = mi.rcMonitor
            return (
                abs(rect.left - mon.left) <= 2 and
                abs(rect.top - mon.top) <= 2 and
                abs(rect.right - mon.right) <= 2 and
                abs(rect.bottom - mon.bottom) <= 2
            )

        found = [False]

        @EnumWindowsProc
        def enum_proc(hwnd, lparam):
            if _get_pname(hwnd).lower() != "wpp.exe":
                return True
            if _get_class(hwnd) in EXCLUDE_CLASSES:
                return True
            if not user32.IsWindowVisible(hwnd):
                return True
            if user32.IsIconic(hwnd):
                return True
            if not _is_fullscreen_on_its_monitor(hwnd):
                return True
            title = _get_text(hwnd)
            if not any(k in title for k in TITLE_KEYWORDS):
                return True

            found[0] = True
            return False

        user32.EnumWindows(enum_proc, 0)
        return found[0]

    def is_seewo_visible(self) -> bool:
        user32_l = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32_l.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
        user32_l.EnumWindows.restype = wintypes.BOOL
        user32_l.IsWindow.argtypes = [wintypes.HWND]
        user32_l.IsWindow.restype = wintypes.BOOL
        user32_l.IsWindowVisible.argtypes = [wintypes.HWND]
        user32_l.IsWindowVisible.restype = wintypes.BOOL
        user32_l.IsIconic.argtypes = [wintypes.HWND]
        user32_l.IsIconic.restype = wintypes.BOOL
        user32_l.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32_l.GetWindowTextLengthW.restype = ctypes.c_int
        user32_l.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32_l.GetWindowTextW.restype = ctypes.c_int
        user32_l.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32_l.GetClassNameW.restype = ctypes.c_int
        user32_l.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32_l.GetWindowThreadProcessId.restype = wintypes.DWORD
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        EXCLUDE_CLASSES = {
            "IME", "MSCTFIME UI", "CiceroUIWndFrame", "GDI+ Hook Window Class",
            "SEEWO_TOUCH_WIN_CLASS", "Chrome_SystemMessageWindow", "Chrome_WidgetWin_0",
            "Base_PowerMessageWindow", "ExtendedResizeNativeWindow",
            ".NET-BroadcastEventWindow.37a9c05.0",
        }
        EXCLUDE_TITLES = {
            "Hidden Window", "MediaContextNotificationWindow", "SystemResourceNotifyWindow",
            "seewo_usbkey_message", "Default IME", "MSCTFIME UI",
        }
        _pname_cache = {}
        def _get_text(hwnd):
            n = user32_l.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32_l.GetWindowTextW(hwnd, buf, n + 1)
            return buf.value
        def _get_class(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32_l.GetClassNameW(hwnd, buf, 256)
            return buf.value
        def _get_pname(hwnd):
            pid = wintypes.DWORD()
            user32_l.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            pid = pid.value
            if pid in _pname_cache:
                return _pname_cache[pid]
            h = kernel32.OpenProcess(0x1000, False, pid)
            name = ""
            if h:
                try:
                    size = wintypes.DWORD(1024)
                    buf = ctypes.create_unicode_buffer(size.value)
                    if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                        name = buf.value.rsplit("\\", 1)[-1]
                finally:
                    kernel32.CloseHandle(h)
            _pname_cache[pid] = name
            return name
        def _is_main_window(hwnd):
            if not user32_l.IsWindow(hwnd):
                return False
            pname = _get_pname(hwnd).lower()
            if pname != "easinote.exe" and "easinote" not in pname and "seewo" not in pname:
                return False
            cls = _get_class(hwnd)
            title = _get_text(hwnd)
            if cls in EXCLUDE_CLASSES or title in EXCLUDE_TITLES:
                return False
            if cls.startswith("HwndWrapper[EasiNote;;"):
                return True
            return bool(title)
        found = [False]
        @EnumWindowsProc
        def enum_proc(hwnd, lparam):
            if _is_main_window(hwnd):
                if user32_l.IsWindowVisible(hwnd) and not user32_l.IsIconic(hwnd):
                    found[0] = True
                    return False
            return True
        user32_l.EnumWindows(enum_proc, 0)
        return found[0]

    def is_teaching(self):
        if self.is_wps_presenting() or self.is_seewo_visible():
            return True
        return False

    def background_listener(self):
        while self.running:
            if not self._hover_hide_inside_since:
                self.teaching = self.is_teaching()
                if self.teaching:
                    self.target_opacity = 0.3
                    self.now_opacity = 0.3
                    self.need_change_opacity = True
                    self.mode = "simple"
                elif self.now_opacity == 0.3:
                    self.target_opacity = 1.0
                    self.now_opacity = 1.0
                    self.need_change_opacity = True
                    self.mode = "normal"
            time.sleep(3)

    def click_event(self):
        time.sleep(0.3)
        if self.dragging:
            while self.dragging:
                if not self.dragging:
                    break
                time.sleep(1)
        else:
            self.need_hide = True
            self.click_to_hide = True
        self.is_onclick_event_run = False

    def update_loop(self):
        while self.running:
            time.sleep(1)
            self._need_refresh = True

    def open_settings_dialog(self):
        global current_class
        if self._settings_open:
            return
        self._settings_open = True
        self.need_hide = False
        self.click_to_hide = False
        self.gradient_count = 0
        dlg = SettingsDialog(settings, self)
        app = QApplication.instance()
        assert isinstance(app, QApplication)
        screen = app.primaryScreen()
        assert screen is not None
        geo = screen.availableGeometry()
        hint = dlg.sizeHint()
        dlg.move(
            max(geo.left(), geo.center().x() - hint.width() // 2),
            max(geo.top(), geo.center().y() - hint.height() // 2),
        )
        try:
            if dlg.exec() == QDialog.DialogCode.Accepted:
                data = dlg.get_values()
                with open(f"{base_dir}/settings.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                settings.clear()
                settings.update(data)
                current_class = max(1, min(6, data["class"]))
                self.api_url = data["api_url"]
                self.run_wait_time = data["class_over_wait_time"]
                try:
                    if settings["absolute_path"]:
                        self.local_schedule = json.load(open(settings["local_schedule_file"], "r", encoding="utf-8"))
                    else:
                        self.local_schedule = json.load(open(f"{base_dir}/{settings['local_schedule_file']}", "r", encoding="utf-8"))
                except Exception as e:
                    print(e)
                    self.local_schedule = {"day1": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day2": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day3": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day4": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day5": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day6": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day7": [{"name":"暂无课程","start":"00:00","end":"23:59"}]}
                if not self.fetching_schedule:
                    threading.Thread(target=self.auto_fetch_schedule, daemon=True).start()
                self.update()
        finally:
            self._settings_open = False
            self.need_hide = False
            self.need_show = False

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Comma and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.open_settings_dialog()
            return
        if key == Qt.Key.Key_Q and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.running = False
            try:
                with open(f"{root_path}\\课程表进度条\\process_lock.lock", "w") as f:
                    f.write("1")
            except:
                pass
            self.timer.stop()
            app = QApplication.instance()
            if app is not None:
                app.quit()
            return
        self._keys_pressed.add(key)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        self._keys_pressed.discard(event.key())
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self._drag_press_time = time.time()
            if not self.is_onclick_event_run:
                threading.Thread(target=self.click_event, daemon=True).start()
            self.is_onclick_event_run = True
            pos = event.position().toPoint()
            mx = pos.x()
            my = pos.y()
            if mx < 0:
                mx = 0
            elif mx > self.win_w:
                mx = self.win_w
            if my < 0:
                my = 0
            elif my > self.win_h:
                my = self.win_h
            self._drag_mx = mx
            self._drag_my = my
            time.sleep(0.1)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False

    def mouseMoveEvent(self, event):
        if self.dragging:
            gp = event.globalPosition().toPoint()
            self.move_window(gp.x(), gp.y(), self._drag_mx, self._drag_my)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        radius = max(0, min(self.corner_radius, min(self.win_w, self.win_h) // 2))
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.win_w, self.win_h), radius, radius)
        painter.setClipPath(path)
        if self.mode == "normal":
            axis = self.draw_schedule(painter)
            self.draw_progress(painter, axis)
        else:
            axis = self.draw_schedule_simple(painter)
            self.draw_progress_simple(painter, axis)
            self.draw_simple_name_on_top(painter)
            self.draw_simple_time(painter, axis)
        painter.end()

    def _tick(self):
        if self._settings_open:
            return
        flag = False
        nx = self.window_x
        ny = self.window_y
        keys = self._keys_pressed
        if Qt.Key.Key_Left in keys:
            nx -= self.move_step
            flag = True
        if Qt.Key.Key_Right in keys:
            nx += self.move_step
            flag = True
        if Qt.Key.Key_Up in keys:
            ny -= self.move_step
            flag = True
        if Qt.Key.Key_Down in keys:
            ny += self.move_step
            flag = True
        if flag:
            self.move_window(nx, ny, 0, 0)
        if self._need_refresh:
            self._need_refresh = False
            self.check_course_trigger()
            self.update()
        if self.dragging and not is_mouse_down() and time.time() - self._drag_press_time > 0.2:
            self.dragging = False
        cursor_pos = QCursor.pos()
        cursor_in_rect = (
            self.window_x <= cursor_pos.x() <= self.window_x + self.win_w
            and self.window_y <= cursor_pos.y() <= self.window_y + self.win_h
        )
        if not self.hiding and not self.need_hide:
            if cursor_in_rect and not self.dragging and not is_mouse_down() and not self.gradient_hide_stuck:
                now_ts = time.time()
                if self._hover_hide_inside_since is None:
                    self._hover_hide_inside_since = now_ts
                elif now_ts - self._hover_hide_inside_since >= 0.05:
                    if self.gradient_count >= 10:
                        self.need_hide = True
                        self.gradient_count = 0
                    else:
                        if self.teaching:
                            if 9 - self.gradient_count >= 0:
                                self.target_opacity = round((9 - self.gradient_count) / 30, 3)
                        else:
                            self.target_opacity = (10 - self.gradient_count) / 10
                        self.now_opacity = self.target_opacity
                        self.need_change_opacity = True
                        self.gradient_count += 1
                    self._hover_hide_inside_since = now_ts
            else:
                # 光标离开 / 正在拖拽 / 鼠标按下
                self._hover_hide_inside_since = None
                self.gradient_count = 0
                if not self.teaching:
                    self.target_opacity = 1.0
                    self.now_opacity = self.target_opacity
                    self.need_change_opacity = True
                else:
                    self.target_opacity = 0.3
                    self.now_opacity = self.target_opacity
                    self.need_change_opacity = True    
                if self.dragging:
                    self.gradient_hide_stuck = True
                if not cursor_in_rect and not self.dragging:
                    self.gradient_hide_stuck = False
        if self.hiding and not self.click_to_hide:
            if not cursor_in_rect:
                now_ts = time.time()
                if self._hover_hide_outside_since is None:
                    self._hover_hide_outside_since = now_ts
                elif now_ts - self._hover_hide_outside_since >= 0.3:
                    self.need_show = True
                    self._hover_hide_outside_since = None
            else:
                self._hover_hide_outside_since = None
        if self.need_hide:
            self.hide()
            self.need_hide = False
            self.hiding = True
            self._hover_hide_inside_since = None
            self._hover_hide_outside_since = None
        if self.need_show:
            self.show()
            self.need_show = False
            self.hiding = False
            self._hover_hide_inside_since = None
            self._hover_hide_outside_since = None
        if self.need_change_opacity:
            self.need_change_opacity = False
            self.setWindowOpacity(self.target_opacity)
            self.update()


if __name__ == "__main__":
    qapp = QApplication(sys.argv)
    sync_class_over_on_startup()
    threading.Thread(target=get_network_time_background,daemon=True).start()
    threading.Thread(target=auto_time_update,daemon=True).start()
    app = ScheduleDisplay()
    app.show()
    sys.exit(qapp.exec())