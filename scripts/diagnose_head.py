"""READ-ONLY: compare the current first 64 KiB of the attached member with the archive."""
import ctypes as c
from ctypes import wintypes as w
import hashlib, json, pathlib, sys

ROOT = pathlib.Path(r'e:\RAID_Recovery_Backup\RAID_Recovery_Backup\DATABASE_20261030_025853')
ARCH = {
    'VKH3B65X': ROOT / r'USB_VKH3B65X_acquisition_20261030_180348\VKH3B65X_first16MiB.bin',
    'VJGH3P3X': ROOT / r'USB_VJGH3P3X_acquisition_20261030_182622\VJGH3P3X_first16MiB.bin',
    'VKJGM9XX': ROOT / r'USB_VKJGM9XX_acquisition_20261030_183527\VKJGM9XX_first16MiB.bin',
    'VLK5JGVY': ROOT / r'DATABASE_20261030_025853\VLK5JGVY_last16MiB.bin',
}
disk_no, serial = int(sys.argv[1]), sys.argv[2].upper()
src = rf'\\.\PhysicalDrive{disk_no}'

k = c.WinDLL('kernel32', use_last_error=True)
k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
k.CreateFileW.restype = w.HANDLE
k.SetFilePointerEx.argtypes = [w.HANDLE, c.c_longlong, c.POINTER(c.c_longlong), w.DWORD]
k.ReadFile.argtypes = [w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p]
k.CloseHandle.argtypes = [w.HANDLE]

h = k.CreateFileW(src, 0x80000000, 3, None, 3, 0, None)
if h == c.c_void_p(-1).value:
    raise c.WinError(c.get_last_error())


def rd(off, size):
    pos = c.c_longlong()
    assert k.SetFilePointerEx(h, off, c.byref(pos), 0) and pos.value == off
    buf = c.create_string_buffer(size)
    n = w.DWORD()
    ok = k.ReadFile(h, buf, size, c.byref(n), None)
    if not ok:
        raise c.WinError(c.get_last_error())
    if n.value != size:
        raise RuntimeError('short read %d/%d' % (n.value, size))
    return buf.raw


a = rd(0, 65536)
b = rd(0, 65536)
k.CloseHandle(h)

arch = ARCH[serial].read_bytes()
head = arch[:65536] if 'last16MiB' not in ARCH[serial].name else None
print('double read stable:', a == b)
print('current  chunk sha256:', hashlib.sha256(a).hexdigest())
print('zeros sha256         :', hashlib.sha256(bytes(65536)).hexdigest())
if head:
    print('archived chunk sha256:', hashlib.sha256(head).hexdigest())
    blocks = []
    for i in range(0, 65536, 4096):
        same = a[i:i + 4096] == head[i:i + 4096]
        blocks.append({'lba_start': i // 512, 'equal': same,
                       'current_sha': hashlib.sha256(a[i:i + 4096]).hexdigest()[:16],
                       'arch_sha': hashlib.sha256(head[i:i + 4096]).hexdigest()[:16]})
    print('per-4KiB equality:')
    for r in blocks:
        print('  LBA %6d..%6d  %s  cur=%s arch=%s' % (r['lba_start'], r['lba_start'] + 7,
                                                     'OK ' if r['equal'] else 'DIFF', r['current_sha'], r['arch_sha']))
    print('first 64 bytes current:', a[:64].hex())
    print('first 64 bytes archive:', head[:64].hex())
