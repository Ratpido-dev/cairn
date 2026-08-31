"""Mise à jour automatique de la base de cartes après un patch Hearthstone.

Le 18/08/2026, un patch d'équilibrage a changé le coût de 8 cartes et le texte
de 13 autres. Cairn a continué d'afficher les anciennes valeurs pendant cinq
jours, sans rien signaler : la base n'était téléchargée QU'À l'installation.

Deux garde-fous sont testés ici :
  - la base se retélécharge d'elle-même quand HearthstoneJSON publie une
    nouvelle version, et seulement dans ce cas ;
  - quand le JEU reformule une carte dont le CODE suppose l'effet, on prévient
    — aucun téléchargement ne peut réparer ça.
"""

import json
import re
from pathlib import Path

import pytest

from src.cairn import cards_fetch

SRC = Path(__file__).resolve().parents[1] / "src" / "cairn"


# ---- la liste des cartes câblées reste complète ------------------------------

# Identifiants dont le code ne suppose RIEN de l'effet : il les reconnaît, mais
# une reformulation ne changerait pas son comportement.
HORS_SURVEILLANCE = {"JAIL_509e"}  # enchantement, repéré par son suffixe


def test_toute_carte_citee_dans_le_code_est_surveillee():
    """Un identifiant de carte en dur = une hypothèse sur son effet.

    Ce test est le seul mécanisme qui empêche ``LOGIQUE_CABLEE`` de pourrir :
    ajouter un compteur pour une nouvelle carte sans l'y déclarer casse ici.
    """
    motif = re.compile(r'"([A-Z]{3,6}_[0-9]{2,4}[a-z]?[0-9]?)"')
    trouves = set()
    for py in SRC.rglob("*.py"):
        if py.name == "cards_fetch.py":  # c'est là que vit la liste elle-même
            continue
        trouves |= set(motif.findall(py.read_text(encoding="utf-8")))
    manquants = trouves - set(cards_fetch.LOGIQUE_CABLEE) - HORS_SURVEILLANCE
    assert not manquants, (
        f"cartes citées dans le code mais absentes de LOGIQUE_CABLEE : "
        f"{sorted(manquants)}"
    )


# ---- détection de la reformulation ------------------------------------------

def test_reformulation_signalee(tmp_path, monkeypatch):
    """Le cas réel : Tol'vir passe de « rejoue chaque carte » à « invoque
    chaque serviteur » — même identifiant, effet différent."""
    ancien = tmp_path / "cards.text.frFR.json"
    ancien.write_text(json.dumps({
        "CATA_560": "Rejoue chaque carte coûtant 1 cristal que vous avez jouée.",
        "END_024": "inchangé",
    }), encoding="utf-8")
    monkeypatch.setitem(cards_fetch.TEXT_TARGETS, "frFR", ancien)

    alertes = cards_fetch._reformulations("frFR", {
        "CATA_560": "Invoque chaque serviteur coûtant 1 cristal que vous avez joué.",
        "END_024": "inchangé",
    })
    assert [a["id"] for a in alertes] == ["CATA_560"]
    assert "Invoque" in alertes[0]["apres"]


def test_pas_d_alerte_a_la_premiere_installation(tmp_path, monkeypatch):
    """Aucun fichier antérieur : rien à comparer, donc rien à signaler."""
    monkeypatch.setitem(cards_fetch.TEXT_TARGETS, "frFR", tmp_path / "absent.json")
    assert cards_fetch._reformulations("frFR", {"CATA_560": "n'importe quoi"}) == []


def test_une_seule_alerte_par_carte(tmp_path, monkeypatch):
    """La même reformulation est vue une fois par locale (fr puis en) : la
    question posée reste la même, et deux lignes identiques dans le doctor
    donnent surtout l'impression d'un bug."""
    vieille = {"id": "CATA_560", "role": "x", "avant": "a", "apres": "b",
               "vu": "2026-08-19"}
    neuve = dict(vieille, vu="2026-08-20")
    assert cards_fetch._sans_doublons([vieille, neuve]) == [neuve]


def test_carte_non_cablee_ignoree(tmp_path, monkeypatch):
    """La plupart des cartes reformulées ne concernent aucune logique : les
    signaler toutes noierait l'alerte utile (13 textes ont changé le 18/08)."""
    ancien = tmp_path / "cards.text.frFR.json"
    ancien.write_text(json.dumps({"ZZZ_999": "avant"}), encoding="utf-8")
    monkeypatch.setitem(cards_fetch.TEXT_TARGETS, "frFR", ancien)
    assert cards_fetch._reformulations("frFR", {"ZZZ_999": "après"}) == []


# ---- contrôle de version -----------------------------------------------------

class _Reponse:
    """Réponse HTTP minimale, utilisable comme gestionnaire de contexte."""

    def __init__(self, **entetes):
        self.headers = entetes

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Une base locale déjà téléchargée, avec son ``meta.json``."""
    cards = tmp_path / "cards.frFR.json"
    cards.write_text("[]", encoding="utf-8")
    monkeypatch.setitem(cards_fetch.TARGETS, "frFR", cards)
    monkeypatch.setattr(cards_fetch, "CARDS_META", tmp_path / "meta.json")
    return tmp_path


def test_meme_empreinte_rien_a_faire(base, monkeypatch):
    cards_fetch._write_meta({"locales": {"frFR": {"etag": "abc"}}})
    monkeypatch.setattr(cards_fetch.urllib.request, "urlopen",
                        lambda *a, **k: _Reponse(ETag="abc"))
    assert cards_fetch.remote_changed("frFR") is False


def test_empreinte_differente_maj_disponible(base, monkeypatch):
    cards_fetch._write_meta({"locales": {"frFR": {"etag": "abc"}}})
    monkeypatch.setattr(cards_fetch.urllib.request, "urlopen",
                        lambda *a, **k: _Reponse(ETag="def"))
    assert cards_fetch.remote_changed("frFR") is True


def test_reseau_muet_reste_indetermine(base, monkeypatch):
    """``None``, surtout pas ``False`` : sans réseau on ne SAIT pas, et il faut
    redemander au prochain lancement plutôt que de dormir douze heures."""
    def _boum(*a, **k):
        raise cards_fetch.urllib.error.URLError("pas de réseau")

    monkeypatch.setattr(cards_fetch.urllib.request, "urlopen", _boum)
    assert cards_fetch.remote_changed("frFR") is None


def test_base_sans_empreinte_compare_les_dates(base, monkeypatch):
    """Base héritée d'une version antérieure de Cairn : pas d'ETag connu, donc
    on compare la date du CDN au mtime du fichier — pas de retéléchargement
    gratuit si le fichier est plus récent."""
    monkeypatch.setattr(cards_fetch.urllib.request, "urlopen",
                        lambda *a, **k: _Reponse(
                            **{"Last-Modified": "Mon, 14 Aug 2000 12:00:00 GMT"}))
    assert cards_fetch.remote_changed("frFR") is False
    monkeypatch.setattr(cards_fetch.urllib.request, "urlopen",
                        lambda *a, **k: _Reponse(
                            **{"Last-Modified": "Tue, 18 Aug 2099 17:37:15 GMT"}))
    assert cards_fetch.remote_changed("frFR") is True


def test_base_absente_est_toujours_periemee(base, monkeypatch):
    cards_fetch.TARGETS["frFR"].unlink()
    assert cards_fetch.remote_changed("frFR") is True


# ---- cadence des contrôles ---------------------------------------------------

def test_pas_de_requete_avant_l_intervalle(base, monkeypatch):
    """Douze heures entre deux HEAD : lancer Cairn dix fois dans la journée ne
    doit pas taper dix fois le CDN."""
    import time

    cards_fetch._write_meta({"verifie_le": time.time()})
    monkeypatch.setattr(cards_fetch, "remote_changed",
                        lambda *a, **k: pytest.fail("le CDN a été interrogé"))
    assert cards_fetch.update_if_stale() is False


def test_force_ignore_l_intervalle(base, monkeypatch):
    import time

    cards_fetch._write_meta({"verifie_le": time.time()})
    monkeypatch.setattr(cards_fetch, "remote_changed", lambda *a, **k: False)
    assert cards_fetch.update_if_stale(force=True) is False  # interrogé, rien à faire


def test_echec_reseau_ne_repousse_pas_le_prochain_controle(base, monkeypatch):
    """Lancé hors ligne, Cairn ne doit pas noter « vérifié » — sinon un patch
    tombé le même jour attendrait douze heures de plus."""
    monkeypatch.setattr(cards_fetch, "remote_changed", lambda *a, **k: None)
    assert cards_fetch.update_if_stale() is False
    assert not cards_fetch.meta().get("verifie_le")


def test_maj_disponible_declenche_le_telechargement(base, monkeypatch):
    telecharges = []
    monkeypatch.setattr(cards_fetch, "remote_changed",
                        lambda loc, **k: loc == "frFR")
    monkeypatch.setattr(cards_fetch, "fetch",
                        lambda loc, **k: telecharges.append(loc) or 0)
    assert cards_fetch.update_if_stale(verbose=False) is True
    assert telecharges == ["frFR"]  # enUS était à jour : on n'y touche pas
    assert cards_fetch.meta().get("verifie_le")


def test_meta_illisible_ne_casse_rien(base):
    """Fichier tronqué par un arrêt brutal : on repart de zéro, sans planter."""
    cards_fetch.CARDS_META.write_text("{ tronqué", encoding="utf-8")
    assert cards_fetch.meta() == {}
