"""Envoi des parties partagées : transport, file d'attente, reprise sur échec.

Séparé de ``sharing`` à dessein. ``sharing`` répond à « qu'est-ce qui a le droit
de partir » (consentement, pseudonymisation, contenu de l'outbox) ; ce module-ci
répond à « comment ça part, et que faire quand ça rate ». Les deux questions ont
des raisons de changer différentes.

Rien ne part tant qu'aucun point de collecte n'est configuré : ``ENDPOINT`` vide
est le comportement par défaut, et Cairn se comporte alors exactement comme
avant — les sessions s'empilent dans l'outbox, visibles et effaçables.

Principes
---------
- **Jamais bloquant.** Aucune erreur d'envoi ne doit se voir en jeu. Tout est
  avalé, daté, réessayé plus tard.
- **Jamais pendant une partie.** L'appelant décide, mais l'outbox n'est de toute
  façon alimentée qu'entre deux parties.
- **Reprise avec attente croissante.** Un serveur en panne ne doit pas être
  martelé à chaque lancement, et une coupure réseau de dix minutes ne doit pas
  coûter la partie.
- **Ce qui est parti est effacé.** L'outbox n'est pas un historique — les
  journaux complets vivent déjà dans ``~/.local/share/cairn/sessions``.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__
from .sharing import outbox_dir

# Point de collecte. Vide = rien ne part (défaut). Il est destiné à être écrit
# en dur ici le jour où le service existe : l'application est publique, donc
# l'URL le sera aussi — c'est au SERVEUR de se protéger (quota par
# ``install_id``, taille maximale, rejet du reste), pas à un secret embarqué
# dans un binaire distribué de faire semblant d'en être un.
ENDPOINT_DEFAUT = ""

# Attente avant le n-ième nouvel essai : une minute, cinq, une demi-heure, deux
# heures, douze, puis un jour. Au-delà on garde la session sans plus réessayer
# tout seul — le bouton d'envoi manuel force toujours le passage.
BACKOFF = (60, 300, 1_800, 7_200, 43_200, 86_400)
TAILLE_MAX = 25 * 1024 * 1024   # une session compressée pèse ~0,5 Mo
TIMEOUT = 30.0
ETAT = "envoi.json"             # dans le dossier de session, jamais envoyé


def endpoint() -> str:
    """URL de collecte — la variable d'environnement l'emporte (tests, essais)."""
    return os.environ.get("CAIRN_SHARE_ENDPOINT", ENDPOINT_DEFAUT).strip()


# ---- état de chaque session en attente ---------------------------------------

def etat(session: Path) -> dict:
    try:
        with open(session / ETAT, encoding="utf-8") as f:
            charge = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return charge if isinstance(charge, dict) else {}


def _noter(session: Path, **champs) -> None:
    fusion = etat(session) | champs
    try:
        (session / ETAT).write_text(
            json.dumps(fusion, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    except OSError:
        pass   # outbox effacée sous nos pieds : sans conséquence


def a_essayer(session: Path, maintenant: float | None = None) -> bool:
    """L'attente avant nouvel essai est-elle écoulée ?"""
    e = etat(session)
    if e.get("abandonne"):
        return False
    maintenant = time.time() if maintenant is None else maintenant
    return maintenant >= (e.get("prochain_essai") or 0)


def _reporter(session: Path, message: str, maintenant: float) -> None:
    tentatives = int(etat(session).get("tentatives") or 0) + 1
    attente = BACKOFF[min(tentatives - 1, len(BACKOFF) - 1)]
    _noter(
        session,
        tentatives=tentatives,
        derniere_erreur=message[:200],
        prochain_essai=maintenant + attente,
        # au-delà du dernier palier on cesse de réessayer tout seul : la
        # session reste visible dans le launcher, et le bouton d'envoi manuel
        # force toujours le passage.
        abandonne=tentatives > len(BACKOFF),
    )


# ---- transport ---------------------------------------------------------------

def archive(session: Path) -> bytes:
    """La session entière en un seul ``tar.gz`` — sauf son fichier d'état.

    Un seul objet par session plutôt qu'un fichier par requête : le serveur n'a
    rien à recoller, et une session à moitié montée n'existe pas.
    """
    tampon = io.BytesIO()
    # USTAR et non le PAX par défaut de Python : PAX préfixe l'archive d'une
    # entrée « ././@PaxHeader » qui n'apporte rien ici (noms courts, ASCII) et
    # que tout lecteur naïf — le point de collecte, par exemple — devrait
    # apprendre à sauter. Le premier bloc de 512 octets décrit ainsi
    # directement le premier vrai fichier.
    with tarfile.open(fileobj=tampon, mode="w:gz",
                      format=tarfile.USTAR_FORMAT) as tar:
        for fichier in sorted(session.iterdir()):
            if fichier.name == ETAT or not fichier.is_file():
                continue
            tar.add(fichier, arcname=f"{session.name}/{fichier.name}")
    return tampon.getvalue()


def envoyer_session(session: Path, url: str, install_id: str = "",
                    timeout: float = TIMEOUT) -> tuple[bool, str, bool]:
    """Envoie UNE session. Rend ``(succès, message, définitif)``, ne lève jamais.

    ``définitif`` distingue « le réseau était coupé » de « ce contenu ne passera
    jamais » : réessayer une session trop volumineuse ou refusée par le serveur
    ne fait que remplir des journaux. Le message n'est pas destiné à
    l'utilisateur — il est écrit dans l'état de la session pour que
    ``cairn-doctor`` puisse dire pourquoi ça coince.
    """
    try:
        corps = archive(session)
    except OSError as err:
        return False, f"lecture impossible : {err}", False
    if len(corps) > TAILLE_MAX:
        # la taille ne va pas diminuer toute seule
        return False, f"trop volumineuse ({len(corps) / 1048576:.1f} Mo)", True
    requete = urllib.request.Request(
        url,
        data=corps,
        method="POST",
        headers={
            "Content-Type": "application/gzip",
            "User-Agent": f"cairn/{__version__}",
            "X-Cairn-Install": install_id,
            "X-Cairn-Session": session.name,
            "X-Cairn-Version": __version__,
        },
    )
    try:
        with urllib.request.urlopen(requete, timeout=timeout) as reponse:
            code = reponse.status
    except urllib.error.HTTPError as err:
        # 4xx = le serveur a compris et refuse ; réessayer ne changera rien.
        # Sauf 408 (délai dépassé) et 429 (quota), qui invitent explicitement à
        # revenir plus tard.
        definitif = 400 <= err.code < 500 and err.code not in (408, 429)
        return False, f"HTTP {err.code}", definitif
    except (urllib.error.URLError, OSError, TimeoutError, ValueError) as err:
        return False, str(err), False
    if 200 <= code < 300:
        return True, "", False
    return False, f"HTTP {code}", False


def envoyer_en_attente(url: str | None = None, install_id: str = "",
                       dest: Path | None = None,
                       maintenant: float | None = None) -> tuple[int, int]:
    """Vide l'outbox autant que possible. Rend ``(envoyées, restantes)``.

    Sans point de collecte configuré, ne fait rien et le dit : ``(0, n)``.
    """
    dest = dest or outbox_dir()
    url = endpoint() if url is None else url
    if not dest.is_dir():
        return (0, 0)
    sessions = sorted(d for d in dest.iterdir() if d.is_dir())
    if not url:
        return (0, len(sessions))
    maintenant = time.time() if maintenant is None else maintenant
    envoyees = 0
    for session in sessions:
        if not a_essayer(session, maintenant):
            continue
        ok, message, definitif = envoyer_session(session, url, install_id)
        if ok:
            # partie livrée : l'outbox n'a pas vocation à garder une copie,
            # le journal complet est déjà archivé par ailleurs
            shutil.rmtree(session, ignore_errors=True)
            envoyees += 1
        elif definitif:
            _noter(session, tentatives=int(etat(session).get("tentatives") or 0) + 1,
                   derniere_erreur=message[:200], abandonne=True)
        else:
            _reporter(session, message, maintenant)
    restantes = len([d for d in dest.iterdir() if d.is_dir()])
    return (envoyees, restantes)


def bloquees(dest: Path | None = None) -> list[tuple[str, str]]:
    """Sessions que Cairn a renoncé à réessayer, avec la raison."""
    dest = dest or outbox_dir()
    if not dest.is_dir():
        return []
    out = []
    for session in sorted(d for d in dest.iterdir() if d.is_dir()):
        e = etat(session)
        if e.get("abandonne"):
            out.append((session.name, e.get("derniere_erreur", "?")))
    return out
