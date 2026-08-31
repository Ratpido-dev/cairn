"""Familles de cartes à cocher — « quels Rafaam ai-je déjà posés ? ».

Certaines cartes ne valent que par la collection qu'elles forment : le deck de
40 de Rafaam contient dix Rafaam distincts et sa condition létale est de les
avoir tous joués ; les trois sœurs Coursevent se cherchent l'une l'autre. Un
compteur « 7/9 » dit *combien*, jamais *lesquels* — or c'est lesquels qui
décide du tour à jouer.

Les membres sont dérivés de la base de cartes par motif d'identifiant, jamais
listés à la main : une extension qui ajoute une variante l'ajoute ici toute
seule, sans patch.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .cards_db import CardsDb
from .game_state import Game, Play


@dataclass(frozen=True)
class FamilyDef:
    key: str
    # Motif ANCRÉ sur l'identifiant : « TIME_005t9t » (un jeton créé par le
    # neuvième Rafaam) n'est pas un Rafaam, seul « t<chiffre> » l'est.
    pattern: str


FAMILY_DEFS: tuple[FamilyDef, ...] = (
    # Rafaam, le voleur de temps : lui + ses neuf variantes (coûts 1 à 10)
    FamilyDef(key="rafaam", pattern=r"TIME_005(t[1-9])?"),
    # Sœurs Coursevent : Sylvanas, Alleria, Vereesa
    FamilyDef(key="windrunner", pattern=r"TIME_609(t[12])?"),
)


@dataclass
class FamilyCard:
    card_id: str
    label: str
    cost: int
    played: bool
    rarity: str = ""


@dataclass
class Family:
    key: str
    cards: list[FamilyCard]

    @property
    def played(self) -> int:
        return sum(1 for c in self.cards if c.played)

    @property
    def total(self) -> int:
        return len(self.cards)


def members(db: CardsDb, definition: FamilyDef) -> list[dict]:
    """Cartes de la famille, du moins chère à la plus chère."""
    rx = re.compile(definition.pattern + r"$")
    found = [
        c for cid, c in db.by_card_id.items()
        if rx.match(cid) and c.get("type") == "MINION" and c.get("cost") is not None
    ]
    return sorted(found, key=lambda c: (c.get("cost", 0), c.get("name", "")))


def _played_ids(game: Game, player_id: int | None) -> set[str]:
    return {
        ev.card_id for ev in game.events
        if isinstance(ev, Play) and ev.player_id == player_id and ev.card_id
    }


def checklist(
    game: Game,
    db: CardsDb,
    player_id: int | None,
    definition: FamilyDef,
    lang: str = "fr",
) -> Family | None:
    """Coche la famille pour un camp — ``None`` si elle ne le concerne pas.

    « Concerne » = au moins un membre a été vu chez lui. Même règle que les
    compteurs contextuels : rien ne s'affiche sur la foi de la classe seule.
    """
    if player_id is None:
        return None
    cards = members(db, definition)
    if not cards:
        return None
    ids = {c["id"] for c in cards}
    seen = {
        e.card_id for e in game.entities.values()
        if e.card_id in ids and e.controller == player_id
    }
    if not seen:
        return None
    played = _played_ids(game, player_id)
    return Family(
        key=definition.key,
        cards=[
            FamilyCard(
                card_id=c["id"],
                label=db.localized_name(c["id"], lang) or c.get("name", c["id"]),
                cost=c.get("cost", 0) or 0,
                played=c["id"] in played,
                rarity=c.get("rarity", ""),
            )
            for c in cards
        ],
    )


def all_checklists(
    game: Game, db: CardsDb, player_id: int | None, lang: str = "fr"
) -> list[Family]:
    found = (checklist(game, db, player_id, d, lang) for d in FAMILY_DEFS)
    return [f for f in found if f is not None]
