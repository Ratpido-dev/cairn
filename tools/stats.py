#!/usr/bin/env python3
"""Winrates par deck + dernières parties, depuis l'historique local (F6).

Usage : python tools/stats.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cairn.history import History, default_db_path  # noqa: E402

RESULT = {"WON": "✓", "LOST": "✗", "TIED": "="}


def main() -> None:
    if not default_db_path().is_file():
        sys.exit("Pas encore d'historique — joue une partie avec le panneau ouvert.")
    history = History()

    stats = history.deck_stats()
    if stats:
        width = max(len(s.deck_name) for s in stats)
        print("── Winrates par deck ──")
        for s in stats:
            print(f"  {s.deck_name:<{width}}  {s.wins}/{s.games}  ({s.winrate:.0%})")

    from src.cairn.deck_view import CLASS_FR

    by_class = history.class_stats()
    if by_class:
        print("\n── Winrates par classe adverse ──")
        for klass, games, wins in by_class:
            label = CLASS_FR.get(klass, klass)
            print(f"  vs {label:<22}  {wins}-{games - wins}  ({wins / games:.0%})")

    recent = history.recent(limit=10)
    if recent:
        print("\n── Dernières parties ──")
        for played_on, ts, deck_name, opponent, result, turns, klass in recent:
            hour = (ts or "")[:5]
            label = CLASS_FR.get(klass or "", "?")
            print(f"  {played_on} {hour}  {RESULT.get(result, '?')} {deck_name or '?'} "
                  f"vs {opponent or '?'} [{label}] ({turns} tours)")
    history.close()


if __name__ == "__main__":
    main()
