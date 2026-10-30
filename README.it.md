# Intel RST RAID5: recuperare un disco membro visualizzato come `Non-RAID`

[简体中文](README.md) | [繁體中文](README.zh-TW.md) | [English](README.en.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md) | [Português](README.pt-BR.md) | **Italiano** | [Polski](README.pl.md) | [Русский](README.ru.md)

## Di che problema si tratta

È un problema documentato e diffuso di Intel RST, non un caso isolato.

L'articolo di supporto Intel **000099952** descrive la perdita di dischi SATA da parte di Intel RST in
determinate condizioni: il disco sparisce dal sistema, il volume va in stato degradato o in errore e il disco
non rientra nel volume dopo il ricollegamento. Riguarda tutte le macchine con Intel RST / VMD.
<https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>

L'enumerazione dei dischi, la determinazione dello stato del volume e la scrittura dei metadati all'avvio sono
eseguite dall'**OROM RST integrato nel BIOS**, non dal driver di Windows. Una correzione efficace può quindi
arrivare solo come aggiornamento BIOS da parte del produttore della scheda madre; aggiornare il lato Windows non
lo sostituisce. La maggior parte delle schede monta ancora un OROM 19.x.

Sotto questo difetto noto ricorre uno schema di guasto recuperabile:

- il disco è fisicamente sano, SMART pulito
- gli altri membri del volume hanno dati integri
- ma il firmware ha marcato quel disco come mancante: `Non-RAID` nell'interfaccia, oppure una voce fantasma da
  0 byte in stato «Perso»
- ricollegare i cavi, cambiare porta, riavviare, aggiornare BIOS o driver non cambia nulla

Questo documento descrive la gestione di quel caso. Poiché comporta la scrittura diretta dei metadati, leggere
per intero la sezione «Avvertenze» prima di qualsiasi operazione.

## Ambito

Classificare prima la situazione. Solo il primo caso rientra in questo metodo.

| Caso | Criteri | Trattamento |
|---|---|---|
| 1. Record di membro errato, area dati intatta | volume `Failed`; un solo membro in `Non-RAID` o una voce «Perso» da 0 byte; seriale con suffisso `:0`; nessun «segna come normale» eseguito | metodo di questo documento |
| 2. Volume eliminato o ricreato, area dati non sovrascritta | eliminare/ricreare riscrive di norma solo i metadati | questo metodo non si applica; i dati restano recuperabili ricostruendo il descrittore o riassemblando offline |
| 3. Area dati sovrascritta | inizializzazione completa eseguita, o ricostruzione nella direzione sbagliata | fuori ambito, richiede recupero professionale |

Il criterio decisivo è **se l'area dati è stata scritta**, non se l'oggetto volume esiste ancora.
Un volume scomparso non significa dati scomparsi; al contrario, un volume presente dopo una ricostruzione che ha
sovrascritto l'area dati è una situazione peggiore.

## Causa

Intel scrive in fondo a ogni disco membro un blocco di metadati che descrive l'intero volume (584 byte in questo
caso). Quando un disco esce, il controller non cancella il record: lo marca in tre punti contemporaneamente.

| Campo | Normale | Dopo l'uscita |
|---|---|---|
| campo seriale | `VLK5JGVY` | `VLK5JGVY:0` (suffisso `:0` aggiunto) |
| status | `0x0000053A` | `0x00000006` (CONFIGURED │ FAILED) |
| scsi_id | posizione reale | `0xFFFFFFFF` |

L'identificazione del membro confronta il campo seriale di 16 byte per uguaglianza esatta. Il record contiene
`VLK5JGVY:0` e il disco dichiara `VLK5JGVY`, quindi non c'è corrispondenza. Essendo una stringa memorizzata sul
disco, ricollegare il cavo o aggiornare il driver non risolve.

Lo stato del volume deriva dal conteggio degli slot in errore: 1 in RAID5 dà `Degraded`, 2 o più danno `Failed`.

## Metodo

1. Rimuovere tutti i membri dalla scheda madre e collegarne uno alla volta via USB.
2. Leggere due volte gli ultimi 64 KiB di ogni disco e conservare gli hash. Sola lettura.
3. Estrarre il blocco di 584 byte dagli ultimi 4 KiB, analizzarlo e confrontare i quattro per scegliere la copia
   più recente con checksum valido.
4. Correggere in memoria: ripristinare il campo seriale, cancellare i marcatori FAILED e di fuori sincronia di
   quel membro, portare lo stato del volume a `Degraded`, incrementare la generazione, ricalcolare il checksum.
   Non modificare altro.
5. Scrivere la stessa copia su tutti i membri sopravvissuti, rendendole identiche byte per byte.
6. Ricollegare solo i membri riparati e verificare nella schermata RST del BIOS che lo stato sia `Degraded`.

```powershell
python scripts\verify_present_state_readonly.py <numero disco> <SERIALE ATA>
python scripts\dump_cfg.py samples\VLK5JGVY_IMSM_configuration.bin
python scripts\apply_mpb_write.py <numero disco> <SERIALE ATA>
python scripts\apply_mpb_write.py <numero disco> <SERIALE ATA> --apply
```

## Risultato

In questo caso sono stati scritti 22, 15 e 15 byte sui tre membri, tutti nel settore di metadati in fondo al
disco, e 0 byte nell'area dati. Il BIOS ha mostrato `Degraded` e il membro è rientrato nel volume. Ricollegando
il membro desincronizzato è partita la ricostruzione; al termine il volume si è montato normalmente in Windows,
con 24 004 676 026 368 byte, pari a quanto registrato nei metadati.

## Avvertenze

1. Non si può tornare indietro. Conservare un'immagine preliminare prima di qualsiasi scrittura.
2. Non scrivere mai i 584 byte come blocco contiguo: operare per settore fisico da 4 KiB in
   lettura-modifica-scrittura.
3. Non impostare mai il volume su `Normal`. Se un membro è realmente indietro, `Normal` fa restituire dati
   obsoleti senza segnalarlo.
4. Prima della verifica impedire a Windows di montare in scrittura: `mountvol /N` oppure
   `Set-Disk -IsReadOnly $true`.
5. Non eseguire `chkdsk /f` prima aver copiato i dati importanti.
6. Non copiare gli offset di questo documento: ricalcolarli in base a capacità e dimensione di settore reali.

## Riferimenti

- Articolo di supporto Intel 000099952: <https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>
- Implementazione IMSM di mdadm: <https://raw.githubusercontent.com/md-raid-utilities/mdadm/main/super-intel.c>
- Procedura completa e tabelle dei campi: [docs/03-procedure.md](docs/03-procedure.md), [docs/02-imsm-metadata-format.md](docs/02-imsm-metadata-format.md)

## Licenza

MIT, vedere [LICENSE](LICENSE).
