# References

## Primary

### Intel — the disconnect / drive-drop advisory

<https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>

Intel article `000099952` describes specific SATA drive-drop states affecting certain RST branches and
points at a hotfix branch. Two conclusions from our case:

- **The fix is firmware-side.** The code that assembles your array at boot is the OROM inside the
  motherboard BIOS. Updating the Windows driver and the RST GUI changes the runtime I/O path only.
  A board whose BIOS ships OROM 19.5 will still assemble the array with 19.5 logic no matter what you
  install in Windows.
- **Consequently, only a BIOS update from your board vendor can deliver the real fix.** We did not find
  a downloadable, verifiable hotfix package for our board; we are not claiming one does not exist.

### `mdadm` IMSM implementation — the authoritative public description of this metadata

<https://raw.githubusercontent.com/md-raid-utilities/mdadm/main/super-intel.c>

The functions worth reading if you want to verify everything in
[02-imsm-metadata-format.md](02-imsm-metadata-format.md):

| Function | Why it matters |
|---|---|
| `struct imsm_super`, `imsm_disk`, `imsm_dev`, `imsm_vol`, `imsm_map` | the exact field layout used above, with `ASSERT_SIZE` checks |
| `__gen_imsm_checksum()` | the additive checksum, `mpb_size` bytes, minus the field itself |
| `mpb_sectors()`, `read_imsm_superblock()`, `store_imsm_mpb()` | the split anchor + extended placement and the write order |
| `serialcmp()` / `__serial_to_disk()` | member matching is a full 16-byte `strncmp` |
| `mark_failure()` / `mark_missing()` | the three markers: serial `+":0"`, `FAILED_DISK`, `scsi_id = ~0` |
| `imsm_count_failed()` / `imsm_check_degraded()` | how the volume state is derived from the members |
| `__prep_thunderdome()` | how conflicting copies from different members are resolved |
| `get_imsm_map()`, `get_imsm_ord_tbl_ent()` | `disk_ord_tbl` and the `IMSM_ORD_REBUILD` bit |

Reference file SHA-256 we worked against:
`9b01ef3756881d9719f754b96e7098085d3da250c4797c41ded3ee834f844d64`

> `mdadm` is a *compatibility* implementation, not Intel's code. It explains the format well enough to
> write it; it does not prove what a given Intel OROM will accept. Treat it as documentation, not as a
> guarantee.

### Linux kernel — RAID 5 and NTFS, for offline verification

- `drivers/md/raid5.c` <https://raw.githubusercontent.com/torvalds/linux/master/drivers/md/raid5.c>
  — parity layout and the left/right asymmetric rotation that produces `parity = 3 - (s % 4)` for a
  4-disk array.
- `fs/ntfs3/ntfs.h` <https://raw.githubusercontent.com/torvalds/linux/master/fs/ntfs3/ntfs.h>
  — on-disk NTFS structures used to validate that the reassembled volume really was a valid filesystem.
- `fs/ntfs3/fslog.c` <https://raw.githubusercontent.com/torvalds/linux/master/fs/ntfs3/fslog.c>
  — `$LogFile` record layout, used to interpret the differing log pages found in the samples.

## Background reading

- UEFI specification, GPT header and partition entry layout — used to confirm that the GPT found on a
  single member really was the volume's own first strip and not a leftover table.
- ATA-8 `IDENTIFY DEVICE` — word 10..19 serial (byte-swapped, space padded), word 60..61 LBA48 sector
  count, word 100..103 LBA48. This is how disk identity was pinned down through an anonymous USB bridge.
- `IOCTL_STORAGE_GET_DEVICE_NUMBER`, `IOCTL_DISK_GET_LENGTH_INFO`, `IOCTL_SCSI_PASS_THROUGH` — the
  Windows APIs used by the scripts to avoid ever trusting a device *number* on its own.

## Tools that helped, outside this repository

- `mdadm --examine` on a Linux box, given a raw image of one member, dumps the same fields and is
  independent of our scripts. If you can boot Linux, use it as a second opinion.
- Any hex editor that can open a raw physical device with a **read-only** handle, for eyeballing the
  last 4 KiB before you run anything.

## What we did *not* have

For the record, and to keep the honesty of the write-up:

- no full-disk image of any member
- no hardware write blocker (reads were done via `GENERIC_READ` handles, writes only by the explicit
  guarded tool)
- no replacement controller or spare disks to rehearse on
- no verified Intel hotfix package for this board

The recovery was done on the only copy of the data that existed.
