"""Chargement asynchrone des tuiles d'art, côté Qt.

Le QML ne peut pas attendre : il demande une URL, on rend tout de suite celle
du fichier s'il est déjà là, sinon la chaîne vide et on télécharge en fond.
Quand des tuiles arrivent, ``revision`` change — les liaisons QML qui la
référencent se réévaluent et la ligne s'illustre d'un coup.
"""

from __future__ import annotations

import queue
import threading

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot

from .. import tiles

WORKERS = 4
# Une seule secousse de liaisons pour toutes les tuiles arrivées coup sur coup :
# au premier affichage d'un deck il en tombe une trentaine en quelques secondes.
COALESCE_MS = 200


class TileCache(QObject):
    """Cache disque + file de téléchargement, exposé au QML."""

    revisionChanged = Signal()
    _arrived = Signal()  # depuis un worker → réveille le fil principal

    def __init__(self, parent=None):
        super().__init__(parent)
        self._revision = 0
        self._queue: queue.Queue[str] = queue.Queue()
        self._pending: set[str] = set()
        self._failed: set[str] = set()
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()

        self._bump = QTimer(self)
        self._bump.setSingleShot(True)
        self._bump.setInterval(COALESCE_MS)
        self._bump.timeout.connect(self._emit_revision)
        # connexion en file d'attente implicite : le signal part d'un worker,
        # le slot démarre le timer sur le fil de l'UI (QTimer n'est pas partagé)
        self._arrived.connect(self._bump.start)

    # ---- API QML -----------------------------------------------------------

    @Property(int, notify=revisionChanged)
    def revision(self) -> int:
        return self._revision

    @Property(bool, notify=revisionChanged)
    def pending(self) -> bool:
        """Reste-t-il des tuiles en vol ? (attente des captures de QA)"""
        with self._lock:
            return bool(self._pending)

    @Slot(str, result=str)
    def url(self, card_id: str) -> str:
        """URL locale de la tuile, ou "" — et dans ce cas, on va la chercher."""
        path = tiles.cached(card_id)
        if path is not None:
            return QUrl.fromLocalFile(str(path)).toString()
        self.fetch(card_id)
        return ""

    @Slot(list)
    def prefetch(self, card_ids: list[str]) -> None:
        """Met en file tout un deck d'un coup (appelé au début de partie)."""
        for card_id in card_ids:
            self.fetch(card_id)

    def fetch(self, card_id: str) -> None:
        if not tiles.valid(card_id):
            return
        with self._lock:
            if card_id in self._pending or card_id in self._failed:
                return
            self._pending.add(card_id)
        self._ensure_workers()
        self._queue.put(card_id)

    def stop(self) -> None:
        """Arrête les workers — à appeler avant de détruire le pont."""
        self._stop.set()
        for _ in self._threads:
            self._queue.put("")  # réveille un worker bloqué sur get()

    # ---- interne -----------------------------------------------------------

    def _ensure_workers(self) -> None:
        """Démarre les fils au premier besoin : une session sans partie ne paie
        rien, et les tests qui n'affichent pas de carte restent mono-fil."""
        if self._threads or self._stop.is_set():
            return
        for i in range(WORKERS):
            thread = threading.Thread(
                target=self._work, name=f"cairn-tiles-{i}", daemon=True
            )
            thread.start()
            self._threads.append(thread)

    def _work(self) -> None:
        while not self._stop.is_set():
            card_id = self._queue.get()
            if not card_id or self._stop.is_set():
                continue
            path = tiles.download(card_id)
            with self._lock:
                self._pending.discard(card_id)
                if path is None:
                    self._failed.add(card_id)
            if path is None:
                continue
            try:
                self._arrived.emit()
            except RuntimeError:
                # le pont a été détruit pendant le téléchargement (fin de
                # process, test qui se termine) : plus personne à prévenir
                self._stop.set()
                return

    def _emit_revision(self) -> None:
        self._revision += 1
        self.revisionChanged.emit()
