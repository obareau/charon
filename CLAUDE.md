# CLAUDE.md

Guide pour Claude Code sur ce dépôt.

## Le projet en une phrase

Application de bureau qui envoie des SysEx DX7/Volca FM par un **port MIDI
réel**, et compose des banks à partir de deux sources.

**Pourquoi elle existe** : le loader SysEx d'AZA passe par la Web MIDI API, qui
n'existe qu'en contexte sécurisé — donc en https, donc par le tunnel Cloudflare.
Dépendre d'un tunnel pour parler à une machine posée sur le bureau est absurde.

## Commandes

```bash
uv run charon                              # lancer
uv run --with pytest pytest tests/ -v      # tester
```

## Architecture

`sysex.py` (format) et `midi.py` (sortie) **n'importent jamais Qt**. C'est ce
qui permet aux tests de tourner sans écran, donc sur les trois systèmes en
intégration continue. Ne pas casser cette séparation.

Détail : [`docs/architecture.md`](docs/architecture.md).

## ⚠️ Pièges vérifiés — ne pas les redécouvrir

**`rtmidi` ignore le SysEx en entrée par défaut.** Sans
`ignore_types(sysex=False)`, on ne reçoit jamais rien et on conclut à tort que
l'envoi a échoué. Le piège le plus coûteux du projet.

**Sans séquenceur ALSA, `rtmidi.MidiOut()` lève** au lieu de rendre une liste
vide — sur un serveur, un conteneur, un runner. macOS et Windows n'ont pas ce
comportement, donc le bug ne se voit que sur Linux. `output_ports()` rend `[]`,
`send()` explique. Corrigé, avec deux tests qui simulent l'absence d'ALSA.

**Ne jamais découper un message SysEx.** Le délai réglable sépare deux messages,
jamais les morceaux d'un seul : un SysEx tronqué en vol est du bruit que
l'appareil rejette.

**Ne jamais réencoder une voix.** Les 128 octets sont recopiés tels quels. C'est
ce qui garantit qu'un patch déplacé d'une bank à l'autre arrive bit pour bit
identique. Interpréter les paramètres introduirait un risque de perte pour
aucun gain.

**La somme de contrôle ne couvre que le bloc de données**, jamais l'en-tête —
c'est ce qui rend sûre la réécriture du canal. Un test le vérifie.

## Le format

Deux tailles identifient tout : **4104 o** (bulk 32 voix) et **163 o** (voix
seule). Une bank = 32 voix de 128 octets, nom aux octets 118-127 de chacune.

Référence complète : [`docs/format-sysex.md`](docs/format-sysex.md).

⚠️ Une voix dans une bank (128 o compressés) et une voix seule (155 o non
compressés) sont **deux encodages différents**. Charon ne convertit pas entre
les deux — ne pas ajouter cette conversion sans implémenter la vraie table de
compression, et surtout sans la tester contre un fichier de référence.

## Avant de committer

1. `uv run --with pytest pytest tests/ -v` — la suite entière
2. Si le format est touché : un test qui prouve le comportement sur des octets
   réels, pas sur une simulation
3. L'intégration continue tourne sur Linux, macOS et Windows — un changement
   qui n'affecte qu'un système se voit là
