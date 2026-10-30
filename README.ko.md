# Intel RST RAID5: 구성원 디스크가 Non-RAID로 표시될 때의 복구 방법

[简体中文](README.md) | [繁體中文](README.zh-TW.md) | [English](README.en.md) | [日本語](README.ja.md) | **한국어** | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md) | [Português](README.pt-BR.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Русский](README.ru.md)

## 어떤 문제인가

개별 사례가 아니라 Intel RST의 공개된 일반적인 문제입니다.

Intel 지원 문서 **000099952**는 특정 조건에서 Intel RST가 SATA 디스크를 잃는 문제를 설명합니다.
디스크가 시스템에서 사라지고, 배열이 저하 또는 실패 상태가 되며, 다시 연결해도 배열로 돌아오지 않습니다.
Intel RST / VMD를 사용하는 모든 시스템이 대상입니다.
<https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>

부팅 시 디스크 열거, 배열 상태 판정, 메타데이터 기록은 **BIOS에 내장된 RST OROM**이 수행합니다.
따라서 실질적인 수정은 메인보드 제조사의 BIOS 업데이트로만 가능하며, Windows 측 드라이버 업데이트로는
대체할 수 없습니다. 대부분의 보드는 여전히 19.x OROM을 내장하고 있습니다.

이 결함 아래에서 반복적으로 나타나는 복구 가능한 형태가 있습니다.

- 디스크 자체는 정상이고 SMART도 깨끗함
- 나머지 구성원의 데이터는 온전함
- 그러나 해당 디스크가 "누락"으로 표시되어 `Non-RAID`로 보이거나, 0바이트·상태 "손실"인 유령 항목으로 표시됨
- 케이블 재연결, 포트 변경, 재부팅, BIOS 업데이트, 드라이버 업데이트 모두 효과 없음

이 문서는 그 경우의 처리 방법을 설명합니다. 디스크 메타데이터를 직접 수정하므로 작업 전에
"주의" 항목을 모두 읽어야 합니다.

## 적용 범위

세 가지로 나누어 판단하며, 첫 번째 경우에만 이 방법을 사용합니다.

| 경우 | 판별 기준 | 처리 |
|---|---|---|
| 1. 구성원 기록 오류, 데이터 영역 온전 | 볼륨이 `Failed`; 구성원 하나만 `Non-RAID` 또는 0바이트 "손실" 항목; 해당 일련번호에 `:0` 접미사; "정상으로 표시"를 실행한 적 없음 | 이 문서의 방법으로 구성원 기록 복구 |
| 2. 볼륨을 삭제·재생성했으나 데이터 영역 미덮어쓰기 | 볼륨 삭제/재생성은 보통 메타데이터만 다시 쓰고 전체 영역을 0으로 지우지 않음 | 이 방법은 적용되지 않지만 데이터 복구는 가능: 서술자 재구성 또는 오프라인 재조립 |
| 3. 데이터 영역이 덮어써짐 | 전체 초기화 실행, 잘못된 방향의 재구축 | 이 문서 범위 밖, 전문 복구 필요 |

판단의 핵심은 **데이터 영역이 기록된 적이 있는가**이며, 볼륨 객체가 남아 있는지가 아닙니다.
볼륨 객체가 사라졌다고 데이터가 사라진 것은 아니며, 반대로 볼륨 객체가 남아 있어도 잘못된 재구축으로
데이터 영역이 덮였다면 더 나쁜 상태입니다.

## 원인

Intel은 각 구성원 디스크 끝에 배열 전체를 설명하는 메타데이터 블록을 기록합니다(이 사례에서 584바이트).
디스크가 빠지면 컨트롤러는 그 기록을 삭제하지 않고 세 곳에 동시에 표시를 남깁니다.

| 필드 | 정상 | 이탈 후 |
|---|---|---|
| 일련번호 필드 | `VLK5JGVY` | `VLK5JGVY:0` (`:0` 추가) |
| status | `0x0000053A` | `0x00000006` (CONFIGURED │ FAILED) |
| scsi_id | 실제 위치 | `0xFFFFFFFF` |

구성원 식별은 16바이트 일련번호 필드의 완전 일치 비교입니다. 기록에는 `VLK5JGVY:0`, 디스크는
`VLK5JGVY`를 보고하므로 일치하지 않습니다. 문자열이 디스크에 저장되어 있으므로 케이블 재연결이나
드라이버 업데이트로는 해결되지 않습니다.

볼륨 상태는 실패 슬롯 수로 계산됩니다. RAID5에서 1개면 `Degraded`, 2개 이상이면 `Failed`입니다.

## 방법

1. 모든 구성원을 메인보드에서 분리하고, USB로 한 번에 하나씩만 연결합니다.
2. 각 디스크의 마지막 64 KiB를 두 번 읽고 해시를 보관합니다. 읽기 전용입니다.
3. 마지막 4 KiB에서 584바이트 메타데이터를 잘라내어 파싱하고, 네 개를 나란히 비교해
   가장 최신이면서 체크섬이 맞는 사본을 찾습니다.
4. 메모리에서 수정합니다: 일련번호 필드 복원, 해당 구성원의 FAILED 및 동기화 해제 비트 제거,
   볼륨 상태를 `Degraded`로, 세대 번호 1 증가, 체크섬 재계산. 나머지 필드는 그대로 둡니다.
5. 같은 메타데이터를 모든 생존 구성원에 기록해 사본을 바이트 단위로 일치시킵니다.
6. 복구한 구성원만 연결해 부팅하고 BIOS RST 화면에서 `Degraded`인지 확인합니다.

```powershell
python scripts\verify_present_state_readonly.py <디스크 번호> <ATA 일련번호>
python scripts\dump_cfg.py samples\VLK5JGVY_IMSM_configuration.bin
python scripts\apply_mpb_write.py <디스크 번호> <ATA 일련번호>          # 예행 실행
python scripts\apply_mpb_write.py <디스크 번호> <ATA 일련번호> --apply  # 실제 기록
```

## 결과

이 사례에서는 세 구성원에 각각 22, 15, 15바이트를 기록했고(모두 디스크 끝 메타데이터 섹터 내,
데이터 영역 0바이트), BIOS가 즉시 `Degraded`를 표시하며 구성원이 다시 참여했습니다.
동기화가 어긋난 구성원을 연결하자 재구축이 시작되었고, 완료 후 볼륨은 Windows에서 정상 마운트되었습니다.
용량 24 004 676 026 368바이트로 메타데이터 기록과 일치합니다.

## 주의

1. 되돌릴 수 없습니다. 작업 전에 사전 이미지를 반드시 보관하십시오.
2. 584바이트를 연속 블록으로 직접 쓰지 마십시오. 4 KiB 물리 섹터 단위로 읽기-수정-쓰기를 해야 합니다.
3. 볼륨을 `Normal`로 설정하지 마십시오. 실제로 뒤처진 구성원이 있으면 오래된 데이터를 조용히 반환합니다.
4. 검증 전에 Windows가 쓰기 가능으로 마운트하지 않도록 하십시오. `mountvol /N` 또는
   `Set-Disk -IsReadOnly $true`를 사용합니다.
5. 중요 데이터를 복사하기 전에 `chkdsk /f`를 실행하지 마십시오.
6. 이 문서의 오프셋을 그대로 쓰지 말고 실제 용량과 섹터 크기로 다시 계산하십시오.

## 참고

- Intel 지원 문서 000099952: <https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>
- mdadm IMSM 구현: <https://raw.githubusercontent.com/md-raid-utilities/mdadm/main/super-intel.c>
- 전체 절차와 필드 표: [docs/03-procedure.md](docs/03-procedure.md), [docs/02-imsm-metadata-format.md](docs/02-imsm-metadata-format.md)

## 라이선스

MIT, [LICENSE](LICENSE) 참조.
