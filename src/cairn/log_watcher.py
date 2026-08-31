"""Suivi live de Power.log : le moteur d'état alimenté pendant la partie.

Trois étages :

- :class:`LogTailer` — lit un fichier qui grossit, par lectures incrémentales.
  Gère : fichier pas encore créé, dernière ligne incomplète (gardée en tampon
  jusqu'au ``\\n``), troncature et remplacement (inode).
- :class:`LiveTracker` — surveille le dossier ``Logs/`` de HS, bascule sur la
  session la plus récente quand HS (re)démarre, et pousse les nouvelles lignes
  dans ``IncrementalParser`` → ``GameStateEngine``.
- ``poll()`` — à appeler périodiquement (boucle CLI, ou QTimer en phase 2) :
  rend les événements de haut niveau (Draw/Play/DeckEntry…) apparus depuis le
  poll précédent.

Le choix du polling (0,5 s par défaut) plutôt qu'inotify est délibéré : coût
nul en pratique (un ``stat()``), zéro dépendance, et Wine rend les événements
inotify moins fiables qu'un stat sur certains montages.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .game_state import Game, GameStateEngine
from .paths import resolve_logs_root
from .power_log import IncrementalParser


class LogTailer:
    """Lecture incrémentale d'un fichier de log qui grossit."""

    def __init__(self, path: Path, from_start: bool = True):
        self.path = Path(path)  # peut être redirigé après un renommage
        self._pos = 0
        self._buf = ""
        self._inode: int | None = None
        self._from_start = from_start

    def poll(self) -> list[str]:
        """Nouvelles lignes complètes depuis le dernier appel."""
        try:
            st = os.stat(self.path)
        except FileNotFoundError:
            return []

        if self._inode is None:
            self._inode = st.st_ino
            if not self._from_start:
                self._pos = st.st_size
        elif st.st_ino != self._inode or st.st_size < self._pos:
            # fichier remplacé ou tronqué : on repart du début
            self._inode = st.st_ino
            self._pos = 0
            self._buf = ""

        if st.st_size == self._pos:
            return []

        with open(self.path, encoding="utf-8", errors="replace") as f:
            f.seek(self._pos)
            chunk = f.read()
            self._pos = f.tell()

        self._buf += chunk
        *lines, self._buf = self._buf.split("\n")
        return [line.rstrip("\r") for line in lines]


@dataclass
class LiveUpdate:
    """Résultat d'un ``poll()`` : ce qui vient de se passer."""

    session_switched: Path | None = None  # nouveau dossier de session, le cas échéant
    new_games: list[Game] = field(default_factory=list)  # parties qui ont démarré
    events: list = field(default_factory=list)  # Draw / Play / DeckEntry / …

    @property
    def empty(self) -> bool:
        return not (self.session_switched or self.new_games or self.events)


class LiveTracker:
    """Boucle live complète : Logs/ → session courante → moteur d'état."""

    def __init__(
        self,
        logs_root: Path | str | None = None,
        from_start: bool = True,
        mirror_dir: Path | None = None,
        prefix_override: str | None = None,
        archive=None,
    ):
        # None = on résout à la construction : le prefix peut avoir été changé
        # dans la configuration depuis l'import du module
        if logs_root is None:
            logs_root = resolve_logs_root(prefix_override)
        self.logs_root = Path(logs_root) if logs_root is not None else None
        self.mirror_dir = mirror_dir
        # Archiveur de sessions (cf. archive.SessionArchive), ou None. Branché
        # ici plutôt que dans le pont Qt : c'est le suiveur qui voit passer les
        # lignes, et tout ce qui les lit — CLI, outils — en profite.
        self.archive = archive
        self.engine = GameStateEngine()
        self._parser = IncrementalParser()
        self._tailer: LogTailer | None = None
        self._session: Path | None = None
        self._from_start = from_start
        self._seen_games = 0
        self._seen_events: dict[int, int] = {}  # index de partie → nb d'events déjà vus
        # HS plafonne Power.log à 10 Mo par session : au-delà il écrit
        # « Truncating log… » puis FERME le descripteur (vérifié dans /proc) —
        # sous Wine sa propre troncature échoue et le logger meurt pour de bon.
        # On le devance donc en vidant le fichier nous-mêmes (cf. maybe_rotate).
        self.log_full = False
        self.rotations = 0
        self.renames = 0          # noms libérés (cf. free_log_name)
        # Rotation DÉSACTIVÉE par défaut : mesuré le 02/08/2026, Hearthstone
        # n'ouvre pas son journal en mode ajout. Après troncature il continue
        # d'écrire à son ancien décalage, ce qui recrée un fichier À TROUS de
        # la même taille (6,7 Mo apparents pour 20 Ko alloués) — sa limite
        # reste donc atteinte, et on ne gagne que des archives de zéros.
        self.rotation_broken = True
        self._rotate_probe: int | None = None

    # ---- session courante --------------------------------------------------

    def _latest_session(self) -> Path | None:
        if self.logs_root is None or not self.logs_root.is_dir():
            return None
        sessions = sorted(
            d for d in self.logs_root.iterdir()
            if d.is_dir() and d.name.startswith("Hearthstone_")
        )
        return sessions[-1] if sessions else None

    # ---- boucle ------------------------------------------------------------

    def poll(self) -> LiveUpdate:
        update = LiveUpdate()

        latest = self._latest_session()
        if latest is not None and latest != self._session:
            self._session = latest
            self._tailer = LogTailer(latest / "Power.log", from_start=self._from_start)
            self._parser.reset()
            self.log_full = False  # nouvelle session = nouveau fichier
            if self.archive is not None:
                # le tailer relit-il tout ? l'archiveur en dépend pour ne pas
                # écrire deux fois les parties déjà en boîte
                self.archive.start(latest, from_start=self._from_start)
            update.session_switched = latest

        if self._tailer is None:
            return update

        self._check_rotation_effective()
        self._follow_reopened_log()

        lines = self._tailer.poll()
        if lines:
            if self.archive is not None:
                self.archive.feed(lines)
            if any(line.startswith("Truncating log") for line in lines):
                self.log_full = True
            events = [ev for line in lines for ev in self._parser.feed(line)]
            self.engine.feed(events)

        # diff des parties et de leurs événements de haut niveau
        games = self.engine.games
        if len(games) > self._seen_games:
            update.new_games = games[self._seen_games:]
            self._seen_games = len(games)
            # une partie commence = la précédente est finie : on la met à l'abri
            # tout de suite plutôt que d'attendre le mégaoctet suivant
            if self.archive is not None:
                self.archive.flush()
        for idx, game in enumerate(games):
            seen = self._seen_events.get(idx, 0)
            if len(game.events) > seen:
                update.events.extend(game.events[seen:])
                self._seen_events[idx] = len(game.events)

        return update

    # ---- rotation du journal ----------------------------------------------

    # ---- libération du nom (parade à la limite des 10 Mo) ------------------

    ACTIVE_GLOB = "Power.log.cairn*"

    def free_log_name(self, threshold: int = 5 * 1024 * 1024) -> bool:
        """Renomme ``Power.log`` pour libérer le NOM, sans toucher au fichier.

        Un renommage ne perturbe **ni le contenu ni la position d'écriture** du
        jeu (même inode) : contrairement à la troncature, aucune perte et aucun
        fichier à trous. Le chemin ``Power.log`` redevient un fichier neuf et
        vide — ce qui remet à zéro toute vérification de taille faite *par
        chemin*, et c'est ce qui peut éviter que HS coupe son logger à 10 Mo.

        On continue de lire le fichier renommé, à la même position.
        """
        if self._session is None or self._tailer is None:
            return False
        src = self._session / "Power.log"
        try:
            if src.stat().st_size < threshold:
                return False
        except OSError:
            return False
        if self._tailer.path != src:
            return False  # déjà renommé : le nom est libre, rien à faire

        n = 1
        while (dst := self._session / f"Power.log.cairn{n}").exists():
            n += 1
        try:
            os.rename(src, dst)
            src.touch()
        except OSError:
            return False

        # même inode, même position : la lecture se poursuit sans rien relire
        self._tailer.path = dst
        self.renames += 1
        return True

    def _follow_reopened_log(self) -> None:
        """Si HS a rouvert ``Power.log`` (sa propre rotation, ou une écriture
        par chemin), le fichier neuf se met à grossir : on le suit."""
        if self._session is None or self._tailer is None:
            return
        fresh = self._session / "Power.log"
        if self._tailer.path == fresh:
            return
        try:
            if fresh.stat().st_size > 0:
                self._tailer = LogTailer(fresh, from_start=True)
        except OSError:
            pass

    @staticmethod
    def _is_sparse(path: Path) -> bool:
        """Fichier à trous : bien moins de blocs alloués que sa taille annoncée.
        Signature d'une écriture au-delà de la fin après troncature."""
        try:
            st = os.stat(path)
        except OSError:
            return False
        return st.st_size > 1_000_000 and st.st_blocks * 512 < st.st_size // 2

    def maybe_rotate(self, threshold: int = 6 * 1024 * 1024) -> bool:
        """Vide ``Power.log`` avant que HS n'atteigne SA limite (10 Mo) et ne
        coupe définitivement son logger.

        Appelée seulement **hors partie** : entre deux parties HS n'écrit quasi
        rien, la fenêtre pendant laquelle une ligne pourrait se perdre entre
        notre lecture et la troncature est donc sans conséquence.

        Le contenu lu est d'abord recopié dans ``mirror_dir`` : on garde un
        journal complet (fixtures, débogage) sans laisser grossir celui de HS.

        Rend True si une rotation a eu lieu.
        """
        if self.rotation_broken or self._tailer is None or self._session is None:
            return False
        path = self._session / "Power.log"
        try:
            size = os.stat(path).st_size
        except FileNotFoundError:
            return False
        if size < threshold:
            return False
        # tout ce qui précède doit avoir été lu, sinon on perdrait des lignes
        if self._tailer._pos < size:
            return False
        if self._is_sparse(path):  # HS réécrit à son ancien décalage : inutile
            self.rotation_broken = True
            return False

        if self.mirror_dir is not None:
            try:
                self.mirror_dir.mkdir(parents=True, exist_ok=True)
                mirror = self.mirror_dir / f"{self._session.name}.Power.log"
                with open(path, "rb") as src, open(mirror, "ab") as dst:
                    dst.write(src.read())
            except OSError:
                pass  # l'archivage est un confort, jamais un blocage

        try:
            os.truncate(path, 0)
        except OSError:
            self.rotation_broken = True
            return False

        self._tailer._pos = 0
        self._tailer._buf = ""
        self.rotations += 1
        self._rotate_probe = size  # vérifié au poll suivant
        return True

    def _check_rotation_effective(self) -> None:
        """Si le fichier retrouve instantanément sa taille d'avant, c'est que
        HS n'écrit pas en mode ajout (fichier à trous) : la rotation est
        contre-productive, on l'abandonne."""
        if self._rotate_probe is None or self._session is None:
            return
        probe, self._rotate_probe = self._rotate_probe, None
        path = self._session / "Power.log"
        try:
            # taille retrouvée d'un coup, ou fichier devenu à trous : dans les
            # deux cas HS n'a pas repris à zéro et la rotation ne sert à rien
            if os.stat(path).st_size >= probe or self._is_sparse(path):
                self.rotation_broken = True
        except OSError:
            pass

    @property
    def current_game(self) -> Game | None:
        return self.engine.games[-1] if self.engine.games else None

    @property
    def session(self) -> Path | None:
        """Dossier de session HS actuellement suivi."""
        return self._session
