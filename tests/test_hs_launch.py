"""Résolution de la commande de lancement de Hearthstone.

Le point à ne jamais perdre de vue : la détection (Lutris, .desktop) n'est
qu'un raccourci pour les cas courants. Le mécanisme qui marche pour tout le
monde, c'est la commande saisie à la main — elle doit donc gagner sur tout, et
les échecs de détection doivent rester silencieux et sans conséquence.
"""

import json

import pytest

from src.cairn import hs_launch
from src.cairn.hs_launch import LaunchMethod, resolve


@pytest.fixture
def prefix(tmp_path):
    p = tmp_path / "Games" / "battle-net"
    p.mkdir(parents=True)
    return p


def _sans_detection(monkeypatch):
    """Neutralise Lutris et les .desktop : la machine de test n'en a pas."""
    monkeypatch.setattr(hs_launch, "_from_lutris", lambda prefix: None)
    monkeypatch.setattr(hs_launch, "_from_desktop", lambda prefix: None)


# ---- la commande manuelle prime -------------------------------------------

def test_commande_manuelle_gagne_sur_la_detection(prefix, monkeypatch):
    monkeypatch.setattr(
        hs_launch, "_from_lutris",
        lambda p: LaunchMethod("lutris", "Lutris", ["lutris", "x"]),
    )
    m = resolve(prefix, command="monscript.sh --plein-ecran")
    assert m.source == "config"
    assert m.argv == ["monscript.sh", "--plein-ecran"]


def test_commande_manuelle_avec_guillemets(prefix, monkeypatch):
    _sans_detection(monkeypatch)
    m = resolve(prefix, command='"/opt/mon jeu/run.sh" --hs')
    assert m.argv == ["/opt/mon jeu/run.sh", "--hs"]


def test_commande_vide_ou_invalide_ne_casse_rien(prefix, monkeypatch):
    _sans_detection(monkeypatch)
    assert resolve(prefix, command="   ") is None      # on retombe sur la détection
    assert resolve(prefix, command='foo "bar') is None  # guillemet non fermé


def test_sans_prefix_seule_la_commande_manuelle_repond():
    assert resolve(None) is None
    assert resolve(None, command="run.sh").source == "config"


def test_prefix_inexistant_ne_lance_pas_de_detection(tmp_path):
    assert resolve(tmp_path / "nulle-part") is None


# ---- Lutris : correspondance par RÉPERTOIRE, pas par nom -------------------

def _faux_lutris(monkeypatch, jeux, code=0):
    class Sortie:
        returncode = code
        stdout = json.dumps(jeux)
    monkeypatch.setattr(hs_launch.subprocess, "run", lambda *a, **k: Sortie())


def test_lutris_trouve_le_jeu_par_son_repertoire(prefix, monkeypatch):
    """C'est tout l'intérêt : le jeu s'appelle « battle-net », pas
    « Hearthstone ». Chercher par nom raterait ; le chemin, lui, est le même
    que celui dont Cairn lit déjà les journaux."""
    monkeypatch.setattr(hs_launch, "_from_desktop", lambda p: None)
    _faux_lutris(monkeypatch, [
        {"slug": "autre-jeu", "name": "Autre", "directory": "/ailleurs"},
        {"slug": "battle-net", "name": "battle-net", "directory": str(prefix)},
    ])
    m = resolve(prefix)
    assert m.source == "lutris"
    assert m.argv == ["lutris", "lutris:rungame/battle-net"]
    assert "battle-net" in m.label


def test_lutris_accepte_un_sous_dossier(prefix, monkeypatch):
    """Selon l'installation, Lutris pointe la racine et Cairn un sous-dossier
    (ou l'inverse) : l'égalité stricte raterait la moitié des cas."""
    monkeypatch.setattr(hs_launch, "_from_desktop", lambda p: None)
    _faux_lutris(monkeypatch, [
        {"slug": "bn", "name": "bn", "directory": str(prefix.parent)},
    ])
    assert resolve(prefix).source == "lutris"


def test_lutris_ignore_un_jeu_qui_habite_ailleurs(prefix, monkeypatch):
    monkeypatch.setattr(hs_launch, "_from_desktop", lambda p: None)
    _faux_lutris(monkeypatch, [
        {"slug": "hearthstone", "name": "Hearthstone", "directory": "/autre/chemin"},
    ])
    # même nommé « Hearthstone » : ce n'est pas le prefix qu'on suit
    assert resolve(prefix) is None


def test_lutris_absent_ou_muet_reste_silencieux(prefix, monkeypatch):
    monkeypatch.setattr(hs_launch, "_from_desktop", lambda p: None)
    def explose(*a, **k):
        raise FileNotFoundError("lutris")
    monkeypatch.setattr(hs_launch.subprocess, "run", explose)
    assert resolve(prefix) is None


def test_lutris_json_illisible_reste_silencieux(prefix, monkeypatch):
    monkeypatch.setattr(hs_launch, "_from_desktop", lambda p: None)
    class Sortie:
        returncode = 0
        stdout = "ceci n'est pas du json"
    monkeypatch.setattr(hs_launch.subprocess, "run", lambda *a, **k: Sortie())
    assert resolve(prefix) is None


# ---- repli .desktop --------------------------------------------------------

def test_desktop_trouve_par_le_chemin_du_prefix(prefix, tmp_path, monkeypatch):
    monkeypatch.setattr(hs_launch, "_from_lutris", lambda p: None)
    apps = tmp_path / "applications"
    apps.mkdir()
    (apps / "hs.desktop").write_text(
        f"[Desktop Entry]\nName=Hearthstone\nExec=env WINEPREFIX={prefix} wine hs.exe %U\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(hs_launch, "_desktop_dirs", lambda: [apps])
    m = resolve(prefix)
    assert m.source == "desktop"
    assert "%U" not in m.argv, "les codes de champ n'ont aucun sens hors d'un bureau"
    assert m.argv[0] == "env"


def test_desktop_ignore_les_notres(prefix, tmp_path, monkeypatch):
    """cairn.desktop parle du prefix lui aussi : sans garde-fou, le bouton
    « lancer Hearthstone » relancerait Cairn."""
    monkeypatch.setattr(hs_launch, "_from_lutris", lambda p: None)
    apps = tmp_path / "applications"
    apps.mkdir()
    (apps / "cairn.desktop").write_text(
        f"[Desktop Entry]\nName=Cairn\nExec=cairn {prefix}\n", encoding="utf-8")
    monkeypatch.setattr(hs_launch, "_desktop_dirs", lambda: [apps])
    assert resolve(prefix) is None


# ---- la commande est toujours montrable ------------------------------------

def test_la_commande_est_affichable(prefix, monkeypatch):
    _sans_detection(monkeypatch)
    m = resolve(prefix, command='"/opt/mon jeu/run.sh" --hs')
    # le launcher affiche cette chaîne : un bouton qui lance un processus sans
    # dire lequel serait une boîte noire
    assert m.command == "'/opt/mon jeu/run.sh' --hs"


def test_lancement_d_un_binaire_absent_rend_une_erreur_lisible():
    ok, message = hs_launch.launch(
        LaunchMethod("config", "test", ["/n/existe/pas/du/tout"]))
    assert ok is False and "introuvable" in message
