import win32gui
import win32con

WM_CLOSE = win32con.WM_CLOSE

def enum_callback(hwnd, _):
    # 获取窗口类名
    cls_name = win32gui.GetClassName(hwnd)
    # CabinetWClass = 文件/文件夹资源管理器窗口
    if cls_name == "CabinetWClass":
        # 过滤一些隐藏壳窗口
        if win32gui.IsWindowVisible(hwnd):
            print(f"关闭文件夹窗口 hwnd={hwnd}")
            win32gui.PostMessage(hwnd, WM_CLOSE, 0, 0)
    return True

if __name__ == "__main__":
    win32gui.EnumWindows(enum_callback, None)
    print("所有文件夹窗口已关闭")