# Intel RST / IMSM RAID 5: Ein auf `Non-RAID` zurückgefallenes Mitglied wieder in das Array bringen (`Failed` → `Degraded` → `Rebuild`)

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | **Deutsch** | [Español](README.es.md) | [Русский](README.ru.md)

> Ein realer, verifizierter Fall: 4-Platten-Intel-RST-RAID-5 (Volume `DATABASE`, 24 TB).
> Die Firmware hatte das Volume als **Failed** eingestuft, eine Platte blieb auf **`Non-RAID`**.
>
> Ergebnis: **`Failed` → `Degraded` → `Rebuild` → eingebunden und lesbar.**
> Kein Formatieren, kein Löschen des Volumes, keine Initialisierung — und nie ein vollständiges Backup.

---

## Kurzfassung

Der Fehler war **rein metadatenseitig**. Wir haben **22 Bytes** in **einem 4-KiB-Sektor** ganz am Ende
der Platte geändert — beim nächsten Start hat die Firmware das Array akzeptiert.
Im Datenbereich wurde **kein einziges Byte** verändert.

## Symptom

| Ort | Anzeige |
|---|---|
| BIOS / UEFI RST (OROM) | Volume vorhanden, aber `Failed`; die zurückgesteckte Platte erscheint als `Non-RAID` |
| Windows RST GUI | Geistereintrag: **Größe 0 Bytes, Status „Verloren", Controller/Port unbekannt**, Seriennummer mit `:0` (z. B. `VLK5JGVY:0`) |
| Die Platte selbst | Physisch gesund. ATA `IDENTIFY`, SMART und Kapazität sind korrekt |

## Ursache

Intel RST schreibt den **MPB** (MetaData Parameter Block) an das **Ende jeder Mitgliedsplatte**.
Jede Kopie enthält die **komplette Array-Beschreibung**. Verschwindet eine Platte, wird ihr Eintrag
nicht gelöscht, sondern an **drei Stellen** markiert:

| Feld | Wert bei fehlendem Mitglied | Bedeutung |
|---|---|---|
| `disk[i].status` | `0x00000006` (`CONFIGURED \| FAILED`) | Slot existiert, ist aber tot |
| `disk[i].scsi_id` | `0xFFFFFFFF` | Position unbekannt |
| `disk[i].serial` | echte Seriennummer + **`:0`** | darf nicht mit einer echten Platte übereinstimmen |
| `map.disk_ord_tbl[slot]` | Bit `0x01000000` gesetzt | nicht synchron |

Die Zuordnung vergleicht das **16-Byte-Serienfeld** per `strncmp` — `"VLK5JGVY:0"` ≠ `"VLK5JGVY"`.
Deshalb lässt sich die Platte durch Umstecken oder Neustarts **niemals** wieder zuordnen.

Der Volume-Status wird aus den Mitgliedern berechnet:

```
Fehleranzahl = Slots mit FAILED-Bit ODER mit IMSM_ORD_REBUILD
RAID5 mit 1 -> Degraded  /  2 oder mehr -> Failed
```

Hier waren es **zwei** (die entfernte Platte und eine Stunden zuvor desynchronisierte) → dauerhaft `Failed`.

## Was wir gemacht haben

1. Alle Mitgliedsplatten vom Mainboard getrennt (kein Controller-Zugriff).
2. Über eine USB-SATA-Brücke die letzten 64 KiB **nur lesend** zweimal gelesen, verglichen, SHA-256 gesichert.
3. **MPB auf der Platte gefunden** — kein zusammenhängender 584-Byte-Block:
   - Anker (Konfig-Bytes `0..511`) bei `letztes LBA - 1`
   - Erweiterung (Bytes `512..583`) in den **ersten 72 Bytes** von `letztes LBA - 2`
   - beides im **selben 4-KiB-Sektor** → Read-Modify-Write des ganzen Sektors.
4. Alle vier Kopien mit der Feldtabelle aus dem öffentlichen `mdadm`-Quelltext geparst:
   drei identisch und gültig (Generation 763553), die entfernte Platte alt (763509) mit **falscher Prüfsumme**.
5. Reparierte Konfiguration aus der neuesten gültigen Kopie gebaut, nur das Nötige geändert:
   Serienfeld → `"VLK5JGVY"`, `status` → `0x0000053a`, `scsi_id` → `0x00000000`,
   `disk_ord_tbl[2]` → `0x00000002`, `map_state` → `2`, `generation_num` → `763554`, Prüfsumme neu.
   **Unberührt:** Family, Volume-ID/Name/Größe, Mitgliederzahl, RAID-Level, Stripe, Datenstart,
   `failed_disk_num`, die Einträge der anderen Platten und die Desync-Markierung der wirklich veralteten Platte.
6. Dieselbe 584-Byte-Konfiguration auf **alle verbliebenen** Platten geschrieben (je ein 4-KiB-RMW),
   sodass alle Kopien **byte-identisch** sind.
7. Zurückgelesen und geprüft: ganzer Sektor, Prüfsumme, Plattenidentität.

Änderungen: **22 Bytes** auf der entfernten Platte, **je 15 Bytes** auf den beiden anderen — ausschließlich
im Metadaten-Sektor am Plattenende.

## Ergebnis

| Phase | Beobachtung |
|---|---|
| Vorher | `Failed`, `VLK5JGVY` = `Non-RAID`, Geistereintrag `VLK5JGVY:0`, `0 Bytes` |
| Start mit nur den 3 reparierten Platten | **`Degraded`**, `VLK5JGVY` wieder Mitglied, fehlend: `VKJGM9XX` |
| Desynchronisierte Platte wieder angesteckt | **`Rebuild`** startet automatisch |
| Windows | Volume mit 24 004 676 026 368 Bytes, **Healthy / OK**, eingebunden, Dateien lesbar |

<img src="docs/images/rst-rebuild-progress.jpg" alt="RST baut das DATABASE-Volume neu auf">

*Dasselbe Array danach: vier Mitglieder mit 7452 GB vorhanden, `DATABASE` wieder RAID 5 mit 22 356 GB,
**Status: Neuaufbau 9 %**. Der Geistereintrag `0 Bytes / Verloren` ist verschwunden.*

## Warnungen

1. **Bei Fehlern ist es irreversibel.** Es gibt kein Backup.
2. **Niemals einen nackten 584-Byte-Block schreiben** — immer den kompletten 4-KiB-Sektor.
3. **Das Volume niemals auf `Normal` setzen.** `Normal` behauptet, alle Mitglieder seien synchron;
   ist eine Platte veraltet, liefert sie **still veraltete Daten** — alle Strukturprüfungen bestehen trotzdem.
   Bis ein echter Rebuild gelaufen ist, ist `Degraded` der einzige ehrliche Zustand.
4. Windows vor der Prüfung **nicht beschreibbar** einbinden (`mountvol /N` oder `Set-Disk -IsReadOnly $true`),
   sonst spielt NTFS sein Journal zurück.
5. Kein `chkdsk /f`, bevor wichtige Daten kopiert sind.
6. Nicht mehrfach „probieren": jeder Besuch im RST-OROM kann Metadaten schreiben.
7. Kapazität und Sektorgröße sind modellabhängig — **Werte neu berechnen, niemals kopieren.**

## Referenzen

- Intel-Hinweis (Auslöser des Problems): <https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>
- `mdadm` IMSM-Implementierung: <https://raw.githubusercontent.com/md-raid-utilities/mdadm/main/super-intel.c>
- Details: [docs/03-procedure.md](docs/03-procedure.md), [docs/02-imsm-metadata-format.md](docs/02-imsm-metadata-format.md)

## Firmware

Ein Update des **Windows**-RST-Treibers/GUI ändert nichts an der Zusammensetzung beim Start.
Zuerst läuft das **OROM im BIOS**: es zählt Platten, bewertet das Array und schreibt Metadaten.
Deshalb zielt diese Reparatur auf das `1.3.00`-MPB-Format, das 19.x-OROMs nativ verstehen — und deshalb
kann die eigentliche Behebung des Intel-Verbindungsfehlers nur als BIOS-Update des Mainboard-Herstellers kommen.

## Lizenz

MIT — siehe [LICENSE](LICENSE). Seriennummern, Modelle und Geometrie sind mit ausdrücklicher
Genehmigung des Eigentümers veröffentlicht.
