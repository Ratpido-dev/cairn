"""Point d'entrée de Cairn — c'est ce que lance la commande `cairn`.

Contrairement à ``tools/panel.py`` (qui suppose un dépôt et bricole
``sys.path``), ce module fonctionne depuis une installation normale : les
fichiers QML sont retrouvés relativement au paquet, et la base de cartes est
téléchargée à la volée au premier lancement si elle manque.
"""

from __future__ import annotations

import sys
from pathlib import Path

QML_DIR = Path(__file__).resolve().parent / "ui" / "qml"
# L'icône est embarquée : la résolution par thème échoue dès que
# ~/.local/share/icons/hicolor n'a pas d'index.theme (cas courant).
ICON = Path(__file__).resolve().parent / "ui" / "cairn.svg"
# Fenêtres flottantes indépendantes : une par widget, pour que chacune ait sa
# propre position mémorisée (règle KWin cairn-pos-*) au lieu d'un bandeau unique
# qui barrait le haut de l'écran.
FLOATING = ("CountersPanel.qml", "AttackMine.qml", "AttackOpp.qml",
            "SecretsPopup.qml", "TurnTimer.qml", "OppHandDots.qml")
WINDOWS = ("DeckPanel.qml", "OppPanel.qml", "Launcher.qml",
           "Consent.qml") + FLOATING


def ensure_cards(verbose: bool = True) -> bool:
    """Télécharge la base de cartes si elle manque (premier lancement), et la
    rafraîchit si Hearthstone a été patché depuis la dernière fois.

    Sans elle Cairn ne sait nommer aucune carte : mieux vaut un téléchargement
    d'une poignée de mégaoctets qu'un écran vide inexplicable. Avec une base
    périmée c'est pire, parce que rien ne le signale : après le patch du
    18/08/2026 le tracker affichait encore huit cartes à leur ancien coût.

    Le contrôle est volontairement SYNCHRONE, avant que l'interface ne charge :
    il ne coûte une requête HEAD que toutes les douze heures, et recharger la
    base à chaud pendant une partie demanderait de propager le changement dans
    le tracker, la vue de deck et les compteurs — beaucoup de risque pour
    quelques secondes gagnées un jour de patch.
    """
    from .paths import CARDS_DIR, CARDS_JSON

    if CARDS_JSON.is_file():
        try:
            from .cards_fetch import update_if_stale

            update_if_stale(verbose=verbose)
        except Exception as err:  # un patch raté ne doit jamais bloquer Cairn
            print(f"Contrôle de la base de cartes impossible : {err}",
                  file=sys.stderr)
        return True
    if verbose:
        print(f"Première utilisation : téléchargement de la base de cartes "
              f"vers {CARDS_DIR} …", flush=True)
    try:
        from .cards_fetch import fetch

        fetch("frFR")
        fetch("enUS")
    except Exception as err:  # réseau coupé, miroir en panne…
        print(f"Échec du téléchargement de la base de cartes : {err}", file=sys.stderr)
        print("Réessaie plus tard avec :  cairn-cards", file=sys.stderr)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    if not ensure_cards():
        return 1

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow  # noqa: F401  (avant engine.load)

    from .ui.bridge import TrackerBridge

    app = QGuiApplication(argv)
    app.setApplicationName("Cairn")
    app.setOrganizationName("cairn")
    # app_id Wayland stable : les règles KWin ciblent « cairn », pas « python3 »
    app.setDesktopFileName("cairn")
    icon = QIcon(str(ICON)) if ICON.is_file() else QIcon()
    if icon.isNull():
        icon = QIcon.fromTheme("cairn")
    app.setWindowIcon(icon)

    bridge = TrackerBridge()
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("tracker", bridge)
    for name in WINDOWS:
        engine.load(QUrl.fromLocalFile(str(QML_DIR / name)))
    if not engine.rootObjects():
        print("Échec de chargement de l'interface QML.", file=sys.stderr)
        return 1

    code = app.exec()
    del engine  # détruire le moteur AVANT le pont (contexte null sinon)
    bridge.shutdown()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
