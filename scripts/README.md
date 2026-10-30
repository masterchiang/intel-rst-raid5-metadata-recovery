# Scripts

These are the **actual** scripts used on the real disks — not a cleaned-up rewrite. They are published
because the checks in them are the interesting part, and because a reader should be able to see exactly
what was executed.

## Read this first

- Each file has **constants at the top from this specific case** (disk paths, expected SHA-256 values,
  capacity). Running them unmodified against your own disks will do one of two things: refuse, or do
  the wrong thing. **Edit the constants.**
- Only `apply_mpb_write.py` ever writes to a disk, and only with `--apply`.
- Everything else opens devices with `GENERIC_READ`.

## The flow

| # | Script | What it does | Touches the disk |
|---|---|---|---|
| 1 | `verify_present_state_readonly.py <n> <serial>` | ATA `IDENTIFY` identity check, capacity/geometry check, double read of the last 64 KiB, comparison against the archived preimage, assembles the on-disk MPB and checks it against the archived hash. Writes a JSON report and the 4 KiB preimage. | read only |
| 2 | `analyze_and_build_target.py` | Parses the archived configurations, replays the `mdadm` state rules, builds the repaired 584-byte configuration and shows the checksum and the field-level diff. | works on files |
| 3 | `field_diff.py` | Prints the field-level difference between the current configuration on each member and the target. | works on files |
| 4 | `apply_mpb_write.py <n> <serial>` | Dry run by default. Verifies identity, capacity, preimage hash **and** that the on-disk MPB is still the reviewed version, then shows exactly which bytes of the 4 KiB sector would change. | write-ACCESS handle, no write |
| 5 | `apply_mpb_write.py <n> <serial> --apply` | One 4 KiB read-modify-write with `FILE_FLAG_WRITE_THROUGH`, `FlushFileBuffers`, then a double read-back compared against the planned image, and an ATA identity re-check. | **writes 1 physical sector** |
| 6 | `verify_member_after_write.py <n> <serial>` | Independent process. Compares the whole last 64 KiB against the pre-write backup, proves every changed byte is inside the MPB sector, re-parses everything. | read only |
| 7 | `write_member.ps1 -Serial <S> [-Apply]` | Wrapper: finds the *unique* USB disk of the expected size, refuses if it has mounted volumes or wrong geometry, then calls the Python tool. | depends on `-Apply` |

Helpers, useful on their own:

| Script | Purpose |
|---|---|
| `dump_cfg.py <file>` | hex dump + fully decoded 584-byte configuration |
| `find_mpb.py` | locates the `Intel Raid ISM Cfg Sig.` signature and reports its exact disk offset / LBA / 4 KiB alignment |
| `inspect_tail.py` | shows how the two MPB sectors sit inside the last physical sector |
| `diagnose_head.py <n> <serial>` | compares the first 64 KiB of an attached disk against its archive, 4 KiB at a time |
| `read_identify.py` | decodes archived ATA `IDENTIFY` blobs (serial, model, firmware, LBA48 count) |

## Why the guards matter more than the patch

The patch itself is 15–22 bytes. Everything else in these files exists to make sure those bytes land on
the right disk, at the right offset, on top of the expected previous content:

- identity comes from **ATA `IDENTIFY`**, never from a device number or a USB bridge serial;
- the preimage hash must match the reviewed value — a disk that changed since review is refused;
- the on-disk configuration hash must match the reviewed baseline — a disk carrying a different
  generation is refused rather than "repaired";
- the write is one aligned 4 KiB operation, matching the physical sector size, so the drive never has
  to do a read-modify-write of a sector it thinks it is only half updating;
- read-back is compared byte for byte against the planned image, and the disk identity is re-checked
  afterwards.

Any failure aborts. None of them retries.

## Python

Written for CPython 3.11 on Windows. `ctypes` against `kernel32` only — no third-party packages, no
`pywin32`, no `dd`.
