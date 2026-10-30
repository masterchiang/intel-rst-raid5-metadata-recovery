# Reference machine

Published with the owner's permission. If you are matching your own case against this one, the
serial numbers are what matter — they are how the metadata identifies a member.

## Platform

| Item | Value |
|---|---|
| CPU | Intel Core i5-13600KF |
| Motherboard | Colorful CVN Z790D5 GAMING FROZEN V20 |
| BIOS | version 1009, dated 2023-08-23 (never flashed during this recovery) |
| Chipset storage mode | Intel VMD enabled — **do not** turn it off; other volumes depend on it |
| VMD hardware IDs | `A77F`, `09AB` |
| Storage driver when the incident happened | Intel RST `19.5.2.1049` |
| Storage driver later installed | Intel RST `20.2.1.1016` (changed nothing about boot-time assembly) |
| RST GUI | `20.0.1024.0` |
| **OROM embedded in BIOS** | **19.5** — this is the code that actually assembles the array at boot |
| OS | Windows 10 Pro 22H2, build 19045 |

The driver/GUI version is listed for completeness. It had **no effect** on whether the array was
recognised; that is decided by the OROM before Windows starts.

## Volumes on the machine

| Volume | Name | Layout | Note |
|---|---|---|---|
| System | `SYSTEM` | 2× SSD, RAID 1 | holds `C:` and `D:`; both later showed `Warning / Scan Needed`, pre-existing and unrelated |
| Work | `MAIN` | 4× NVMe, RAID 5 (~2.8 TB) | unrelated |
| **Affected** | **`DATABASE`** | **4× HDD, RAID 5, 24 TB** | the array in this case |

## The affected array

| Property | Value |
|---|---|
| RAID level | 5 |
| Members | 4 |
| Strip size | 256 × 512 B = **128 KiB** |
| Layout | left-asymmetric; parity member for stripe `s` = `3 - (s % 4)` |
| Data start on member | LBA 0 |
| Volume size | 46 884 132 864 sectors = **24 004 676 026 368 bytes** |
| `family_num` | `0x0345F4B5` |
| `orig_family_num` | `0x000001DE` |
| MPB signature | `Intel Raid ISM Cfg Sig. 1.3.00` |
| MPB size | 584 bytes |
| `attributes` | `0xA4000010` |
| Blocks per member | 15 628 046 336 (data stripes × 256 + 2048 reserved) |

### Members

| Label | ATA serial | Logical slot | Model | Firmware | Post-incident SATA port |
|---|---|---:|---|---|---:|
| A | `VKJGM9XX` | 1 | HGST HUH728080ALE600 | A4GNT7JD | 2 |
| B | `VLK5JGVY` | 2 | HGST HUH728080ALE601 | A4GL0003 | 4 |
| C | `VKH3B65X` | 0 | HGST HUH728080ALE600 | A4GNT7JD | 5 |
| D | `VJGH3P3X` | 3 | HGST HUH728080ALE601 | A4GL0003 | 3 |

All four: 8 001 563 222 016 bytes, 15 628 053 168 × 512 B sectors,
**512-byte logical / 4096-byte physical** sectors, LBA48, 7200 rpm.

> **SATA port is not the logical slot.** The controller's port numbers and the RAID member order are
> completely independent. Do not infer slot order from ports, from USB device order, or from old
> Windows disk numbers.

## The USB bridge

| Property | Value |
|---|---|
| Enclosure | Shenzhen YongzhenWeiye (generic USB-SATA bridge) |
| Bridge serial reported by Windows | `DD564198338A1` |
| Pass-through of ATA `IDENTIFY` | works (SATA-III UAS @ Oxford chipset) |

> The bridge serial is **not** the disk serial. Always confirm identity with ATA `IDENTIFY`, never with
> `Get-Disk | Select SerialNumber`.

## What happened, physically

1. The machine was moved. The SATA connector on member **A** came loose.
2. The array went `Degraded` and kept running with three members for several hours.
3. On shutdown the cable of member **B** was accidentally pulled.
4. **A** was reconnected. Now two slots had problems → the firmware marked the volume **`Failed`**.
5. No rebuild ever ran. **B** was reconnected later but showed up as `Non-RAID`, with a phantom
   `VLK5JGVY:0` record of size 0.

That order matters: it is *B*, the disk pulled last, that is still fully in sync; it is *A*, the disk
that missed hours of writes, that is genuinely stale. The metadata in the baseline copy said exactly
this — A out of sync, B missing — which is why the repair restored B and left A marked out of sync.
