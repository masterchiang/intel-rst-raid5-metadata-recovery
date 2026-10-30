"""Generic READ-ONLY post-write verification for one DATABASE member.

Compares the current end-of-disk 64 KiB with the archived end-of-disk backup,
parses the on-disk MPB and replays the reference state rule.
"""
import ctypes as c
from ctypes import wintypes as w
import hashlib, json, pathlib, struct, sys

OUT = pathlib.Path(r'e:\RAID_Recovery_Backup\VLK5JGVY_repair_20261031')
ROOT = pathlib.Path(r'e:\RAID_Recovery_Backup\RAID_Recovery_Backup\DATABASE_20261030_025853')
SIZE = 8001563222016
BLK = 8001563217920
ARCHIVE_TAIL = {
    'VKH3B65X': ROOT / r'USB_VKH3B65X_acquisition_20261030_180348\VKH3B65X_last16MiB.bin',
    'VJGH3P3X': ROOT / r'USB_VJGH3P3X_acquisition_20261030_182622\VJGH3P3X_last16MiB.bin',
    'VLK5JGVY': ROOT / r'DATABASE_20261030_025853\VLK5JGVY_last16MiB.bin',
    'VKJGM9XX': ROOT / r'USB_VKJGM9XX_acquisition_20261030_183527\VKJGM9XX_last16MiB.bin',
}
EXPECT_CFG_SHA = 'a773a7513c17ba35d5a1b58d6e9f06fe93094e0e6b1e628362bd3f9d92dcb36b'

disk_no, serial = int(sys.argv[1]), sys.argv[2].upper()
source = rf'\\.\PhysicalDrive{disk_no}'

k = c.WinDLL('kernel32', use_last_error=True)
k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
k.CreateFileW.restype = w.HANDLE
k.SetFilePointerEx.argtypes = [w.HANDLE, c.c_longlong, c.POINTER(c.c_longlong), w.DWORD]
k.SetFilePointerEx.restype = w.BOOL
k.ReadFile.argtypes = [w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p]
k.ReadFile.restype = w.BOOL
k.CloseHandle.argtypes = [w.HANDLE]

h = k.CreateFileW(source, 0x80000000, 3, None, 3, 0, None)
if h == c.c_void_p(-1).value:
    raise c.WinError(c.get_last_error())


def rd(off, size):
    pos = c.c_longlong()
    assert k.SetFilePointerEx(h, off, c.byref(pos), 0) and pos.value == off
    buf = c.create_string_buffer(size)
    n = w.DWORD()
    assert k.ReadFile(h, buf, size, c.byref(n), None) and n.value == size
    return buf.raw


head = rd(0, 4096)
tail = rd(SIZE - 65536, 65536)
k.CloseHandle(h)

arch_tail = ARCHIVE_TAIL[serial].read_bytes()[-65536:]
diff = [i for i in range(65536) if tail[i] != arch_tail[i]]
rel = BLK - (SIZE - 65536)
cfg = tail[rel + 3072:rel + 3072 + 512] + tail[rel + 2560:rel + 2560 + 72]


def cks(b):
    n = struct.unpack_from('<I', b, 0x24)[0] // 4
    return (sum(struct.unpack_from('<I', b, i * 4)[0] for i in range(n))
            - struct.unpack_from('<I', b, 0x20)[0]) & 0xFFFFFFFF


def rec(b, i):
    o = 0xD8 + i * 48
    return {'idx': i, 'serial': repr(b[o:o + 16]),
            'scsi_id': '%08x' % struct.unpack_from('<I', b, o + 20)[0],
            'status': '%08x' % struct.unpack_from('<I', b, o + 24)[0],
            'blocks_lo': struct.unpack_from('<I', b, o + 16)[0],
            'blocks_hi': struct.unpack_from('<I', b, o + 32)[0]}


failed, slots = 0, []
for slot in range(4):
    o = struct.unpack_from('<I', cfg, 568 + 4 * slot)[0]
    r = rec(cfg, o & 0xFFFFFF)
    f, rb = bool(int(r['status'], 16) & 4), bool(o & (1 << 24))
    failed += 1 if (f or rb) else 0
    slots.append({'slot': slot, 'serial': r['serial'], 'failed_bit': f, 'out_of_sync': rb})

res = {'serial_expected': serial, 'disk_number': disk_no,
       'changed_bytes_in_last64k': len(diff),
       'changed_offsets_in_64k': diff,
       'all_changes_inside_mpb_sector': all(rel <= i < rel + 4096 for i in diff),
       'post_4k_sha256': hashlib.sha256(tail[rel:rel + 4096]).hexdigest(),
       'cfg_sha256': hashlib.sha256(cfg).hexdigest(),
       'cfg_matches_group_target': hashlib.sha256(cfg).hexdigest() == EXPECT_CFG_SHA,
       'checksum_stored': '%08x' % struct.unpack_from('<I', cfg, 0x20)[0],
       'checksum_computed': '%08x' % cks(cfg),
       'generation': struct.unpack_from('<I', cfg, 0x2C)[0],
       'family': '%08x' % struct.unpack_from('<I', cfg, 0x28)[0],
       'map_state': cfg[534], 'raid_level': cfg[535], 'num_members': cfg[536],
       'failed_disk_num': cfg[538],
       'ordinals': ['%08x' % struct.unpack_from('<I', cfg, 568 + 4 * i)[0] for i in range(4)],
       'disks': [rec(cfg, i) for i in range(4)],
       'replay_failed_count': failed,
       'replay_state': {0: 'normal', 2: 'degraded', 3: 'failed'}[3 if failed >= 2 else (2 if failed == 1 else 0)],
       'slots': slots,
       'head4k_sha256': hashlib.sha256(head).hexdigest()}
OUT.joinpath('postwrite_%s.json' % serial).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(res, ensure_ascii=False, indent=2))
