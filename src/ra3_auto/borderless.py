"""Apply borderless monitor geometry to RA3 and Uprising processes."""

import ctypes
import sys
import time
from ctypes import wintypes

from ra3_auto.paths import PROCESS_NAMES_ARGUMENT, log_path
from ra3_auto.processes import find_first_process


user32 = ctypes.WinDLL("user32", use_last_error=True)

GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_BORDER = 0x00800000
WS_DLGFRAME = 0x00400000
WS_MAXIMIZEBOX = 0x00010000
WS_MINIMIZEBOX = 0x00020000
WS_SYSMENU = 0x00080000
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
MONITOR_DEFAULTTONEAREST = 2
LOG_PATH = log_path("borderless.log")


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.SetWindowLongW.restype = wintypes.LONG
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
user32.GetMonitorInfoW.restype = wintypes.BOOL


def log(message):
    with LOG_PATH.open("a", encoding="utf-8") as stream:
        stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def find_window(pid):
    windows = []

    @EnumWindowsProc
    def callback(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            windows.append(hwnd)
            return False
        return True

    user32.EnumWindows(callback, 0)
    return windows[0] if windows else None


def apply_borderless(hwnd):
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    style &= ~(
        WS_CAPTION
        | WS_THICKFRAME
        | WS_BORDER
        | WS_DLGFRAME
        | WS_MAXIMIZEBOX
        | WS_MINIMIZEBOX
        | WS_SYSMENU
    )
    user32.SetWindowLongW(hwnd, GWL_STYLE, style)

    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    overscan = 4
    if not user32.SetWindowPos(
        hwnd,
        None,
        info.rcMonitor.left - overscan,
        info.rcMonitor.top - overscan,
        info.rcMonitor.right - info.rcMonitor.left + overscan * 2,
        info.rcMonitor.bottom - info.rcMonitor.top + overscan * 2,
        SWP_FRAMECHANGED | SWP_NOZORDER | SWP_NOACTIVATE,
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def main():
    if "--self-test" in sys.argv:
        return 0
    process_names = [
        name.strip()
        for name in (
            sys.argv[1]
            if len(sys.argv) > 1
            else PROCESS_NAMES_ARGUMENT
        ).split(",")
        if name.strip()
    ]
    log(f"helper started processes={','.join(process_names)}")
    applied_pid = None
    while True:
        pid, process_name = find_first_process(process_names)
        if not pid:
            applied_pid = None
            time.sleep(2.0)
            continue
        if pid != applied_pid:
            hwnd = find_window(pid)
            if hwnd:
                apply_borderless(hwnd)
                applied_pid = pid
                log(f"applied to {process_name} pid={pid} hwnd={hwnd}")
        time.sleep(1.0)


if __name__ == "__main__":
    raise SystemExit(main())
