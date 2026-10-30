# Case study: `Failed` RAID 5, one member stuck at `Non-RAID`

This is the narrative. For the byte-level material see
[02-imsm-metadata-format.md](02-imsm-metadata-format.md); for the runbook see
[03-procedure.md](03-procedure.md).

## What the machine was doing

A 4-disk Intel RST RAID 5 (`DATABASE`, 24 TB, 128 KiB strips) on a Z790 board with VMD enabled.
Two other arrays on the same machine, both untouched throughout: a 2-disk RAID 1 holding the OS, and a
4× NVMe RAID 5 for working data.

The machine was physically moved. The SATA connector of member **`VKJGM9XX`** came loose.

## How it went from `Degraded` to `Failed`

```
1. VKJGM9XX drops out                      -> Degraded (3 of 4 members, writes continue)
2. several hours of normal use              -> the array keeps writing with parity recomputed
3. machine shut down, VKJGM9XX re-seated
4. at the same time VLK5JGVY is pulled by mistake
5. both slots now problematic               -> Failed
6. VLK5JGVY plugged back                    -> shows as Non-RAID, never rejoins
```

Step 2 is the part that decides everything later. While the array ran degraded, **writes continued on
the other three members**. So `VKJGM9XX` is genuinely stale, while `VLK5JGVY` — the disk pulled last —
was never left behind a write.

That is exactly what the metadata said when we finally read it:

```
slot 1 (VKJGM9XX): status 0x053A (healthy flags) but ordinal 0x01000001 -> out of sync
slot 2 (VLK5JGVY): status 0x000006, scsi_id 0xFFFFFFFF, serial "VLK5JGVY:0" -> missing
```

## The false trail

The RST GUI showed a phantom disk:

> Controller: unknown · Port: unknown · Port location: unknown · **Status: Lost** · Size: **0 Bytes** ·
> Serial number: **`VLK5JGVY:0`** · Model: *(blank)* · Capacity: 0

It is very tempting to read this as "the disk is dead" or "the disk is empty". It is neither. It is a
**record of a slot**, kept alive by the other three members, describing a member that the firmware has
decided is gone. The physical disk is fine and even reports a healthy SMART table.

The `:0` is not a partition suffix and not a USB artifact. It is part of the serial *field*, and it is
what prevents the disk from ever being matched again.

## Why the usual advice does not work

| Advice you will find online | Why it fails here |
|---|---|
| "Just re-seat the cable and reboot" | The blocker is a byte in the metadata, not the cable. We tried nothing else and went straight to the metadata for this reason. |
| "Mark the volume as Normal in the RST GUI / OROM" | `Normal` is a claim that all members are in sync. `VKJGM9XX` is genuinely stale. Marking `Normal` would have made reads return old data silently. Also, the firmware recomputes the state from the members, so storing `Normal` next to a member flagged out-of-sync creates an inconsistency it may "fix" by rewriting your metadata. |
| "Delete the array and recreate it without losing data" | Destroys the volume header mapping. Never do this to recover data. |
| "Let it rebuild onto the missing disk" | There was nothing to rebuild *onto*: the missing disk was not a member any more. And if the firmware had picked the stale disk as the rebuild **source**, it would have written old data across a healthy array. |
| "Update the RST driver" | The OROM in the BIOS assembles the array before Windows loads. The driver version cannot influence it. |
| "Use `TestDisk` / `R-Studio` to read the data" | Legitimate as a data-extraction last resort, but it only reads. It would have left the array dead and 24 TB of files reachable only through a paid tool. We wanted the array back. |

## The decision that mattered

Once the four metadata copies had been read and compared, the picture was unambiguous:

- three members carried the **same** configuration, generation 763553, valid checksum, and it said
  "`VLK5JGVY` is missing and `VKJGM9XX` is out of sync";
- the fourth (`VLK5JGVY`) carried an **older** configuration, generation 763509, with a **broken**
  checksum, saying "I am a member, `VKJGM9XX` is missing".

So the newest, most consistent statement of reality was the one on the *other three* disks — and it
was wrong about exactly one thing: it had written `VLK5JGVY` off.

The repair therefore was not "make the volume `Normal`". It was: **take the newest valid copy, restore
`VLK5JGVY`'s identity in it, keep `VKJGM9XX` marked out of sync, and put that same copy back on every
surviving member.**

The two possibilities for `VKJGM9XX` — declare it in sync, or admit it is stale — were decided by the
timeline: it missed hours of writes. Declaring it in sync would have been a lie that the firmware
cannot detect, and the price of that lie is silent corruption in whatever files happened to live on
those stripes.

## What happened next, in order

1. Three members (`VKH3B65X`, `VLK5JGVY`, `VJGH3P3X`) went back on the motherboard SATA ports,
   `VKJGM9XX` stayed out.
2. **BIOS showed `Degraded`, and `VLK5JGVY` was a member again** — no longer `Non-RAID`, and the
   phantom `0 Bytes` entry was gone.
3. `VKJGM9XX` was re-attached. **BIOS showed `Rebuild`** and it started automatically.
4. Windows mounted the volume (24 004 676 026 368 bytes, exactly the original size) and the files
   opened normally.

Note what step 2 proves and what it does not. It proves the metadata is now acceptable to the real
firmware — the thing that no offline model could prove beforehand. It does not prove the data on the
three members is internally consistent; only reading files does that, which is why the data was
checked before the rebuild was allowed to run.

## Things that could have gone wrong

- **The 4 KiB sector.** The configuration is not a contiguous 584-byte blob. Writing it as one would
  have corrupted the sector's other byte ranges. Everything was written as a full-sector
  read-modify-write.
- **The checksum.** A repaired configuration with a stale checksum is worse than no repair: the
  firmware may silently ignore that copy and pick a different one.
- **Mixed generations.** If only the broken disk had been repaired, three members would still say
  "this slot is dead" with a higher generation on some of them. Writing the identical configuration to
  all of them removed the arbitration entirely.
- **Windows.** The volume's NTFS was dirty. A read-write mount would have replayed the journal into a
  degraded array. The owner chose to go straight to a rebuild instead, which is a legitimate call —
  and because a rebuild recomputes the stale disk from the others, any writes made in that window are
  propagated correctly rather than left inconsistent.

## Honest limitations of this write-up

- We did not have a full backup, so we could not verify every byte of the recovered volume.
- Two sample stripes had non-zero XOR across the four members; XOR cannot localise the culprit, and
  both candidate versions passed structural checks. These were resolved *by* the rebuild, not by our
  analysis.
- The behaviour of Intel's closed OROM was inferred from the public `mdadm` implementation and then
  confirmed by a single successful real-world attempt. That is evidence, not a proof.
- The array is still one disk-fault away from failing again. Data was copied out afterwards.

## Credit where due

The insight that this was a metadata problem rather than a dying disk came from reading the four
members' last sectors and comparing them, and the field-level interpretation came from the public
`mdadm` source. Whoever maintains `super-intel.c` has quietly saved a lot of people's data.
