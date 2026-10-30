import hashlib, json, pathlib, struct

OUT = pathlib.Path(r'e:\RAID_Recovery_Backup\VLK5JGVY_repair_20261031')
CMP = pathlib.Path(r'e:\RAID_Recovery_Backup\RAID_Recovery_Backup\DATABASE_20261030_025853\four_member_offline_comparison_20261030_183739')

tgt = (OUT / 'target_VLK5JGVY_MPB_584.bin').read_bytes()
cur = {'B': (CMP / 'VLK5JGVY_IMSM_configuration.bin').read_bytes(),
       'C': (CMP / 'VKH3B65X_IMSM_configuration.bin').read_bytes(),
       'D': (CMP / 'VJGH3P3X_IMSM_configuration.bin').read_bytes()}

NAMES = [(0x20, 4, 'check_sum'), (0x24, 4, 'mpb_size'), (0x28, 4, 'family_num'), (0x2C, 4, 'generation_num'),
         (0x30, 4, 'error_log_size'), (0x34, 4, 'attributes'), (0x38, 1, 'num_disks'), (0x39, 1, 'num_raid_devs'),
         (0x44, 4, 'pwr_cycle_count'), (0x48, 4, 'bbm_log_size')]
for i in range(4):
    o = 0xD8 + i * 48
    NAMES += [(o, 16, 'disk%d.serial' % i), (o + 16, 4, 'disk%d.total_blocks_lo' % i), (o + 20, 4, 'disk%d.scsi_id' % i),
              (o + 24, 4, 'disk%d.status' % i), (o + 28, 4, 'disk%d.owner_cfg_num' % i), (o + 32, 4, 'disk%d.total_blocks_hi' % i)]
DEV = 0xD8 + 4 * 48
NAMES += [(DEV + 8, 4, 'dev.size_low'), (DEV + 12, 4, 'dev.size_high'), (DEV + 20, 4, 'dev.status'),
          (DEV + 24, 4, 'dev.reserved_blocks')]
VOL, MAP, ORD = DEV + 80, DEV + 112, DEV + 160
NAMES += [(VOL + 8, 1, 'vol.migr_state'), (VOL + 9, 1, 'vol.migr_type'), (VOL + 10, 1, 'vol.dirty'),
          (MAP + 4, 4, 'map.blocks_per_member_lo'), (MAP + 8, 4, 'map.num_data_stripes_lo'),
          (MAP + 12, 2, 'map.blocks_per_strip'), (MAP + 14, 1, 'map.map_state'), (MAP + 15, 1, 'map.raid_level'),
          (MAP + 16, 1, 'map.num_members'), (MAP + 18, 1, 'map.failed_disk_num'), (MAP + 19, 1, 'map.ddf')]
for i in range(4):
    NAMES += [(ORD + 4 * i, 4, 'map.ordinal[slot%d]' % i)]


def val(b, o, n):
    return b[o:o + n]


rows = {}
for k, c in cur.items():
    d = [{'field': nm, 'off': o, 'before': val(c, o, n).hex(), 'after': val(tgt, o, n).hex()}
         for o, n, nm in NAMES if c[o:o + n] != tgt[o:o + n]]
    rows[k] = d
    print('=== %s : %d field(s) change' % (k, len(d)))
    for r in d:
        print('   %-24s @%3d  %s -> %s' % (r['field'], r['off'], r['before'], r['after']))
    allb = [i for i in range(584) if c[i] != tgt[i]]
    print('   raw byte count %d, offsets %s' % (len(allb), allb))

print()
print('target sha256', hashlib.sha256(tgt).hexdigest())
(OUT / 'field_diff.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
