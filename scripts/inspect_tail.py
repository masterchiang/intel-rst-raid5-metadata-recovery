import hashlib, json, pathlib, struct

PRE = pathlib.Path(r'e:\RAID_Recovery_Backup\RAID_Recovery_Backup\DATABASE_20261030_025853\USB_VLK5JGVY_strategy2_preimage_20261030_231035_369')
CFGDIR = pathlib.Path(r'e:\RAID_Recovery_Backup\RAID_Recovery_Backup\DATABASE_20261030_025853\four_member_offline_comparison_20261030_183739')

tail = (PRE / 'VLK5JGVY_last_physical4KiB_ORIGINAL_PREIMAGE_ONLY.bin').read_bytes()
print('tail4k len', len(tail), 'sha256', hashlib.sha256(tail).hexdigest())

b = (CFGDIR / 'VLK5JGVY_IMSM_configuration.bin').read_bytes()
print('sector0 (=LBA n-3) :', tail[0:72].hex() == b[512:584].hex(), 'head72 matches cfg[512:584]')
print('sector1 (=LBA n-2) :', tail[512:1024] == b[0:512], 'matches cfg[0:512]')
print('sector2 (=LBA n-1) first 64:', tail[1024:1088].hex())
nonff = [i for i in range(1024, 2048) if tail[i] != 0xFF]
print('sector2 non-FF byte count', len(nonff), 'first offsets', nonff[:16])
print('sector2 uniq bytes', sorted(set(tail[1024:1536]))[:8])
print('sector3 (LBA n) all FF?', tail[1536:2048] == b'\xff' * 512)
for name, lo, hi in (('sec0', 0, 512), ('sec1', 512, 1024), ('sec2', 1024, 1536), ('sec3', 1536, 2048)):
    seg = tail[lo:hi]
    print('%s nonzero=%d first_nonzero=%s' % (name, sum(1 for x in seg if x), next((i for i, x in enumerate(seg) if x), None)))

# where does the 16MiB tail file place these?
big = (PRE / 'VLK5JGVY_range001_offset8001563156480_len65536.bin').read_bytes()
start = 8001563156480
off4k = 8001563217920 - start
print('offset of last4K inside 64K tail file:', off4k, 'match:', big[off4k:off4k + 4096] == tail)
print('bytes after last4K in 64K file:', 65536 - off4k - 4096)
