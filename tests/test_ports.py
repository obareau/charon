"""Étiquetage des interfaces MIDI.

Un port de bouclage n'est pas une machine : y envoyer un dump ne va nulle part.
Le signaler dans la liste évite le quart d'heure passé à chercher pourquoi le
Volca ne réagit pas. Aucun import Qt : ce test tourne sans écran.
"""
import pytest

from charon.app import port_label


@pytest.mark.parametrize("nom", [
    "Midi Through:Midi Through Port-0 14:0",   # Linux / ALSA
    "IAC Driver Bus 1",                        # macOS
    "loopMIDI Port",                           # Windows
    "LoopBe Internal MIDI",                    # Windows
])
def test_les_bouclages_sont_signales(nom):
    etiquette = port_label(nom)
    assert etiquette.startswith(nom), "le nom réel doit rester lisible en tête"
    assert "bouclage" in etiquette


@pytest.mark.parametrize("nom", [
    "Volca FM:Volca FM MIDI 1",
    "USB MIDI Interface",
    "Elektron Digitakt",
])
def test_une_vraie_interface_nest_pas_annotee(nom):
    assert port_label(nom) == nom
