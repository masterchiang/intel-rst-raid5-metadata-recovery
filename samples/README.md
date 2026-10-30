# Real 584-byte IMSM configurations from this case

Cut out of the last 4 KiB physical sector of each member, exactly as described in
[../docs/02-imsm-metadata-format.md](../docs/02-imsm-metadata-format.md):

```python
cfg = sector[3072:3072+512] + sector[2560:2560+72]
```

| File | Member | Generation | Checksum | Volume state inside |
|---|---|---:|---|---|
| `VKH3B65X_IMSM_configuration.bin` | C, slot 0 | 763553 | valid | failed |
| `VKJGM9XX_IMSM_configuration.bin` | A, slot 1 | 763553 | valid | failed |
| `VJGH3P3X_IMSM_configuration.bin` | D, slot 3 | 763553 | valid | failed |
| `VLK5JGVY_IMSM_configuration.bin` | B, slot 2 — the disk that was `Non-RAID` | 763509 | **invalid** | degraded |
| `target_repaired_763554.bin` | what was written to all three survivors | 763554 | valid | degraded |

SHA-256:

```
b3c6013dee1ace62fb7a4b06ad2dbe6eb7e944d1f7e0b73e8ab1924302412f47  VKH3B65X_IMSM_configuration.bin
b3c6013dee1ace62fb7a4b06ad2dbe6eb7e944d1f7e0b73e8ab1924302412f47  VKJGM9XX_IMSM_configuration.bin
b3c6013dee1ace62fb7a4b06ad2dbe6eb7e944d1f7e0b73e8ab1924302412f47  VJGH3P3X_IMSM_configuration.bin
43c02ffb75553d39eac93234179b0152e350a024940adf81fb20d34951be6425  VLK5JGVY_IMSM_configuration.bin
a773a7513c17ba35d5a1b58d6e9f06fe93094e0e6b1e628362bd3f9d92dcb36b  target_repaired_763554.bin
```

Three files being byte-identical is the whole point: the three survivors agreed with each other, and
disagreed with the disk that had been ejected.

## What is inside these 584 bytes, and what is not

Inside: array family, generation, member order, member serials, per-member status and geometry,
volume name and size, strip size, RAID level, and the volume state.

Not inside: **any file or file-system content.** No partitions, no file names, no user data.
These are safe to publish and safe to inspect.

## Using them to learn the format

```bash
python ../scripts/dump_cfg.py VLK5JGVY_IMSM_configuration.bin
python ../scripts/field_diff.py      # field-level diff of the first four against the target
```

The `VLK5JGVY` file is the most instructive one: it is the disk describing itself as `FAILED`
(`status 0x053E`) while also believing the *other* disk is missing (`0xFFFFFFFF`, serial `":1"`).
Both members could not have been more wrong about each other.
