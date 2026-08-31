#!/usr/bin/env python3
"""Suivi live d'une session Hearthstone dans le terminal.

Usage : python tools/live.py   (Ctrl-C pour quitter)
Lance-le avant ou après HS, peu importe : il attend le jeu, suit la partie
en cours et affiche pioches, cartes jouées et entrées de deck en direct.
C'est la préfiguration en mode texte de l'UI de la phase 2.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cairn.cards_db import CardsDb  # noqa: E402
from src.cairn.game_state import DeckEntry, Draw, Play  # noqa: E402
from src.cairn.log_watcher import LiveTracker  # noqa: E402

POLL_S = 0.5


def main() -> None:
    db = CardsDb.load()

    def label(card_id):
        if not card_id:
            return "?"
        card = db.by_card_id.get(card_id)
        return card["name"] if card else card_id

    # from_start=False : en (re)lançant l'outil pendant une session déjà
    # entamée, on ne rejoue pas tout le passé — on suit ce qui arrive.
    tracker = LiveTracker(from_start=False)
    print("Cairn — suivi live (Ctrl-C pour quitter). En attente de Hearthstone…")

    try:
        while True:
            update = tracker.poll()
            if update.session_switched:
                print(f"\n■ Session : {update.session_switched.name}")
            for _ in update.new_games:
                print("\n■ Nouvelle partie !")
            game = tracker.current_game
            local = game.local_player_id() if game else None
            for ev in update.events:
                mine = local is not None and ev.player_id == local
                who = "moi" if mine else "adv"
                if isinstance(ev, Draw) and not ev.during_mulligan:
                    print(f"  🂠 [{who}] pioche : {label(ev.card_id)}")
                elif isinstance(ev, Play):
                    print(f"  ▶ [{who}] joue : {label(ev.card_id)}")
                elif isinstance(ev, DeckEntry):
                    kind = "entre dans le deck" if ev.created else "retourne au deck"
                    origin = f" ← {label(ev.creator_card_id)}" if ev.creator_card_id else ""
                    print(f"  ⤵ [{who}] {label(ev.card_id)} {kind}{origin}")
            if game and game.complete and update.events:
                name = game.player_names.get(local, "")
                verdict = game.results.get(name, "?")
                print(f"■ Fin de partie : {verdict}")
            time.sleep(POLL_S)
    except KeyboardInterrupt:
        print("\nÀ la prochaine.")


if __name__ == "__main__":
    main()
