# The Intel IMSM MPB on disk — field by field

Everything here was verified against four real disks *and* cross-checked against the public
`mdadm` IMSM implementation (`super-intel.c`). The `mdadm` struct definitions
(`struct imsm_super`, `imsm_disk`, `imsm_dev`, `imsm_vol`, `imsm_map`) map onto the 584-byte
configuration byte for byte, which is why the offsets below can be trusted.

> This is a compatibility format description, not Intel's private specification.
> Intel's actual driver and OROM are closed source; behaviour is inferred, not guaranteed.

## 1. Where it lives on the disk

For a member with `size` bytes and 512-byte logical sectors:

```
n            = size / 512                (last LBA is n-1)
anchor       = (n - 2) * 512             configuration bytes  [0 .. 511]
extended     = (n - 3) * 512             configuration bytes [512 .. 583]  in the FIRST 72 bytes
unused       = (n - 1) * 512             not part of this MPB — preserve it
```

In the case documented here:

```
size              = 8 001 563 222 016
n                 = 15 628 053 168
anchor offset     = 8 001 563 220 992   (LBA 15 628 053 166)
extended offset   = 8 001 563 220 480   (LBA 15 628 053 165)
unused            = 8 001 563 221 504   (LBA 15 628 053 167)
```

### Why this matters more than anything else

These drives report **512-byte logical / 4096-byte physical** sectors. All three regions above
(`n-4 … n-1`) sit inside **one single 4 KiB physical sector**, at byte offset `8 001 563 217 920`.

So the safe write is:

```
read  4096 bytes at 8 001 563 217 920
patch bytes [2560 .. 2631]  <- configuration [512 .. 583]
patch bytes [3072 .. 3583]  <- configuration [  0 .. 511]
leave bytes [0 .. 2559], [2632 .. 3071], [3584 .. 4095] exactly as read
write 4096 bytes back to 8 001 563 217 920
```

Never write a bare 584-byte buffer. Never write only one of the two sectors — the drive would have to
do two separate read-modify-writes on the same physical sector instead of one clean 4 KiB update.

## 2. The 584-byte configuration

Layout for **4 members / 1 volume**, which is what produces `mpb_size = 584`:

```
0x000  32  signature           "Intel Raid ISM Cfg Sig. 1.3.00" + NUL padding
0x020   4  check_sum           u32 LE
0x024   4  mpb_size            u32 LE = 584
0x028   4  family_num          u32 LE  array identity, e.g. 0x0345F4B5
0x02C   4  generation_num      u32 LE  bumped on every configuration write
0x030   4  error_log_size      u32 LE
0x034   4  attributes          u32 LE  capability flags, e.g. 0xA4000010
0x038   1  num_disks           4
0x039   1  num_raid_devs       1
0x03A   1  error_log_pos
0x03B   1  fill
0x03C   4  cache_size
0x040   4  orig_family_num
0x044   4  pwr_cycle_count
0x048   4  bbm_log_size        bad-block-management log size, 0 here
0x04C   2  num_raid_devs_created
0x04E   2  filler
0x050   8  creation_time       u64 LE
0x058 128  filler[32]
0x0D8  48  disk[0]             first member record
0x108  48  disk[1]
0x138  48  disk[2]
0x168  48  disk[3]
0x198  80  dev                 volume / device record header
0x1E8  32  vol                 migration & dirty state
0x208  48  map                 geometry + member order
0x238  16  disk_ord_tbl[4]     one u32 per slot
0x248 = 584
```

### `disk[]` record — 48 bytes

```
+0   16  serial[16]            ASCII, NUL padded  (see the warning below)
+16   4  total_blocks_lo       u32 LE
+20   4  scsi_id               u32 LE, 0xFFFFFFFF = "location unknown"
+24   4  status                u32 LE, see bit table
+28   4  owner_cfg_num
+32   4  total_blocks_hi
+36  12  filler[3]
```

> **The 16-byte serial field is not a simple string.** On real Intel-written metadata it looks like:
>
> ```
> 56 4b 48 33 42 36 35 58 00 35 46 46 41 31 38 31   "VKH3B65X\0" + "5FFA181"
> ```
>
> i.e. the 8-character ATA serial, a NUL, then up to 7 more characters that Intel stores after it.
> Member matching compares **all 16 bytes** (`strncmp(..., 16)`), so both halves matter.
> When you restore a member, **copy its own 16-byte field verbatim from its own last good record** —
> do not rebuild the string by hand.

### `status` bits

```
0x00000001  SPARE         disk is an unused spare
0x00000002  CONFIGURED    disk belongs to a volume
0x00000004  FAILED        permanent failure / missing
0x02000000  JOURNAL       device used as a journaling drive
```

Real healthy members in this case carried `0x0000053A`. Intel sets additional private bits
(`0x0530`) that `mdadm` does not define; **preserve them**. Do not "clean" a status field down to
`0x00000002` — that produces a record that looks nothing like the other healthy members.

A disk that the firmware has given up on carries `0x00000006` = `CONFIGURED | FAILED`.

### `dev` record header — 80 bytes at 0x198

```
+0   16  volume[16]            "DATABASE"
+16   4  size_low              u32 LE, volume size in 512-byte sectors (low)
+20   4  size_high
+24   4  status                u32 LE, DEV_* flags (bootable, dirty, hidden, CnG, ...)
+28   4  reserved_blocks
+32   1  migr_priority
+33   1  num_sub_vols
+34   1  tid
+35   1  cng_master_disk
+36   2  cache_policy
+38   1  cng_state
+39   1  cng_sub_state
+40  40  filler
```

### `vol` — 32 bytes at 0x1E8 (before the map)

```
+0    4  curr_migr_unit_lo
+4    4  checkpoint_id
+8    1  migr_state          0 = normal, 1 = migrating
+9    1  migr_type           0 init, 1 rebuild, 2 verify, 3 gen-migr, 4 state-change, 5 repair
+10   1  dirty               0 clean, 1 dirty, 2 dsrecord valid
+11   1  fs_state            fast-sync state, 0xFF = disabled
+12   2  verify_errors
+14   2  bad_blocks
+16   4  curr_migr_unit_hi
+20  12  filler[3]
+32   →  map follows
```

A non-zero `migr_type` with `migr_state = 0` is **leftover residue**, not evidence that a rebuild
is happening or ever happened. Do not "clean" it either.

### `map` — 48 bytes + 4 bytes per member, at 0x208

```
+0    4  pba_of_lba0_lo          start LBA of the volume on the members (0 here)
+4    4  blocks_per_member_lo
+8    4  num_data_stripes_lo
+12   2  blocks_per_strip        strip size in 512-byte blocks: 256 => 128 KiB
+14   1  map_state               0 normal, 1 uninitialized, 2 degraded, 3 failed
+15   1  raid_level              5
+16   1  num_members             4
+17   1  num_domains
+18   1  failed_disk_num         valid only when map_state == degraded
+19   1  ddf
+20   4  pba_of_lba0_hi
+24   4  blocks_per_member_hi
+28   4  num_data_stripes_hi
+32  16  filler[4]
+48  4*n disk_ord_tbl[n]
```

`disk_ord_tbl[slot]` is a u32:

```
low 24 bits : index into disk[]  (which physical member occupies this slot)
bit 24      : IMSM_ORD_REBUILD   -> this member is out of sync / being rebuilt
```

So `0x01000002` = "disk[2], out of sync" and `0x00000002` = "disk[2], in sync".

## 3. Checksum

```
sum = 0
for each u32 LE word in configuration[0 .. mpb_size)
    sum += word
checksum = (sum - stored_checksum_field) mod 2^32
```

The stored value must equal that. Setting the checksum field to 0 before summing and writing the
result afterwards gives the same answer, because the field itself is subtracted.

An invalid checksum means the firmware may ignore the whole copy. One of our four disks had a
**stale copy with a bad checksum** — a very useful signal that it had not been updated for a long time.

## 4. How the volume state is derived

Reproducing `imsm_count_failed()` / `imsm_check_degraded()` from the reference implementation:

```
failed = 0
for slot in 0..num_members-1:
    idx  = disk_ord_tbl[slot] & 0xFFFFFF
    rec  = disk[idx]
    if rec is absent
       or (rec.status & 0x04)          # FAILED
       or (disk_ord_tbl[slot] & (1<<24)):   # out of sync
        failed += 1

RAID 5:  failed == 0 -> Normal,  failed == 1 -> Degraded,  failed >= 2 -> Failed
```

This rule reproduced the firmware's observed behaviour exactly:

| Configuration | counted failures | computed | what the firmware displayed |
|---|---|---|---|
| original (2 problem slots) | 2 | Failed | **Failed** |
| repaired (1 problem slot) | 1 | Degraded | **Degraded** |

That agreement is the main reason we trusted the byte-level model enough to write.

## 5. Choosing the generation number

`generation_num` is the tie-breaker when several members carry different copies. The reference
implementation keeps the copy with the highest generation (with extra rules around disk status).

If you repair only one member and leave the others older, you are betting that the firmware resolves
the conflict the same way. We removed the bet: **all surviving members received the identical
configuration with `generation = previous + 1`**, so there is nothing left to resolve.

## 6. What `map_state` must be, and what it must not be

`map_state = 0` (Normal) is a *claim* that every member is synchronised. If a member is actually
stale, that claim is false and it is dangerous: reads served from the stale disk return old data while
every structural check still passes.

Worse, the firmware recomputes the state from the members anyway. Storing `Normal` while one member is
out of sync produces "stored state ≠ computed state", which is exactly the kind of inconsistency that
makes a controller rewrite your metadata behind your back.

Until a real rebuild has completed, **`Degraded` (2) is the only honest value.**
