#!/usr/bin/env python3
"""Captures d'écran reproductibles, alimentées par une fixture — QA visuelle.

Usage : python tools/screenshot.py [octets] [dossier] [fixture]

Injecte N octets d'une partie archivée (défaut : 2 Mo ≈ milieu de partie),
laisse les tuiles d'art arriver, puis capture chaque fenêtre hors écran. Aucun
Hearthstone n'a besoin de tourner, et le rendu est déterministe : la même
fixture et le même nombre d'octets redonnent exactement la même image.

Les captures publiées sont prises sur des fixtures **pseudonymisées**
(``cairn.sharing.pseudonymiser_fichier``) : un journal brut contient le
battletag de l'adversaire.
"""

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402  (import AVANT le load :
# sans lui, rootObjects() rend un wrapper QWindow non downcasté, sans grabWindow)

from src.cairn.app import WINDOWS  # noqa: E402
from src.cairn.ui.bridge import TrackerBridge  # noqa: E402
from tools.panel import QML_DIR, FixtureReplayer  # noqa: E402

# Nom de fichier par fenêtre. La liste vient de ``app.WINDOWS``, donc une
# fenêtre ajoutée au produit se capture toute seule — c'est ce qui manquait
# quand le bandeau de compteurs a été supprimé et que ce script a cessé de
# fonctionner sans que rien ne le signale.
SORTIES = {
    "DeckPanel.qml": "panneau-deck",
    "OppPanel.qml": "panneau-adversaire",
    "Launcher.qml": "launcher",
    "Consent.qml": "consentement",
    "CountersPanel.qml": "compteurs",
    "AttackMine.qml": "attaque-moi",
    "AttackOpp.qml": "attaque-adversaire",
    "SecretsPopup.qml": "secrets",
    "TurnTimer.qml": "chrono",
    "OppHandDots.qml": "main-adverse",
}


def main() -> None:
    nbytes = int(sys.argv[1]) if len(sys.argv) > 1 else 2_000_000
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "docs" / "captures"
    fixture = sys.argv[3] if len(sys.argv) > 3 else None

    app = QGuiApplication([])
    replayer = FixtureReplayer(speed=1, fixture=fixture)
    bridge = TrackerBridge(
        logs_root=replayer.logs_root,
        poll_ms=100_000,
        history_path=replayer.history_path,
        assume_running=True,
    )

    # injection déterministe de N octets, puis rafraîchissements manuels
    replayer._chunk = nbytes
    replayer.step()
    for _ in range(3):
        bridge.refresh()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("tracker", bridge)
    for name in WINDOWS:
        engine.load(QUrl.fromLocalFile(str(QML_DIR / name)))
    if not engine.rootObjects():
        sys.exit("Échec de chargement du QML")

    # Forcer l'affichage de chaque fenêtre, ce qui casse au passage les
    # liaisons du type ``visible: !tracker.consentAsked``. Sans ça, une fenêtre
    # que la configuration locale masque n'est jamais mise en page : elle garde
    # la taille de son premier calcul et se capture avec tous ses textes
    # empilés — c'est exactement ce qui arrivait au dialogue de consentement
    # dès lors qu'on avait répondu une fois à la question.
    for window in engine.rootObjects():
        window.setProperty("visible", True)

    # les tuiles d'art arrivent en fond : sans attente, la capture montre des
    # lignes nues et ne vaut rien comme QA visuelle
    deadline = time.monotonic() + 25
    while bridge.tilesPending and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.1)
    # Laisse le rendu se stabiliser. Il en faut beaucoup plus qu'on ne croit :
    # les fenêtres qui se dimensionnent d'après leur contenu (le dialogue de
    # consentement) sortent trop courtes du premier passage de layout, et la
    # capture montre alors des textes empilés les uns sur les autres. Vingt
    # passages ne suffisaient pas ; cent vingt oui, pour deux secondes.
    for _ in range(120):
        app.processEvents()
        time.sleep(0.02)

    out.mkdir(parents=True, exist_ok=True)
    for name, window in zip(WINDOWS, engine.rootObjects()):
        assert isinstance(window, QQuickWindow), type(window)
        image = window.grabWindow()
        chemin = out / f"apercu-{SORTIES.get(name, Path(name).stem.lower())}.png"
        image.save(str(chemin))
        print(f"{chemin.name} ({image.width()}×{image.height()})")
    print(f"\ndeck : {bridge.deckName}, vs {bridge.opponentName}, "
          f"{bridge.remainingTotal} au deck")
    # détruire le moteur AVANT le pont : sinon les bindings QML se réévaluent
    # sur un contexte null à la sortie (pluie de TypeError sans conséquence)
    del engine
    bridge.shutdown()
    replayer.cleanup()


if __name__ == "__main__":
    main()
