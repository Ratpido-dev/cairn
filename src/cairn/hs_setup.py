"""Détection du prefix Wine/Proton de Hearthstone et activation de ses journaux.

Sans ces deux choses, Cairn ne voit RIEN — et c'est invisible pour l'utilisateur :
le jeu tourne, le tracker aussi, mais aucun journal n'est produit ou lu. C'était
le principal obstacle à une installation par quelqu'un d'autre que l'auteur.

Deux problèmes distincts :

1. **Où est installé le jeu ?** Chaque lanceur pose son prefix ailleurs (Lutris,
   Steam/Proton, Heroic, Bottles, PlayOnLinux, wine nu). On sonde les
   emplacements connus, on retient celui dont les journaux sont les plus récents.
2. **Le jeu écrit-il ses journaux ?** Hearthstone ne les produit que si un
   ``log.config`` existe dans son dossier utilisateur. On sait le vérifier et
   l'écrire — sans jamais écraser sans sauvegarde la configuration d'un autre
   tracker déjà installé.
3. **Le jeu va-t-il s'arrêter d'écrire ?** Chaque journal est plafonné à 10 Mo,
   après quoi Hearthstone ferme le fichier et le suivi devient aveugle. La clé
   ``FileSizeLimit.Int=-1`` de ``client.config`` (dossier d'installation du jeu)
   lève ce plafond ; c'est ce que posent HDT et Firestone, et c'est pourquoi ils
   ne connaissent pas ce problème.

Priorité de résolution : variable d'environnement > configuration > détection.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

PREFIX_ENV = "CAIRN_HS_PREFIX"

# Chemin du jeu À L'INTÉRIEUR d'un prefix, et sous-chemin du log.config
HS_SUBPATH = Path("drive_c/Program Files (x86)/Hearthstone")
_LOGCONFIG_SUBPATH = Path("AppData/Local/Blizzard/Hearthstone/log.config")

# Motifs relatifs au HOME, dans l'ordre de vraisemblance. Le prefix est le
# dossier qui CONTIENT « drive_c ».
_CANDIDATE_GLOBS = (
    "Games/*",                                          # Lutris (défaut)
    "Games/*/*",
    "Jeux/*",                                           # Lutris en français
    ".local/share/lutris/runners/winesteam/prefix",
    ".steam/steam/steamapps/compatdata/*/pfx",          # Steam / Proton
    ".local/share/Steam/steamapps/compatdata/*/pfx",
    ".steam/root/steamapps/compatdata/*/pfx",
    "Games/Heroic/Prefixes/default/*/pfx",              # Heroic
    ".var/app/com.usebottles.bottles/data/bottles/bottles/*",  # Bottles Flatpak
    ".local/share/bottles/bottles/*",                   # Bottles natif
    ".PlayOnLinux/wineprefix/*",                        # PlayOnLinux
    ".wine",                                            # wine nu
)

# Lève le plafond de 10 Mo par journal. À placer dans le dossier D'INSTALLATION
# du jeu (à côté de Hearthstone.exe), pas dans AppData. C'est ce que font HDT et
# Firestone — d'où le fait qu'ils ne rencontrent jamais la coupure du logger.
CLIENT_CONFIG_BODY = "[Log]\nFileSizeLimit.Int=-1\n"
_CLIENT_CONFIG_KEY = "FileSizeLimit.Int"


def client_config_path(prefix: Path) -> Path:
    return prefix / HS_SUBPATH / "client.config"


def client_config_ok(prefix: Path | None) -> bool:
    """La limite de taille des journaux est-elle levée ?"""
    if prefix is None:
        return False
    try:
        text = client_config_path(prefix).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    m = re.search(rf"{re.escape(_CLIENT_CONFIG_KEY)}\s*=\s*(-?\d+)", text)
    return bool(m) and int(m.group(1)) < 0


def ensure_client_config(prefix: Path) -> bool:
    """Lève le plafond des journaux. Conserve le reste du fichier s'il existe.

    Prend effet au prochain démarrage de Hearthstone.
    """
    path = client_config_path(prefix)
    if client_config_ok(prefix):
        return True
    try:
        existing = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        if existing and not existing.endswith("\n"):
            existing += "\n"
        if _CLIENT_CONFIG_KEY in existing:
            # clé présente mais avec une autre valeur : on la corrige sur place
            new = re.sub(
                rf"{re.escape(_CLIENT_CONFIG_KEY)}\s*=\s*-?\d+",
                f"{_CLIENT_CONFIG_KEY}=-1",
                existing,
            )
        else:
            if existing:
                path.with_suffix(".config.bak").write_text(existing, encoding="utf-8")
            new = existing + CLIENT_CONFIG_BODY
        path.write_text(new, encoding="utf-8")
    except OSError:
        return False
    return client_config_ok(prefix)


# Journaux dont Cairn a besoin. Volontairement DEUX seulement : moins le jeu
# écrit, plus la session reste légère (et le plafond est de toute façon levé
# par client.config ci-dessus).
_LOG_CONFIG_BODY = """[Power]
LogLevel=1
FilePrinting=true
ConsolePrinting=false
ScreenPrinting=false
Verbose=true

[Decks]
LogLevel=1
FilePrinting=true
ConsolePrinting=false
ScreenPrinting=false
Verbose=true
"""


def _steam_libraries() -> list[Path]:
    """Bibliothèques Steam supplémentaires (jeux sur un second disque)."""
    out: list[Path] = []
    for vdf in (
        Path.home() / ".steam/steam/steamapps/libraryfolders.vdf",
        Path.home() / ".local/share/Steam/steamapps/libraryfolders.vdf",
    ):
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for path in re.findall(r'"path"\s+"([^"]+)"', text):
            out.append(Path(path) / "steamapps/compatdata")
    return out


def iter_candidate_prefixes():
    """Tous les prefixes plausibles présents sur la machine."""
    home = Path.home()
    for pattern in _CANDIDATE_GLOBS:
        try:
            yield from home.glob(pattern)
        except OSError:
            continue
    for lib in _steam_libraries():
        try:
            yield from lib.glob("*/pfx")
        except OSError:
            continue


def has_hearthstone(prefix: Path) -> bool:
    return (prefix / HS_SUBPATH).is_dir()


def _logs_mtime(prefix: Path) -> float:
    """Date du journal le plus récent — départage plusieurs installations."""
    logs = prefix / HS_SUBPATH / "Logs"
    try:
        return max((d.stat().st_mtime for d in logs.iterdir()), default=0.0)
    except OSError:
        return 0.0


def find_prefixes() -> list[Path]:
    """Prefixes contenant Hearthstone, du plus récemment joué au plus ancien."""
    found = {p.resolve() for p in iter_candidate_prefixes() if has_hearthstone(p)}
    return sorted(found, key=_logs_mtime, reverse=True)


def detect_prefix(override: str | Path | None = None) -> Path | None:
    """Prefix à utiliser. Priorité : argument > variable d'env > détection.

    L'argument vient de la configuration utilisateur ; il l'emporte pour qu'une
    installation exotique reste utilisable sans toucher au code.
    """
    for candidate in (override, os.environ.get(PREFIX_ENV)):
        if candidate:
            path = Path(candidate).expanduser()
            if has_hearthstone(path):
                return path
    prefixes = find_prefixes()
    return prefixes[0] if prefixes else None


def logs_root(prefix: Path) -> Path:
    return prefix / HS_SUBPATH / "Logs"


def find_log_config(prefix: Path) -> Path | None:
    """Chemin du log.config EXISTANT (le dossier utilisateur varie :
    « steamuser » sous Proton, le vrai nom de compte sous Lutris)."""
    users = prefix / "drive_c/users"
    try:
        candidates = [u / _LOGCONFIG_SUBPATH for u in users.iterdir() if u.is_dir()]
    except OSError:
        return None
    existing = [c for c in candidates if c.is_file()]
    if existing:
        return max(existing, key=lambda p: p.stat().st_mtime)
    return None


def log_config_target(prefix: Path) -> Path | None:
    """Où ÉCRIRE le log.config : à côté du dossier Blizzard déjà créé par le
    jeu, sinon dans le dossier utilisateur qui a servi le plus récemment."""
    users = prefix / "drive_c/users"
    try:
        user_dirs = [u for u in users.iterdir() if u.is_dir() and u.name != "Public"]
    except OSError:
        return None
    if not user_dirs:
        return None
    with_blizzard = [
        u for u in user_dirs
        if (u / "AppData/Local/Blizzard/Hearthstone").is_dir()
    ]
    pool = with_blizzard or user_dirs
    return max(pool, key=lambda u: u.stat().st_mtime) / _LOGCONFIG_SUBPATH


@dataclass
class LogConfigStatus:
    state: str  # "ok" | "incomplete" | "missing" | "no_prefix"
    path: Path | None = None

    @property
    def ready(self) -> bool:
        return self.state == "ok"


def _section_enabled(text: str, section: str) -> bool:
    """Section présente ET écrivant bien dans un fichier."""
    m = re.search(rf"^\[{section}\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    return bool(m) and re.search(r"FilePrinting\s*=\s*true", m.group(1), re.I) is not None


def log_config_status(prefix: Path | None) -> LogConfigStatus:
    if prefix is None:
        return LogConfigStatus("no_prefix")
    path = find_log_config(prefix)
    if path is None:
        return LogConfigStatus("missing", log_config_target(prefix))
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return LogConfigStatus("missing", path)
    if _section_enabled(text, "Power") and _section_enabled(text, "Decks"):
        return LogConfigStatus("ok", path)
    return LogConfigStatus("incomplete", path)


def ensure_log_config(prefix: Path, force: bool = False) -> LogConfigStatus:
    """Active les journaux du jeu. Sans effet si déjà bon (sauf ``force``).

    Un log.config existant est SAUVEGARDÉ avant réécriture : il peut venir d'un
    autre tracker, et on ne détruit pas silencieusement le réglage d'autrui.
    """
    status = log_config_status(prefix)
    if status.ready and not force:
        return status
    target = status.path or log_config_target(prefix)
    if target is None:
        return LogConfigStatus("missing")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file():
            backup = target.with_suffix(".config.bak")
            if not backup.exists():
                backup.write_bytes(target.read_bytes())
        target.write_text(_LOG_CONFIG_BODY, encoding="utf-8")
    except OSError:
        return LogConfigStatus("missing", target)
    return log_config_status(prefix)
