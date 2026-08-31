"""Effets globaux en jeu — le critère structurel, et ce qu'il exclut.

Le piège de cette section, c'est le bruit : une partie contient des centaines
d'enchantements, dont la quasi-totalité sont des buffs de serviteur sans
intérêt (« Âme brisée » ×166 sur le corpus). Le tri se fait sur la CIBLE de
l'enchantement, pas sur une liste de cartes à entretenir.
"""

import pytest

from src.cairn.cards_db import CardsDb
from src.cairn.effects import global_effects
from src.cairn.game_state import Entity, Game
from src.cairn.paths import CARDS_JSON

pytestmark = pytest.mark.skipif(
    not CARDS_JSON.is_file(), reason="base de cartes absente"
)

AMARA = "TLC_835e"      # Protection d'Amara — attachée au joueur
AME_BRISEE = "JAIL_430e1"  # buff de serviteur, le plus fréquent du corpus


@pytest.fixture(scope="module")
def db():
    return CardsDb.load()


def _partie(enchantements):
    """``enchantements`` : liste de (card_id, type de la cible)."""
    g = Game(player_names={1: "moi", 2: "adv"}, player_entity={1: 10, 2: 11})
    g.entities[10] = Entity(entity_id=10,
                            tags={"CONTROLLER": "1", "CARDTYPE": "PLAYER"})
    g.entities[11] = Entity(entity_id=11,
                            tags={"CONTROLLER": "2", "CARDTYPE": "PLAYER"})
    eid = 100
    for card_id, type_cible in enchantements:
        cible = eid
        g.entities[cible] = Entity(entity_id=cible,
                                   tags={"CONTROLLER": "1", "ZONE": "PLAY",
                                         "CARDTYPE": type_cible})
        g.entities[cible + 1] = Entity(
            entity_id=cible + 1, card_id=card_id,
            tags={"CONTROLLER": "1", "ZONE": "PLAY", "CARDTYPE": "ENCHANTMENT",
                  "ATTACHED": str(cible)},
        )
        eid += 2
    return g


def test_effet_attache_au_joueur_est_global(db):
    effets = global_effects(_partie([(AMARA, "PLAYER")]), db, 1)
    assert [e.label for e in effets] == ["Protection d’Amara"]
    assert effets[0].card_id == AMARA and effets[0].count == 1


def test_buff_de_serviteur_est_ignore(db):
    """C'est 287 enchantements sur 396 dans le corpus : sans ce filtre, la
    section serait un mur illisible."""
    assert global_effects(_partie([(AME_BRISEE, "MINION")]), db, 1) == []


def test_effet_sur_le_heros_compte_aussi(db):
    effets = global_effects(_partie([(AMARA, "HERO")]), db, 1)
    assert len(effets) == 1


def test_arme_et_lieu_restent_locaux(db):
    """Un enchantement d'arme suit son objet : on le voit sur le plateau."""
    partie = _partie([(AMARA, "WEAPON"), (AMARA, "LOCATION")])
    assert global_effects(partie, db, 1) == []


def test_effets_identiques_groupes(db):
    effets = global_effects(
        _partie([(AMARA, "PLAYER"), (AMARA, "PLAYER"), (AMARA, "PLAYER")]), db, 1
    )
    assert len(effets) == 1 and effets[0].count == 3


def test_enchantement_sans_cible_ignore(db):
    """Certains enchantements internes n'ont pas de tag ATTACHED : sans cible
    connue, on ne peut pas dire s'ils sont globaux — on s'abstient."""
    g = _partie([])
    g.entities[500] = Entity(entity_id=500, card_id=AMARA,
                             tags={"CONTROLLER": "1", "ZONE": "PLAY",
                                   "CARDTYPE": "ENCHANTMENT"})
    assert global_effects(g, db, 1) == []


def test_carte_source_retrouvee_par_le_createur(db):
    """Le survol doit montrer la carte QUI a posé l'effet.

    Un enchantement n'a pas de rendu d'image et son texte propre n'apprend
    rien (« PV augmentés. ») : sans sa source, « Protection d'Amara » reste une
    devinette. Le tag CREATOR la donne.
    """
    g = _partie([(AMARA, "PLAYER")])
    g.entities[11].card_id = "JAIL_430"   # Briseuse d'âme Azalina
    g.entities[101].tags["CREATOR"] = "11"
    effet = global_effects(g, db, 1)[0]
    assert effet.source_card_id == "JAIL_430"
    assert effet.source_name == "Briseuse d’âme Azalina"


def test_source_deduite_du_suffixe_sans_createur(db):
    """HS ne pose parfois CREATOR qu'à la révélation : en attendant, le suffixe
    de l'identifiant (JAIL_430e1 → JAIL_430) suffit."""
    g = _partie([(AME_BRISEE, "PLAYER")])
    assert global_effects(g, db, 1)[0].source_card_id == "JAIL_430"


def test_camp_adverse_separe(db):
    partie = _partie([(AMARA, "PLAYER")])
    assert global_effects(partie, db, 1)      # chez moi
    assert global_effects(partie, db, 2) == []  # rien chez lui


def test_sur_le_corpus_reel(db):
    """Les effets globaux doivent rester peu nombreux : c'est ce qui distingue
    la section d'un déversoir. Mesuré : 0 à 3 par partie."""
    from pathlib import Path

    from src.cairn.game_state import replay_file

    base = Path.home() / "Bureau/le gnome zip HS/Le gnome unzip"
    if not base.is_dir():
        pytest.skip("corpus externe absent")
    vus = 0
    for dossier in sorted(base.iterdir()):
        log = dossier / "Power.log"
        if not log.is_file():
            continue
        for game in replay_file(log):
            local = game.local_player_id()
            if local is None:
                continue
            effets = global_effects(game, db, local)
            assert len(effets) <= 6, f"section noyée : {[e.label for e in effets]}"
            vus += len(effets)
    assert vus > 0, "le corpus contient forcément des effets globaux"
