import pathlib, struct, sys

ROOT = pathlib.Path(r'e:\RAID_Recovery_Backup\RAID_Recovery_Backup\DATABASE_20261030_025853\four_member_offline_comparison_20261030_183739')
name = sys.argv[1] if len(sys.argv) > 1 else 'VLK5JGVY'
b = (ROOT / f'{name}_IMSM_configuration.bin').read_bytes()
for off in range(0, len(b), 16):
    row = b[off:off + 16]
    print('%04x  %-48s |%s|' % (off, ' '.join('%02x' % x for x in row),
                                ''.join(chr(x) if 32 <= x < 127 else '.' for x in row)))
print()
print('disk table raw:')
for i in range(4):
    o = 0xD8 + i * 48
    r = b[o:o + 48]
    print(' idx%d off=%d serial=%r blocks_lo=%d scsi_id=%08x status=%08x owner=%d bhi=%d filler=%s' % (
        i, o, r[0:16], struct.unpack_from('<I', r, 16)[0], struct.unpack_from('<I', r, 20)[0],
        struct.unpack_from('<I', r, 24)[0], struct.unpack_from('<I', r, 28)[0],
        struct.unpack_from('<I', r, 32)[0], r[36:48].hex()))
