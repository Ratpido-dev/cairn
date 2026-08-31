"""Listes d'archétypes de référence, collées par l'utilisateur, et appariement.

Pourquoi pas un site. HSGuru refuse explicitement les agents automatiques
(``robots.txt`` : ``User-agent: ClaudeBot / Disallow: /``) et répond 403.
Au-delà du refus, dépendre d'un site tiers serait un mauvais socle : sa
structure change sans préavis, ses listes périment à chaque patch, et Cairn
cesserait de fonctionner le jour où l'un ou l'autre bouge.

Le modèle retenu inverse la charge : **l'utilisateur colle un code de deck**,
Cairn le décode et s'en sert de référence. Ça respecte la source, ça marche
hors ligne, et il choisit quand rafraîchir.

## Pourquoi ça reconnaît plus que les signatures

``archetypes.py`` exige qu'une carte-signature précise ait été JOUÉE — 48 % de
reconnaissance mesurée sur les archives. Ici on compare **toutes** les cartes
vues sortir de son deck à toutes les listes connues de sa classe : sept cartes
banales qui figurent toutes dans la même liste valent une signature.

## Variantes d'un même archétype

Un archétype n'a pas UNE liste : deux joueurs du même deck changent trois
cartes. On empile donc plusieurs listes sous le même nom, et un archétype vaut
sa **meilleure** variante — celle que l'adversaire joue probablement. Prendre
l'union des variantes serait trop permissif (elle grandit à chaque ajout, donc
l'archétype le mieux documenté gagnerait toujours) ; la moyenne, trop sévère.

## Le poids d'une carte : sa rareté entre les ARCHÉTYPES

Une carte présente dans tous les archétypes d'une classe ne dit rien ; une
carte présente dans un seul les départage à elle seule. On pondère donc chaque
carte observée par ``1 / nombre d'archétypes qui la contiennent`` — l'idée de
l'IDF en recherche documentaire.

**Le comptage se fait par archétype, jamais par variante.** La nuance décide de
tout : les cartes communes aux deux variantes d'un même deck sont son cœur,
donc très parlantes. Les compter comme « présentes deux fois » les dévaluerait
exactement à l'inverse de ce qu'elles valent.

## Trois verrous contre les fausses étiquettes

On ne voit qu'une fraction du deck adverse. Une étiquette fausse pollue
durablement les statistiques, alors qu'un « non reconnu » ne coûte rien :

1. **Minimum de cartes vues** — en dessous, aucune méthode ne tranche
   honnêtement.
2. **Score plancher** — une liste doit expliquer une part suffisante de ce
   qu'on a vu.
3. **Marge sur la deuxième** — deux listes à égalité, c'est une ambiguïté, pas
   un gagnant. On préfère ne rien dire.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from .cards_db import CardsDb
from .deckstring import DeckstringError, decode_deckstring

MIN_CARTES_VUES = 4     # en deçà, on ne tranche pas
SCORE_PLANCHER = 0.34   # part pondérée du vu qu'une liste doit expliquer
MARGE_MIN = 0.12        # écart exigé avec la deuxième liste


def default_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "cairn" / "decks_reference.json"


@dataclass
class DeckRef:
    """Une liste d'archétype de référence, telle que l'utilisateur l'a collée."""

    name: str
    klass: str
    card_ids: set[str] = field(default_factory=set)
    deckstring: str = ""

    def as_dict(self) -> dict:
        return {"name": self.name, "class": self.klass,
                "cards": sorted(self.card_ids), "deckstring": self.deckstring}


class DeckRefs:
    """Collection de listes de référence, rangée en JSON à côté de la config."""

    def __init__(self, path: Path | None = None):
        self.path = path or default_path()
        self.refs: list[DeckRef] = []
        self.load()

    # ---- persistance -------------------------------------------------------

    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            brut = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return          # fichier abîmé : on repart vide plutôt que planter
        self.refs = [
            DeckRef(name=d.get("name", ""), klass=d.get("class", ""),
                    card_ids=set(d.get("cards", [])), deckstring=d.get("deckstring", ""))
            for d in brut if isinstance(d, dict) and d.get("name")
        ]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps([r.as_dict() for r in self.refs],
                                  ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)      # écriture atomique : pas de fichier à moitié écrit

    # ---- édition -----------------------------------------------------------

    def add(self, name: str, deckstring: str, db: CardsDb) -> str:
        """Ajoute une liste depuis un code de deck. Rend "" ou un message d'erreur."""
        name = name.strip()
        if not name:
            return "donne un nom à cet archétype"
        try:
            deck = decode_deckstring(deckstring)
        except DeckstringError as err:
            return f"code de deck illisible : {err}"
        cartes, classes = set(), set()
        for dbf, _ in deck.cards:
            c = db.by_dbf_id.get(dbf)
            if not c:
                continue
            cartes.add(c["id"])
            kl = c.get("cardClass")
            if kl and kl != "NEUTRAL":
                classes.add(kl)
        if not cartes:
            return "aucune carte reconnue dans ce code"
        # La classe se déduit des cartes de classe ; un deck n'en a qu'une.
        klass = max(classes, key=lambda k: sum(
            1 for dbf, _ in deck.cards
            if (db.by_dbf_id.get(dbf) or {}).get("cardClass") == k)) if classes else ""
        code = deckstring.strip()
        # Un même archétype a des VARIANTES : deux listes qui ne diffèrent que
        # de trois cartes sont le même deck. On les empile sous le même nom au
        # lieu de s'écraser ; seul un code identique est ignoré (doublon).
        if any(r.name == name and r.deckstring == code for r in self.refs):
            return "cette liste est déjà enregistrée"
        self.refs.append(DeckRef(name=name, klass=klass, card_ids=cartes,
                                 deckstring=code))
        self.save()
        return ""

    # Format d'export de Hearthstone, tel que le rendent les sites de méta :
    #     ### Dragon Pirate Warrior
    #     AAECAQcE6IcH...
    #     ### You can view this deck at https://...
    # Le nom est DANS le collage : redemander de le saisir serait absurde, et
    # ingérable pour huit listes d'affilée.
    _TITRE = re.compile(r"^###\s*(?!You can view)(.+?)\s*$", re.M)
    _CODE = re.compile(r"^\s*(AAE[A-Za-z0-9+/=]{20,})\s*$", re.M)

    @classmethod
    def parse_paste(cls, texte: str) -> list[tuple[str, str]]:
        """[(nom, code), …] extraits d'un collage, une ou plusieurs listes.

        On apparie chaque code au dernier titre rencontré au-dessus de lui : les
        exports intercalent une ligne « ### You can view this deck at… » qu'il
        faut ignorer, d'où le filtre dans l'expression.
        """
        trouves: list[tuple[str, str]] = []
        titre = ""
        for ligne in texte.splitlines():
            t = cls._TITRE.match(ligne.strip())
            if t:
                titre = t.group(1).strip()
                continue
            c = cls._CODE.match(ligne)
            if c:
                trouves.append((titre, c.group(1)))
        return trouves

    def add_paste(self, texte: str, db: CardsDb, defaut: str = "") -> tuple[int, str]:
        """Ajoute toutes les listes d'un collage. Rend (ajoutées, message)."""
        listes = self.parse_paste(texte)
        if not listes:
            # collage d'un code nu, sans en-tête : le nom saisi fait foi
            code = texte.strip()
            if code:
                err = self.add(defaut, code, db)
                return (0, err) if err else (1, "")
            return 0, "aucun code de deck trouvé dans ce collage"
        ajoutees, erreurs = 0, []
        for nom, code in listes:
            err = self.add(nom or defaut, code, db)
            if err and "déjà" not in err:
                erreurs.append(f"{nom or '?'} : {err}")
            elif not err:
                ajoutees += 1
        return ajoutees, " · ".join(erreurs[:2])

    def remove(self, name: str) -> None:
        self.refs = [r for r in self.refs if r.name != name]
        self.save()

    def variants(self, name: str) -> int:
        return sum(1 for r in self.refs if r.name == name)

    def archetype_names(self) -> list[tuple[str, str, int, int]]:
        """[(nom, classe, variantes, cartes distinctes)] — une ligne par archétype."""
        par: dict[str, list[DeckRef]] = {}
        for r in self.refs:
            par.setdefault(r.name, []).append(r)
        return sorted(
            (nom, v[0].klass, len(v), len(set().union(*(x.card_ids for x in v))))
            for nom, v in par.items()
        )

    def for_class(self, klass: str | None) -> list[DeckRef]:
        return [r for r in self.refs if klass and r.klass == klass]

    # ---- appariement -------------------------------------------------------

    def exclusives(self, klass: str | None, db: CardsDb) -> dict[str, str]:
        """card_id → archétype, pour les cartes propres à UN SEUL archétype.

        Sert à EXPLIQUER pourquoi un deck a été reconnu (« il a joué Suivre les
        fantômes »), pas à le reconnaître : le score s'en charge déjà, puisque
        ces cartes y pèsent 1,0 par construction.

        **Restreint aux cartes de CLASSE.** Une neutre exclusive dans nos listes
        ne l'est pas dans le méta : « Rat déloyal » ressort propre à Control
        Priest alors que n'importe qui peut la jouer.
        """
        par: dict[str, set[str]] = {}
        for r in self.for_class(klass):
            par.setdefault(r.name, set()).update(r.card_ids)
        if len(par) < 2:
            return {}
        excl: dict[str, str] = {}
        for nom, cartes in par.items():
            autres = set().union(*(c for n, c in par.items() if n != nom))
            for cid in cartes - autres:
                carte = db.by_card_id.get(cid)
                if carte and carte.get("cardClass") == klass:
                    excl[cid] = nom
        return excl

    def match(self, vues: set[str], klass: str | None,
              db: CardsDb | None = None) -> tuple[str, float]:
        """Meilleure liste pour les cartes observées. Rend ("", 0.0) si on doute.

        ``vues`` : cartes que l'adversaire a jouées ET qui venaient de son deck
        (cf. ``archetypes.deck_card_ids``) — une carte volée ne prouve rien.
        """
        listes = self.for_class(klass)
        if not listes or len(vues) < MIN_CARTES_VUES:
            return "", 0.0

        # Pas de règle spéciale « carte exclusive » ici, et c'est délibéré : elle
        # a été écrite, mesurée, puis RETIRÉE. Sur 400 tirages par archétype elle
        # se déclenchait 19 % du temps et ne changeait pas un seul verdict — la
        # pondération plus bas lui donne déjà un poids de 1,0 (présente dans un
        # seul archétype), donc le score la nomme tout seul. ``exclusives()``
        # reste exposée : elle sert à EXPLIQUER un verdict, pas à le produire.

        # variantes regroupées par archétype
        par_nom: dict[str, list[DeckRef]] = {}
        for r in listes:
            par_nom.setdefault(r.name, []).append(r)

        # Poids d'une carte = son pouvoir de discrimination entre ARCHÉTYPES,
        # pas entre variantes. La nuance est décisive : les cartes communes aux
        # deux variantes d'un même deck sont son cœur, donc très parlantes —
        # les compter comme « présentes deux fois » les dévaluerait à tort.
        union = {nom: set().union(*(r.card_ids for r in v))
                 for nom, v in par_nom.items()}
        poids: dict[str, float] = {}
        for cid in vues:
            presence = sum(1 for cartes in union.values() if cid in cartes)
            poids[cid] = 1.0 / presence if presence else 0.0
        total = sum(poids.values())
        if total <= 0:
            return "", 0.0      # rien de vu n'appartient à aucune liste connue

        # Un archétype vaut sa MEILLEURE variante : c'est celle que l'adversaire
        # joue probablement. Prendre l'union serait trop permissif (elle grandit
        # à chaque variante ajoutée), la moyenne trop sévère.
        scores = sorted(
            (
                (max(sum(poids[c] for c in vues if c in r.card_ids) / total
                     for r in variantes), nom)
                for nom, variantes in par_nom.items()
            ),
            reverse=True,
        )
        meilleur, nom = scores[0]
        second = scores[1][0] if len(scores) > 1 else 0.0
        if meilleur >= SCORE_PLANCHER and (meilleur - second) >= MARGE_MIN:
            return nom, meilleur

        # Rattrapage par CONTENANCE. Mesuré sur les vraies parties : quinze
        # cartes vues, les quinze présentes dans « Control Priest » et treize
        # dans « Quest Priest » — la marge refusait, alors que la réponse est
        # évidente. Un deck qui contient TOUT ce qu'on a vu, quand aucun autre
        # n'y arrive, est le bon même si les scores sont proches.
        #
        # C'est plus sûr que d'abaisser la marge : on n'accepte pas « presque
        # autant », on exige une couverture ENTIÈRE et unique.
        entiers = [
            nom_a for nom_a, cartes in
            ((n, set().union(*(r.card_ids for r in v))) for n, v in par_nom.items())
            if vues <= cartes
        ]
        if len(entiers) == 1:
            return entiers[0], meilleur
        return "", meilleur     # trop faible, ambigu, ou plusieurs contenances
