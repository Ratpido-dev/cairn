"""Rattrapage : renseigne l'archétype des parties déjà enregistrées.

L'historique ne garde que des métadonnées ; l'archétype se lit dans les cartes,
donc dans les journaux archivés. Ce script rejoue les archives et complète la
base pour les parties qu'il retrouve — les autres gardent un archétype vide,
ce qui est le comportement voulu (vide = pas reconnu, jamais deviné).

Usage : python tools/backfill_archetypes.py [--dry-run]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from src.cairn import archetypes                      # noqa: E402
from src.cairn.cards_db import CardsDb                # noqa: E402
from src.cairn.config import Config                   # noqa: E402
from src.cairn.deck_view import opponent_class        # noqa: E402
from src.cairn.game_state import replay_file          # noqa: E402
from src.cairn.deck_refs import DeckRefs              # noqa: E402
from src.cairn.history import History                 # noqa: E402
from src.cairn.paths import SESSIONS_DIR              # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    a_blanc = "--dry-run" in argv
    db = CardsDb.load()
    compte = Config.load().own_account
    hist = History()
    refs = DeckRefs()   # listes collées par l'utilisateur

    trouves = poses = 0
    for dossier in sorted(SESSIONS_DIR.iterdir()):
        journaux = list(dossier.glob("Power.log*")) if dossier.is_dir() else []
        for journal in journaux:
            try:
                parties = replay_file(journal)
            except Exception as err:
                print(f"  ! {dossier.name} illisible : {err}")
                continue
            for index, game in enumerate(parties):
                if game.is_spectated(compte) or not game.complete:
                    continue
                local = game.local_player_id(compte)
                if local is None:
                    continue
                adv = next((p for p in game.player_names if p != local), None)
                klass = opponent_class(game, db)
                arch = archetypes.detect(game, db, adv, klass, refs=refs)
                trouves += 1
                if not a_blanc:
                    # concession : le journal la donne explicitement
                    mon_nom = game.player_names.get(local, "")
                    qui = ("me" if game.conceded_by == mon_nom
                           else "opp" if game.conceded_by else "")
                    hist.set_concede(dossier.name, index, qui, game.conceded_turn)
                if not arch:
                    continue
                poses += 1
                if not a_blanc:
                    hist.set_archetype(dossier.name, index, arch)

    print(f"{trouves} parties rejouées · {poses} archétypes reconnus"
          + (" (essai à blanc, rien écrit)" if a_blanc else " et écrits"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
