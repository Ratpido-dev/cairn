"""Élimination automatique des secrets — surtout ses garde-fous.

Écarter à tort un bon candidat est PIRE que ne rien écarter : on jouerait dans
le secret. Ces tests couvrent donc autant les cas où l'on doit éliminer que
ceux où l'on doit s'abstenir.
"""

import pytest

from src.cairn.cards_db import CardsDb
from src.cairn.game_state import Draw, Entity, Game, Play
from src.cairn.paths import CARDS_JSON
from src.cairn.secrets import candidates

pytestmark = pytest.mark.skipif(
    not CARDS_JSON.is_file(), reason="base de cartes absente"
)

CONTRESORT = "CORE_EX1_287"      # se déclenche sur un sort, sans condition
RUNES = "CORE_LOOT_101"          # se déclenche sur un serviteur posé
PIEGE_EXPLOSIF = "CORE_EX1_610"  # lié à une ATTAQUE : jamais éliminable


@pytest.fixture(scope="module")
def db():
    return CardsDb.load()


def _partie(nb_secrets=1, mes_coups=(), tour=6, klass="MAGE"):
    """Partie synthétique : l'adversaire (2) pose des secrets, moi (1) joue.

    ``mes_coups`` : liste de (tour, card_id) — mes cartes jouées.
    """
    g = Game(player_names={1: "moi", 2: "adv"}, player_entity={1: 10, 2: 11})
    g.format_type = "FT_STANDARD"
    g.turns = tour
    g.entities[10] = Entity(entity_id=10, tags={"CONTROLLER": "1"})
    g.entities[11] = Entity(entity_id=11, tags={"CONTROLLER": "2"})
    # héros adverse, pour la classe
    g.entities[12] = Entity(entity_id=12, card_id="HERO_08",
                            tags={"CONTROLLER": "2", "ZONE": "PLAY",
                                  "CARDTYPE": "HERO"})
    for i in range(nb_secrets):
        eid = 200 + i
        g.entities[eid] = Entity(entity_id=eid,
                                 tags={"CONTROLLER": "2", "ZONE": "SECRET"})
        # posé au tour 2 : nos coups des tours suivants comptent
        g.events.append(Play(player_id=2, entity_id=eid, card_id=None, turn=2))
    # une pioche révélée : c'est ce qui désigne le joueur local pour le moteur
    g.events.append(Draw(player_id=1, entity_id=1, card_id="CORE_CS2_182",
                         during_mulligan=True))
    for i, (t, cid) in enumerate(mes_coups):
        g.events.append(Play(player_id=1, entity_id=300 + i, card_id=cid, turn=t))
    return g


def _etat(db, game, klass="MAGE"):
    return {c.card_id: c.ruled_out for c in candidates(game, db, 2, klass)}


def test_sans_declencheur_rien_n_est_ecarte(db):
    etat = _etat(db, _partie(tour=2))
    assert etat and not any(etat.values())


def test_un_sort_joue_ecarte_contresort(db):
    """Contresort contre TOUJOURS : s'il n'a pas sauté, ce n'est pas lui."""
    etat = _etat(db, _partie(mes_coups=[(4, "CORE_EX1_622")]))  # Mot de l'ombre
    assert etat[CONTRESORT] is True
    assert etat[RUNES] is False  # aucun serviteur posé : Runes reste possible


def test_un_serviteur_pose_ecarte_les_runes(db):
    etat = _etat(db, _partie(mes_coups=[(4, "CORE_CS2_182")]))  # Yéti chillwind
    assert etat[RUNES] is True
    assert etat[CONTRESORT] is False


def test_les_pieges_d_attaque_ne_sont_jamais_ecartes(db):
    """Le moteur ne journalise pas les attaques : tout ce qui en dépend reste
    possible, quoi qu'il arrive. C'est le sens par défaut, et il est sûr."""
    etat = _etat(db, _partie(mes_coups=[(4, "CORE_EX1_622"), (4, "CORE_CS2_182")]),
                 klass="HUNTER")
    assert etat[PIEGE_EXPLOSIF] is False


def test_deux_secrets_en_jeu_bloquent_toute_deduction(db):
    """HS n'en déclenche qu'un et laisse l'autre : l'absence de déclenchement
    ne prouve plus rien. C'est LE garde-fou qui rend la déduction sûre."""
    etat = _etat(db, _partie(nb_secrets=2, mes_coups=[(4, "CORE_EX1_622")]))
    assert not any(etat.values())


def test_les_coups_du_tour_de_la_pose_ne_comptent_pas(db):
    """Un sort lancé AVANT que le secret ne soit posé ne le teste pas."""
    etat = _etat(db, _partie(mes_coups=[(2, "CORE_EX1_622")]))
    assert etat[CONTRESORT] is False


# ---- classe du secret POSÉ, et non du héros d'en face ------------------------

def test_secret_d_une_autre_classe_change_les_candidats(db):
    """Un Chasseur qui pose un secret de Mage (vol, Découverte) : ce sont les
    secrets de MAGE qu'il faut proposer.

    Vu en partie le 10/08/2026 — le tracker listait les cinq secrets de
    Chasseur, c'est-à-dire cinq mauvaises réponses. HS publie la classe sur
    l'entité posée (tag CLASS) même quand la carte reste cachée : c'est ce qui
    lui permet d'afficher « Secret de mage » sans rien révéler.
    """
    g = _partie()
    g.entities[200].tags["CLASS"] = "MAGE"
    classes = {
        db.by_card_id[c.card_id]["cardClass"]
        for c in candidates(g, db, 2, "HUNTER")   # héros adverse : Chasseur
    }
    assert classes == {"MAGE"}


def test_sans_tag_de_classe_on_retombe_sur_le_heros(db):
    """Tant que HS n'a rien publié, la classe adverse reste le meilleur pari."""
    classes = {
        db.by_card_id[c.card_id]["cardClass"]
        for c in candidates(_partie(), db, 2, "HUNTER")
    }
    assert classes == {"HUNTER"}


def test_deux_classes_de_secrets_en_jeu_sont_cumulees(db):
    """Deux secrets, deux classes : aucune des deux ne doit disparaître."""
    g = _partie(nb_secrets=2)
    g.entities[200].tags["CLASS"] = "MAGE"
    g.entities[201].tags["CLASS"] = "PALADIN"
    classes = [
        db.by_card_id[c.card_id]["cardClass"] for c in candidates(g, db, 2, "HUNTER")
    ]
    assert set(classes) == {"MAGE", "PALADIN"}
    # chaque classe reste groupée, sinon la liste devient illisible
    assert classes == sorted(classes)


def test_une_quete_en_zone_secret_ne_donne_pas_sa_classe(db):
    """La zone SECRET accueille aussi les quêtes — et une quête est publique,
    donc elle ne dit rien des secrets encore cachés."""
    g = _partie()
    g.entities[200].tags["CLASS"] = "MAGE"
    g.entities[200].tags["QUEST"] = "1"
    classes = {
        db.by_card_id[c.card_id]["cardClass"]
        for c in candidates(g, db, 2, "HUNTER")
    }
    assert classes == {"HUNTER"}   # repli sur le héros


def test_les_ecartes_descendent_en_bas_de_liste(db):
    """Ce qui reste possible d'abord : c'est ce qu'on lit en premier."""
    liste = candidates(_partie(mes_coups=[(4, "CORE_EX1_622")]), db, 2, "MAGE")
    ecartes = [c.ruled_out for c in liste]
    assert ecartes == sorted(ecartes)  # False avant True


# ---- réimpressions et formats (#3) ------------------------------------------
# En Wild, chaque version d'un secret (EX1_289, CORE_EX1_289, VAN_EX1_289…)
# sortait sur sa propre ligne : Barrière de glace apparaissait trois fois.

def _wild(db, nb_secrets=1, mes_coups=(), revealed=(), fmt="FT_WILD"):
    g = _partie(nb_secrets=nb_secrets, mes_coups=mes_coups)
    g.format_type = fmt
    for i, cid in enumerate(revealed):
        g.entities[400 + i] = Entity(entity_id=400 + i, card_id=cid,
                                     tags={"CONTROLLER": "2", "ZONE": "GRAVEYARD"})
    return g


def _noms(db, game, klass="MAGE"):
    return [c.name for c in candidates(game, db, 2, klass)]


@pytest.mark.parametrize("fmt", ["FT_WILD", "FT_STANDARD", "FT_CLASSIC", "FT_TWIST", None])
@pytest.mark.parametrize("klass", ["MAGE", "HUNTER", "PALADIN", "ROGUE"])
def test_aucun_secret_en_double(db, fmt, klass):
    cs = candidates(_wild(db, fmt=fmt), db, 2, klass)
    noms = [(c.card_class, c.name) for c in cs]
    assert len(noms) == len(set(noms))


def test_wild_une_seule_barriere_de_glace(db):
    noms = _noms(db, _wild(db))
    assert noms.count(db.by_card_id["EX1_289"]["name"]) == 1
    assert noms.count(db.by_card_id["EX1_287"]["name"]) == 1  # Contresort


def test_wild_exclut_le_format_classique(db):
    for c in candidates(_wild(db), db, 2, "MAGE"):
        assert db.by_card_id[c.card_id].get("set") != "VANILLA"


def test_classique_ne_garde_que_vanilla(db):
    cs = candidates(_wild(db, fmt="FT_CLASSIC"), db, 2, "MAGE")
    assert cs
    for c in cs:
        assert db.by_card_id[c.card_id].get("set") == "VANILLA"


def test_wild_retient_la_version_core(db):
    ids = {c.card_id for c in candidates(_wild(db), db, 2, "MAGE")}
    assert "CORE_EX1_289" in ids and "EX1_289" not in ids


def test_reimpressions_epuisees_ensemble(db):
    # deux exemplaires partis sous deux ids différents : la carte est épuisée
    game = _wild(db, revealed=("EX1_289", "CORE_EX1_289"))
    assert db.by_card_id["EX1_289"]["name"] not in _noms(db, game)


def test_un_seul_exemplaire_parti_reste_candidat(db):
    game = _wild(db, revealed=("EX1_289",))
    assert db.by_card_id["EX1_289"]["name"] in _noms(db, game)


def test_la_deduction_marche_aussi_en_wild(db):
    game = _wild(db, mes_coups=[(4, "CORE_CS2_029")])
    assert _etat(db, game)[CONTRESORT] is True
