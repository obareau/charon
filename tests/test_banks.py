"""Tests de l'atelier : découper deux banks, en recomposer une troisième."""
import pytest

from charon.sysex import (
    Message, voices, voice_name, build_bank, BULK_HEADER, EMPTY_VOICE,
    BULK_SIZE, VOICES_PER_BANK, PACKED_VOICE_SIZE, NAME_OFFSET, EOX,
)


def _voice(nom: str, remplissage: int) -> bytes:
    """Une voix compressée reconnaissable : contenu constant + nom lisible."""
    v = bytearray([remplissage & 0x7F] * PACKED_VOICE_SIZE)
    v[NAME_OFFSET:NAME_OFFSET + 10] = nom.ljust(10)[:10].encode("ascii")
    return bytes(v)


def _bank(prefixe: str) -> bytes:
    return build_bank([_voice(f"{prefixe}{i:02d}", i) for i in range(VOICES_PER_BANK)])


def test_bank_construite_est_un_bulk_valide():
    b = _bank("A")
    m = Message(b)
    assert m.size == BULK_SIZE
    assert m.format_name == "DX7 — bulk 32 voix"
    assert m.checksum_ok is True, "la somme doit être recalculée à l'assemblage"
    assert b.startswith(BULK_HEADER[:2]) and b[-1] == EOX


def test_les_32_voix_se_relisent_dans_l_ordre():
    b = _bank("A")
    vs = voices(b)
    assert len(vs) == VOICES_PER_BANK
    assert [voice_name(v) for v in vs] == [f"A{i:02d}" for i in range(32)]


def test_piocher_dans_deux_banks_pour_en_faire_une_troisieme():
    """Le cas d'usage réel : 16 voix de A, 16 de B, dans un ordre choisi."""
    a, b = _bank("A"), _bank("B")
    va, vb = voices(a), voices(b)

    choix = [va[i] for i in range(0, 32, 2)][:16] + [vb[i] for i in range(1, 32, 2)][:16]
    c = build_bank(choix)

    assert Message(c).checksum_ok is True
    noms = [voice_name(v) for v in voices(c)]
    assert noms[:16] == [f"A{i:02d}" for i in range(0, 32, 2)]
    assert noms[16:] == [f"B{i:02d}" for i in range(1, 32, 2)]
    # les octets des voix doivent être repris tels quels, pas réencodés
    assert voices(c)[0] == va[0]
    assert voices(c)[16] == vb[1]


def test_moins_de_32_voix_comble_avec_une_voix_muette():
    c = build_bank([_voice("SEULE", 9)])
    assert Message(c).checksum_ok is True
    vs = voices(c)
    assert voice_name(vs[0]) == "SEULE"
    assert all(v == EMPTY_VOICE for v in vs[1:]), "les emplacements libres sont comblés"
    assert voice_name(vs[1]) == "INIT"


def test_refus_au_dela_de_32_voix():
    with pytest.raises(ValueError, match="33"):
        build_bank([_voice("X", 1)] * 33)


def test_refus_dune_voix_de_mauvaise_taille():
    with pytest.raises(ValueError, match="voix 1"):
        build_bank([b"\x00" * 100])


def test_voices_refuse_ce_qui_nest_pas_un_bulk():
    with pytest.raises(ValueError, match="pas un bulk"):
        voices(b"\xf0\x43\x00\xf7")


def test_canal_applique_a_la_bank_assemblee():
    c = build_bank([_voice("X", 1)], channel=7)
    m = Message(c)
    assert m.channel == 7
    assert m.checksum_ok is True, "forcer le canal ne doit pas casser la somme"


def test_nom_nettoye_des_caracteres_non_imprimables():
    v = bytearray(_voice("OK", 1))
    v[NAME_OFFSET + 3] = 0x01          # caractère de contrôle au milieu du nom
    assert "\x01" not in voice_name(bytes(v))
