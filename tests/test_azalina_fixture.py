"""Régression sur la partie du 01/08 19h (Azalina + adversaire Voleur).

Vérité terrain fournie par le joueur (captures d'écran) : HS affichait
« 36 cartes dans votre deck » quand le tracker en voyait 19 — bug corrigé
par le comptage en vérité des zones + la classification par bloc.
"""

import pytest

from src.cairn.cards_db import CardsDb
from src.cairn.counters import compute_counters
from src.cairn.decks_log import parse_queue_events
from src.cairn.deck_view import compute_deck_view, opponent_class, pick_queued_deck
from src.cairn.game_state import replay_file
from src.cairn.paths import CARDS_JSON, FIXTURES_DIR

FIXTURE_DIR = FIXTURES_DIR / "Hearthstone_2026_08_01_19_09_13"

pytestmark = pytest.mark.skipif(
    not (FIXTURE_DIR / "Power.log").is_file() or not CARDS_JSON.is_file(),
    reason="fixture ou base de cartes absente",
)


@pytest.fixture(scope="module")
def db():
    return CardsDb.load()


@pytest.fixture(scope="module")
def game_and_view(db):
    (game,) = replay_file(FIXTURE_DIR / "Power.log")
    queue = parse_queue_events(
        (FIXTURE_DIR / "Decks.log").read_text(encoding="utf-8", errors="replace")
    )
    return game, compute_deck_view(game, pick_queued_deck(queue, game), db)


def test_remaining_total_verite_des_zones(game_and_view):
    _, view = game_and_view
    # fin de partie : 28 entités dans le deck (compté depuis les zones,
    # inclut les copies Azalina inconnues)
    assert view.remaining_total == 28


def test_entrees_azalina_groupees(game_and_view):
    _, view = game_and_view
    # les copies inconnues sont regroupées en une ligne ×N, pas noyées
    unknown = [e for e in view.entries if not e.known]
    assert unknown, "les entrées Azalina doivent apparaître"
    assert max(e.count for e in unknown) >= 10


def test_adversaire_voleur_detecte(game_and_view, db):
    game, _ = game_and_view
    assert opponent_class(game, db) == "ROGUE"


def test_compteurs_contextuels_muets_sans_leur_carte(game_and_view, db):
    """Partie vs Voleur : aucun compteur armé par une carte absente ne doit
    s'afficher (c'était le défaut de l'ancien gating par classe)."""
    game, view = game_and_view
    icons = {c.icon for c in compute_counters(game, view, db)}
    assert "⏳" not in icons, "Rafaam affiché alors qu'aucun Rafaam n'a été joué"
    assert icons.isdisjoint({"✦", "🐉", "🕯", "☠"})


def test_compteur_attaque_sans_crash(game_and_view, db):
    game, view = game_and_view
    counters = compute_counters(game, view, db)
    # fin de partie : peuvent être absents (héros au cimetière) mais jamais
    # planter ; s'ils sont là, ce sont des entiers avec leur camp
    for attack in (c for c in counters if c.icon == "⚔"):
        assert attack.kind in ("good", "bad") and attack.text.isdigit()
