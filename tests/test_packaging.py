"""Empaquetage : chemins de données, raccourci, métadonnées du projet.

Ces tests protègent l'installation « chez quelqu'un d'autre » : c'est là que
les chemins en dur et les fichiers oubliés se voient.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


# ---- résolution du dossier de données ---------------------------------------

def _paths_with_env(tmp_path, **env):
    """Recharge cairn.paths dans un sous-processus avec un environnement donné."""
    code = (
        "import json;"
        "from src.cairn.paths import DATA_DIR, CARDS_JSON;"
        "print(json.dumps({'data': str(DATA_DIR), 'cards': str(CARDS_JSON)}))"
    )
    e = dict(os.environ, **env)
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=e, capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    import json

    return json.loads(out.stdout)


def test_variable_denvironnement_prioritaire(tmp_path):
    r = _paths_with_env(tmp_path, CAIRN_DATA_DIR=str(tmp_path / "ailleurs"))
    assert r["data"] == str(tmp_path / "ailleurs")
    assert r["cards"].endswith("cards/cards.frFR.json")


def test_mode_depot_utilise_le_dossier_data(tmp_path):
    """Lancé depuis les sources, on garde data/ du dépôt (pas de doublon)."""
    r = _paths_with_env(tmp_path, CAIRN_DATA_DIR="")
    assert r["data"] == str(ROOT / "data")


def test_mode_installe_retombe_sur_xdg(tmp_path):
    """Sans dossier data/ voisin, tout va dans ~/.local/share/cairn."""
    faux_home = tmp_path / "home"
    (faux_home / ".local/share").mkdir(parents=True)
    code = (
        "import json, sys, types, pathlib;"
        "import src.cairn.paths as p;"
        "print(json.dumps(str(p._xdg_data())))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=dict(os.environ, HOME=str(faux_home), XDG_DATA_HOME=str(faux_home / ".local/share")),
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    assert str(faux_home) in out.stdout


# ---- fichiers d'empaquetage --------------------------------------------------

def test_raccourci_bien_forme():
    text = (ROOT / "packaging/cairn.desktop").read_text(encoding="utf-8")
    for key in ("Type=Application", "Name=Cairn", "Exec=cairn", "Icon=cairn",
                "Terminal=false", "StartupWMClass=cairn"):
        assert key in text, f"clé manquante : {key}"
    # StartupWMClass doit coller à l'app_id posé par l'application, sinon
    # l'icône de la barre des tâches ne se rattache pas à la fenêtre
    app = (ROOT / "src/cairn/app.py").read_text(encoding="utf-8")
    assert 'setDesktopFileName("cairn")' in app


def test_icone_presente_et_lisible():
    svg = (ROOT / "packaging/cairn.svg").read_text(encoding="utf-8")
    assert svg.lstrip().startswith("<svg")
    assert "viewBox" in svg          # indispensable pour être redimensionnable
    assert "#e08a2e" in svg          # la pierre de faîte, couleur de la marque


def test_pyproject_coherent():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'cairn = "cairn.app:main"' in text
    assert 'cairn-doctor = "cairn.doctor:main"' in text
    assert 'cairn-cards = "cairn.cards_fetch:main"' in text
    # le QML doit voyager avec le paquet, sinon l'interface ne charge pas
    assert '"ui/qml/*.qml"' in text
    # les modules cités par les points d'entrée existent bien
    for mod in ("app", "doctor", "cards_fetch"):
        assert (ROOT / "src/cairn" / f"{mod}.py").is_file()


def test_installateur_sans_sudo_ni_chemin_absolu_en_dur():
    sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    # on ignore les commentaires : le mot peut légitimement y figurer
    code = "\n".join(l for l in sh.splitlines() if not l.lstrip().startswith("#"))
    assert "sudo" not in code, "l'installation doit rester dans le dossier personnel"
    assert "XDG_DATA_HOME" in sh and "XDG_CURRENT_DESKTOP" in sh
    # aucun chemin de la machine de développement ne doit traîner
    assert "/home/ratpido" not in sh
    assert "--uninstall" in sh and "--desktop" in sh


@pytest.mark.skipif(not (ROOT / "install.sh").is_file(), reason="pas d'installateur")
def test_installateur_syntaxiquement_valide():
    assert subprocess.run(["bash", "-n", str(ROOT / "install.sh")]).returncode == 0


def test_aucun_chemin_machine_en_dur_dans_le_paquet():
    """Le bug qui rendait le projet inutilisable ailleurs : un chemin en dur."""
    for py in (ROOT / "src/cairn").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "/home/ratpido" not in text, f"chemin de dev dans {py.name}"
        assert not re.search(r'Path\.home\(\)\s*/\s*"Games"', text), \
            f"prefix de jeu en dur dans {py.name}"


# ---- icône : le raccourci ne doit jamais rester blanc ------------------------

def test_icone_embarquee_dans_le_paquet():
    """L'icône voyage AVEC le paquet : la résolution par thème échoue dès que
    ~/.local/share/icons/hicolor n'a pas d'index.theme, cas fréquent."""
    icon = ROOT / "src/cairn/ui/cairn.svg"
    assert icon.is_file(), "icône absente du paquet"
    assert (ROOT / "packaging/cairn.svg").read_text(encoding="utf-8") == \
        icon.read_text(encoding="utf-8"), "les deux copies ont divergé"

    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"ui/*.svg"' in text, "l'icône ne serait pas installée avec le paquet"

    app = (ROOT / "src/cairn/app.py").read_text(encoding="utf-8")
    assert "QIcon(str(ICON))" in app, "l'icône doit être chargée par chemin, pas par thème"


def test_icone_se_rasterise_vraiment():
    """Un SVG accepté mais rendu vide donnerait la même page blanche."""
    pytest.importorskip("PySide6")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication, QIcon

    app = QGuiApplication.instance() or QGuiApplication([])
    pixmap = QIcon(str(ROOT / "src/cairn/ui/cairn.svg")).pixmap(64, 64)
    assert not pixmap.isNull() and pixmap.size().width() == 64

    image = pixmap.toImage()
    couleurs = {
        image.pixelColor(x, y).name()
        for x in range(0, 64, 2)
        for y in range(0, 64, 2)
    }
    assert "#e08a2e" in couleurs, "la pierre de faîte (braise) n'est pas rendue"
    assert "#8b93a7" in couleurs, "les pierres grises ne sont pas rendues"


def test_installateur_pose_une_icone_resoluble():
    """Deux filets : index.theme pour la résolution par nom, ET chemin absolu."""
    sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "index.theme" in sh
    assert "Icon=$ICONS/cairn.svg" in sh, "le raccourci doit pointer un chemin absolu"
