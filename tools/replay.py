#!/usr/bin/env python3
"""Rejoue un Power.log et raconte chaque partie (noms de cartes frFR).

Usage :
    python tools/replay.py                    # dernière fixture archivée
    python tools/replay.py <chemin/Power.log> # un log précis
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cairn.cards_db import CardsDb  # noqa: E402
from src.cairn.game_state import DeckEntry, Draw, Play, replay_file  # noqa: E402
from src.cairn.paths import FIXTURES_DIR  # noqa: E402

RESULT_FR = {"WON": "VICTOIRE", "LOST": "défaite", "TIED": "égalité"}


def card_label(db: CardsDb, card_id: str | None) -> str:
    if not card_id:
        return "? (carte cachée)"
    card = db.by_card_id.get(card_id)
    return card["name"] if card else card_id


def main() -> None:
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        fixtures = sorted(FIXTURES_DIR.glob("*/Power.log"))
        if not fixtures:
            sys.exit("Aucune fixture — lance tools/archive_fixtures.py après une partie.")
        path = fixtures[-1]

    db = CardsDb.load()
    games = replay_file(path)
    print(f"{path}\n{len(games)} partie(s)\n")

    for i, game in enumerate(games, 1):
        local = game.local_player_id()
        local_name = game.player_names.get(local, "?") if local else "?"
        opponent = next(
            (n for n in game.results if n != local_name),
            next((n for p, n in game.player_names.items() if p != local), "?"),
        )
        result = RESULT_FR.get(game.results.get(local_name, ""), "— interrompue —")
        hero = game.hero_card_id(local) if local else None

        print(f"══ Partie {i} : {result} contre {opponent}")
        print(f"   {game.game_type}/{game.format_type}, {game.turns} tours, héros {card_label(db, hero)}")

        draws = [e for e in game.events if isinstance(e, Draw) and e.player_id == local]
        mulligan = [d for d in draws if d.during_mulligan]
        print(f"   Main de départ : {', '.join(card_label(db, d.card_id) for d in mulligan) or '?'}")
        print(f"   {len(draws) - len(mulligan)} pioches ensuite, "
              f"{sum(1 for e in game.events if isinstance(e, Play) and e.player_id == local)} cartes jouées")

        entries = [e for e in game.events if isinstance(e, DeckEntry)]
        if entries:
            print(f"   ⤵ {len(entries)} entrée(s) de deck :")
            for entry in entries:
                who = "moi" if entry.player_id == local else "adv"
                origin = f" ← {card_label(db, entry.creator_card_id)}" if entry.creator_card_id else ""
                kind = "créée" if entry.created else "renvoyée"
                print(f"      [{who}] {card_label(db, entry.card_id)} ({kind}){origin}")
        print()


if __name__ == "__main__":
    main()
