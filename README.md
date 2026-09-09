# Charon — passeur SysEx vers Volca FM

Application de bureau qui envoie des patches SysEx **DX7 / Volca FM** vers la
machine, par un port MIDI réel.

**Pourquoi elle existe :** le loader SysEx d'AZA passe par la Web MIDI API, qui
n'existe que dans un contexte sécurisé — donc en https, donc par le tunnel. En
studio, devant la machine, c'est une dépendance absurde. Charon parle
directement au port MIDI du système.

Linux (ALSA/JACK), macOS (CoreMIDI) et Windows, via `python-rtmidi`.

## Lancer

```bash
uv run charon
```

## Ce qu'il sait faire

- lister les ports MIDI de sortie, et suivre leurs branchements à chaud
- lire un `.syx` contenant **un ou plusieurs** messages, et les séparer
- reconnaître les formats DX7 : **bulk 32 voix** (4104 o) et **voix seule** (163 o)
- **vérifier la somme de contrôle** avant d'envoyer — un fichier corrompu se voit
  avant que la machine ne le refuse
- **forcer le canal MIDI** du message, sans casser la somme de contrôle
- temporiser entre messages quand un fichier en contient plusieurs
