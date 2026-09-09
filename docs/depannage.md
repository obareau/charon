# Dépannage

Chaque entrée décrit un symptôme réel et sa cause, pas une liste de vérifications
génériques.

---

## « Aucun port MIDI détecté »

**La machine n'est pas vue.** Dans l'ordre :

1. le Volca est branché **et allumé** — un Volca éteint n'expose aucun port ;
2. c'est bien un câble **USB de données**, pas un câble de charge seule ;
3. clique **Rafraîchir** — la liste n'est relue qu'à la demande, pas en continu.

**Sur Linux**, si aucun port n'apparaît jamais, même avec du matériel branché :

```bash
aconnect -l          # le séquenceur ALSA répond-il ?
ls /dev/snd/         # les périphériques existent-ils ?
```

Sur un serveur ou dans un conteneur sans ALSA, c'est normal : Charon rend une
liste vide au lieu de planter, c'est voulu.

---

## L'envoi dit « transmis », mais la machine ne change pas

C'est le cas le plus fréquent, et **ce n'est presque jamais un problème de
Charon** : les octets sont bien partis.

- **Le canal ne correspond pas.** Le Volca n'écoute qu'un canal. Utilise le
  sélecteur **Canal** pour forcer celui de la machine plutôt que d'espérer que
  le fichier porte le bon.
- **Le port choisi n'est pas le bon.** « Midi Through » est un bouclage du
  noyau : envoyer dessus ne va nulle part. C'est utile pour tester, jamais pour
  jouer.
- **La machine est dans un menu.** Un Volca en édition peut ignorer un dump.
- **La réception SysEx est désactivée** sur certaines machines.

---

## « Somme de contrôle fausse » dans la colonne État

Le fichier est abîmé, ou n'est pas ce qu'il prétend être. Charon te laisse
l'envoyer quand même après confirmation — mais la machine le refusera
probablement, ou chargera un patch corrompu.

Origines habituelles : téléchargement interrompu, fichier passé par un canal
qui a réécrit des octets (courriel, éditeur de texte), ou extrait d'une archive
tronquée.

---

## « Pas une bank » à l'ouverture dans l'atelier

L'atelier n'accepte que les **bulks 32 voix** (4104 octets). Une voix seule
(163 octets) ne peut pas y être piochée : ce n'est pas le même encodage —
128 octets compressés dans une bank, 155 non compressés dans une voix seule.
Charon ne convertit pas entre les deux, et ne fait pas semblant.

Une voix seule s'envoie parfaitement depuis l'onglet **Envoyer des fichiers**.

---

## Un fichier n'affiche qu'un message alors qu'il en contient plusieurs

Vérifie qu'il n'est pas tronqué : Charon s'arrête au premier `F0` sans `F7`
correspondant, plutôt que de transmettre un message incomplet.

---

## Rien ne se passe quand je clique « Envoyer »

Le bouton exige **une sélection**. Dans l'onglet des fichiers, sélectionne les
lignes à envoyer — tout est sélectionné par défaut au chargement, mais un clic
ailleurs peut avoir vidé la sélection.

---

## Sur macOS : le Volca n'apparaît pas

CoreMIDI est natif, il n'y a rien à installer. Si le port manque :
**Applications → Utilitaires → Configuration audio et MIDI**, fenêtre
**Studio MIDI** — l'appareil doit y figurer. S'il n'y est pas, le problème est
en amont de Charon.

---

## Pour développer : je reçois du SysEx nulle part en entrée

⚠️ **`rtmidi` ignore le SysEx en entrée par défaut.** Il faut
`midi_in.ignore_types(sysex=False)` juste après l'ouverture du port. Sans ça on
ne reçoit jamais rien, et on croit que l'envoi a échoué alors qu'il fonctionne.

C'est le piège qui coûte le plus de temps sur ce projet — il est commenté dans
`tests/test_midi_loopback.py`.
