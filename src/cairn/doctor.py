#!/usr/bin/env python3
"""Diagnostic d'installation de Cairn.

    cairn-doctor          # état des lieux
    cairn-doctor --fix    # corrige ce qui peut l'être (journaux, plafond)

Affiche tout ce dont dépend le tracker : prefix du jeu, journaux activés,
base de cartes, compositeur. À joindre à tout rapport de bug.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .hs_setup import (
    PREFIX_ENV,
    client_config_ok,
    client_config_path,
    ensure_client_config,
    detect_prefix,
    ensure_log_config,
    find_prefixes,
    log_config_status,
    logs_root,
)
from .paths import CARDS_JSON, CARDS_JSON_EN

OK, WARN, BAD = "\033[32m✓\033[0m", "\033[33m!\033[0m", "\033[31m✗\033[0m"


def line(mark: str, label: str, detail: str = "") -> None:
    print(f" {mark} {label:<26} {detail}")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    fix = "--fix" in argv
    print("\n\033[1mCairn — diagnostic\033[0m\n")

    # ---- prefix du jeu ------------------------------------------------------
    env = os.environ.get(PREFIX_ENV)
    if env:
        line(OK if Path(env).is_dir() else BAD, f"${PREFIX_ENV}", env)

    found = find_prefixes()
    prefix = detect_prefix()
    if prefix is None:
        line(BAD, "prefix Hearthstone", "INTROUVABLE")
        print(
            "\n   Aucune installation détectée. Indique-la à la main :\n"
            f"     export {PREFIX_ENV}=/chemin/vers/le/prefix\n"
            "   (le prefix est le dossier qui CONTIENT « drive_c »)\n"
        )
        return 1

    line(OK, "prefix Hearthstone", str(prefix))
    for other in found[1:]:
        line(WARN, "autre installation", f"{other} (ignorée)")

    root = logs_root(prefix)
    sessions = sorted(root.glob("Hearthstone_*")) if root.is_dir() else []
    line(
        OK if sessions else WARN,
        "sessions de journaux",
        f"{len(sessions)} dans {root}" if sessions else f"aucune dans {root}",
    )

    # ---- journaux du jeu ----------------------------------------------------
    status = log_config_status(prefix)
    if fix and not status.ready:
        status = ensure_log_config(prefix)
        print("   → log.config écrit ; REDÉMARRE Hearthstone pour qu'il en tienne compte.")
    labels = {
        "ok": (OK, "activés"),
        "incomplete": (BAD, "incomplets — relance avec --fix"),
        "missing": (BAD, "absents — relance avec --fix"),
        "no_prefix": (BAD, "prefix introuvable"),
    }
    mark, text = labels[status.state]
    line(mark, "journaux du jeu", f"{text}  {status.path or ''}")

    # plafond de 10 Mo : sans cette clé, HS cesse d'écrire en pleine session
    if fix and not client_config_ok(prefix):
        ensure_client_config(prefix)
        print("   → client.config écrit ; REDÉMARRE Hearthstone.")
    capped = not client_config_ok(prefix)
    line(
        BAD if capped else OK,
        "plafond des journaux",
        ("10 Mo — relance avec --fix (sinon HS coupe le suivi en pleine partie)"
         if capped else f"levé  {client_config_path(prefix)}"),
    )

    # taille du journal courant : la limite Blizzard des 10 Mo coupe le logger
    if sessions:
        power = sessions[-1] / "Power.log"
        if power.is_file():
            st = power.stat()
            mo = st.st_size / 1048576
            sparse = st.st_blocks * 512 < st.st_size // 2 and st.st_size > 1_000_000
            line(
                BAD if sparse else (OK if mo < 8 else WARN),
                "Power.log courant",
                f"{mo:.1f} Mo"
                + (
                    "  FICHIER À TROUS — mets log_rotation à false dans la config"
                    if sparse
                    else ("  (plafond levé : il peut grossir librement)"
                          if not capped else "  / 10 — plafond encore actif")
                ),
            )

    # ---- base de cartes -----------------------------------------------------
    for label, path, needed in (
        ("base de cartes (FR)", CARDS_JSON, True),
        ("noms anglais", CARDS_JSON_EN, False),
    ):
        if path.is_file():
            line(OK, label, f"{path.stat().st_size / 1048576:.1f} Mo")
        else:
            line(
                BAD if needed else WARN,
                label,
                "absente — python tools/fetch_cards.py"
                + ("" if needed else " enUS"),
            )

    # Le drapeau « pos » (haut/fond du deck) est calculé au téléchargement : une
    # base antérieure à cette version fait taire le suivi des bouts de deck,
    # silencieusement. Autant le dire.
    if CARDS_JSON.is_file():
        try:
            from .cards_db import CardsDb

            db = CardsDb.load()
            n = len(db.deck_bottom_ids) + len(db.deck_top_ids)
        except Exception:
            n = 0
        if n:
            line(OK, "bouts de deck connus", f"{n} cartes repérées")
        else:
            line(WARN, "bouts de deck connus",
                 "base trop ancienne — relance « cairn-cards all »")

    # Fraîcheur de la base et reformulations en attente : le téléchargement est
    # automatique (cf. app.ensure_cards), mais une carte dont le JEU a changé
    # l'effet demande une relecture du code — ça, aucun téléchargement ne le
    # fait, donc on le laisse s'afficher jusqu'à « cairn-cards --vu ».
    if CARDS_JSON.is_file():
        from .cards_fetch import meta

        infos = meta()
        fr = (infos.get("locales") or {}).get("frFR") or {}
        if fr.get("le"):
            line(OK, "base à jour depuis", fr["le"])
        else:
            line(WARN, "version de la base",
                 "inconnue — sera datée au prochain « cairn-cards all »")
        for a in infos.get("alertes") or []:
            line(WARN, f"effet reformulé : {a['id']}",
                 f"{a['role']} — texte changé le {a.get('vu', '?')}, "
                 f"logique à revérifier (« cairn-cards --vu » pour masquer)")

    # ---- affichage ----------------------------------------------------------
    session_type = os.environ.get("XDG_SESSION_TYPE", "?")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "?")
    kde = "KDE" in desktop.upper()
    line(
        OK if kde else WARN,
        "bureau",
        f"{desktop} ({session_type})"
        + ("" if kde else " — règles KWin indisponibles, cf. README"),
    )
    if kde:
        rules = Path.home() / ".config/kwinrulesrc"
        installed = rules.is_file() and "cairn-overlay" in rules.read_text(
            encoding="utf-8", errors="replace"
        )
        line(
            OK if installed else WARN,
            "règles de fenêtres",
            "installées" if installed else "manquantes — relance install.sh, ou « Replacer les widgets » dans le launcher",
        )

    ready = status.ready and CARDS_JSON.is_file() and not capped
    print("\n\033[1m" + ("Tout est prêt." if ready else "Configuration incomplète — voir ci-dessus.") + "\033[0m\n")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
