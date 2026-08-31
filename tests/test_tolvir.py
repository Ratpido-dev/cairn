"""« Confrontation des Tol'vir » — les SERVITEURS à (1) déjà joués.

La carte invoque tout ce que son camp a joué comme serviteur à 1 cristal depuis
le début de la partie. Sa valeur se construit donc dix tours avant qu'elle ne
tombe : un tracker qui n'affiche la liste qu'au moment où la carte est vue
arrive trop tard pour changer quoi que ce soit. D'où l'armement par la CLASSE.

Le patch du 18/08/2026 l'a réécrite — elle « rejouait chaque CARTE à (1) » —
d'où les sorts à (1) explicitement testés comme NON comptés : c'est le piège
dans lequel le tracker est tombé pendant deux jours.
"""

import pytest

from src.cairn.cards_db import CardsDb
from src.cairn.counters import compute_counters
from src.cairn.deck_view import compute_deck_view
from src.cairn.game_state import Draw, Entity, Game, Play
from src.cairn.paths import CARDS_JSON

pytestmark = pytest.mark.skipif(
    not CARDS_JSON.is_file(), reason="base de cartes absente"
)

TOLVIR = "CATA_560"          # Confrontation des Tol'vir (Chasseur, 4 cristaux)
UN = "CORE_AT_029"           # Boucanier — SERVITEUR à 1 cristal
UN_BIS = "CORE_BT_351"       # Démon belliqueux — SERVITEUR à 1 cristal
UN_SORT = "CORE_AT_055"      # Soins rapides — SORT à 1 cristal, ne compte PAS
DEUX = "CORE_AT_064"         # Rossée — sort à 2 cristaux
HEROS = {"HUNTER": "HERO_05", "PRIEST": "HERO_09"}


@pytest.fixture(scope="module")
def db():
    return CardsDb.load()


def _partie(classe_adverse="HUNTER", coups_adverses=(), ma_classe="PRIEST"):
    g = Game(player_names={1: "moi", 2: "adv"}, player_entity={1: 10, 2: 11})
    g.format_type = "FT_STANDARD"
    g.turns = 12
    g.entities[10] = Entity(entity_id=10, tags={"CONTROLLER": "1"})
    g.entities[11] = Entity(entity_id=11, tags={"CONTROLLER": "2"})
    for pid, (eid, classe) in enumerate(
        ((20, ma_classe), (21, classe_adverse)), start=1
    ):
        g.entities[eid] = Entity(
            entity_id=eid, card_id=HEROS[classe],
            tags={"CONTROLLER": str(pid), "ZONE": "PLAY", "CARDTYPE": "HERO"},
        )
    # une pioche révélée : c'est ce qui désigne le joueur local pour le moteur
    g.events.append(Draw(player_id=1, entity_id=1, card_id=UN, during_mulligan=True))
    for i, card_id in enumerate(coups_adverses):
        g.events.append(Play(player_id=2, entity_id=300 + i, card_id=card_id, turn=4))
    return g


def _liste(db, game):
    return [(c.label, c.count) for c in compute_deck_view(game, None, db).opp_replay]


def test_cartes_a_1_listees_et_groupees(db):
    game = _partie(coups_adverses=[UN, UN, UN_BIS, DEUX])
    assert _liste(db, game) == [("Boucanier", 2), ("Démon belliqueux", 1)]


def test_les_sorts_a_1_ne_comptent_pas(db):
    """LE test de la correction du 20/08/2026.

    La carte « invoque chaque SERVITEUR coûtant 1 » depuis le patch du 18/08 —
    avant, elle « rejouait chaque CARTE coûtant 1 ». Compter les sorts
    surévalue la menace, et c'est le pire sens de l'erreur : on joue autour
    d'un rejeu qui n'arrivera jamais.
    """
    game = _partie(coups_adverses=[UN, UN_SORT, UN_SORT])
    assert _liste(db, game) == [("Boucanier", 1)]


def test_un_camp_qui_n_a_joue_que_des_sorts_a_1_ne_montre_rien(db):
    game = _partie(coups_adverses=[UN_SORT, UN_SORT])
    assert _liste(db, game) == []


def test_le_cout_imprime_fait_foi_pas_le_cout_paye(db):
    """Une carte à (2) réduite à (1) ne sera PAS rejouée : c'est le coût de la
    carte qui compte, pas ce qu'il en a coûté (mesuré sur la Fauteuse de
    troubles, cf. deck_view.plays_costing)."""
    game = _partie(coups_adverses=[DEUX])
    game.entities[300] = Entity(
        entity_id=300, card_id=DEUX,
        tags={"CONTROLLER": "2", "TAG_LAST_KNOWN_COST_IN_HAND": "1"},
    )
    assert _liste(db, game) == []


def test_rien_contre_une_classe_sans_la_carte(db):
    """Un Prêtre ne joue pas Confrontation des Tol'vir : pas de section."""
    game = _partie(classe_adverse="PRIEST", coups_adverses=[UN, UN_BIS])
    assert _liste(db, game) == []


def test_la_carte_volee_arme_la_liste_hors_chasseur(db):
    """Azalina, Découverte, vol… : la carte peut arriver chez n'importe qui.
    Dès qu'on l'a vue passer, la liste doit se tenir."""
    game = _partie(classe_adverse="PRIEST", coups_adverses=[UN])
    game.entities[400] = Entity(
        entity_id=400, card_id=TOLVIR,
        tags={"CONTROLLER": "2", "ZONE": "HAND"},
    )
    assert _liste(db, game) == [("Boucanier", 1)]


def test_ma_propre_liste_suit_les_memes_regles(db):
    game = _partie(ma_classe="HUNTER", classe_adverse="PRIEST")
    game.events.append(Play(player_id=1, entity_id=500, card_id=UN, turn=6))
    view = compute_deck_view(game, None, db)
    assert [c.label for c in view.my_replay] == ["Boucanier"]
    assert view.opp_replay == []


def test_le_compteur_s_affiche_avant_que_la_carte_soit_jouee(db):
    """Le cœur de la demande : contre un Chasseur, le compteur existe dès le
    premier tour — pas au moment où la Confrontation tombe."""
    game = _partie(coups_adverses=[UN, UN_BIS])
    view = compute_deck_view(game, None, db)
    replay = [c for c in compute_counters(game, view, db) if c.pair == "replay"]
    # seul le camp concerné a une colonne : je suis Prêtre et n'ai pas la carte
    assert [(c.side, c.short) for c in replay] == [("opp", "2")]


def test_pas_de_compteur_sans_chasseur_ni_carte(db):
    game = _partie(classe_adverse="PRIEST", coups_adverses=[UN])
    view = compute_deck_view(game, None, db)
    assert not [c for c in compute_counters(game, view, db) if c.pair == "replay"]
