# Intel RST / IMSM RAID 5: devolver al array un miembro degradado a `Non-RAID` (`Failed` → `Degraded` → `Rebuild`)

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | [Deutsch](README.de.md) | **Español** | [Русский](README.ru.md)

> Caso real y verificado: RAID 5 de Intel RST con 4 discos (volumen `DATABASE`, 24 TB).
> El firmware marcó el volumen como **Failed** y uno de los discos quedó en **`Non-RAID`**.
>
> Resultado: **`Failed` → `Degraded` → `Rebuild` → montado y legible.**
> Sin formatear, sin borrar el volumen, sin inicializar, y sin haber tenido nunca una copia completa.

---

## Resumen

El fallo era **únicamente de metadatos**. Cambiamos **22 bytes** dentro de **un solo sector físico de
4 KiB** al final del disco, y el firmware lo aceptó en el siguiente arranque.
En la zona de datos **no se tocó ni un byte**.

## ¿Para quién es esta página?

- [ ] Intel RST **RAID 5 con 4 discos**
- [ ] El volumen aparece como **`Failed`** en la pantalla RST de la BIOS y/o en la app RST de Windows
- [ ] **Solo uno** de los discos aparece como **`Non-RAID`**, o la app muestra una entrada fantasma de
      **0 bytes / estado «Perdido»**
- [ ] Su número de serie parece `TUSERIAL:0`, es decir el real con **`:0`** añadido
- [ ] No has inicializado, borrado ni «marcado como normal» el volumen

**El disco no está roto: lo que está mal escrito es su etiqueta (los metadatos).**

El controlador identifica los discos comparando el nombre **carácter por carácter**. Tras el incidente
la etiqueta dice `VLK5JGVY:0` y el disco dice `VLK5JGVY`, así que nunca volverán a coincidir.
Reconectar cables, actualizar la BIOS o cambiar el driver no sirve: el problema es **texto guardado en
el disco**.

## Síntoma

| Dónde | Qué se ve |
|---|---|
| BIOS / UEFI RST (OROM) | El volumen existe pero está `Failed`; el disco reconectado aparece como `Non-RAID` |
| GUI de RST en Windows | Entrada fantasma: **tamaño 0 Bytes, estado «Perdido», controlador/puerto desconocido**, serie con sufijo `:0` (p. ej. `VLK5JGVY:0`) |
| El disco en sí | Físicamente sano: `IDENTIFY` ATA, SMART y capacidad correctos |

## Causa

Intel RST guarda el **MPB** (MetaData Parameter Block) al **final de cada disco miembro**, con una
**copia completa de la descripción del array**. Cuando un disco desaparece, su registro no se borra:
se marca en **tres lugares a la vez**.

| Campo | Valor cuando falta el miembro | Significado |
|---|---|---|
| `disk[i].status` | `0x00000006` (`CONFIGURED \| FAILED`) | el slot existe pero está muerto |
| `disk[i].scsi_id` | `0xFFFFFFFF` | ubicación desconocida |
| `disk[i].serial` | serie real + **`:0`** | no debe coincidir con ningún disco físico |
| `map.disk_ord_tbl[slot]` | bit `0x01000000` activado | fuera de sincronía |

La comparación usa los **16 bytes del campo de serie** con `strncmp`: `"VLK5JGVY:0"` ≠ `"VLK5JGVY"`.
Por eso reconectar el cable o reiniciar no sirve **nunca**.

Además el estado se recalcula desde los miembros:

```
número de fallos = slots con bit FAILED O con IMSM_ORD_REBUILD
RAID5 con 1 -> Degraded  /  con 2 o más -> Failed
```

Aquí eran **dos** (el disco extraído y otro que llevaba horas desincronizado) → `Failed` permanente.

## Qué hicimos

1. Sacamos todos los discos del puerto del chipset (el controlador no interviene).
2. Leímos los últimos 64 KiB de cada disco **solo en lectura**, dos veces, comparando ambas y guardando SHA-256.
3. **Localizamos el MPB**: no es un bloque contiguo de 584 bytes.
   - ancla (bytes `0..511`) en `último LBA - 1`
   - parte extendida (bytes `512..583`) en los **primeros 72 bytes** de `último LBA - 2`
   - ambas dentro del **mismo sector físico de 4 KiB** → hay que hacer read-modify-write del sector completo.
4. Analizamos las cuatro copias con la tabla de campos del código público de `mdadm`.
   Tres eran idénticas y válidas (generación 763553); el disco extraído tenía una copia vieja (763509)
   con **checksum incorrecto**.
5. Construimos la configuración reparada desde la copia válida más reciente cambiando solo lo necesario:
   campo de serie → `"VLK5JGVY"`, `status` → `0x0000053a`, `scsi_id` → `0x00000000`,
   `disk_ord_tbl[2]` → `0x00000002`, `map_state` → `2`, `generation_num` → `763554`, checksum recalculado.
   **Sin tocar:** family, ID/nombre/tamaño del volumen, número de miembros, nivel RAID, stripe,
   inicio de datos, `failed_disk_num`, los registros de los otros discos y la marca de desincronización
   del miembro que realmente se quedó atrás.
6. Escribimos la **misma** configuración de 584 bytes en **todos** los miembros restantes
   (un RMW de 4 KiB por disco), dejando todas las copias **idénticas byte a byte**.
7. Releímos y verificamos: sector completo, checksum e identidad del disco.

Cambios: **22 bytes** en el disco extraído y **15 bytes** en cada uno de los otros dos, siempre dentro
del sector de metadatos al final del disco.

## Resultado

| Fase | Observación |
|---|---|
| Antes | `Failed`, `VLK5JGVY` = `Non-RAID`, entrada fantasma `VLK5JGVY:0`, `0 Bytes` |
| Arranque con solo los 3 discos reparados | **`Degraded`**, `VLK5JGVY` vuelve como miembro, falta `VKJGM9XX` |
| Reconnectar el disco desincronizado | **`Rebuild`** se inicia automáticamente |
| Windows | Volumen de 24 004 676 026 368 bytes, **Healthy / OK**, montado, archivos legibles |

<img src="docs/images/rst-rebuild-progress.jpg" alt="RST reconstruyendo el volumen DATABASE">

*El mismo array después: los cuatro miembros de 7452 GB presentes, `DATABASE` de nuevo como RAID 5 de
22 356 GB, **estado: reconstrucción 9 %**. La entrada fantasma `0 Bytes / Perdido` ya no está.*

## Advertencias

1. **Si te equivocas es irreversible.** No hay copia de seguridad.
2. **Nunca escribas un bloque crudo de 584 bytes**; trabaja siempre con el sector completo de 4 KiB.
3. **Nunca pongas el volumen en `Normal`.** `Normal` afirma que todos los miembros están sincronizados;
   si uno está atrasado, devolverá **datos antiguos en silencio** y todas las comprobaciones estructurales
   pasarán igualmente. Hasta un rebuild real, `Degraded` es el único estado honesto.
4. **No dejes que Windows monte en escritura** antes de verificar: NTFS reproducirá su journal.
   Usa `mountvol /N` o `Set-Disk -IsReadOnly $true`.
5. No ejecutes `chkdsk /f` antes de copiar los datos importantes.
6. No lo intentes repetidamente: cada entrada en el OROM del RST puede reescribir metadatos.
7. La capacidad y el tamaño de sector cambian según el modelo: **recalcula, nunca copies números.**

## Referencias

- Aviso de Intel (origen del problema): <https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>
- Implementación IMSM de `mdadm`: <https://raw.githubusercontent.com/md-raid-utilities/mdadm/main/super-intel.c>
- Detalles: [docs/03-procedure.md](docs/03-procedure.md), [docs/02-imsm-metadata-format.md](docs/02-imsm-metadata-format.md)

## Firmware

Actualizar el driver o la GUI de RST **en Windows** no cambia cómo se ensambla el array al arrancar.
El **OROM dentro de la BIOS** es quien enumera los discos, decide el estado y escribe metadatos primero.
Por eso esta reparación usa el formato MPB `1.3.00`, que los OROM 19.x entienden de forma nativa, y por eso
la corrección real del fallo de desconexión de Intel solo puede llegar como actualización de BIOS del fabricante.

## Licencia

MIT — ver [LICENSE](LICENSE). Números de serie, modelos y geometría se publican con autorización expresa
del propietario.
