# Intel RST RAID5: recuperar um disco membro exibido como `Non-RAID`

[简体中文](README.md) | [繁體中文](README.zh-TW.md) | [English](README.en.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | [Français](README.fr.md) | [Español](README.es.md) | **Português** | [Italiano](README.it.md) | [Polski](README.pl.md) | [Русский](README.ru.md)

## Que tipo de problema é este

É um problema documentado e difundido do Intel RST, não um caso isolado.

O artigo de suporte da Intel **000099952** descreve a perda de discos SATA pelo Intel RST em determinadas
condições: o disco desaparece do sistema, o volume fica degradado ou em falha, e o disco não volta ao volume
quando reconectado. Afeta qualquer máquina com Intel RST / VMD.
<https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>

A enumeração dos discos, a determinação do estado do volume e a gravação dos metadados na inicialização são
feitas pela **OROM do RST embutida na BIOS**, e não pelo driver do Windows. Uma correção efetiva só pode vir
como atualização de BIOS do fabricante da placa; atualizar o lado do Windows não substitui isso. A maioria das
placas ainda traz uma OROM 19.x.

Sob esse defeito conhecido aparece repetidamente um padrão recuperável:

- o disco está fisicamente saudável, SMART limpo
- os demais membros do volume têm dados íntegros
- mas o firmware marcou o disco como ausente: `Non-RAID` na interface, ou um registro fantasma de 0 byte em
  estado “Perdido”
- reconectar cabos, trocar de porta, reiniciar, atualizar a BIOS ou o driver não muda nada

Este documento descreve o tratamento desse caso. Como envolve escrever diretamente nos metadados, leia a seção
“Cuidados” por inteiro antes de qualquer ação.

## Escopo

Classifique primeiro a situação. Apenas o primeiro caso usa este método.

| Caso | Critérios | Tratamento |
|---|---|---|
| 1. Registro de membro incorreto, área de dados intacta | volume `Failed`; apenas um membro em `Non-RAID` ou um registro “Perdido” de 0 byte; serial com sufixo `:0`; nenhum “marcar como normal” executado | método deste documento |
| 2. Volume excluído ou recriado, área de dados não sobrescrita | excluir/recriar normalmente reescreve só os metadados | este método não se aplica; os dados ainda são recuperáveis reconstruindo o descritor ou remontando offline |
| 3. Área de dados sobrescrita | inicialização completa executada, ou reconstrução na direção errada | fora do escopo, requer recuperação profissional |

O critério decisivo é **se a área de dados foi escrita**, e não se o objeto de volume ainda existe.
Volume ausente não significa dados ausentes; por outro lado, volume presente após uma reconstrução que
sobrescreveu a área de dados é um estado pior.

## Causa

A Intel grava no fim de cada disco membro um bloco de metadados que descreve todo o volume (584 bytes neste
caso). Quando um disco sai, o controlador não apaga o registro: marca em três lugares ao mesmo tempo.

| Campo | Normal | Após a saída |
|---|---|---|
| campo de serial | `VLK5JGVY` | `VLK5JGVY:0` (sufixo `:0` acrescentado) |
| status | `0x0000053A` | `0x00000006` (CONFIGURED │ FAILED) |
| scsi_id | localização real | `0xFFFFFFFF` |

A identificação de membro compara o campo de serial de 16 bytes por igualdade exata. O registro contém
`VLK5JGVY:0` e o disco informa `VLK5JGVY`, portanto não há correspondência. Como a string fica gravada no
disco, reconectar o cabo ou atualizar o driver não resolve.

O estado do volume é derivado da contagem de posições em falha: 1 em RAID5 resulta em `Degraded`, 2 ou mais
resultam em `Failed`.

## Método

1. Retire todos os membros da placa-mãe e conecte um por vez por USB.
2. Leia duas vezes os últimos 64 KiB de cada disco e guarde os hashes. Somente leitura.
3. Extraia o bloco de 584 bytes dos últimos 4 KiB, faça o parse e compare os quatro para escolher a cópia mais
   recente com checksum válido.
4. Corrija em memória: restaurar o campo de serial, limpar as marcas FAILED e de fora de sincronia desse membro,
   mudar o estado do volume para `Degraded`, incrementar a geração, recalcular o checksum. Não altere o resto.
5. Grave essa mesma cópia em todos os membros sobreviventes, deixando-as idênticas byte a byte.
6. Reconecte apenas os membros reparados e verifique na tela RST da BIOS se o estado é `Degraded`.

```powershell
python scripts\verify_present_state_readonly.py <número do disco> <SERIAL ATA>
python scripts\dump_cfg.py samples\VLK5JGVY_IMSM_configuration.bin
python scripts\apply_mpb_write.py <número do disco> <SERIAL ATA>
python scripts\apply_mpb_write.py <número do disco> <SERIAL ATA> --apply
```

## Resultado

Neste caso foram gravados 22, 15 e 15 bytes nos três membros, todos dentro do setor de metadados no fim do
disco, e 0 byte na área de dados. A BIOS exibiu `Degraded` e o membro voltou ao volume. Ao reconectar o membro
dessincronizado, a reconstrução iniciou; ao terminar, o volume montou normalmente no Windows, com
24 004 676 026 368 bytes, igual ao registrado nos metadados.

## Cuidados

1. Não há como desfazer. Guarde uma imagem prévia antes de qualquer gravação.
2. Nunca grave os 584 bytes como bloco contíguo: trabalhe em setor físico de 4 KiB com leitura-modificação-escrita.
3. Nunca defina o volume como `Normal`. Se um membro estiver realmente atrasado, `Normal` faz o sistema devolver
   dados antigos silenciosamente.
4. Antes de verificar, impeça o Windows de montar com escrita: `mountvol /N` ou `Set-Disk -IsReadOnly $true`.
5. Não execute `chkdsk /f` antes de copiar os dados importantes.
6. Não copie os offsets deste documento: recalcule conforme a capacidade e o tamanho de setor reais.

## Referências

- Artigo de suporte Intel 000099952: <https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>
- Implementação IMSM do mdadm: <https://raw.githubusercontent.com/md-raid-utilities/mdadm/main/super-intel.c>
- Procedimento completo e tabelas de campos: [docs/03-procedure.md](docs/03-procedure.md), [docs/02-imsm-metadata-format.md](docs/02-imsm-metadata-format.md)

## Licença

MIT, consulte [LICENSE](LICENSE).
