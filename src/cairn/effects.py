"""Effets globaux en jeu — les « Global / Current effects » de Firestone.

Ce qui modifie durablement la partie sans être un serviteur : la Protection
d'Amara, l'Atlas de Godfrey, un pouvoir héroïque amélioré, une aura de coût…
Le joueur découvre sinon l'effet au moment où il le subit.

**Le critère est structurel, pas une liste de cartes.** Hearthstone attache
chaque enchantement à une entité (tag ``ATTACHED``) : collé à un serviteur,
c'est un buff local qui n'a rien à faire ici ; collé au JOUEUR, au HÉROS ou à
la PARTIE, c'est un effet global. Mesuré sur 68 parties : 287 enchantements de
serviteur contre 109 d'effets globaux, et 18 cartes distinctes seulement — la
liste blanche qu'on redoutait d'entretenir n'existe pas, et rien ne périmera à
la prochaine extension.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .cards_db import CardsDb
from .game_state import Game, PLAY

# Cibles qui font d'un enchantement un effet global. Un enchantement sur une
# ARME ou un LIEU reste local : il suit son objet, on le voit sur le plateau.
_GLOBAL_TARGETS = ("PLAYER", "HERO", "GAME")


@dataclass
class Effect:
    """Un effet global actif, groupé (« Âme brisée ×3 »)."""

    label: str
    card_id: str
    count: int = 1
    rarity: str = ""
    # Carte QUI a posé l'effet. C'est elle qu'il faut montrer au survol : le
    # texte propre à l'enchantement ne dit rien (« PV augmentés. », « Astuce
    # copiée. ») et il n'existe aucun rendu d'image pour un enchantement. La
    # carte source, elle, a son illustration ET son texte complet — « Âme
    # brisée » devient « Briseuse d'âme Azalina », ce qui répond vraiment à
    # « qu'est-ce que ça fait ? ».
    source_card_id: str = ""
    source_name: str = ""


# Un enchantement dérive presque toujours de sa carte par un suffixe (JAIL_430e1
# ← JAIL_430). Repli quand le tag CREATOR manque encore : HS ne le pose parfois
# qu'à la révélation.
_SUFFIX = re.compile(r"^(?P<base>.+?)(?:e\d*|t\d*)$")


def _source_of(game: Game, db: CardsDb, ent) -> str:
    creator = game.entities.get(ent.creator_entity_id or -1)
    if creator is not None and creator.card_id and creator.card_id in db.by_card_id:
        return creator.card_id
    m = _SUFFIX.match(ent.card_id or "")
    base = m.group("base") if m else ""
    return base if base in db.by_card_id else ""


def _attached_type(game: Game, entity) -> str:
    raw = entity.tags.get("ATTACHED")
    if not (raw and raw.isdigit()):
        return ""
    cible = game.entities.get(int(raw))
    return cible.tags.get("CARDTYPE", "") if cible else ""


def global_effects(game: Game, db: CardsDb, player_id: int | None) -> list[Effect]:
    """Effets globaux actifs chez un camp, du plus présent au moins présent."""
    if player_id is None:
        return []

    groupes: dict[str, Effect] = {}
    for ent in game.entities.values():
        if (
            ent.zone != PLAY
            or ent.controller != player_id
            or ent.tags.get("CARDTYPE") != "ENCHANTMENT"
            or not ent.card_id
        ):
            continue
        if _attached_type(game, ent) not in _GLOBAL_TARGETS:
            continue
        card = db.by_card_id.get(ent.card_id)
        if card is None:
            continue  # enchantement interne sans carte : rien à montrer
        deja = groupes.get(ent.card_id)
        if deja is not None:
            deja.count += 1
        else:
            source = _source_of(game, db, ent)
            groupes[ent.card_id] = Effect(
                label=card.get("name", ent.card_id),
                card_id=ent.card_id,
                rarity=card.get("rarity", ""),
                source_card_id=source,
                source_name=(db.by_card_id.get(source) or {}).get("name", ""),
            )
    return sorted(groupes.values(), key=lambda e: (-e.count, e.label))
