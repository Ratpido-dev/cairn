#!/usr/bin/env python3
"""Diagnostic d'installation — raccourci vers `cairn.doctor` (alias `cairn-doctor`)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.cairn.doctor import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
