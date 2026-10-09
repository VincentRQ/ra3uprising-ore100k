"""Reliable windowed edge scrolling for Red Alert 3 and Uprising.

RA3's native edge scrolling is disabled in windowed mode. This helper watches
the foreground game window and holds the corresponding arrow key while the OS
cursor is at a window/monitor edge. Input is sent as correctly sized Win32
INPUT records with DirectInput-compatible scan codes.
"""

import atexit
import ctypes
import sys
import time
from ctypes import wintypes

from ra3_auto.paths import PROCESS_NAMES_ARGUMENT, log_path


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
TH32CS_SNAPPROCESS = 0x00000002
ERROR_ALREADY_EXISTS = 183
MONITOR_DEFAULTTONEAREST = 2

SCAN_CODES = {
    "left": 0x4B,
    "right": 0x4D,
    "up": 0x48,
    "down": 0x50,
}

LOG_PATH = log_path("edge-scroll.log")


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUTUNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", INPUTUNION)]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.ClipCursor.argtypes = [ctypes.POINTER(RECT)]
user32.ClipCursor.restype = wintypes.BOOL
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
user32.GetMonitorInfoW.restype = wintypes.BOOL
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE


def log(message):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as stream:
        stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def acquire_single_instance(process_names):
    identity = ",".join(sorted(name.casefold() for name in process_names))
    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, False, "Local\\RA3AutoEnhance_EdgeScroll_v1")
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        log(f"duplicate helper ignored for {identity}")
        return None
    return handle


def find_process(process_names):
    wanted = {name.casefold(): name for name in process_names}
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if snapshot == invalid_handle:
        return None, None
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        found = {}
        while ok:
            folded = entry.szExeFile.casefold()
            if folded in wanted:
                found[folded] = entry.th32ProcessID
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        for name in process_names:
            pid = found.get(name.casefold())
            if pid:
                return pid, name
        return None, None
    finally:
        kernel32.CloseHandle(snapshot)


def find_window(pid):
    windows = []

    @EnumWindowsProc
    def callback(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            windows.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    return windows[0] if windows else None


def get_active_rect(hwnd, edge_zone):
    window_rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(window_rect)):
        raise ctypes.WinError(ctypes.get_last_error())

    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return window_rect

    covers_monitor = (
        window_rect.left <= info.rcMonitor.left + edge_zone
        and window_rect.top <= info.rcMonitor.top + edge_zone
        and window_rect.right >= info.rcMonitor.right - edge_zone
        and window_rect.bottom >= info.rcMonitor.bottom - edge_zone
    )
    return info.rcMonitor if covers_monitor else window_rect


def send_scan_code(scan_code, key_up):
    event = INPUT(type=INPUT_KEYBOARD)
    event.ki = KEYBDINPUT(
        wVk=0,
        wScan=scan_code,
        dwFlags=(
            KEYEVENTF_SCANCODE
            | KEYEVENTF_EXTENDEDKEY
            | (KEYEVENTF_KEYUP if key_up else 0)
        ),
        time=0,
        dwExtraInfo=0,
    )
    ctypes.set_last_error(0)
    sent = user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
    if sent != 1:
        error = ctypes.get_last_error()
        log(f"SendInput failed scan=0x{scan_code:02X} up={key_up} error={error}")
        return False
    return True


class EdgeController:
    def __init__(self):
        self.held = set()
        self.clipped = False

    def set_directions(self, desired):
        for direction in sorted(self.held - desired):
            send_scan_code(SCAN_CODES[direction], key_up=True)
            self.held.discard(direction)
            log(f"release {direction}")
        for direction in sorted(desired - self.held):
            if send_scan_code(SCAN_CODES[direction], key_up=False):
                self.held.add(direction)
                log(f"press {direction}")

    def release(self):
        self.set_directions(set())
        if self.clipped:
            user32.ClipCursor(None)
            self.clipped = False
            log("cursor clip off")

    def clip(self, rect):
        if user32.ClipCursor(ctypes.byref(rect)):
            if not self.clipped:
                log(f"cursor clip on {rect.left},{rect.top}-{rect.right},{rect.bottom}")
            self.clipped = True


def main():
    expected_input_size = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
    if ctypes.sizeof(INPUT) != expected_input_size:
        raise SystemExit(
            f"invalid INPUT layout: got {ctypes.sizeof(INPUT)}, expected {expected_input_size}"
        )
    if "--self-test" in sys.argv:
        return 0

    process_names = [
        name.strip()
        for name in (
            sys.argv[1] if len(sys.argv) > 1 else PROCESS_NAMES_ARGUMENT
        ).split(",")
        if name.strip()
    ]
    edge_zone = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    poll_seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 0.015
    if not process_names:
        raise SystemExit("at least one process name is required")
    if not 1 <= edge_zone <= 50:
        raise SystemExit("edge zone must be between 1 and 50 pixels")

    mutex = acquire_single_instance(process_names)
    if mutex is None:
        return

    controller = EdgeController()
    atexit.register(controller.release)
    pid = None
    process_name = None
    hwnd = None
    active_rect = None
    next_process_scan = 0.0
    next_rect_refresh = 0.0
    log(
        f"helper started processes={','.join(process_names)} zone={edge_zone} "
        f"poll={poll_seconds:.3f} INPUT={ctypes.sizeof(INPUT)}"
    )

    try:
        while True:
            now = time.monotonic()
            if hwnd is None or not user32.IsWindow(hwnd):
                controller.release()
                pid = process_name = hwnd = active_rect = None
                if now >= next_process_scan:
                    pid, process_name = find_process(process_names)
                    hwnd = find_window(pid) if pid else None
                    next_process_scan = now + 0.75
                    if hwnd:
                        log(f"watching {process_name} pid={pid} hwnd={hwnd}")
                time.sleep(0.10)
                continue

            foreground = user32.GetForegroundWindow()
            foreground_pid = wintypes.DWORD()
            if foreground:
                user32.GetWindowThreadProcessId(foreground, ctypes.byref(foreground_pid))
            if foreground_pid.value != pid:
                controller.release()
                time.sleep(poll_seconds)
                continue

            if active_rect is None or now >= next_rect_refresh or not controller.clipped:
                active_rect = get_active_rect(hwnd, edge_zone)
                controller.clip(active_rect)
                next_rect_refresh = now + 0.50

            cursor = POINT()
            if not user32.GetCursorPos(ctypes.byref(cursor)):
                controller.release()
                time.sleep(poll_seconds)
                continue

            desired = set()
            if cursor.x <= active_rect.left + edge_zone - 1:
                desired.add("left")
            elif cursor.x >= active_rect.right - edge_zone:
                desired.add("right")
            if cursor.y <= active_rect.top + edge_zone - 1:
                desired.add("up")
            elif cursor.y >= active_rect.bottom - edge_zone:
                desired.add("down")
            controller.set_directions(desired)
            time.sleep(poll_seconds)
    finally:
        controller.release()
        kernel32.CloseHandle(mutex)
        log("helper stopped")


if __name__ == "__main__":
    raise SystemExit(main())
