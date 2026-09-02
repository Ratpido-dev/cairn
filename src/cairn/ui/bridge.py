"""Pont Python ↔ QML : modèles de listes + état exposé au panneau.

Le rafraîchissement est tiré par un QTimer (500 ms) qui appelle
``LiveTracker.poll()`` puis recalcule la :class:`DeckView` — voir
``deck_view.py`` pour le choix « fonction pure recalculée ».
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QModelIndex,
    QObject,
    Qt,
    QTimer,
    Signal,
    Slot,
)

import os
import subprocess
import sys
import threading
import time
from datetime import datetime

from ..cards_db import CardsDb
from ..config import Config, LEAGUES
from ..deck_refs import DeckRefs
from ..counters import COUNTER_DEFS, compute_counters
from ..decks_log import QueueParser, read_decks_log
from ..families import all_checklists
from ..deck_view import CLASS_FR, DeckView, compute_deck_view, opponent_class, pick_queued_deck
from ..game_state import learn_own_account, round_number
from ..history import History
from ..hs_setup import (
    client_config_ok,
    detect_prefix,
    ensure_client_config,
    ensure_log_config,
    log_config_status,
)
from ..i18n import (
    addon_desc,
    addon_icon,
    class_name,
    counter_label,
    league_name,
    row_label,
    t as t_,
)
from ..archive import SessionArchive
from ..log_watcher import LiveTracker, LogTailer
from ..paths import DATA_DIR, SESSIONS_DIR
from ..pools import pool_for
from .. import archetypes, envoi, hs_launch, sharing
from ..secrets import (
    candidates as secret_candidates,
    secret_classes_in_play,
    secrets_in_play,
)
from .tile_cache import TileCache


def _counter_rows(counters, lang: str) -> list[dict]:
    """Regroupe les compteurs en lignes « libellé | moi | adversaire ».

    L'ordre est celui de première apparition : les compteurs sont déjà rangés
    du plus général au plus contextuel, et une ligne qui saute de place à
    chaque tour serait illisible.
    """
    lignes: dict[str, dict] = {}
    for c in counters:
        if c.group != "panel":
            continue
        ligne = lignes.setdefault(
            c.pair,
            {"label": row_label(c.pair, lang), "meText": "", "meAlert": False,
             "oppText": "", "oppAlert": False, "tip": ""},
        )
        cote = "me" if c.side == "me" else "opp"
        ligne[f"{cote}Text"] = c.short or c.text
        ligne[f"{cote}Alert"] = c.alert
        # l'infobulle garde les phrases complètes, un camp par ligne
        ligne["tip"] = (ligne["tip"] + "\n" + c.text).strip() if ligne["tip"] else c.text
    return list(lignes.values())


def _fmt_minutes(seconds: int | None) -> str:
    """Durée MOYENNE d'une partie, arrondie à la minute : « 12 min ».

    Volontairement différent de ``_fmt_duration`` (« 11:29 »), qui chronomètre
    UNE partie en cours. Une moyenne à la seconde près donnerait une fausse
    impression de précision — elle porte sur quelques dizaines de parties.
    ``""`` quand rien n'est chronométré, pour que l'UI n'affiche rien plutôt
    qu'un « 0 min » qui ressemblerait à une mesure.
    """
    if not seconds or seconds <= 0:
        return ""
    return f"{round(seconds / 60)} min"


def _fmt_duration(seconds: int | None) -> str:
    """Durée lisible : « 11:29 » (mm:ss), « 1:04:12 » au-delà de l'heure."""
    if seconds is None or seconds < 0:
        return ""
    h, rest = divmod(int(seconds), 3600)
    m, sec = divmod(rest, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


class _ListModel(QAbstractListModel):
    """Modèle générique : liste de dicts, rôles déclarés à la construction."""

    def __init__(self, roles: list[str], parent=None):
        super().__init__(parent)
        self._roles = {Qt.UserRole + i: name for i, name in enumerate(roles)}
        self._items: list[dict] = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def roleNames(self):
        return {role: name.encode() for role, name in self._roles.items()}

    def data(self, index, role):
        if not index.isValid():
            return None
        return self._items[index.row()].get(self._roles.get(role, ""))

    def replace(self, items: list[dict]) -> None:
        if items == self._items:
            return
        self.beginResetModel()
        self._items = items
        self.endResetModel()


class TrackerBridge(QObject):
    """Objet racine exposé au QML (``tracker``)."""

    changed = Signal()
    tilesChanged = Signal()  # des tuiles d'art viennent d'arriver sur disque

    def __init__(
        self,
        logs_root: Path | None = None,
        poll_ms: int = 500,
        history_path: Path | None = None,
        assume_running: bool = False,  # replay/captures : pas de process HS
        parent=None,
    ):
        super().__init__(parent)
        self._db = CardsDb.load()
        self._config = Config.load()
        self._logs_root_arg = logs_root
        self._mirror = None if history_path is not None else SESSIONS_DIR
        # Archivage des sessions : jamais en mode replay/tests (history_path
        # fourni), sinon on remplirait les archives de parties rejouées.
        self._archive = (
            SessionArchive(SESSIONS_DIR)
            if history_path is None and self._config.archive_sessions
            else None
        )
        self._backfilled = False
        self._tracker = self._build_tracker()
        self._queue_parser = QueueParser()
        self._queue_events: list = []
        self._player_decks: list = []  # decks du joueur, pour la saisie manuelle
        self._decks_tailer: LogTailer | None = None
        self._view = DeckView()
        self._deckstring = ""
        self._history = History(path=history_path)
        self._recorded: set[int] = set()  # index de parties déjà en historique
        self._opp_class: str | None = None
        self._assume_running = assume_running
        self._hs_running = assume_running
        self._hs_check_countdown = 0
        self._session_game_base = 0
        self._log_full_seen = False
        self._selected_deck = ""  # filtre des stats du launcher ("" = tous)
        self._selected_class = ""  # 2e niveau de filtre : la classe adverse
        self._staged: set[str] = set()   # sessions déjà déposées dans l'outbox
        # Un seul fil de partage à la fois (préparation + envoi) : voir _en_fond
        self._partage_en_cours = threading.Event()
        # listes d'archétypes collées par l'utilisateur (cf. deck_refs.py)
        self._refs = DeckRefs()
        # résolution du lancement du jeu : mise en cache, résolue en fond
        self._launch_cle = None
        self._launch_cache = None
        self._launch_resolu = False
        self._launch_en_cours = threading.Event()
        self._tiles = TileCache(self)
        self._tiles.revisionChanged.connect(self.tilesChanged)

        # les modèles de listes existent : on peut les peupler

        self._deck_model = _ListModel(
            ["name", "cost", "total", "remaining", "cardId", "rarity",
             # « gift » : carte ARRIVÉE en cours de partie (copie, cadeau,
             # bombe) — elle s'affiche dans la liste du deck avec une icône de
             # cadeau au lieu d'une section « ENTRÉES » séparée
             "gift", "origin"],
            self,
        )
        _entry_roles = ["label", "origin", "known", "count", "cardId", "rarity"]
        self._entries_model = _ListModel(_entry_roles, self)
        self._deck_bottom_model = _ListModel(_entry_roles, self)
        self._deck_top_model = _ListModel(_entry_roles, self)
        self._opp_model = _ListModel(
            ["label", "count", "cost", "cardId", "rarity", "origin", "gift"], self)
        _card_roles = ["label", "count", "cost", "cardId", "rarity"]
        self._opp_hand_model = _ListModel(_card_roles + ["origin"], self)
        # une ligne par carte tenue, cachées comprises, avec le tour d'arrivée.
        # « created » et « creatorId » servent aux pastilles flottantes posées
        # sous sa main : cadeau quand la carte a été créée, et aperçu de la
        # carte CRÉATRICE au survol quand la carte elle-même reste cachée.
        self._opp_hand_slots_model = _ListModel(
            ["label", "known", "origin", "cost", "cardId", "rarity", "badge",
             "created", "creatorId"],
            self,
        )
        self._my_hand_model = _ListModel(_card_roles + ["origin"], self)
        # Effets globaux : le nom de l'effet, mais la CARTE SOURCE en illustration
        # et en aperçu — un enchantement n'a ni rendu ni texte utile (« PV
        # augmentés. »), sa carte source a les deux. « note » porte le texte
        # propre à l'effet, affiché sous l'aperçu.
        _effect_roles = ["label", "count", "cardId", "rarity", "origin", "note"]
        self._my_effects_model = _ListModel(_effect_roles, self)
        self._opp_effects_model = _ListModel(_effect_roles, self)
        # cartes à (1) déjà jouées (Confrontation des Tol'vir), par camp
        self._my_replay_model = _ListModel(_card_roles, self)
        self._opp_replay_model = _ListModel(_card_roles, self)
        self._opp_deck_model = _ListModel(_card_roles + ["origin", "struck"], self)
        self._my_grave_model = _ListModel(_card_roles, self)
        self._opp_grave_model = _ListModel(_card_roles, self)
        # atlas : pas de « count », chaque ligne est une place dans la file
        _atlas_roles = ["label", "cost", "cardId", "rarity", "rank"]
        self._my_atlas_model = _ListModel(_atlas_roles, self)
        self._opp_atlas_model = _ListModel(_atlas_roles, self)
        self._secrets_model = _ListModel(
            ["label", "cost", "cardId", "ruledOut", "auto"], self
        )
        # familles à cocher : une seule liste par camp, découpée en sections
        # par le rôle « title » (ListView.section côté QML)
        _family_roles = ["title", "label", "cost", "cardId", "rarity", "played"]
        self._my_family_model = _ListModel(_family_roles, self)
        self._opp_family_model = _ListModel(_family_roles, self)
        self._family_sections: tuple[int, int] = (0, 0)  # (moi, adversaire)
        self._ruled_out: set[str] = set()  # secrets barrés à la main
        # Une LIGNE par compteur, deux colonnes moi/adversaire : le
        # regroupement se fait ici et pas en QML, où il serait illisible.
        self._counters_model = _ListModel(
            ["label", "meText", "meAlert", "oppText", "oppAlert", "tip"], self
        )
        # points d'attaque : deux pastilles flottantes séparées, donc deux
        # simples chaînes plutôt qu'un modèle (« » = rien à montrer)
        self._attack: dict[str, str] = {"good": "", "bad": ""}
        # modèles du launcher
        self._addons_model = _ListModel(
            ["key", "label", "enabled", "icon", "desc"], self
        )
        # « key » double « label » : le QML colore les médaillons de classe sur
        # la clé (MAGE, ROGUE…), qui ne change pas avec la langue affichée
        self._class_stats_model = _ListModel(
            ["label", "key", "wins", "losses", "pct", "duration"], self
        )
        self._deck_stats_model = _ListModel(
            ["name", "wins", "games", "pct", "duration"], self)
        # part du camembert : archétype adverse, sa taille et son winrate
        self._archetype_model = _ListModel(
            ["label", "games", "wins", "pct", "share", "duration", "known", "slot"],
            self)
        self._deck_ref_model = _ListModel(
            ["name", "klass", "cards", "variants"], self)
        self._recent_model = _ListModel(
            ["date", "deck", "vsClass", "vsKey", "won", "session", "gameIndex",
             "duration", "conceded", "quickConcede"],
            self
        )
        self._refresh_addons_model()
        self._refresh_stats_models()

        self._refresh_deck_refs()   # listes d'archétypes déjà enregistrées

        self._poll_ms = poll_ms
        self._timer = QTimer(self)
        self._timer.setInterval(poll_ms)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

        # Rattrapage au démarrage : les parties de la veille attendent peut-être
        # encore (réseau coupé, machine éteinte avant la fin de l'envoi). En fil
        # de fond, et seulement si le joueur a accepté — sinon l'outbox est vide
        # de toute façon.
        if self._config.share_enabled:
            self._en_fond(self._vider_outbox_si_possible)

    def shutdown(self) -> None:
        """Arrête timers et téléchargements — à appeler avant de lâcher le pont.

        Sans ça, un fil de tuile qui finit après la destruction du QObject émet
        dans le vide (« Signal source has been deleted »).
        """
        self._timer.stop()
        self._tiles.stop()
        if self._archive is not None:
            self._archive.close()   # dernier bloc, sinon la fin de session est perdue

    def _build_tracker(self) -> LiveTracker:
        """Construit le suiveur sur le prefix courant (config ou détection)."""
        tracker = LiveTracker(
            logs_root=self._logs_root_arg,
            from_start=True,
            mirror_dir=self._mirror,
            prefix_override=self._config.hs_prefix or None,
            archive=self._archive,
        )
        tracker.rotation_broken = not self._config.log_rotation
        return tracker

    # ---- installation du jeu -----------------------------------------------

    def _prefix(self):
        return detect_prefix(self._config.hs_prefix or None)

    @Property(str, notify=changed)
    def hsPrefix(self):
        prefix = self._prefix()
        return str(prefix) if prefix else ""

    @Property(str, notify=changed)
    def setupProblem(self):
        """Clé du problème d'installation à signaler ("" si tout va bien)."""
        if self._logs_root_arg is not None:
            return ""  # mode replay : rien à configurer
        prefix = self._prefix()
        if prefix is None:
            return "no_prefix"
        if log_config_status(prefix).state != "ok":
            return "logs_off"
        if not client_config_ok(prefix):
            return "log_capped"
        return ""

    @Slot()
    def enableGameLogs(self):
        """Écrit le log.config du jeu (sauvegarde l'existant le cas échéant)."""
        prefix = self._prefix()
        if prefix is not None:
            ensure_log_config(prefix)
            ensure_client_config(prefix)   # lève aussi le plafond des 10 Mo
        self.changed.emit()

    # ---- lancement du jeu ---------------------------------------------------
    #
    # Cairn connaît déjà le prefix : on ne cherche donc pas un jeu qui
    # s'APPELLE Hearthstone, mais celui qui HABITE le prefix qu'on suit
    # (cf. hs_launch). La commande manuelle reste le mécanisme principal.

    def _launch_method(self):
        """Méthode de lancement, MISE EN CACHE — ne jamais résoudre ici.

        Piège coûteux, découvert en production : cette valeur est lue par
        quatre propriétés QML, donc réévaluée à chaque signal ``changed``,
        c'est-à-dire toutes les 500 ms. Or la résolution lance
        ``lutris -l --json``, **mesuré entre 1,4 et 1,9 seconde**. Résultat :
        la boucle d'événements passait son temps dans un sous-processus, KDE
        affichait « Cairn (Ne répond plus) », et plus aucun survol ne
        fonctionnait. Une propriété QML doit être quasi gratuite.

        On résout donc UNE fois, en fond, et on ne recommence que si le prefix
        ou la commande de l'utilisateur change.
        """
        cle = (self._config.hs_launch_command, str(self._prefix() or ""))
        if cle != self._launch_cle:
            self._launch_cle = cle
            self._launch_resolu = False
            self._launch_cache = None
            self._resoudre_lancement(cle)
        return self._launch_cache

    def _resoudre_lancement(self, cle) -> None:
        """Résout en fond : même une seule fois, 1,5 s sur le fil de l'UI se voit."""
        if self._launch_en_cours.is_set():
            return
        self._launch_en_cours.set()

        def _courir():
            try:
                trouve = hs_launch.resolve(self._prefix(), self._config.hs_launch_command)
            except Exception:
                trouve = None
            finally:
                self._launch_en_cours.clear()
            # le prefix a pu changer pendant la résolution : on jette le résultat
            if cle == self._launch_cle:
                self._launch_cache = trouve
                self._launch_resolu = True
                self.changed.emit()

        threading.Thread(target=_courir, daemon=True).start()

    @Property(str, notify=changed)
    def hsLaunchCommand(self):
        """La commande qui SERA exécutée — toujours affichée, jamais implicite."""
        m = self._launch_method()
        return m.command if m else ""

    @Property(str, notify=changed)
    def hsLaunchLabel(self):
        m = self._launch_method()
        return m.label if m else ""

    @Property(bool, notify=changed)
    def canLaunchHs(self):
        return self._launch_method() is not None

    @Property(bool, notify=changed)
    def hsLaunchResolved(self):
        """La détection est-elle terminée ?

        Elle tourne en fond (elle coûte ~1,5 s) : sans cet état, le launcher
        afficherait « aucun lanceur détecté » pendant une seconde avant de le
        remplacer par le bouton. Un faux négatif qui clignote est pire que
        d'attendre en silence.
        """
        self._launch_method()          # amorce la résolution si besoin
        return self._launch_resolu

    @Property(str, notify=changed)
    def hsLaunchCustom(self):
        """Ce que l'utilisateur a saisi (vide s'il s'en remet à la détection)."""
        return self._config.hs_launch_command

    @Slot(str)
    def setHsLaunchCommand(self, command: str):
        self._config.hs_launch_command = command.strip()
        self._config.save()
        self.changed.emit()

    @Slot(result=str)
    def launchHs(self) -> str:
        """Lance le jeu. Rend "" si tout va bien, sinon le message d'erreur."""
        m = self._launch_method()
        if m is None:
            return "aucune commande de lancement connue"
        ok, message = hs_launch.launch(m)
        # HS met plusieurs secondes à ouvrir sa fenêtre : on force un contrôle
        # rapproché plutôt que d'attendre le prochain cycle paresseux.
        self._hs_check_countdown = 0
        self.changed.emit()
        return "" if ok else message

    @Slot(str)
    def setPrefix(self, path: str):
        """Force le prefix quand la détection se trompe, et se rebranche dessus."""
        self._config.hs_prefix = path.strip()
        self._config.save()
        self._tracker = self._build_tracker()
        self._recorded.clear()
        self._session_game_base = 0
        self.changed.emit()

    # ---- boucle ------------------------------------------------------------

    def _refresh_own_account(self) -> None:
        """Apprend le compte du joueur dès qu'assez de parties le permettent.

        Une seule écriture de config : une fois connu, le compte ne change plus
        (c'est une identité Battle.net). On ne redemande donc rien au moteur.
        """
        if self._config.own_account:
            return
        appris = learn_own_account(self._tracker.engine.games)
        if appris:
            self._config.own_account = appris
            self._config.save()

    def refresh(self) -> None:
        # HS tourne-t-il ? (toutes les ~3 s — pgrep est peu coûteux mais pas gratuit)
        if not self._assume_running:
            self._hs_check_countdown -= 1
            if self._hs_check_countdown <= 0:
                self._hs_check_countdown = 6
                running = (
                    subprocess.run(
                        ["pgrep", "-f", "Hearthstone.exe"], capture_output=True
                    ).returncode
                    == 0
                )
                if running != self._hs_running:
                    self._hs_running = running
                    self.changed.emit()

        update = self._tracker.poll()

        # Rattrapage, une seule fois par lancement : les sessions que HS n'a pas
        # encore effacées, et celles que l'outbox de partage a conservées. C'est
        # tout ce qui reste à sauver du passé — le premier poll a déjà déclaré la
        # session EN COURS à l'archiveur, qui l'exclut donc du rattrapage.
        # Synchrone et assumé : ~0,8 s une fois au démarrage pour ~130 Mo.
        if self._archive is not None and not self._backfilled:
            self._backfilled = True
            if self._archive.backfill(self._tracker.logs_root, sharing.outbox_dir()):
                self.changed.emit()

        # log HS saturé (limite Blizzard 10 Mo) : le suivi devient aveugle —
        # prévenir l'utilisateur et cacher les overlays (partie invérifiable)
        if self._tracker.log_full != self._log_full_seen:
            self._log_full_seen = self._tracker.log_full
            self.changed.emit()

        # Rattrapage d'un gros journal : le tailer ne rend qu'une tranche par
        # passe pour ne pas figer l'interface. Enchaîner à 0 ms rend la main à
        # la boucle d'événements entre deux tranches — l'interface reste vivante
        # et le rattrapage garde sa vitesse. Retour à la cadence normale ensuite.
        self._timer.setInterval(0 if update.catching_up else self._poll_ms)

        if update.session_switched is not None:
            # Hearthstone relancé = nouveau dossier de journaux. Les mises en
            # file de la session précédente ne valent plus rien : les garder
            # faisait ressortir le deck d'hier sur la partie d'aujourd'hui.
            self._queue_events.clear()
            self._decks_tailer = LogTailer(update.session_switched / "Decks.log")
            try:
                self._player_decks = read_decks_log(update.session_switched / "Decks.log")
            except OSError:
                self._player_decks = []
            # index de BASE de la session : les parties du moteur sont globales,
            # l'historique attend un index par session (bug du 01/08 corrigé)
            self._session_game_base = len(self._tracker.engine.games) - len(update.new_games)
        if self._decks_tailer is not None:
            for line in self._decks_tailer.poll():
                queued = self._queue_parser.feed(line)
                if queued is not None:
                    self._queue_events.append(queued)

        self._refresh_own_account()

        # historique : archiver chaque partie terminée, une seule fois —
        # avec un index RELATIF à la session (les parties du moteur sont globales)
        session = self._tracker.session
        if session is not None:
            for idx, g in enumerate(self._tracker.engine.games):
                if g.complete and idx not in self._recorded and idx >= self._session_game_base:
                    if g.is_spectated(self._config.own_account):
                        # partie d'un contact regardée en spectateur : elle n'est
                        # pas à nous, ni pour les statistiques ni pour le corpus.
                        self._recorded.add(idx)
                        continue
                    if g.is_deckless_mode():
                        # Champ de bataille / Mercenaires : pas de deck, donc
                        # aucun winrate par deck ni par archétype à en tirer.
                        self._recorded.add(idx)
                        continue
                    klass = opponent_class(g, self._db)
                    loc = g.local_player_id(self._config.own_account)
                    adv = next((p for p in g.player_names if p != loc), None)
                    self._history.record(
                        session.name,
                        idx - self._session_game_base,
                        g,
                        pick_queued_deck(self._queue_events, g),
                        opponent_class=klass,
                        # archétype déduit des cartes venues de SON deck
                        opponent_archetype=archetypes.detect(
                            g, self._db, adv, klass, refs=self._refs),
                    )
                    self._recorded.add(idx)
                    self._refresh_stats_models()

        game = self._tracker.current_game
        # On devance la limite des 10 Mo de HS en vidant son journal. Hors
        # partie c'est gratuit (HS n'écrit rien entre deux parties) ; en pleine
        # partie on ne s'y résout qu'au bord du gouffre, où perdre une ligne
        # vaut mieux que perdre tout le reste de la session.
        # Parade à la limite des 10 Mo : on libère le NOM Power.log (renommage,
        # donc sans perte ni trou — cf. log_watcher). Sans effet si HS mesure sa
        # limite sur son propre descripteur, mais alors sans coût non plus.
        if self._config.log_rotation and self._tracker.free_log_name():
            self.changed.emit()
        if self._config.log_rotation:   # ancienne troncature, désactivée par défaut
            idle = game is None or game.complete
            if self._tracker.maybe_rotate(
                threshold=6 * 1024 * 1024 if idle else 8_500_000
            ):
                self.changed.emit()
        if game is None or game.is_spectated(self._config.own_account):
            # Spectateur : ni deck, ni compteurs, ni chrono. Sans ce garde-fou
            # Cairn adoptait le deck du joueur observé, puis restait « en
            # combat » au relancement suivant.
            return
        deck = pick_queued_deck(self._queue_events, game)
        # gardé pour le bouton « copier le deckcode » : la vue ne retient que
        # le nom du deck, pas la chaîne d'origine
        self._deckstring = deck.deckstring if deck else ""
        view = compute_deck_view(game, deck, self._db)
        if view == self._view:
            return
        self._view = view
        self._opp_class = opponent_class(game, self._db)

        enabled = {d.key for d in COUNTER_DEFS if self._config.counter_enabled(d.key)}
        lang = self._config.language
        counters = compute_counters(game, view, self._db, enabled=enabled, lang=lang)

        self._counters_model.replace(_counter_rows(counters, lang))
        self._attack = {"good": "", "bad": ""}
        for c in counters:
            if c.group == "attack" and c.kind in self._attack:
                self._attack[c.kind] = c.text

        self._deck_model.replace(
            [
                {
                    "name": self._db.localized_name(r.card_id, lang) if r.card_id else r.name,
                    "cost": r.cost,
                    "total": r.total,
                    "remaining": r.remaining,
                    "cardId": r.card_id,
                    "rarity": r.rarity,
                    "gift": r.gift,
                    "origin": r.origin,
                }
                for r in view.rows
            ]
        )
        def _entries(rows):
            return [
                {
                    "label": self._db.localized_name(e.card_id, lang) if (e.known and e.card_id) else e.label,
                    "origin": e.origin,
                    "known": e.known,
                    "count": e.count,
                    "cardId": e.card_id,
                    "rarity": e.rarity,
                }
                for e in rows
            ]

        self._entries_model.replace(_entries(view.entries))
        self._deck_bottom_model.replace(_entries(view.deck_bottom))
        self._deck_top_model.replace(_entries(view.deck_top))
        def _cards(rows):
            return [
                {
                    "label": self._db.localized_name(r.card_id, lang) or r.label,
                    "count": r.count,
                    "cost": r.cost,
                    "cardId": r.card_id,
                    "rarity": r.rarity,
                }
                for r in rows
            ]

        def _with_origin(rows):
            return [
                dict(d, origin=r.origin, struck=getattr(r, "struck", False))
                for d, r in zip(_cards(rows), rows)
            ]

        self._opp_hand_model.replace(_with_origin(view.opponent_hand))
        hidden = "? hidden card" if lang == "en" else "? carte cachée"
        self._opp_hand_slots_model.replace(
            [
                {
                    "label": (
                        self._db.localized_name(s.card_id, lang) if s.known else hidden
                    ),
                    "known": s.known,
                    "origin": s.origin,
                    # coût inconnu = pas de gemme de mana (CardRow : cost < 0)
                    "cost": s.cost,
                    "cardId": s.card_id,
                    "rarity": s.rarity,
                    # « M » = gardée au mulligan, sinon le numéro de manche
                    "badge": "M" if s.from_mulligan
                    else ("" if s.turn is None else str(s.turn)),
                    "created": bool(s.creator_card_id),
                    "creatorId": s.creator_card_id,
                }
                for s in view.opponent_hand_slots
            ]
        )
        self._my_hand_model.replace(_with_origin(view.my_hand))

        def _effects(effets):
            return [
                {
                    "label": self._db.localized_name(e.card_id, lang),
                    "count": e.count,
                    # illustration ET aperçu = la carte SOURCE quand on la
                    # connaît : l'enchantement n'a pas de rendu, et son propre
                    # texte (« PV augmentés. ») n'apprend rien
                    "cardId": e.source_card_id or e.card_id,
                    "rarity": e.rarity,
                    "origin": (
                        self._db.localized_name(e.source_card_id, lang)
                        if e.source_card_id else ""
                    ),
                    # l'aperçu montre la carte source : la note rappelle DE
                    # QUEL effet il s'agit, et ce que l'enchantement lui-même
                    # annonce (« Protection d'Amara — PV augmentés. »)
                    "note": " — ".join(
                        p for p in (
                            self._db.localized_name(e.card_id, lang),
                            self._db.text(e.card_id, lang),
                        ) if p
                    ) if e.source_card_id else self._db.text(e.card_id, lang),
                }
                for e in effets
            ]

        self._my_effects_model.replace(_effects(view.my_effects))
        self._opp_effects_model.replace(_effects(view.opp_effects))
        self._my_replay_model.replace(_cards(view.my_replay))
        self._opp_replay_model.replace(_cards(view.opp_replay))
        self._opp_deck_model.replace(_with_origin(view.opp_deck_known))
        self._my_grave_model.replace(_cards(view.my_graveyard))
        self._opp_grave_model.replace(_cards(view.opp_graveyard))

        def _atlas(cards):
            hidden = "? hidden card" if lang == "en" else "? carte cachée"
            return [
                {
                    "label": self._db.localized_name(c.card_id, lang) if c.known else hidden,
                    "cost": c.cost,
                    "cardId": c.card_id,
                    "rarity": c.rarity,
                    "rank": i + 1,  # rang dans la file, 1 = la prochaine à revenir
                }
                for i, c in enumerate(cards)
            ]

        self._my_atlas_model.replace(_atlas(view.my_atlas))
        self._opp_atlas_model.replace(_atlas(view.opp_atlas))

        opp_id = next(
            (p for p in game.player_names if p != game.local_player_id()), None
        )
        self._secrets_model.replace(
            [
                {
                    "label": self._db.localized_name(c.card_id, lang),
                    "cost": c.cost,
                    "cardId": c.card_id,
                    # barré à la main OU écarté par déduction
                    "ruledOut": c.card_id in self._ruled_out or c.ruled_out,
                    "auto": c.ruled_out,   # écarté par le tracker, pas par le joueur
                }
                for c in secret_candidates(game, self._db, opp_id, self._opp_class)
            ]
        )
        self._opp_secrets = secrets_in_play(game, self._db, opp_id)
        # Classes des secrets RÉELLEMENT posés : à afficher, car elles ne sont
        # pas toujours celle du héros d'en face (Chasseur qui pose un secret de
        # Mage) et la liste de candidats serait alors incompréhensible.
        self._opp_secret_classes = [
            class_name(k, lang)
            for k in secret_classes_in_play(game, self._db, opp_id)
        ]

        self._opp_model.replace(
            [
                {
                    "label": self._db.localized_name(p.card_id, lang) if p.card_id else p.label,
                    "count": p.count,
                    "cost": p.cost,
                    "cardId": p.card_id,
                    "rarity": p.rarity,
                    # d'où elle vient : nom de la carte qui la lui a donnée
                    "origin": p.origin,
                    "gift": p.created,
                }
                for p in view.opponent_plays
            ]
        )
        self._refresh_family_models(game, lang)
        self._prefetch_tiles(view)
        self._stage_for_sharing()
        self.changed.emit()

    def _stage_for_sharing(self) -> None:
        """Copie la session courante dans l'outbox, si l'utilisateur a accepté.

        Appelé à chaque poll mais ne travaille qu'une fois par session tant que
        la partie n'est pas finie : recopier 15 Mo toutes les 500 ms n'aurait
        aucun sens. Une session est redéposée quand une nouvelle partie s'y
        termine, pour que l'outbox reflète le journal complet.
        """
        if not self._config.share_enabled:
            return
        session = self._tracker.session
        if session is None:
            return
        game = self._tracker.current_game
        # on ne dépose qu'entre deux parties : pendant, le journal bouge encore
        if game is not None and not game.complete:
            return
        cle = f"{session.name}:{len(self._tracker.engine.games)}"
        if cle in self._staged:
            return
        self._staged.add(cle)   # avant le travail : sinon le poll suivant, qui
        # arrive dans 500 ms, en relance un deuxième
        meta = sharing.metadonnees(
            self._parties_de_la_session(),
            install_id=self._install_id(),
            rang=self._rang_brut(),
        )
        self._en_fond(lambda: self._preparer_et_envoyer(session, meta))

    def _preparer_et_envoyer(self, session, meta: dict) -> None:
        """Pseudonymise la session puis vide l'outbox. **Hors du fil Qt.**

        Pseudonymiser neuf mégaoctets prend une bonne seconde et l'envoi peut
        attendre trente secondes sur un réseau qui ne répond pas : les deux
        gelaient l'interface au-dessus du jeu s'ils tournaient ici.
        """
        try:
            # respirer() entre deux blocs : une regex ne rend pas le GIL,
            # ce court sommeil est le seul moment où le fil de l'interface
            # peut s'exécuter pendant la pseudonymisation.
            sharing.preparer(session, sel=self._install_id(), meta=meta,
                             respirer=lambda: time.sleep(0.002))
        except OSError:
            return   # disque plein, session disparue : jamais bloquant
        self._vider_outbox_si_possible()

    def _vider_outbox_si_possible(self) -> None:
        """Envoie ce qui attend, si l'utilisateur a accepté et qu'un point de
        collecte est configuré. Silencieux de bout en bout."""
        if not self._config.share_enabled:
            return
        try:
            envoi.envoyer_en_attente(install_id=self._install_id())
        except Exception:
            pass   # un envoi raté ne doit JAMAIS remonter jusqu'au joueur
        self.changed.emit()   # le compteur du launcher suit

    def _en_fond(self, travail) -> None:
        """Lance ``travail`` dans un fil, **un seul à la fois**.

        Sans le verrou, une fin de partie pendant un envoi lent lancerait un
        deuxième fil qui réécrirait l'outbox pendant que le premier la lit.
        """
        if self._partage_en_cours.is_set():
            return
        self._partage_en_cours.set()

        def _courir():
            try:
                travail()
            finally:
                self._partage_en_cours.clear()

        threading.Thread(target=_courir, name="cairn-partage", daemon=True).start()

    def _parties_de_la_session(self) -> list[dict]:
        """Type et format de chaque partie — c'est dans le journal, mais le
        recopier ici évite au destinataire de tout rejouer pour trier."""
        return [
            {
                "type": g.game_type or "",       # GT_RANKED, GT_CASUAL…
                "format": g.format_type or "",   # FT_STANDARD, FT_WILD…
                "tours": g.turns,
                "terminee": g.complete,
            }
            for g in self._tracker.engine.games
        ]

    def _rang_brut(self) -> str:
        """« GOLD 7 » / « LEGEND » / "" — la forme stockée, pas la traduction."""
        ligue = self._config.rank_league
        if not ligue:
            return ""
        if ligue == "LEGEND":
            return "LEGEND"
        return f"{ligue} {self._config.rank_level}" if self._config.rank_level else ligue

    def _install_id(self) -> str:
        """Identifiant d'installation, créé au premier besoin."""
        if not self._config.install_id:
            self._config.install_id = sharing.nouvel_identifiant_installation()
            self._config.save()
        return self._config.install_id

    def _refresh_family_models(self, game, lang: str) -> None:
        """Cases à cocher des familles (Rafaam, sœurs Coursevent), par camp.

        Un compteur « 7/9 » dit combien ; ces listes disent *lesquels*, ce qui
        est l'information dont dépend le tour à jouer.
        """
        local = game.local_player_id()
        opp = next((p for p in game.player_names if p != local), None)
        counts = []
        for model, player_id in (
            (self._my_family_model, local), (self._opp_family_model, opp)
        ):
            rows = []
            families = all_checklists(game, self._db, player_id, lang)
            counts.append(len(families))
            for family in families:
                title = (f"{t_(f'family_{family.key}', lang)} · "
                         f"{family.played}/{family.total}")
                rows += [
                    {
                        "title": title,
                        "label": c.label,
                        "cost": c.cost,
                        "cardId": c.card_id,
                        "rarity": c.rarity,
                        "played": c.played,
                    }
                    for c in family.cards
                ]
            model.replace(rows)
        # le QML dimensionne sa liste sur lignes + en-têtes : il lui faut le
        # nombre de sections, que ListView ne sait pas donner avant rendu
        self._family_sections = tuple(counts)

    def _prefetch_tiles(self, view: DeckView) -> None:
        """Illustre tout le deck d'un coup plutôt que ligne par ligne au survol.

        Les 30 cartes de la liste sont demandées dès la première vue ; le reste
        (cimetières, main adverse…) suit au fil de la partie. Le cache ignore
        ce qu'il a déjà, l'appel est donc gratuit une fois les tuiles sur disque.
        """
        for rows in (
            view.rows, view.entries, view.deck_bottom, view.deck_top,
            view.opponent_plays, view.opponent_hand,
            view.my_hand, view.my_effects, view.opp_effects,
            view.opp_deck_known,
            view.my_graveyard, view.opp_graveyard, view.my_atlas, view.opp_atlas,
        ):
            for row in rows:
                if row.card_id:
                    self._tiles.fetch(row.card_id)
        # les vignettes des compteurs viennent de cartes qui ne sont pas
        # forcément dans une des listes ci-dessus (Rafaam adverse, Zarimi…)
        for i in range(self._counters_model.rowCount()):
            idx = self._counters_model.index(i, 0)
            for role, name in self._counters_model.roleNames().items():
                if name == b"cardId":
                    cid = self._counters_model.data(idx, role)
                    if cid:
                        self._tiles.fetch(cid)

    # ---- tuiles d'art ------------------------------------------------------

    @Slot(str, result=str)
    def tile(self, card_id: str) -> str:
        """URL locale de la tuile d'art, "" tant qu'elle n'est pas téléchargée."""
        return self._tiles.url(card_id)

    @Property(int, notify=tilesChanged)
    def tileRevision(self) -> int:
        """Change quand des tuiles arrivent — les liaisons QML s'y accrochent
        pour se réévaluer sans avoir à observer chaque fichier."""
        return self._tiles.revision

    @Property(bool, notify=tilesChanged)
    def tilesPending(self) -> bool:
        """Des tuiles sont encore en téléchargement (attente des captures)."""
        return self._tiles.pending

    # ---- launcher : options et stats ---------------------------------------

    def _refresh_addons_model(self) -> None:
        self._addons_model.replace(
            [
                {
                    "key": d.key,
                    "label": counter_label(d.key, self._config.language),
                    "enabled": self._config.counter_enabled(d.key),
                    "icon": addon_icon(d.key),
                    "desc": addon_desc(d.key, self._config.language),
                }
                for d in COUNTER_DEFS
            ]
        )

    def _refresh_stats_models(self) -> None:
        deck = self._selected_deck or None
        self._class_stats_model.replace(
            [
                {
                    "label": class_name(klass, self._config.language),
                    "key": klass or "",
                    "wins": wins,
                    "losses": games - wins,
                    "pct": round(100 * wins / games) if games else 0,
                    # durée moyenne d'une partie face à cette classe
                    "duration": _fmt_minutes(secondes),
                }
                for klass, games, wins, secondes in self._history.class_stats(deck_name=deck)
            ]
        )
        arch = self._history.archetype_stats(
            deck_name=deck, opponent_class=self._selected_class or None)
        total = sum(n for _, n, _, _ in arch) or 1
        self._archetype_model.replace(
            [
                {
                    "label": a or t_("unknownDeck", self._config.language),
                    "games": n,
                    "wins": v,
                    "pct": round(100 * v / n) if n else 0,
                    # part du camembert, en pourcentage du total de la classe
                    "share": round(100 * n / total, 1),
                    "duration": _fmt_minutes(d),
                    "known": bool(a),
                    # teinte STABLE : suit l'entité, pas son rang
                    "slot": archetypes.slot(self._selected_class or None, a),
                }
                for a, n, v, d in arch
            ]
        )
        self._deck_stats_model.replace(
            [
                {
                    "name": s.deck_name,
                    "wins": s.wins,
                    "games": s.games,
                    "pct": round(100 * s.winrate),
                    "duration": _fmt_minutes(s.avg_duration_s),
                }
                for s in self._history.deck_stats()
            ]
        )
        self._recent_model.replace(
            [
                {
                    "date": f"{played_on} {(ts or '')[:5]}",
                    "deck": deck_name or "?",
                    "vsClass": class_name(klass, self._config.language) or "?",
                    "vsKey": klass or "",
                    "won": result == "WON",
                    "session": session,
                    "gameIndex": game_index,
                    "duration": _fmt_duration(duration_s),
                    # « concédée » : par qui, et assez tôt pour que ce ne soit
                    # pas une vraie partie. Deux tours ou moins = personne n'a
                    # joué, on le dit plutôt que d'afficher « 0:12 ».
                    "conceded": conceded or "",
                    "quickConcede": bool(conceded) and (conceded_turn or 0) <= 2,
                }
                for played_on, ts, deck_name, _opp, result, _turns, klass,
                    session, game_index, duration_s, conceded, conceded_turn
                in self._history.recent(limit=15, deck_name=deck)
            ]
        )

    @Slot(str, bool, result="QVariantMap")
    def poolFor(self, card_id: str, of_opponent: bool) -> dict:
        """Ce qu'une carte à résurrection peut réellement ramener, au survol.

        Rendu vide pour toute carte ordinaire → le QML n'affiche alors rien.
        """
        game = self._tracker.current_game
        if game is None:
            return {"label": "", "entries": []}
        local = game.local_player_id()
        if of_opponent:
            player = next((p for p in game.player_names if p != local), None)
        else:
            player = local
        label, entries = pool_for(
            game, self._db, card_id, player, lang=self._config.language)
        return {
            "label": label,
            "entries": [
                {"name": e.name, "cost": e.cost, "count": e.count} for e in entries
            ],
        }

    # ---- saisie manuelle et gestion des decks ------------------------------

    @Slot(str, str, bool)
    def addManualGame(self, deck_name: str, opponent_class: str, won: bool) -> None:
        """Ajoute une partie à la main (journal HS coupé, partie hors suivi…)."""
        if not deck_name:
            return
        self._history.add_manual(deck_name, opponent_class, bool(won))
        self._refresh_stats_models()
        self.changed.emit()

    @Slot(str)
    def archiveDeck(self, deck_name: str) -> None:
        """Repart de zéro sur un deck : ses parties sortent des stats mais
        restent en base (deck fraîchement crafté, winrate d'apprentissage…)."""
        self._history.archive_deck(deck_name)
        if self._selected_deck == deck_name:
            self._selected_deck = ""
        self._refresh_stats_models()
        self.changed.emit()

    @Slot(str)
    def deleteDeck(self, deck_name: str) -> None:
        """Supprime DÉFINITIVEMENT les parties d'un deck (double clic en UI)."""
        self._history.delete_deck(deck_name)
        if self._selected_deck == deck_name:
            self._selected_deck = ""
        self._refresh_stats_models()
        self.changed.emit()

    @Slot(str, int)
    def deleteGame(self, session: str, game_index: int) -> None:
        """Supprime une partie précise de l'historique."""
        self._history.delete_game(session, game_index)
        self._refresh_stats_models()
        self.changed.emit()

    @Property("QStringList", notify=changed)
    def knownDecks(self):
        """Decks proposés à la saisie : ceux vus dans Decks.log + l'historique."""
        names = [d.name for d in self._player_decks]
        for s in self._history.deck_stats():
            if s.deck_name and s.deck_name != "?" and s.deck_name not in names:
                names.append(s.deck_name)
        return names

    @Property("QStringList", constant=True)
    def classNames(self):
        lang = self._config.language
        return sorted(class_name(k, lang) for k in CLASS_FR)

    @Slot(str, result=str)
    def classKey(self, label: str) -> str:
        """Libellé français → clé interne (« Voleur » → « ROGUE »)."""
        lang = self._config.language
        return next((k for k in CLASS_FR if class_name(k, lang) == label), "")

    @Property("QVariant", notify=changed)
    def deckRefModel(self):
        return self._deck_ref_model

    @Slot(str, str, result=str)
    def addDeckRef(self, name: str, texte: str) -> str:
        """Enregistre une ou PLUSIEURS listes depuis un collage.

        Le format d'export de Hearthstone porte déjà le nom (« ### Pirate
        Warrior »), et les sites de méta en donnent huit d'affilée : faire
        saisir un nom par liste serait absurde. Le champ « nom » ne sert donc
        que pour un code nu, sans en-tête.

        Rend "" si tout va bien, sinon un message à afficher.
        """
        ajoutees, err = self._refs.add_paste(texte, self._db, defaut=name)
        if ajoutees:
            self._refresh_deck_refs()
            self.changed.emit()
            return "" if not err else err
        return err or "aucune nouvelle liste dans ce collage"

    @Slot(str)
    def removeDeckRef(self, name: str) -> None:
        self._refs.remove(name)
        self._refresh_deck_refs()
        self.changed.emit()

    def _refresh_deck_refs(self) -> None:
        """Listes de référence de la CLASSE sélectionnée uniquement.

        Les montrer toutes noyait l'information : on clique « Guerrier » et on
        se retrouve avec AYAYA Rogue et Attack Druid sous les yeux. Hors
        sélection (aucune classe choisie), on montre tout — c'est là qu'on gère
        sa collection.
        """
        choisie = self._selected_class
        self._deck_ref_model.replace(
            [
                {"name": nom,
                 "klass": class_name(kl, self._config.language) if kl else "?",
                 "cards": cartes,
                 "variants": n}
                for nom, kl, n, cartes in self._refs.archetype_names()
                if not choisie or kl == choisie
            ]
        )

    @Property("QVariant", notify=changed)
    def archetypeModel(self):
        return self._archetype_model

    @Property(str, notify=changed)
    def selectedClass(self):
        return self._selected_class

    @Slot(str)
    def selectClass(self, key: str) -> None:
        """Deuxième niveau de filtre : deck → classe → archétypes.

        Re-cliquer sur la même classe la désélectionne, comme pour les decks.
        """
        self._selected_class = "" if key == self._selected_class else key
        self._refresh_stats_models()
        self._refresh_deck_refs()   # la liste suit la classe choisie
        self.changed.emit()

    @Slot(str)
    def selectDeck(self, name: str) -> None:
        """Filtre les stats du launcher sur un deck (re-clic = tout voir)."""
        self._selected_deck = "" if name == self._selected_deck else name
        self._selected_class = ""   # un archétype ne se lit que par couple deck×classe
        self._refresh_stats_models()
        self._refresh_deck_refs()
        self.changed.emit()

    @Slot(str, bool)
    def setAddonEnabled(self, key: str, enabled: bool) -> None:
        self._config.counters[key] = bool(enabled)
        self._config.save()
        self._refresh_addons_model()
        self._view = DeckView()  # force le recalcul des compteurs au prochain poll

    @Slot(str, float)
    def setScale(self, which: str, value: float) -> None:
        value = max(0.6, min(2.0, float(value)))
        if which in ("panel_scale", "opp_scale", "bar_scale"):
            setattr(self._config, which, value)
            self._config.save()
            self.changed.emit()

    @Slot(str)
    def setLanguage(self, lang: str) -> None:
        """Bascule FR/EN : libellés, noms de cartes et aperçus HearthstoneJSON."""
        self._config.language = "en" if lang == "en" else "fr"
        self._config.save()
        self._view = DeckView()  # force le recalcul des modèles au prochain poll
        self._refresh_addons_model()
        self.changed.emit()

    @Property(str, notify=changed)
    def language(self):
        return self._config.language

    @Property(str, notify=changed)
    def cardLocale(self):
        """Locale des rendus de cartes HearthstoneJSON."""
        return "enUS" if self._config.language == "en" else "frFR"

    # ---- partage volontaire de parties -------------------------------------

    @Property(bool, notify=changed)
    def consentAsked(self):
        """La question a-t-elle déjà été posée ? (elle ne l'est qu'une fois)"""
        return self._config.consent_asked

    @Property(bool, notify=changed)
    def shareGames(self):
        return self._config.share_enabled

    @Slot(bool)
    def answerConsent(self, accepte: bool) -> None:
        """Réponse au consentement initial — ne se pose qu'une fois."""
        self._config.share_games = "yes" if accepte else "no"
        self._config.save()
        self.changed.emit()

    @Slot(bool)
    def setShareGames(self, enabled: bool) -> None:
        self._config.share_games = "yes" if enabled else "no"
        self._config.save()
        if not enabled:
            sharing.vider_outbox()   # refuser doit effacer ce qui attendait
            self._staged.clear()
        self.changed.emit()


    @Property(str, notify=changed)
    def outboxSummary(self):
        n, octets = sharing.taille_outbox()
        if n == 0:
            return ""
        en = self._config.language == "en"
        mo = octets / 1048576
        if en:
            return f"{n} session{'s' if n > 1 else ''} ready · {mo:.1f} MB"
        return f"{n} session{'s' if n > 1 else ''} en attente · {mo:.1f} Mo"

    @Property("QStringList", constant=True)
    def rankLeagues(self):
        """Paliers traduits, précédés d'un « — » qui vaut « non renseigné »."""
        vide = "— non renseigné —" if self._config.language != "en" else "— not set —"
        return [vide] + [league_name(k, self._config.language) for k in LEAGUES]

    @Property(int, notify=changed)
    def rankLeagueIndex(self):
        ligue = self._config.rank_league
        return LEAGUES.index(ligue) + 1 if ligue in LEAGUES else 0

    @Property(int, notify=changed)
    def rankLevel(self):
        return self._config.rank_level

    @Property(bool, notify=changed)
    def rankHasLevel(self):
        """La Légende n'a pas de palier 10 → 1."""
        return bool(self._config.rank_league) and self._config.rank_league != "LEGEND"

    @Slot(int, int)
    def setRank(self, index_ligue: int, niveau: int) -> None:
        """index 0 = non renseigné ; le rang reste facultatif."""
        if index_ligue <= 0 or index_ligue > len(LEAGUES):
            self._config.rank_league = ""
            self._config.rank_level = 0
        else:
            self._config.rank_league = LEAGUES[index_ligue - 1]
            self._config.rank_level = max(0, min(10, int(niveau)))
        self._config.save()
        self.changed.emit()

    @Property(str, notify=changed)
    def rankLabel(self):
        """« Or 7 » — ce que l'utilisateur lit."""
        ligue = self._config.rank_league
        if not ligue:
            return ""
        nom = league_name(ligue, self._config.language)
        if ligue == "LEGEND" or not self._config.rank_level:
            return nom
        return f"{nom} {self._config.rank_level}"

    @Property(str, notify=changed)
    def installId(self):
        """Identifiant d'installation, tel qu'il est — sans le créer.

        Surtout pas ``_install_id()`` ici : QML évalue les liaisons d'un bloc
        même invisible, et cette propriété fabriquerait alors un identifiant
        pour quelqu'un qui a refusé le partage. Il n'apparaît que là où il
        existe déjà, c'est-à-dire à partir du premier envoi préparé.
        """
        return self._config.install_id

    @Slot()
    def copyInstallId(self) -> None:
        """Met l'identifiant dans le presse-papiers.

        Il sert à deux choses qu'on ne peut pas faire de tête : retrouver ses
        propres parties dans le corpus public
        (``tools/corpus.py --installation <id>``) et demander leur suppression.
        """
        from PySide6.QtGui import QGuiApplication

        identifiant = self._install_id()
        clip = QGuiApplication.clipboard()
        if clip is not None:
            clip.setText(identifiant)
        self.changed.emit()

    @Slot()
    def clearOutbox(self) -> None:
        sharing.vider_outbox()
        self._staged.clear()
        self.changed.emit()

    @Slot()
    def sendOutboxNow(self) -> None:
        """Bouton « envoyer maintenant » — force le passage.

        L'envoi est automatique, mais il attend : entre deux parties, et selon
        une attente croissante après un échec. Ce bouton sert quand on VEUT que
        ça parte tout de suite — typiquement après avoir rebranché le réseau,
        ou pour une session que Cairn a fini par abandonner.
        """
        def _forcer():
            for session in sharing.outbox_dir().glob("*/"):
                if session.is_dir():
                    envoi._noter(session, prochain_essai=0, abandonne=False)
            self._vider_outbox_si_possible()

        self._en_fond(_forcer)

    @Property(bool, notify=changed)
    def shareConfigured(self):
        """Un point de collecte est-il configuré ? Sinon rien ne peut partir,
        et le launcher doit le dire au lieu d'afficher un envoi qui n'aura
        jamais lieu."""
        return bool(envoi.endpoint())

    @Slot()
    def openOutbox(self) -> None:
        """Ouvre le dossier : l'utilisateur doit pouvoir VOIR ce qui partirait."""
        chemin = sharing.outbox_dir()
        chemin.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["xdg-open", str(chemin)])
        except OSError:
            pass

    @Slot(bool)
    def setOppPanelEnabled(self, enabled: bool) -> None:
        self._config.opp_panel = bool(enabled)
        self._config.save()
        self.changed.emit()

    # ---- archives de sessions ----------------------------------------------

    @Property(bool, notify=changed)
    def archiveEnabled(self):
        return self._config.archive_sessions

    @Slot(bool)
    def setArchiveEnabled(self, enabled: bool) -> None:
        """Coupe ou rallume l'archivage. Rallumer prend effet au lancement
        suivant : l'archiveur est branché sur le suiveur à sa construction."""
        self._config.archive_sessions = bool(enabled)
        self._config.save()
        if not enabled and self._archive is not None:
            self._archive.close()
            self._archive = None
            self._tracker.archive = None
        self.changed.emit()

    @Property(str, notify=changed)
    def archiveSummary(self):
        """« 14 sessions · 11,3 Mo » — ce qui est à l'abri, et ce que ça coûte."""
        archive = self._archive or SessionArchive(SESSIONS_DIR)
        sessions = archive.sessions()
        if not sessions:
            return ""
        mo = sum(s.size for s in sessions) / 1048576
        if self._config.language == "en":
            unite = "session" if len(sessions) == 1 else "sessions"
            return f"{len(sessions)} {unite} · {mo:.1f} MB"
        return f"{len(sessions)} session{'s' if len(sessions) > 1 else ''} · {mo:.1f} Mo"

    @Slot()
    def openArchive(self) -> None:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["xdg-open", str(SESSIONS_DIR)])
        except OSError:
            pass

    @Slot(bool)
    def setHandDotsEnabled(self, enabled: bool) -> None:
        self._config.hand_dots = bool(enabled)
        self._config.save()
        self.changed.emit()

    # ---- propriétés lues par le QML ----------------------------------------
    # (les attributs Python ordinaires sont INVISIBLES pour QML : tout ce que
    # lit le QML doit être une vraie Property)

    @Property(QObject, constant=True)
    def deckModel(self):
        return self._deck_model

    @Property(QObject, constant=True)
    def entriesModel(self):
        return self._entries_model

    @Property(QObject, constant=True)
    def deckBottomModel(self):
        return self._deck_bottom_model

    @Property(QObject, constant=True)
    def deckTopModel(self):
        return self._deck_top_model

    @Property(QObject, constant=True)
    def oppModel(self):
        return self._opp_model

    @Property(QObject, constant=True)
    def oppHandModel(self):
        return self._opp_hand_model

    @Property(QObject, constant=True)
    def oppHandSlotsModel(self):
        return self._opp_hand_slots_model

    @Property(QObject, constant=True)
    def myHandModel(self):
        return self._my_hand_model

    @Property(QObject, constant=True)
    def myEffectsModel(self):
        return self._my_effects_model

    @Property(QObject, constant=True)
    def oppEffectsModel(self):
        return self._opp_effects_model

    @Property(QObject, constant=True)
    def myReplayModel(self):
        return self._my_replay_model

    @Property(QObject, constant=True)
    def oppReplayModel(self):
        return self._opp_replay_model

    @Property(QObject, constant=True)
    def oppDeckModel(self):
        return self._opp_deck_model

    @Property(QObject, constant=True)
    def myGraveyardModel(self):
        return self._my_grave_model

    @Property(QObject, constant=True)
    def oppGraveyardModel(self):
        return self._opp_grave_model

    @Property(QObject, constant=True)
    def myAtlasModel(self):
        return self._my_atlas_model

    @Property(QObject, constant=True)
    def oppAtlasModel(self):
        return self._opp_atlas_model

    @Property(QObject, constant=True)
    def myFamilyModel(self):
        return self._my_family_model

    @Property(QObject, constant=True)
    def oppFamilyModel(self):
        return self._opp_family_model

    @Property(int, notify=changed)
    def myFamilySections(self):
        return self._family_sections[0]

    @Property(int, notify=changed)
    def oppFamilySections(self):
        return self._family_sections[1]

    @Property(QObject, constant=True)
    def secretsModel(self):
        return self._secrets_model

    @Property(int, notify=changed)
    def oppSecretCount(self):
        return getattr(self, "_opp_secrets", 0)

    @Property(str, notify=changed)
    def oppSecretClasses(self):
        """« Mage » — la classe du secret posé, quand le jeu l'a publiée.

        Vide tant qu'elle est inconnue : les candidats sont alors ceux de la
        classe adverse, et l'afficher serait un mensonge.
        """
        return " · ".join(getattr(self, "_opp_secret_classes", []))

    @Slot(str)
    def toggleSecretRuledOut(self, card_id: str):
        """Barre/rétablit un candidat : la déduction manuelle du joueur."""
        self._ruled_out ^= {card_id}
        self._view = DeckView()   # force le recalcul des modèles au prochain poll
        self.changed.emit()

    @Slot(str, result="QVariantMap")
    def cardInfo(self, card_id: str) -> dict:
        """Nom, coût et TEXTE DE RÈGLES d'une carte, pour l'aperçu au survol.

        Indispensable aux « effets en jeu » : un enchantement n'a aucun rendu
        de carte à afficher (l'URL officielle rend une image vide), seulement un
        nom. Sans son texte, « Âme brisée » ne dit pas ce qu'elle fait.
        """
        card = self._db.by_card_id.get(card_id or "")
        if card is None:
            return {"name": "", "text": "", "cost": -1, "type": "", "rarity": ""}
        lang = self._config.language
        return {
            "name": self._db.localized_name(card_id, lang),
            "text": self._db.text(card_id, lang),
            "cost": card.get("cost", -1) if card.get("cost") is not None else -1,
            "type": card.get("type", ""),
            "rarity": card.get("rarity", ""),
        }

    @Slot(str, result=str)
    def drawChance(self, card_id: str) -> str:
        """Probabilité de piocher cette carte à la prochaine pioche.

        Somme de TOUTES les lignes de cette carte : depuis que les cartes
        ajoutées en cours de partie ont leur propre ligne (l'icône cadeau), un
        même nom peut en occuper deux — s'arrêter à la première annoncerait
        « 1/25 » là où le deck en contient deux.
        """
        restant = sum(
            r.remaining for r in self._view.rows if r.card_id == card_id
        )
        total = self._view.remaining_total
        if restant <= 0 or total <= 0:
            return ""
        pct = round(100 * restant / total)
        return f"{restant}/{total} · {pct} %"

    @Property(QObject, constant=True)
    def countersModel(self):
        return self._counters_model

    @Property(str, notify=changed)
    def attackMine(self):
        return self._attack["good"]

    @Property(str, notify=changed)
    def attackOpp(self):
        return self._attack["bad"]

    # ---- position des widgets flottants ------------------------------------

    @Slot(str, bool, result=bool)
    def sectionCollapsed(self, name: str, default: bool) -> bool:
        """État replié d'une section du launcher, retenu entre deux lancements."""
        return self._config.section_collapsed(name, default)

    @Slot(str, bool)
    def setSectionCollapsed(self, name: str, collapsed: bool) -> None:
        if self._config.section_collapsed(name) == collapsed:
            return
        self._config.set_section_collapsed(name, collapsed)
        self._config.save()

    @Property(str, notify=changed)
    def addonsBadge(self) -> str:
        """« 15/17 » — actifs sur total. Une propriété plutôt qu'un appel à
        ``rowCount()`` depuis QML : cette méthode n'est pas invocable et la
        liaison partait en boucle d'erreurs."""
        actifs = sum(1 for d in COUNTER_DEFS if self._config.counter_enabled(d.key))
        return f"{actifs}/{len(COUNTER_DEFS)}"

    @Slot(str, int, int)
    def rememberPos(self, widget: str, x: int, y: int) -> None:
        """Retient où l'utilisateur a posé un widget.

        Appelé au relâché du glisser, pas en continu : écrire le fichier à
        chaque pixel parcouru rendrait le déplacement saccadé.
        """
        if self._config.pos_of(widget) == (max(0, x), max(0, y)):
            return
        self._config.set_pos(widget, x, y)
        self._config.save()

    @Slot(str, result="QVariantMap")
    def savedPos(self, widget: str) -> dict:
        """Position retenue, ou ``{}`` si le widget n'a jamais été déplacé.

        Sous Wayland le QML ne peut pas s'en servir pour se placer (seul KWin
        décide, cf. règles ``cairn-pos-*``) ; sous X11 et sous les compositeurs
        qui l'autorisent, si.
        """
        pos = self._config.pos_of(widget)
        return {"x": pos[0], "y": pos[1]} if pos else {}

    @Slot()
    def resetPositions(self) -> None:
        """Remet tous les widgets à leur place d'origine.

        Filet de sécurité pour le widget poussé hors écran (résolution changée,
        écran débranché) : il devient irrattrapable à la souris.

        Deux mémoires à effacer, pas une : la nôtre, et celle de KWin. Sous
        Wayland c'est KWin qui retient les positions (règles ``cairn-pos-*`` en
        mode Remember) — vider seulement ``config.json`` ne déplacerait rien, et
        le bouton mentirait.
        """
        self._config.widget_pos = {}
        self._config.save()
        self._reset_kwin_positions()
        self.changed.emit()

    @staticmethod
    def _reset_kwin_positions() -> None:
        if "KDE" not in os.environ.get("XDG_CURRENT_DESKTOP", ""):
            return
        # Trois cas, du plus spécifique au plus général : le dépôt (mode
        # source), la copie posée par install.sh, et enfin les emplacements
        # système — un paquet de distribution (AUR, .deb…) pose le script sous
        # ``share/cairn`` et ne garde ni l'arborescence du dépôt ni le dossier
        # de données de l'utilisateur.
        for script in (
            Path(__file__).resolve().parents[3] / "tools" / "install_kwin_rule.sh",
            DATA_DIR / "install_kwin_rule.sh",
            Path(sys.prefix) / "share" / "cairn" / "install_kwin_rule.sh",
            Path("/usr/share/cairn/install_kwin_rule.sh"),
        ):
            if script.is_file():
                break
        else:
            return
        try:
            subprocess.run(
                ["bash", str(script), "--reset-pos"],
                check=False, capture_output=True, timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            pass  # hors KDE ou script absent : la config locale suffit

    @Property(QObject, constant=True)
    def addonsModel(self):
        return self._addons_model

    @Property(QObject, constant=True)
    def classStatsModel(self):
        return self._class_stats_model

    @Property(QObject, constant=True)
    def deckStatsModel(self):
        return self._deck_stats_model

    @Property(QObject, constant=True)
    def recentModel(self):
        return self._recent_model

    @Property(float, notify=changed)
    def panelScale(self):
        return self._config.panel_scale

    @Property(float, notify=changed)
    def oppScale(self):
        return self._config.opp_scale

    @Property(float, notify=changed)
    def barScale(self):
        return self._config.bar_scale

    @Property(bool, notify=changed)
    def oppPanelEnabled(self):
        return self._config.opp_panel

    @Property(bool, notify=changed)
    def handDotsEnabled(self):
        return self._config.hand_dots

    @Property(str, notify=changed)
    def deckName(self):
        if self._view.deck_name:
            return self._view.deck_name
        en = self._config.language == "en"
        if self.hasGame:
            # Partie en cours dont le deck est indéterminable (partie amicale) :
            # le dire, plutôt que laisser croire à une attente de partie.
            return "Unknown deck" if en else "Deck inconnu"
        return "Waiting for a game…" if en else "En attente de partie…"

    @Property(str, notify=changed)
    def opponentName(self):
        return self._view.opponent_name

    @Property(int, notify=changed)
    def remainingTotal(self):
        return self._view.remaining_total

    @Property(str, notify=changed)
    def result(self):
        return self._view.result

    @Property(bool, notify=changed)
    def hasGame(self):
        return bool(self._view.rows or self._view.opponent_name)

    @Property(bool, notify=changed)
    def hsRunning(self):
        return self._hs_running

    @Property(str, notify=changed)
    def gameDuration(self):
        """Chrono de la partie en cours, rafraîchi à chaque poll."""
        game = self._tracker.current_game
        if game is None:
            return ""
        return _fmt_duration(game.duration_seconds())

    @Property(int, notify=changed)
    def turnCount(self):
        """Manche courante, pas le tag TURN brut (cf. game_state.round_number)."""
        game = self._tracker.current_game
        return round_number(game.turns) if game is not None else 0

    @Property(str, notify=changed)
    def turnDuration(self):
        """Temps passé dans le tour en cours — la corde, en clair."""
        game = self._tracker.current_game
        return _fmt_duration(game.turn_seconds()) if game is not None else ""

    @Property(bool, notify=changed)
    def myTurn(self):
        game = self._tracker.current_game
        if game is None:
            return False
        return game.current_player is not None \
            and game.current_player == game.local_player_id()

    # Une partie perdue par déconnexion ne reçoit JAMAIS son STATE=COMPLETE :
    # le journal s'arrête net, au milieu d'un tour. Sans ce garde-fou les
    # panneaux restaient affichés par-dessus le menu principal, pour une partie
    # finie depuis longtemps — constaté après une coupure de connexion.
    #
    # Le silence du journal est le seul signal disponible. Il est fiable :
    # Hearthstone y écrit en continu pendant une partie, ne serait-ce que les
    # options proposées à chaque instant ; trois minutes sans une ligne ne
    # peuvent pas arriver dans une partie vivante, la corde force à jouer.
    #
    # Rien n'est marqué comme terminé pour autant : la partie reste incomplète
    # dans le moteur, donc elle n'entrera pas dans l'historique sans résultat.
    SILENCE_ABANDON_S = 180

    def _partie_abandonnee(self, game) -> bool:
        if self._assume_running:
            return False   # rejeu d'archive : les horodatages sont d'un autre jour
        dernier = game.last_ts or game.ts
        if not dernier:
            return False
        try:
            h, m, s = (int(x) for x in dernier[:8].split(":"))
        except ValueError:
            return False
        maintenant = datetime.now()
        ecart = maintenant.hour * 3600 + maintenant.minute * 60 + maintenant.second \
            - (h * 3600 + m * 60 + s)
        if ecart < 0:
            ecart += 86400   # le journal a franchi minuit
        return ecart > self.SILENCE_ABANDON_S

    @Property(str, notify=changed)
    def myThinkTime(self):
        """Temps de réflexion cumulé du joueur local sur la partie."""
        game = self._tracker.current_game
        if game is None:
            return ""
        return _fmt_duration(game.player_seconds(game.local_player_id()))

    @Property(str, notify=changed)
    def oppThinkTime(self):
        game = self._tracker.current_game
        if game is None:
            return ""
        local = game.local_player_id()
        opp = next((p for p in game.player_names if p != local), None)
        return _fmt_duration(game.player_seconds(opp)) if opp is not None else ""

    @Property(bool, notify=changed)
    def inGame(self):
        """Vrai pendant une partie seulement — les overlays se cachent dans
        les menus et dès l'écran de fin (demande utilisateur du 01/08).
        Log saturé = suivi aveugle : on cache aussi (la fin de partie ne
        sera jamais vue)."""
        if self._tracker.log_full:
            return False
        game = self._tracker.current_game
        if game is None or game.is_spectated(self._config.own_account):
            return False  # on regarde la partie d'un contact : pas la nôtre
        if game.is_deckless_mode():
            return False  # Champ de bataille, Mercenaires : rien à suivre
        if self._partie_abandonnee(game):
            return False
        return not game.complete

    @Property(bool, notify=changed)
    def logFull(self):
        return self._tracker.log_full

    @Property(str, notify=changed)
    def logStatus(self):
        """État du journal HS : sa taille, et le nombre de fois qu'Cairn l'a
        vidé pour l'empêcher d'atteindre la limite fatale des 10 Mo."""
        session = self._tracker.session
        if session is None:
            return ""
        try:
            mo = (session / "Power.log").stat().st_size / 1048576
        except OSError:
            return ""
        active = self._tracker._tailer.path if self._tracker._tailer else None
        if active is not None and active.name != "Power.log":
            try:
                mo = active.stat().st_size / 1048576
            except OSError:
                pass
        txt = f"journal HS {mo:.1f} Mo"
        if self._tracker.renames:
            txt += f" · nom libéré ×{self._tracker.renames}"
        else:
            txt += " / 10"
        if not self._config.log_rotation:
            return txt
        if self._tracker.rotation_broken:
            return txt + " · rotation inopérante (Wine)"
        if self._tracker.rotations:
            txt += f" · {self._tracker.rotations} rotation"
            if self._tracker.rotations > 1:
                txt += "s"
        return txt

    @Property(str, notify=changed)
    def selectedDeck(self):
        return self._selected_deck

    @Property(str, notify=changed)
    def overallSummary(self):
        games, wins = self._history.overall()
        if games == 0:
            return ""
        pct = round(100 * wins / games)
        if self._config.language == "en":
            unit = "game" if games == 1 else "games"
            return f"{games} {unit} · {wins}W – {games - wins}L · {pct} %"
        unit = "partie" if games == 1 else "parties"
        return f"{games} {unit} · {wins} V – {games - wins} D · {pct} %"

    @Property(str, notify=changed)
    def opponentClass(self):
        return class_name(self._opp_class, self._config.language)

    @Property(bool, notify=changed)
    def hasDeckcode(self):
        return bool(self._deckstring)

    @Slot()
    def copyDeckcode(self) -> None:
        """Met le deckcode du deck joué dans le presse-papiers.

        Il est en clair dans ``Decks.log`` à chaque mise en file : autant le
        rendre au joueur, qui n'a sinon aucun moyen de récupérer la liste
        exacte qu'il vient de jouer sans repasser par le client.
        """
        if not self._deckstring:
            return
        from PySide6.QtGui import QGuiApplication

        clip = QGuiApplication.clipboard()
        if clip is not None:
            clip.setText(self._deckstring)

    @Property(str, notify=changed)
    def deckRecord(self):
        """« 42-15 · 74 % » — le bilan du deck joué, dans l'en-tête du panneau.

        Les chiffres existaient déjà, mais seulement dans le launcher : en
        partie on ne voyait que le bilan face à la classe adverse. Firestone
        affiche les deux côte à côte, et c'est le bon réflexe — le premier dit
        si le deck marche, le second si le matchup est jouable.
        """
        nom = self._view.deck_name
        if not nom:
            return ""
        stats = next((d for d in self._history.deck_stats() if d.deck_name == nom), None)
        if stats is None or stats.games == 0:
            return ""
        return f"{stats.wins}-{stats.games - stats.wins} · {round(100 * stats.winrate)} %"

    @Property(str, notify=changed)
    def vsClassRecord(self):
        """« 0-1 contre Voleur » — le bilan historique contre cette classe."""
        if not self._opp_class:
            return ""
        wins, losses = self._history.vs_class(self._opp_class)
        if wins == losses == 0:
            return ""
        klass = class_name(self._opp_class, self._config.language)
        joiner = "vs" if self._config.language == "en" else "contre"
        return f"{wins}-{losses} {joiner} {klass}"
