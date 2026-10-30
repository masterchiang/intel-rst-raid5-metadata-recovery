# Runbook

> Target audience: someone with a 4-member Intel RST RAID 5 where **one member reports `Non-RAID`**
> and the volume is `Failed`, and where the data on the other members looks intact.
>
> This is written from a Windows machine, because that is what the affected machine had.
> Linux with `mdadm` can do the same job — arguably more safely, because `mdadm --examine` shows you
> everything before you write anything.

---

## Phase 0 — Decide whether this applies at all

Answer all of these before touching anything:

- [ ] The volume is RAID 5 with 4 members and the failure was a **cable/connection event**, not a
      controller death, not a firmware re-flash, not an OS reinstall.
- [ ] At most **one** member is reported as `Non-RAID` / missing. Another member being *out of sync*
      is expected and fine (that is what Degraded means).
- [ ] The volume was never re-initialised, never had a member "reset to normal", never had a rebuild
      started onto the wrong disk.
- [ ] You can read the members' raw sectors (a USB-SATA bridge is enough).
- [ ] You accept that there is no backup and no undo.

If the volume was re-initialised, or a rebuild was started onto a disk holding the only good copy,
**stop**. You are in a different failure class and metadata editing will not fix it.

## Phase 1 — Freeze everything (read-only)

1. Power off. Label every disk. Write down which physical slot each came from.
2. **Do not** leave the array attached to the motherboard while you experiment. The OROM can rewrite
   metadata on every boot.
3. Connect **one** disk at a time through a USB-SATA bridge. Windows will happily hand you the whole
   raw device as `\\.\PhysicalDriveN`.
4. For each disk, read and hash:
   - first 64 KiB
   - last 64 KiB
   - read each range **twice** and require the two reads to be identical

```powershell
# which disk is it? capacity and geometry must match your member size exactly
Get-Disk | Where-Object BusType -eq 'USB' |
  Select-Object Number,FriendlyName,Size,LogicalSectorSize,PhysicalSectorSize,PartitionStyle
```

> **Expect a surprise here.** On one member Windows "recognised" a GPT and mounted a 0-byte volume,
> because that member happens to hold the *first* strip of the volume and therefore a copy of the
> protective MBR and GPT header. `PartitionStyle : GPT` with `FileSystem : (blank)` and `Size : 0` is
> exactly what that looks like. **It is not a real filesystem** and nothing was written — verify by
> comparing the first 4 KiB against your backup afterwards.

Verify the disk is the one you think it is, using the **ATA serial**, never the USB bridge's serial:

```
python scripts\verify_present_state_readonly.py <PhysicalDriveNumber> <EXPECTED_ATA_SERIAL>
```

It refuses to continue unless capacity, sector geometry, ATA serial and the on-disk MPB all match.

## Phase 2 — Find and decode the MPB

```
python scripts\dump_cfg.py <path to a 584-byte configuration file>
```

You need the 584 bytes assembled from the two sectors described in
[02-imsm-metadata-format.md](02-imsm-metadata-format.md). If you have no such file yet, dump the last
4 KiB of the disk and cut it yourself:

```python
blk = read(offset = size - 4096, length = 4096)     # one physical sector
cfg = blk[3072:3072+512] + blk[2560:2560+72]        # anchor + extended
assert len(cfg) == 584
```

Now compare the members. You are looking for:

| Observation | Meaning |
|---|---|
| N-1 copies byte-identical, valid checksum | that is your baseline |
| one copy with older generation and/or bad checksum | that is a disk that stopped being updated |
| the `Non-RAID` disk appears in the baseline as `status 0x06`, `scsi_id 0xFFFFFFFF`, serial `"<serial>:0"` | confirmed: it was marked missing, not erased |

If the `Non-RAID` disk's own copy says its status is `0x053E` (healthy flags + `FAILED`), that is also
expected: it kept a stale self-description from before the incident.

## Phase 3 — Build the repaired configuration (in memory, no writes)

Starting from the baseline copy, change only this:

| Field | From | To | Why |
|---|---|---|---|
| `disk[b].serial[16]` | `"<serial>:0"` + rest | the disk's own 16-byte field from its own record | the `:0` suffix alone blocks matching |
| `disk[b].status` | `0x00000006` | `0x0000053A` (or the disk's own `0x053E & ~0x04`) | clear `FAILED`, keep the private healthy bits |
| `disk[b].scsi_id` | `0xFFFFFFFF` | the value that disk last carried (often `0`) | `0xFFFFFFFF` is the "missing" marker |
| `disk_ord_tbl[slot_b]` | `... &#124; 0x01000000` | clear bit 24 | it is not out of sync |
| `map.map_state` | `3` | `2` | one problem slot remains |
| `generation_num` | `G` | `G + 1` | newest copy, and identical on every member you write |
| `check_sum` | — | recompute last | |

**Do not change:** `family_num`, `orig_family_num`, volume name/size, `num_disks`, `num_raid_devs`,
`raid_level`, `num_members`, `blocks_per_strip`, `pba_of_lba0`, `blocks_per_member`,
`num_data_stripes`, `failed_disk_num`, the other members' records, or the out-of-sync bit of the
member that genuinely missed writes.

Build it twice, from two different starting points if you can (e.g. from the baseline, and by fixing
the disk's own copy) and confirm both converge on the same 584 bytes. In our case both routes produced
`0x00000002` for the ordinal and `0x0000053A` for the status.

## Phase 4 — Guarded write

```
python scripts\apply_mpb_write.py <PhysicalDriveNumber> <ATA_SERIAL>          # dry run
python scripts\apply_mpb_write.py <PhysicalDriveNumber> <ATA_SERIAL> --apply  # real write
```

The tool refuses to write unless **all** of these hold:

- device capacity equals the expected member size
- `IOCTL_STORAGE_GET_DEVICE_NUMBER` reports the disk number you asked for
- ATA `IDENTIFY` serial matches
- the 4 KiB preimage hash matches the reviewed value
- the assembled on-disk configuration matches the reviewed baseline hash

Then it does exactly one 4 KiB `WriteFile` with `FILE_FLAG_WRITE_THROUGH` + `FlushFileBuffers`,
re-reads the sector twice, and compares against the planned image. A mismatch aborts.

## Phase 5 — Write the same configuration to every surviving member

Do this. Not just the broken one.

If you patch only the dropped disk, the other members still carry a copy that says
"this slot is missing/failed". Whether the firmware resolves that in your favour is an implementation
detail you cannot verify. Writing the identical 584 bytes to every remaining member removes the
question entirely — all copies agree, so there is nothing to resolve.

## Phase 6 — First controller contact

1. Power off. Detach the USB bridge and every member disk from it.
2. Attach **only the members you just repaired** to the motherboard SATA ports. Keep the out-of-sync
   member **physically disconnected**.
3. Boot into the UEFI RST screen. **Look, do not touch.**
   - Expected: volume present, **`Degraded`**, repaired disk listed as a member, missing member = the
     one you kept out.
   - Forbidden: `Mark as Normal` / `Reset to normal`, `Delete volume`, `Initialize`, any rebuild
     action on a healthy disk.
4. If it says `Failed`, the volume is gone, or the disk is still `Non-RAID` — **power off and stop**.
   Re-read the last 4 KiB of each member and diff it against your pre-boot image. That diff tells you
   exactly what the firmware did, and you can decide from evidence instead of guessing.

## Phase 7 — Read the data before you celebrate

Do **not** let Windows mount it read-write first. NTFS will replay its journal into a degraded array.

```powershell
mountvol /N                                   # stop auto-mounting of new volumes
mountvol G: /P                                # drop any stale mount point (if one exists)
```

After boot:

```powershell
Get-Disk | Format-Table Number,FriendlyName,Size,OperationalStatus
Set-Disk -Number <N> -IsReadOnly $true        # make the volume read-only before you look at it
```

If Windows offers "scan and fix", choose **continue without scanning**.

Copy out the files you care about and compare checksums against anything you have. Only after the data
is safely elsewhere should you consider anything that writes.

## Phase 8 — Rebuild the out-of-sync member

Re-attach the member that stayed out. Expect one of:

- the firmware starts a rebuild automatically, or
- it shows the member as missing/offline and asks you to mark it as a rebuild target.

Either way, be clear about what a rebuild does: it **overwrites that disk's data area with values
recomputed from the other members**. If that disk actually held newer data than the rest, that data is
gone. In a cable-fault scenario where the disk was absent during writes, the others are newer and the
rebuild is the correct direction.

Our out-of-sync member was rebuilt and the volume returned to `Normal`.

## Phase 9 — Afterwards

- Enable write-cache buffer flushing (or switch to write-through) on the volume. RST often ships with
  `Write cache buffer flushing: Disabled` + `Write-back`, which loses in-flight writes on power loss.
- Run an **online read-only** scan (`chkdsk X: /scan`), never `/f`, until your data is copied out.
- Re-take your metadata backups: after any controller contact, every member's MPB has changed
  (generation, scsi_id, rebuild flags). The old hashes no longer describe the disks.
- Fix the physical cause. In this case a loose SATA connector started everything.

---

## Failure modes we actually hit

| Symptom | Cause | What we did |
|---|---|---|
| Windows showed `PartitionStyle: GPT` on a member and mounted a 0-byte volume | that member carries the volume's first strip, hence a copy of the MBR/GPT | verified the first 4 KiB was byte-identical to the backup; no filesystem driver attached so nothing was written |
| `Get-Volume` reported `Size 0`, `FileSystem` blank | no NTFS boot sector on that single member | ignored it; do not "initialise" it |
| An ad-hoc one-liner read returned all zeros for the first 4 KiB | a bug in that throwaway script, not on the disk | re-read with the checked script; the sector was fine. **Always double-read and verify.** |
| Volume mounted fine but `C:`/`D:` of an unrelated RAID1 showed `Scan Needed` | pre-existing, unrelated | left alone |
