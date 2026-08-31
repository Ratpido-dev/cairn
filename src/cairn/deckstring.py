"""Décodage des deckstrings Hearthstone (format officiel Blizzard).

Un deckstring est un blob base64 de varints :
``[0, version, format, héros..., cartes ×1, cartes ×2, cartes ×N, sideboards?]``
Les identifiants sont des dbfId (référencés par HearthstoneJSON).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from io import BytesIO

# format (mode de jeu) du deck
FORMAT_WILD = 1
FORMAT_STANDARD = 2
FORMAT_CLASSIC = 3
FORMAT_TWIST = 4


class DeckstringError(ValueError):
    """Deckstring illisible ou corrompu."""


@dataclass
class Deck:
    fmt: int
    heroes: list[int]
    cards: list[tuple[int, int]]  # (dbfId, quantité)
    # cartes de sideboard (E.T.C., Zilliax…) : (dbfId, quantité, dbfId du propriétaire)
    sideboards: list[tuple[int, int, int]] = field(default_factory=list)

    @property
    def size(self) -> int:
        return sum(count for _, count in self.cards)


def _read_varint(stream: BytesIO) -> int:
    """Varint LEB128 non signé."""
    result = 0
    shift = 0
    while True:
        raw = stream.read(1)
        if not raw:
            raise DeckstringError("fin de flux inattendue dans un varint")
        byte = raw[0]
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result
        shift += 7
        if shift > 63:
            raise DeckstringError("varint trop long")


def decode_deckstring(deckstring: str) -> Deck:
    """Décode un deckstring base64 en :class:`Deck`.

    Gère les sideboards (marqueur ``0x01`` après les blocs de cartes),
    introduits avec E.T.C. / Zilliax.
    """
    try:
        raw = base64.b64decode(deckstring.strip(), validate=True)
    except Exception as exc:  # binascii.Error selon la version
        raise DeckstringError(f"base64 invalide : {exc}") from exc

    data = BytesIO(raw)
    if _read_varint(data) != 0:
        raise DeckstringError("octet réservé non nul en tête")
    version = _read_varint(data)
    if version != 1:
        raise DeckstringError(f"version de deckstring inconnue : {version}")
    fmt = _read_varint(data)

    heroes = [_read_varint(data) for _ in range(_read_varint(data))]

    cards: list[tuple[int, int]] = []
    for copies in (1, 2, 3):
        for _ in range(_read_varint(data)):
            dbf_id = _read_varint(data)
            count = _read_varint(data) if copies == 3 else copies
            cards.append((dbf_id, count))

    sideboards: list[tuple[int, int, int]] = []
    marker = data.read(1)
    if marker == b"\x01":
        for copies in (1, 2, 3):
            for _ in range(_read_varint(data)):
                dbf_id = _read_varint(data)
                count = _read_varint(data) if copies == 3 else copies
                owner = _read_varint(data)
                sideboards.append((dbf_id, count, owner))

    return Deck(fmt=fmt, heroes=heroes, cards=cards, sideboards=sideboards)
