"""One-shot, version-pinned refill of identified Uprising OreNode instances.

Retail 1.1 disassembly: OreNode constructor 0x71a6a0, serializer
0x70a940, depletion setter 0x756960. +0x14 is gathered ore; +0x28
is initial ore. +0x24 is the low/depleted announcement state.
No executable edits, code injection, recurring refills or blanket number edits.
"""
import argparse
import ctypes
import hashlib
import json
import shutil
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

from ra3_auto import ore100k as o
from ra3_auto.ore_setup import discover_game
from ra3_auto.ore_disk import ROOT

VTABLE = 0xc3a978

def u32(data, offset=0):
    return struct.unpack_from('<I', data, offset)[0]

def read(handle, address, length):
    result = o.read_mem(handle, address, length)
    if result is None or len(result) != length:
        raise RuntimeError(f'Cannot read ore structure at {address:#x}')
    return result

def node(handle, address):
    data = read(handle, address, 0x2c)
    if (u32(data),u32(data,12),u32(data,16)) != (VTABLE,0xc3a830,0xc35c44):
        raise ValueError('Ore instance identity changed')
    module, owner = u32(data,4),u32(data,8)
    md = read(handle,module,20)
    if tuple(struct.unpack('<5I',md)) != (0x8e220ee2,0xfee87083,100000,250,60):
        raise ValueError('Unexpected ore module identity or defaults')
    template = u32(read(handle,owner+4,4))
    if read(handle,template+4,8) != struct.pack('<II',0x942fff2d,0x212445f1):
        raise ValueError('Owner is not the retail OreNode object')
    arr = u32(read(handle,owner+0x320,4))
    modules = struct.unpack('<32I',read(handle,arr,128))
    if 0 not in modules or address not in modules[:modules.index(0)]:
        raise ValueError('Ore module is not attached to its owner')
    gathered,initial,state = u32(data,0x14),u32(data,0x28),u32(data,0x24)
    if not (initial in (30000,100000) and gathered <= initial and state <= 2):
        raise ValueError('Invalid ore counters')
    return dict(address=address,owner=owner,module=module,initial=initial,
                gathered=gathered,current=initial-gathered,notification_state=state)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    for option in ('inspect', 'apply', 'self-test'):
        actions.add_argument('--' + option, action='store_true')
    parser.add_argument('--expected-mines', type=int)
    parser.add_argument('--game-dir', type=Path)
    parser.add_argument('--saves-dir', type=Path, default=Path.home() / 'Saved Games/Red Alert 3 Uprising')
    args = parser.parse_args()
    if args.self_test:
        assert u32(struct.pack('<I',100000)) == 100000
        return
    apply = args.apply
    if apply and (args.expected_mines is None or args.expected_mines < 1):
        parser.error('--apply requires --expected-mines from the inspection result')
    game = args.game_dir.resolve() if args.game_dir else discover_game()
    if game is None: raise RuntimeError('Uprising not found; supply --game-dir')
    engine = game / 'Data/ra3ep1_1.1.game'
    binary = engine.read_bytes()
    # Verify the exact routines used to derive field meanings before any writes.
    for addr,code in [(0x71a6e6,'8b4f085f894e28'),
                      (0x75696f,'8b5e288beb2be8'),
                      (0x70a98c,'8d4f14'),(0x70a9fc,'83c728')]:
        expected=bytes.fromhex(code)
        if binary[addr-0x400000:addr-0x400000+len(expected)] != expected:
            raise RuntimeError(f'Unsupported engine at {addr:#x}')
    pid,name=o.find_first_process(['ra3ep1_1.1.game'])
    if not pid: raise RuntimeError('No Uprising engine')
    handle=o.k32.OpenProcess(0x410 | (0x28|0x800 if apply else 0),False,pid)
    if not handle: raise ctypes.WinError(ctypes.get_last_error())
    suspended=False
    ntdll=ctypes.WinDLL('ntdll')
    for f in [ntdll.NtSuspendProcess,ntdll.NtResumeProcess]:
        f.argtypes=[ctypes.c_void_p]; f.restype=ctypes.c_long
    try:
        query = o.k32.QueryFullProcessImageNameW
        query.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_uint32)]
        query.restype=ctypes.c_int
        image=ctypes.create_unicode_buffer(32768)
        size=ctypes.c_uint32(len(image))
        if not query(handle,0,image,ctypes.byref(size)) or Path(image.value).resolve()!=engine.resolve():
            raise RuntimeError('Running engine does not match the validated installation')
        addresses=[]
        for a in o.find_pattern(handle,struct.pack('<I',VTABLE)):
            data=o.read_mem(handle,a,20)
            if data and len(data)==20 and (u32(data,12),u32(data,16))==(0xc3a830,0xc35c44):
                node(handle,a)
                addresses.append(a)
        if not addresses or len(set(addresses)) != len(addresses):
            raise RuntimeError('No uniquely identified ore mines')
        if args.expected_mines is not None and len(addresses) != args.expected_mines:
            raise RuntimeError(f'Expected {args.expected_mines} ore mines, found {len(addresses)}')
        if not apply:
            print(json.dumps([node(handle,a) for a in addresses],indent=2))
            return
        stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
        backup=ROOT/'backups'/f'loaded-save-refill-{stamp}'
        backup.mkdir(parents=True,exist_ok=False)
        files=[]
        for p in args.saves_dir.rglob('*.RA3U*'):
            if not p.is_file(): continue
            dest=backup/p.relative_to(args.saves_dir)
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(p,dest)
            digest=hashlib.sha256(p.read_bytes()).hexdigest()
            if hashlib.sha256(dest.read_bytes()).hexdigest()!=digest:
                raise RuntimeError('Save backup verification failed')
            files.append(dict(path=str(p),backup=str(dest),sha256=digest))
        if not files: raise RuntimeError('No original Uprising saves backed up')
        status=ntdll.NtSuspendProcess(handle)
        if status!=0: raise RuntimeError(f'Cannot briefly suspend engine: {status}')
        suspended=True
        before=[node(handle,a) for a in addresses]
        receipt=dict(pid=pid,engine=str(engine),engine_sha256=hashlib.sha256(binary).hexdigest(),
                     time=datetime.now(timezone.utc).isoformat(),saves=files,before=before,
                     fields={'0x14':'gathered ore','0x24':'notification state','0x28':'initial ore'})
        receipt_path=backup/'ore-counters-before.json'
        receipt_path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        written=[]
        try:
            for item in before:
                for offset,value in [(0x28,100000),(0x14,0),(0x24,0)]:
                    address=item['address']+offset
                    old=read(handle,address,4)
                    buf=ctypes.create_string_buffer(struct.pack('<I',value))
                    count=ctypes.c_size_t()
                    written.append((address,old))
                    if not o.k32.WriteProcessMemory(handle,ctypes.c_void_p(address),buf,4,ctypes.byref(count)) or count.value!=4:
                        raise ctypes.WinError(ctypes.get_last_error())
            after=[node(handle,a) for a in addresses]
            if not all(x['initial']==100000 and x['current']==100000 and x['notification_state']==0 for x in after):
                raise RuntimeError('Ore refill readback failed')
        except BaseException:
            for address,old in reversed(written):
                count=ctypes.c_size_t()
                buf=ctypes.create_string_buffer(old)
                o.k32.WriteProcessMemory(handle,ctypes.c_void_p(address),buf,4,ctypes.byref(count))
            raise
        finally:
            result=ntdll.NtResumeProcess(handle)
            if result!=0: raise RuntimeError(f'Engine resume failed: {result}')
            suspended=False
        receipt['after']=after
        receipt['status']='verified live refill; save in-game to persist'
        receipt_path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
        print(json.dumps(dict(mines=len(after),initial=100000,current_at_refill=100000,
                             backup=str(backup),receipt=str(receipt_path))))
    finally:
        if suspended: ntdll.NtResumeProcess(handle)
        o.k32.CloseHandle(handle)

if __name__=='__main__': main()
