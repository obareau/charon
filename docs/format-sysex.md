# Le format SysEx DX7, tel que Charon le connaît

> Ce document décrit **exactement ce que le code implémente et que les tests
> vérifient** — ni plus. Là où Charon ne sait rien, c'est écrit.

Le Volca FM accepte les dumps du DX7 : c'est le même format, hérité tel quel.
Deux tailles suffisent à identifier ce qu'on tient.

---

## Les deux messages reconnus

### Bulk 32 voix — 4104 octets

```
F0 43 0n 09 20 00  <4096 octets de données>  <somme>  F7
└┬┘ └┬┘ └┬┘ └┬┘ └──┬──┘
 │   │   │   │     └── nombre d'octets à suivre, sur 7 bits : 0x20 0x00 = 4096
 │   │   │   └──────── format 9 = 32 voix
 │   │   └──────────── sous-statut (quartet haut) | canal MIDI (quartet bas)
 │   └──────────────── 0x43 = Yamaha
 └──────────────────── début de SysEx
```

6 + 4096 + 1 + 1 = **4104**.

### Voix seule — 163 octets

```
F0 43 0n 00 01 1B  <155 octets de données>  <somme>  F7
```

6 + 155 + 1 + 1 = **163**.

⚠️ **Les deux encodages diffèrent.** Une voix dans un bulk occupe **128 octets
compressés** ; la même voix seule en occupe **155 non compressés**. Ce ne sont
pas les mêmes octets — Charon ne convertit pas de l'un vers l'autre, et ne
prétend pas le faire.

---

## La somme de contrôle

Complément à deux de la somme des données, sur 7 bits :

```python
somme = (128 - (sum(données) & 0x7F)) & 0x7F
```

Elle couvre **uniquement le bloc de données** — jamais l'en-tête, jamais le F7.

C'est ce qui rend sûre la réécriture du canal : l'octet 2 est dans l'en-tête,
le modifier ne peut pas invalider le fichier. Un test le vérifie explicitement
(`test_set_channel_change_le_canal_sans_casser_la_somme`).

---

## Le canal MIDI

L'octet 2 vaut `(sous-statut << 4) | canal`, le canal étant compté de 0 à 15.
Charon n'écrit que le quartet bas et laisse le sous-statut intact — un dump de
paramètre (sous-statut 1) reste un dump de paramètre après changement de canal.

Dans l'interface, les canaux sont affichés **1-16**, comme sur la machine.

---

## Une bank, vue de l'intérieur

Le bloc de 4096 octets est fait de **32 voix de 128 octets**, à la suite,
sans séparateur :

```
voix 1 : données[0    : 128]
voix 2 : données[128  : 256]
…
voix 32: données[3968 : 4096]
```

Dans chaque voix compressée, les **10 derniers octets (118 à 127)** portent le
nom, en ASCII. C'est tout ce que Charon lit d'une voix.

### ⚠️ Ce que Charon ne sait PAS

**Il n'interprète aucun paramètre.** Enveloppes, ratios, algorithme,
feedback : ces 118 premiers octets sont pour lui un bloc opaque, recopié tel
quel. C'est délibéré, et c'est ce qui garantit qu'une voix déplacée d'une bank
à l'autre arrive **bit pour bit identique** — aucune interprétation ne peut
introduire de perte.

Un éditeur de patch, lui, aurait besoin de cette carte des paramètres. Ce n'est
pas ce qu'est Charon.

---

## Composer une bank

Choisir 32 blocs de 128 octets, les concaténer, recalculer la somme, remettre
l'en-tête. Rien d'autre.

Moins de 32 voix choisies : les emplacements libres reçoivent une **voix
muette** — 128 octets à zéro, dont le nom `INIT`. Tous les niveaux de sortie
étant à zéro, elle occupe la place sans rien émettre.

⚠️ **Une bank compte toujours exactement 32 voix.** Un bulk plus court n'existe
pas dans le format ; la machine le rejetterait.

---

## Ce qui n'est ni reconnu ni rejeté

Tout message qui commence par `F0` et finit par `F7` sans faire 4104 ni 163
octets est transmis **tel quel**, affiché comme « brut », sa somme annoncée
« non vérifiable ».

Ce n'est pas un refus : un SysEx d'une autre machine est parfaitement valide,
il n'est simplement pas interprétable ici. Charon le fait passer sans y toucher.
