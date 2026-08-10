import ctypes
import struct
import sys
import time
from ctypes import wintypes

from ra3_auto.paths import PROCESS_NAMES_ARGUMENT, log_path
from ra3_auto.processes import find_first_process

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
MEM_COMMIT = 0x1000
PAGE_READWRITE = 0x04
LOG_PATH = log_path("ore100k.log")


def log(message):
    with LOG_PATH.open("a", encoding="utf-8") as stream:
        stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")

class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                ('AllocationProtect', wintypes.DWORD), ('RegionSize', ctypes.c_size_t),
                ('State', wintypes.DWORD), ('Protect', wintypes.DWORD), ('Type', wintypes.DWORD)]

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.OpenProcess.restype = wintypes.HANDLE
k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.ReadProcessMemory.restype = wintypes.BOOL
k32.WriteProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.restype = wintypes.BOOL
k32.VirtualProtectEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
k32.VirtualProtectEx.restype = wintypes.BOOL
k32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t
k32.CloseHandle.argtypes = [wintypes.HANDLE]

def read_mem(h, addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t(0)
    ok = k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got))
    return buf.raw[:got.value] if ok else None

def write_mem(h, addr, data):
    buf = ctypes.create_string_buffer(data)
    got = ctypes.c_size_t(0)
    old = wintypes.DWORD(0)
    k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), PAGE_READWRITE, ctypes.byref(old))
    ok = k32.WriteProcessMemory(h, ctypes.c_void_p(addr), buf, len(data), ctypes.byref(got))
    k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), old.value, ctypes.byref(old))
    return ok

def find_pattern(h, needle):
    hits = []
    addr = 0
    while addr < 0x7FFFFFFF0000:
        mbi = MEMORY_BASIC_INFORMATION()
        r = k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi))
        if not r: break
        size = mbi.RegionSize
        if size > 0 and (mbi.State & MEM_COMMIT):
            prot = mbi.Protect & 0xFF
            if prot in (0x04, 0x02, 0x40, 0x20, 0x08):
                chunk = 65536
                for off in range(0, size, chunk):
                    n = min(chunk, size - off)
                    data = read_mem(h, mbi.BaseAddress + off, n)
                    if not data: continue
                    idx = 0
                    while True:
                        i = data.find(needle, idx)
                        if i < 0: break
                        hits.append(mbi.BaseAddress + off + i)
                        idx = i + 1
        addr += size if size > 0 else 0x1000
    return hits

def main():
    if "--self-test" in sys.argv:
        find_first_process([])
        return 0

    proc_names = [
        name.strip()
        for name in (
            sys.argv[1]
            if len(sys.argv) > 1
            else PROCESS_NAMES_ARGUMENT
        ).split(',')
        if name.strip()
    ]
    patch = struct.pack('<III', 30000, 250, 60)
    newval = struct.pack('<I', 100000)

    log(f"helper started processes={','.join(proc_names)}")
    active_pid = None
    patched_addresses = []
    while True:
        pid, proc_name = find_first_process(proc_names)
        if pid != active_pid:
            active_pid = pid
            patched_addresses = []
            if pid:
                log(f"found {proc_name} pid={pid}")
        if pid:
            h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION, False, pid)
            if h:
                if not patched_addresses:
                    hits = find_pattern(h, patch)
                    for x in hits:
                        current = read_mem(h, x, 4)
                        if current and len(current) == 4 and struct.unpack('<I', current)[0] == 30000:
                            if write_mem(h, x, newval):
                                patched_addresses.append(x)
                                log(f"patched 30000->100000 at 0x{x:x}")
                else:
                    valid_addresses = []
                    for x in patched_addresses:
                        current = read_mem(h, x, 4)
                        if not current or len(current) != 4:
                            continue
                        value = struct.unpack('<I', current)[0]
                        if value == 30000:
                            write_mem(h, x, newval)
                        if value in (30000, 100000):
                            valid_addresses.append(x)
                    patched_addresses = valid_addresses
                k32.CloseHandle(h)
        time.sleep(5)

if __name__ == '__main__':
    raise SystemExit(main())
