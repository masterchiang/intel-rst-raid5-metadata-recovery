# Intel RAID 5 says "Failed" and one disk shows "Non-RAID" — how to get your array back

**English** | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | [Español](README.es.md) | [Русский](README.ru.md)

A disk is not broken. It is only *labelled* broken — and we can relabel it.

This repository documents a real recovery of a 24 TB Intel RST RAID 5 where the firmware had
declared the volume **Failed** and one member disk was stuck at **Non-RAID** forever.
Nothing was formatted, nothing was deleted, and the data came back.
**The total change was 22 bytes on one disk.**

It also contains the tools we used, so you can do the same — and the full byte-level explanation,
so you can check our work before you trust it with your own data.

---

## Read this first (30 seconds)

| This is | This is not |
|---|---|
| A fix for **one specific situation**: your array is `Failed` and one member shows as `Non-RAID`, with your data still intact on the other disks | A general data-recovery tool |
| A description of **why re-seating cables and rebooting does nothing**, and what actually does | A one-click program. You will edit bytes on a raw disk. |
| A **worked example with real serial numbers and real hashes** so you can compare against your own machine | Safe. There is no undo. A wrong offset can destroy the array. |

If you only remember one thing: **your disk is fine, its name tag is wrong.** Read
[What actually went wrong](#what-actually-went-wrong) and you will understand your own case in
two minutes.

## Is this your situation?

Tick the boxes. If you cannot tick most of them, this page is probably not your fix.

- [ ] Intel RST / Optane / VMD RAID **5** with **4 disks** (3 or 5 disks: same idea, different arithmetic)
- [ ] The volume shows **`Failed`** in the BIOS RST screen and/or in the Intel RST app in Windows
- [ ] **One** disk is reported as **`Non-RAID`**, "unknown", or appears as a ghost entry with
      **size 0 bytes / status Lost**
- [ ] That ghost entry's serial number looks like `YOURSERIAL:0` — the real serial with **`:0`** added
- [ ] The other disks are healthy and the volume was working until a **cable, connector, power or
      re-seating event**
- [ ] You have **not** initialised, deleted, re-created, or "reset to normal" the volume
- [ ] You have **not** let a rebuild run onto the disk that holds your only good copy

**If you already deleted or re-initialised the volume: stop.** That is a different failure, and this
method does not apply.

## What actually went wrong

Intel's RAID controller does not store the array layout in one place. It writes a **small label near
the end of every single disk**, and each label describes the **whole array**: which disks belong to
it, in what order, and what state each one is in.

Here is the important part. When a disk drops out, the controller **does not remove it from the label**.
It marks it as dead, in a very specific way:

| What the label says | Normal disk | After it drops out |
|---|---|---|
| the disk's name | `VLK5JGVY` | **`VLK5JGVY:0`** ← two characters appended |
| its status | `alive` | **`failed`** |
| where to find it | a port number | **`unknown`** |
| is it in sync | yes | **no** |

The controller recognises a disk by comparing the **name in the label** with the **name the disk
reports about itself**. Those are compared **exactly**, character for character.

So after the accident the label says `VLK5JGVY:0`, the disk says `VLK5JGVY`, the two never match
again, and the disk is shown as `Non-RAID` for the rest of its life.
No amount of re-seating, rebooting, BIOS updates or driver updates can change that, because the
mismatch is **text stored on the disk**, not a hardware fault.

The volume then shows `Failed` for a second reason: the controller counts how many members are
"not right". This array had **two** (the disk that came loose hours earlier and had missed writes,
plus this one). A 4-disk RAID 5 tolerates one. Two means `Failed`.

## The fix, in one sentence

**Put the disk's real name back into the label, clear the "failed" and "out of sync" marks from
*that* member, tell the label the array is `Degraded` (1 problem left, on the disk that really did
miss writes), recompute the label's checksum, and write the same corrected label to every surviving
disk so there is nothing left to argue about.**

Numbers for this case:

| Disk | Bytes changed | Where |
|---|---:|---|
| the `Non-RAID` disk (`VLK5JGVY`) | **22** | one 4 KiB block at the very end of the disk |
| each of the two healthy disks | **15** | same place on each |

**Zero bytes changed in the data area.** No partition table touched, no file touched.

## What we got

| Stage | What the screen said |
|---|---|
| Before | `Failed`; the disk is `Non-RAID`; a ghost entry of **0 bytes, Lost**, serial `VLK5JGVY:0` |
| Boot with only the 3 repaired disks | **`Degraded`** — the disk is a member again; the missing member is the *other* one |
| Plug the missing one back in | **`Rebuild`** starts by itself |
| In Windows | 24 004 676 026 368 bytes — exactly the original size — mounted, files open normally |

<img src="docs/images/rst-rebuild-progress.jpg" alt="Intel RST rebuilding the DATABASE volume">

*After the repair: four members present again, the volume back as RAID 5, status **rebuild 9%**.
The `0 bytes / Lost` ghost entry is gone.*

Three disks whose labels we had edited went on to survive a full rebuild of the fourth.

## Stop — read this before you touch anything

1. **There is no undo.** We had no backup. You probably don't either. Read twice, write once.
2. **Never write a bare 584-byte block.** The label is split across two sectors that live inside
   **one 4 KiB physical sector**. Read the whole 4 KiB, change only the label bytes, write the whole
   4 KiB back.
3. **Never set the volume to `Normal`.** `Normal` means "all disks are in sync". If one disk is
   actually behind, `Normal` makes Windows serve **old data silently** — every check passes and your
   files quietly rot. `Degraded` is the only honest state until a rebuild has really happened.
4. **Do not let Windows mount it read-write** before you verify anything. NTFS will replay its journal
   into a degraded array. Use `mountvol /N` or `Set-Disk -IsReadOnly $true`.
5. **Do not run `chkdsk /f`** before your important data is copied somewhere else.
6. **Do not "try a few things".** Every boot into the BIOS RAID screen can rewrite the label.
   Read first, decide once, act once.
7. **Never copy our numbers.** Capacities and sector sizes differ between models. The offsets here are
   for 8 001 563 222 016-byte disks with 512/4096 sectors. Recompute yours.

## Do it yourself

You need: a USB-SATA dock/adapter, a Windows machine (or Linux), and patience. Details and the
reasoning behind each step: **[docs/03-procedure.md](docs/03-procedure.md)**.

```
Step 1  Take every disk off the motherboard. Work on one disk at a time through USB.
Step 2  Read the last 64 KiB of each disk twice, hash it, and keep those backups.
Step 3  Cut the 584-byte label out of the last 4 KiB and decode it. Compare the four labels.
Step 4  Build the corrected label in memory (5 fields change). Check the checksum.
Step 5  Dry-run the writer. Read what it says it will change. Then write, and let it verify.
Step 6  Put only the repaired disks back on the motherboard and boot into the BIOS RAID screen.
```

Concrete commands:

```powershell
# what disk is attached? capacity and geometry must match your members exactly
Get-Disk | Where-Object BusType -eq 'USB' |
  Select-Object Number,FriendlyName,Size,LogicalSectorSize,PhysicalSectorSize

# read-only: confirm it is the disk you think it is, and dump its label
python scripts\verify_present_state_readonly.py <disk number> <ATA SERIAL>

# read-only: decode any 584-byte label and print every field
python scripts\dump_cfg.py samples\VLK5JGVY_IMSM_configuration.bin

# dry run - refuses on any mismatch, writes nothing without --apply
python scripts\apply_mpb_write.py <disk number> <ATA SERIAL>

# the real thing, only after every guard passed
python scripts\apply_mpb_write.py <disk number> <ATA SERIAL> --apply
```

The scripts are the ones actually used on the real disks, with this case's constants at the top of
each file. **You must edit those constants for your own disks.** They are not an installer.

## What is in this repository

| Path | What it is, in plain words |
|---|---|
| [docs/01-case-study.md](docs/01-case-study.md) | The whole story, hour by hour, plus the advice we tried and why it fails |
| [docs/02-imsm-metadata-format.md](docs/02-imsm-metadata-format.md) | The complete map of the 584-byte label: every field, every bit, the checksum formula |
| [docs/03-procedure.md](docs/03-procedure.md) | Step-by-step runbook with commands and the failure modes we hit |
| [docs/04-hardware.md](docs/04-hardware.md) | The exact machine, disks, serial numbers, geometry — so you can compare |
| [docs/05-evidence.md](docs/05-evidence.md) | Every hash and every byte we changed, so you can audit instead of trust |
| [docs/06-references.md](docs/06-references.md) | The Intel advisory, the `mdadm` source, kernel sources |
| `scripts/` | Read-only inspectors and one guarded writer |
| `samples/` | The four real labels from before the repair, and the corrected one |

## FAQ

**My volume says `Failed` but no disk says `Non-RAID`. Does this apply?**
Probably not. This fix is specifically about a member being *unable to rejoin*. If all disks are
present and the volume is still `Failed`, you have a different problem.

**Can I just mark it "Normal" in the BIOS screen?**
No. That writes a label claiming everything is in sync, which is false. It hides the difference
instead of fixing it, and the controller recomputes the state from the disks anyway — so it may
"correct" your edit straight back.

**Will I lose data from the disk that was out of sync?**
If a rebuild runs onto it, yes — its data area is overwritten with values recomputed from the other
disks. In a cable-fault case that is the *correct* direction: the other disks are newer. But copy out
what you care about first.

**Do I have to modify all the disks, or only the broken one?**
Modify all surviving disks. If you patch only the broken one, the others still carry a label that says
"that slot is dead". Whether the controller believes the newer label is something you cannot verify —
we did not want to gamble, so we made every label identical.

**Can I do this on Linux instead of Windows?**
Yes, and it is arguably safer: `mdadm --examine /dev/sdX` prints the same fields, and you can write
with `dd` or with mdadm's own `--update`. The format is identical.

**Does this work on RAID 1, RAID 10, or RAID 6?**
The label format is the same, but the rules for what counts as "too many failed disks" differ.
Read `docs/02` and the `mdadm` source before assuming.

**Will updating the Intel driver fix it?**
No. The array is assembled by code inside your motherboard BIOS before Windows starts. The driver
version only affects what happens afterwards. This is also why the real fix for Intel's drive-drop bug
can only come as a **BIOS update from your motherboard vendor**.

**Is this "hacking" my disks?**
It is writing six fields of a configuration record that Intel's own software writes on every change.
It is exactly as reversible as that record's backup — which is why step 2 is "keep a backup".

**My disk is 10 TB / 14 TB / different brand.**
Then all the offsets differ. Read `docs/02`, compute yours, and check them against a dump of your own
disk before writing anything.

## For the technically curious

The short version: the label is Intel's **MPB** (MetaData Parameter Block), signature
`Intel Raid ISM Cfg Sig. 1.3.00`, 584 bytes for a 4-disk single-volume array, stored in the last two
512-byte sectors of every member. Its checksum is a plain sum of little-endian 32-bit words.
All of it, with offsets, status bits and the state rules, is in
**[docs/02-imsm-metadata-format.md](docs/02-imsm-metadata-format.md)**.

The behaviour was derived from the public `mdadm` implementation of this format and then confirmed
on real firmware: the state we computed offline matched exactly what the BIOS displayed, before and
after the repair.

## References

- **Intel advisory — the drive-drop bug that starts all of this:**
  <https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>
- `mdadm` IMSM implementation — the authoritative public description of this format:
  <https://raw.githubusercontent.com/md-raid-utilities/mdadm/main/super-intel.c>
- Linux `drivers/md/raid5.c`, `fs/ntfs3/*` — see [docs/06-references.md](docs/06-references.md)

## License

MIT — see [LICENSE](LICENSE). Serial numbers, models and geometry are published with the owner's
permission. Data has no price; if this saves yours, it was worth writing down.
