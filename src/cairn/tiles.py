"""Cache disque des tuiles d'art de carte (le bandeau 256×36 de HearthstoneJSON).

C'est ce qui donne aux lignes du panneau leur allure de tracker Hearthstone
plutôt que de tableur : chaque ligne porte l'illustration de sa carte, fondue
vers la gauche pour que le nom reste lisible.

Le module est volontairement sans Qt (testable, réutilisable en ligne de
commande) ; la partie asynchrone vit dans ``ui/tile_cache.py``.
"""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://art.hearthstonejson.com/v1/tiles/{card_id}.png"

# Les identifiants HS sont du [A-Z0-9_] — on refuse le reste plutôt que de
# construire une URL ou un chemin à partir d'une chaîne venue des logs.
_VALID_ID = re.compile(r"^[A-Za-z0-9_]+$")


def cache_dir() -> Path:
    """``~/.cache/cairn/tiles`` (ou ``$XDG_CACHE_HOME``), créé à la demande."""
    base = os.environ.get("CAIRN_CACHE_DIR") or os.environ.get("XDG_CACHE_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".cache"
    if not os.environ.get("CAIRN_CACHE_DIR"):
        root = root / "cairn"
    return root / "tiles"


def valid(card_id: str) -> bool:
    return bool(card_id) and _VALID_ID.match(card_id) is not None


def path_for(card_id: str) -> Path | None:
    """Emplacement local de la tuile, ``None`` si l'identifiant est douteux."""
    return cache_dir() / f"{card_id}.png" if valid(card_id) else None


def cached(card_id: str) -> Path | None:
    """Chemin de la tuile SI elle est déjà sur le disque, sinon ``None``."""
    path = path_for(card_id)
    return path if path is not None and path.is_file() else None


def download(card_id: str, timeout: float = 12.0) -> Path | None:
    """Télécharge une tuile et rend son chemin (``None`` si elle n'existe pas).

    Écriture atomique : un téléchargement interrompu ne doit pas laisser un PNG
    tronqué que la session suivante prendrait pour un cache valide.
    """
    dest = path_for(card_id)
    if dest is None:
        return None
    if dest.is_file():
        return dest
    req = urllib.request.Request(
        URL.format(card_id=card_id), headers={"User-Agent": "cairn"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return None
    if not data.startswith(b"\x89PNG"):
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(f".{os.getpid()}.part")
    try:
        tmp.write_bytes(data)
        tmp.replace(dest)
    except OSError:
        tmp.unlink(missing_ok=True)
        return None
    return dest
