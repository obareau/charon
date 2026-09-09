"""Sortie MIDI réelle — la raison d'être de Charon.

Le loader d'AZA passe par la Web MIDI API, qui exige un contexte sécurisé :
en studio, devant la machine, ça oblige à sortir par le tunnel https pour
parler à un appareil posé sur le bureau. Ici on ouvre le port du système.

`python-rtmidi` couvre ALSA/JACK (Linux), CoreMIDI (macOS) et WinMM (Windows)
derrière la même interface.
"""
import time

import rtmidi


class MidiError(RuntimeError):
    pass


def backend_available() -> bool:
    """Le système offre-t-il seulement une couche MIDI ?

    Sur une machine Linux sans séquenceur ALSA — serveur, conteneur, runner
    d'intégration — l'ouverture échoue au lieu de rendre une liste vide.
    """
    try:
        out = rtmidi.MidiOut()
    except Exception:                      # noqa: BLE001 — dépend du système
        return False
    del out
    return True


def output_ports() -> list[str]:
    """Noms des ports de sortie, dans l'ordre où rtmidi les indexe.

    Renvoie une liste vide quand aucune couche MIDI n'est disponible : pas de
    système MIDI et aucun appareil branché sont, pour l'appelant, la même
    situation — rien où envoyer. C'est `send()` qui doit expliquer pourquoi,
    au moment où quelqu'un tente vraiment quelque chose.

    Recréé à chaque appel : un port apparaît ou disparaît au branchement, et
    une liste mise en cache ferait viser un index périmé.
    """
    try:
        out = rtmidi.MidiOut()
    except Exception:                      # noqa: BLE001 — dépend du système
        return []
    try:
        return list(out.get_ports())
    finally:
        del out


def send(port_index: int, messages, delay_ms: int = 200, progress=None) -> int:
    """Envoie des messages SysEx sur un port, et renvoie le nombre transmis.

    `delay_ms` sépare deux messages consécutifs. Ce n'est pas de la prudence
    superflue : un dump de 32 voix fait 4104 octets, soit ~1,3 s à 31250 bauds,
    et enchaîner sans laisser respirer la machine fait perdre des messages sur
    plusieurs Volca. On ne découpe jamais un message : un SysEx tronqué en vol
    n'est pas un SysEx, c'est du bruit que l'appareil rejette.

    `progress(i, total)` est appelé avant chaque envoi, pour l'interface.
    """
    messages = list(messages)
    if not messages:
        return 0

    try:
        out = rtmidi.MidiOut()
    except Exception as exc:               # noqa: BLE001 — dépend du système
        raise MidiError(
            "aucune couche MIDI disponible sur ce système "
            f"(ALSA absent ou inaccessible) : {exc}") from exc
    ports = out.get_ports()
    if not ports:
        del out
        raise MidiError("aucun port MIDI de sortie — la machine est-elle branchée et allumée ?")
    if not 0 <= port_index < len(ports):
        del out
        raise MidiError(f"port {port_index} inexistant ({len(ports)} port(s) disponibles)")

    sent = 0
    try:
        out.open_port(port_index)
        for i, msg in enumerate(messages):
            if progress:
                progress(i, len(messages))
            out.send_message(list(msg))
            sent += 1
            if i < len(messages) - 1 and delay_ms > 0:
                time.sleep(delay_ms / 1000.0)
    except Exception as exc:                       # noqa: BLE001 — remonté tel quel à l'UI
        raise MidiError(f"échec de l'envoi après {sent} message(s) : {exc}") from exc
    finally:
        try:
            out.close_port()
        finally:
            del out
    return sent
