# Intel RST RAID5 : récupérer un disque membre signalé comme `Non-RAID`

[简体中文](README.md) | [繁體中文](README.zh-TW.md) | [English](README.en.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Deutsch](README.de.md) | **Français** | [Español](README.es.md) | [Português](README.pt-BR.md) | [Italiano](README.it.md) | [Polski](README.pl.md) | [Русский](README.ru.md)

## De quel type de problème il s'agit

Il s'agit d'un problème documenté et répandu d'Intel RST, pas d'un cas isolé.

L'article de support Intel **000099952** décrit la perte de disques SATA par Intel RST dans certaines
conditions : le disque disparaît du système, le volume passe en dégradé ou en échec, et le disque ne réintègre
pas le volume après rebranchement. Toutes les machines utilisant Intel RST / VMD sont concernées.
<https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>

L'énumération des disques, la détermination de l'état du volume et l'écriture des métadonnées au démarrage
sont effectuées par l'**OROM RST intégré au BIOS**, et non par le pilote Windows. Une correction réelle ne peut
donc venir que d'une mise à jour de BIOS du fabricant de la carte mère ; une mise à jour côté Windows ne la
remplace pas. La plupart des cartes embarquent encore un OROM 19.x.

Sous ce défaut connu revient un schéma de panne récupérable :

- le disque est physiquement sain, SMART propre
- les autres membres du volume contiennent des données intactes
- mais le firmware a marqué ce disque comme manquant : `Non-RAID` dans l'interface, ou une entrée fantôme de
  0 octet en état « Perdu »
- rebrancher les câbles, changer de port, redémarrer, flasher le BIOS ou mettre à jour les pilotes ne change rien

Ce document décrit le traitement de ce cas. Comme il implique d'écrire directement dans les métadonnées,
lisez intégralement la section « Précautions » avant toute manipulation.

## Périmètre

Classez d'abord la situation. Seul le premier cas relève de cette méthode.

| Cas | Critères | Traitement |
|---|---|---|
| 1. Enregistrement de membre erroné, zone de données intacte | volume `Failed` ; un seul membre en `Non-RAID` ou une entrée « Perdu » de 0 octet ; numéro de série suffixé par `:0` ; aucun « marquer comme normal » effectué | méthode de ce document |
| 2. Volume supprimé ou recréé, zone de données non écrasée | la suppression/recréation ne réécrit en général que les métadonnées | cette méthode ne s'applique pas ; les données restent récupérables par reconstruction du descripteur ou réassemblage hors ligne |
| 3. Zone de données écrasée | initialisation complète effectuée, ou reconstruction dans le mauvais sens | hors périmètre, récupération professionnelle nécessaire |

Le critère décisif est **la zone de données a-t-elle été écrite**, et non la présence de l'objet volume.
Un volume disparu ne signifie pas des données disparues ; à l'inverse, un volume toujours présent après une
reconstruction qui a écrasé la zone de données est dans un état pire.

## Cause

Intel écrit à la fin de chaque disque membre un bloc de métadonnées décrivant tout le volume (584 octets ici).
Quand un disque disparaît, le contrôleur ne supprime pas son enregistrement : il le marque à trois endroits.

| Champ | Normal | Après disparition |
|---|---|---|
| champ numéro de série | `VLK5JGVY` | `VLK5JGVY:0` (suffixe `:0` ajouté) |
| status | `0x0000053A` | `0x00000006` (CONFIGURED │ FAILED) |
| scsi_id | emplacement réel | `0xFFFFFFFF` |

L'identification d'un membre compare le champ de numéro de série de 16 octets en égalité exacte.
L'enregistrement contient `VLK5JGVY:0`, le disque annonce `VLK5JGVY` : aucune correspondance n'est possible.
La chaîne étant stockée sur le disque, rebrancher le câble ou mettre à jour le pilote n'y change rien.

L'état du volume se déduit du nombre d'emplacements en échec : 1 en RAID5 donne `Degraded`, 2 ou plus donnent
`Failed`.

## Méthode

1. Retirer tous les membres de la carte mère et n'en connecter qu'un à la fois en USB.
2. Lire deux fois les derniers 64 KiB de chaque disque et conserver les empreintes. Lecture seule.
3. Extraire le bloc de 584 octets des derniers 4 KiB, l'analyser et comparer les quatre pour retenir la copie
   la plus récente dont la somme de contrôle est valide.
4. Corriger en mémoire : restaurer le champ numéro de série, effacer les marques FAILED et hors synchronisation
   de ce membre, passer l'état du volume à `Degraded`, incrémenter la génération, recalculer la somme de
   contrôle. Ne rien changer d'autre.
5. Écrire cette même copie sur tous les membres survivants pour qu'elles soient identiques octet par octet.
6. Ne rebrancher que les membres réparés et vérifier dans l'écran RST du BIOS que l'état est `Degraded`.

```powershell
python scripts\verify_present_state_readonly.py <numéro de disque> <NUMERO DE SERIE ATA>
python scripts\dump_cfg.py samples\VLK5JGVY_IMSM_configuration.bin
python scripts\apply_mpb_write.py <numéro de disque> <NUMERO DE SERIE ATA>
python scripts\apply_mpb_write.py <numéro de disque> <NUMERO DE SERIE ATA> --apply
```

## Résultat

Dans ce cas, 22, 15 et 15 octets ont été écrits sur les trois membres, tous dans le secteur de métadonnées en
fin de disque, et 0 octet dans la zone de données. Le BIOS a affiché `Degraded` et le membre a réintégré le
volume. Après rebranchement du membre désynchronisé, une reconstruction a démarré ; une fois terminée, le volume
s'est monté normalement sous Windows, avec 24 004 676 026 368 octets, conformément aux métadonnées.

## Précautions

1. Aucun retour en arrière possible. Conservez une image préalable avant toute écriture.
2. N'écrivez jamais les 584 octets comme un bloc contigu : travaillez par secteur physique de 4 KiB en
   lecture-modification-écriture.
3. Ne passez jamais le volume en `Normal`. Si un membre est réellement en retard, `Normal` fait renvoyer
   silencieusement des données anciennes.
4. Avant vérification, empêchez Windows de monter en écriture : `mountvol /N` ou
   `Set-Disk -IsReadOnly $true`.
5. Ne lancez pas `chkdsk /f` avant d'avoir copié les données importantes.
6. Ne recopiez pas les offsets de ce document : recalculez-les selon la capacité et la taille de secteur réelles.

## Références

- Article de support Intel 000099952 : <https://www.intel.com/content/www/us/en/support/articles/000099952/technologies.html>
- Implémentation IMSM de mdadm : <https://raw.githubusercontent.com/md-raid-utilities/mdadm/main/super-intel.c>
- Procédure complète et tables de champs : [docs/03-procedure.md](docs/03-procedure.md), [docs/02-imsm-metadata-format.md](docs/02-imsm-metadata-format.md)

## Licence

MIT, voir [LICENSE](LICENSE).
