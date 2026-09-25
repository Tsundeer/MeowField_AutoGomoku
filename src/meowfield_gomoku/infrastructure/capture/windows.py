# -*- coding: utf-8 -*-
"""游戏窗口查找、前台化、截图与鼠标点击（Windows）。

截图优先 PrintWindow(PW_RENDERFULLCONTENT)，失败（全黑/异常）回退 mss 屏幕区域抓取。
所有坐标均基于客户区（游戏渲染区），点击坐标 = 客户区原点 + 截图内坐标。
"""
import ctypes
import ctypes.wintypes as wt
import time

import numpy as np

from ... import config as C

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_gdi32 = ctypes.windll.gdi32

PW_RENDERFULLCONTENT = 0x00000002


def set_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            _user32.SetProcessDPIAware()
        except Exception:
            pass


# ---------- 进程名 ----------
def _process_name(pid):
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return "?"
    try:
        buf = ctypes.create_unicode_buffer(512)
        size = wt.DWORD(len(buf))
        if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            import os
            return os.path.basename(buf.value)
        return "?"
    finally:
        _kernel32.CloseHandle(h)


# ---------- 窗口枚举 ----------
def _enum_windows():
    result = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    cb = WNDENUMPROC(lambda h, l: (result.append(h), True)[1])
    _user32.EnumWindows(cb, 0)
    return result


def find_game_window():
    """按标题关键词找可见窗口；多个时优先进程名匹配。

    返回 (hwnd, title, proc_name)；找不到抛 RuntimeError。
    """
    import os
    my_pid = os.getpid()
    candidates = []
    for hwnd in _enum_windows():
        if not _user32.IsWindowVisible(hwnd):
            continue
        length = _user32.GetWindowTextLengthW(hwnd)
        if not length:
            continue
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if any(k in title for k in C.WINDOW_TITLE_KEYWORDS):
            pid = wt.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == my_pid:
                continue  # 排除本程序自身窗口（标题同样含关键词）
            proc = _process_name(pid.value)
            candidates.append((hwnd, title, proc))
    if not candidates:
        raise RuntimeError(
            f"未找到标题包含 {C.WINDOW_TITLE_KEYWORDS} 的窗口，请确认游戏已启动")
    for hwnd, title, proc in candidates:
        if any(hint in proc.lower() for hint in C.WINDOW_PROCESS_HINTS):
            return hwnd, title, proc
    # 兜底：排除本程序自身可执行（python/pythonw/打包 exe），
    # 避免提权重启等场景误匹配自己的另一个实例
    import os
    import sys
    self_names = {os.path.basename(sys.executable).lower(),
                  "python.exe", "pythonw.exe", "meowfield_autogomoku.exe"}
    for hwnd, title, proc in candidates:
        if proc.lower() not in self_names:
            return hwnd, title, proc
    raise RuntimeError(
        f"仅找到本程序自身的窗口，未找到游戏窗口（关键词 "
        f"{C.WINDOW_TITLE_KEYWORDS}，进程 {C.WINDOW_PROCESS_HINTS}）")


# ---------- 客户区几何 ----------
def client_rect_screen(hwnd):
    """返回客户区在屏幕上的 (left, top, width, height)。"""
    rect = wt.RECT()
    if not _user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("GetClientRect 失败")
    pt = wt.POINT(0, 0)
    _user32.ClientToScreen(hwnd, ctypes.byref(pt))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        raise RuntimeError("客户区尺寸异常")
    return pt.x, pt.y, w, h


def is_foreground(hwnd):
    return _user32.GetForegroundWindow() == hwnd


def get_cursor_pos():
    pt = wt.POINT()
    if _user32.GetCursorPos(ctypes.byref(pt)):
        return pt.x, pt.y
    return None


def focus_window(hwnd):
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        time.sleep(0.15)
    # 绕过前台锁定：模拟 Alt 键
    _user32.keybd_event(0x12, 0, 0, 0)
    _user32.SetForegroundWindow(hwnd)
    _user32.keybd_event(0x12, 0, 2, 0)  # KEYEVENTF_KEYUP
    time.sleep(0.05)


# ---------- 截图 ----------
def _print_window(hwnd):
    """PrintWindow 渲染整窗后裁剪出客户区，返回 BGR ndarray 或 None。

    注意：PrintWindow 从窗口左上角（含标题栏/边框）开始渲染，
    必须按窗口尺寸建位图再按客户区偏移裁剪，否则像素与客户区坐标
    存在标题栏高度的偏移，导致点击位置整体偏离。
    """
    wr = wt.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(wr)):
        return None
    ww, wh = wr.right - wr.left, wr.bottom - wr.top
    if ww <= 0 or wh <= 0:
        return None

    cr = wt.RECT()
    if not _user32.GetClientRect(hwnd, ctypes.byref(cr)):
        return None
    pt = wt.POINT(0, 0)
    if not _user32.ClientToScreen(hwnd, ctypes.byref(pt)):
        return None
    off_x, off_y = pt.x - wr.left, pt.y - wr.top
    cw, ch = cr.right - cr.left, cr.bottom - cr.top
    if cw <= 0 or ch <= 0:
        return None
    if off_x < 0 or off_y < 0 or off_x + cw > ww or off_y + ch > wh:
        return None  # 布局异常，交由 mss 回退

    hdc = _user32.GetDC(hwnd)
    if not hdc:
        return None
    mem = _gdi32.CreateCompatibleDC(hdc)
    bmp = _gdi32.CreateCompatibleBitmap(hdc, ww, wh)
    old = _gdi32.SelectObject(mem, bmp)
    try:
        if not _user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT):
            return None
        class BMIH(ctypes.Structure):
            _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG),
                        ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                        ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                        ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                        ("biClrImportant", wt.DWORD)]
        bmi = BMIH()
        bmi.biSize = ctypes.sizeof(BMIH)
        bmi.biWidth = ww
        bmi.biHeight = -wh  # 顶行在前
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0  # BI_RGB
        buf = ctypes.create_string_buffer(ww * wh * 4)
        if not _gdi32.GetDIBits(mem, bmp, 0, wh, buf, ctypes.byref(bmi), 0):
            return None
        arr = np.frombuffer(buf, dtype=np.uint8).reshape(wh, ww, 4)
        return np.ascontiguousarray(arr[off_y:off_y + ch, off_x:off_x + cw, :3])
    finally:
        _gdi32.SelectObject(mem, old)
        _gdi32.DeleteObject(bmp)
        _gdi32.DeleteDC(mem)
        _user32.ReleaseDC(hwnd, hdc)


def _screen_grab(left, top, w, h):
    import mss
    with mss.mss() as sct:
        img = np.asarray(sct.grab({"left": left, "top": top, "width": w, "height": h}))
        return np.ascontiguousarray(img[:, :, :3])  # BGRA->BGR


def capture_client(hwnd, prefer_printwindow=True):
    """截取客户区，返回 (BGR ndarray, origin) ，origin=(left,top)。

    PrintWindow 按窗口尺寸渲染后裁剪客户区，与 mss 屏幕抓取的
    客户区像素一一对齐，坐标换算不再有标题栏偏移。
    """
    left, top, w, h = client_rect_screen(hwnd)
    frame = None
    if prefer_printwindow:
        pw = _print_window(hwnd)
        if pw is not None and pw.std() > 2.5:
            frame = pw
    if frame is None:
        frame = _screen_grab(left, top, w, h)
    return frame, (left, top)


# ---------- 鼠标 ----------
def move_mouse(x, y):
    _user32.SetCursorPos(int(x), int(y))


def click_at(x, y, hold=0.06):
    """移动并在绝对屏幕坐标处左键单击。"""
    move_mouse(x, y)
    time.sleep(0.05)
    INPUT_MOUSE, MOUSEEVENTF_LEFTDOWN, LEFTUP = 0, 2, 4


    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                    ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]

    class _INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("mi", _MOUSEINPUT)]
        _anonymous_ = ("u",)
        _fields_ = [("type", wt.DWORD), ("u", _U)]

    def _mouse(flags):
        inp = _INPUT()
        inp.type = INPUT_MOUSE
        inp.mi = _MOUSEINPUT(0, 0, 0, flags, 0, None)
        _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    _mouse(MOUSEEVENTF_LEFTDOWN)
    time.sleep(hold)
    _mouse(LEFTUP)
