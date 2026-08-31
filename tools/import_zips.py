#!/usr/bin/env python3
"""Dépile les sessions envoyées par quelqu'un d'autre (zips Windows) vers un
dossier de sessions rejouables.

Pendant du collecteur ``tools/windows/`` : lui produit un .zip par session,
celui-ci les remet à plat, vérifie que chaque session contient bien des
parties, et refuse d'écraser une session déjà présente.

Usage :
    python tools/import_zips.py ~/recu/frere/*.zip           # → data/fixtures
    python tools/import_zips.py -d ~/parties-frere ~/recu/*.zip
    python tools/import_zips.py --liste ~/recu/*.zip         # sans rien écrire

Par défaut la destination est ``data/fixtures`` : les parties d'autrui y
deviennent des cas de test. Pour les garder à part (ne pas les publier avec
le dépôt), passe ``-d``.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cairn.paths import FIXTURES_DIR  # noqa: E402

KEEP = ("Power.log", "Decks.log", "LoadingScreen.log")


def sessions_du_zip(archive: Path) -> tuple[str, dict[str, bytes]]:
    """Nom de session + contenu utile. Le nom vient du zip lui-même, que le
    collecteur nomme d'après le dossier de session (``Hearthstone_<date>``)."""
    fichiers: dict[str, bytes] = {}
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            nom = Path(info.filename).name
            if nom in KEEP and not info.is_dir():
                fichiers[nom] = z.read(info)
    return archive.stem, fichiers


def parties(power: bytes) -> int:
    """Nombre de parties réellement rejouables dans un Power.log.

    Attention : ``CREATE_GAME`` apparaît DEUX fois par partie, une par flux —
    HS écrit le même déroulé sous ``GameState`` et sous ``PowerTaskList``.
    Compter les occurrences brutes annonce le double. Le moteur ne suit que
    ``GameState``, c'est donc lui qui fait foi.
    """
    return power.count(b"GameState.DebugPrintPower() - CREATE_GAME")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zips", nargs="+", type=Path)
    ap.add_argument("-d", "--dest", type=Path, default=FIXTURES_DIR,
                    help=f"dossier de destination (défaut : {FIXTURES_DIR})")
    ap.add_argument("--liste", action="store_true", help="n'écrit rien")
    args = ap.parse_args(argv)

    total_parties = importees = ignorees = vides = 0

    for archive in sorted(args.zips):
        if not archive.is_file():
            print(f"  introuvable : {archive}", file=sys.stderr)
            continue
        try:
            nom, fichiers = sessions_du_zip(archive)
        except zipfile.BadZipFile:
            print(f"  archive illisible : {archive.name}", file=sys.stderr)
            continue

        power = fichiers.get("Power.log")
        if not power:
            print(f"  {archive.name} : pas de Power.log")
            vides += 1
            continue
        n = parties(power)
        if n == 0:
            # Sans log.config côté joueur, HS écrit un Power.log qui ne contient
            # que ses erreurs internes : aucune partie à en tirer.
            print(f"  {archive.name} : aucune partie (journaux du jeu non activés ?)")
            vides += 1
            continue

        dest = args.dest / nom
        if dest.exists():
            print(f"  {nom} : déjà présent, ignoré")
            ignorees += 1
            continue

        mo = len(power) / 1048576
        print(f"  {nom} : {n} partie{'s' if n > 1 else ''}, {mo:.1f} Mo")
        total_parties += n
        importees += 1
        if args.liste:
            continue
        dest.mkdir(parents=True, exist_ok=True)
        for fnom, data in fichiers.items():
            (dest / fnom).write_bytes(data)

    print()
    verbe = "à importer" if args.liste else "importée(s)"
    print(f"{importees} session(s) {verbe} — {total_parties} partie(s) au total"
          f" · {ignorees} déjà là · {vides} sans partie")
    if importees and not args.liste:
        print(f"→ {args.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
