"""Read-only analysis: rebuild the IMSM MPB target for VLK5JGVY and verify against
the archived reference implementation (mdadm super-intel.c) rules.

No device handle is opened here. Inputs are the archived plain-file configurations.
"""
import hashlib, json, pathlib, struct

ROOT = pathlib.Path(r'e:\RAID_Recovery_Backup\RAID_Recovery_Backup\DATABASE_20261030_025853')
CMP = ROOT / 'four_member_offline_comparison_20261030_183739'
MODEL = ROOT / 'OFFLINE_METADATA_MODEL_20261030_203713'
OUT = pathlib.Path(r'e:\RAID_Recovery_Backup\VLK5JGVY_repair_20261031')

SER = {'C': 'VKH3B65X', 'A': 'VKJGM9XX', 'B': 'VLK5JGVY', 'D': 'VJGH3P3X'}
DISK0, DEV0 = 0xD8, 0xD8 + 4 * 48
VOL, MAP, ORD = DEV0 + 80, DEV0 + 80 + 32, DEV0 + 80 + 32 + 48
STATE = {0: 'normal', 1: 'uninitialized', 2: 'degraded', 3: 'failed'}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def checksum(cfg):
    n = u32(cfg, 0x24) // 4
    s = 0
    for i in range(n):
        s += u32(cfg, i * 4)
    return (s - u32(cfg, 0x20)) & 0xFFFFFFFF


cfgs = {k: (CMP / f'{v}_IMSM_configuration.bin').read_bytes() for k, v in SER.items()}
base, bcfg = cfgs['C'], cfgs['B']
res = {}

res['inputs'] = {k: {'serial': SER[k], 'len': len(v), 'sha256': sha(v),
                     'generation': u32(v, 0x2C),
                     'checksum_stored': '%08x' % u32(v, 0x20),
                     'checksum_computed': '%08x' % checksum(v),
                     'checksum_ok': u32(v, 0x20) == checksum(v)}
                 for k, v in cfgs.items()}


def rec(cfg, i):
    o = DISK0 + i * 48
    return {'idx': i, 'off': o, 'serial_raw_hex': cfg[o:o + 16].hex(),
            'serial_raw_repr': repr(cfg[o:o + 16]),
            'total_blocks_lo': u32(cfg, o + 16), 'scsi_id': '%08x' % u32(cfg, o + 20),
            'status': '%08x' % u32(cfg, o + 24), 'owner': u32(cfg, o + 28),
            'total_blocks_hi': u32(cfg, o + 32), 'filler_hex': cfg[o + 36:o + 48].hex()}


def summary(cfg, tag):
    return {'tag': tag, 'generation': u32(cfg, 0x2C), 'mpb_size': u32(cfg, 0x24),
            'family': '%08x' % u32(cfg, 0x28), 'attributes': '%08x' % u32(cfg, 0x34),
            'checksum_stored': '%08x' % u32(cfg, 0x20),
            'checksum_computed': '%08x' % checksum(cfg),
            'map_state': cfg[MAP + 14], 'map_state_name': STATE[cfg[MAP + 14]],
            'raid_level': cfg[MAP + 15], 'num_members': cfg[MAP + 16],
            'failed_disk_num': cfg[MAP + 18],
            'migr_state': cfg[VOL + 8], 'migr_type': cfg[VOL + 9], 'dirty': cfg[VOL + 10],
            'dev_status': '%08x' % u32(cfg, DEV0 + 20),
            'disks': [rec(cfg, i) for i in range(4)],
            'ordinals': ['%08x' % u32(cfg, ORD + 4 * i) for i in range(4)]}


res['baseline_763553'] = summary(base, 'A/C/D baseline gen 763553')
res['vlk5jgvy_own_763509'] = summary(bcfg, 'VLK5JGVY own gen 763509 (bad checksum)')

# ---------------------------------------------------------------- target build
tgt = bytearray(base)

# (1) B's slot-2 disk record: undo exactly the three "missing member" markers that the
#     reference implementation writes (serial+" :0", CONFIGURED|FAILED, scsi_id ~0).
#     Values come from this disk's own last self-record, never invented.
own = bcfg[DISK0 + 2 * 48:DISK0 + 3 * 48]
assert own[0:9] == b'VLK5JGVY\x00', repr(own[0:16])
own_status, own_scsi = struct.unpack_from('<I', own, 24)[0], struct.unpack_from('<I', own, 20)[0]
assert own_status == 0x53E, hex(own_status)          # healthy member flags + FAILED_DISK
assert own_scsi == 0, hex(own_scsi)                  # real locator last assigned to this disk
assert u32(base, DISK0 + 2 * 48 + 24) == 0x06        # baseline: CONFIGURED|FAILED placeholder
assert u32(base, DISK0 + 2 * 48 + 20) == 0xFFFFFFFF  # baseline: "locator unknown"
assert u32(base, DISK0 + 2 * 48 + 16) == u32(own, 16) and u32(base, DISK0 + 2 * 48 + 32) == u32(own, 32)
tgt[DISK0 + 2 * 48:DISK0 + 2 * 48 + 16] = own[0:16]                       # VLK5JGVY\0 + 00159
struct.pack_into('<I', tgt, DISK0 + 2 * 48 + 20, own_scsi)                # 0x00000000
struct.pack_into('<I', tgt, DISK0 + 2 * 48 + 24, own_status & ~0x04)      # 0x0000053a

# (2) B's map ordinal (slot 2): drop IMSM_ORD_REBUILD -> in sync
o2 = u32(base, ORD + 8)
assert o2 == 0x01000002, hex(o2)
struct.pack_into('<I', tgt, ORD + 8, o2 & ~(1 << 24))       # -> 0x00000002

# (3) map_state failed -> degraded; A (slot 1) keeps out-of-sync + failed_disk_num 1
assert tgt[MAP + 14] == 3 and tgt[MAP + 18] == 1
tgt[MAP + 14] = 2

# (4) generation bump for written members
struct.pack_into('<I', tgt, 0x2C, u32(base, 0x2C) + 1)

# (5) checksum last
struct.pack_into('<I', tgt, 0x20, 0)
struct.pack_into('<I', tgt, 0x20, checksum(bytes(tgt)))
tgt = bytes(tgt)
res['target'] = summary(tgt, 'TARGET candidate gen 763554')

diff = [i for i in range(584) if base[i] != tgt[i]]
runs = []
for i in diff:
    if runs and i == runs[-1][1] + 1:
        runs[-1][1] = i
    else:
        runs.append([i, i])
res['diff_vs_baseline'] = {'count': len(diff),
                           'runs': [{'start': a, 'end': b, 'len': b - a + 1,
                                     'before_hex': base[a:b + 1].hex(),
                                     'after_hex': tgt[a:b + 1].hex()} for a, b in runs]}


def replay(cfg):
    failed, slots = 0, []
    for slot in range(4):
        o = u32(cfg, ORD + 4 * slot)
        idx = o & 0xFFFFFF
        r = rec(cfg, idx)
        f, rb = bool(int(r['status'], 16) & 0x04), bool(o & (1 << 24))
        failed += 1 if (f or rb) else 0
        slots.append({'slot': slot, 'idx': idx, 'serial': r['serial_raw_repr'],
                      'failed_bit': f, 'out_of_sync': rb, 'counted_failed': f or rb})
    state = 3 if failed >= 2 else (2 if failed == 1 else 0)
    return {'failed_count': failed, 'computed_state': STATE[state], 'slots': slots}


res['rule_replay'] = {'baseline_with_A_B_problems': replay(base),
                      'target_with_B_C_D_attached': replay(tgt)}

s2 = (MODEL / 'S2_return_B_keep_A_out_of_sync_NOT_FOR_WRITEBACK.cfg.bin').read_bytes()
res['archived_S2'] = summary(s2, 'archived S2 model')
res['archived_S2_vs_target'] = [{'off': i, 's2': s2[i:i + 1].hex(), 'tgt': tgt[i:i + 1].hex()}
                                for i in range(584) if s2[i] != tgt[i]]

exc = (MODEL / 'S2_return_B_keep_A_out_of_sync_VLK5JGVY_LAST3SECTORS_EXCERPT_NOT_A_DISK.bin').read_bytes()
res['excerpt_layout_test'] = {
    'len': len(exc), 'sha256': sha(exc),
    'sector0_head72_eq_cfg512_584': exc[0:72] == s2[512:584],
    'sector0_eq_cfg512_584': exc[0:512] == s2[512:584],
    'sector1_eq_cfg0_512': exc[512:1024] == s2[0:512],
    'sector2_all_zero': exc[1024:1536] == bytes(512),
    'sector0_tail_hex': exc[72:96].hex(),
    'sector2_head64_hex': exc[1024:1088].hex()}

OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'target_VLK5JGVY_MPB_584.bin').write_bytes(tgt)
(OUT / 'analysis.json').write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding='utf-8')

print('=== inputs')
for k, v in res['inputs'].items():
    print(' ', k, v['serial'], 'gen', v['generation'], 'cksum', v['checksum_stored'], v['checksum_computed'], v['checksum_ok'])
print('=== diff vs baseline 763553:', res['diff_vs_baseline']['count'], 'bytes in', len(res['diff_vs_baseline']['runs']), 'runs')
for r in res['diff_vs_baseline']['runs']:
    print('   %3d..%3d  before=%s  after=%s' % (r['start'], r['end'], r['before_hex'], r['after_hex']))
print('=== target')
t = res['target']
print('  gen', t['generation'], 'cksum', t['checksum_stored'], 'computed', t['checksum_computed'],
      'map_state', t['map_state'], t['map_state_name'], 'failed_disk_num', t['failed_disk_num'])
print('  ordinals', t['ordinals'])
for d in t['disks']:
    print('   idx%d %-28r scsi_id=%s status=%s blocks=%d/%d' % (d['idx'], d['serial_raw_repr'], d['scsi_id'], d['status'], d['total_blocks_hi'], d['total_blocks_lo']))
print('=== replay')
for k, v in res['rule_replay'].items():
    print(' ', k, 'failed=%d state=%s' % (v['failed_count'], v['computed_state']))
    for s in v['slots']:
        print('     slot%d idx%d %-28r failed=%s oos=%s' % (s['slot'], s['idx'], s['serial'], s['failed_bit'], s['out_of_sync']))
print('=== S2 vs target differing bytes:', len(res['archived_S2_vs_target']))
for d in res['archived_S2_vs_target']:
    print('   off %3d s2=%s target=%s' % (d['off'], d['s2'], d['tgt']))
print('=== excerpt layout')
print(json.dumps(res['excerpt_layout_test'], indent=2))
print('TARGET sha256', sha(tgt))
