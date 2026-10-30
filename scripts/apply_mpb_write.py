"""Apply the reviewed 584-byte IMSM MPB to ONE member, in place, on one physical sector.

Scope of the only write in this program:
  offset 8001563217920 (4096-byte physical sector, LBA 15628053160..15628053167)
  exactly 4096 bytes: read -> replace MPB anchor (block+3072, 512 B) and extended
  MPB (block+2560, first 72 B) -> write the whole sector back.
Everything else in the sector, and the whole rest of the disk, is untouched.

Dry-run unless --apply is given. Refuses when identity / capacity / current bytes
do not match the reviewed preimage, so it cannot hit the wrong disk or a changed disk.
"""
import ctypes as c
from ctypes import wintypes as w
import hashlib, json, pathlib, struct, sys
from datetime import datetime, timezone, timedelta

OUT = pathlib.Path(r'e:\RAID_Recovery_Backup\VLK5JGVY_repair_20261031')
SIZE = 8001563222016
BLK_OFF = 8001563217920
ANCHOR_IN_BLK, EXT_IN_BLK = 3072, 2560
EXPECTED_CFG_4 = {  # archived on-disk 584-byte MPB per member before the write
    'VLK5JGVY': '43c02ffb75553d39eac93234179b0152e350a024940adf81fb20d34951be6425',
    'VKH3B65X': 'b3c6013dee1ace62fb7a4b06ad2dbe6eb7e944d1f7e0b73e8ab1924302412f47',
    'VJGH3P3X': 'b3c6013dee1ace62fb7a4b06ad2dbe6eb7e944d1f7e0b73e8ab1924302412f47',
}
EXPECTED_PRE_4K = {
    'VLK5JGVY': '35ac0f1e4e1ff396db4a5643330948ab9a4e4d821f538af2a33da2b6549f0218',
    # C / D / A share the same gen-763553 MPB, so their last physical 4 KiB is identical
    # in the archived end-of-disk backups (SHA256 c2210c38...960e4).
    'VKH3B65X': 'c2210c381c7eb101c6022927887e8dbf74a8b3ee41aaa8322b9466c0ba3960e4',
    'VJGH3P3X': 'c2210c381c7eb101c6022927887e8dbf74a8b3ee41aaa8322b9466c0ba3960e4',
}

args = [a for a in sys.argv[1:] if not a.startswith('--')]
apply = '--apply' in sys.argv
disk_no = int(args[0])
serial = args[1].upper()
source = rf'\\.\PhysicalDrive{disk_no}'
assert serial in EXPECTED_CFG_4, serial
target_cfg = (OUT / 'target_VLK5JGVY_MPB_584.bin').read_bytes()
assert len(target_cfg) == 584
stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S_%f')[:-3]

k = c.WinDLL('kernel32', use_last_error=True)
k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
k.CreateFileW.restype = w.HANDLE
k.DeviceIoControl.argtypes = [w.HANDLE, w.DWORD, c.c_void_p, w.DWORD, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p]
k.DeviceIoControl.restype = w.BOOL
k.SetFilePointerEx.argtypes = [w.HANDLE, c.c_longlong, c.POINTER(c.c_longlong), w.DWORD]
k.SetFilePointerEx.restype = w.BOOL
k.ReadFile.argtypes = [w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p]
k.ReadFile.restype = w.BOOL
k.WriteFile.argtypes = [w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p]
k.WriteFile.restype = w.BOOL
k.FlushFileBuffers.argtypes = [w.HANDLE]
k.FlushFileBuffers.restype = w.BOOL
k.CloseHandle.argtypes = [w.HANDLE]
k.CloseHandle.restype = w.BOOL

GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
OPEN_EXISTING, FILE_FLAG_WRITE_THROUGH = 3, 0x80000000


class SPT(c.Structure):
    _fields_ = [('Length', w.USHORT), ('ScsiStatus', c.c_ubyte), ('PathId', c.c_ubyte), ('TargetId', c.c_ubyte),
                ('Lun', c.c_ubyte), ('CdbLength', c.c_ubyte), ('SenseInfoLength', c.c_ubyte), ('DataIn', c.c_ubyte),
                ('DataTransferLength', w.ULONG), ('TimeOutValue', w.ULONG), ('DataBufferOffset', c.c_size_t),
                ('SenseInfoOffset', w.ULONG), ('Cdb', c.c_ubyte * 16)]


def ata_text(d, s, e):
    raw = d[s:e]
    return bytes(v for i in range(0, len(raw), 2) for v in (raw[i + 1], raw[i])).decode('ascii', 'strict').strip(' \0')


def identify(h, cdb_len):
    req = SPT()
    req.Length = c.sizeof(SPT)
    req.CdbLength = cdb_len
    req.SenseInfoLength = 32
    req.DataIn = 1
    req.DataTransferLength = 512
    req.TimeOutValue = 10
    req.DataBufferOffset = 88
    req.SenseInfoOffset = 56
    req.Cdb[0] = 0x85 if cdb_len == 16 else 0xA1
    req.Cdb[1] = 0x08
    req.Cdb[2] = 0x0E
    req.Cdb[6 if cdb_len == 16 else 4] = 1
    req.Cdb[13 if cdb_len == 16 else 8] = 0xA0
    req.Cdb[14 if cdb_len == 16 else 9] = 0xEC
    buf = c.create_string_buffer(600)
    c.memmove(buf, c.byref(req), c.sizeof(req))
    n = w.DWORD()
    ok = k.DeviceIoControl(h, 0x0004D004, buf, 600, buf, 600, c.byref(n), None)
    if not ok:
        return None
    if SPT.from_buffer_copy(buf.raw[:56]).ScsiStatus != 0:
        return None
    return buf.raw[88:600]


def open_disk(access, flags=0):
    h = k.CreateFileW(source, access, 3, None, OPEN_EXISTING, flags, None)
    if h == c.c_void_p(-1).value:
        raise c.WinError(c.get_last_error())
    return h


def read_exact(h, offset, size):
    pos = c.c_longlong()
    if not k.SetFilePointerEx(h, offset, c.byref(pos), 0) or pos.value != offset:
        raise RuntimeError('seek failed')
    buf = c.create_string_buffer(size)
    n = w.DWORD()
    if not k.ReadFile(h, buf, size, c.byref(n), None):
        raise c.WinError(c.get_last_error())
    if n.value != size:
        raise RuntimeError('short read %d/%d' % (n.value, size))
    return buf.raw


def write_exact(h, offset, data):
    pos = c.c_longlong()
    if not k.SetFilePointerEx(h, offset, c.byref(pos), 0) or pos.value != offset:
        raise RuntimeError('seek failed')
    buf = c.create_string_buffer(data, len(data))
    n = w.DWORD()
    if not k.WriteFile(h, buf, len(data), c.byref(n), None):
        raise c.WinError(c.get_last_error())
    if n.value != len(data):
        raise RuntimeError('short write %d/%d' % (n.value, len(data)))
    if not k.FlushFileBuffers(h):
        raise c.WinError(c.get_last_error())


def assemble(blk):
    return blk[ANCHOR_IN_BLK:ANCHOR_IN_BLK + 512] + blk[EXT_IN_BLK:EXT_IN_BLK + 72]


def cfg_checksum(cfg):
    n = struct.unpack_from('<I', cfg, 0x24)[0] // 4
    return (sum(struct.unpack_from('<I', cfg, i * 4)[0] for i in range(n))
            - struct.unpack_from('<I', cfg, 0x20)[0]) & 0xFFFFFFFF


report = {'timestamp': stamp, 'mode': 'APPLY' if apply else 'DRY_RUN', 'source': source,
          'expected_serial': serial, 'write_offset': BLK_OFF, 'write_length': 4096,
          'target_cfg_sha256': hashlib.sha256(target_cfg).hexdigest()}

hid = open_disk(GENERIC_READ | GENERIC_WRITE)
try:
    n = w.DWORD()
    length = c.c_longlong()
    if not k.DeviceIoControl(hid, 0x0007405C, None, 0, c.byref(length), 8, c.byref(n), None):
        raise c.WinError(c.get_last_error())
    if length.value != SIZE:
        raise RuntimeError('capacity mismatch %d' % length.value)
    dev = (w.DWORD * 3)()
    k.DeviceIoControl(hid, 0x002D1080, None, 0, c.byref(dev), 12, c.byref(n), None)
    if dev[0] != 7 or dev[1] != disk_no:
        raise RuntimeError('device number mismatch %s' % list(dev))
    ident = identify(hid, 16) or identify(hid, 12)
    if not ident:
        raise RuntimeError('ATA IDENTIFY unavailable')
    got_serial = ata_text(ident, 20, 40)
    report['ata'] = {'serial': got_serial, 'model': ata_text(ident, 54, 94), 'firmware': ata_text(ident, 46, 54)}
    if got_serial != serial:
        raise RuntimeError('WRONG DISK: expected %s got %s' % (serial, got_serial))
    (OUT / ('%s_ATA_IDENTIFY_%s.bin' % (serial, stamp))).write_bytes(ident)

    pre = read_exact(hid, BLK_OFF, 4096)
    pre2 = read_exact(hid, BLK_OFF, 4096)
    if pre != pre2:
        raise RuntimeError('unstable 4KiB read')
    pre_sha = hashlib.sha256(pre).hexdigest()
    report['pre'] = {'sha256': pre_sha}
    exp = EXPECTED_PRE_4K.get(serial)
    if exp and pre_sha != exp:
        raise RuntimeError('preimage 4KiB changed since review: %s' % pre_sha)
    cur_cfg = assemble(pre)
    cur_sha = hashlib.sha256(cur_cfg).hexdigest()
    report['pre_cfg'] = {'sha256': cur_sha, 'expected': EXPECTED_CFG_4[serial]}
    if cur_sha != EXPECTED_CFG_4[serial]:
        raise RuntimeError('on-disk MPB is not the reviewed archived version')

    post = bytearray(pre)
    post[ANCHOR_IN_BLK:ANCHOR_IN_BLK + 512] = target_cfg[0:512]
    post[EXT_IN_BLK:EXT_IN_BLK + 72] = target_cfg[512:584]
    post = bytes(post)
    report['post'] = {'sha256': hashlib.sha256(post).hexdigest(),
                      'changed_offsets': [i for i in range(4096) if pre[i] != post[i]]}

    (OUT / ('%s_preimage4k_%s.bin' % (serial, stamp))).write_bytes(pre)
    (OUT / ('%s_planned_post4k_%s.bin' % (serial, stamp))).write_bytes(post)

    if not apply:
        report['status'] = 'DRY_RUN_OK: all preconditions met, nothing written'
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0)

    write_exact(hid, BLK_OFF, post)
    report['write_issued'] = True

    back = read_exact(hid, BLK_OFF, 4096)
    back2 = read_exact(hid, BLK_OFF, 4096)
    report['readback'] = {'sha256': hashlib.sha256(back).hexdigest(),
                          'equals_planned': back == post,
                          'stable': back == back2}
    new_cfg = assemble(back)
    report['readback_cfg'] = {'sha256': hashlib.sha256(new_cfg).hexdigest(),
                              'equals_target': new_cfg == target_cfg,
                              'checksum_stored': '%08x' % struct.unpack_from('<I', new_cfg, 0x20)[0],
                              'checksum_computed': '%08x' % cfg_checksum(new_cfg),
                              'generation': struct.unpack_from('<I', new_cfg, 0x2C)[0],
                              'map_state': new_cfg[534]}
    ident2 = identify(hid, 16) or identify(hid, 12)
    report['ata_after'] = ata_text(ident2, 20, 40) if ident2 else None
    if report['ata_after'] != serial:
        raise RuntimeError('identity changed after write')
    if back != post or not report['readback_cfg']['equals_target']:
        raise RuntimeError('READBACK MISMATCH - stop, do not retry blindly')
    (OUT / ('%s_postimage4k_%s.bin' % (serial, stamp))).write_bytes(back)
    report['status'] = 'WRITE_VERIFIED: preimage saved, readback equals planned image'
finally:
    k.CloseHandle(hid)

OUT.joinpath('apply_report_%s_%s.json' % (serial, stamp)).write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
