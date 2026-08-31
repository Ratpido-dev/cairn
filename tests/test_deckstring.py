"""Tests du décodeur de deckstrings — sur des deckstrings réels du joueur.

Les chaînes ci-dessous viennent du Decks.log du 31/07/2026 (session
Hearthstone_2026_07_31_23_37_18).
"""

import pytest

from src.cairn.deckstring import Deck, DeckstringError, decode_deckstring

# « bingo bis » — ancien format (préfixe AAEB…, sans sideboard)
BINGO_BIS = (
    "AAEBAYO6AgbtAuvwAqH5A/uKBNi2BNu5BAyq6wP+7gOh9AO9gAT3nwS6pAT7pQTspwT5rASZtgTVtgT58QQAAA=="
)
# « troublemaker » — format récent (préfixe AAEC…)
TROUBLEMAKER = (
    "AAECAcH1BgiXoATNngaGqAeHqAeIqAe0wQeI2QeI3QcL958E0J4G2aIG94EHwZcHmrMH+cMH1cUHjdoHv/cH5fcHAAA="
)


def test_decode_bingo_bis_30_cartes():
    deck = decode_deckstring(BINGO_BIS)
    assert isinstance(deck, Deck)
    assert deck.size == 30
    assert len(deck.heroes) == 1
    # 6 cartes ×1 + 12 cartes ×2 = 30
    singles = [c for c in deck.cards if c[1] == 1]
    doubles = [c for c in deck.cards if c[1] == 2]
    assert len(singles) == 6
    assert len(doubles) == 12


def test_decode_troublemaker_30_cartes():
    deck = decode_deckstring(TROUBLEMAKER)
    assert deck.size == 30
    assert len(deck.heroes) == 1
    assert all(dbf > 0 for dbf, _ in deck.cards)


def test_dbf_ids_croissants_par_bloc():
    # Blizzard trie les dbfId croissants à l'intérieur de chaque bloc :
    # bonne vérification d'un décodage varint correct.
    deck = decode_deckstring(BINGO_BIS)
    singles = [dbf for dbf, n in deck.cards if n == 1]
    doubles = [dbf for dbf, n in deck.cards if n == 2]
    assert singles == sorted(singles)
    assert doubles == sorted(doubles)


def test_base64_invalide():
    with pytest.raises(DeckstringError):
        decode_deckstring("pas-un-deckstring!!")


def test_flux_tronque():
    with pytest.raises(DeckstringError):
        decode_deckstring("AAEB")
