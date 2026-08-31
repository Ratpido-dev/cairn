#!/usr/bin/env python3
"""Archive les sessions de logs HS contenant un Power.log dans data/fixtures/.

Usage : python tools/archive_fixtures.py
À lancer après avoir joué : chaque session avec un Power.log est copiée
(Power.log + Decks.log + LoadingScreen.log) et servira de fixture aux tests
du parser (phase 1). Idempotent : une session déjà archivée est ignorée.
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cairn.paths import FIXTURES_DIR, HS_LOGS_ROOT  # noqa: E402

KEEP = ("Power.log", "Decks.log", "LoadingScreen.log")


def main() -> None:
    if HS_LOGS_ROOT is None or not HS_LOGS_ROOT.is_dir():
        sys.exit("Hearthstone introuvable — lance « python tools/doctor.py »")

    archived = skipped = empty = 0
    for session in sorted(HS_LOGS_ROOT.iterdir()):
        power = session / "Power.log"
        # Sans log.config, HS crée quand même un Power.log qui ne contient que
        # des lignes d'erreur internes. Une fixture utile contient au moins un
        # début de partie (CREATE_GAME) — c'est ça qu'on archive.
        if not session.is_dir() or not power.is_file():
            empty += 1
            continue
        head = power.read_text(encoding="utf-8", errors="replace")
        if "CREATE_GAME" not in head:
            empty += 1
            continue
        dest = FIXTURES_DIR / session.name
        if dest.exists():
            skipped += 1
            continue
        dest.mkdir(parents=True)
        for name in KEEP:
            src = session / name
            if src.is_file():
                shutil.copy2(src, dest / name)
        size = (dest / "Power.log").stat().st_size
        print(f"archivé : {session.name} (Power.log {size/1024:.0f} Ko)")
        archived += 1

    print(f"\n{archived} archivée(s), {skipped} déjà là, {empty} sans Power.log")
    if archived == skipped == 0:
        print("→ joue une partie (le log.config est en place), puis relance-moi.")


if __name__ == "__main__":
    main()
