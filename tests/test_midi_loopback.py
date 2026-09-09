"""Test d'intégration : les octets traversent-ils vraiment un port MIDI ?

Passe par « Midi Through », le port de bouclage du noyau ALSA. Ignoré partout
où il n'existe pas (macOS, Windows, machine sans ALSA) — l'absence de matériel
n'est pas un échec.
"""
import threading
import time

import pytest

rtmidi = pytest.importorskip("rtmidi")

from charon.midi import output_ports, send          # noqa: E402
from charon.sysex import Message, SOX, EOX, set_channel  # noqa: E402


def _through(ports):
    return next((i for i, p in enumerate(ports) if "Through" in p), None)


def _loopback_index():
    """Index du port de bouclage, ou None — jamais d'exception à la collecte."""
    try:
        return _through(output_ports())
    except Exception:                      # noqa: BLE001 — ceinture et bretelles
        return None


def _bulk() -> bytes:
    data = bytes([(i * 7) & 0x7F for i in range(4096)])
    chk = (128 - (sum(data) & 0x7F)) & 0x7F
    return bytes([SOX, 0x43, 0x00, 0x09, 0x20, 0x00]) + data + bytes([chk, EOX])


@pytest.mark.skipif(_loopback_index() is None,
                    reason="pas de port MIDI de bouclage sur cette machine")
def test_un_dump_traverse_intact_et_le_canal_suit():
    bulk = _bulk()
    assert Message(bulk).checksum_ok is True

    out_idx = _through(output_ports())
    mi = rtmidi.MidiIn()
    in_idx = _through(mi.get_ports())
    mi.open_port(in_idx)
    mi.ignore_types(sysex=False)      # ⚠ rtmidi ignore le SysEx en entrée par défaut

    recu, stop = [], threading.Event()

    def pomper():
        while not stop.is_set():
            msg = mi.get_message()
            if msg:
                recu.append(bytes(msg[0]))
            else:
                time.sleep(0.002)

    t = threading.Thread(target=pomper, daemon=True)
    t.start()
    try:
        payloads = [bulk, set_channel(bulk, 5)]
        assert send(out_idx, payloads, delay_ms=150) == 2
        time.sleep(1.5)
    finally:
        stop.set()
        t.join()
        mi.close_port()
        del mi

    assert len(recu) == 2, f"{len(recu)} message(s) reçus au lieu de 2"
    assert recu == payloads, "les 4104 octets n'ont pas traversé à l'identique"
    assert Message(recu[1]).channel == 5
    assert Message(recu[1]).checksum_ok is True, "le canal forcé a cassé la somme"


def test_absence_de_couche_midi_rend_une_liste_vide(monkeypatch):
    """Sans séquenceur ALSA — serveur, conteneur, CI — on ne plante pas.

    « Pas de système MIDI » et « aucun appareil branché » sont la même
    situation pour l'appelant : rien où envoyer.
    """
    import charon.midi as m

    def explose():
        raise RuntimeError("MidiOutAlsa::initialize: error creating ALSA sequencer client object.")

    monkeypatch.setattr(m.rtmidi, "MidiOut", explose)
    assert m.output_ports() == []
    assert m.backend_available() is False


def test_send_explique_l_absence_de_couche_midi(monkeypatch):
    """send(), lui, doit dire pourquoi : quelqu'un tente vraiment quelque chose."""
    import charon.midi as m

    def explose():
        raise RuntimeError("pas d'ALSA ici")

    monkeypatch.setattr(m.rtmidi, "MidiOut", explose)
    with pytest.raises(m.MidiError, match="aucune couche MIDI"):
        m.send(0, [b"\xf0\x43\xf7"])
