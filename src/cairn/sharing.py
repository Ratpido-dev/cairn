"""Partage volontaire de parties — file d'attente locale et pseudonymisation.

Rien ne part d'ici : ce module prépare des sessions dans une *outbox* locale, et
c'est ``envoi`` qui les expédie. Découpler les deux permet de tout tester sans
serveur, et de laisser l'utilisateur inspecter ce qui le concerne avant que ça
ne quitte sa machine.

Ce qui part rejoint un corpus **public** : le point de collecte rend ce qu'il a
reçu à qui le demande (``collecte/``, ``tools/corpus.py``). C'est précisément la
pseudonymisation ci-dessous qui rend cette ouverture défendable — il n'existe
nulle part de version brute de ce qui a été publié.

Sur la pseudonymisation
-----------------------
Un Power.log contient deux identifiants par joueur : le **battletag**
(``Joueur#12345``) et le **GameAccountId** de Blizzard. Le RGPD range
l'un comme l'autre parmi les « identifiants en ligne » de l'article 4(1),
donc parmi les données personnelles — savoir le nom civil n'est pas requis.

Le point dur n'est pas l'utilisateur, qui consent pour lui-même, mais son
**adversaire**, qui n'a jamais rien accepté et que l'article 14 obligerait à
informer. D'où le remplacement, par défaut, des identifiants par des jetons
stables *à l'intérieur* d'un fichier : le parseur continue de relier les
événements aux bons joueurs, et rien ne permet de remonter à quelqu'un.

Techniquement le battletag littéral n'apporte rien : aucun compteur, aucune
statistique, aucun test de parseur n'en dépend. C'est le premier argument
avant même le juridique.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# « pseudo#12345 » — Blizzard impose au moins 3 chiffres après le croisillon.
_BATTLETAG = re.compile(r"(?<![\w#])([^\s\[\]=#]{2,24})#(\d{3,})\b")
# « GameAccountId=[hi=144115198130930503 lo=103736218] » : le « lo » identifie
# le compte, le « hi » est la même constante de région pour tout le monde.
_ACCOUNT = re.compile(r"(GameAccountId=\[hi=)(\d+)( lo=)(\d+)(\])")

# Les journaux emploient ces noms pour « personne » : à ne pas pseudonymiser,
# ce ne sont pas des joueurs.
_NON_JOUEURS = {"UNKNOWN", "UNKNOWN HUMAN PLAYER", "The Innkeeper"}


def outbox_dir() -> Path:
    base = os.environ.get("CAIRN_DATA_DIR")
    root = Path(base).expanduser() if base else (
        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "cairn"
    )
    return root / "outbox"


def nouvel_identifiant_installation() -> str:
    """Identifiant aléatoire d'installation — pas de compte, pas d'e-mail.

    Il ne sert qu'à dédupliquer les envois et à honorer une demande de
    suppression : sans lui, « effacez mes données » serait impossible à traiter.
    """
    return str(uuid.uuid4())


@dataclass
class Pseudonymiseur:
    """Remplace les identifiants par des jetons stables dans un même flux.

    ``sel`` rend les jetons imprévisibles d'une installation à l'autre : sans
    lui, un même battletag donnerait le même jeton partout, ce qui permettrait
    de recouper les envois de plusieurs utilisateurs — exactement ce qu'on
    cherche à empêcher.
    """

    sel: str
    _joueurs: dict[str, str] = None  # battletag -> jeton
    _comptes: dict[str, str] = None  # lo -> jeton

    def __post_init__(self) -> None:
        self._joueurs = {}
        self._comptes = {}

    def _jeton(self, valeur: str, largeur: int) -> str:
        empreinte = hashlib.blake2b(
            f"{self.sel}\0{valeur}".encode(), digest_size=8
        ).hexdigest()
        return str(int(empreinte, 16))[:largeur].rjust(largeur, "1")

    def battletag(self, nom: str, numero: str) -> str:
        entier = f"{nom}#{numero}"
        if nom in _NON_JOUEURS:
            return entier
        if entier not in self._joueurs:
            n = len(self._joueurs) + 1
            # forme volontairement identique à un vrai battletag : le parseur
            # et les outils d'analyse n'ont pas à connaître la différence
            self._joueurs[entier] = f"Joueur{n}#{self._jeton(entier, 6)}"
        return self._joueurs[entier]

    def compte(self, lo: str) -> str:
        if lo not in self._comptes:
            self._comptes[lo] = self._jeton(lo, 9)
        return self._comptes[lo]

    def texte(self, contenu: str) -> str:
        contenu = _BATTLETAG.sub(
            lambda m: self.battletag(m.group(1), m.group(2)), contenu
        )
        contenu = self._noms_nus(contenu)
        return _ACCOUNT.sub(
            lambda m: f"{m.group(1)}0{m.group(3)}{self.compte(m.group(4))}{m.group(5)}",
            contenu,
        )

    def _noms_nus(self, contenu: str) -> str:
        """Deuxième passe : le battletag **sans son discriminant**.

        Hearthstone écrit parfois le joueur sans son numéro —
        ``FULL_ENTITY - Updating Deryth CardID=`` — et ces lignes-là
        échappaient au motif principal, qui exige ``nom#1234``. Deux
        occurrences suffisent à identifier quelqu'un : un pseudo est bien plus
        distinctif que son discriminant.

        Faisable seulement APRÈS la première passe, qui apprend les noms. Le
        remplacement est ancré sur des frontières de mot pour ne pas mordre
        dans un nom de carte ou un identifiant plus long.
        """
        for entier, jeton in self._joueurs.items():
            nom = entier.split("#", 1)[0]
            contenu = re.sub(
                rf"(?<![\w#]){re.escape(nom)}(?![\w#])",
                jeton.split("#", 1)[0],
                contenu,
            )
        return contenu

    @property
    def joueurs_remplaces(self) -> int:
        return len(self._joueurs)


def pseudonymiser_fichier(source: Path, cible: Path, sel: str) -> int:
    """Écrit une copie pseudonymisée. Rend le nombre de joueurs remplacés."""
    p = Pseudonymiseur(sel=sel)
    contenu = source.read_text(encoding="utf-8", errors="replace")
    cible.write_text(p.texte(contenu), encoding="utf-8")
    return p.joueurs_remplaces


# LoadingScreen.log distingue construit / arène / Battlegrounds : sans lui,
# impossible d'écarter les modes hors périmètre d'une analyse par rang.
FICHIERS = ("Power.log", "Decks.log", "LoadingScreen.log")


def metadonnees(
    sessions_games: list[dict],
    install_id: str,
    rang: str = "",
    version: str = "",
) -> dict:
    """Ce que le journal ne dit pas et que le destinataire ne peut pas deviner.

    Le RANG en fait partie : Hearthstone ne l'écrit dans AUCUN de ses journaux
    (vérifié sur toutes les sessions — Firestone et HDT le lisent dans la
    mémoire du jeu, cf. le module MindVision du cahier des charges). Il est
    donc déclaré par le joueur, une fois, et voyage ici.

    Le type de partie, lui, est bien dans le journal (``GameType=GT_RANKED``) :
    on le recopie pour qu'une analyse par rang puisse écarter le classique et
    l'arène sans avoir à tout rejouer.
    """
    return {
        "schema": 1,
        "install_id": install_id,
        "prepare_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # toujours vrai : la pseudonymisation n'est plus un réglage (cf.
        # ``preparer``). Le champ reste, il date les envois d'avant.
        "anonymise": True,
        "cairn": version,
        "rang_declare": rang,      # "" si le joueur ne l'a pas renseigné
        "parties": sessions_games,
    }


def preparer(session: Path, sel: str, dest: Path | None = None,
             meta: dict | None = None) -> Path | None:
    """Dépose une session PSEUDONYMISÉE dans l'outbox. Rend son dossier.

    Il n'y a **pas** d'option pour envoyer les journaux bruts, et c'est
    délibéré. Le consentement de l'utilisateur ne couvre que lui : son
    adversaire apparaît dans le même fichier sans avoir rien accepté, et
    l'article 14 du RGPD obligerait alors à l'informer — ce qui est impossible.
    Un réglage « ne pas anonymiser » ne pouvait donc être coché que par erreur.

    Idempotent : une session déjà préparée est simplement remplacée, ce qui
    permet de rappeler la fonction à chaque fin de partie d'une même session.
    """
    if not (session / "Power.log").is_file():
        return None
    dest = (dest or outbox_dir()) / session.name
    dest.mkdir(parents=True, exist_ok=True)
    for nom in FICHIERS:
        src = session / nom
        if not src.is_file():
            continue
        pseudonymiser_fichier(src, dest / nom, sel)
    if meta is not None:
        (dest / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return dest


def taille_outbox(dest: Path | None = None) -> tuple[int, int]:
    """(nombre de sessions en attente, octets occupés)."""
    dest = dest or outbox_dir()
    if not dest.is_dir():
        return (0, 0)
    sessions = [d for d in dest.iterdir() if d.is_dir()]
    octets = sum(f.stat().st_size for d in sessions for f in d.rglob("*") if f.is_file())
    return (len(sessions), octets)


def vider_outbox(dest: Path | None = None) -> int:
    """Supprime tout ce qui attend. Rend le nombre de sessions supprimées."""
    dest = dest or outbox_dir()
    if not dest.is_dir():
        return 0
    n = 0
    for d in list(dest.iterdir()):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            n += 1
    return n
