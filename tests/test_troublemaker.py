"""Régression sur la partie du 02/08 12:07 — Fauteuse de troubles du Lotus.

Vérité terrain tirée du journal lui-même : quand l'adversaire a posé sa
Fauteuse (12:12:52), le jeu a résolu **6 projectiles** et a annoncé
``TAG_SCRIPT_DATA_NUM_1=6`` juste avant. À ce moment-là il avait joué 5
cartes coûtant (2) — le compteur déduit (1 + cartes à (2)) doit donc dire 6,
ni plus ni moins. Ma copie en main, elle, est montée à 9.
"""

import pytest

from src.cairn.cards_db import CardsDb
from src.cairn.counters import compute_counters
from src.cairn.deck_view import compute_deck_view
from src.cairn.game_state import GameStateEngine, replay_file
from src.cairn.paths import CARDS_JSON, FIXTURES_DIR
from src.cairn.power_log import parse_lines

FIXTURE_DIR = FIXTURES_DIR / "Hearthstone_2026_08_02_12_07_01"
POWER_LOG = FIXTURE_DIR / "Power.log"

pytestmark = pytest.mark.skipif(
    not POWER_LOG.is_file() or not CARDS_JSON.is_file(),
    reason="fixture ou base de cartes absente",
)

TROUBLEMAKER = "JAIL_470"


@pytest.fixture(scope="module")
def db():
    return CardsDb.load()


@pytest.fixture(scope="module")
def lines():
    return POWER_LOG.read_text(encoding="utf-8", errors="replace").splitlines()


def _shots(game, db):
    """Les deux compteurs ⇶, indexés par camp."""
    view = compute_deck_view(game, None, db)
    out = {}
    for c in compute_counters(game, view, db):
        if c.icon == "⇶":
            out["moi" if c.kind == "good" else "adv"] = int(c.text.split()[-1])
    return out


def _game_at(lines, cut):
    engine = GameStateEngine()
    engine.feed(parse_lines(lines[:cut]))
    return engine.games[0]


def _line_of_his_play(lines):
    """Ligne où il pose sa Fauteuse : le BLOCK_START de la carte quittant sa main."""
    for i, raw in enumerate(lines):
        if "BLOCK_START BlockType=PLAY" in raw and "id=22 zone=HAND" in raw:
            return i
    pytest.fail("pose de la Fauteuse introuvable dans la fixture")


def test_projectiles_adverses_au_moment_de_la_pose(lines, db):
    """Le chiffre que le joueur ne peut pas deviner — et que le jeu confirme."""
    game = _game_at(lines, _line_of_his_play(lines))
    assert _shots(game, db)["adv"] == 6


def test_ma_copie_suit_le_tag_du_jeu(lines, db):
    (game,) = replay_file(POWER_LOG)
    mine = [
        e for e in game.entities.values()
        if e.card_id == TROUBLEMAKER and e.controller == game.local_player_id()
    ]
    assert [e.tags.get("TAG_SCRIPT_DATA_NUM_1") for e in mine] == ["9"]
    assert _shots(game, db)["moi"] == 9


def test_compteur_muet_sans_la_carte(db):
    """Aucune Fauteuse vue = pas de compteur (règle des add-ons contextuels)."""
    from tests.test_counters import _fake_game  # partie synthétique minimale

    game = _fake_game(opp_cards=["EX1_001"])
    view = compute_deck_view(game, None, db)
    assert not [c for c in compute_counters(game, view, db) if c.icon == "⇶"]


def test_les_deux_camps_sont_comptes(lines, db):
    (game,) = replay_file(POWER_LOG)
    shots = _shots(game, db)
    assert set(shots) == {"moi", "adv"}, "le compteur doit exister des deux côtés"
