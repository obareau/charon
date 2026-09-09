# Architecture

Quatre modules, une règle : **le noyau ignore tout de l'interface**. `sysex.py`
et `midi.py` n'importent jamais Qt — c'est ce qui permet aux tests de tourner
sans écran, donc sur les trois systèmes en intégration continue.

```
charon/
  sysex.py     ← format : découper, valider, composer.  Aucune dépendance.
  midi.py      ← sortie réelle : lister les ports, envoyer.  rtmidi seul.
  workshop.py  ← onglet « Atelier de banks ».  Qt.
  app.py       ← fenêtre, onglets, port partagé, journal.  Qt.
```

Le sens des flèches ne s'inverse jamais : `app.py` connaît `sysex.py`, l'inverse
n'arrive pas.

---

## `sysex.py` — le format

Sans état, sans effet de bord, testable en isolation.

| Fonction | Rôle |
|---|---|
| `split_messages(blob)` | isole chaque `F0…F7` d'un fichier, ignore le rembourrage |
| `Message` | un message et ce qu'on en déduit : taille, format, canal, somme |
| `expected_checksum` / `stored_checksum` | comparer l'attendu et l'écrit |
| `set_channel(msg, 1-16)` | réécrit le canal sans toucher aux données |
| `voices(bulk)` | les 32 voix compressées d'une bank |
| `voice_name(packed)` | le nom, nettoyé des caractères non imprimables |
| `build_bank(voix, canal)` | assemble et recalcule la somme |

Détail du format : [`format-sysex.md`](format-sysex.md).

---

## `midi.py` — la sortie réelle

`python-rtmidi` couvre ALSA/JACK, CoreMIDI et WinMM derrière une seule
interface. Deux points de conception :

**Les ports sont relus à chaque appel.** Un port apparaît ou disparaît au
branchement ; une liste mise en cache ferait viser un index périmé, donc
envoyer un dump vers le mauvais appareil.

**L'absence de couche MIDI n'est pas une panne.** Sur un Linux sans séquenceur
ALSA, `rtmidi.MidiOut()` lève. `output_ports()` rend alors une liste vide :
pour l'appelant, « pas de système MIDI » et « aucun appareil branché » sont la
même situation — rien où envoyer. C'est `send()` qui explique la cause, au
moment où quelqu'un tente vraiment quelque chose.

⚠️ **Un message n'est jamais découpé.** Le délai réglable sépare deux messages,
jamais les morceaux d'un seul : un SysEx tronqué en vol n'est pas un SysEx,
c'est du bruit que l'appareil rejette. 4104 octets prennent déjà ~1,3 s à
31250 bauds.

---

## `app.py` et `workshop.py` — l'interface

Un port MIDI et un journal **partagés** en haut et en bas, deux onglets entre
les deux. L'atelier ne connaît pas le port : il émet `send_requested(bytes)`,
la fenêtre s'occupe du reste.

**L'envoi vit dans un `QThread`.** Un dump prend plus d'une seconde sur le
câble ; sans fil séparé, la fenêtre se figerait pendant tout l'envoi et
paraîtrait plantée.

---

## Tests

```bash
uv run --with pytest pytest tests/ -v
```

| Fichier | Ce qu'il couvre |
|---|---|
| `test_sysex.py` | formats, sommes, découpage, canal |
| `test_banks.py` | découper deux banks, en composer une troisième |
| `test_midi_loopback.py` | **envoi réel** par le port de bouclage, et absence d'ALSA |

Le test de bouclage envoie un vrai dump de 4104 octets sur « Midi Through » et
vérifie qu'il **revient identique**, canal forcé compris. Il s'ignore
proprement là où ce port n'existe pas (macOS, Windows).

⚠️ **`rtmidi` ignore le SysEx en entrée par défaut.** Sans
`ignore_types(sysex=False)`, on ne reçoit jamais rien et on croit que l'envoi a
échoué. C'est le piège le plus coûteux de ce projet.

---

## Intégration continue

`.github/workflows/tests.yml` — Linux, macOS et Windows, en 3.11 et 3.13.

Elle a immédiatement gagné son coût : elle a trouvé le plantage sans ALSA
décrit plus haut, sur la plateforme même où le projet a été écrit. Trois
systèmes au vert et Linux seul en échec, parce que macOS et Windows n'ont pas
ce comportement.

---

## L'apparence

La palette reprend celle du DX7 de 1983, parce qu'un outil qui parle à cette
machine gagne à lui ressembler — et parce que quatre matières suffisent à s'en
souvenir :

| Élément | Couleur | Ce que ça imite |
|---|---|---|
| Châssis | `#2B2724` | le brun sombre du boîtier, plus chaud qu'un noir |
| Touches | `#C6BCA8` | les touches à membrane beige, avec un liseré bas qui les bombe |
| Accent | `#C2551F` | l'orange Yamaha, réservé à l'action principale |
| Journal | `#A9BE55` sur `#23300F` | l'écran LCD vert-jaune à caractères sombres |
| Police de l'écran | DotGothic16 | une **matrice de points**, embarquée sous OFL |

⚠️ **La sélection n'utilise pas l'orange plein.** Essayé, puis abandonné : elle
recouvrait la colonne État et rendait illisibles les couleurs de somme de
contrôle, qui sont l'information la plus utile de la table. C'est un ambre
brûlé avec un liseré orange à gauche — présent sans écraser.
