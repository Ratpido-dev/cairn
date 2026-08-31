#!/usr/bin/env python3
"""Affiche les decks du dernier Decks.log, décodés et résolus en noms frFR.

Usage : python tools/show_decks.py [--full]
Sert de test de bout en bout de la phase 0 :
Decks.log réel → deckstrings → dbfIds → base HearthstoneJSON.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cairn.cards_db import CardsDb  # noqa: E402
from src.cairn.decks_log import read_decks_log  # noqa: E402
from src.cairn.deckstring import DeckstringError, decode_deckstring  # noqa: E402
from src.cairn.paths import latest_session_dir  # noqa: E402

CLASS_FR = {
    "DEATHKNIGHT": "Chevalier de la mort", "DEMONHUNTER": "Chasseur de démons",
    "DRUID": "Druide", "HUNTER": "Chasseur", "MAGE": "Mage", "PALADIN": "Paladin",
    "PRIEST": "Prêtre", "ROGUE": "Voleur", "SHAMAN": "Chaman",
    "WARLOCK": "Démoniste", "WARRIOR": "Guerrier",
}


def main() -> None:
    full = "--full" in sys.argv
    session = latest_session_dir()
    if session is None or not (session / "Decks.log").is_file():
        sys.exit("Pas de Decks.log — lance Hearthstone au moins jusqu'au menu.")

    db = CardsDb.load()
    decks = read_decks_log(session / "Decks.log")
    print(f"{len(decks)} decks dans {session.name} (base : {len(db)} cartes frFR)\n")

    for deck_info in decks:
        try:
            deck = decode_deckstring(deck_info.deckstring)
        except DeckstringError as exc:
            print(f"✗ {deck_info.name} : ÉCHEC DÉCODAGE ({exc})")
            continue
        hero = db.by_dbf_id.get(deck.heroes[0], {}) if deck.heroes else {}
        klass = CLASS_FR.get(hero.get("cardClass", ""), hero.get("cardClass", "?"))
        unknown = sum(1 for dbf, _ in deck.cards if dbf not in db.by_dbf_id)
        flags = f", {len(deck.sideboards)} en sideboard" if deck.sideboards else ""
        warn = f"  ⚠ {unknown} dbfId inconnus" if unknown else ""
        print(f"✓ {deck_info.name} — {klass}, {deck.size} cartes{flags}{warn}")
        if full:
            for dbf, count in sorted(deck.cards, key=lambda c: (db.cost(c[0]) or 0, db.name(c[0]))):
                cost = db.cost(dbf)
                cost_s = f"{cost}" if cost is not None else "?"
                print(f"    {cost_s:>2}  {db.name(dbf)}  ×{count}")
            for dbf, count, owner in deck.sideboards:
                print(f"    ↳ sideboard de {db.name(owner)} : {db.name(dbf)} ×{count}")
            print()


if __name__ == "__main__":
    main()
