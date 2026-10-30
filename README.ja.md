# Intel RST / IMSM RAID 5：`Non-RAID` に落ちたメンバーディスクを配列へ戻す（`Failed` → `Degraded` → `Rebuild`）

[简体中文](README.md) | [繁體中文](README.zh-TW.md) | [English](README.en.md) | **日本語** | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md) | [Português](README.pt-BR.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Русский](README.ru.md)

## 問題の性質

これは Intel RST の公開された一般的な問題であり、個別の事例ではありません。

Intel のサポート記事 **000099952** は、Intel RST が特定条件下で SATA ディスクを失う問題を記載しています。
ディスクがシステムから消え、アレイが劣化または失敗状態になり、再接続しても復帰しません。
対象は Intel RST / VMD を使用するすべてのマシンです。
<https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>

起動時のディスク列挙、アレイ状態の判定、メタデータの書き込みは **BIOS 内蔵の RST OROM** が行います。
したがって有効な修正はマザーボードベンダーによる BIOS 更新であり、Windows 側のドライバ更新では代替できません。

> 4 台構成 Intel RST RAID 5（ボリューム名 `DATABASE`、24 TB）の実例です。
> ファームウェアがボリュームを **Failed** と判定し、1 台のメンバーが **`Non-RAID`** のままでした。
>
> 結果：**`Failed` → `Degraded` → `Rebuild` → マウント成功、ファイル読み出し可。**
> フォーマット・ボリューム削除・初期化は一切なし。全ディスクのバックアップも存在しませんでした。

---

## 要点

故障は**メタデータだけの問題**でした。ディスクの**最後尾にある 1 つの 4 KiB 物理セクタ**のうち
**22 バイト**を書き換えただけで、次回起動時にファームウェアが受け付けました。

データ領域には**1 バイトも触れていません**。

## このページは誰のためのものか

- [ ] Intel RST の **RAID 5（4 台構成）**
- [ ] BIOS の RST 画面や Windows の RST アプリでボリュームが **`Failed`**
- [ ] **1 台だけ**が **`Non-RAID`**、または RST アプリに **サイズ 0 バイト／状態「失われた」** という幽霊エントリがある
- [ ] そのエントリのシリアルが `あなたのシリアル:0` になっている（**`:0` が 2 文字追加されている**）
- [ ] 初期化・削除・「正常としてマーク」をしていない

ディスク自体に異常はありません。問題はメタデータ内の識別文字列です。コントローラは 16 バイトのシリアル欄を
完全一致で比較します。障害後、記録は `VLK5JGVY:0`、ディスクは `VLK5JGVY` を返すため一致しません。
ケーブルの入れ直しや BIOS／ドライバの更新では解決しません。

## 症状

| 場所 | 表示 |
|---|---|
| BIOS / UEFI の RST (OROM) | ボリュームは存在するが `Failed`。戻したディスクは `Non-RAID` |
| Windows の RST GUI | **サイズ 0 Bytes、状態「失われた」、コントローラ/ポート不明**、シリアルに `:0` が付く（例 `VLK5JGVY:0`） |
| ディスク自体 | 物理的には健全。ATA `IDENTIFY`、SMART、容量すべて正常 |

## 原因

Intel RST は **MPB**（MetaData Parameter Block）を**各メンバーの末尾**に書き、そこに
**配列全体の記述**を保持します。ディスクが消えると、記録は削除されず**3 か所に印**が付きます。

| フィールド | 欠落時の値 | 意味 |
|---|---|---|
| `disk[i].status` | `0x00000006` (`CONFIGURED \| FAILED`) | スロットは存在するが死んでいる |
| `disk[i].scsi_id` | `0xFFFFFFFF` | 所在不明 |
| `disk[i].serial` | 実シリアル + **`:0`** | 物理ディスクと照合させない |
| `map.disk_ord_tbl[slot]` | ビット `0x01000000` をセット | 同期外れ |

メンバー照合は **16 バイトのシリアル欄を `strncmp` で完全一致**比較します。
`"VLK5JGVY:0"` ≠ `"VLK5JGVY"` なので、ケーブルを何度挿し直しても永久に紐付きません。

さらにボリューム状態はメンバーから再計算されます：

```
失敗数 = FAILED ビットが立つスロット + IMSM_ORD_REBUILD が立つスロット
RAID5 で 1 個 -> Degraded ／ 2 個以上 -> Failed
```

本件は**2 個**該当（抜かれたディスク＋数時間前に同期外れになったディスク）ため `Failed` のままでした。

## 実施内容

1. すべてのメンバーをマザーボードから外す（ファームウェアに触らせない）。
2. USB-SATA ブリッジ経由で各ディスク末尾 64 KiB を**読み取り専用**で 2 回読み、一致を確認、SHA-256 保存。
3. **MPB の位置**：連続した 584 バイトではありません。
   - アンカー（設定バイト `0..511`）＝ 最終 LBA の 1 つ前
   - 拡張部（設定バイト `512..583`）＝ 最終 LBA の 2 つ前の**先頭 72 バイト**
   - 両者は**同一の 4 KiB 物理セクタ**内 → セクタ単位の read-modify-write が必須。
4. 公開 `mdadm` の構造体定義で 4 コピーすべてを解析。3 コピーは同一・チェックサム正常（世代 763553）、
   抜かれたディスクは古い世代 763509 かつ**チェックサム不正**。
5. 最新の正常コピーを基に修復版を構築。変更点のみ：
   - シリアル欄 `"VLK5JGVY:0"` → `"VLK5JGVY"`（+NUL+固有サフィックス）
   - `status` `0x00000006` → `0x0000053a`（FAILED をクリア、健全メンバーのフラグは維持）
   - `scsi_id` `0xFFFFFFFF` → `0x00000000`（そのディスク自身が過去に持っていた値）
   - `disk_ord_tbl[2]` `0x01000002` → `0x00000002`（`IMSM_ORD_REBUILD` をクリア）
   - `map_state` `3` → `2`
   - `generation_num` `763553` → `763554`
   - チェックサム再計算
   - **不可触**：family、ボリューム ID/名前/サイズ、メンバー数、RAID レベル、ストライプ、
     データ開始位置、`failed_disk_num`、他メンバーの記録、本当に同期外れだったメンバーのフラグ。
6. 残った全メンバーに**同一の 584 バイト設定**を書き込み（各 1 回の 4 KiB read-modify-write）、
   すべてのコピーを**バイト単位で一致**させる。
7. セクタ全体・チェックサム・ディスク同一性を読み戻して検証。

変更量：**抜かれたディスク 22 バイト、他 2 台は各 15 バイト**。すべてメタデータセクタ内。

## 結果

| 段階 | 観測 |
|---|---|
| 修復前 | `Failed`、`VLK5JGVY` は `Non-RAID`、幽霊エントリ `VLK5JGVY:0` / `0 Bytes` |
| 3 台のみで起動 | **`Degraded`**、`VLK5JGVY` がメンバーに復帰、欠落は `VKJGM9XX` |
| 同期外れの 1 台を戻す | **`Rebuild`** が自動開始 |
| Windows | 24 004 676 026 368 バイトのボリュームが **Healthy / OK**、マウント成功、ファイル正常 |

<img src="docs/images/rst-rebuild-progress.jpg" alt="RST による DATABASE ボリュームの再構築">

*修復後の同じ配列：7452 GB のメンバー 4 台が揃い、`DATABASE` は RAID 5 / 22 356 GB に復帰、
**状態：再構築 9%**。`0 Bytes / 失われた` の幽霊エントリは消えています。*

## 警告

1. **失敗すれば不可逆**。バックアップはありません。
2. **584 バイトの生ブロブを直接書かない**。必ず 4 KiB セクタ単位で。
3. **`Normal` にしてはいけない**。`Normal` は「全メンバー同期済み」という主張であり、
   実際に古いメンバーがあると**静かに古いデータを返します**。再構築が終わるまで `Degraded` が唯一の正直な状態。
4. 検証前に Windows へ**書き込み可能でマウントさせない**（NTFS がジャーナルを再生します）。
   `mountvol /N` か `Set-Disk -IsReadOnly $true` を使用。
5. 重要データを退避する前に `chkdsk /f` を実行しない。
6. 何度も試さない。RST OROM に入るたびにメタデータが書き換わる可能性があります。
7. 容量・セクタサイズは機種ごとに違います。**数値をコピーせず再計算してください。**

## 参照

- Intel 公式情報（本件の発端）：<https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>
- `mdadm` IMSM 実装：<https://raw.githubusercontent.com/md-raid-utilities/mdadm/main/super-intel.c>
- 詳細： [docs/03-procedure.md](docs/03-procedure.md)、[docs/02-imsm-metadata-format.md](docs/02-imsm-metadata-format.md)

## ファームウェアについて

**Windows** 側の RST ドライバ／GUI を更新しても、起動時の配列組み立ては変わりません。
最初にディスクを列挙し状態を判定しメタデータを書くのは **BIOS 内の OROM** です。
だからこそ本修復は 19.x OROM が解釈できる `1.3.00` MPB 形式を対象にしており、
Intel の切断問題の根本修正はマザーボードベンダーの BIOS 更新でしか提供されません。

## ライセンス

MIT（[LICENSE](LICENSE)）。シリアル・型番・ジオメトリは所有者の明示的な同意の下で公開しています。
