"""Lecture de ``Decks.log`` : noms, ids et deckstrings des decks du joueur.

Format observé (session du 31/07/2026) :

    I 23:37:45.8505768 Deck Contents Received:
    I 23:37:45.8505768 ### bingo bis
    I 23:37:45.8505768 # Deck ID: 2174489721
    I 23:37:45.8505768 AAEBAYO6AgbtAuvw...

Le fichier peut contenir plusieurs blocs « Deck Contents Received » ;
le dernier vu pour un même Deck ID fait foi.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_LINE = re.compile(r"^[IDWE] [\d:.]+ (.*)$")


@dataclass
class PlayerDeck:
    name: str
    deck_id: int | None
    deckstring: str


def parse_decks_log(text: str) -> list[PlayerDeck]:
    decks: dict[str, PlayerDeck] = {}  # clé = deckstring ou deck_id
    current_name: str | None = None
    current_id: int | None = None

    for raw_line in text.splitlines():
        m = _LINE.match(raw_line.strip())
        if not m:
            continue
        payload = m.group(1).strip()

        if payload.startswith("### "):
            current_name = payload[4:].strip()
            current_id = None
        elif payload.startswith("# Deck ID:"):
            try:
                current_id = int(payload.split(":", 1)[1].strip())
            except ValueError:
                current_id = None
        elif payload.startswith("AAE") and current_name is not None:
            key = str(current_id) if current_id is not None else payload
            decks[key] = PlayerDeck(
                name=current_name, deck_id=current_id, deckstring=payload
            )
            current_name = None
            current_id = None

    return list(decks.values())


def read_decks_log(path: Path) -> list[PlayerDeck]:
    return parse_decks_log(path.read_text(encoding="utf-8", errors="replace"))


@dataclass
class QueueEvent:
    """« Finding Game With Deck: » — LE deck joué, horodaté à la mise en file."""

    ts: str  # HH:MM:SS.fffffff
    deck: PlayerDeck


_TS_LINE = re.compile(r"^[IDWE] ([\d:.]+) (.*)$")


class QueueParser:
    """Parseur incrémental des mises en file d'attente (pour le suivi live)."""

    def __init__(self) -> None:
        self._armed = False  # on vient de voir « Finding Game With Deck: »
        self._ts: str | None = None
        self._name: str | None = None
        self._deck_id: int | None = None

    def feed(self, raw_line: str) -> QueueEvent | None:
        m = _TS_LINE.match(raw_line.strip())
        if not m:
            return None
        ts, payload = m.group(1), m.group(2).strip()

        if payload.startswith("Finding Game With Deck"):
            self._armed, self._ts = True, ts
            self._name = self._deck_id = None
            return None
        if not self._armed:
            return None

        if payload.startswith("### "):
            self._name = payload[4:].strip()
        elif payload.startswith("# Deck ID:"):
            try:
                self._deck_id = int(payload.split(":", 1)[1].strip())
            except ValueError:
                self._deck_id = None
        elif payload.startswith("AAE") and self._name is not None:
            event = QueueEvent(
                ts=self._ts or ts,
                deck=PlayerDeck(name=self._name, deck_id=self._deck_id, deckstring=payload),
            )
            self._armed = False
            return event
        else:
            self._armed = False  # bloc interrompu par autre chose
        return None


def parse_queue_events(text: str) -> list[QueueEvent]:
    parser = QueueParser()
    events = []
    for line in text.splitlines():
        ev = parser.feed(line)
        if ev is not None:
            events.append(ev)
    return events
