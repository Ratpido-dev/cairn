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


# Nom du verrou d'instance unique. Sous Wayland il porte le même identifiant
# que l'app_id, ce qui le rend prévisible sans dépendre du chemin d'install.
_VERROU = "cairn-instance"

# Titre du launcher, tel que Launcher.qml le pose. C'est la SEULE fenêtre
# qu'un second lancement doit ramener au premier plan.
LAUNCHER_TITRE = "Cairn — launcher"


def _instance_deja_lancee() -> bool:
    """Vrai si un Cairn tourne déjà — et on lui demande de se montrer.

    Un second lancement posait dix fenêtres de plus par-dessus les premières,
    chacune avec son propre suivi du journal : deux fois le travail, deux fois
    la mémoire, et des règles KWin qui ne savaient plus quelle fenêtre placer.
    Cliquer une deuxième fois sur l'icône est pourtant le geste le plus naturel
    du monde quand les panneaux sont cachés derrière le jeu.

    Un socket local plutôt qu'un fichier de verrou : un fichier survit à un
    plantage et bloque alors tous les lancements suivants, ce qui est pire que
    le problème qu'il résout. Le socket, lui, meurt avec le processus.
    """
    from PySide6.QtNetwork import QLocalSocket

    sonde = QLocalSocket()
    sonde.connectToServer(_VERROU)
    if not sonde.waitForConnected(300):
        return False
    sonde.write(b"montre-toi")
    sonde.waitForBytesWritten(300)
    sonde.disconnectFromServer()
    return True


def _poser_le_verrou(app, engine) -> object:
    """Ouvre le socket d'instance et remet les fenêtres au premier plan quand
    un second lancement s'annonce. Rend le serveur, à garder en vie."""
    from PySide6.QtNetwork import QLocalServer

    QLocalServer.removeServer(_VERROU)   # reste d'un plantage précédent
    serveur = QLocalServer(app)

    def _reveiller():
        client = serveur.nextPendingConnection()
        if client is not None:
            client.disconnectFromServer()
        # UNIQUEMENT le launcher. Les autres fenêtres — panneaux, widgets,
        # consentement — ont une visibilité pilotée par une liaison QML, et
        # ``show()`` l'écrase : réveiller tout le monde faisait réapparaître la
        # question du partage à chaque re-clic sur l'icône, alors qu'elle avait
        # déjà été répondue. Les panneaux, eux, doivent rester régis par « une
        # partie est-elle en cours ».
        for fenetre in engine.rootObjects():
            if fenetre.property("title") != LAUNCHER_TITRE:
                continue
            # Sous Wayland un client ne peut pas se donner le focus ; montrer
            # la fenêtre et la relever est tout ce qui est permis.
            fenetre.show()
            fenetre.raise_()
            fenetre.requestActivate()

    serveur.newConnection.connect(_reveiller)
    serveur.listen(_VERROU)
    return serveur


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    if _instance_deja_lancee():
        print("Cairn est déjà lancé.", file=sys.stderr)
        return 0

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

    verrou = _poser_le_verrou(app, engine)   # à garder en vie : sinon le
    # socket se ferme et un second lancement repart de plus belle
    code = app.exec()
    verrou.close()
    del engine  # détruire le moteur AVANT le pont (contexte null sinon)
    bridge.shutdown()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
