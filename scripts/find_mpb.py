import hashlib, pathlib

PRE = pathlib.Path(r'e:\RAID_Recovery_Backup\RAID_Recovery_Backup\DATABASE_20261030_025853\USB_VLK5JGVY_strategy2_preimage_20261030_231035_369')
print('sha256 of 4096 zero bytes:', hashlib.sha256(b'\0' * 4096).hexdigest())
print('sha256 of 4096 FF bytes  :', hashlib.sha256(b'\xff' * 4096).hexdigest())

MAGIC = b'Intel Raid ISM Cfg Sig.'
for name, base in (('VLK5JGVY_range001_offset8001563156480_len65536.bin', 8001563156480),):
    d = (PRE / name).read_bytes()
    print(name, 'len', len(d), 'sha', hashlib.sha256(d).hexdigest())
    idx, hits = d.find(MAGIC), []
    while idx != -1:
        hits.append({'file_off': idx, 'disk_off': base + idx, 'lba512': (base + idx) // 512,
                     'align4096': (base + idx) % 4096})
        idx = d.find(MAGIC, idx + 1)
    print(' signature hits:', hits)
    nz = [i for i in range(len(d)) if d[i]]
    print(' nonzero bytes in this 64K:', len(nz), 'first', nz[:8], 'last', nz[-8:] if nz else None)

# full last 16MiB from the acquisition backup
for p in sorted(pathlib.Path(r'e:\RAID_Recovery_Backup\RAID_Recovery_Backup\DATABASE_20261030_025853').rglob('VLK5JGVY_last16MiB.bin')):
    d = p.read_bytes()
    base = 8001563222016 - 16 * 1024 * 1024
    print(p)
    print('  len', len(d), 'sha', hashlib.sha256(d).hexdigest())
    idx, hits = d.find(MAGIC), []
    while idx != -1:
        hits.append({'file_off': idx, 'disk_off': base + idx, 'lba512': (base + idx) // 512,
                     'align4096': (base + idx) % 4096})
        idx = d.find(MAGIC, idx + 1)
    print('  +1.3.00 hits:', hits)
    print('  +2.0.00 hits:', [{'file_off': i, 'lba512': (base + i) // 512}
                                for i in [d.find(b'Intel Raid ISM Cfg Sig. 2.0.00')] if i != -1])
    print('  tail32', d[-32:].hex())
