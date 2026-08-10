"""Persistent, windowless supervisor for RA3 and Uprising enhancements."""

import argparse
import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path

from ra3_auto.paths import PROCESS_NAMES_ARGUMENT, log_path
from ra3_auto.processes import process_entries


FROZEN = bool(getattr(sys, "frozen", False))
PROJECT_ROOT = (
    Path(sys.executable).resolve().parent
    if FROZEN
    else Path(__file__).resolve().parents[2]
)
SOURCE_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = log_path("supervisor.log")
CHILD_LOG_PATH = log_path("children.log")

ERROR_ALREADY_EXISTS = 183
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
PROCESS_TERMINATE = 0x0001
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
kernel32.CreateMutexW.restype = ctypes.c_void_p
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
kernel32.OpenProcess.restype = ctypes.c_void_p
kernel32.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
kernel32.TerminateProcess.restype = ctypes.c_int


def log(message):
    with LOG_PATH.open("a", encoding="utf-8") as stream:
        stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def acquire_single_instance():
    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(
        None, False, "Local\\RA3AutoEnhance_Supervisor_v1"
    )
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        log("duplicate supervisor ignored")
        return None
    return handle


def python_windowless():
    executable = Path(sys.executable)
    candidate = executable.with_name("pythonw.exe")
    return candidate if candidate.exists() else executable


def child_specs():
    if FROZEN:
        return {
            "borderless": [str(PROJECT_ROOT / "RA3Borderless.exe"), PROCESS_NAMES_ARGUMENT],
            "edge-scroll": [str(PROJECT_ROOT / "RA3EdgeScroll.exe"), PROCESS_NAMES_ARGUMENT],
            "ore-watchdog": [str(PROJECT_ROOT / "RA3Ore100K.exe"), PROCESS_NAMES_ARGUMENT],
            "steam-options": [str(PROJECT_ROOT / "RA3SteamOptions.exe")],
        }

    pythonw = str(python_windowless())
    return {
        "borderless": [pythonw, "-m", "ra3_auto.borderless", PROCESS_NAMES_ARGUMENT],
        "edge-scroll": [pythonw, "-m", "ra3_auto.edge_scroll", PROCESS_NAMES_ARGUMENT],
        "ore-watchdog": [pythonw, "-m", "ra3_auto.ore100k", PROCESS_NAMES_ARGUMENT],
        "steam-options": [pythonw, "-m", "ra3_auto.steam_options"],
    }


def child_environment():
    environment = os.environ.copy()
    if not FROZEN:
        existing = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            str(SOURCE_ROOT) if not existing else str(SOURCE_ROOT) + os.pathsep + existing
        )
    return environment


def start_child(name, command, child_log):
    executable = Path(command[0])
    if not executable.exists():
        log(f"cannot start {name}: executable missing: {executable}")
        return None
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        env=child_environment(),
        stdin=subprocess.DEVNULL,
        stdout=child_log,
        stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
        close_fds=True,
    )
    log(f"started {name} pid={process.pid}")
    return process


def descendant_pids(root_pid):
    children = {}
    for pid, parent_pid, _name in process_entries():
        children.setdefault(parent_pid, []).append(pid)
    ordered = []

    def visit(parent_pid):
        for child_pid in children.get(parent_pid, []):
            visit(child_pid)
            ordered.append(child_pid)

    visit(root_pid)
    return ordered


def terminate_pid(pid):
    handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not handle:
        return
    try:
        kernel32.TerminateProcess(handle, 0)
    finally:
        kernel32.CloseHandle(handle)


def terminate_process_tree(process):
    if not process or process.poll() is not None:
        return
    for pid in descendant_pids(process.pid):
        terminate_pid(pid)
    process.terminate()


def self_test():
    if FROZEN:
        missing = [
            Path(command[0]).name
            for command in child_specs().values()
            if not Path(command[0]).exists()
        ]
        if missing:
            log(f"self-test missing executables: {','.join(missing)}")
            return 1
    else:
        __import__("ra3_auto.borderless")
        __import__("ra3_auto.edge_scroll")
        __import__("ra3_auto.ore100k")
        __import__("ra3_auto.steam_options")
    log("self-test passed")
    return 0


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-seconds",
        type=float,
        default=0.0,
        help="stop cleanly after this many seconds",
    )
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.self_test:
        return self_test()

    mutex = acquire_single_instance()
    if mutex is None:
        return 0
    children = {}
    failures = {}
    retry_at = {}
    child_log = CHILD_LOG_PATH.open("a", encoding="utf-8")
    log(f"supervisor started executable={sys.executable}")
    deadline = time.monotonic() + args.run_seconds if args.run_seconds > 0 else None
    try:
        while True:
            now = time.monotonic()
            if deadline is not None and now >= deadline:
                log("bounded run complete")
                break
            for name, command in child_specs().items():
                process = children.get(name)
                if process is not None and process.poll() is not None:
                    count = failures.get(name, 0) + 1
                    failures[name] = count
                    delay = min(60.0, 3.0 * (2 ** min(count - 1, 4)))
                    retry_at[name] = now + delay
                    log(
                        f"{name} exited code={process.returncode}; "
                        f"restart in {delay:.0f}s"
                    )
                    children[name] = None
                    process = None
                if process is None and now >= retry_at.get(name, 0.0):
                    children[name] = start_child(name, command, child_log)
            time.sleep(3.0)
    finally:
        for name, process in children.items():
            if process and process.poll() is None:
                log(f"stopping {name} pid={process.pid}")
                terminate_process_tree(process)
        for process in children.values():
            if process:
                try:
                    process.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5.0)
        child_log.close()
        kernel32.CloseHandle(mutex)
        log("supervisor stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
