"""Textes de règles des cartes — nettoyage et chargement paresseux.

Ils servent à UNE chose : rendre lisibles les « effets en jeu ». Un
enchantement n'a pas de rendu d'image, donc survoler « Âme brisée » ne montrait
rien du tout ; désormais l'aperçu affiche sa carte source et son texte.

Le fichier est séparé de la base principale et chargé à la première demande :
les textes pèsent autant que toute la base élaguée, pour un usage occasionnel.
"""

import json

import pytest

from src.cairn.cards_db import CardsDb
from src.cairn.cards_fetch import plain_text, texts
from src.cairn.paths import CARDS_JSON


def test_balises_et_marqueurs_de_gabarit_retires():
    brut = "<b>Cri de guerre :</b> inflige $3 points de dégâts."
    assert plain_text(brut) == "Cri de guerre : inflige 3 points de dégâts."


def test_les_variantes_conditionnelles_sont_coupees():
    """« @ » sépare le texte de base des variantes affichées en cours de
    partie (« Encore 3 ! », « Prêt ! ») : seule la première décrit la carte."""
    assert plain_text("Si 20 serviteurs sont morts…@ <i>(Encore {0} !)</i>") \
        == "Si 20 serviteurs sont morts…"


def test_les_cesures_de_mise_en_page_sont_recollees():
    """« [x] » signale des retours à la ligne calculés pour la largeur de la
    carte : les garder hacherait l'infobulle en tronçons de quatre mots."""
    assert plain_text("[x]Rejoue chaque carte\ncoûtant 1 cristal\nque vous avez jouée") \
        == "Rejoue chaque carte coûtant 1 cristal que vous avez jouée"


def test_les_vrais_paragraphes_sont_gardes():
    assert plain_text("<b>Provocation</b>\nRâle d’agonie : piochez.") \
        == "Provocation\nRâle d’agonie : piochez."


def test_texte_absent_rend_une_chaine_vide():
    assert plain_text(None) == "" and plain_text("") == ""


def test_les_cartes_sans_texte_ne_sont_pas_ecrites():
    """Le fichier ne doit contenir que ce qui sert : la moitié des entrées de
    HearthstoneJSON n'ont aucun texte de règles."""
    cartes = [
        {"id": "A", "text": "<b>Provocation</b>", "set": "CORE"},
        {"id": "B", "set": "CORE"},
        {"id": "C", "text": "", "set": "CORE"},
        {"id": "D", "text": "Ignoré", "set": "BATTLEGROUNDS"},
    ]
    assert texts(cartes) == {"A": "Provocation"}


@pytest.mark.skipif(not CARDS_JSON.is_file(), reason="base de cartes absente")
def test_lecture_par_la_base_de_cartes(tmp_path):
    db = CardsDb.load()
    # une carte du jeu, texte non vide (la base doit avoir été téléchargée
    # avec les textes : `cairn-cards all`)
    assert "1 cristal" in db.text("CATA_560")
    # identifiant inconnu : pas d'exception, pas de texte
    assert db.text("PAS_UNE_CARTE") == "" and db.text(None) == ""


def test_base_sans_fichier_de_textes_reste_muette(monkeypatch, tmp_path):
    """Une installation antérieure aux textes ne doit pas planter : la
    fonctionnalité se tait, le reste du tracker continue."""
    from src.cairn import cards_db

    monkeypatch.setattr(cards_db, "CARDS_TEXT", tmp_path / "absent.json")
    db = cards_db.CardsDb([{"id": "X", "dbfId": 1, "name": "X"}])
    assert db.text("X") == ""


def test_repli_du_texte_anglais_sur_le_francais(monkeypatch, tmp_path):
    """La base anglaise peut manquer une carte trop récente : mieux vaut le
    texte français que rien."""
    from src.cairn import cards_db

    (tmp_path / "fr.json").write_text(json.dumps({"X": "Provocation"}), encoding="utf-8")
    monkeypatch.setattr(cards_db, "CARDS_TEXT", tmp_path / "fr.json")
    monkeypatch.setattr(cards_db, "CARDS_TEXT_EN", tmp_path / "absent.json")
    db = cards_db.CardsDb([{"id": "X", "dbfId": 1, "name": "X"}])
    assert db.text("X", "en") == "Provocation"
