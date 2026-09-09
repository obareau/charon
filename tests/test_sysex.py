"""Tests du noyau SysEx — formats DX7, sommes de contrôle, canal."""
from charon.sysex import (
    Message, split_messages, expected_checksum, set_channel,
    BULK_SIZE, VOICE_SIZE, SOX, EOX,
)


def _dump(header: bytes, data_len: int, filler: int = 0) -> bytes:
    """Fabrique un dump DX7 valide, somme de contrôle comprise."""
    data = bytes([filler] * data_len)
    chk = (128 - (sum(data) & 0x7F)) & 0x7F
    return header + data + bytes([chk, EOX])


BULK_HEADER = bytes([SOX, 0x43, 0x00, 0x09, 0x20, 0x00])
VOICE_HEADER = bytes([SOX, 0x43, 0x00, 0x00, 0x01, 0x1B])


def test_bulk_dump_reconnu_et_valide():
    m = Message(_dump(BULK_HEADER, 4096, filler=3))
    assert m.size == BULK_SIZE
    assert m.format_name == "DX7 — bulk 32 voix"
    assert m.well_formed and m.known
    assert m.checksum_ok is True
    assert m.status() == "somme OK"


def test_voix_seule_reconnue():
    m = Message(_dump(VOICE_HEADER, 155, filler=7))
    assert m.size == VOICE_SIZE
    assert m.format_name == "DX7 — voix seule"
    assert m.checksum_ok is True


def test_somme_fausse_detectee_avant_envoi():
    """Un octet de somme corrompu doit se voir — c'est tout l'intérêt du contrôle."""
    raw = bytearray(_dump(BULK_HEADER, 4096))
    raw[-2] = (raw[-2] + 1) & 0x7F
    m = Message(bytes(raw))
    assert m.checksum_ok is False
    assert m.status() == "SOMME FAUSSE"


def test_format_inconnu_transmis_sans_verdict():
    """Un SysEx non-DX7 n'est pas invalide : il est seulement non vérifiable."""
    m = Message(bytes([SOX, 0x7D, 0x01, 0x02, EOX]))
    assert not m.known
    assert m.checksum_ok is None
    assert m.status() == "non vérifiable"
    assert m.format_name == "brut (5 o)"


def test_message_malforme():
    m = Message(bytes([SOX, 0x43, 0x00]))       # pas de F7
    assert not m.well_formed
    assert m.status() == "malformé"


def test_split_plusieurs_messages_et_rembourrage():
    """Plusieurs dumps a la suite, avec des octets parasites entre eux."""
    a = _dump(VOICE_HEADER, 155, filler=1)
    b = _dump(VOICE_HEADER, 155, filler=2)
    blob = b"\x00\x00" + a + b"\xff" + b + b"\x00"
    msgs = split_messages(blob)
    assert len(msgs) == 2
    assert msgs[0] == a and msgs[1] == b


def test_split_ignore_un_message_tronque():
    a = _dump(VOICE_HEADER, 155)
    msgs = split_messages(a + bytes([SOX, 0x43, 0x00]))   # second sans F7
    assert len(msgs) == 1


def test_set_channel_change_le_canal_sans_casser_la_somme():
    """Le canal vit dans l'en-tete ; la somme ne couvre que les donnees."""
    orig = _dump(BULK_HEADER, 4096, filler=5)
    m0 = Message(orig)
    assert m0.channel == 1

    for ch in (1, 5, 16):
        moved = Message(set_channel(orig, ch))
        assert moved.channel == ch
        assert moved.checksum_ok is True, "la somme doit rester valide"
        assert moved.size == m0.size
        assert moved.raw[6:] == orig[6:], "les donnees ne doivent pas bouger"


def test_set_channel_preserve_le_sous_statut():
    """L'octet porte (sous-statut << 4) | canal : seul le quartet bas change."""
    raw = bytearray(_dump(VOICE_HEADER, 155))
    raw[2] = 0x10 | 0x03            # sous-statut 1, canal 4
    moved = set_channel(bytes(raw), 9)
    assert moved[2] == 0x10 | 0x08  # sous-statut intact, canal 9


def test_set_channel_refuse_hors_bornes():
    raw = _dump(VOICE_HEADER, 155)
    for bad in (0, 17, -1):
        try:
            set_channel(raw, bad)
        except ValueError:
            continue
        raise AssertionError(f"canal {bad} aurait du etre refuse")


def test_checksum_non_calculable_sur_taille_inconnue():
    assert expected_checksum(bytes([SOX, 0x43, 0x00, EOX])) is None
