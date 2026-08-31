"""Config pytest : rend ``src`` importable et prépare les parties de référence."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Les fixtures sont versionnées compressées (cf. paths.preparer_fixtures) : sans
# cet appel, la moitié des tests se sauteraient sur un dépôt fraîchement cloné,
# et la CI serait verte en n'ayant presque rien vérifié.
from src.cairn.paths import preparer_fixtures  # noqa: E402

preparer_fixtures()
