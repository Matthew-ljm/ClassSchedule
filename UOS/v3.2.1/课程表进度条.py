#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# UOS Linux 版课程表进度条（由 Win 版移植，PyQt5 + X11/wmctrl/xprop/xdotool）
import sys
import os
# wmctrl/xprop/xdotool 均为 X11 工具，Wayland 会话下强制走 XWayland/XCB
if sys.platform != "win32" and not os.environ.get("QT_QPA_PLATFORM"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
import re
import time
import copy
import math
import threading
import subprocess
from datetime import datetime
import ntplib
import psutil
import requests
from datetime import datetime, timedelta, timezone
import json
from typing import cast

from PyQt5.QtWidgets import (QApplication, QWidget, QDialog, QFormLayout,
                             QSpinBox, QLineEdit, QCheckBox, QDialogButtonBox,
                             QPushButton, QMessageBox, QTabWidget, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QHBoxLayout, QLabel,
                             QHeaderView, QAbstractItemView, QComboBox,
                             QListWidget, QListWidgetItem, QMenu, QScrollArea,
                             QGroupBox, QColorDialog, QSystemTrayIcon, QAction)
from PyQt5.QtCore import Qt, QTimer, QRectF, QPoint, QCoreApplication
from PyQt5.QtGui import (QPainter, QColor, QFont, QFontMetrics, QPainterPath,
                         QPixmap, QFontDatabase, QCursor, QScreen, QIcon, QPen)

# 全局鼠标监听（pynput 在 UOS 上可选，缺失时降级为仅 Qt 事件）
try:
    from pynput.mouse import Listener
    PYNPUT_AVAILABLE = True
except Exception:
    PYNPUT_AVAILABLE = False

client = ntplib.NTPClient()
timestamp_now = time.time()
dt_now = datetime.now()
time_lock = threading.Lock()

# ===== UOS 部署路径约定 =====
doc_path = os.path.expanduser("~/Documents")
APP_DIR_NAME = "课程表进度条"
APP_DIR = os.path.join(doc_path, APP_DIR_NAME)
MAIN_BIN = os.path.join(APP_DIR, APP_DIR_NAME)
GUARD_DIR = os.path.join(doc_path, "ClassSchedule-UOS")
GUARD_BIN = os.path.join(GUARD_DIR, "ClassSchedule-UOS")    
UPDATER_DIR = os.path.join(doc_path, "ClassSchedule-updater")
UPDATER_BIN = os.path.join(UPDATER_DIR, "ClassScheduleUpdater")
CLASS_OVER_DIR = os.path.join(doc_path, "class-over")
CLASS_OVER_EXE = os.path.join(CLASS_OVER_DIR, "class-over")
CLASS_OVER_LOCK = os.path.join(CLASS_OVER_DIR, "class-over.lock")

FONT_CACHE = {}
EMOJI_FONT_CACHE = {}
_font_family_cn = None
_font_family_emj = None
base_dir = None

DEVNULL = subprocess.DEVNULL


def res_path(filename):
    """配置类文件：优先可执行文件目录，脚本运行时取脚本目录。"""
    global base_dir
    if getattr(sys, 'frozen', False) or hasattr(sys, '_MEIPASS'):
        base_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, filename)

def resource_path(filename):
    meipass = cast(str, getattr(sys, "_MEIPASS", None))
    if meipass is not None:
        p = os.path.join(meipass, filename)
        if os.path.exists(p):
            return p
    assert base_dir is not None
    return os.path.join(base_dir, filename)


font_path = res_path("NotoSansCJKsc-Black.otf")
emj_font_path = res_path("seguiemj-1.45-3d.ttf")
print(font_path)
print(emj_font_path)

try:
    assert base_dir is not None
    settings = json.load(open(os.path.join(base_dir, "settings.json"), "r", encoding="utf-8"))
except Exception as e:
    print(e)
    settings = {}

current_class = 4
try:
    current_class = settings["class"]
except Exception as e:
    print(e)
current_class = max(1, min(6, current_class))

# ===== 课程颜色映射（十六进制，存入 settings.json） =====
DEFAULT_COURSE_COLORS = {
    "语文": "#e74c3c", "数学": "#3498db", "英语": "#2ecc71",
    "物理": "#e67e22", "化学": "#9b59b6", "历史": "#c0392b",
    "地理": "#2980b9", "政治": "#8e44ad", "体育": "#f1c40f",
    "自习": "#95a5a6", "早读": "#f1948a", "生物": "#27ae60",
    "课间": "#fafac8", "课间操": "#1abc9c", "午休": "#7f8c8d",
    "休息日": "#2ecc71", "早餐": "#fab450", "晨检晨读": "#ffa078",
    "眼操": "#64c8c8", "班会": "#b464dc", "夕检": "#a0a0a0",
    "午餐自由活动": "#78d2a0", "选修": "#5aaae6", "信息技术": "#46bed2",
    "社团": "#dc82b4", "课后服务": "#82d2be", "道德与法治": "#8e44ad", "道法": "#8e44ad",
    "艺术课": "#ff8cbe", "年级统测": "#b4785a", "晚餐": "#ffb450", "晚自习": "#956ea6",
}
DEFAULT_COURSE_DEFAULT_COLOR = "#a29bfe"


def hex_to_rgb(hex_str):
    """#rrggbb -> (r, g, b)；无效时返回 (162, 155, 254)"""
    try:
        s = (hex_str or "").strip()
        if s.startswith("#"):
            s = s[1:]
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        if len(s) == 6:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        pass
    return (162, 155, 254)


def rgb_to_hex(rgb):
    """(r, g, b) -> #rrggbb"""
    try:
        r, g, b = rgb
        return "#{:02x}{:02x}{:02x}".format(int(r) & 0xff, int(g) & 0xff, int(b) & 0xff)
    except Exception:
        return "#a29bfe"


def load_course_colors(data):
    """从 settings 字典加载课程颜色，返回 (colors_dict_rgb, default_color_rgb)"""
    colors = {}
    raw = data.get("course_colors") if isinstance(data, dict) else None
    if isinstance(raw, dict):
        for name, val in raw.items():
            if isinstance(name, str) and name:
                colors[name] = hex_to_rgb(val)
    if not colors:
        colors = {k: hex_to_rgb(v) for k, v in DEFAULT_COURSE_COLORS.items()}
    default_hex = data.get("course_default_color") if isinstance(data, dict) else None
    if not isinstance(default_hex, str) or not default_hex.strip():
        default_hex = DEFAULT_COURSE_DEFAULT_COLOR
    return colors, hex_to_rgb(default_hex)


DEFAULT_SETTINGS = {
    "class": 4,
    "class_over_wait_time": 30,
    "class_over_countdown": 10,
    "local_schedule_file": "schedule.json",
    "absolute_path": False,
    "api_url": "https://test.m-code.top/api/class-schedule/",
    "protector_start_delay": 0,
    "class_over_status": True,
    "course_colors": DEFAULT_COURSE_COLORS,
    "course_default_color": DEFAULT_COURSE_DEFAULT_COLOR,
    "use_cloud_source": True,
}

assert base_dir is not None
SETTINGS_FILE = os.path.join(base_dir, "settings.json")
# class-over 倒计时通知通道（替代 Win 命名管道）：
# 外部进程向该 FIFO 写入正整数=开始倒计时，0=提前结束，如 echo 10 > countdown.fifo
COUNTDOWN_FIFO = os.path.join(base_dir, "countdown.fifo")

# ===== X11 辅助工具（随打包资源附带） =====
WMCTRL_BIN = resource_path("wmctrl")
XPROP_BIN = resource_path("xprop")
XDOTOOL_BIN = resource_path("xdotool")
for _tool in (WMCTRL_BIN, XPROP_BIN, XDOTOOL_BIN):
    try:
        if os.path.exists(_tool):
            os.chmod(_tool, 0o755)
    except Exception:
        pass


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
            try:
                os.chmod(CLASS_OVER_EXE, 0o755)
            except OSError:
                pass
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
            "自动下课组件状态异常：class-over 与 class-over.lock "
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
    # 目录完全不存在（如开发环境）时启动不弹窗，仅在设置界面里提示
    state = detect_class_over_state()
    if state is None:
        return
    target = bool(settings.get("class_over_status", False))
    ok, reason = set_class_over_state(target)
    if ok:
        return
    QMessageBox.warning(parent, "自动下课组件", class_over_problem_message(reason, target))


CN_FONT_CANDIDATES = (
    "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC",
    "WenQuanYi Micro Hei", "WenQuanYi Zen Hei", "Droid Sans Fallback",
    "Sans Serif",
)
EMOJI_FONT_CANDIDATES = ("Noto Color Emoji", "Symbola", "Sans Serif")


def _resolve_font_family(path, candidates):
    if path and os.path.exists(path):
        try:
            fid = QFontDatabase.addApplicationFont(path)
            if fid >= 0:
                fams = QFontDatabase.applicationFontFamilies(fid)
                if fams:
                    return fams[0]
        except Exception:
            pass
    db = QFontDatabase()
    have = set(db.families())
    for name in candidates:
        if name in have:
            return name
    fams = db.families()
    return fams[0] if fams else "sans-serif"


def _ensure_font_families():
    global _font_family_cn, _font_family_emj
    if _font_family_cn is None:
        _font_family_cn = _resolve_font_family(font_path, CN_FONT_CANDIDATES)
    if _font_family_emj is None:
        _font_family_emj = _resolve_font_family(emj_font_path, EMOJI_FONT_CANDIDATES)


def _get_font(size, emoji):
    _ensure_font_families()
    cache = EMOJI_FONT_CACHE if emoji else FONT_CACHE
    if size not in cache:
        f = QFont(_font_family_emj if emoji else _font_family_cn)
        f.setPixelSize(size)
        cache[size] = f
    return cache[size]


def _text_width(fm, text):
    # PyQt5 旧版本使用 width()，5.11+ 推荐 horizontalAdvance()
    if hasattr(fm, "horizontalAdvance"):
        return fm.horizontalAdvance(text)
    return fm.width(text)


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
            w += _text_width(QFontMetrics(f), ch)
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
        total_w += _text_width(fm, ch)
        ch_h = fm.ascent() + fm.descent()
        if ch_h > max_h:
            max_h = ch_h

    if total_w <= 0 or max_h <= 0:
        return None

    result = QPixmap(total_w, max_h)
    result.fill(Qt.transparent)
    p = QPainter(result)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    x = 0
    for ch in text:
        f = emj_font if is_emoji_char(ch) else cn_font
        fm = QFontMetrics(f)
        p.setFont(f)
        p.setPen(QColor(*color))
        y = (max_h - (fm.ascent() + fm.descent())) // 2
        p.drawText(x, y + fm.ascent(), ch)
        x += _text_width(fm, ch)
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


def kill_all_same_process(exe_path):
    for proc in psutil.process_iter(["pid", "exe"]):
        try:
            proc_exe = proc.info["exe"]
            if proc_exe == exe_path:
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def _popen_detached(args, shell=False):
    return subprocess.Popen(
        args,
        shell=shell,
        stdout=DEVNULL,
        stderr=DEVNULL,
        stdin=DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


try:
    _popen_detached([UPDATER_BIN])
except Exception:
    pass


# 打包部署后：单实例检测 + 拉起守护进程（开发环境不做，避免误判系统 python3）
if getattr(sys, "frozen", False):
    if get_proc_count(MAIN_BIN) > 1:
        os._exit(0)
    if get_proc_count(GUARD_BIN) == 0:
        try:
            _popen_detached([GUARD_BIN])
        except Exception:
            pass


# ===== 全局鼠标/键盘状态 =====
_global_buttons = set()
_click_hooks = []


def _on_global_mouse(button, pressed):
    if pressed:
        _global_buttons.add(button)
    else:
        _global_buttons.discard(button)
    for hook in list(_click_hooks):
        try:
            hook(button, pressed)
        except Exception:
            pass


def start_global_listener():
    if not PYNPUT_AVAILABLE:
        return
    try:
        listener = Listener(on_click=lambda x, y, b, p: _on_global_mouse(b, p))
        listener.daemon = True
        listener.start()
    except Exception:
        pass


def is_mouse_down():
    return bool(_global_buttons)


def is_ctrl_down():
    app = QApplication.instance()
    if app is None:
        return False
    return bool(app.queryKeyboardModifiers() & Qt.ControlModifier)


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
        p = psutil.Process(os.getpid())
        if sys.platform != "win32":
            try:
                p.nice(0)
            except Exception:
                pass
    except Exception:
        pass


init_program()
os.environ["PYTHONIOENCODING"] = "utf-8"
MAIN_EXE_PATH = os.path.abspath(sys.executable)


class CourseColorDialog(QDialog):
    """课程颜色映射编辑对话框"""

    def __init__(self, colors, default_color, parent=None):
        super().__init__(parent)
        self.setWindowTitle("课程颜色设置")
        self.resize(520, 560)

        self._edits = []  # [(name_edit, color_edit, delete_btn)]

        outer = QVBoxLayout(self)

        # 顶部操作区
        top_bar = QHBoxLayout()
        self.add_btn = QPushButton("添加课程")
        self.add_btn.clicked.connect(self._add_row)
        self.reset_btn = QPushButton("恢复默认")
        self.reset_btn.clicked.connect(self._reset_default)
        top_bar.addWidget(self.add_btn)
        top_bar.addWidget(self.reset_btn)
        top_bar.addStretch()
        outer.addLayout(top_bar)

        # 颜色列表（滚动区）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.form = QFormLayout(scroll_content)
        self.form.setLabelAlignment(Qt.AlignLeft)
        scroll.setWidget(scroll_content)
        outer.addWidget(scroll, 1)

        # 默认颜色
        default_row = QHBoxLayout()
        default_row.addWidget(QLabel("未匹配课程的默认颜色"))
        self.default_edit = ColorEdit(default_color or DEFAULT_COURSE_DEFAULT_COLOR)
        default_row.addWidget(self.default_edit)
        default_row.addStretch()
        outer.addLayout(default_row)

        # 按钮
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        save_btn = buttons.button(QDialogButtonBox.Save)
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        save_btn.setText("确定")
        cancel_btn.setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        # 加载现有颜色
        if isinstance(colors, dict) and colors:
            for name, color in colors.items():
                self._add_row(str(name), str(color))
        else:
            for name, color in DEFAULT_COURSE_COLORS.items():
                self._add_row(name, color)

    def _add_row(self, name="", color="#a29bfe"):
        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("课程名称")
        color_edit = ColorEdit(color)
        del_btn = QPushButton("删除")
        del_btn.setFixedWidth(60)
        row = QHBoxLayout()
        row.addWidget(name_edit, 1)
        row.addWidget(color_edit)
        row.addWidget(del_btn)
        self._edits.append((name_edit, color_edit, del_btn))
        del_btn.clicked.connect(lambda: self._delete_row(name_edit))
        wrap = QWidget()
        wrap.setLayout(row)
        self.form.addRow(wrap)

    def _delete_row(self, name_edit):
        for i, (ne, ce, db) in enumerate(self._edits):
            if ne is name_edit:
                self._edits.pop(i)
                self.form.removeRow(i)
                break

    def _reset_default(self):
        reply = QMessageBox.warning(
            self, "恢复默认",
            "确定要恢复默认课程颜色吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for ne, ce, db in self._edits:
            ne.setParent(None)
            ce.setParent(None)
            db.setParent(None)
        self._edits.clear()
        while self.form.rowCount() > 0:
            self.form.removeRow(0)
        for name, color in DEFAULT_COURSE_COLORS.items():
            self._add_row(name, color)
        self.default_edit.edit.setText(DEFAULT_COURSE_DEFAULT_COLOR)

    def get_values(self):
        colors = {}
        for name_edit, color_edit, _ in self._edits:
            name = name_edit.text().strip()
            color = color_edit.value()
            if name and TRIGGER_COLOR_RE.match(color or "") and QColor(color).isValid():
                colors[name] = color
        default = self.default_edit.value()
        if not TRIGGER_COLOR_RE.match(default or "") or not QColor(default).isValid():
            default = DEFAULT_COURSE_DEFAULT_COLOR
        return colors, default


class SettingsDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        form = QFormLayout(self)
        self.class_box = QSpinBox()
        self.class_box.setRange(1, 6)
        self.class_box.setValue(int(data.get("class", 4)))
        self._class_over_wait_time = int(data.get("class_over_wait_time", 30))
        self._class_over_countdown = int(data.get("class_over_countdown", 10))
        self.file_edit = QLineEdit(str(data.get("local_schedule_file", "schedule.json")))
        self.class_over_status = QCheckBox("启用")
        actual_class_over_state = detect_class_over_state()
        if actual_class_over_state is None:
            QMessageBox.warning(
                self,
                "弹窗提醒组件",
                class_over_problem_message("corrupted", False)
                + "\n\n已将“弹窗提醒状态”设为关闭并尝试写入 settings.json。",
            )
            data["class_over_status"] = False
            try:
                write_settings_file(data)
            except Exception as e:
                QMessageBox.critical(
                    self, "弹窗提醒组件", f"settings.json 写入失败：\n{e}"
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
        raw_rules = data.get("custom_class_over_rule", [])
        self.custom_rules = copy.deepcopy(raw_rules) if isinstance(raw_rules, list) else []
        self.edit_trigger_btn = QPushButton("编辑触发器规则")
        self.edit_trigger_btn.clicked.connect(self.edit_trigger_rules)
        # 课程颜色
        raw_cc = data.get("course_colors")
        self.course_colors = copy.deepcopy(raw_cc) if isinstance(raw_cc, dict) else copy.deepcopy(DEFAULT_COURSE_COLORS)
        self.course_default_color = data.get("course_default_color", DEFAULT_COURSE_DEFAULT_COLOR)
        if not isinstance(self.course_default_color, str) or not self.course_default_color.strip():
            self.course_default_color = DEFAULT_COURSE_DEFAULT_COLOR
        self.edit_course_color_btn = QPushButton("课程颜色设置")
        self.edit_course_color_btn.clicked.connect(self.edit_course_colors)
        self.cloud_source_check = QCheckBox("启用云端数据源")
        self.cloud_source_check.setChecked(bool(data.get("use_cloud_source", True)))
        form.addRow("班级", self.class_box)
        form.addRow("本地课表文件", self.file_edit)
        form.addRow("弹窗提醒状态", self.class_over_status)
        form.addRow("本地课表", self.edit_schedule_btn)
        form.addRow("弹窗提醒", self.edit_trigger_btn)
        form.addRow("课程颜色", self.edit_course_color_btn)
        form.addRow("云端数据源", self.cloud_source_check)
        form.addRow("API 地址", self.api_edit)
        form.addRow("保护器延迟", self.protector_start_delay)
        form.addRow(self.reset_btn)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        save_btn = buttons.button(QDialogButtonBox.Save)
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
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
                + "\n\n仍将保存设置（弹窗提醒状态：关闭）。",
            )
        super().accept()

    def get_values(self):
        filename = self.file_edit.text().strip()
        return {
            "class": self.class_box.value(),
            "class_over_wait_time": self._class_over_wait_time,
            "class_over_countdown": self._class_over_countdown,
            "local_schedule_file": filename,
            "class_over_status": self.class_over_status.isChecked(),
            "api_url": self.api_edit.text().strip(),
            "protector_start_delay": self.protector_start_delay.value(),
            "absolute_path": os.path.isabs(filename),
            "custom_class_over_rule": self.custom_rules,
            "course_colors": self.course_colors,
            "course_default_color": self.course_default_color,
            "use_cloud_source": self.cloud_source_check.isChecked(),
        }

    def reset_values(self):
        reply = QMessageBox.warning(
            self,
            "恢复默认",
            "确定要恢复默认设置吗？\n\n当前所有设置将被默认内容覆盖，此操作无法撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.class_box.setValue(int(DEFAULT_SETTINGS["class"]))
        self._class_over_wait_time = int(DEFAULT_SETTINGS["class_over_wait_time"])
        self._class_over_countdown = int(DEFAULT_SETTINGS["class_over_countdown"])
        self.file_edit.setText(DEFAULT_SETTINGS["local_schedule_file"])
        self.class_over_status.setChecked(bool(DEFAULT_SETTINGS["class_over_status"]))
        self.api_edit.setText(DEFAULT_SETTINGS["api_url"])
        self.protector_start_delay.setValue(int(DEFAULT_SETTINGS["protector_start_delay"]))
        self.course_colors = copy.deepcopy(DEFAULT_COURSE_COLORS)
        self.course_default_color = DEFAULT_COURSE_DEFAULT_COLOR
        self.cloud_source_check.setChecked(bool(DEFAULT_SETTINGS["use_cloud_source"]))
        self.accept()

    def edit_course_colors(self):
        dlg = CourseColorDialog(self.course_colors, self.course_default_color, self)
        if dlg.exec_() == QDialog.Accepted:
            colors, default = dlg.get_values()
            if colors:
                self.course_colors = colors
            self.course_default_color = default

    def edit_schedule(self):
        assert base_dir is not None
        filename = self.file_edit.text().strip()
        if not filename:
            QMessageBox.warning(self, "编辑本地课表", "请先填写本地课表文件路径。")
            return
        if os.path.isabs(filename):
            schedule_path = filename
        else:
            schedule_path = os.path.join(base_dir, filename)
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
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            schedule_data = {}

        editor = ScheduleEditorDialog(schedule_path, schedule_data, self)
        if editor.exec_() != QDialog.Accepted:
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

    def edit_trigger_rules(self):
        dlg = TriggerRuleDialog(self.custom_rules, self)
        if dlg.exec_() == QDialog.Accepted:
            self.custom_rules = dlg.get_rules()


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
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(path_label)

        self.tabs = QTabWidget()
        for day_idx in range(1, 8):
            table = QTableWidget(0, 3)
            table.setHorizontalHeaderLabels(["课程名称", "开始时间", "结束时间"])
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            header = table.horizontalHeader()
            assert header is not None
            header.setSectionResizeMode(0, QHeaderView.Stretch)
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
        self.reveal_btn.clicked.connect(self.reveal_in_file_manager)
        bottom_row.addWidget(self.reveal_btn)
        bottom_row.addStretch()
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        save_btn = buttons.button(QDialogButtonBox.Save)
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
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

    def reveal_in_file_manager(self):
        try:
            path = os.path.normpath(self.file_path)
            parent = os.path.dirname(path)
            if parent and os.path.isdir(parent):
                _popen_detached(["xdg-open", parent])
            else:
                QMessageBox.warning(
                    self, "在文件夹中显示", f"文件所在文件夹不存在：\n{parent}"
                )
        except Exception as e:
            QMessageBox.critical(self, "在文件夹中显示", f"无法打开文件管理器：\n{e}")


TRIGGER_JUMP_END = "end"
TRIGGER_CMD_PREFIX = "cmd:"

WINDOW_TYPES_IN_ORDER = ("two_button_tip", "kill_process", "single_tip")
WINDOW_TYPE_LABELS = {
    "two_button_tip": "两按钮选择窗",
    "kill_process": "进程清理窗",
    "single_tip": "单按钮提示窗",
}

TRIGGER_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

DEFAULT_RULE_TEMPLATES = [
    {
        "name": "自动下课",
        "wait_time": 30,
        "trigger_now_course": ["语文","数学","英语","物理","地理","道德与法治","生物","化学","历史","政治","道法","语文晚补","数学晚补","英语晚补","物理晚补"],
        "trigger_next_course": ["课间", "休息", "课间操", "眼操", "午休", "夕检", "社团"],
        "main_window": [
            {
                "two_button_tip": [
                    {
                        "id": "1",
                        "title": [
                            {
                                "text": "$$秒后自动下课",
                                "countdown": 10,
                                "bc": "#ffffff",
                                "tc": "#e53935"
                            }
                        ],
                        "left": [
                            {
                                "text": "现在下课",
                                "bc": "#e53935",
                                "tc": "#ffffff",
                                "cmd": "destroy",
                                "jump_to": "2"
                            }
                        ],
                        "right": [
                            {
                                "text": "拖堂两分钟",
                                "bc": "#1976d2",
                                "tc": "#ffffff",
                                "cmd": "destroy && sleep 120",
                                "popup": True,
                                "popup_times": 3,
                                "jump_to": "2"
                            }
                        ],
                        "cmd": "destroy",
                        "jump_to": "2"
                    }
                ],
                "kill_process": [
                    {
                        "id": "2",
                        "title": [
                            {
                                "text": "正在清理进程",
                                "bc": "#ffffff",
                                "tc": "#222222"
                            }
                        ],
                        "cmd": "destroy",
                        "jump_to": "3"
                    }
                ],
                "single_tip": [
                    {
                        "id": "3",
                        "title": [
                            {
                                "text": "进程清理完毕",
                                "bc": "#ffffff",
                                "tc": "#2e7d32"
                            }
                        ],
                        "button": [
                            {
                                "text": "$$s后自动关闭",
                                "countdown": 3,
                                "bc": "#1976d2",
                                "tc": "#ffffff",
                                "cmd": "destroy",
                                "jump_to": "end"
                            }
                        ],
                        "cmd": "destroy",
                        "jump_to": "end"
                    }
                ]
            }
        ]
    },
    {
        "name": "抢饭提醒",
        "wait_time": 20,
        "trigger_now_course": ["语文","数学","英语","物理","地理","道德与法治","生物","化学","历史","政治","道法","语文晚补","数学晚补","英语晚补","物理晚补"],
        "trigger_next_course": ["午饭", "午餐", "午餐自由活动", "晚餐"],
        "main_window": [
            {
                "two_button_tip": [
                    {
                        "id": "1",
                        "title": [
                            {
                                "text": "抢饭时间到，请选择一项以避开高峰",
                                "bc": "#ffffff",
                                "tc": "#e53935"
                            }
                        ],
                        "left": [
                            {
                                "text": "现在下课",
                                "bc": "#e53935",
                                "tc": "#ffffff",
                                "cmd": "destroy",
                                "jump_to": "2"
                            }
                        ],
                        "right": [
                            {
                                "text": "拖堂十分钟",
                                "bc": "#2e7d32",
                                "tc": "#ffffff",
                                "cmd": "destroy && sleep 600",
                                "jump_to": "2"
                            }
                        ],
                        "cmd": "destroy",
                        "jump_to": "2"
                    }
                ],
                "kill_process": [
                    {
                        "id": "2",
                        "title": [
                            {
                                "text": "正在清理进程",
                                "bc": "#ffffff",
                                "tc": "#222222"
                            }
                        ],
                        "cmd": "destroy",
                        "jump_to": "3"
                    }
                ],
                "single_tip": [
                    {
                        "id": "3",
                        "title": [
                            {
                                "text": "进程清理完毕",
                                "bc": "#ffffff",
                                "tc": "#2e7d32"
                            }
                        ],
                        "button": [
                            {
                                "text": "$$s后自动关闭",
                                "countdown": 3,
                                "bc": "#1976d2",
                                "tc": "#ffffff",
                                "cmd": "destroy",
                                "jump_to": "end"
                            }
                        ],
                        "cmd": "destroy",
                        "jump_to": "end"
                    }
                ]
            }
        ]
    }
]

def _trigger_first_dict(container, key):
    if isinstance(container, dict):
        value = container.get(key)
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
    return {}


def _trigger_cmd_parts(cmd):
    return [p.strip() for p in str(cmd or "").split("&&") if p.strip()]


def _parse_trigger_action(node, default_jump=TRIGGER_JUMP_END):
    node = node if isinstance(node, dict) else {}
    parts = _trigger_cmd_parts(node.get("cmd", ""))
    kind = "none"
    seconds = 60
    command = ""
    system_part = next(
        (p for p in parts if p[: len(TRIGGER_CMD_PREFIX)].lower() == TRIGGER_CMD_PREFIX),
        None,
    )
    if system_part is not None:
        kind = "system"
        command = system_part[len(TRIGGER_CMD_PREFIX):].strip()
    else:
        match = re.search(r"sleep\s+(\d+)", " ".join(parts), re.IGNORECASE)
        if match:
            kind = "sleep"
            seconds = int(match.group(1))
        elif any(p.lower() == "destroy" for p in parts):
            kind = "destroy"
    return {
        "kind": kind,
        "seconds": seconds,
        "command": command,
        "jump_to": str(node.get("jump_to", default_jump) or default_jump),
    }


def _serialize_trigger_action(action):
    kind = action.get("kind", "none")
    if kind == "sleep":
        cmd = f"sleep {int(action.get('seconds', 0) or 0)}"
    elif kind == "system":
        cmd = TRIGGER_CMD_PREFIX + str(action.get("command", "")).strip()
    elif kind == "destroy":
        cmd = "destroy"
    else:
        cmd = ""
    return {
        "cmd": cmd,
        "jump_to": str(action.get("jump_to", TRIGGER_JUMP_END) or TRIGGER_JUMP_END),
    }


def _parse_trigger_button(node, default_jump):
    node = node if isinstance(node, dict) else {}
    raw_times = node.get("popup_times", 1)
    popup_times = int(raw_times) if isinstance(raw_times, (int, float)) else 1
    return {
        "text": str(node.get("text", "")),
        "bc": str(node.get("bc", "#1976d2")),
        "tc": str(node.get("tc", "#ffffff")),
        "popup": bool(node.get("popup", False)),
        "popup_times": max(0, popup_times),
        "action": _parse_trigger_action(node, default_jump),
    }


def _serialize_trigger_button(button):
    out = {
        "text": button.get("text", ""),
        "bc": button.get("bc", "#1976d2"),
        "tc": button.get("tc", "#ffffff"),
    }
    out.update(_serialize_trigger_action(button.get("action", {})))
    if button.get("popup"):
        out["popup"] = True
        out["popup_times"] = max(0, int(button.get("popup_times", 1) or 0))
    return out


def _blank_trigger_node(ntype, node_id, jump_target):
    node = {
        "type": ntype,
        "id": str(node_id),
        "title_text": "",
        "title_bc": "#ffffff",
        "title_tc": "#222222",
        "action": {
            "kind": "destroy",
            "seconds": 0,
            "command": "",
            "jump_to": jump_target,
        },
    }
    if ntype == "two_button_tip":
        node["title_text"] = "$$秒后执行提醒"
        node["title_tc"] = "#e53935"
        node["countdown"] = 10
        node["left"] = {
            "text": "立即执行",
            "bc": "#e53935",
            "tc": "#ffffff",
            "popup": False,
            "popup_times": 1,
            "action": {"kind": "destroy", "seconds": 0, "command": "", "jump_to": jump_target},
        }
        node["right"] = {
            "text": "稍后提醒",
            "bc": "#1976d2",
            "tc": "#ffffff",
            "popup": False,
            "popup_times": 3,
            "action": {"kind": "sleep", "seconds": 60, "command": "", "jump_to": jump_target},
        }
    elif ntype == "kill_process":
        node["title_text"] = "正在清理进程"
    else:
        node["title_text"] = "提醒结束"
        node["title_tc"] = "#2e7d32"
        node["btn_countdown"] = 3
        node["button"] = {
            "text": "$$s后自动关闭",
            "bc": "#1976d2",
            "tc": "#ffffff",
            "popup": False,
            "popup_times": 1,
            "action": {"kind": "destroy", "seconds": 0, "command": "", "jump_to": TRIGGER_JUMP_END},
        }
    return node


def _parse_trigger_node(ntype, raw):
    raw = raw if isinstance(raw, dict) else {}
    title = _trigger_first_dict(raw, "title")
    win_jump = str(raw.get("jump_to", TRIGGER_JUMP_END) or TRIGGER_JUMP_END)
    node = {
        "type": ntype,
        "id": str(raw.get("id", "")),
        "title_text": str(title.get("text", "")),
        "title_bc": str(title.get("bc", "#ffffff")),
        "title_tc": str(title.get("tc", "#222222")),
        "action": _parse_trigger_action(raw, win_jump),
    }
    if ntype == "two_button_tip":
        countdown = title.get("countdown")
        node["countdown"] = int(countdown) if isinstance(countdown, (int, float)) else None
        node["left"] = _parse_trigger_button(_trigger_first_dict(raw, "left"), win_jump)
        node["right"] = _parse_trigger_button(_trigger_first_dict(raw, "right"), win_jump)
    elif ntype == "single_tip":
        raw_button = _trigger_first_dict(raw, "button")
        countdown = raw_button.get("countdown")
        node["btn_countdown"] = int(countdown) if isinstance(countdown, (int, float)) else 3
        node["button"] = _parse_trigger_button(raw_button, win_jump)
    return node


def _serialize_trigger_node(node):
    title = {
        "text": node.get("title_text", ""),
        "bc": node.get("title_bc", "#ffffff"),
        "tc": node.get("title_tc", "#222222"),
    }
    ntype = node.get("type")
    out = {"id": node.get("id", "")}
    if ntype == "two_button_tip":
        if node.get("countdown") is not None:
            title["countdown"] = int(node["countdown"])
        out["title"] = [title]
        out["left"] = [_serialize_trigger_button(node.get("left", {}))]
        out["right"] = [_serialize_trigger_button(node.get("right", {}))]
        out.update(_serialize_trigger_action(node.get("action", {})))
        return out
    if ntype == "kill_process":
        out["title"] = [title]
        out.update(_serialize_trigger_action(node.get("action", {})))
        return out
    button = _serialize_trigger_button(node.get("button", {}))
    ordered_button = {
        "text": button["text"],
        "countdown": max(1, int(node.get("btn_countdown", 3) or 3)),
        "bc": button["bc"],
        "tc": button["tc"],
        "cmd": button["cmd"],
        "jump_to": button["jump_to"],
    }
    if button.get("popup"):
        ordered_button["popup"] = True
        ordered_button["popup_times"] = button["popup_times"]
    out["title"] = [title]
    out["button"] = [ordered_button]
    out["cmd"] = button["cmd"]
    out["jump_to"] = button["jump_to"]
    return out


def _trigger_course_list(value):
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()]


def _trigger_safe_wait_time(value):
    try:
        seconds = int(value)
        if seconds >= 0:
            return seconds
    except (TypeError, ValueError):
        pass
    return 30


def parse_trigger_rules(raw):
    rules = []
    if not isinstance(raw, list):
        return rules
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        page = _trigger_first_dict(entry, "main_window")
        nodes = []
        for ntype in WINDOW_TYPES_IN_ORDER:
            raw_node = _trigger_first_dict(page, ntype)
            if raw_node:
                nodes.append(_parse_trigger_node(ntype, raw_node))
        rules.append({
            "name": str(entry.get("name", "新规则")),
            "wait_time": _trigger_safe_wait_time(entry.get("wait_time", 30)),
            "now_courses": _trigger_course_list(entry.get("trigger_now_course")),
            "next_courses": _trigger_course_list(entry.get("trigger_next_course")),
            "nodes": nodes,
        })
    return rules


def serialize_trigger_rules(rules):
    result = []
    for rule in rules:
        page = {}
        for node in rule.get("nodes", []):
            page[node["type"]] = [_serialize_trigger_node(node)]
        result.append({
            "name": rule.get("name", ""),
            "wait_time": _trigger_safe_wait_time(rule.get("wait_time", 30)),
            "trigger_now_course": _trigger_course_list(rule.get("now_courses")),
            "trigger_next_course": _trigger_course_list(rule.get("next_courses")),
            "main_window": [page],
        })
    return result


def _courses_to_text(courses):
    return ",".join(_trigger_course_list(courses))


def _parse_course_text(text):
    parts = re.split(r"[,，、;；\s]+", str(text or ""))
    return [p for p in (x.strip() for x in parts) if p]


def _blank_trigger_rule(name="新规则"):
    return {
        "name": name,
        "wait_time": 30,
        "now_courses": [],
        "next_courses": [],
        "nodes": [_blank_trigger_node("two_button_tip", "1", TRIGGER_JUMP_END)],
    }


class ColorEdit(QWidget):

    def __init__(self, value="#ffffff", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(value)
        self.edit.setMaxLength(7)
        self.pick_btn = QPushButton()
        self.pick_btn.setFixedWidth(34)
        self.pick_btn.clicked.connect(self._pick_color)
        self.edit.textChanged.connect(self._update_swatch)
        lay.addWidget(self.edit)
        lay.addWidget(self.pick_btn)
        self._update_swatch()

    def _pick_color(self):
        current = self.edit.text().strip()
        initial = QColor(current) if TRIGGER_COLOR_RE.match(current or "") else QColor("#ffffff")
        color = QColorDialog.getColor(initial, self, "选择颜色")
        if color.isValid():
            self.edit.setText(color.name())

    def _update_swatch(self):
        value = self.edit.text().strip()
        if TRIGGER_COLOR_RE.match(value or "") and QColor(value).isValid():
            bg = value
        else:
            bg = "#eeeeee"
        self.pick_btn.setStyleSheet(
            f"background:{bg};border:1px solid #999999;border-radius:4px;"
        )

    def value(self):
        return self.edit.text().strip()


ACTION_KINDS = (
    ("none", "无动作"),
    ("destroy", "内置：destroy（销毁窗口）"),
    ("sleep", "内置：sleep（等待 N 秒）"),
    ("system", "手写系统命令（保存为 cmd: 前缀）"),
)


class ActionEdit(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.kind = QComboBox()
        for kind, label in ACTION_KINDS:
            self.kind.addItem(label, kind)

        self.seconds = QSpinBox()
        self.seconds.setRange(1, 86400)
        self.seconds.setSuffix(" 秒")

        self.command = QLineEdit()
        self.command.setPlaceholderText("系统 shell 命令，如 shutdown -h +1")

        self.jump = QComboBox()
        self.jump.setEditable(True)
        self.jump.setMinimumWidth(170)

        lay.addWidget(self.kind)
        lay.addWidget(self.seconds)
        lay.addWidget(self.command, 1)
        lay.addWidget(QLabel("jump_to"))
        lay.addWidget(self.jump)

        self.kind.currentIndexChanged.connect(self._update_visible)
        self._update_visible()

    def _update_visible(self):
        kind = self.kind.currentData()
        self.seconds.setVisible(kind == "sleep")
        self.command.setVisible(kind == "system")

    def set_action(self, action, jump_ids):
        action = action if isinstance(action, dict) else {}
        index = self.kind.findData(action.get("kind", "none"))
        self.kind.setCurrentIndex(max(0, index))
        seconds = int(action.get("seconds", 60) or 60)
        self.seconds.setValue(max(1, seconds))
        self.command.setText(str(action.get("command", "")))
        self.refresh_jumps(
            jump_ids, str(action.get("jump_to", TRIGGER_JUMP_END) or TRIGGER_JUMP_END)
        )
        self._update_visible()

    def refresh_jumps(self, jump_ids, current=None):
        if current is None:
            current = self._jump_value()
        self.jump.blockSignals(True)
        self.jump.clear()
        self.jump.addItem("结束（end）", TRIGGER_JUMP_END)
        for node_id, label in jump_ids:
            self.jump.addItem(f"{node_id} · {label}", node_id)
        index = self.jump.findData(current)
        if index >= 0:
            self.jump.setCurrentIndex(index)
        else:
            self.jump.setEditText(current)
        self.jump.blockSignals(False)

    def _jump_value(self):
        data = self.jump.currentData()
        if data is not None:
            return str(data)
        return self.jump.currentText().strip()

    def get_action(self):
        return {
            "kind": self.kind.currentData(),
            "seconds": self.seconds.value(),
            "command": self.command.text().strip(),
            "jump_to": self._jump_value() or TRIGGER_JUMP_END,
        }


class TriggerRuleDialog(QDialog):

    def __init__(self, raw_rules, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑触发器规则")
        self.resize(980, 720)
        self.rules = parse_trigger_rules(raw_rules)
        self._result = None
        self.rule = None
        self.node = None
        self._loading = False
        self._refs = {}
        self._action_edits = []
        self.add_node_btns = {}

        self._build_ui()
        self._refresh_rule_list(0)

    def _build_ui(self):
        root = QVBoxLayout(self)

        hint = QLabel(
            "规则按列表顺序从上到下判断（即优先级，越靠前优先级越高），课程结束时第一条命中的规则弹出它自己的窗口，"
            "每条规则可单独设置触发延迟与触发课程（课程名单留空表示不限课程）。"
            "每个规则包含名称、窗口节点及节点间的跳转逻辑。当前支持三种窗口："
            "两按钮选择窗、进程清理窗、单按钮提示窗（每种每条规则最多一个）。"
            "按钮下的动作在点击按钮时执行；窗口自身的动作在倒计时走完、未操作时收尾执行。"
            "命令可选内置 destroy / sleep N，或手写系统命令（自动保存为 cmd: 前缀）；"
            "jump_to 为下一窗口的 id，选“结束（end）”结束整条流程。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#555555;")
        root.addWidget(hint)

        body = QHBoxLayout()

        left = QVBoxLayout()
        left.addWidget(QLabel("规则列表（上=优先级高）"))
        self.rule_list = QListWidget()
        self.rule_list.currentItemChanged.connect(self._on_rule_changed)
        left.addWidget(self.rule_list, 1)
        move_row = QHBoxLayout()
        self.move_up_btn = QPushButton("上移")
        self.move_up_btn.setToolTip("提高该规则的触发优先级（更靠前判断）")
        self.move_up_btn.clicked.connect(lambda: self._move_rule(-1))
        self.move_down_btn = QPushButton("下移")
        self.move_down_btn.setToolTip("降低该规则的触发优先级（更靠后判断）")
        self.move_down_btn.clicked.connect(lambda: self._move_rule(1))
        move_row.addWidget(self.move_up_btn)
        move_row.addWidget(self.move_down_btn)
        move_row_widget = QWidget()
        move_row_widget.setLayout(move_row)
        left.addWidget(move_row_widget)
        for text, slot in (
            ("自定义添加", self._add_custom_rule),
            ("加载默认模板", self._show_template_menu),
            ("复制规则", self._copy_rule),
            ("删除规则", self._delete_rule),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            left.addWidget(btn)
        left_widget = QWidget()
        left_widget.setLayout(left)
        left_widget.setFixedWidth(210)
        body.addWidget(left_widget)

        right = QVBoxLayout()
        head = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("给这条规则起个名字，如：自动下课")
        self.name_edit.textChanged.connect(self._on_name_changed)
        head.addRow("规则名称", self.name_edit)

        self.wait_time_spin = QSpinBox()
        self.wait_time_spin.setRange(0, 3600)
        self.wait_time_spin.setSuffix(" 秒")
        self.wait_time_spin.setToolTip("课程结束后等待多少秒再弹出本规则的窗口")
        self.wait_time_spin.valueChanged.connect(self._on_rule_fields_changed)
        head.addRow("触发延迟 wait_time", self.wait_time_spin)

        self.now_course_edit = QLineEdit()
        self.now_course_edit.setPlaceholderText("逗号分隔，如：语文,数学,英语；留空表示不限当前课程")
        self.now_course_edit.setToolTip("对应 trigger_now_course：当前节课程名称在此名单内才触发，留空表示任意课程")
        self.now_course_edit.textChanged.connect(self._on_rule_fields_changed)
        head.addRow("触发当前课程", self.now_course_edit)

        self.next_course_edit = QLineEdit()
        self.next_course_edit.setPlaceholderText("逗号分隔，如：课间,午休,午餐；留空表示不限下节课程")
        self.next_course_edit.setToolTip("对应 trigger_next_course：下一节课程名称在此名单内才触发，留空表示任意课程")
        self.next_course_edit.textChanged.connect(self._on_rule_fields_changed)
        head.addRow("触发下节课程", self.next_course_edit)
        right.addLayout(head)

        node_row = QHBoxLayout()
        node_row.addWidget(QLabel("窗口节点"))
        node_row.addStretch()
        for ntype in WINDOW_TYPES_IN_ORDER:
            btn = QPushButton(f"添加{WINDOW_TYPE_LABELS[ntype]}")
            btn.clicked.connect(lambda _, t=ntype: self._add_node(t))
            node_row.addWidget(btn)
            self.add_node_btns[ntype] = btn
        self.del_node_btn = QPushButton("删除选中节点")
        self.del_node_btn.clicked.connect(self._delete_node)
        node_row.addWidget(self.del_node_btn)
        right.addLayout(node_row)

        self.node_list = QListWidget()
        self.node_list.setMaximumHeight(110)
        self.node_list.currentItemChanged.connect(self._on_node_changed)
        right.addWidget(self.node_list)

        self.node_scroll = QScrollArea()
        self.node_scroll.setWidgetResizable(True)
        self.node_scroll.setFrameStyle(0)
        right.addWidget(self.node_scroll, 1)

        right_widget = QWidget()
        right_widget.setLayout(right)
        body.addWidget(right_widget, 1)
        root.addLayout(body, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        save_btn = buttons.button(QDialogButtonBox.Save)
        cancel_btn = buttons.button(QDialogButtonBox.Cancel)
        assert save_btn is not None and cancel_btn is not None
        save_btn.setText("保存")
        cancel_btn.setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _refresh_rule_list(self, select_row=0):
        self._loading = True
        self.rule_list.clear()
        for idx, rule in enumerate(self.rules):
            self.rule_list.addItem(QListWidgetItem(self._rule_list_label(idx, rule)))
        if 0 <= select_row < self.rule_list.count():
            self.rule_list.setCurrentRow(select_row)
        self._loading = False
        self._load_current_rule()

    @staticmethod
    def _rule_list_label(idx, rule):
        return f'{idx + 1}. {rule.get("name") or "（未命名规则）"}'

    def _on_rule_changed(self, current, previous):
        if self._loading:
            return
        self._load_current_rule()

    def _current_rule_index(self):
        row = self.rule_list.currentRow()
        return row if 0 <= row < len(self.rules) else -1

    def _load_current_rule(self):
        self._save_current_node()
        idx = self._current_rule_index()
        self.rule = self.rules[idx] if idx >= 0 else None
        self._loading = True
        self.name_edit.setText(self.rule["name"] if self.rule else "")
        self.wait_time_spin.setValue(
            int(self.rule.get("wait_time", 30) or 0) if self.rule else 30
        )
        self.now_course_edit.setText(
            _courses_to_text(self.rule.get("now_courses", [])) if self.rule else ""
        )
        self.next_course_edit.setText(
            _courses_to_text(self.rule.get("next_courses", [])) if self.rule else ""
        )
        for edit in (self.wait_time_spin, self.now_course_edit, self.next_course_edit):
            edit.setEnabled(self.rule is not None)
        self._rebuild_node_list(0)
        self._loading = False
        self._update_add_node_buttons()
        self._update_move_buttons()
        self._load_current_node()

    def _on_name_changed(self, text):
        if self._loading or self.rule is None:
            return
        self.rule["name"] = text
        item = self.rule_list.item(self.rule_list.currentRow())
        if item is not None:
            item.setText(self._rule_list_label(self.rule_list.currentRow(), self.rule))

    def _on_rule_fields_changed(self, *args):
        if self._loading or self.rule is None:
            return
        self.rule["wait_time"] = int(self.wait_time_spin.value())
        self.rule["now_courses"] = _parse_course_text(self.now_course_edit.text())
        self.rule["next_courses"] = _parse_course_text(self.next_course_edit.text())

    def _move_rule(self, delta):
        idx = self._current_rule_index()
        target = idx + delta
        if idx < 0 or not (0 <= target < len(self.rules)):
            return
        self._save_current_node()
        self.rules[idx], self.rules[target] = self.rules[target], self.rules[idx]
        self._refresh_rule_list(target)

    def _update_move_buttons(self):
        idx = self._current_rule_index()
        count = len(self.rules)
        self.move_up_btn.setEnabled(idx > 0)
        self.move_down_btn.setEnabled(0 <= idx < count - 1)

    def _unique_rule_name(self, base):
        used = {r["name"] for r in self.rules}
        if base not in used:
            return base
        for i in range(2, 1000):
            candidate = f"{base} {i}"
            if candidate not in used:
                return candidate
        return base

    def _add_custom_rule(self):
        self._save_current_node()
        rule = _blank_trigger_rule(self._unique_rule_name("新规则"))
        self.rules.append(rule)
        self._refresh_rule_list(len(self.rules) - 1)

    def _show_template_menu(self):
        menu = QMenu(self)
        for template in DEFAULT_RULE_TEMPLATES:
            menu.addAction(template["name"], lambda e=template: self._load_template(e))
        btn = self.sender()
        if isinstance(btn, QPushButton):
            menu.exec_(btn.mapToGlobal(btn.rect().bottomLeft()))
        else:
            menu.exec_(self.mapToGlobal(self.rect().center()))

    def _load_template(self, template_entry):
        parsed = parse_trigger_rules([copy.deepcopy(template_entry)])
        if not parsed:
            return
        template_rule = parsed[0]
        idx = next(
            (i for i, r in enumerate(self.rules) if r["name"] == template_rule["name"]), -1
        )
        if idx >= 0:
            reply = QMessageBox.question(
                self,
                "加载默认模板",
                f"已存在同名规则“{template_rule['name']}”。\n\n"
                "“是”用模板替换现有规则，“否”另存为副本，“取消”不加载。",
                QMessageBox.Yes
                | QMessageBox.No
                | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if reply == QMessageBox.Cancel:
                return
            if reply == QMessageBox.Yes:
                self._save_current_node()
                self.rules[idx] = template_rule
                self._refresh_rule_list(idx)
                return
            template_rule["name"] = self._unique_rule_name(template_rule["name"])
        self._save_current_node()
        self.rules.append(template_rule)
        self._refresh_rule_list(len(self.rules) - 1)

    def _copy_rule(self):
        idx = self._current_rule_index()
        if idx < 0:
            return
        self._save_current_node()
        new_rule = copy.deepcopy(self.rules[idx])
        new_rule["name"] = self._unique_rule_name(f'{new_rule["name"]} 副本')
        self.rules.append(new_rule)
        self._refresh_rule_list(len(self.rules) - 1)

    def _delete_rule(self):
        idx = self._current_rule_index()
        if idx < 0:
            return
        reply = QMessageBox.question(
            self,
            "删除规则",
            f"确定删除规则“{self.rules[idx]['name']}”吗？此操作无法撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        del self.rules[idx]
        self._refs = {}
        self.node = None
        self._refresh_rule_list(min(idx, len(self.rules) - 1))

    def _rebuild_node_list(self, select_row=0):
        self._loading = True
        self.node_list.clear()
        for node in (self.rule["nodes"] if self.rule else []):
            self.node_list.addItem(QListWidgetItem(self._node_label(node)))
        if 0 <= select_row < self.node_list.count():
            self.node_list.setCurrentRow(select_row)
        self._loading = False

    @staticmethod
    def _node_label(node):
        return f'{node.get("id") or "?"}  {WINDOW_TYPE_LABELS[node["type"]]}  {node.get("title_text", "")}'

    def _on_node_changed(self, current, previous):
        if self._loading:
            return
        self._load_current_node()

    def _current_node_index(self):
        row = self.node_list.currentRow()
        nodes = self.rule["nodes"] if self.rule else []
        return row if 0 <= row < len(nodes) else -1

    def _load_current_node(self):
        self._save_current_node()
        idx = self._current_node_index()
        self.node = self.rule["nodes"][idx] if (self.rule is not None and idx >= 0) else None
        self._build_node_form()
        self._update_add_node_buttons()

    def _jump_ids(self):
        result = []
        for node in (self.rule["nodes"] if self.rule else []):
            if self.node is not None and node is self.node and self._refs:
                node_id = self._refs["id"].text().strip()
                title = self._refs["title"].text()
            else:
                node_id = node.get("id", "")
                title = node.get("title_text", "")
            label = WINDOW_TYPE_LABELS[node["type"]]
            if title:
                label = f"{label} {title}"
            result.append((node_id or "?", label))
        return result

    def _add_node(self, ntype):
        if self.rule is None:
            return
        if any(n["type"] == ntype for n in self.rule["nodes"]):
            QMessageBox.information(
                self, "添加窗口", f"每条规则最多包含一个{WINDOW_TYPE_LABELS[ntype]}。"
            )
            return
        used_ids = {n["id"] for n in self.rule["nodes"]}
        node_id = next(str(i) for i in range(1, 1000) if str(i) not in used_ids)
        if ntype == "two_button_tip":
            following = next(
                (n["id"] for n in self.rule["nodes"]
                 if n["type"] in ("kill_process", "single_tip")),
                TRIGGER_JUMP_END,
            )
            jump_target = following
        elif ntype == "kill_process":
            jump_target = next(
                (n["id"] for n in self.rule["nodes"] if n["type"] == "single_tip"),
                TRIGGER_JUMP_END,
            )
        else:
            jump_target = TRIGGER_JUMP_END
        self._save_current_node()
        node = _blank_trigger_node(ntype, node_id, jump_target)
        self.rule["nodes"].append(node)
        self._rebuild_node_list(len(self.rule["nodes"]) - 1)
        self._load_current_node()

    def _delete_node(self):
        idx = self._current_node_index()
        if idx < 0 or self.rule is None:
            return
        reply = QMessageBox.question(
            self,
            "删除窗口节点",
            f"确定删除节点“{self._node_label(self.rule['nodes'][idx])}”吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._refs = {}
        self.node = None
        del self.rule["nodes"][idx]
        self._rebuild_node_list(min(idx, len(self.rule["nodes"]) - 1))
        self._load_current_node()

    def _update_add_node_buttons(self):
        present = {n["type"] for n in self.rule["nodes"]} if self.rule else set()
        for ntype, btn in self.add_node_btns.items():
            btn.setEnabled(self.rule is not None and ntype not in present)
        self.del_node_btn.setEnabled(self.node is not None)

    def _sync_node_header(self, *args):
        if self.node is None or not self._refs:
            return
        item = self.node_list.item(self.node_list.currentRow())
        if item is not None:
            node_id = self._refs["id"].text().strip() or "?"
            item.setText(
                f'{node_id}  {WINDOW_TYPE_LABELS[self.node["type"]]}  {self._refs["title"].text()}'
            )
        jump_ids = self._jump_ids()
        for edit in self._action_edits:
            edit.refresh_jumps(jump_ids)

    def _set_scroll_widget(self, widget):
        old = self.node_scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self.node_scroll.setWidget(widget)

    def _build_button_group(self, title, button_model, jump_ids):
        group = QGroupBox(title)
        form = QFormLayout(group)
        text_edit = QLineEdit(button_model.get("text", ""))
        bc_edit = ColorEdit(button_model.get("bc", "#1976d2"))
        tc_edit = ColorEdit(button_model.get("tc", "#ffffff"))
        form.addRow("文字", text_edit)
        form.addRow("背景色", bc_edit)
        form.addRow("文字色", tc_edit)
        ref = {"text": text_edit, "bc": bc_edit, "tc": tc_edit}
        row = QHBoxLayout()
        popup_chk = QCheckBox("等待结束后重新弹出本窗口")
        popup_times = QSpinBox()
        popup_times.setRange(0, 99)
        popup_times.setSuffix(" 次")
        popup_times.setSpecialValueText("无限次")
        times_val = button_model.get("popup_times", 3)
        popup_times.setValue(int(times_val if times_val is not None else 3))
        popup_chk.setChecked(bool(button_model.get("popup", False)))
        popup_times.setEnabled(popup_chk.isChecked())
        popup_chk.toggled.connect(popup_times.setEnabled)
        row.addWidget(popup_chk)
        row.addWidget(popup_times)
        row.addWidget(QLabel("（0=无限重弹）"))
        row.addStretch()
        row_widget = QWidget()
        row_widget.setLayout(row)
        form.addRow("重弹设置", row_widget)
        ref["popup"] = popup_chk
        ref["popup_times"] = popup_times

        action_edit = ActionEdit()
        action_edit.set_action(button_model.get("action", {}), jump_ids)
        form.addRow("点击按钮执行", action_edit)
        self._action_edits.append(action_edit)
        ref["action"] = action_edit
        return group, ref

    def _build_window_action_group(self, title, node, jump_ids):
        group = QGroupBox(title)
        lay = QVBoxLayout(group)
        action_edit = ActionEdit()
        action_edit.set_action(node.get("action", {}), jump_ids)
        lay.addWidget(action_edit)
        self._action_edits.append(action_edit)
        return group, action_edit

    def _build_node_form(self):
        widget = QWidget()
        form = QFormLayout(widget)
        refs = {}
        self._action_edits = []
        node = self.node
        jump_ids = self._jump_ids()

        if node is None:
            form.addRow(
                QLabel("左侧选择一条规则，然后通过上方按钮添加窗口节点（三种窗口每种最多一个）。")
            )
            self._set_scroll_widget(widget)
            self._refs = refs
            return

        ntype = node["type"]

        id_edit = QLineEdit(node.get("id", ""))
        id_edit.setMaxLength(20)
        type_lab = QLabel(WINDOW_TYPE_LABELS[ntype])
        title_edit = QLineEdit(node.get("title_text", ""))
        title_edit.setToolTip("支持 $$ 占位符，显示时替换为倒计时秒数")
        bc_edit = ColorEdit(node.get("title_bc", "#ffffff"))
        tc_edit = ColorEdit(node.get("title_tc", "#222222"))
        form.addRow("节点 id", id_edit)
        form.addRow("窗口类型", type_lab)
        form.addRow("标题文字", title_edit)
        form.addRow("标题背景色", bc_edit)
        form.addRow("标题文字色", tc_edit)
        refs.update(id=id_edit, title=title_edit, bc=bc_edit, tc=tc_edit)

        if ntype == "two_button_tip":
            cd_row = QHBoxLayout()
            countdown_chk = QCheckBox("启用倒计时")
            countdown_spin = QSpinBox()
            countdown_spin.setRange(1, 86400)
            countdown_spin.setSuffix(" 秒")
            has_countdown = node.get("countdown") is not None
            countdown_chk.setChecked(has_countdown)
            countdown_spin.setValue(int(node.get("countdown") or 10))
            countdown_spin.setEnabled(has_countdown)
            countdown_chk.toggled.connect(countdown_spin.setEnabled)
            cd_row.addWidget(countdown_chk)
            cd_row.addWidget(countdown_spin)
            cd_row.addStretch()
            cd_widget = QWidget()
            cd_widget.setLayout(cd_row)
            form.addRow("自动倒计时", cd_widget)
            refs["countdown_chk"] = countdown_chk
            refs["countdown_spin"] = countdown_spin

            left_group, left_ref = self._build_button_group(
                "左按钮", node.get("left", {}), jump_ids
            )
            right_group, right_ref = self._build_button_group(
                "右按钮（可用于拖堂/稍后提醒）", node.get("right", {}), jump_ids
            )
            form.addRow(left_group)
            form.addRow(right_group)
            refs["left"] = left_ref
            refs["right"] = right_ref

            window_group, window_action = self._build_window_action_group(
                "窗口收尾动作（倒计时归零、没有点击按钮时执行）", node, jump_ids
            )
            form.addRow(window_group)
            refs["window_action"] = window_action

        elif ntype == "kill_process":
            window_group, window_action = self._build_window_action_group(
                "窗口收尾动作（进程清理完成后执行）", node, jump_ids
            )
            form.addRow(window_group)
            refs["window_action"] = window_action

        else:  # single_tip
            btn_cd_row = QHBoxLayout()
            btn_cd_row.addWidget(QLabel("按钮倒计时"))
            btn_countdown = QSpinBox()
            btn_countdown.setRange(1, 86400)
            btn_countdown.setSuffix(" 秒")
            btn_countdown.setValue(int(node.get("btn_countdown", 3) or 3))
            btn_cd_row.addWidget(btn_countdown)
            btn_cd_row.addStretch()
            btn_cd_widget = QWidget()
            btn_cd_widget.setLayout(btn_cd_row)
            form.addRow(btn_cd_widget)
            refs["btn_countdown"] = btn_countdown

            button_group, button_ref = self._build_button_group(
                "唯一按钮（点击与倒计时归零执行同一动作）",
                node.get("button", {}), jump_ids,
            )
            form.addRow(button_group)
            refs["button"] = button_ref

        form.addRow(QLabel("提示：标题/按钮文字中的 $$ 会在显示时替换为剩余秒数。"))

        self._set_scroll_widget(widget)
        self._refs = refs
        id_edit.textChanged.connect(self._sync_node_header)
        title_edit.textChanged.connect(self._sync_node_header)

    def _save_current_node(self):
        if self.node is None or not self._refs:
            return
        refs = self._refs
        node = self.node
        node["id"] = refs["id"].text().strip()
        node["title_text"] = refs["title"].text()
        node["title_bc"] = refs["bc"].value()
        node["title_tc"] = refs["tc"].value()
        ntype = node["type"]
        if ntype == "two_button_tip":
            node["countdown"] = (
                refs["countdown_spin"].value()
                if refs["countdown_chk"].isChecked()
                else None
            )
            for key in ("left", "right"):
                r = refs[key]
                button = node[key]
                button["text"] = r["text"].text()
                button["bc"] = r["bc"].value()
                button["tc"] = r["tc"].value()
                button["popup"] = r["popup"].isChecked()
                button["popup_times"] = r["popup_times"].value()
                button["action"] = r["action"].get_action()
            node["action"] = refs["window_action"].get_action()
        elif ntype == "kill_process":
            node["action"] = refs["window_action"].get_action()
        else:  # single_tip
            node["btn_countdown"] = refs["btn_countdown"].value()
            r = refs["button"]
            button = node["button"]
            button["text"] = r["text"].text()
            button["bc"] = r["bc"].value()
            button["tc"] = r["tc"].value()
            button["popup"] = r["popup"].isChecked()
            button["popup_times"] = r["popup_times"].value()
            button["action"] = r["action"].get_action()

    def _select_rule_node(self, rule_idx, node_idx=None):
        self._refresh_rule_list(rule_idx)
        if node_idx is not None:
            self._loading = True
            self.node_list.setCurrentRow(node_idx)
            self._loading = False
            self._load_current_node()

    @staticmethod
    def _check_color(value, where):
        if not TRIGGER_COLOR_RE.match(value or "") or not QColor(value).isValid():
            raise ValueError(f"{where}的颜色值无效：{value}（应为 #rgb 或 #rrggbb）")

    def _iter_node_actions(self, node):
        yield "窗口收尾动作", node.get("action", {})
        if node["type"] == "two_button_tip":
            yield "左按钮", node["left"]["action"]
            yield "右按钮", node["right"]["action"]
        elif node["type"] == "single_tip":
            yield "按钮", node["button"]["action"]

    def _collect_rules(self):
        self._save_current_node()
        names_seen = set()
        for rule_idx, rule in enumerate(self.rules):
            name = rule.get("name", "").strip()
            rule_label = f"第 {rule_idx + 1} 条规则"
            if not name:
                self._select_rule_node(rule_idx)
                raise ValueError(f"{rule_label}的名称为空，请填写规则名称。")
            if name in names_seen:
                self._select_rule_node(rule_idx)
                raise ValueError(f"规则名称重复：{name}")
            names_seen.add(name)
            rule["name"] = name

            ids_seen = set()
            for node_idx, node in enumerate(rule.get("nodes", [])):
                node["id"] = node.get("id", "").strip()
                where = f"规则“{name}”的节点“{node['id'] or node_idx + 1}”"
                if not node["id"]:
                    self._select_rule_node(rule_idx, node_idx)
                    raise ValueError(f"规则“{name}”中存在没有 id 的窗口节点。")
                if node["id"] in ids_seen:
                    self._select_rule_node(rule_idx, node_idx)
                    raise ValueError(f"规则“{name}”中窗口 id 重复：{node['id']}")
                ids_seen.add(node["id"])

                self._check_color(node.get("title_bc", ""), f"{where}标题背景色")
                self._check_color(node.get("title_tc", ""), f"{where}标题文字色")

                if node["type"] == "two_button_tip":
                    for side, button in (("左按钮", node["left"]), ("右按钮", node["right"])):
                        if not button.get("text"):
                            self._select_rule_node(rule_idx, node_idx)
                            raise ValueError(f"{where}{side}文字不能为空。")
                        self._check_color(button.get("bc", ""), f"{where}{side}背景色")
                        self._check_color(button.get("tc", ""), f"{where}{side}文字色")
                elif node["type"] == "single_tip":
                    button = node["button"]
                    if not button.get("text"):
                        self._select_rule_node(rule_idx, node_idx)
                        raise ValueError(f"{where}按钮文字不能为空。")
                    self._check_color(button.get("bc", ""), f"{where}按钮背景色")
                    self._check_color(button.get("tc", ""), f"{where}按钮文字色")

            valid_jumps = ids_seen | {TRIGGER_JUMP_END}
            for node_idx, node in enumerate(rule.get("nodes", [])):
                for action_name, action in self._iter_node_actions(node):
                    kind = action.get("kind", "none")
                    if kind == "system" and not action.get("command"):
                        self._select_rule_node(rule_idx, node_idx)
                        raise ValueError(
                            f"规则“{name}”节点“{node['id']}”的{action_name}"
                            "选择了手写系统命令，但命令内容为空。"
                        )
                    jump_to = str(action.get("jump_to", TRIGGER_JUMP_END) or TRIGGER_JUMP_END)
                    if jump_to not in valid_jumps:
                        self._select_rule_node(rule_idx, node_idx)
                        raise ValueError(
                            f"规则“{name}”节点“{node['id']}”的{action_name}"
                            f"跳转目标不存在：{jump_to}（请选择已有节点 id 或 end）。"
                        )
        self._result = serialize_trigger_rules(self.rules)

    def accept(self):
        try:
            self._collect_rules()
        except ValueError as e:
            QMessageBox.critical(self, "编辑触发器规则", str(e))
            return
        super().accept()

    def get_rules(self):
        if self._result is None:
            return serialize_trigger_rules(self.rules)
        return self._result


class ScheduleDisplay(QWidget):
    def __init__(self):
        super().__init__()
        app = QApplication.instance()
        assert app is not None
        screen = app.primaryScreen()
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
        self.window_x = (self.screen_w - self.win_w) // 2
        self.window_y = 0

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setGeometry(self.window_x, self.window_y, self.win_w, self.win_h)

        self.win_title = "课表进度条"
        self.setWindowTitle(self.win_title)

        # X11 窗口 id（wmctrl/xprop/xdotool 均使用该十六进制值）
        self.win_id_dec = int(self.winId())
        self.win_id_hex = hex(self.win_id_dec)
        print(self.win_id_hex)

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
        self.gradient_count = 0
        self.gradient_hide_stuck = False
        self.after_second_click_running = False
        self.hiding = False
        self.fetching_schedule = False
        self._hover_hide_inside_since = None
        self._hover_hide_outside_since = None
        self.dragging = False
        self._drag_press_time = 0.0
        self._settings_open = False
        self.countdown_lock = False
        self.countdown_total = 0
        self.countdown_start_ts = 0.0
        self.countdown_restore_pending = False
        # Ctrl 按住时：悬停不渐变隐藏、单击不隐藏（由 _tick 每帧刷新）
        self.ctrl_pressed = False
        if PYNPUT_AVAILABLE:
            _click_hooks.append(self._dispatch_global_click)

        try:
            self.api_url = settings["api_url"]
        except Exception as e:
            print(e)
            self.api_url = "https://test.m-code.top/api/class-schedule/"

        empty_schedule = {"day1": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day2": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day3": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day4": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day5": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day6": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day7": [{"name":"暂无课程","start":"00:00","end":"23:59"}]}
        try:
            if settings.get("absolute_path"):
                schedule_file = settings["local_schedule_file"]
                if os.path.exists(schedule_file):
                    self.local_schedule = json.load(open(schedule_file, "r", encoding="utf-8"))
                else:
                    self.local_schedule = empty_schedule
            else:
                assert base_dir is not None
                schedule_file = os.path.join(base_dir, settings['local_schedule_file'])
                if os.path.exists(schedule_file):
                    self.local_schedule = json.load(open(schedule_file, "r", encoding="utf-8"))
                else:
                    self.local_schedule = empty_schedule
        except Exception as e:
            print(e)
            self.local_schedule = empty_schedule
        self.course_colors, self.default_color = load_course_colors(settings)
        self.schedule_data = None
        self.data_source = "本地"
        self.is_single_week = False
        try:
            self.run_wait_time = settings["class_over_wait_time"]
        except Exception as e:
            print(e)
            self.run_wait_time = 30
        self.class_over_running = False
        self.cloud_enabled = bool(settings.get("use_cloud_source", True))
        self.use_local_schedule()
        self.running = True
        if self.cloud_enabled:
            threading.Thread(target=self.auto_fetch_schedule, daemon=True).start()
        threading.Thread(target=self.keep_protect_process, daemon=True).start()
        threading.Thread(target=self.countdown_fifo_server, daemon=True).start()
        self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.update_thread.start()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

        self.tray_icon = None
        self.tray_menu = None
        self._init_tray_icon()

        self.update()

    def auto_fetch_schedule(self):
        self.fetching_schedule = True
        while self.running and self.cloud_enabled:
            retry_max = 3
            retry_count = 0
            success = False
            while retry_count < retry_max and not success and self.running and self.cloud_enabled:
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
        self.fetching_schedule = False

    # ===== X11 窗口管理 =====
    def _run_x_tool(self, args, timeout=2):
        try:
            return subprocess.run(
                args, stdout=subprocess.PIPE, stderr=DEVNULL,
                timeout=timeout, start_new_session=False,
            )
        except Exception:
            return None

    def minimize_restart_daemon(self):
        while True:
            time.sleep(2)
            if self._settings_open:
                continue
            if self.is_window_minimized():
                self._run_x_tool([XDOTOOL_BIN, "windowactivate", "--sync", self.win_id_hex])

    def is_window_minimized(self):
        try:
            out = subprocess.check_output(
                [XPROP_BIN, "-id", self.win_id_hex, "_NET_WM_STATE"],
                encoding="utf-8", errors="ignore", timeout=2,
                stderr=DEVNULL,
            )
            return "_NET_WM_STATE_HIDDEN" in out
        except Exception:
            return False

    def _force_geometry_once(self):
        # 部分 WM 会忽略程序首次请求的位置，show 之后用 wmctrl 再校正一次
        self._run_x_tool([
            WMCTRL_BIN, "-i", "-r", self.win_id_hex, "-e",
            f"0,{int(self.window_x)},{int(self.window_y)},{int(self.win_w)},{int(self.win_h)}",
        ])

    def _our_wmctrl_ids(self):
        """枚举本进程所有被 WM 管理的窗口（含设置窗、触发器编辑窗等）。"""
        ids = []
        if not os.path.exists(WMCTRL_BIN):
            return ids
        try:
            out = subprocess.check_output(
                [WMCTRL_BIN, "-lp"], encoding="utf-8", errors="ignore",
                timeout=2, stderr=DEVNULL,
            )
        except Exception:
            return ids
        pid = os.getpid()
        for line in out.splitlines():
            parts = line.split()
            # 形如：0x03800007 -1 2867 hostname 标题
            if len(parts) >= 3 and parts[0].startswith("0x"):
                try:
                    if int(parts[2]) == pid:
                        ids.append(parts[0])
                except ValueError:
                    continue
        return ids

    def top_daemon(self):
        time.sleep(1.5)
        while True:
            try:
                if not self.dragging:
                    if self._settings_open:
                        target_ids = self._our_wmctrl_ids()
                    else:
                        target_ids = [self.win_id_hex]
                    for wid in target_ids:
                        self._run_x_tool([
                            WMCTRL_BIN, "-i", "-r", wid,
                            "-b", "add,above,sticky,skip_taskbar",
                        ])
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

    def format_simple_time(self, sec):
        sec = int(max(0, sec))
        m, s = divmod(sec, 60)
        if m > 0:
            return f"{m}m{s:02d}s"
        return f"{s:02d}s"

    def draw_countdown_mode(self, painter):
        painter.fillRect(0, 0, self.win_w, self.win_h, QColor(236, 240, 241, 255))
        info_w = 150
        ax = info_w + 5
        ay = 5
        aw = self.win_w - ax - 5
        ah = self.win_h - 10
        total = max(1, int(self.countdown_total or 0))
        remaining = max(
            0.0, total - (time.monotonic() - self.countdown_start_ts)
        )
        frac = max(0.0, min(1.0, remaining / total))
        if remaining > 6:
            bar_color = (46, 204, 113)    # 绿
        elif remaining > 3:
            bar_color = (241, 196, 15)    # 黄
        else:
            bar_color = (231, 76, 60)     # 红
        painter.fillRect(int(ax), int(ay), int(aw), int(ah), QColor(176, 176, 176))
        fill_w = int(round(aw * frac))
        if fill_w > 0:
            painter.fillRect(int(ax), int(ay), fill_w, int(ah), QColor(*bar_color))
        now = dt_now
        dt_str = now.strftime("%m/%d")
        wk = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"][now.isoweekday()]
        time_txt = f"{dt_str} {wk} {now.strftime('%H:%M')}"
        time_surf = render_mixed(time_txt, 18, (44, 62, 80))
        if time_surf is not None:
            painter.drawPixmap(7, (self.win_h - time_surf.height()) // 2, time_surf)
        sec_show = max(0, math.ceil(remaining - 1e-6))
        remain_txt = self.format_simple_time(sec_show)
        pix = render_mixed(remain_txt, 26, (255, 255, 255))
        if pix is not None:
            cx = int(ax + aw // 2 - pix.width() // 2)
            cy = int(ay + ah // 2 - pix.height() // 2)
            shadow = render_mixed(remain_txt, 26, (44, 62, 80))
            if shadow is not None:
                painter.drawPixmap(cx + 1, cy + 1, shadow)
            painter.drawPixmap(cx, cy, pix)

    @staticmethod
    def _rule_course_list(rule, key):
        value = rule.get(key) if isinstance(rule, dict) else None
        if not isinstance(value, list):
            return []
        return [str(x).strip() for x in value if str(x).strip()]

    def _rule_wait_seconds(self, rule):
        try:
            value = rule.get("wait_time")
            if value is not None and int(value) >= 0:
                return int(value)
        except (TypeError, ValueError):
            pass
        return int(getattr(self, "run_wait_time", 30) or 30)

    def _match_trigger_rule(self, curr_name, next_name):
        rules = settings.get("custom_class_over_rule")
        if not isinstance(rules, list):
            return None
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            now_list = self._rule_course_list(rule, "trigger_now_course")
            next_list = self._rule_course_list(rule, "trigger_next_course")
            if now_list and curr_name not in now_list:
                continue
            if next_list and next_name not in next_list:
                continue
            return rule
        return None

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
                    next_name = ""
                    if idx + 1 < len(data):
                        next_name = self.parse_course_name(data[idx+1]["name"])
                    rule = self._match_trigger_rule(curr_name, next_name)
                    if rule is not None:
                        self.class_over_running = True
                        rule_name = str(rule.get("name", ""))
                        wait_time = self._rule_wait_seconds(rule)

                        def delay_start():
                            try:
                                time.sleep(wait_time)
                                _popen_detached([CLASS_OVER_EXE, rule_name])
                                time.sleep(max(0, min(70, 70 - wait_time)))
                            except Exception:
                                pass
                            self.class_over_running = False
                        threading.Thread(target=delay_start, daemon=True).start()
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
            threading.Thread(target=self.after_second_click, daemon=True).start()

    def _dispatch_global_click(self, button, pressed):
        self.on_click(0, 0, button, pressed)

    def keep_protect_process(self):
        while self.running:
            # 仅打包部署后守护 ClassSchedule-UOS；开发环境不去动系统里安装的程序
            if getattr(sys, "frozen", False) and get_proc_count(GUARD_BIN) == 0:
                try:
                    _popen_detached([GUARD_BIN])
                except Exception:
                    pass
            time.sleep(2)

    # ===== 倒计时 FIFO 通道（替代 Win 命名管道） =====
    def countdown_fifo_server(self):
        if not hasattr(os, "mkfifo"):
            # 非 POSIX 平台（如开发用 Windows）无 FIFO 支持，空转即可
            while self.running:
                time.sleep(60)
            return
        while self.running:
            try:
                if not os.path.exists(COUNTDOWN_FIFO):
                    try:
                        os.mkfifo(COUNTDOWN_FIFO)
                        os.chmod(COUNTDOWN_FIFO, 0o666)
                    except OSError:
                        time.sleep(1)
                        continue
                # 阻塞等待写者；echo 内容写完关闭后 read 返回 b""，再进入下一轮
                with open(COUNTDOWN_FIFO, "rb") as f:
                    data = b""
                    while self.running:
                        chunk = f.read(4096)
                        if not chunk:
                            break
                        data += chunk
                text = data.decode("utf-8", errors="ignore")
                lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                if lines:
                    self._handle_countdown_message(lines[-1])
            except Exception:
                time.sleep(1)

    def _handle_countdown_message(self, message):
        try:
            seconds = int(float(str(message).strip()))
        except (TypeError, ValueError):
            return
        if seconds > 0:
            self.countdown_total = seconds
            self.countdown_start_ts = time.monotonic()
            self.countdown_restore_pending = False
            self.gradient_count = 0
            self.target_opacity = 1.0
            self.now_opacity = 1.0
            self.need_change_opacity = True
            if self.hiding:
                self.need_show = True
            self.mode = "countdown"
            self.countdown_lock = True
        elif self.countdown_lock:
            self.countdown_lock = False
            self.countdown_restore_pending = True

    def _restore_after_countdown(self):
        self.mode = "normal"
        self.target_opacity = 1.0
        self.now_opacity = 1.0
        self.need_change_opacity = True
        self.update()

    def click_event(self):
        time.sleep(0.3)
        if self.dragging:
            while self.dragging:
                if not self.dragging:
                    break
                time.sleep(1)
        elif not self.ctrl_pressed:
            # Ctrl 按住时单击不隐藏
            self.need_hide = True
            # 没有全局鼠标监听时无法感知“外部第二次点击”，
            # 改由“光标移出 0.3 秒”恢复（见 _tick）
            if PYNPUT_AVAILABLE:
                self.click_to_hide = True
        self.is_onclick_event_run = False

    def update_loop(self):
        while self.running:
            time.sleep(1)
            self._need_refresh = True

    def _make_tray_icon(self):
        assert base_dir is not None
        for name in ("icon.ico", "icon.png"):
            icon_path = os.path.join(base_dir, name)
            if os.path.isfile(icon_path):
                icon = QIcon(icon_path)
                if not icon.isNull():
                    return icon

        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        bg = QPainterPath()
        bg.addRoundedRect(QRectF(2, 2, 60, 60), 14, 14)
        painter.fillPath(bg, QColor("#1976d2"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPoint(32, 32), 20, 20)
        pen = QPen(QColor("#1976d2"))
        pen.setWidth(4)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPoint(32, 32), QPoint(32, 20))
        painter.drawLine(QPoint(32, 32), QPoint(42, 36))
        painter.end()
        return QIcon(pixmap)

    def _init_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray_menu = QMenu()
        settings_action = QAction("设置", self)
        settings_action.triggered.connect(self.open_settings_dialog)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)
        self.tray_menu.addAction(settings_action)
        self.tray_menu.addAction(quit_action)

        self.tray_icon = QSystemTrayIcon(self._make_tray_icon(), self)
        self.tray_icon.setToolTip(self.win_title)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger and self.tray_menu is not None:
            self.tray_menu.exec_(QCursor.pos())

    def quit_app(self):
        self.running = False
        # 守护进程会无条件拉起本程序，退出前先结束守护（与旧 UOS 版行为一致）
        if getattr(sys, "frozen", False):
            kill_all_same_process(GUARD_BIN)
        self.timer.stop()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        app = QApplication.instance()
        if app is not None:
            app.quit()

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
        assert app is not None
        screen = app.primaryScreen()
        geo = screen.availableGeometry()
        hint = dlg.sizeHint()
        dlg.move(
            max(geo.left(), geo.center().x() - hint.width() // 2),
            max(geo.top(), geo.center().y() - hint.height() // 2),
        )
        try:
            if dlg.exec_() == QDialog.Accepted:
                data = dlg.get_values()
                assert base_dir is not None
                with open(os.path.join(base_dir, "settings.json"), "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                settings.clear()
                settings.update(data)
                current_class = max(1, min(6, data["class"]))
                self.api_url = data["api_url"]
                self.run_wait_time = data["class_over_wait_time"]
                self.course_colors, self.default_color = load_course_colors(settings)
                try:
                    if settings["absolute_path"]:
                        self.local_schedule = json.load(open(settings["local_schedule_file"], "r", encoding="utf-8"))
                    else:
                        self.local_schedule = json.load(open(os.path.join(base_dir, settings['local_schedule_file']), "r", encoding="utf-8"))
                except Exception as e:
                    print(e)
                    self.local_schedule = {"day1": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day2": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day3": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day4": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day5": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day6": [{"name":"暂无课程","start":"00:00","end":"23:59"}], "day7": [{"name":"暂无课程","start":"00:00","end":"23:59"}]}
                # 云端数据源开关处理
                self.cloud_enabled = bool(data.get("use_cloud_source", True))
                if self.cloud_enabled:
                    if not self.fetching_schedule:
                        threading.Thread(target=self.auto_fetch_schedule, daemon=True).start()
                else:
                    # 关闭云端：轮询线程会因 cloud_enabled=False 自行退出，切换到本地课表
                    self.use_local_schedule()
                self.update()
        finally:
            self._settings_open = False
            self.need_hide = False
            self.need_show = False

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Comma and event.modifiers() & Qt.ControlModifier:
            self.open_settings_dialog()
            return
        if key == Qt.Key_Q and event.modifiers() & Qt.ControlModifier:
            self.quit_app()
            return
        self._keys_pressed.add(key)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        self._keys_pressed.discard(event.key())
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self._drag_press_time = time.time()
            if not self.is_onclick_event_run:
                threading.Thread(target=self.click_event, daemon=True).start()
            self.is_onclick_event_run = True
            pos = event.pos()
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
        if event.button() == Qt.LeftButton:
            self.dragging = False

    def mouseMoveEvent(self, event):
        if self.dragging:
            gp = event.globalPos()
            self.move_window(gp.x(), gp.y(), self._drag_mx, self._drag_my)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        radius = max(0, min(self.corner_radius, min(self.win_w, self.win_h) // 2))
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.win_w, self.win_h), radius, radius)
        painter.setClipPath(path)
        if self.countdown_lock or self.mode == "countdown":
            self.draw_countdown_mode(painter)
        else:
            axis = self.draw_schedule(painter)
            self.draw_progress(painter, axis)
        painter.end()

    def _tick(self):
        self.ctrl_pressed = is_ctrl_down()
        if self._settings_open:
            return
        if self.countdown_restore_pending:
            self.countdown_restore_pending = False
            self._restore_after_countdown()
        if self.countdown_lock:
            remaining = self.countdown_total - (
                time.monotonic() - self.countdown_start_ts
            )
            if remaining <= 0:
                self.countdown_lock = False
                self._restore_after_countdown()
            else:
                self.target_opacity = 1.0
                self.now_opacity = 1.0
                if self.hiding:
                    self.need_show = True
                self.update()
        flag = False
        nx = self.window_x
        ny = self.window_y
        keys = self._keys_pressed
        if Qt.Key_Left in keys:
            nx -= self.move_step
            flag = True
        if Qt.Key_Right in keys:
            nx += self.move_step
            flag = True
        if Qt.Key_Up in keys:
            ny -= self.move_step
            flag = True
        if Qt.Key_Down in keys:
            ny += self.move_step
            flag = True
        if flag:
            self.move_window(nx, ny, 0, 0)
        if self._need_refresh:
            self._need_refresh = False
            self.check_course_trigger()
            self.update()
        if PYNPUT_AVAILABLE and self.dragging and not is_mouse_down() and time.time() - self._drag_press_time > 0.2:
            self.dragging = False
        cursor_pos = QCursor.pos()
        cursor_in_rect = (
            self.window_x <= cursor_pos.x() <= self.window_x + self.win_w
            and self.window_y <= cursor_pos.y() <= self.window_y + self.win_h
        )
        if not self.countdown_lock and not self.hiding and not self.need_hide:
            if cursor_in_rect and not self.dragging and not is_mouse_down() and not self.gradient_hide_stuck and not self.ctrl_pressed:
                now_ts = time.time()
                if self._hover_hide_inside_since is None:
                    self._hover_hide_inside_since = now_ts
                elif now_ts - self._hover_hide_inside_since >= 0.02:
                    if self.gradient_count >= 10:
                        self.need_hide = True
                        self.gradient_count = 0
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
                self.target_opacity = 1.0
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
            if self.countdown_lock:
                self.need_hide = False
                self.click_to_hide = False
            else:
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
    settings_only = "--settings" in sys.argv[1:]
    qapp = QApplication(sys.argv)
    _ensure_font_families()
    if _font_family_cn:
        qapp.setFont(QFont(_font_family_cn, 10))
    start_global_listener()
    if settings_only:
        dlg = SettingsDialog(settings)
        screen = qapp.primaryScreen()
        geo = screen.availableGeometry()
        hint = dlg.sizeHint()
        dlg.move(
            max(geo.left(), geo.center().x() - hint.width() // 2),
            max(geo.top(), geo.center().y() - hint.height() // 2),
        )
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_values()
            with open(os.path.join(base_dir, "settings.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            settings.clear()
            settings.update(data)
        sys.exit(0)
    qapp.setQuitOnLastWindowClosed(False)
    sync_class_over_on_startup()
    threading.Thread(target=get_network_time_background, daemon=True).start()
    threading.Thread(target=auto_time_update, daemon=True).start()
    app = ScheduleDisplay()
    app.show()
    sys.exit(qapp.exec_())
