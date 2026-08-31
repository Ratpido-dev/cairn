"""Chemins du projet et du prefix Hearthstone.

Le prefix n'est plus en dur : il est détecté (cf. ``hs_setup``) et peut être
forcé par la configuration ou la variable ``CAIRN_HS_PREFIX``. Les constantes
de module restent disponibles pour les outils, mais tout code devant suivre un
changement de configuration passe par ``resolve_logs_root()``.
"""

from __future__ import annotations

import gzip
import os
from pathlib import Path

from .hs_setup import HS_SUBPATH, detect_prefix, logs_root

# ---- données de Cairn -------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[2]


def _xdg_data() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "cairn"


def _data_dir() -> Path:
    """Où vivent la base de cartes et les fixtures.

    Trois cas, dans l'ordre : la variable ``CAIRN_DATA_DIR``, puis le dossier
    ``data/`` du dépôt s'il existe (développement, lancement depuis les
    sources), enfin ``~/.local/share/cairn`` (installation normale).
    """
    forced = os.environ.get("CAIRN_DATA_DIR")
    if forced:
        return Path(forced).expanduser()
    repo = _ROOT / "data"
    if (repo / "cards").is_dir() or (repo / "fixtures").is_dir():
        return repo
    return _xdg_data()


DATA_DIR = _data_dir()
# Base COMPLÈTE (pas seulement collectible) : le tracker doit connaître les
# tokens, bombes et cartes créées — et les cartes trop récentes pour être
# marquées collectible dans HearthstoneJSON (cf. set TIME_TRAVEL, 07/2026).
CARDS_DIR = DATA_DIR / "cards"
CARDS_JSON = CARDS_DIR / "cards.frFR.json"
# noms anglais : fichier optionnel, chargé seulement en mode EN (id → name)
CARDS_JSON_EN = CARDS_DIR / "cards.enUS.json"
# Textes des cartes (id → texte de règles), un fichier par locale. À PART de la
# base principale, et chargé seulement au premier survol : les textes pèsent
# autant que tout le reste réuni, alors qu'ils ne servent qu'à l'infobulle.
CARDS_TEXT = CARDS_DIR / "cards.text.frFR.json"
CARDS_TEXT_EN = CARDS_DIR / "cards.text.enUS.json"
# Version de la base téléchargée (empreintes HTTP, date du dernier contrôle,
# alertes de reformulation) — cf. ``cards_fetch``. Fichier de quelques
# centaines d'octets, jamais chargé par le tracker en cours de partie.
CARDS_META = CARDS_DIR / "meta.json"
FIXTURES_DIR = DATA_DIR / "fixtures"


def preparer_fixtures(racine: Path | None = None) -> int:
    """Décompresse les journaux de fixture versionnés en ``.gz``.

    Les parties de référence sont **stockées compressées** (1,3 Mo au lieu de
    21) et **pseudonymisées** : un ``Power.log`` brut contient le battletag de
    l'adversaire, qui n'a jamais rien accepté. Tout le reste du code — tailer,
    archiveur, outils — attend un ``Power.log`` ordinaire, alors on le lui
    rend, une fois, à la demande. Le fichier décompressé n'est pas versionné.

    Rend le nombre de journaux écrits (0 si tout était déjà là).
    """
    racine = racine or FIXTURES_DIR
    if not racine.is_dir():
        return 0
    ecrits = 0
    for archive in racine.glob("*/*.log.gz"):
        clair = archive.with_suffix("")  # « Power.log.gz » → « Power.log »
        if clair.is_file():
            continue
        with gzip.open(archive, "rb") as src:
            clair.write_bytes(src.read())
        ecrits += 1
    return ecrits
# Journaux de session archivés (compressés). TOUJOURS dans le dossier
# utilisateur, jamais dans DATA_DIR : en mode source celui-ci est le dépôt, et
# des dizaines de mégaoctets de parties n'ont rien à y faire.
SESSIONS_DIR = _xdg_data() / "sessions"


# ---- chemins du jeu (détectés) ----------------------------------------------

def resolve_prefix(override: str | Path | None = None) -> Path | None:
    """Prefix Wine/Proton du jeu, ``None`` si Hearthstone est introuvable."""
    return detect_prefix(override)


def resolve_logs_root(override: str | Path | None = None) -> Path | None:
    """Dossier ``Logs/`` du jeu, ``None`` si le prefix est introuvable."""
    prefix = resolve_prefix(override)
    return logs_root(prefix) if prefix is not None else None


PREFIX = resolve_prefix()
HS_DIR = (PREFIX / HS_SUBPATH) if PREFIX else None
HS_LOGS_ROOT = logs_root(PREFIX) if PREFIX else None


def latest_session_dir(root: Path | None = None) -> Path | None:
    """Dossier de logs de la session HS la plus récente (``Hearthstone_<date>``)."""
    root = root or resolve_logs_root()
    if root is None or not root.is_dir():
        return None
    sessions = [
        d for d in root.iterdir() if d.is_dir() and d.name.startswith("Hearthstone_")
    ]
    return max(sessions, key=lambda d: d.name, default=None)
