"""Smoke test UI : le QML charge sans erreur et affiche la fixture (offscreen)."""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.cairn.paths import CARDS_JSON, FIXTURES_DIR  # noqa: E402

pytestmark = pytest.mark.skipif(
    not CARDS_JSON.is_file() or not any(FIXTURES_DIR.glob("*/Power.log")),
    reason="base de cartes ou fixture absente",
)


def test_panneau_charge_et_affiche_la_fixture():
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow

    from src.cairn.ui.bridge import TrackerBridge
    from tools.panel import QML, FixtureReplayer

    app = QGuiApplication.instance() or QGuiApplication([])
    replayer = FixtureReplayer(speed=1)
    try:
        bridge = TrackerBridge(
            logs_root=replayer.logs_root,
            poll_ms=100_000,
            history_path=replayer.history_path,
            assume_running=True,
        )
        replayer._chunk = 2_000_000
        replayer.step()
        bridge.refresh()

        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("tracker", bridge)
        engine.load(QUrl.fromLocalFile(str(QML)))
        assert engine.rootObjects(), "QML non chargé"
        window = engine.rootObjects()[0]
        assert isinstance(window, QQuickWindow)

        app.processEvents()
        assert bridge.deckName == "Thief Priest"
        assert bridge.hasGame
        # la fenêtre a une vraie hauteur (régression : modèles non exposés → 77 px)
        assert window.height() > 300
        # Le corps défile : sans Flickable, les sections ajoutées (main,
        # ailleurs, cimetière, chrono) débordaient hors de la fenêtre et
        # devenaient inatteignables — la fin de liste doit rester joignable.
        from PySide6.QtQuick import QQuickItem

        scroller = window.findChild(QQuickItem, "deckScroller")
        assert scroller is not None, "corps défilable absent du panneau"
        reste = scroller.property("contentHeight") - scroller.property("height")
        if reste > 0:
            scroller.setProperty("contentY", reste)
            app.processEvents()
            assert scroller.property("contentY") == pytest.approx(reste), (
                "le bas du panneau doit être atteignable"
            )

        del scroller
        del window
        del engine  # avant le pont, pour éviter les bindings sur contexte null
        bridge.shutdown()  # sinon un fil de tuile émet dans un pont détruit
    finally:
        replayer.cleanup()


def test_widgets_flottants_chargent_et_se_dimensionnent():
    """Chaque widget est une fenêtre à part, dimensionnée par son contenu.

    Régression visée : le bandeau unique barrait toute la largeur de l'écran et
    masquait le haut du plateau. Un widget vide doit rester invisible (le popup
    de secrets n'a rien à dire dans la plupart des parties), et le panneau de
    compteurs doit grandir avec le nombre de compteurs armés.
    """
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow  # importé AVANT load()

    from src.cairn.app import FLOATING, QML_DIR
    from src.cairn.ui.bridge import TrackerBridge
    from tools.panel import FixtureReplayer

    app = QGuiApplication.instance() or QGuiApplication([])
    replayer = FixtureReplayer(speed=1)
    try:
        bridge = TrackerBridge(
            logs_root=replayer.logs_root,
            poll_ms=100_000,
            history_path=replayer.history_path,
            assume_running=True,
        )
        replayer._chunk = 2_000_000
        replayer.step()
        bridge.refresh()

        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("tracker", bridge)
        for name in FLOATING:
            engine.load(QUrl.fromLocalFile(str(QML_DIR / name)))
        assert len(engine.rootObjects()) == len(FLOATING), "un widget n'a pas chargé"
        app.processEvents()

        par_titre = {w.property("title"): w for w in engine.rootObjects()}
        assert set(par_titre) == {
            "Cairn · compteurs", "Cairn · mes dégâts",
            "Cairn · dégâts adverses", "Cairn · secrets", "Cairn · chrono",
            "Cairn · main adverse",
        }
        assert all(isinstance(w, QQuickWindow) for w in par_titre.values())

        # aucun widget ne doit s'étaler : c'était tout le problème du bandeau.
        # Les pastilles de la main adverse sont la seule exception assumée :
        # elles s'alignent sous un éventail de dix cartes, donc elles sont
        # larges — mais hautes de rien du tout.
        etroits = [w for t, w in par_titre.items() if t != "Cairn · main adverse"]
        assert all(w.width() < 260 for w in etroits)
        pastilles = par_titre["Cairn · main adverse"]
        assert pastilles.width() < 420 and pastilles.height() < 70

        # les pastilles d'attaque affichent bien un nombre
        assert bridge.attackMine.isdigit() and bridge.attackOpp.isdigit()
        for titre in ("Cairn · mes dégâts", "Cairn · dégâts adverses"):
            assert par_titre[titre].property("visible")
            assert par_titre[titre].height() < 60  # une pastille, pas un panneau

        # le panneau de compteurs est haut comme son contenu
        compteurs = par_titre["Cairn · compteurs"]
        assert compteurs.property("visible")
        assert compteurs.height() > 3 * bridge.countersModel.rowCount()

        # rien à dire = rien à l'écran
        assert bridge.oppSecretCount == 0
        assert not par_titre["Cairn · secrets"].property("visible")

        del par_titre
        del engine  # avant le pont, pour éviter les bindings sur contexte null
        bridge.shutdown()
    finally:
        replayer.cleanup()


def test_main_adverse_pastilles_de_tour():
    """Chaque carte tenue par l'adversaire porte son tour d'arrivée.

    « M » pour une carte gardée au mulligan, le numéro de manche sinon. Les
    cartes cachées comptent autant que les autres : savoir qu'il tient quelque
    chose depuis le tour 1 (une pièce non jouée…) change les décisions, même
    sans savoir quoi.
    """
    from PySide6.QtCore import Qt

    from src.cairn.ui.bridge import TrackerBridge
    from tools.panel import FixtureReplayer

    replayer = FixtureReplayer(speed=1)
    try:
        bridge = TrackerBridge(
            logs_root=replayer.logs_root,
            poll_ms=100_000,
            history_path=replayer.history_path,
            assume_running=True,
        )
        replayer._chunk = 2_000_000
        replayer.step()
        bridge.refresh()

        model = bridge.oppHandSlotsModel
        roles = {name.decode(): role for role, name in model.roleNames().items()}
        lignes = [
            {
                nom: model.data(model.index(i, 0), role)
                for nom, role in roles.items()
            }
            for i in range(model.rowCount())
        ]
        assert lignes, "l'adversaire tient forcément des cartes"

        # une pastille par carte : « M » ou un numéro de manche
        for ligne in lignes:
            assert ligne["badge"] == "M" or ligne["badge"].isdigit()
        # ordre chronologique : c'est ce qui rend la colonne lisible
        tours = [0 if x["badge"] == "M" else int(x["badge"]) for x in lignes]
        assert tours == sorted(tours)

        # les cartes cachées sont listées elles aussi, sans gemme de mana
        cachees = [x for x in lignes if not x["known"]]
        assert cachees, "la main adverse est majoritairement cachée"
        assert all(x["cost"] < 0 for x in cachees)
        # …et certaines portent quand même l'effet qui les a produites
        assert any(x["origin"] for x in cachees)

        bridge.shutdown()
    finally:
        replayer.cleanup()


def test_entete_bilan_du_deck_et_deckcode(tmp_path):
    """L'en-tête donne le bilan du deck, et le deckcode part au presse-papiers.

    Les deux chiffres de l'en-tête répondent à deux questions différentes : le
    bilan du deck dit « est-ce que ce deck marche ? », le bilan face à la classe
    dit « est-ce que ce duel est jouable ? ».
    """
    from PySide6.QtGui import QGuiApplication

    from src.cairn.ui.bridge import TrackerBridge
    from tools.panel import FixtureReplayer

    app = QGuiApplication.instance() or QGuiApplication([])
    replayer = FixtureReplayer(speed=1)
    try:
        bridge = TrackerBridge(
            logs_root=replayer.logs_root,
            poll_ms=100_000,
            history_path=replayer.history_path,  # historique jetable
            assume_running=True,
        )
        replayer._chunk = 2_000_000
        replayer.step()
        bridge.refresh()

        assert bridge.deckName == "Thief Priest"
        # historique vierge : pas de bilan à afficher, et surtout pas « 0-0 »
        assert bridge.deckRecord == ""

        # une partie enregistrée à la main suffit à faire apparaître le bilan
        bridge.addManualGame("Thief Priest", bridge.classNames[0], True)
        bridge.refresh()
        assert bridge.deckRecord.startswith("1-0")
        assert "100 %" in bridge.deckRecord

        # le deckcode est celui lu dans Decks.log, prêt à être recollé en jeu
        assert bridge.hasDeckcode
        bridge.copyDeckcode()
        clip = QGuiApplication.clipboard()
        if clip is not None:  # pas de presse-papiers sur certains CI offscreen
            assert clip.text().startswith("AAE")

        bridge.shutdown()
    finally:
        replayer.cleanup()


def test_fiches_add_ons_completes():
    """Chaque add-on a une icône ET une explication : le titre seul ne disait
    pas à quoi il servait (retour utilisateur : « j'ai "entrées" mais je sais
    pas ce que c'est »)."""
    from src.cairn.counters import COUNTER_DEFS
    from src.cairn.i18n import addon_desc, addon_icon, counter_label

    for cdef in COUNTER_DEFS:
        assert counter_label(cdef.key), f"{cdef.key} sans titre"
        assert addon_icon(cdef.key) != "•", f"{cdef.key} sans icône"
        desc = addon_desc(cdef.key)
        assert desc and len(desc) < 70, f"{cdef.key} : description absente ou trop longue"
        assert addon_desc(cdef.key, "en"), f"{cdef.key} sans description anglaise"


def test_launcher_charge_et_replie_les_add_ons(tmp_path):
    """Le launcher se charge, et la section des add-ons est repliée d'entrée.

    Ce test aurait attrapé la boucle de liaisons du 05/08 : la largeur des
    fiches se calculait sur la grille, qui se dimensionnait sur les fiches —
    le chargement partait à l'infini, sans message d'erreur.
    """
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem, QQuickWindow  # importés AVANT load()

    from src.cairn.app import QML_DIR
    from src.cairn.ui.bridge import TrackerBridge

    app = QGuiApplication.instance() or QGuiApplication([])
    bridge = TrackerBridge(
        logs_root=tmp_path, poll_ms=100_000,
        history_path=tmp_path / "h.sqlite", assume_running=True,
    )
    try:
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("tracker", bridge)
        engine.load(QUrl.fromLocalFile(str(QML_DIR / "Launcher.qml")))
        assert engine.rootObjects(), "launcher non chargé"
        window = engine.rootObjects()[0]
        assert isinstance(window, QQuickWindow)
        app.processEvents()

        scroller = window.findChild(QQuickItem, "launcherScroller")
        assert scroller is not None
        replie = scroller.property("contentHeight")

        titre = next(
            (t for t in window.findChildren(QQuickItem)
             if t.property("section") == "addons"), None
        )
        assert titre is not None, "titre de section des add-ons introuvable"

        # replier doit vraiment libérer de la hauteur, sinon ça ne sert à rien.
        # On teste le MÉCANISME, pas l'état de départ : celui-ci dépend de la
        # configuration de la machine qui lance les tests.
        depart = bool(titre.property("collapsed"))
        titre.setProperty("collapsed", not depart)
        app.processEvents()
        apres = scroller.property("contentHeight")
        haut, bas = max(replie, apres), min(replie, apres)
        assert haut > bas * 1.5, "replier les add-ons ne libère presque rien"

        actifs, total = bridge.addonsBadge.split("/")
        assert int(actifs) <= int(total) and int(total) >= 15

        del scroller
        del titre
        del window
        del engine
        bridge.shutdown()
    finally:
        pass


def test_bouton_lancer_hs_visible_quand_le_jeu_est_arrete():
    """Le bouton doit exister sur une installation SAINE, jeu arrêté.

    Régression : il avait été posé dans le panneau « installation incomplète »,
    qui ne s'affiche qu'en cas de problème — donc invisible précisément chez
    les gens dont tout fonctionne. Un test sur la seule présence de la
    propriété du pont n'aurait rien vu : c'est la visibilité RENDUE qui compte.
    """
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    # AVANT load() : sans cet import la fenêtre racine est un QWindow nu, sans
    # contentItem, et l'inspection de l'arbre échoue. Le test ne passait que
    # parce qu'un AUTRE test de ce fichier faisait l'import avant lui.
    from PySide6.QtQuick import QQuickWindow

    import time

    from src.cairn import hs_launch
    from src.cairn.app import QML_DIR
    from src.cairn.ui.bridge import TrackerBridge
    from tools.panel import FixtureReplayer

    app = QGuiApplication.instance() or QGuiApplication([])
    replayer = FixtureReplayer(speed=1)
    try:
        bridge = TrackerBridge(
            logs_root=replayer.logs_root,
            poll_ms=100_000,
            history_path=replayer.history_path,
            assume_running=False,          # jeu ARRÊTÉ : le bouton a un sens
        )
        replayer._chunk = 2_000_000
        replayer.step()
        bridge.refresh()
        # On FORCE l'état plutôt que de l'espérer : sans ça le test dépendait
        # de la présence d'un vrai Hearthstone sur la machine, et virait au
        # rouge dès que l'auteur lançait une partie. Un test ne doit jamais
        # dépendre de ce qui tourne à côté.
        bridge._hs_running = False
        assert bridge.hsRunning is False
        # la détection du lanceur tourne en FOND (~1,5 s) : sans cette attente
        # le test observerait l'état transitoire « pas encore résolu ».
        for _ in range(120):
            if bridge.hsLaunchResolved:
                break
            app.processEvents()
            time.sleep(0.05)
        assert bridge.hsLaunchResolved, "détection du lanceur jamais terminée"
        # Même raison que pour hsRunning : le bouton n'est visible que si un
        # lanceur a été TROUVÉ, et une machine sans Hearthstone — un runner de
        # CI, par exemple — n'en trouve aucun. Le bouton y est alors masqué à
        # juste titre, et le test échouait pour une raison qui n'a rien à voir
        # avec ce qu'il vérifie. On impose donc un lanceur, une fois la
        # résolution de fond terminée pour qu'elle ne l'écrase pas. Ce test
        # vérifie OÙ le bouton est posé dans l'arbre ; la détection, elle, a
        # ses propres tests dans test_hs_launch.py.
        bridge._launch_cle = (bridge._config.hs_launch_command,
                              str(bridge._prefix() or ""))
        bridge._launch_cache = hs_launch.LaunchMethod(
            source="config", label="lanceur de test", argv=["/bin/true"],
        )
        bridge._launch_resolu = True
        assert bridge.canLaunchHs, "le lanceur forcé n'a pas pris"

        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("tracker", bridge)
        engine.load(QUrl.fromLocalFile(str(QML_DIR / "Launcher.qml")))
        fenetre = engine.rootObjects()[0]
        assert isinstance(fenetre, QQuickWindow)
        fenetre.setProperty("visible", True)
        for _ in range(40):
            app.processEvents()

        def descend(item):
            for enfant in item.childItems():
                yield enfant
                yield from descend(enfant)

        attendu = "Lancer Hearthstone"
        boutons = [
            i for i in descend(fenetre.contentItem())
            if i.property("label") == attendu
        ]
        assert boutons, f"aucun bouton « {attendu} » dans le launcher"

        def vraiment_visible(item):
            while item is not None:
                if not item.isVisible():
                    return False
                item = item.parentItem()
            return True

        assert any(vraiment_visible(b) for b in boutons), (
            "le bouton existe mais reste masqué : vérifier la visibilité de "
            "TOUS ses parents, pas seulement la sienne"
        )

        del engine
        bridge.shutdown()
    finally:
        replayer.cleanup()


def test_apercu_de_carte_ne_s_effondre_pas_pendant_le_chargement():
    """L'aperçu doit réserver sa hauteur AVANT que l'illustration arrive.

    Le rendu officiel vient du réseau. Tant que la hauteur dépendait de
    ``artOk`` (status === Ready), la fenêtre s'ouvrait à quelques pixels de
    haut pendant l'aller-retour, puis grandissait. Relevé sur une vraie
    session : des aperçus de 1, 32, 59, 74, 100, 115, 137, 151 px au lieu de
    336 — d'où un survol qui « marchait une fois sur deux » selon que l'image
    arrivait avant ou après que l'utilisateur bouge la souris.
    """
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow

    from src.cairn.app import QML_DIR
    from src.cairn.ui.bridge import TrackerBridge
    from tools.panel import FixtureReplayer

    app = QGuiApplication.instance() or QGuiApplication([])
    replayer = FixtureReplayer(speed=1)
    try:
        bridge = TrackerBridge(
            logs_root=replayer.logs_root,
            poll_ms=100_000,
            history_path=replayer.history_path,
            assume_running=True,
        )
        replayer._chunk = 2_000_000
        replayer.step()
        for _ in range(3):
            bridge.refresh()

        modele = bridge.deckModel
        roles = {bytes(v).decode(): k for k, v in modele.roleNames().items()}
        assert modele.rowCount() > 0, "deck vide : la fixture n'a pas été rejouée"

        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("tracker", bridge)
        engine.load(QUrl.fromLocalFile(str(QML_DIR / "DeckPanel.qml")))
        panneau = engine.rootObjects()[0]
        panneau.setProperty("visible", True)
        for _ in range(40):
            app.processEvents()

        def descend(objet):
            for enfant in objet.children():
                yield enfant
                yield from descend(enfant)

        def apercu():
            for o in descend(panneau):
                if isinstance(o, QQuickWindow) and o is not panneau:
                    if "aper" in o.title():
                        return o
            return None

        for i in range(min(3, modele.rowCount())):
            card_id = modele.data(modele.index(i, 0), roles["cardId"])
            panneau.setProperty("hoverCard", "")
            for _ in range(5):
                app.processEvents()
            panneau.setProperty("hoverCard", card_id)
            # volontairement PEU de cycles : on veut l'état AVANT que le
            # réseau ait pu répondre. C'est exactement l'instant qui cassait.
            for _ in range(3):
                app.processEvents()
            fenetre = apercu()
            assert fenetre is not None, f"aucun aperçu ouvert pour {card_id}"
            assert fenetre.height() >= 300, (
                f"aperçu effondré à {fenetre.height()} px pour {card_id} : "
                "la hauteur ne doit pas attendre l'illustration"
            )

        del engine
        bridge.shutdown()
    finally:
        replayer.cleanup()


def test_les_proprietes_du_pont_sont_quasi_gratuites():
    """Aucune propriété QML ne doit lancer de sous-processus.

    Régression vécue en production : ``canLaunchHs`` / ``hsLaunchCommand``
    résolvaient le lanceur à chaque lecture, donc à chaque signal ``changed``
    (toutes les 500 ms). La résolution lance ``lutris -l --json``, mesuré à
    1,4-1,9 s. La boucle d'événements ne rendait plus la main, KDE affichait
    « Cairn — launcher (Ne répond plus) », et plus aucun survol ne marchait.

    Une propriété lue par une liaison QML est lue des milliers de fois : elle
    doit être un accès mémoire, jamais un travail. Ce test verrouille ça pour
    TOUTES les propriétés du pont, pas seulement celles du lancement.
    """
    import time

    from PySide6.QtCore import QMetaProperty
    from PySide6.QtGui import QGuiApplication

    from src.cairn.ui.bridge import TrackerBridge
    from tools.panel import FixtureReplayer

    QGuiApplication.instance() or QGuiApplication([])
    replayer = FixtureReplayer(speed=1)
    try:
        bridge = TrackerBridge(
            logs_root=replayer.logs_root,
            poll_ms=100_000,
            history_path=replayer.history_path,
            assume_running=True,
        )
        replayer._chunk = 2_000_000
        replayer.step()
        bridge.refresh()

        meta = bridge.metaObject()
        noms = [meta.property(i).name() for i in range(meta.propertyCount())]
        noms = [n for n in noms if n != "objectName"]
        assert "canLaunchHs" in noms, "la propriété surveillée a disparu"

        lentes = []
        for nom in noms:
            debut = time.perf_counter()
            for _ in range(5):
                getattr(bridge, nom)
            ms = (time.perf_counter() - debut) * 1000 / 5
            if ms > 50:            # large : on cherche un sous-processus (>1000 ms)
                lentes.append((nom, ms))

        assert not lentes, (
            "propriétés trop lentes pour une liaison QML : "
            + ", ".join(f"{n} = {ms:.0f} ms" for n, ms in lentes)
            + " — une propriété ne doit rien calculer de coûteux, encore moins "
              "lancer un sous-processus"
        )
        bridge.shutdown()
    finally:
        replayer.cleanup()


def test_changer_de_ligue_ne_change_pas_le_palier(tmp_path, monkeypatch):
    """Régression : le launcher inversait l'échelle des paliers.

    Le modèle du palier descend de 10 à 1 — l'index 0 vaut donc le palier 10.
    La liste des ligues envoyait ``niveauBox.currentIndex + 1``, ce qui donnait
    11 − palier : « Or 5 » devenait « Platine 6 » au simple changement de
    ligue, et quelqu'un qui entrait en Bronze 10 était enregistré Bronze 1 —
    l'extrémité opposée de l'échelle. Le rang étant une métadonnée du corpus
    partagé, l'erreur ne se voyait pas et voyageait quand même.

    Ce test pilote les VRAIES listes du launcher : un test sur ``setRank`` seul
    n'aurait rien vu, puisque le pont recevait consciencieusement la mauvaise
    valeur.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from PySide6.QtCore import Q_ARG, QMetaObject, Qt, QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickItem, QQuickWindow  # importés AVANT load()

    from src.cairn.app import QML_DIR
    from src.cairn.ui.bridge import TrackerBridge

    app = QGuiApplication.instance() or QGuiApplication([])
    bridge = TrackerBridge(
        logs_root=tmp_path, poll_ms=100_000,
        history_path=tmp_path / "h.sqlite", assume_running=True,
    )
    engine = QQmlApplicationEngine()
    try:
        bridge.setRank(3, 5)                      # index 3 = GOLD, palier 5
        assert bridge.rankLabel == "Or 5"

        engine.rootContext().setContextProperty("tracker", bridge)
        engine.load(QUrl.fromLocalFile(str(QML_DIR / "Launcher.qml")))
        assert engine.rootObjects(), "launcher non chargé"
        window = engine.rootObjects()[0]
        assert isinstance(window, QQuickWindow)
        app.processEvents()

        ligue = window.findChild(QQuickItem, "rankLeagueCombo")
        palier = window.findChild(QQuickItem, "rankLevelCombo")
        assert ligue is not None and palier is not None, "listes du rang introuvables"

        # ce que l'utilisateur LIT dans la liste des paliers
        modele = list(palier.property("model"))
        assert modele[palier.property("currentIndex")] == 5

        # il déroule la ligue, choisit Platine, et ne touche à rien d'autre
        ligue.setProperty("currentIndex", 4)
        QMetaObject.invokeMethod(ligue, "activated", Qt.DirectConnection, Q_ARG(int, 4))
        app.processEvents()
        assert bridge.rankLabel == "Platine 5", bridge.rankLabel
        assert bridge._rang_brut() == "PLATINUM 5"

        # puis il choisit le palier 8 : index 2 dans un modèle qui descend
        palier.setProperty("currentIndex", 2)
        QMetaObject.invokeMethod(palier, "activated", Qt.DirectConnection, Q_ARG(int, 2))
        app.processEvents()
        assert bridge.rankLabel == "Platine 8", bridge.rankLabel

        # depuis « non renseigné », on entre dans une ligue par son palier 10 —
        # le pire de la ligue, ce que la liste affiche déjà. Jamais le palier 1.
        bridge.setRank(0, 0)
        app.processEvents()
        ligue.setProperty("currentIndex", 1)
        QMetaObject.invokeMethod(ligue, "activated", Qt.DirectConnection, Q_ARG(int, 1))
        app.processEvents()
        assert bridge._rang_brut() == "BRONZE 10", bridge._rang_brut()

        del ligue
        del palier
        del window
    finally:
        del engine
        bridge.shutdown()


# ---- partie perdue par déconnexion ----------------------------------------

def _faux_pont(assume_running: bool = False):
    """Le calcul d'abandon seul, sans monter tout le pont Qt."""
    from src.cairn.ui.bridge import TrackerBridge

    class Faux:
        SILENCE_ABANDON_S = TrackerBridge.SILENCE_ABANDON_S
        _assume_running = assume_running
        _partie_abandonnee = TrackerBridge._partie_abandonnee

    return Faux()


def _partie_a(secondes_avant: int):
    """Une partie dont la dernière ligne de journal date d'il y a N secondes."""
    from datetime import datetime, timedelta
    from src.cairn.game_state import Game

    t = datetime.now() - timedelta(seconds=secondes_avant)
    return Game(ts=t.strftime("%H:%M:%S.0000000"),
                last_ts=t.strftime("%H:%M:%S.0000000"))


def test_partie_coupee_par_une_deconnexion_est_abandonnee():
    """Une déconnexion n'écrit jamais STATE=COMPLETE : le journal s'arrête net.
    Sans garde-fou les panneaux restaient au-dessus du menu principal."""
    assert _faux_pont()._partie_abandonnee(_partie_a(600)) is True


def test_partie_vivante_n_est_pas_abandonnee():
    """Hearthstone écrit en continu pendant une partie : quelques secondes de
    silence sont normales, trois minutes ne le sont pas."""
    assert _faux_pont()._partie_abandonnee(_partie_a(20)) is False


def test_rejeu_d_archive_jamais_abandonne():
    """En rejeu, les horodatages sont ceux d'un autre jour : appliquer le
    délai masquerait toute la partie."""
    assert _faux_pont(assume_running=True)._partie_abandonnee(_partie_a(99999)) is False


# ---- choix manuel du deck -------------------------------------------------

def test_deck_force_est_lie_a_la_partie_en_cours():
    """Le choix ne doit pas déborder sur la partie suivante : sinon il devient
    un réglage caché, et le deck d'hier revient sur la partie d'aujourd'hui —
    exactement le bug qu'on vient de corriger dans l'autre sens."""
    from src.cairn.ui.bridge import TrackerBridge
    from src.cairn.decks_log import PlayerDeck
    from src.cairn.game_state import Game

    class Faux:
        _deck_force = TrackerBridge._deck_force
        _deck_force_nom = "A"
        _deck_force_partie = None
        _player_decks = [PlayerDeck(name="A", deck_id=1, deckstring="AAE")]

    pont, partie = Faux(), Game(ts="10:00:00.0000000")

    # première partie : le choix ne vaut que pour elle, il faut l'y rattacher
    assert pont._deck_force(partie) is None      # rattachement, choix effacé
    pont._deck_force_nom = "A"
    trouve = pont._deck_force(partie)
    assert trouve is not None and trouve.name == "A"

    # partie suivante : retour à la déduction automatique
    assert pont._deck_force(Game(ts="11:00:00.0000000")) is None
    assert pont._deck_force_nom == ""


def test_seuls_les_decks_avec_liste_sont_proposes():
    """`knownDecks` contient aussi des noms venus de l'historique, sans
    deckstring : les imposer n'afficherait aucune carte."""
    from src.cairn.ui.bridge import TrackerBridge
    from src.cairn.decks_log import PlayerDeck

    class Faux:
        playerDecks = TrackerBridge.playerDecks.fget
        _player_decks = [
            PlayerDeck(name="avec", deck_id=1, deckstring="AAECAQ=="),
            PlayerDeck(name="sans", deck_id=2, deckstring=""),
        ]

    assert Faux.playerDecks(Faux()) == ["avec"]
