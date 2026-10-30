# Intel RST RAID5: przywracanie dysku składowego widocznego jako `Non-RAID`

[简体中文](README.md) | [繁體中文](README.zh-TW.md) | [English](README.en.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md) | [Português](README.pt-BR.md) | [Italiano](README.it.md) | **Polski** | [Русский](README.ru.md)

## Charakter problemu

To udokumentowany, powszechny problem Intel RST, a nie pojedynczy przypadek.

Artykuł pomocy technicznej Intel **000099952** opisuje gubienie dysków SATA przez Intel RST w określonych
warunkach: dysk znika z systemu, wolumin przechodzi w stan zdegradowany lub awaryjny, a po ponownym podłączeniu
dysk nie wraca do woluminu. Dotyczy wszystkich maszyn z Intel RST / VMD.
<https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>

Wyliczanie dysków, ustalanie stanu woluminu i zapis metadanych przy starcie wykonuje **OROM RST wbudowany
w BIOS**, a nie sterownik Windows. Skuteczna poprawka może więc przyjść wyłącznie jako aktualizacja BIOS od
producenta płyty; aktualizacja po stronie Windows jej nie zastąpi. Większość płyt nadal ma OROM 19.x.

Pod tym znanym defektem powtarza się odzyskiwalny schemat awarii:

- dysk jest fizycznie sprawny, SMART czysty
- pozostałe dyski składowe mają nietknięte dane
- ale firmware oznaczył ten dysk jako brakujący: `Non-RAID` w interfejsie albo wpis widmo 0 bajtów w stanie
  „Utracony”
- przełożenie kabli, zmiana portu, restart, aktualizacja BIOS lub sterownika nic nie zmieniają

Ten dokument opisuje postępowanie w takim przypadku. Ponieważ polega ono na bezpośrednim zapisie metadanych,
przed przystąpieniem do pracy należy przeczytać całą sekcję „Ostrzeżenia”.

## Zakres

Najpierw zaklasyfikuj sytuację. Tylko pierwszy przypadek podlega tej metodzie.

| Przypadek | Kryteria | Postępowanie |
|---|---|---|
| 1. Błędny wpis dysku składowego, obszar danych nietknięty | wolumin `Failed`; tylko jeden dysk jako `Non-RAID` lub wpis „Utracony” 0 bajtów; numer seryjny z przyrostkiem `:0`; nie wykonano „oznacz jako normalny” | metoda z tego dokumentu |
| 2. Wolumin usunięty lub utworzony ponownie, obszar danych nie nadpisany | usunięcie/utworzenie zwykle przepisuje tylko metadane | ta metoda nie ma zastosowania; dane nadal można odzyskać, odtwarzając deskryptor lub składając wolumin poza kontrolerem |
| 3. Obszar danych nadpisany | wykonano pełną inicjalizację albo przebudowę w złym kierunku | poza zakresem, wymaga profesjonalnego odzyskiwania |

Decyduje to, **czy obszar danych został zapisany**, a nie czy obiekt woluminu nadal istnieje.
Brak woluminu nie oznacza braku danych; odwrotnie — wolumin istniejący po przebudowie, która nadpisała obszar
danych, to stan gorszy.

## Przyczyna

Intel zapisuje na końcu każdego dysku składowego blok metadanych opisujący cały wolumin (w tym przypadku
584 bajty). Gdy dysk wypada, kontroler nie usuwa wpisu, lecz oznacza go w trzech miejscach jednocześnie.

| Pole | Normalnie | Po wypadnięciu |
|---|---|---|
| pole numeru seryjnego | `VLK5JGVY` | `VLK5JGVY:0` (dodany przyrostek `:0`) |
| status | `0x0000053A` | `0x00000006` (CONFIGURED │ FAILED) |
| scsi_id | rzeczywista lokalizacja | `0xFFFFFFFF` |

Identyfikacja dysku składowego porównuje 16-bajtowe pole numeru seryjnego na dokładną równość. Wpis zawiera
`VLK5JGVY:0`, a dysk zgłasza `VLK5JGVY`, więc dopasowanie jest niemożliwe. Ponieważ ciąg jest zapisany na
dysku, przełożenie kabla ani aktualizacja sterownika tego nie zmienią.

Stan woluminu wynika z liczby slotów w błędzie: 1 w RAID5 daje `Degraded`, 2 lub więcej daje `Failed`.

## Metoda

1. Odłącz wszystkie dyski od płyty głównej i podłączaj po jednym przez USB.
2. Odczytaj dwukrotnie ostatnie 64 KiB każdego dysku i zachowaj skróty. Tylko odczyt.
3. Wyodrębnij blok 584 bajtów z ostatnich 4 KiB, przeanalizuj go i porównaj cztery kopie, aby wybrać najnowszą
   z poprawną sumą kontrolną.
4. Popraw w pamięci: przywróć pole numeru seryjnego, usuń znaczniki FAILED i braku synchronizacji tego dysku,
   ustaw stan woluminu na `Degraded`, zwiększ numer generacji, przelicz sumę kontrolną. Reszty nie zmieniaj.
5. Zapisz tę samą kopię na wszystkich ocalałych dyskach, aby były identyczne co do bajtu.
6. Podłącz tylko naprawione dyski i sprawdź na ekranie RST w BIOS, czy stan to `Degraded`.

```powershell
python scripts\verify_present_state_readonly.py <numer dysku> <NUMER SERYJNY ATA>
python scripts\dump_cfg.py samples\VLK5JGVY_IMSM_configuration.bin
python scripts\apply_mpb_write.py <numer dysku> <NUMER SERYJNY ATA>
python scripts\apply_mpb_write.py <numer dysku> <NUMER SERYJNY ATA> --apply
```

## Wynik

W tym przypadku zapisano 22, 15 i 15 bajtów na trzech dyskach, wszystkie w sektorze metadanych na końcu dysku,
oraz 0 bajtów w obszarze danych. BIOS pokazał `Degraded`, a dysk wrócił do woluminu. Po podłączeniu dysku
poza synchronizacją uruchomiła się przebudowa; po jej zakończeniu wolumin zamontował się poprawnie w Windows,
o rozmiarze 24 004 676 026 368 bajtów, zgodnym z metadanymi.

## Ostrzeżenia

1. Nie ma cofnięcia. Przed jakimkolwiek zapisem zachowaj obraz początkowy.
2. Nigdy nie zapisuj 584 bajtów jako bloku ciągłego: pracuj na sektorze fizycznym 4 KiB w trybie
   odczyt-modyfikacja-zapis.
3. Nigdy nie ustawiaj woluminu na `Normal`. Jeśli dysk faktycznie pozostaje w tyle, `Normal` powoduje ciche
   zwracanie starych danych.
4. Przed weryfikacją uniemożliw montowanie w trybie zapisu: `mountvol /N` lub `Set-Disk -IsReadOnly $true`.
5. Nie uruchamiaj `chkdsk /f`, dopóki ważne dane nie zostaną skopiowane.
6. Nie kopiuj przesunięć z tego dokumentu: przelicz je dla rzeczywistej pojemności i rozmiaru sektora.

## Odnośniki

- Artykuł pomocy Intel 000099952: <https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>
- Implementacja IMSM w mdadm: <https://raw.githubusercontent.com/md-raid-utilities/mdadm/main/super-intel.c>
- Pełna procedura i tabele pól: [docs/03-procedure.md](docs/03-procedure.md), [docs/02-imsm-metadata-format.md](docs/02-imsm-metadata-format.md)

## Licencja

MIT, patrz [LICENSE](LICENSE).
