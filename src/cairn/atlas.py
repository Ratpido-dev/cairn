"""Atlas de Godfrey : la file d'attente des cartes surpiochées.

« Godfrey, le traître » (JAIL_509) pose au début de partie un enchantement
« Atlas de Godfrey » (JAIL_509e). Tant qu'il est là, une carte piochée avec
10 cartes en main n'est plus défaussée : elle est mise de côté et rejoint la
main **dans l'ordre d'arrivée**, à 1 cristal de moins, dès qu'une place se
libère. C'est une information que le joueur ne peut pas deviner et qui décide
des fins de partie — d'où ce module.

Lecture du journal (vérifiée sur la partie du 02/08/2026, 01:26) : à chaque
surpioche, l'atlas crée DEUX entités en SETASIDE — la carte réelle (cachée
si elle appartient à l'adversaire) et une **copie révélée** qui sert de tuile
d'historique. C'est la copie qui donne l'identité : elle porte ``CREATOR`` =
l'atlas et ``COPIED_FROM_ENTITY_ID`` = la carte réelle. Et c'est la zone de la
carte réelle qui dit si elle attend encore (SETASIDE) ou si elle est déjà
passée en main. La carte d'origine, elle, part bien au cimetière (BURNED_CARD)
— ce n'est donc pas elle qu'il faut suivre.

Le mécanisme est symétrique : « Briseuse d'âme Azalina » copie les débuts de
partie adverses, si bien qu'on peut avoir son propre atlas face à un Démoniste
Godfrey. Les deux files se calculent avec le même code, camp par camp.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cards_db import CardsDb
from .game_state import Game, SETASIDE

GODFREY = "JAIL_509"
ATLAS_ENCHANTMENT = "JAIL_509e"
# Ce que l'atlas retire au coût de la carte quand elle arrive enfin en main.
ATLAS_DISCOUNT = 1


@dataclass
class AtlasCard:
    """Une carte en attente dans l'atlas, dans l'ordre où elle en sortira."""

    label: str  # nom de la carte, ou "" si elle n'a pas été révélée
    cost: int  # coût RÉDUIT, tel qu'elle arrivera en main
    card_id: str = ""
    rarity: str = ""
    known: bool = True


def _atlas_ids(game: Game, player_id: int | None) -> set[int]:
    """Entités « Atlas de Godfrey » d'un camp (deux si Azalina l'a copié)."""
    if player_id is None:
        return set()
    return {
        e.entity_id
        for e in game.entities.values()
        if e.card_id == ATLAS_ENCHANTMENT and e.controller == player_id
    }


def has_atlas(game: Game, player_id: int | None) -> bool:
    return bool(_atlas_ids(game, player_id))


def _int_tag(tags: dict[str, str], tag: str) -> int | None:
    raw = tags.get(tag)
    return int(raw) if raw is not None and raw.isdigit() else None


def queue(game: Game, db: CardsDb, player_id: int | None) -> list[AtlasCard]:
    """File d'attente d'un camp, première carte à revenir en tête.

    L'ordre de sortie suit l'ordre d'entrée (FIFO) : les entités HS étant
    numérotées dans l'ordre de création, l'id de la carte réelle donne cet
    ordre sans avoir à horodater quoi que ce soit.
    """
    atlas = _atlas_ids(game, player_id)
    if not atlas:
        return []

    queued: list[tuple[int, AtlasCard]] = []
    for ent in game.entities.values():
        if ent.creator_entity_id not in atlas:
            continue
        real_id = _int_tag(ent.tags, "COPIED_FROM_ENTITY_ID")
        if real_id is None:
            continue  # l'enchantement « Coût −1 » de l'atlas, pas une carte
        real = game.entities.get(real_id)
        if real is None or real.zone != SETASIDE:
            continue  # déjà partie en main (ou jamais mise de côté)
        card = db.by_card_id.get(ent.card_id or "")
        base = _int_tag(ent.tags, "COST")
        if base is None:
            base = (card.get("cost") or 0) if card else 0
        queued.append(
            (
                real_id,
                AtlasCard(
                    label=card.get("name", "") if card else "",
                    cost=max(0, base - ATLAS_DISCOUNT),
                    card_id=ent.card_id or "",
                    rarity=(card.get("rarity", "") if card else ""),
                    known=card is not None,
                ),
            )
        )
    return [card for _, card in sorted(queued, key=lambda pair: pair[0])]


def revealed(game: Game, player_id: int | None) -> dict[int, str]:
    """Identités que l'atlas a montrées : entity_id de la carte RÉELLE → card_id.

    ``queue`` s'arrête à ce qui attend encore en SETASIDE, ce qui est juste
    pour afficher la file. Mais la copie révélée, elle, ne disparaît pas quand
    la carte rejoint la main : son ``COPIED_FROM_ENTITY_ID`` continue de
    désigner la carte réelle, et son ``card_id`` de la nommer.

    Sans cette relecture, une carte qu'on a VUE entrer dans l'atlas
    redevenait « ? carte cachée » à la seconde où l'adversaire la récupérait —
    c'est-à-dire au moment où savoir ce qu'il tient devient utile.
    """
    atlas = _atlas_ids(game, player_id)
    if not atlas:
        return {}
    connues: dict[int, str] = {}
    for ent in game.entities.values():
        if ent.creator_entity_id not in atlas or not ent.card_id:
            continue
        real_id = _int_tag(ent.tags, "COPIED_FROM_ENTITY_ID")
        if real_id is None:
            continue  # l'enchantement « Coût −1 » de l'atlas, pas une carte
        connues[real_id] = ent.card_id
    return connues
