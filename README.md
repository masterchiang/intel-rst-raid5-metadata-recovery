# Intel RST / IMSM RAID 5: bringing a dropped member back from `Non-RAID` to `Degraded` → `Rebuild`

**English** | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Español](README.es.md) | [Русский](README.ru.md)

> A real, verified, end-to-end recovery of a 4-disk Intel RST RAID 5 volume (`DATABASE`, 24 TB) that
> the firmware had declared **Failed**, with one member disk stuck at **`Non-RAID`**.
>
> Result: **`Failed` → `Degraded` → `Rebuild` → mounted and readable.**
> No formatting. No volume deletion. No initialisation. No full-disk backup was ever available.

---

## TL;DR

The volume was `Failed` and one member disk (`VLK5JGVY`) was reported as `Non-RAID`.
The data on the remaining members was intact and even the filesystem structures could be read offline.

The whole failure was **metadata-only**. We patched **22 bytes** inside one 4 KiB physical sector at the
very end of that disk, and the firmware accepted it on the next boot.

Everything needed is in this repository: the exact byte layout, the exact field values, the read-only
verification scripts, and the guarded write tool.

If you are here because your array says `Failed`, **read [Warnings](#warnings-before-you-touch-anything) first.**

---

## The symptom

Typical Intel RST behaviour after a member disk is lost and re-attached:

| Where | What you see |
|---|---|
| BIOS / UEFI RST (OROM) | The volume exists but is `Failed`. The re-attached disk shows as `Non-RAID`. |
| Windows RST GUI | A phantom entry with **`Size 0 Bytes`, `Status: Lost`, `Controller/Port: Unknown`**, and a serial number with a `:0` suffix (e.g. `VLK5JGVY:0`). |
| The disk itself | Physically healthy. ATA `IDENTIFY` returns the correct serial, capacity and SMART data. |

The disk is **not** broken and **not** blank. It just carries a metadata record that says
"this slot belongs to a member that is missing/failed", so the firmware refuses to bind the
physical disk to that slot.

<table>
<tr>
<td width="50%"><img src="docs/images/usb-member-diskgenius.png" alt="Member disk geometry"><br><i>A member disk taken out of the array and connected over USB. Note <code>512 B</code> logical / <code>4096 B</code> physical sectors and <code>15628053168</code> sectors.</i></td>
<td width="50%"><img src="docs/images/usb-member-ata-identify.png" alt="ATA IDENTIFY over USB bridge"><br><i>ATA identity is still fully readable through the USB bridge (<code>SATA-III UAS @ Oxford</code>) — serial, LBA count, 4K/512 geometry, WWN.</i></td>
</tr>
<tr>
<td colspan="2"><img src="docs/images/usb-member-smart.png" alt="SMART of the member disk"><br><i>SMART of the same disk: 0 reallocated sectors, 0 pending sectors, 0 offline uncorrectable. A perfectly healthy drive that the firmware classified as <code>Non-RAID</code>.</i></td>
</tr>
</table>

## Root cause

Intel RST stores its array configuration in a structure called the **MPB** (MetaData Parameter Block),
written at the very end of **every** member disk. The on-disk signature is:

```
Intel Raid ISM Cfg Sig. 1.3.00
```

Each member carries a **full copy of the whole array description**, not just its own record.
When a disk disappears, the controller does not delete its record — it **marks it**, and it marks it in
three separate places at once:

| Field | Value when the member is missing | Meaning |
|---|---|---|
| `disk[i].status` | `0x00000006` (`CONFIGURED \| FAILED`) | this slot exists but is dead |
| `disk[i].scsi_id` | `0xFFFFFFFF` | "I don't know where this disk is" |
| `disk[i].serial` | real serial **+ `:0`** appended | do not match this against a physical disk |
| `map.disk_ord_tbl[slot]` | bit `0x01000000` (`IMSM_ORD_REBUILD`) set | this member is out of sync |

This is not a guess: it is exactly what the public `mdadm` IMSM implementation writes in
`mark_failure()` / `mark_missing()` (see [references](docs/06-references.md)).

**The serial is the killer.** Member matching compares the **full 16-byte serial field** with
`strncmp`. `"VLK5JGVY:0"` is not equal to `"VLK5JGVY"`, so the physical disk can never be bound to its
own slot, no matter how many times you reboot or re-seat the cable.

On top of that the volume state is recomputed from the members:

```
failed_count = number of slots with (FAILED bit set) OR (IMSM_ORD_REBUILD set)
RAID5 with 1 failed  -> Degraded
RAID5 with 2+ failed -> Failed
```

In our case **two** slots were counted as failed: the dropped disk and the member that had gone
out of sync hours earlier. Two out of four on RAID 5 = `Failed`, forever, until the metadata changes.

## What we actually did

Full step-by-step in [docs/03-procedure.md](docs/03-procedure.md). Short version:

1. **Took every member off the motherboard.** No controller involvement, no chance of the firmware
   "helpfully" rewriting anything while we worked.
2. **Read the last 64 KiB of each disk over a USB-SATA bridge, read-only**, twice, and verified the two
   reads were identical. Saved SHA-256 of everything.
3. **Located the MPB on disk.** It is *not* a contiguous 584-byte blob:
   - anchor sector (config bytes `0..511`) at `last_LBA - 1`
   - extended part (config bytes `512..583`) in the **first 72 bytes** of `last_LBA - 2`
   - both live inside the **same 4 KiB physical sector** — the one on which you must do a
     read-modify-write, never a 584-byte write.
4. **Parsed all four copies** with the field map from the public `mdadm` source and compared them.
   Three copies were identical and checksum-valid (generation 763553). The dropped disk held a stale
   copy (generation 763509) with a **broken checksum**.
5. **Constructed the repaired configuration** from the newest valid copy, changing only what had to change:
   - B's serial field: `"VLK5JGVY:0"` → `"VLK5JGVY"` (+NUL + its own 5-char suffix)
   - B's `status`: `0x00000006` → `0x0000053a`  (clear `FAILED`, keep the flags a healthy member has)
   - B's `scsi_id`: `0xFFFFFFFF` → `0x00000000`  (the value that disk itself carried last)
   - B's `disk_ord_tbl[2]`: `0x01000002` → `0x00000002`  (clear `IMSM_ORD_REBUILD`)
   - `map.map_state`: `3` (Failed) → `2` (Degraded)
   - `generation_num`: `763553` → `763554`
   - recomputed the checksum
   - **left untouched:** array family, volume id/name/size, member count, RAID level, strip size,
     data start, `failed_disk_num`, the *other* members' records, and the out-of-sync flag of the
     member that had genuinely missed writes.
6. **Wrote the same 584-byte configuration to every remaining member** (one 4 KiB read-modify-write per
   disk), so all surviving copies became **byte-identical**. This removes every cross-generation
   ambiguity the firmware might have to resolve at boot.
7. **Read back and verified** the whole sector, the checksum, and the disk identity.

Total damage to the array: **22 bytes on the dropped disk, 15 bytes on each of the other two** — all
inside the metadata sector, at the very end of each disk. Not one byte in the data area.

## Result

| Stage | Observed |
|---|---|
| Before | `Failed`; `VLK5JGVY` = `Non-RAID`; phantom `VLK5JGVY:0`, `0 Bytes`, `Lost` |
| After writing 3 members, booting with only those 3 | **`Degraded`**, `VLK5JGVY` back as a member, missing member = `VKJGM9XX` |
| After re-attaching the out-of-sync member | **`Rebuild`** started automatically |
| Windows | `Intel Raid 5 Volume DATABASE`, 24 004 676 026 368 bytes, **Healthy / OK**, mounted, files open fine |

The 3 disks that were patched kept on working through a full rebuild. The volume came back.

## Warnings before you touch anything

1. **This is irreversible if you get it wrong.** We had no full backup and neither will you. A wrong
   offset or a wrong checksum can turn a recoverable array into a lost one.
2. **Never write a bare 584-byte blob.** The configuration is split across two sectors inside one
   4 KiB physical sector. Read the whole sector, modify only the MPB bytes, write the whole sector back.
3. **Never set the volume to `Normal`.** `Normal` is a *claim* that all members are synchronised. If a
   member is genuinely stale, `Normal` hides the problem: reads return old data from the stale disk, all
   structural checks pass, and you get silent corruption. `Degraded` is the only honest state until a
   real rebuild has happened.
4. **Do not let Windows mount the volume read-write before you have verified anything.** NTFS will
   replay its journal and write to a degraded array. Use `mountvol /N` or set the disk read-only first.
5. **Do not run `chkdsk /f`** on a recovered array until you have copied your important data out.
6. **Do not "try things" repeatedly.** Every boot inside the RST OROM can rewrite metadata. Read-only
   first, decide, then act once.
7. Every disk model, capacity and geometry is different. The offsets here are for
   `8001563222016`-byte members with 512/4096 sectors. **Recalculate; never copy numbers.**

## Repository layout

```
README.md                     you are here (English)
README.zh-CN.md               full Chinese version
README.ja/de/es/ru.md         condensed guides (JA / DE / ES / RU)
docs/01-case-study.md         the whole story, timeline, what was ruled out
docs/02-imsm-metadata-format.md  584-byte MPB field map, checksum, status bits
docs/03-procedure.md          step-by-step runbook with commands
docs/04-hardware.md           exact machine, disks, serials, geometry
docs/05-evidence.md           hashes, read-back proofs, what changed byte by byte
docs/06-references.md         Intel advisory, mdadm source, kernel sources
docs/images/                  screenshots
scripts/                      read-only inspectors + guarded writer
samples/                      the four real 584-byte configurations (before) + the repaired one
```

## Quick start for your own case

```powershell
# 1. read-only: dump the MPB of one attached member and decode every field
python scripts\dump_cfg.py samples\VLK5JGVY_IMSM_configuration.bin

# 2. read-only: verify a disk's identity + current metadata before doing anything
python scripts\verify_present_state_readonly.py 2 VLK5JGVY

# 3. dry-run the writer (it refuses on any mismatch, and writes nothing without --apply)
python scripts\apply_mpb_write.py 2 VLK5JGVY

# 4. only when every guard passes
python scripts\apply_mpb_write.py 2 VLK5JGVY --apply
```

Read [docs/03-procedure.md](docs/03-procedure.md) before running anything. The scripts are the ones that
were actually used, with hard-coded constants from this case at the top of each file — **edit them for
your own disk**, they are not a generic installer.

## References

- **Intel advisory (the bug that started all of this):**
  <https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>
- `mdadm` IMSM reference implementation (the authoritative public description of this format):
  <https://raw.githubusercontent.com/md-raid-utilities/mdadm/main/super-intel.c>
- Linux `drivers/md/raid5.c`, `fs/ntfs3/*` — see [docs/06-references.md](docs/06-references.md)

## Notes on firmware versions

Upgrading the **Windows** RST driver / RST GUI does **not** change how your array is assembled at boot.
The **OROM embedded in the motherboard BIOS** enumerates the disks, decides the array state, and writes
metadata first. That is the code that must understand your metadata — which is why this repair targets
the `1.3.00` MPB format that 19.x OROMs parse natively, and why any real fix for the Intel disconnect
bug has to come from the motherboard vendor as a BIOS update.

## License

MIT — see [LICENSE](LICENSE). Case data (serials, models, geometry) is published with the owner's
explicit permission, in the hope that it helps someone else.
