"""READ-ONLY pre-write verification for the VLK5JGVY IMSM metadata repair.

Opens \\.\PhysicalDriveN with GENERIC_READ only. Only IOCTL_DISK_GET_LENGTH_INFO,
IOCTL_STORAGE_GET_DEVICE_NUMBER, ATA IDENTIFY DEVICE (0xEC, DATA IN) and ReadFile
are issued. No write/format/state-changing ioctl exists in this file.

Outputs a JSON report plus the exact pre/post 4096-byte physical sector images.
"""
import ctypes as c
from ctypes import wintypes as w
import hashlib, json, pathlib, struct, sys
from datetime import datetime, timezone, timedelta

OUT = pathlib.Path(r'e:\RAID_Recovery_Backup\VLK5JGVY_repair_20261031')
CMP = pathlib.Path(r'e:\RAID_Recovery_Backup\RAID_Recovery_Backup\DATABASE_20261030_025853\four_member_offline_comparison_20261030_183739')
PRE = pathlib.Path(r'e:\RAID_Recovery_Backup\RAID_Recovery_Backup\DATABASE_20261030_025853\USB_VLK5JGVY_strategy2_preimage_20261030_231035_369')

SIZE = 8001563222016
BLK_OFF = 8001563217920
ANCHOR_IN_BLK = 3072
EXT_IN_BLK = 2560
EXPECTED_SERIAL = 'VLK5JGVY'
ARCHIVED_4K_SHA = '35ac0f1e4e1ff396db4a5643330948ab9a4e4d821f538af2a33da2b6549f0218'

disk_no = int(sys.argv[1])
source = rf'\\.\PhysicalDrive{disk_no}'

k = c.WinDLL('kernel32', use_last_error=True)
k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
k.CreateFileW.restype = w.HANDLE
k.DeviceIoControl.argtypes = [w.HANDLE, w.DWORD, c.c_void_p, w.DWORD, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p]
k.DeviceIoControl.restype = w.BOOL
k.SetFilePointerEx.argtypes = [w.HANDLE, c.c_longlong, c.POINTER(c.c_longlong), w.DWORD]
k.SetFilePointerEx.restype = w.BOOL
k.ReadFile.argtypes = [w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p]
k.ReadFile.restype = w.BOOL
k.CloseHandle.argtypes = [w.HANDLE]
k.CloseHandle.restype = w.BOOL


class SPT(c.Structure):
    _fields_ = [('Length', w.USHORT), ('ScsiStatus', c.c_ubyte), ('PathId', c.c_ubyte), ('TargetId', c.c_ubyte),
                ('Lun', c.c_ubyte), ('CdbLength', c.c_ubyte), ('SenseInfoLength', c.c_ubyte), ('DataIn', c.c_ubyte),
                ('DataTransferLength', w.ULONG), ('TimeOutValue', w.ULONG), ('DataBufferOffset', c.c_size_t),
                ('SenseInfoOffset', w.ULONG), ('Cdb', c.c_ubyte * 16)]


def ata_text(data, start, end):
    raw = data[start:end]
    return bytes(v for i in range(0, len(raw), 2) for v in (raw[i + 1], raw[i])).decode('ascii', 'strict').strip(' \0')


def identify(h, cdb_len):
    sense_offset, data_offset = 56, 88
    size = data_offset + 512
    req = SPT()
    req.Length = c.sizeof(SPT)
    req.CdbLength = cdb_len
    req.SenseInfoLength = 32
    req.DataIn = 1
    req.DataTransferLength = 512
    req.TimeOutValue = 10
    req.DataBufferOffset = data_offset
    req.SenseInfoOffset = sense_offset
    req.Cdb[0] = 0x85 if cdb_len == 16 else 0xA1
    req.Cdb[1] = 0x08
    req.Cdb[2] = 0x0E
    req.Cdb[6 if cdb_len == 16 else 4] = 1
    req.Cdb[13 if cdb_len == 16 else 8] = 0xA0
    req.Cdb[14 if cdb_len == 16 else 9] = 0xEC
    buf = c.create_string_buffer(size)
    c.memmove(buf, c.byref(req), c.sizeof(req))
    returned = w.DWORD()
    ok = k.DeviceIoControl(h, 0x0004D004, buf, size, buf, size, c.byref(returned), None)
    err = c.get_last_error() if not ok else 0
    if not ok:
        if err in (1, 50, 87):
            return None
        raise c.WinError(err)
    resp = SPT.from_buffer_copy(buf.raw[:56])
    if resp.ScsiStatus != 0:
        return None
    data = buf.raw[data_offset:data_offset + 512]
    if data == bytes(512) or data == bytes([255]) * 512:
        return None
    return data


report = {'mode': 'READ_ONLY', 'source': source,
          'started': datetime.now(timezone(timedelta(hours=8))).isoformat()}

h = k.CreateFileW(source, 0x80000000, 3, None, 3, 0, None)   # GENERIC_READ
if h == c.c_void_p(-1).value:
    raise c.WinError(c.get_last_error())
try:
    got = w.DWORD()
    length = c.c_longlong()
    if not k.DeviceIoControl(h, 0x0007405C, None, 0, c.byref(length), 8, c.byref(got), None):
        raise c.WinError(c.get_last_error())
    if length.value != SIZE:
        raise RuntimeError('capacity %d != %d' % (length.value, SIZE))
    dev = (w.DWORD * 3)()
    if not k.DeviceIoControl(h, 0x002D1080, None, 0, c.byref(dev), 12, c.byref(got), None):
        raise c.WinError(c.get_last_error())
    if dev[0] != 7 or dev[1] != disk_no:
        raise RuntimeError('device number mismatch %s' % list(dev))
    report['capacity'] = length.value
    report['device_number'] = list(dev)

    def read_exact(offset, size):
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

    tail = read_exact(SIZE - 65536, 65536)
    tail2 = read_exact(SIZE - 65536, 65536)
    if tail != tail2:
        raise RuntimeError('second 64KiB read differs')
    blk = read_exact(BLK_OFF, 4096)
    blk2 = read_exact(BLK_OFF, 4096)
    if blk != blk2:
        raise RuntimeError('second 4KiB read differs')
finally:
    k.CloseHandle(h)

hid = k.CreateFileW(source, 0xC0000000, 3, None, 3, 0, None)  # ACCESS required by IOCTL_SCSI_PASS_THROUGH
if hid == c.c_void_p(-1).value:
    raise c.WinError(c.get_last_error())
ident = None
try:
    for cdb_len in (16, 12):
        ident = identify(hid, cdb_len)
        if ident:
            break
finally:
    k.CloseHandle(hid)
if not ident:
    raise RuntimeError('ATA IDENTIFY unavailable; refusing to continue')
serial, model, fw = ata_text(ident, 20, 40), ata_text(ident, 54, 94), ata_text(ident, 46, 54)
sectors = struct.unpack_from('<Q', ident, 200)[0]
report['ata'] = {'serial': serial, 'model': model, 'firmware': fw, 'lba48_sectors': sectors}
if serial != EXPECTED_SERIAL or sectors * 512 != SIZE:
    raise RuntimeError('wrong disk: %s %d' % (serial, sectors))

report['tail64k'] = {'sha256': hashlib.sha256(tail).hexdigest(), 'double_read_equal': True}
report['tail_matches_archived_preimage'] = tail == (PRE / 'VLK5JGVY_range001_offset8001563156480_len65536.bin').read_bytes()
report['preimage_4k'] = {'offset': BLK_OFF, 'sha256': hashlib.sha256(blk).hexdigest(), 'double_read_equal': True,
                         'matches_archived': hashlib.sha256(blk).hexdigest() == ARCHIVED_4K_SHA}
(OUT / 'present_preimage_4k.bin').write_bytes(blk)

cfg = blk[ANCHOR_IN_BLK:ANCHOR_IN_BLK + 512] + blk[EXT_IN_BLK:EXT_IN_BLK + 72]
archived = (CMP / 'VLK5JGVY_IMSM_configuration.bin').read_bytes()
report['ondisk_cfg'] = {'sha256': hashlib.sha256(cfg).hexdigest(), 'equals_archived': cfg == archived,
                        'generation': struct.unpack_from('<I', cfg, 0x2C)[0],
                        'checksum_stored': '%08x' % struct.unpack_from('<I', cfg, 0x20)[0]}
report['archived_cfg_sha256'] = hashlib.sha256(archived).hexdigest()

target = (OUT / 'target_VLK5JGVY_MPB_584.bin').read_bytes()
assert len(target) == 584
post = bytearray(blk)
post[ANCHOR_IN_BLK:ANCHOR_IN_BLK + 512] = target[0:512]
post[EXT_IN_BLK:EXT_IN_BLK + 72] = target[512:584]
post = bytes(post)
(OUT / 'planned_postimage_4k.bin').write_bytes(post)
changed = [i for i in range(4096) if blk[i] != post[i]]
report['postimage_4k'] = {
    'sha256': hashlib.sha256(post).hexdigest(),
    'changed_offsets_in_block': changed,
    'changed_count': len(changed),
    'prefix_0_2560_preserved': blk[0:EXT_IN_BLK] == post[0:EXT_IN_BLK],
    'gap_2632_3072_preserved': blk[EXT_IN_BLK + 72:ANCHOR_IN_BLK] == post[EXT_IN_BLK + 72:ANCHOR_IN_BLK],
    'last_sector_preserved': blk[3584:4096] == post[3584:4096],
    'changed_bytes_all_inside_mpb': all(EXT_IN_BLK <= i < EXT_IN_BLK + 72 or ANCHOR_IN_BLK <= i < ANCHOR_IN_BLK + 512 for i in changed)}
report['status'] = 'READ_ONLY_VERIFICATION_COMPLETE'

OUT.joinpath('prewrite_verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
