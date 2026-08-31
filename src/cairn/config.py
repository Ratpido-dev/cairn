"""Configuration utilisateur (~/.config/cairn/config.json).

Chaque add-on (compteur, panneau) est activable depuis le launcher ;
les échelles permettent d'agrandir les fenêtres si on voit mal.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


# Les six paliers du classé. « LEGEND » n'a pas de niveau 10→1.
LEAGUES = ("BRONZE", "SILVER", "GOLD", "PLATINUM", "DIAMOND", "LEGEND")


def default_config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "cairn" / "config.json"


@dataclass
class Config:
    # add-ons : clé de compteur → activé (les clés absentes = activées)
    counters: dict[str, bool] = field(default_factory=dict)
    opp_panel: bool = True
    # pastilles flottantes posées sous la main adverse (tour d'arrivée, cadeau,
    # vignette) — elles remplacent la section « EN MAIN » du panneau gauche
    hand_dots: bool = True
    language: str = "fr"  # "fr" | "en"
    hs_prefix: str = ""  # force le prefix Wine/Proton si la détection se trompe
    # Commande de lancement du jeu, saisie par l'utilisateur. C'est le SEUL
    # mécanisme qui marche pour tout le monde : la détection (Lutris, .desktop)
    # n'est qu'un raccourci pour les cas courants, et ne trouvera jamais un
    # script maison ou un lanceur exotique. Vide = on tente la détection.
    hs_launch_command: str = ""
    # Archivage compressé des journaux de session (cf. archive.py). Actif par
    # défaut : Hearthstone efface ses vieux dossiers de logs sans prévenir, et
    # une session archivée coûte moins d'un mégaoctet.
    archive_sessions: bool = True
    log_rotation: bool = False  # cf. log_watcher : sans effet sous Wine
    panel_scale: float = 1.0
    opp_scale: float = 1.0
    bar_scale: float = 1.0
    # ---- partage volontaire de parties -------------------------------------
    # "" = jamais demandé (le consentement s'affiche au démarrage), sinon
    # "yes" / "no". Trois états et non un booléen : sans ça, impossible de
    # distinguer « a refusé » de « n'a pas encore vu la question ».
    share_games: str = ""
    # Pas de réglage d'anonymisation : elle est inconditionnelle (cf.
    # ``sharing.preparer``). L'ancienne clé « share_anonymise » des fichiers
    # existants est simplement ignorée à la relecture.
    install_id: str = ""           # UUID local : sert aux demandes de suppression
    # « lo » du GameAccountId du joueur, appris tout seul (cf.
    # ``game_state.learn_own_account``) : c'est le seul moyen de reconnaître
    # une partie regardée en spectateur, que HS journalise comme les autres.
    # Jamais partagé — ``sharing.preparer`` anonymise inconditionnellement.
    own_account: str = ""
    # Rang déclaré par le joueur : Hearthstone ne l'écrit dans AUCUN journal
    # (Firestone le lit dans la mémoire du jeu). Déclaratif, donc, et facultatif.
    rank_league: str = ""          # BRONZE | SILVER | GOLD | PLATINUM | DIAMOND | LEGEND
    rank_level: int = 0            # 10 → 1 ; ignoré en Légende
    # ---- position des widgets flottants ------------------------------------
    # nom de widget → {"x": int, "y": int}. Sous Wayland un client ne peut pas
    # se placer lui-même (c'est KWin qui décide, cf. règles cairn-pos-*) ; on
    # garde quand même la position pour les sessions X11 et pour survivre à un
    # changement d'environnement. Le widget la réapplique s'il le peut.
    widget_pos: dict[str, dict[str, int]] = field(default_factory=dict)
    # Sections du launcher repliées. Les add-ons se règlent une fois puis ne
    # bougent plus : les garder dépliés obligeait à faire défiler toute la
    # grille pour atteindre les statistiques.
    sections_collapsed: dict[str, bool] = field(default_factory=dict)

    @property
    def consent_asked(self) -> bool:
        return self.share_games in ("yes", "no")

    @property
    def share_enabled(self) -> bool:
        return self.share_games == "yes"

    def counter_enabled(self, key: str) -> bool:
        return self.counters.get(key, True)

    # ---- position des widgets ----------------------------------------------

    def section_collapsed(self, name: str, default: bool = False) -> bool:
        valeur = self.sections_collapsed.get(name)
        return default if valeur is None else bool(valeur)

    def set_section_collapsed(self, name: str, collapsed: bool) -> None:
        self.sections_collapsed[name] = bool(collapsed)

    def pos_of(self, widget: str) -> tuple[int, int] | None:
        """Position retenue pour un widget, ou None s'il n'a jamais bougé."""
        raw = self.widget_pos.get(widget)
        if not isinstance(raw, dict):
            return None
        try:
            return int(raw["x"]), int(raw["y"])
        except (KeyError, TypeError, ValueError):
            return None

    def set_pos(self, widget: str, x: int, y: int) -> None:
        # les positions négatives viennent d'un écran débranché ou d'un
        # placement raté : les retenir condamnerait le widget hors de l'écran
        self.widget_pos[widget] = {"x": max(0, int(x)), "y": max(0, int(y))}

    # ---- persistance -------------------------------------------------------

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or default_config_path()
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        cfg = cls()
        cfg.counters = dict(data.get("counters", {}))
        cfg.opp_panel = bool(data.get("opp_panel", True))
        cfg.hand_dots = bool(data.get("hand_dots", True))
        cfg.language = "en" if data.get("language") == "en" else "fr"
        cfg.hs_prefix = str(data.get("hs_prefix") or "")
        cfg.log_rotation = bool(data.get("log_rotation", False))
        cfg.archive_sessions = bool(data.get("archive_sessions", True))
        partage = data.get("share_games")
        cfg.share_games = partage if partage in ("yes", "no") else ""
        cfg.install_id = str(data.get("install_id") or "")
        ligue = str(data.get("rank_league") or "")
        cfg.rank_league = ligue if ligue in LEAGUES else ""
        try:
            cfg.rank_level = max(0, min(10, int(data.get("rank_level", 0))))
        except (TypeError, ValueError):
            cfg.rank_level = 0
        replis = data.get("sections_collapsed")
        if isinstance(replis, dict):
            cfg.sections_collapsed = {str(k): bool(v) for k, v in replis.items()}
        brut = data.get("widget_pos")
        if isinstance(brut, dict):
            for nom, val in brut.items():
                if isinstance(val, dict) and {"x", "y"} <= set(val):
                    try:
                        cfg.set_pos(str(nom), val["x"], val["y"])
                    except (TypeError, ValueError):
                        pass
        for name in ("panel_scale", "opp_scale", "bar_scale"):
            try:
                setattr(cfg, name, max(0.6, min(2.0, float(data.get(name, 1.0)))))
            except (TypeError, ValueError):
                pass
        return cfg

    def save(self, path: Path | None = None) -> None:
        path = path or default_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
        )
