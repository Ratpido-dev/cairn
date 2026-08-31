"""Régression sur la partie du 02/08 01h26 — Azalina copie un Démoniste Godfrey.

Le cas tordu par excellence, et celui qui a motivé le module ``atlas`` :
« Briseuse d'âme Azalina » copie les débuts de partie adverses, donc le Prêtre
hérite à la fois du deck de 40 Rafaam **et** de l'Atlas de Godfrey. Tout ce
que le tracker montrait jusque-là pour l'adversaire seul doit exister des deux
côtés.

Les vérifications de file se font en cours de partie (l'atlas se vide quand la
place se libère) : on rejoue le journal par tranches de lignes.
"""

import pytest

from src.cairn import atlas
from src.cairn.cards_db import CardsDb
from src.cairn.counters import compute_counters
from src.cairn.deck_view import compute_deck_view
from src.cairn.game_state import GameStateEngine, replay_file
from src.cairn.paths import CARDS_JSON, FIXTURES_DIR
from src.cairn.power_log import parse_lines

FIXTURE_DIR = FIXTURES_DIR / "Hearthstone_2026_08_02_01_25_43"
POWER_LOG = FIXTURE_DIR / "Power.log"

pytestmark = pytest.mark.skipif(
    not POWER_LOG.is_file() or not CARDS_JSON.is_file(),
    reason="fixture ou base de cartes absente",
)

# Repères relevés dans le journal : la surpioche adverse met « ÉCHELLE DE
# RAFAAM ! » dans l'atlas (l. 54643), qui en ressort une place libérée plus
# tard (l. 56041).
IN_ATLAS = 54700
OUT_OF_ATLAS = 56100


@pytest.fixture(scope="module")
def db():
    return CardsDb.load()


@pytest.fixture(scope="module")
def lines():
    return POWER_LOG.read_text(encoding="utf-8", errors="replace").splitlines()


def _game_at(lines, cut):
    """État de la partie après les ``cut`` premières lignes du journal."""
    engine = GameStateEngine()
    engine.feed(parse_lines(lines[:cut]))
    return engine.games[0]


def _sides(game):
    local = game.local_player_id()
    return local, next(p for p in game.player_names if p != local)


@pytest.fixture(scope="module")
def finished():
    (game,) = replay_file(POWER_LOG)
    return game


def test_azalina_copie_l_atlas_des_deux_cotes(finished):
    """L'adversaire pose Godfrey, Azalina le copie : deux atlas en jeu."""
    local, opp = _sides(finished)
    assert atlas.has_atlas(finished, opp)
    assert atlas.has_atlas(finished, local), "l'atlas copié par Azalina manque"


def test_file_adverse_visible_avec_son_cout_reduit(lines, db):
    game = _game_at(lines, IN_ATLAS)
    _, opp = _sides(game)
    queue = atlas.queue(game, db, opp)
    assert [c.label for c in queue] == ["ÉCHELLE DE RAFAAM !"]
    assert queue[0].known
    # carte à (4) dans la base : elle reviendra en main à (3)
    assert db.by_card_id["TIME_031"]["cost"] == 4
    assert queue[0].cost == 3


def test_la_file_se_vide_quand_la_place_se_libere(lines, db):
    game = _game_at(lines, OUT_OF_ATLAS)
    _, opp = _sides(game)
    assert atlas.queue(game, db, opp) == []


def test_file_ordonnee_par_arrivee(lines, db):
    """L'ordre de sortie = l'ordre d'entrée : c'est ce que l'UI numérote."""
    game = _game_at(lines, IN_ATLAS)
    _, opp = _sides(game)
    queue = atlas.queue(game, db, opp)
    ids = [
        int(e.tags["COPIED_FROM_ENTITY_ID"])
        for e in game.entities.values()
        if e.card_id in {c.card_id for c in queue}
        and e.tags.get("COPIED_FROM_ENTITY_ID", "").isdigit()
    ]
    assert ids == sorted(ids)


def test_compteur_atlas_pendant_l_attente(lines, db):
    game = _game_at(lines, IN_ATLAS)
    view = compute_deck_view(game, None, db)
    counters = [c for c in compute_counters(game, view, db) if c.icon == "📜"]
    assert [c.text for c in counters] == ["adv atlas 1"]
    assert counters[0].kind == "bad"


def test_compteur_atlas_muet_quand_la_file_est_vide(lines, db):
    game = _game_at(lines, OUT_OF_ATLAS)
    view = compute_deck_view(game, None, db)
    assert not [c for c in compute_counters(game, view, db) if c.icon == "📜"]


def test_rafaam_compte_les_deux_camps(finished, db):
    """Le miroir Rafaam : mon compteur existe aussi, et les deux sont
    étiquetés — sans ça, impossible de savoir où on en est de SA condition."""
    view = compute_deck_view(finished, None, db)
    rafaam = [c for c in compute_counters(finished, view, db) if c.icon == "⏳"]
    assert len(rafaam) == 2
    mine, opp = rafaam
    assert mine.kind == "good" and mine.text.startswith("moi ")
    assert opp.kind == "bad" and opp.text.startswith("adv ")
    # partie réelle : il a posé les 9 autres Rafaam (létal), moi un seul
    assert mine.text == "moi Rafaam 1/9"
    assert "LÉTAL" in opp.text and opp.alert


def _game_with_atlas(cards, player=1):
    """Partie minimale : un atlas et sa file, pour le camp ``player``.

    ``cards`` : (id de la carte réelle, zone de la carte réelle, cardId, coût).
    Reproduit ce que fait HS — la copie révélée porte l'identité, la carte
    réelle porte la zone.
    """
    from src.cairn.game_state import Entity, Game

    game = Game(player_names={1: "moi", 2: "adv"})
    game.entities[9] = Entity(9, card_id=atlas.ATLAS_ENCHANTMENT,
                              tags={"ZONE": "PLAY", "CONTROLLER": str(player)})
    copy_id = 100
    for real_id, zone, card_id, cost in cards:
        game.entities[real_id] = Entity(real_id, tags={"ZONE": zone,
                                                       "CONTROLLER": str(player)})
        game.entities[copy_id] = Entity(
            copy_id, card_id=card_id,
            tags={"ZONE": "SETASIDE", "CONTROLLER": str(player), "CREATOR": "9",
                  "COPIED_FROM_ENTITY_ID": str(real_id), "COST": str(cost)},
        )
        copy_id += 1
    return game


def test_ma_file_a_moi(db):
    """Même code pour mon camp : le journal ne l'a pas encore montré (je n'ai
    pas surpioché ce soir-là), mais l'atlas copié fonctionne à l'identique."""
    game = _game_with_atlas([
        (20, "SETASIDE", "TIME_031", 4),
        (30, "HAND", "EX1_001", 2),      # déjà revenue en main → hors file
        (40, "SETASIDE", "JAIL_514", 10),
    ])
    queue = atlas.queue(game, db, player_id=1)
    assert [c.card_id for c in queue] == ["TIME_031", "JAIL_514"]
    assert [c.cost for c in queue] == [3, 9]
    assert atlas.queue(game, db, player_id=2) == []


def test_enchantements_de_l_atlas_exclus_et_carte_cachee(db):
    from src.cairn.game_state import Entity

    game = _game_with_atlas([(20, "SETASIDE", None, 0)])
    # l'atlas crée aussi son enchantement « Coût −1 » : pas de carte copiée,
    # donc pas de ligne dans la file
    game.entities[200] = Entity(200, card_id="GBL_003e",
                                tags={"ZONE": "PLAY", "CONTROLLER": "1", "CREATOR": "9"})
    (card,) = atlas.queue(game, db, player_id=1)
    assert not card.known and card.label == ""


def test_vue_expose_les_deux_files(finished, db):
    view = compute_deck_view(finished, None, db)
    # en fin de partie les deux files sont vides, mais les champs existent
    assert view.my_atlas == [] and view.opp_atlas == []


# ---- ce que l'atlas a montré reste connu une fois la carte en main ---------

def test_carte_sortie_de_l_atlas_reste_identifiee_en_main(lines, db):
    """LE point : une carte vue entrer dans l'atlas ne doit pas redevenir
    « ? carte cachée » quand l'adversaire la récupère.

    ``queue`` s'arrête à ce qui attend en SETASIDE, ce qui est juste pour la
    file. Mais la copie révélée de l'atlas continue de nommer la carte réelle
    (``COPIED_FROM_ENTITY_ID``), donc l'information ne se perd pas — elle
    n'était simplement pas relue au bon endroit.
    """
    game = _game_at(lines, OUT_OF_ATLAS)
    local, opp = _sides(game)

    # elle a bien quitté la file…
    assert [c.label for c in atlas.queue(game, db, opp)] == []
    # …mais on sait toujours ce que c'est
    assert "TIME_031" in atlas.revealed(game, opp).values()

    vue = compute_deck_view(game, None, db)
    # comparaison par identifiant : le nom de cette carte contient une espace
    # INSÉCABLE avant le « ! », et un test qui compare des libellés se casse
    # sur ce genre de détail sans rien dire d'utile.
    en_main = [s for s in vue.opponent_hand_slots if s.card_id == "TIME_031"]
    assert en_main, "la carte sortie de l'atlas doit être identifiée dans sa main"
    slot = en_main[0]
    assert slot.known
    # c'est cardId qui alimente l'aperçu au survol ET la vignette de la
    # pastille : sans lui, le survol retomberait sur la carte créatrice
    assert slot.label == db.by_card_id["TIME_031"]["name"]

    assert "TIME_031" in [c.card_id for c in vue.opponent_hand]


def test_les_cartes_jamais_vues_restent_cachees(lines, db):
    """Le garde-fou : on ne révèle QUE ce que l'atlas a montré. Une main
    adverse entièrement connue serait un bug, pas une fonctionnalité."""
    game = _game_at(lines, OUT_OF_ATLAS)
    local, opp = _sides(game)
    vue = compute_deck_view(game, None, db)
    slots = vue.opponent_hand_slots
    assert any(not s.known for s in slots), "tout est connu : la révélation fuit"
    revelees = set(atlas.revealed(game, opp).values())
    for s in slots:
        if s.known and s.card_id and s.card_id not in revelees:
            # légitime : HS avait déjà publié l'id (carte créée, découverte…)
            ent = [e for e in game.entities.values()
                   if e.zone == "HAND" and e.controller == opp and e.card_id == s.card_id]
            assert ent, f"{s.label} connue sans source identifiable"
