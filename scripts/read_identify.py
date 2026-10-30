import pathlib

def ata_text(data, start, end):
    raw = data[start:end]
    return bytes(v for i in range(0, len(raw), 2) for v in (raw[i + 1], raw[i])).decode('ascii', 'replace').strip(' \0')

for p in sorted(pathlib.Path(r'e:\RAID_Recovery_Backup\RAID_Recovery_Backup').rglob('*_ATA_IDENTIFY.bin')):
    d = p.read_bytes()
    print(p)
    print('  serial field(%d): %r' % (len(ata_text(d, 20, 40)), ata_text(d, 20, 40)))
    print('  model : %r' % ata_text(d, 54, 94))
    print('  fw    : %r' % ata_text(d, 46, 54))
    print('  raw20..40:', d[20:40].hex())
    print()
