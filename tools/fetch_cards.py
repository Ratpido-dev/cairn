#!/usr/bin/env python3
"""Télécharge la base de cartes HearthstoneJSON.

Usage : python tools/fetch_cards.py [frFR|enUS|all] [--with-bg]  (défaut : all)
Simple raccourci vers `cairn.cards_fetch` (aussi installé sous `cairn-cards`).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cairn.cards_fetch import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
