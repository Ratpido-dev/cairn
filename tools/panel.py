#!/usr/bin/env python3
"""Panneau deck de Cairn (phase 2).

Usage :
    python tools/panel.py                      # suivi live de Hearthstone
    python tools/panel.py --replay [vitesse]   # rejoue la dernière fixture
                                               # (vitesse ×N, défaut 40)

Fenêtre sans bordure, au-dessus des autres, déplaçable à la souris.
Si KWin ne la garde pas au-dessus du jeu : Règles de fenêtres KDE →
« Cairn » → Garder au-dessus. Jouer HS en fenêtré sans bordure.
"""

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

from src.cairn.app import FLOATING  # noqa: E402
from src.cairn.paths import FIXTURES_DIR, preparer_fixtures  # noqa: E402
from src.cairn.ui.bridge import TrackerBridge  # noqa: E402

QML_DIR = ROOT / "src" / "cairn" / "ui" / "qml"
QML = QML_DIR / "DeckPanel.qml"
QML_OPP = QML_DIR / "OppPanel.qml"
QML_HOME = QML_DIR / "Launcher.qml"


class FixtureReplayer:
    """Copie une fixture par blocs dans un faux dossier Logs — même chemin de
    code que le live, mais accéléré : idéal pour voir l'UI sans jouer."""

    def __init__(self, speed: float = 40.0, chunk: int = 24 * 1024,
                 fixture: str | None = None):
        preparer_fixtures()
        fixtures = sorted(FIXTURES_DIR.glob("*/Power.log"))
        if not fixtures:
            sys.exit("Aucune fixture — joue une partie puis tools/archive_fixtures.py")
        if fixture:  # captures de QA : viser une partie précise
            fixtures = [f for f in fixtures if fixture in f.parent.name] or fixtures
        src_dir = fixtures[-1].parent
        self._tmp = Path(tempfile.mkdtemp(prefix="cairn-replay-"))
        self.session = self._tmp / src_dir.name
        self.session.mkdir()
        shutil.copy2(src_dir / "Decks.log", self.session / "Decks.log")
        self._content = (src_dir / "Power.log").read_bytes()
        self._pos = 0
        self._chunk = chunk
        self._out = open(self.session / "Power.log", "ab")
        self.interval_ms = max(10, int(500 / speed))

    @property
    def logs_root(self) -> Path:
        return self._tmp

    @property
    def history_path(self) -> Path:
        """Historique jetable : un replay ne doit PAS polluer le vrai."""
        return self._tmp / "history.sqlite"

    def step(self) -> None:
        if self._pos >= len(self._content):
            return
        self._out.write(self._content[self._pos:self._pos + self._chunk])
        self._out.flush()
        self._pos += self._chunk

    def cleanup(self) -> None:
        self._out.close()
        shutil.rmtree(self._tmp, ignore_errors=True)


def main() -> None:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Cairn")
    app.setOrganizationName("cairn")
    # app_id Wayland stable → la règle KWin « garder au-dessus » peut cibler
    # « cairn » au lieu de « python3 » (qui matcherait tout script Python)
    app.setDesktopFileName("cairn")

    replayer = None
    if "--replay" in sys.argv:
        idx = sys.argv.index("--replay")
        speed = float(sys.argv[idx + 1]) if len(sys.argv) > idx + 1 else 40.0
        replayer = FixtureReplayer(speed=speed)
        bridge = TrackerBridge(
            logs_root=replayer.logs_root,
            poll_ms=100,
            history_path=replayer.history_path,
            assume_running=True,  # pas de process HS en mode replay
        )
        feeder = QTimer()
        feeder.setInterval(replayer.interval_ms)
        feeder.timeout.connect(replayer.step)
        feeder.start()
        app.aboutToQuit.connect(replayer.cleanup)
    else:
        bridge = TrackerBridge()

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("tracker", bridge)
    engine.load(QUrl.fromLocalFile(str(QML)))
    engine.load(QUrl.fromLocalFile(str(QML_OPP)))
    engine.load(QUrl.fromLocalFile(str(QML_HOME)))
    # widgets flottants indépendants : chacun sa fenêtre, donc sa position
    for name in FLOATING:
        engine.load(QUrl.fromLocalFile(str(QML_DIR / name)))
    if not engine.rootObjects():
        sys.exit("Échec de chargement du QML")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
