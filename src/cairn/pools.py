"""Pools de résurrection : ce qu'une carte peut réellement ramener.

Certaines cartes ne ressuscitent pas n'importe quoi — elles piochent dans les
serviteurs **déjà morts (ou déjà joués) pendant cette partie**, filtrés par
coût et par mécanique. Impossible à deviner de tête en jeu : ce module calcule
le pool exact, affiché au survol de la carte dans le tracker.

Ajouter une carte = une ligne dans ``POOL_DEFS`` (aucune autre modification).
"""

from __future__ import annotations

from collections import Counter as _Counter
from dataclasses import dataclass
from typing import Callable

from .cards_db import CardsDb
from .game_state import Death, Game, Play
from .i18n import t


@dataclass(frozen=True)
class PoolDef:
    """Une carte à pool. ``source`` : d'où viennent les candidats.

    - ``deaths``  : serviteurs alliés morts pendant la partie
    - ``played``  : serviteurs alliés joués pendant la partie
    """

    label_key: str          # clé i18n
    label_arg: int          # le coût cité dans le libellé
    source: str
    predicate: Callable[[dict, CardsDb], bool]


def _dr(card: dict, db: CardsDb) -> bool:
    return db.has_deathrattle(card.get("id"))


def _cost(card: dict) -> int:
    return card.get("cost") or 0


# Les ids sont ceux de HearthstoneJSON (cf. tools/fetch_cards.py).
POOL_DEFS: dict[str, PoolDef] = {
    # Chasseur de démons — Rêve d'émeraude
    "EDR_891": PoolDef(  # Chasseur corrompu vorace, 5 mana 5/3
        label_key="pool_dr_max", label_arg=4,
        source="deaths",
        predicate=lambda c, db: _dr(c, db) and _cost(c) <= 4,
    ),
    "EDR_892": PoolDef(  # Gangroptère féroce, 7 mana 7/5
        label_key="pool_dr_min", label_arg=5,
        source="deaths",
        predicate=lambda c, db: _dr(c, db) and _cost(c) >= 5,
    ),
    "MIS_102": PoolDef(  # Politique de retour, 3 mana — découvre parmi les JOUÉS
        label_key="pool_dr_played", label_arg=0,
        source="played",
        predicate=_dr,
    ),
}


@dataclass
class PoolEntry:
    name: str
    cost: int
    count: int
    card_id: str


def pool_for(
    game: Game, db: CardsDb, card_id: str, player_id: int | None, lang: str = "fr"
) -> tuple[str, list[PoolEntry]]:
    """(libellé, candidats) pour la carte survolée — ``("", [])`` si sans objet.

    ``player_id`` = le propriétaire de la carte : une résurrection ne ramène
    que SES serviteurs.
    """
    pool_def = POOL_DEFS.get(card_id or "")
    if pool_def is None or player_id is None:
        return ("", [])

    wanted = Death if pool_def.source == "deaths" else Play
    counts: _Counter[str] = _Counter()
    for ev in game.events:
        if not isinstance(ev, wanted) or ev.player_id != player_id or not ev.card_id:
            continue
        card = db.by_card_id.get(ev.card_id)
        if card is None or card.get("type") != "MINION":
            continue
        if pool_def.predicate(card, db):
            counts[ev.card_id] += 1

    entries = [
        PoolEntry(
            name=db.localized_name(cid, lang),
            cost=_cost(db.by_card_id[cid]),
            count=n,
            card_id=cid,
        )
        for cid, n in counts.items()
    ]
    entries.sort(key=lambda e: (e.cost, e.name))
    return (t(pool_def.label_key, lang, n=pool_def.label_arg), entries)
