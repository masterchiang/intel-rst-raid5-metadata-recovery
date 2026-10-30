# Evidence

Everything below is a hash or a measurement taken from the real case, kept so that someone can check
our reasoning instead of trusting it.

## 1. The four copies before the repair

| Member | `generation` | checksum valid | volume state it records | SHA-256 of the 584-byte configuration |
|---|---:|---|---|---|
| `VKH3B65X` (C, slot 0) | 763553 | yes | failed | `b3c6013dee1ace62fb7a4b06ad2dbe6eb7e944d1f7e0b73e8ab1924302412f47` |
| `VJGH3P3X` (D, slot 3) | 763553 | yes | failed | `b3c6013dee1ace62fb7a4b06ad2dbe6eb7e944d1f7e0b73e8ab1924302412f47` |
| `VKJGM9XX` (A, slot 1) | 763553 | yes | failed | `b3c6013dee1ace62fb7a4b06ad2dbe6eb7e944d1f7e0b73e8ab1924302412f47` |
| `VLK5JGVY` (B, slot 2) | 763509 | **no** (`11d13318` stored vs `10d03318` computed) | degraded | `43c02ffb75553d39eac93234179b0152e350a024940adf81fb20d34951be6425` |

Three identical copies with a valid checksum, one stale copy with a broken checksum. The stale copy is
the disk that had been out of the array longest — consistent with the physical story.

### Disk records in the baseline (generation 763553)

| Slot | serial field (16 bytes) | `status` | `scsi_id` | ordinal |
|---:|---|---|---|---|
| 0 | `"VKH3B65X" NUL "5FFA181"` | `0x0000053A` | `0x00000003` | `0x00000000` |
| 1 | `"VKJGM9XX" NUL "00505"` | `0x0000053A` | `0x00000000` | `0x01000001` ← out of sync |
| 2 | `"VLK5JGVY:0" NUL "159"` | `0x00000006` | `0xFFFFFFFF` | `0x01000002` ← out of sync |
| 3 | `"VJGH3P3X" NUL "00475"` | `0x0000053A` | `0x00000001` | `0x00000003` |

Slot 2 is the textbook "missing member" record: `CONFIGURED|FAILED`, null locator, serial suffixed
with `:0`. `map_state = 3`, `failed_disk_num = 1`, `migration_state = 0`, `migr_type = 1` (residue).

## 2. The repaired configuration

SHA-256 `a773a7513c17ba35d5a1b58d6e9f06fe93094e0e6b1e628362bd3f9d92dcb36b`,
checksum `0xb4816209` (matches computation), `generation = 763554`, `map_state = 2`,
`failed_disk_num = 1`.

| Slot | serial field | `status` | `scsi_id` | ordinal |
|---:|---|---|---|---|
| 0 | `"VKH3B65X" NUL "5FFA181"` | `0x0000053A` | `0x00000003` | `0x00000000` |
| 1 | `"VKJGM9XX" NUL "00505"` | `0x0000053A` | `0x00000000` | `0x01000001` ← still out of sync, intentionally |
| 2 | `"VLK5JGVY" NUL "00159"` | `0x0000053A` | `0x00000000` | `0x00000002` |
| 3 | `"VJGH3P3X" NUL "00475"` | `0x0000053A` | `0x00000001` | `0x00000003` |

State replay with this configuration and three members attached:

```
failed = 1  (slot 1, IMSM_ORD_REBUILD)
state  = Degraded
```

which is what the OROM then displayed.

## 3. Exactly what changed, per disk

### `VLK5JGVY` (the disk that was `Non-RAID`) — 22 bytes

Against the configuration that was already on that disk (generation 763509):

| Offset | Field | Before | After |
|---:|---|---|---|
| 32–35 | `check_sum` | `1833d111` | `096281b4` |
| 44 | `generation_num` (low byte) | `75` | `a2` |
| 68 | `pwr_cycle_count` (low byte) | `1b` | `30` |
| 236 | `disk[0].scsi_id` (low byte) | `02` | `03` |
| 272,273,274 | `disk[1].serial` | `3a 31 00` (`":1" NUL`) | `00 30 30` |
| 280–283 | `disk[1].total_blocks_lo` | `00000000` | `b02a81a3` |
| 284–287 | `disk[1].scsi_id` | `ffffffff` | `00000000` |
| 288–289 | `disk[1].status` | `02 00` | `3a 05` |
| 296 | `disk[1].total_blocks_hi` | `00` | `03` |
| 332 | `disk[2].scsi_id` (low byte) | `00` | — unchanged in the final version |
| 336 | `disk[2].status` | `3e` | `3a` |

Note how small the change to *its own* record was: this disk already carried a usable self
description (`"VLK5JGVY"`, real block count, `scsi_id 0`, status `0x053E`). It only needed the
`FAILED` bit cleared. Most of the byte changes are the stale *other* member's record being brought up
to the same state as the rest of the array.

### `VKH3B65X` and `VJGH3P3X` — 15 bytes each

| Offset | Field | Before | After |
|---:|---|---|---|
| 32–35 | `check_sum` | `0d5d52b5` | `096281b4` |
| 44 | `generation_num` (low byte) | `a1` | `a2` |
| 320 | `disk[2].serial[8]` | `3a` (`':'`) | `00` |
| 322 | `disk[2].serial[10]` | `00` | `30` (`'0'`) |
| 332–335 | `disk[2].scsi_id` | `ffffffff` | `00000000` |
| 336–337 | `disk[2].status` | `06 00` | `3a 05` |
| 534 | `map.map_state` | `03` | `02` |
| 579 | `disk_ord_tbl[2]` high byte | `01` | `00` |

## 4. Physical write proof

Both the target disk and the two other members ended up with the **identical physical sector**:

| | before | after |
|---|---|---|
| 4 KiB sector (offset `8001563217920`) | `VLK5JGVY`: `35ac0f1e4e1ff396db4a5643330948ab9a4e4d821f538af2a33da2b6549f0218`<br>`VKH3B65X` / `VJGH3P3X`: `c2210c381c7eb101c6022927887e8dbf74a8b3ee41aaa8322b9466c0ba3960e4` | all three: `04553866e753bfef715a82eb042fa5ca969f90df6f242ae460540226681c7e48` |

Independent re-read after the write, comparing the whole last 64 KiB against the pre-write backup:

```
VLK5JGVY : 22 changed bytes, all inside the MPB sector
VKH3B65X : 15 changed bytes, all inside the MPB sector
VJGH3P3X : 15 changed bytes, all inside the MPB sector
```

First 64 KiB of every disk verified byte-identical to its pre-write backup (i.e. nothing outside the
metadata area moved, including the GPT that Windows had briefly "recognised" on two of them).

## 5. Data-area integrity at the time of the repair

Two 128 KiB sample stripes did not XOR to zero across the four members:

| Physical offset | Sample length | Non-zero XOR bytes |
|---:|---:|---:|
| 1 074 397 184 | 131 072 | 98 |
| 4 000 779 468 800 | 131 072 | 2 089 |

XOR alone cannot tell you **which** disk is wrong — excluding any one member and recomputing it from
the other three yields the same syndrome. Both versions passed structural NTFS checks, so neither could
be declared correct from structure alone.

We therefore did not use these samples to decide anything, and we did not "fix" them. The rebuild of
the out-of-sync member resolved them by construction, because the other three members are the source.

## 6. Timeline of the metadata

```
763509  last write seen by VLK5JGVY (before it left the array; checksum already broken)
763553  written by the controller after VLK5JGVY was gone: three copies, byte identical
        -> volume Failed, VLK5JGVY recorded as missing ("VLK5JGVY:0")
763554  written by us to all three surviving members: VLK5JGVY restored as an in-sync member
        -> volume Degraded
after   the firmware took over and rewrote everything (rebuild flags, scsi_id, new generations)
```

The last line is the reason the hashes in this document are historical: after the first controller
contact, the on-disk metadata is no longer the one we wrote.
