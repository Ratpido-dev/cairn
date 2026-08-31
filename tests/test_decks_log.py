"""Tests du lecteur de Decks.log — extrait réel du 31/07/2026."""

from src.cairn.decks_log import parse_decks_log

SAMPLE = """\
I 23:37:45.8505768 Deck Contents Received:
I 23:37:45.8505768 ### bingo bis
I 23:37:45.8505768 # Deck ID: 2174489721
I 23:37:45.8505768 AAEBAYO6AgbtAuvwAqH5A/uKBNi2BNu5BAyq6wP+7gOh9AO9gAT3nwS6pAT7pQTspwT5rASZtgTVtgT58QQAAA==
I 23:37:45.8505768 ### sanglier V2
I 23:37:45.8505768 # Deck ID: 2189924496
I 23:37:45.8505768 AAEBAZ/HAgTU7QPoiwSJsgT52wQN8gyZ6wOH9wPT+QOMgQTLoASEowSKowSitgSktgSh1AT28QSZ/AcAAA==
"""


def test_parse_extrait_reel():
    decks = parse_decks_log(SAMPLE)
    assert len(decks) == 2
    by_name = {d.name: d for d in decks}
    assert by_name["bingo bis"].deck_id == 2174489721
    assert by_name["bingo bis"].deckstring.startswith("AAEBAYO6")
    assert by_name["sanglier V2"].deck_id == 2189924496


def test_doublon_meme_id_garde_le_dernier():
    decks = parse_decks_log(SAMPLE + SAMPLE)
    assert len(decks) == 2


def test_texte_vide():
    assert parse_decks_log("") == []
