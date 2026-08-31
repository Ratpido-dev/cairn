#!/usr/bin/env python3
"""Télécharge le corpus public de parties partagées.

Le pendant de ``src/cairn/envoi.py`` : celui-ci envoie, celui-là rapatrie. Le
corpus est ouvert — voir la section « Pourquoi le corpus est ouvert » du
README — donc ce script n'a besoin d'aucune clé, d'aucun compte, et fonctionne
contre n'importe quel point de collecte, pas seulement celui de l'auteur.

Usage :
    python tools/corpus.py --url https://collecte.exemple.workers.dev
    python tools/corpus.py --liste                    # juste voir ce qu'il y a
    python tools/corpus.py --installation <id>        # une seule installation
    python tools/corpus.py --dest ~/corpus --extraire

Le point de collecte est pris dans ``CAIRN_SHARE_ENDPOINT`` à défaut de
``--url``, pour que « ce que j'envoie » et « ce que je relis » ne puissent pas
diverger silencieusement.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cairn import __version__  # noqa: E402

TIMEOUT = 60.0
AGENT = {"User-Agent": f"cairn-corpus/{__version__}"}

# Plafonds. Le corpus est ouvert, donc ce qu'on télécharge vient d'inconnus :
# c'est le seul endroit du projet où Cairn consomme des données que personne
# n'a filtrées. Une session pèse ~500 Ko compressée, ~10 Mo déballée ; ces
# plafonds laissent une marge de vingt fois et ferment quand même la porte à la
# bombe de décompression — 8 Mo de gzip peuvent rendre plusieurs gigaoctets, et
# c'est le disque de celui qui télécharge qui se remplit, pas le serveur.
LECTURE_MAX = 16 * 1024 * 1024    # une réponse HTTP
DEBALLE_MAX = 200 * 1024 * 1024   # une archive une fois déballée


class Refus(Exception):
    """Contenu hors des clous. Ce n'est pas une panne : c'est un refus."""


def _lire(url: str, plafond: int = LECTURE_MAX) -> bytes:
    """Lit une réponse, en s'arrêtant net au plafond.

    ``read(n)`` et non ``read()`` : un serveur hostile — ou simplement une URL
    ``--url`` mal choisie — peut sinon servir un flux sans fin, et c'est la
    mémoire du client qui s'épuise.
    """
    requete = urllib.request.Request(url, headers=AGENT)
    with urllib.request.urlopen(requete, timeout=TIMEOUT) as reponse:
        corps = reponse.read(plafond + 1)
    if len(corps) > plafond:
        raise Refus(f"réponse de plus de {plafond // 1048576} Mo : {url}")
    return corps


def index(base: str, installation: str = "") -> list[dict]:
    """L'index complet, page après page. Le curseur est l'affaire du serveur."""
    sessions: list[dict] = []
    curseur = None
    while True:
        params = {}
        if installation:
            params["installation"] = installation
        if curseur:
            params["curseur"] = curseur
        url = f"{base}/parties"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        page = json.loads(_lire(url))
        sessions.extend(page.get("sessions") or [])
        curseur = page.get("curseur")
        if not curseur:
            return sessions


def telecharger(base: str, cle: str, dest: Path) -> Path | None:
    """Rapatrie une session. Rend son chemin, ou ``None`` si elle est déjà là.

    Sauter ce qui existe déjà rend le script relançable : le corpus grandit,
    on le resynchronise, on ne le retélécharge pas.
    """
    cible = dest / f"{cle.replace('/', '_')}"
    if cible.exists():
        return None
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(_lire(f"{base}/parties/{cle}"))
    return cible


def extraire(archive: Path, dest: Path) -> None:
    """Déballe une archive reçue, sans lui faire confiance.

    Deux protections, contre deux attaques différentes :

    - ``filter="data"`` refuse les chemins absolus, les ``..``, les liens
      symboliques et les fichiers spéciaux. Sans lui, une archive contenant
      ``../../.ssh/authorized_keys`` écrit où elle veut ;
    - le total annoncé est vérifié AVANT d'écrire quoi que ce soit. Le filtre
      ne regarde que les noms, pas les tailles : une archive de 500 Ko qui se
      déballe en 40 Go passerait sans lui.
    """
    with tarfile.open(archive, "r:gz") as tar:
        total = sum(m.size for m in tar.getmembers() if m.isfile())
        if total > DEBALLE_MAX:
            raise Refus(f"{archive.name} : {total / 1048576:.0f} Mo une fois "
                        f"déballée, plafond {DEBALLE_MAX // 1048576} Mo")
        tar.extractall(dest, filter="data")


def main() -> None:
    a = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--url", default=os.environ.get("CAIRN_SHARE_ENDPOINT", ""),
                   help="point de collecte (défaut : $CAIRN_SHARE_ENDPOINT)")
    a.add_argument("--dest", type=Path, default=Path("corpus"),
                   help="où ranger les archives (défaut : ./corpus)")
    a.add_argument("--installation", default="",
                   help="ne prendre que les sessions de cette installation")
    a.add_argument("--liste", action="store_true",
                   help="afficher l'index sans rien télécharger")
    a.add_argument("--extraire", action="store_true",
                   help="déballer chaque archive après téléchargement")
    args = a.parse_args()

    base = args.url.rstrip("/")
    if not base:
        sys.exit("Aucun point de collecte : --url ou CAIRN_SHARE_ENDPOINT.")

    try:
        sessions = index(base, args.installation)
    except (urllib.error.URLError, OSError, ValueError, Refus) as err:
        sys.exit(f"Index illisible : {err}")

    octets = sum(s.get("octets") or 0 for s in sessions)
    print(f"{len(sessions)} sessions, {octets / 1048576:.1f} Mo")
    if args.liste:
        for s in sessions:
            print(f"  {s['cle']:<70} {(s.get('octets') or 0) / 1024:>7.0f} Ko"
                  f"  {s.get('recu', '')}")
        return

    pris = saute = rates = 0
    for s in sessions:
        try:
            chemin = telecharger(base, s["cle"], args.dest)
        except (urllib.error.URLError, OSError, Refus) as err:
            print(f"  ✗ {s['cle']} : {err}")
            rates += 1
            continue
        if chemin is None:
            saute += 1
            continue
        pris += 1
        if not args.extraire:
            continue
        # une archive refusée ne doit pas arrêter les 3 000 suivantes
        try:
            extraire(chemin, args.dest)
        except (Refus, tarfile.TarError, OSError) as err:
            print(f"  ✗ {s['cle']} : {err}")
            rates += 1
    print(f"{pris} téléchargées, {saute} déjà là, {rates} en échec "
          f"→ {args.dest}")


if __name__ == "__main__":
    main()
