# Report: recovering an Intel RST RAID5 array from `Failed` to accessible

[简体中文](README.md) | **English** | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Español](README.es.md) | [Русский](README.ru.md)

Period: 2026-10-30 to 2026-10-31
Subject: Intel RST RAID5 made of four 8 TB HGST disks, volume name `DATABASE`, volume size 24 004 676 026 368 bytes
Outcome: member `VLK5JGVY` rejoined the array, the volume went from `Failed` to `Degraded`, the rebuild completed, and the volume mounted normally in Windows
Data handling: no format, no volume deletion, no initialisation; 0 bytes written in the data area

This document records the investigation, the conclusions and their basis, the operations performed, and the results.

---

## Contents

- [0. Summary](#0-summary)
- [1. Environment](#1-environment)
- [2. Incident](#2-incident)
- [3. Symptoms](#3-symptoms)
- [4. Investigation](#4-investigation)
- [5. Metadata format](#5-metadata-format)
- [6. Repair design](#6-repair-design)
- [7. Execution record](#7-execution-record)
- [8. Result](#8-result)
- [9. Open items and limitations](#9-open-items-and-limitations)
- [10. Reproducing the procedure](#10-reproducing-the-procedure)
- [11. References](#11-references)

---

## 0. Summary

| Item | Detail |
|---|---|
| Symptom | Volume state `Failed`; member `VLK5JGVY` shown as `Non-RAID`; a 0-byte disk record in state "Lost" in the RST application |
| Immediate cause | Moving the case loosened member `VKJGM9XX`; the array ran degraded for several hours; member `VLK5JGVY` was accidentally unplugged at shutdown, leaving two members in a bad state |
| Root cause | The serial field of that member's record had `:0` appended, and member matching uses an exact 16-byte comparison, so the disk could no longer be associated with its record |
| Method | Start from the newest valid configuration copy, change 5 fields, recompute the checksum, write the same configuration to all 3 surviving members |
| Data area modified | 0 bytes |
| Metadata modified | 22 bytes on `VLK5JGVY`, 15 bytes on `VKH3B65X`, 15 bytes on `VJGH3P3X` |
| Result | `Failed` → `Degraded` → rebuild → volume mounted, files readable |
| Not verified | The model derives from the public mdadm implementation and was not tested against other firmware versions |

---

## 1. Environment

### 1.1 Platform

| Item | Value |
|---|---|
| CPU | Intel Core i5-13600KF |
| Motherboard | Colorful CVN Z790D5 GAMING FROZEN V20 |
| BIOS | 1009 (2023-08-23), not flashed during this work |
| Storage mode | VMD enabled, hardware IDs `A77F` / `09AB` |
| OROM version in BIOS | 19.5 |
| Windows driver | 19.5.2.1049 at the time of failure, later 20.2.1.1016 |
| RST application | 20.0.1024.0 |
| OS | Windows 10 Pro 22H2, build 19045 |

### 1.2 Volumes

| Volume | Composition | Purpose |
|---|---|---|
| `SYSTEM` | 2 × SSD RAID1 | OS, contains `C:` and `D:` |
| `MAIN` | 4 × NVMe RAID5 | 2.86 TB working set |
| `DATABASE` | 4 × 8 TB HDD RAID5 | 24 TB archive; subject of this report |

`DATABASE` was the only copy. There was no off-site backup and no local space for a 24 TB image.

### 1.3 Array parameters

| Item | Value |
|---|---|
| RAID level / members | 5 / 4 |
| Strip size | 256 × 512 B = 128 KiB |
| Parity position | parity member of stripe s is `3 - (s % 4)`, left-asymmetric |
| Volume size | 46 884 132 864 sectors = 24 004 676 026 368 bytes |
| Configuration signature | `Intel Raid ISM Cfg Sig. 1.3.00` |
| Configuration size | 584 bytes |
| `family_num` | `0x0345F4B5` |
| Per-disk capacity | 8 001 563 222 016 bytes, 15 628 053 168 sectors, 512 B logical / 4096 B physical |

### 1.4 Members

| Label | Serial | Logical slot | Model | Firmware | SATA port after the incident |
|---|---|---:|---|---|---:|
| A | `VKJGM9XX` | 1 | HGST HUH728080ALE600 | A4GNT7JD | 2 |
| B | `VLK5JGVY` | 2 | HGST HUH728080ALE601 | A4GL0003 | 4 |
| C | `VKH3B65X` | 0 | HGST HUH728080ALE600 | A4GNT7JD | 5 |
| D | `VJGH3P3X` | 3 | HGST HUH728080ALE601 | A4GL0003 | 3 |

SATA port numbers do not correspond to RAID logical slots and cannot be used to infer one from the other.

---

## 2. Incident

```
Step 1  The case was moved; the SATA connector of member A (VKJGM9XX) came loose
        The array entered Degraded and continued serving from 3 members

Step 2  The system ran for several hours
        During this period the array kept writing to C, B and D, including NTFS
        journal, timestamps and other metadata
        Member A took no part in these writes

Step 3  At shutdown A was re-seated, and at the same moment member B (VLK5JGVY)
        was unplugged by mistake

Step 4  Power on
        A out of sync and B missing; two members bad at once
        The firmware set the volume state to Failed

Step 5  B was plugged back in
        BIOS showed Non-RAID; it did not rejoin
        The RST application gained a 0-byte disk record in state "Lost"
```

A clarification on Step 2: the owner believed that "nothing was written to the array after A dropped out", and
therefore that A still held valid data. In a degraded array, however, read and write service continues normally,
and filesystem metadata writes occur whenever the OS is running. A therefore holds old data, and C, B and D hold
the current data. This determination fixed the direction of the later rebuild (see 6.4).

---

## 3. Symptoms

### 3.1 BIOS / UEFI RST screen

The volume exists with the correct name, level and capacity. State is `Failed`. One member is missing.
The re-attached `VLK5JGVY` is shown as `Non-RAID`.

### 3.2 Intel RST application in Windows

An anomalous disk record is present:

- Controller, port, port location: unknown
- State: Lost
- Size: 0 Bytes
- Serial: `VLK5JGVY:0`
- Model, firmware: empty

The UI suggests a failed or empty disk, which contradicts the hardware.

### 3.3 The disk itself

Read through a USB-SATA bridge:

- ATA `IDENTIFY` is clean: serial, model, firmware and LBA48 capacity all correct
- SMART is clean: 0 reallocated, 0 pending, 0 offline uncorrectable
- Capacity 8 001 563 222 016 bytes, 15 628 053 168 sectors
- 512-byte logical, 4096-byte physical sectors

The three views contradict each other, which places the fault outside the hardware.

<table>
<tr>
<td width="50%"><img src="docs/images/usb-member-diskgenius.png" alt="Member disk geometry"><br>Sector geometry of a member disk behind the USB bridge</td>
<td width="50%"><img src="docs/images/usb-member-ata-identify.png" alt="ATA IDENTIFY over USB"><br>Full ATA identity remains readable through the bridge</td>
</tr>
<tr>
<td colspan="2"><img src="docs/images/usb-member-smart.png" alt="SMART of the member disk"><br>SMART of the same disk, with no defect counters</td>
</tr>
</table>

---

## 4. Investigation

The entire investigation was read-only. No data was written to any disk during this phase.

### 4.1 Disk hardware

Method: remove the disks and read ATA `IDENTIFY` and SMART through a USB-SATA bridge.

Result: serial, capacity and SMART all normal.

Conclusion: no hardware fault.

### 4.2 Whether a rebuild had already run

If the array had used member A as a rebuild target during the degraded period, A's data would have been
overwritten with recomputed values.

Method: read the metadata at the end of all four disks and check `migration_state` and `migration_type`.

Result: `migration_state = 0`, with a residual `migration_type = 1`.

Conclusion: no rebuild had occurred. `migration_state = 0` means no migration or rebuild is in progress; the
non-zero `migration_type` is historical residue and must not be read as evidence that a rebuild happened.

### 4.3 Filesystem integrity

Method: using ordinary file copies of the four disks, reassemble the volume in memory according to the RAID5
stripe rules and validate each layer.

| Check | Result |
|---|---|
| Primary GPT header CRC32 | passed (`deaf682b`) |
| Backup GPT header CRC32 | passed (`418d6e5e`) |
| Partition array CRC32, primary vs backup | passed (`34df0453`), byte-identical |
| NTFS boot sector, primary vs backup | identical |
| First 128 records of the primary MFT, structure and runlists | passed; first 8 records byte-identical to the mirror |
| Root directory, 6 INDX blocks, 94 name entries | passed; 19 entries cross-checked against the MFT |

Conclusion: the data and the filesystem structures are intact. The problem is not in the data.

### 4.4 Metadata comparison

Method: read the configuration block at the end of each disk, parse it field by field using the public mdadm
IMSM structure definitions, and compare the four.

Result:

| Disk | Generation | Checksum | Recorded volume state |
|---|---:|---|---|
| `VKH3B65X` | 763553 | valid | failed |
| `VJGH3P3X` | 763553 | valid | failed |
| `VKJGM9XX` | 763553 | valid | failed |
| `VLK5JGVY` | 763509 | invalid (stored `11d13318`, computed `10d03318`) | degraded |

The C, D and A copies are byte-identical, so they were written at the same moment. `VLK5JGVY`'s copy is an older
generation with an invalid checksum, so it had not been updated for a long time.

In the three newer copies, the record for `VLK5JGVY` reads:

```
serial   "VLK5JGVY:0"     the serial field with ":0" appended
status   0x00000006       CONFIGURED | FAILED
scsi_id  0xFFFFFFFF       no location information
ordinal  0x01000002       out-of-sync / rebuild bit set
```

These values match what `mark_failure()` and `mark_missing()` in mdadm write when marking a member as missing.

Conclusion: the fault is in the metadata. The disk contents are intact.

### 4.5 Member matching

Member matching compares the 16-byte serial field for exact equality (`strncmp(..., 16)`).

The configuration records `VLK5JGVY:0`; the disk reports `VLK5JGVY`. The two are not equal, so no match is possible.

This explains the following observations:

- replacing the cable, the port or the machine has no effect
- updating BIOS or drivers has no effect
- the UI reports a capacity of 0 because the disk is not associated with any member record

Because the string is stored on the disk, the member cannot rejoin without modifying the metadata.

### 4.6 XOR sampling and its limits

To determine which member's data was not trustworthy, 28 stripes (128 KiB each) from the middle of the array were
sampled and XOR-checked.

| Physical offset | Length | Non-zero bytes |
|---:|---:|---:|
| 1 074 397 184 | 131 072 | 98 |
| 4 000 779 468 800 | 131 072 | 2 089 |

The other 26 samples XOR to zero.

The two non-zero samples cannot identify the faulty member: excluding any one of A/B/C/D and recomputing it from
the other three produces an identical difference pattern, the same four-disk syndrome. Without a trusted reference,
XOR shows only that a stripe is inconsistent, not which member is wrong.

Both candidate versions also pass the NTFS structural checks (the differences are concentrated in the LSN fields of
MFT records 32–39 and in `$LogFile` pages), so structural validity cannot decide it either.

The question is therefore not solvable offline. The conclusion in section 2 was used instead: A was absent during
the degraded period and its content is behind. That is an engineering judgement, not a proven result.

---

## 5. Metadata format

Full field tables in [docs/02-imsm-metadata-format.md](docs/02-imsm-metadata-format.md). Only the parts relevant to
this fault are repeated here.

### 5.1 Position on disk

Intel writes a configuration block describing the whole array at the end of every member. For a 4-member
single-volume array it is 584 bytes, spread over the last few sectors:

```
third-from-last 512 B sector, first 72 bytes = configuration bytes [512..583]
second-from-last 512 B sector (all 512 B)    = configuration bytes [  0..511]
last 512 B sector                            = not part of this block, must be left untouched
```

These three sectors lie inside one 4 KiB physical sector. Writing therefore has to be a read-modify-write of the
whole 4 KiB sector; the 584 bytes must not be written as a contiguous block.

Offsets for this case:

| Item | Value |
|---|---|
| Configuration start | 8 001 563 220 992 (second-from-last sector) |
| Extended part | 8 001 563 220 480 (third-from-last sector) |
| Physical sector start | 8 001 563 217 920 (4 KiB aligned) |

### 5.2 Disk record fields

Each disk record is 48 bytes:

| Offset | Length | Field | Value in this case (failed disk) |
|---:|---:|---|---|
| +0 | 16 | serial | `"VLK5JGVY"` + NUL + `"00159"` |
| +16 | 4 | total_blocks_lo | 2 743 151 280 |
| +20 | 4 | scsi_id | `0x00000000` (normal); `0xFFFFFFFF` (missing) |
| +24 | 4 | status | `0x0000053A` (normal); `0x00000006` (missing) |
| +28 | 4 | owner_cfg_num | 0 |
| +32 | 4 | total_blocks_hi | 3 |
| +36 | 12 | filler | 0 |

The serial field is not plain text: the trailing part (such as `00159`) is also part of the identifier. Repairing it
requires copying the 16 bytes from that disk's own record; the string must not be reassembled by hand.

Published bits of `status`: `0x01` SPARE, `0x02` CONFIGURED, `0x04` FAILED, `0x02000000` JOURNAL. A healthy member
in this array carried `0x0000053A`, where `0x0530` are undocumented bits that must be preserved.

`ordinal` (`disk_ord_tbl`) is 32 bits: the low 24 bits are the disk record index, and bit 24 `0x01000000` marks the
member out of sync or awaiting rebuild.

### 5.3 Checksum

Sum of all little-endian 32-bit words in the configuration, minus the checksum field itself, modulo 2³². An invalid
checksum causes the firmware to ignore that copy.

### 5.4 State derivation

```
failed slots = slots with the FAILED bit + slots with the out-of-sync bit
RAID5:  0 -> Normal,  1 -> Degraded,  >=2 -> Failed
```

The rule comes from the mdadm implementation and is public documentation. Its credibility here rests on how well it
reproduces the observed behaviour:

| Configuration | Computed failed slots | Computed state | What the BIOS displayed |
|---|---:|---|---|
| before repair | 2 | Failed | Failed |
| after repair | 1 | Degraded | Degraded |

Both before and after matched, which is why the field edits were made according to this model.

---

## 6. Repair design

### 6.1 Options

| Option | Content | Outcome | Decision |
|---|---|---|---|
| 1 | Read-only offline extraction, no metadata change | Files retrievable, array still unusable | Requires another 24 TB of destination space, which was unavailable; also requires maintaining a bespoke reassembly environment |
| 2 | Modify the metadata: restore `VLK5JGVY` as a member, set the volume to Degraded, keep A isolated | Array accessible, further assessment possible | adopted |
| 3 | Set the volume to Normal | UI looks correct | rejected, see 6.2 |

### 6.2 Why Normal was rejected

`Normal` asserts that all members hold identical data. Member A was offline during the degraded period and genuinely
missed writes, and the two differing stripes in 4.6 cannot exclude it. Setting the volume to Normal would mean:

- the controller considers all four members synchronised and will never rebuild A
- reads landing in A's stale regions return old data without reporting an error
- structural checks still pass, so the corruption is hard to detect

The firmware also derives the volume state from the members. Storing a state that contradicts the member states may
cause the controller to rewrite the metadata on its own.

Until a rebuild has actually completed, `Degraded` is the state that matches reality.

### 6.3 Why all three members were written

If only `VLK5JGVY` were modified, C, D and A would still carry the old configuration (generation 763553) that records
B as missing. The repaired B would be generation 763554 and should win according to mdadm's behaviour, but the rules
Intel's private driver uses when merging copies across generations — in particular whether failure flags propagate —
cannot be verified externally.

Writing the same configuration (generation 763554) to every surviving member makes the copies byte-identical, so
there is no conflict to resolve at boot. The cost is modifying two more disks, 15 bytes each.

### 6.4 Basis for allowing A to be overwritten

Once the member relationship was restored, re-attaching A caused the controller to rebuild it. A rebuild recomputes
A's entire data area from the other three members and overwrites it. It is irreversible.

The basis is the timeline in section 2: A was offline during the degraded period, so its data is behind C, B and D.
The rebuild direction is correct. Had that judgement been reversed, the rebuild would have overwritten the newest
data. The premise was confirmed verbally by the owner and is not proven by data verification.

### 6.5 Field values

| Field | Before | After | Basis |
|---|---|---|---|
| `generation_num` | 763553 | 763554 | strictly newer than any existing copy; identical on all written disks, so no arbitration is needed |
| `disk[2].serial` | `"VLK5JGVY:0"` + `159` | `"VLK5JGVY"` + `00159` | the 16 bytes from that disk's own record |
| `disk[2].status` | `0x00000006` | `0x0000053A` | that disk's own record is `0x0000053E`; clearing FAILED gives a value identical to the other healthy members |
| `disk[2].scsi_id` | `0xFFFFFFFF` | `0x00000000` | the historical value in that disk's own record |
| `disk_ord_tbl[2]` | `0x01000002` | `0x00000002` | clear the out-of-sync bit |
| `map_state` | 3 | 2 | after the repair only A remains as a failed slot |
| others | — | unchanged | family, volume name, size, member count, level, strip, data start, `failed_disk_num`, the other records, A's out-of-sync bit |

Of these, `scsi_id` is a copied historical value rather than a derived one. If the firmware applies additional rules
to that field, the first boot could have failed.

---

## 7. Execution record

### 7.1 Preconditions

Checked before writing; any failure aborts the operation:

1. device capacity equals 8 001 563 222 016 bytes
2. `IOCTL_STORAGE_GET_DEVICE_NUMBER` returns the requested disk number
3. the ATA `IDENTIFY` serial matches (the USB bridge serial is not used)
4. the preimage hash of the target 4 KiB sector matches the reviewed value
5. the hash of the configuration currently on the disk matches the reviewed baseline

### 7.2 Write method

A single 4096-byte write at offset `8 001 563 217 920`, 4 KiB aligned, with `FILE_FLAG_WRITE_THROUGH` plus
`FlushFileBuffers`. The sector was then read back twice and compared with the planned image, and the disk identity
was re-checked.

### 7.3 Changes per disk

| Disk | Bytes | Content |
|---|---:|---|
| `VLK5JGVY` | 22 | checksum, generation, its own status (FAILED cleared), the other member's record updated, volume state |
| `VKH3B65X` | 15 | checksum, generation, `VLK5JGVY`'s serial/status/scsi_id, volume state, out-of-sync bit |
| `VJGH3P3X` | 15 | same as above |

After the writes, the trailing 4 KiB sector hashes identically on all three disks:

```
04553866e753bfef715a82eb042fa5ca969f90df6f242ae460540226681c7e48
```

The trailing 64 KiB was then re-read and compared byte for byte with the pre-write backups: the number of changed
bytes matches the table above and all of them fall inside the configuration sector. The first 64 KiB of all three
disks is identical to the backups.

Full hashes and the byte-level diff: [docs/05-evidence.md](docs/05-evidence.md).

---

## 8. Result

### 8.1 First boot

`VLK5JGVY`, `VKH3B65X` and `VJGH3P3X` were attached, `VKJGM9XX` kept isolated, and the machine booted into the UEFI
RST screen.

It showed `Degraded`. `VLK5JGVY` was a member again, the 0-byte record was gone, and the missing member was shown as
`VKJGM9XX`.

### 8.2 Re-attaching the out-of-sync member

After `VKJGM9XX` was re-attached, the BIOS showed `Rebuild` and the rebuild started automatically.

### 8.3 OS-side readings

| Item | Value |
|---|---|
| Physical disk | `Intel Raid 5 Volume DATABASE`, 24 004 676 026 368 bytes, GPT, Online, Healthy |
| Volume | `G:`, NTFS, 22 356.1 GB, 9 029.3 GB free, Healthy / OK |
| File access | opened and checked, normal |

The volume byte count matches the size recorded in the metadata, which confirms the strip geometry, data start and
member order.

<img src="docs/images/rst-rebuild-progress.jpg" alt="Intel RST rebuilding the DATABASE volume">

The RST screen during the rebuild: four members present, volume back as RAID5, rebuild at 9%.

---

## 9. Open items and limitations

1. `C:` and `D:` (the other RAID1, SYSTEM volume) still report `Warning / Scan Needed`. That state predates this work,
   is unrelated to the metadata modification, and has not been addressed.
2. The array currently uses write-back caching with write-cache buffer flushing disabled. Enabling flushing or
   switching to write-through would reduce what a power loss can take with it.
3. The archive on `E:` is on the same machine as the data, so it is not an off-site backup. Important data needs to be
   copied off the machine.
4. All four disks' metadata has since been rewritten by the firmware (generation, `scsi_id`, rebuild flags). The hashes
   in this document describe the moment of the write and not the current disk contents. A future repair of this kind
   would need fresh preimages.
5. The repair derives from the public mdadm implementation and was not tested against other BIOS or OROM versions. The
   success in this case is a single empirical result.
6. `scsi_id` was a copied historical value rather than a derived one; additional firmware rules on that field could
   cause an acceptance failure.

---

## 10. Reproducing the procedure

### 10.1 Applicability

All of the following should hold:

- Intel RST RAID5 with 4 members
- volume state `Failed`
- exactly one member shown as `Non-RAID`, or a 0-byte disk record in state "Lost"
- that record's serial carries a `:0` suffix
- the volume was not deleted, initialised, or "marked as normal"
- the incident began with a cable, connector, power or case-move event

A volume that has been deleted or re-initialised is outside the scope of this method.

### 10.2 Steps

Detailed flow: [docs/03-procedure.md](docs/03-procedure.md).

```powershell
# identify the attached disk (capacity and sector geometry must match the members)
Get-Disk | Where-Object BusType -eq 'USB' |
  Select-Object Number,FriendlyName,Size,LogicalSectorSize,PhysicalSectorSize

# read-only: verify identity and dump the configuration
python scripts\verify_present_state_readonly.py <disk number> <ATA SERIAL>

# read-only: decode a 584-byte configuration
python scripts\dump_cfg.py samples\VLK5JGVY_IMSM_configuration.bin

# dry run; writes nothing without --apply
python scripts\apply_mpb_write.py <disk number> <ATA SERIAL>

# only after all preconditions pass
python scripts\apply_mpb_write.py <disk number> <ATA SERIAL> --apply
```

The constants at the top of each script correspond to this case and must be changed for other disks. Offsets must be
recomputed for the actual capacity and sector size.

### 10.3 Repository contents

| Path | Content |
|---|---|
| [docs/01-case-study.md](docs/01-case-study.md) | Supplementary notes on the case and the approaches that were excluded |
| [docs/02-imsm-metadata-format.md](docs/02-imsm-metadata-format.md) | Complete 584-byte field map, status bits, checksum, on-disk layout |
| [docs/03-procedure.md](docs/03-procedure.md) | Step-by-step procedure and the problems encountered during it |
| [docs/04-hardware.md](docs/04-hardware.md) | Machine configuration, disk models, serials, geometry |
| [docs/05-evidence.md](docs/05-evidence.md) | All hashes and the byte-level change record |
| [docs/06-references.md](docs/06-references.md) | Intel advisory, mdadm source, kernel sources |
| `scripts/` | Read-only inspection tools and a writer with precondition checks |
| `samples/` | The real configuration blocks from before the repair and the repaired one |

---

## 11. References

- Intel support article on the drive-drop issue:
  <https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>
- mdadm IMSM implementation: <https://raw.githubusercontent.com/md-raid-utilities/mdadm/main/super-intel.c>
  Relevant functions: `mark_failure()`, `mark_missing()`, `__gen_imsm_checksum()`, `store_imsm_mpb()`,
  `imsm_count_failed()`, `imsm_check_degraded()`, `__prep_thunderdome()`
- Linux `drivers/md/raid5.c`, `fs/ntfs3/ntfs.h`, `fs/ntfs3/fslog.c`

A note on versions: the OROM built into this machine's BIOS is 19.5, and it is the OROM that enumerates the disks and
determines the array state at power-on. The Windows driver version does not affect that process, which is why the
repair uses the `1.3.00` configuration format. A fix for the Intel issue would have to come from the motherboard
vendor as a BIOS update; upgrading the Windows side cannot substitute for it.

---

## License

MIT, see [LICENSE](LICENSE). Serial numbers, models and geometry are published with the owner's permission.
