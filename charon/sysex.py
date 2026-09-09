"""Lecture et validation des messages SysEx DX7 / Volca FM.

Le Volca FM accepte les dumps du DX7 : c'est le même format, hérité tel quel.
Deux tailles nous intéressent, et elles suffisent à identifier le contenu sans
rien deviner :

    4104 octets  bulk 32 voix   F0 43 0n 09 20 00 <4096 données> <somme> F7
     163 octets  voix seule     F0 43 0n 00 01 1B  <155 données> <somme> F7

Tout le reste est accepté et transmis tel quel, mais annoncé comme « brut » :
un SysEx inconnu n'est pas forcément invalide, il n'est simplement pas
interprétable ici.
"""
from dataclasses import dataclass

SOX = 0xF0          # début de message SysEx
EOX = 0xF7          # fin de message SysEx
YAMAHA = 0x43

BULK_SIZE = 4104
VOICE_SIZE = 163

# Position de l'octet qui porte le canal : F0 43 0n ...
CHANNEL_BYTE = 2


def split_messages(blob: bytes) -> list[bytes]:
    """Découpe un fichier en messages SysEx complets.

    Un `.syx` contient souvent plusieurs dumps à la suite. On isole chaque
    F0…F7 et on ignore ce qui traîne entre les messages — certains
    exportateurs intercalent des octets de rembourrage.
    """
    out, i, n = [], 0, len(blob)
    while i < n:
        start = blob.find(SOX, i)
        if start == -1:
            break
        end = blob.find(EOX, start + 1)
        if end == -1:                     # message tronqué : on s'arrête là
            break
        out.append(blob[start:end + 1])
        i = end + 1
    return out


def data_span(msg: bytes) -> tuple[int, int] | None:
    """Bornes [début, fin[ du bloc de données couvert par la somme de contrôle.

    Renvoie None si le message n'est pas un dump DX7 reconnu — on ne calcule
    pas une somme sur un format qu'on ne comprend pas.
    """
    if len(msg) == BULK_SIZE:
        return 6, 6 + 4096
    if len(msg) == VOICE_SIZE:
        return 6, 6 + 155
    return None


def expected_checksum(msg: bytes) -> int | None:
    """Somme de contrôle Yamaha : complément à deux du total, sur 7 bits."""
    span = data_span(msg)
    if span is None:
        return None
    start, end = span
    return (128 - (sum(msg[start:end]) & 0x7F)) & 0x7F


def stored_checksum(msg: bytes) -> int | None:
    """L'octet de somme tel qu'il figure dans le fichier (avant le F7 final)."""
    if data_span(msg) is None:
        return None
    return msg[-2]


def set_channel(msg: bytes, channel: int) -> bytes:
    """Réécrit le canal MIDI du message. `channel` est 1-16, comme sur la machine.

    L'octet 2 vaut (sous-statut << 4) | canal : on ne touche que le quartet bas,
    ce qui laisse le sous-statut intact. La somme de contrôle ne couvre que le
    bloc de données, jamais l'en-tête — la réécriture ne l'invalide donc pas.
    """
    if not 1 <= channel <= 16:
        raise ValueError("canal MIDI hors bornes (1-16)")
    if len(msg) <= CHANNEL_BYTE:
        return msg
    out = bytearray(msg)
    out[CHANNEL_BYTE] = (out[CHANNEL_BYTE] & 0xF0) | (channel - 1)
    return bytes(out)


@dataclass
class Message:
    """Un message SysEx, avec ce qu'on a pu en déduire."""
    raw: bytes
    index: int = 0

    @property
    def size(self) -> int:
        return len(self.raw)

    @property
    def is_yamaha(self) -> bool:
        return self.size >= 2 and self.raw[1] == YAMAHA

    @property
    def channel(self) -> int | None:
        """Canal MIDI annoncé, 1-16 — seulement pour un message Yamaha."""
        if not self.is_yamaha or self.size <= CHANNEL_BYTE:
            return None
        return (self.raw[CHANNEL_BYTE] & 0x0F) + 1

    @property
    def format_name(self) -> str:
        if self.size == BULK_SIZE:
            return "DX7 — bulk 32 voix"
        if self.size == VOICE_SIZE:
            return "DX7 — voix seule"
        return f"brut ({self.size} o)"

    @property
    def known(self) -> bool:
        return data_span(self.raw) is not None

    @property
    def well_formed(self) -> bool:
        return self.size >= 2 and self.raw[0] == SOX and self.raw[-1] == EOX

    @property
    def checksum_ok(self) -> bool | None:
        """True/False pour un dump reconnu, None si la somme n'est pas calculable."""
        exp = expected_checksum(self.raw)
        if exp is None:
            return None
        return exp == stored_checksum(self.raw)

    def status(self) -> str:
        if not self.well_formed:
            return "malformé"
        ok = self.checksum_ok
        if ok is None:
            return "non vérifiable"
        return "somme OK" if ok else "SOMME FAUSSE"


def read_file(path) -> list[Message]:
    """Lit un fichier et renvoie ses messages, dans l'ordre."""
    with open(path, "rb") as fh:
        blob = fh.read()
    return [Message(raw=m, index=i) for i, m in enumerate(split_messages(blob))]
