param(
 [Parameter(Mandatory=$true)][ValidateSet('VKH3B65X','VJGH3P3X','VKJGM9XX','VLK5JGVY')][string]$Serial,
 [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$expectedSize = 8001563222016

$cand = @(Get-Disk | Where-Object { [string]$_.BusType -eq 'USB' -and $_.Size -eq $expectedSize })
if ($cand.Count -ne 1) { throw "USB 目标盘不是唯一：找到 $($cand.Count) 块 8001563222016 字节的 USB 盘。同一时间只接一块 DATABASE 盘。" }
$d = $cand[0]
if ($d.IsBoot -or $d.IsSystem) { throw '目标盘是启动/系统盘，拒绝执行。' }
if ($d.LogicalSectorSize -ne 512 -or $d.PhysicalSectorSize -ne 4096) { throw "扇区几何异常：$($d.LogicalSectorSize)/$($d.PhysicalSectorSize)" }
if ([string]$d.PartitionStyle -ne 'RAW') { Write-Warning "PartitionStyle=$($d.PartitionStyle)（VLK5JGVY 写前为 RAW，若此处不是 RAW 请先告知）" }
$letters = @(Get-Partition -DiskNumber $d.Number -ErrorAction SilentlyContinue | Where-Object { $_.DriveLetter })
if ($letters.Count -gt 0) { throw "该盘有已挂载卷 $($letters.DriveLetter -join ','), 拒绝在原盘写入。" }

"TARGET_DISK=$($d.Number)  $($d.FriendlyName)  bus=$($d.BusType)  size=$($d.Size)  partitionStyle=$($d.PartitionStyle)"

$py = 'E:\AppData\Local\Programs\Python\Python311\python.exe'
$script = Join-Path $PSScriptRoot 'apply_mpb_write.py'
if ($Apply) { & $py $script $d.Number $Serial --apply } else { & $py $script $d.Number $Serial }
if ($LASTEXITCODE -ne 0) { throw "写入程序退出码 $LASTEXITCODE，未做任何重试。" }

$after = Get-Disk -Number $d.Number
if ([string]$after.BusType -ne 'USB' -or $after.Size -ne $expectedSize -or $after.Path -ne $d.Path) {
  throw '读取/写入期间 USB 设备映射发生变化。'
}
"DEVICE_MAPPING_STABLE_AFTER_RUN"
