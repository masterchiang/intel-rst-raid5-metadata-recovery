# Intel RST RAID5：成員磁碟顯示 Non-RAID 時的復原方法

[简体中文](README.md) | **繁體中文** | [English](README.en.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md) | [Português](README.pt-BR.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Русский](README.ru.md)

## 問題的性質

這是 Intel RST 已公開的普遍問題，不是個案。

Intel 官方支援文章 **000099952** 記錄了 Intel RST 在特定條件下遺失 SATA 磁碟的問題：磁碟從系統中消失、
陣列降級或進入失敗狀態、重新接入後無法回到陣列。影響範圍是所有使用 Intel RST / VMD 的機器。
<https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>

開機時列舉磁碟、判定陣列狀態、寫入中繼資料的是 **BIOS 內建的 RST OROM**，不是 Windows 驅動程式。
因此有效的修正需要主機板廠商在 BIOS 中更新 RST 模組，Windows 端升級無法取代，多數主機板目前仍內建 19.x。

在此已知缺陷下，會反覆出現一種可復原的故障形態：

- 磁碟本身完好，SMART 正常
- 其餘成員資料完好
- 但該磁碟被固件標記為「遺失」，介面顯示 `Non-RAID`，或顯示為 0 位元組、狀態「遺失」的幽靈記錄
- 重插排線、換埠、重開機、刷 BIOS、升級驅動皆無效

本文說明這類情況的處理方式。由於涉及直接修改磁碟中繼資料，操作前請完整閱讀「注意」一節。

## 適用範圍

先分成三種情況，只有第一種適用本文方法。

| 情況 | 判別依據 | 處理方式 |
|---|---|---|
| 一、成員記錄錯誤，資料區完好 | 卷狀態 `Failed`；僅一塊成員顯示 `Non-RAID`、或存在 0 位元組「遺失」記錄；該記錄序號帶 `:0` 後綴；未執行過「標記為正常」 | 本文方法，修復成員記錄 |
| 二、卷已刪除或重建，但資料區未被覆寫 | 刪除卷、重新建立卷通常只重寫中繼資料，不清零整卷 | 本文方法不適用；資料仍可救回，可重建描述元或離線重組 |
| 三、資料區已被覆寫 | 執行過完整初始化、或在錯誤方向執行過重建 | 超出本文範圍，需專業資料救援 |

判別重點是**資料區有沒有被寫過**，而不是「卷物件還在不在」。卷物件消失不等於資料消失；
反過來說，卷物件還在但資料區被錯誤重建覆寫過，情況更糟。

## 原因

Intel 在每一塊成員磁碟末端寫入一份描述整個陣列的中繼資料區塊（本案例 584 位元組）。
磁碟離線時，控制器不會刪除其記錄，而是在三個欄位同時標記：

| 欄位 | 正常 | 離線後 |
|---|---|---|
| 序號欄位 | `VLK5JGVY` | `VLK5JGVY:0`（追加 `:0`） |
| status | `0x0000053A` | `0x00000006`（CONFIGURED │ FAILED） |
| scsi_id | 實際位置 | `0xFFFFFFFF` |

成員識別採用 16 位元組序號欄位的完全相等比較。記錄寫的是 `VLK5JGVY:0`，磁碟自報的是 `VLK5JGVY`，
兩者不相等，因此無法再匹配。字串存在磁碟上，所以重插排線或升級驅動都不會改變結果。

卷狀態由失敗槽位數推算：RAID5 失敗 1 個為 `Degraded`，2 個以上為 `Failed`。

## 方法

1. 將所有成員從主機板拆下，一次只透過 USB 接一塊，避免控制器介入。
2. 每塊磁碟末端 64 KiB 讀兩遍、留存雜湊備份，全程只讀。
3. 從最後 4 KiB 切出 584 位元組中繼資料並解析，四塊並排比對，找出最新且校驗正確的那一份。
4. 在記憶體中修正：序號欄位還原、清除該成員的 FAILED 與失步位、卷狀態改為 `Degraded`、
   世代號加一、重算校驗和；其餘欄位不動。
5. 將同一份中繼資料寫入所有存活成員，使各副本位元組一致。
6. 只接回已修復的成員開機，進入 BIOS RST 檢視是否為 `Degraded`。

```powershell
python scripts\verify_present_state_readonly.py <磁碟號> <ATA序號>
python scripts\dump_cfg.py samples\VLK5JGVY_IMSM_configuration.bin
python scripts\apply_mpb_write.py <磁碟號> <ATA序號>          # 試執行
python scripts\apply_mpb_write.py <磁碟號> <ATA序號> --apply  # 寫入
```

## 結果

本案例中，寫入三塊成員各 22、15、15 位元組（皆位於磁碟末端的中繼資料扇區，資料區 0 位元組），
BIOS 随即顯示 `Degraded`，成員重新入組；接回失步成員後進入重建，完成後卷在 Windows 下正常掛載，
容量 24 004 676 026 368 位元組，與中繼資料記錄一致。

## 注意

1. 沒有撤銷。操作前必須留存前像。
2. 絕不可直接寫入 584 位元組的連續區塊，須以整個 4 KiB 實體扇區為單位讀─改─寫。
3. 不可將卷設為 `Normal`。若某成員確實落後，`Normal` 會讓讀取靜默回傳舊資料。
4. 驗證前不要讓 Windows 以可寫方式掛載；先 `mountvol /N` 或 `Set-Disk -IsReadOnly $true`。
5. 重要資料複製出來之前不要執行 `chkdsk /f`。
6. 不要照抄本文的位移量，須依實際容量與扇區大小重新計算。

## 參考

- Intel 支援文章 000099952：<https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>
- mdadm IMSM 實作：<https://raw.githubusercontent.com/md-raid-utilities/mdadm/main/super-intel.c>
- 完整流程與欄位表見 [docs/03-procedure.md](docs/03-procedure.md)、[docs/02-imsm-metadata-format.md](docs/02-imsm-metadata-format.md)

## 授權

MIT，見 [LICENSE](LICENSE)。
