"""Fait échouer la CI quand trop de tests se sont SAUTÉS.

Pourquoi ce script existe. La plupart des tests de Cairn ont besoin de la base
de cartes et des parties de référence ; sans elles, ils ne échouent pas — ils
se **sautent**, et pytest affiche quand même « vert ». Mesuré sur ce dépôt :
sans la base de cartes, 150 tests passent et **202 se sautent**. Une CI naïve
annoncerait donc un succès en n'ayant exécuté que 43 % de la suite.

C'est le pire genre de CI : elle ne dit pas « je n'ai rien vérifié », elle dit
« tout va bien ». Ce script transforme ce silence en échec.

Usage : python tools/ci_check_skips.py report.xml --max-skips 10
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET


def compter(rapport: str) -> tuple[int, int, int, int]:
    """(total, sautés, échecs, erreurs) lus dans le JUnit XML de pytest."""
    racine = ET.parse(rapport).getroot()
    # pytest écrit <testsuites><testsuite …> ; certains outils écrivent
    # directement <testsuite>. On accepte les deux plutôt que de supposer.
    suites = racine.findall("testsuite") or [racine]
    total = sautes = echecs = erreurs = 0
    for s in suites:
        total += int(s.get("tests", 0))
        sautes += int(s.get("skipped", 0))
        echecs += int(s.get("failures", 0))
        erreurs += int(s.get("errors", 0))
    return total, sautes, echecs, erreurs


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("rapport", help="fichier JUnit XML produit par --junitxml")
    p.add_argument("--max-skips", type=int, default=10,
                   help="nombre de tests sautés au-delà duquel on échoue")
    args = p.parse_args(argv)

    total, sautes, echecs, erreurs = compter(args.rapport)
    executes = total - sautes
    part = (100 * executes / total) if total else 0
    print(f"{total} tests · {executes} exécutés ({part:.0f} %) · {sautes} sautés "
          f"· {echecs} échecs · {erreurs} erreurs")

    if sautes > args.max_skips:
        print(
            f"\nÉCHEC : {sautes} tests sautés (plafond : {args.max_skips}).\n"
            "La suite n'a pas vraiment tourné. La cause la plus probable est\n"
            "que la base de cartes n'a pas été téléchargée avant les tests\n"
            "(étape « cairn-cards »), ou que les parties de référence manquent.\n"
            "Un vert obtenu ainsi ne prouverait rien.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
