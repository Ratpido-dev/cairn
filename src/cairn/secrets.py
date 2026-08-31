"""Secrets adverses : combien sont posés, et lesquels c'est encore possible.

Hearthstone ne révèle un secret qu'au moment où il se déclenche. Le tracker
affiche donc les **candidats** : tous les secrets de la classe adverse légaux
dans le format en cours, moins ceux dont on a déjà vu toutes les copies partir.

Élimination automatique : faite, mais **volontairement partielle**. Écarter à
tort un bon candidat est pire que ne rien écarter — on jouerait *dans* le
secret. Trois garde-fous, tous nécessaires :

1. seuls les déclencheurs **inconditionnels et observables dans les journaux**
   comptent (cf. ``_TRIGGERS``) ; tout ce qui dépend d'une attaque est hors
   de portée, le moteur ne suit pas les attaques ;
2. on n'élimine que si l'adversaire a **exactement un secret en jeu** — avec
   deux secrets, HS en déclenche un et laisse l'autre, donc l'absence de
   déclenchement ne prouve rien ;
3. on ne regarde que les coups joués **après la pose** du secret courant.

Le candidat écarté est grisé, pas supprimé, et le barrage manuel d'un clic
reste disponible : la déduction du joueur prime toujours sur la nôtre.
"""

from __future__ import annotations

from dataclasses import dataclass

from .cards_db import CardsDb
from .game_state import Game, Play

# Extensions légales en Standard. Déduites des parties réelles d'août 2026 —
# **à mettre à jour à chaque rotation** (une par an, au printemps).
STANDARD_SETS = frozenset(
    {
        "CORE",
        "THE_LOST_CITY",
        "CATACLYSM",
        "TIME_TRAVEL",
        "EMERALD_DREAM",
        "ESCAPEFROM_VIOLET_HOLD",
    }
)

# La zone SECRET accueille aussi les quêtes et les sigils : on ne compte que
# les cartes réellement marquées « Secret ».
_SECRET_ZONE = "SECRET"


# Déclencheurs qu'on sait observer. Une carte ABSENTE de cette table n'est
# jamais éliminée automatiquement — c'est le sens par défaut, et il est sûr.
#
#   "spell"       l'adversaire (= nous) a lancé un sort
#   "minion"      … a joué un serviteur
#   "three_cards" … a joué trois cartes dans le même tour
#   "turn_end"    notre tour s'est terminé
#
# Volontairement absents : tous les pièges liés à une ATTAQUE (Piège explosif,
# Piège givrant, Barrière de glace, Allié de l'oasis, Détournement mystique) —
# le moteur ne journalise pas les attaques. Et Plaque de pression, qui exige un
# serviteur à détruire : sans plateau elle ne part pas, l'éliminer serait faux.
_TRIGGERS: dict[str, str] = {
    "CORE_EX1_287": "spell",        # Contresort — contre le sort, sans condition
    "CORE_LOOT_101": "minion",      # Runes explosives — dès un serviteur posé
    "CORE_GIL_577": "three_cards",  # Piège à rat — 3 cartes dans le tour
    "END_024": "turn_end",          # Flammes de l'infini — fin de notre tour
}


@dataclass
class SecretCandidate:
    name: str
    cost: int
    card_id: str
    ruled_out: bool = False  # écarté par déduction (grisé, pas supprimé)
    card_class: str = ""     # classe du secret — deux classes peuvent coexister


def secret_card_ids(db: CardsDb) -> set[str]:
    return db.secret_ids


def secrets_in_play(game: Game, db: CardsDb, player_id: int | None) -> int:
    """Nombre de secrets actuellement actifs chez un joueur."""
    if player_id is None:
        return 0
    return sum(
        1
        for e in game.entities.values()
        if e.zone == _SECRET_ZONE
        and e.controller == player_id
        and (e.card_id is None or db.is_secret(e.card_id))
    )


def secret_classes_in_play(
    game: Game, db: CardsDb, player_id: int | None
) -> list[str]:
    """Classes des secrets RÉELLEMENT posés chez un joueur.

    Un secret n'appartient pas forcément à la classe de celui qui le pose :
    Découverte, vol, génération aléatoire… Vu en partie le 10/08/2026 — un
    Chasseur pose un secret de Mage, et le tracker proposait les cinq secrets
    de Chasseur, c'est-à-dire cinq mauvaises réponses.

    Hearthstone le dit lui-même : l'entité posée en zone SECRET porte un tag
    ``CLASS`` même quand son identité reste cachée — c'est ce qui permet au
    jeu d'afficher le bandeau « Secret de mage » sans révéler la carte.
    """
    if player_id is None:
        return []
    classes = []
    for e in game.entities.values():
        if e.zone != _SECRET_ZONE or e.controller != player_id:
            continue
        if e.tags.get("QUEST") == "1" or e.tags.get("SIDEQUEST") == "1":
            continue  # la zone SECRET accueille aussi les quêtes
        if e.card_id and not db.is_secret(e.card_id):
            continue
        card = db.by_card_id.get(e.card_id or "")
        klass = (card or {}).get("cardClass") or e.tags.get("CLASS")
        if klass and klass != "NEUTRAL":
            classes.append(klass)
    return sorted(set(classes))


def _revealed(game: Game, db: CardsDb, player_id: int) -> dict[str, int]:
    """Secrets déjà dévoilés (déclenchés ou détruits) et leur nombre."""
    seen: dict[str, int] = {}
    for e in game.entities.values():
        if (
            e.controller == player_id
            and e.card_id
            and db.is_secret(e.card_id)
            and e.zone in ("GRAVEYARD", "REMOVEDFROMGAME")
        ):
            seen[e.card_id] = seen.get(e.card_id, 0) + 1
    return seen


def _observed_triggers(game: Game, db: CardsDb, player_id: int) -> set[str]:
    """Déclencheurs survenus DEPUIS la pose du secret courant, sans effet.

    Vide dès que l'adversaire a plus d'un secret en jeu : avec deux secrets, HS
    en déclenche un seul et laisse l'autre, donc rien ne se déduit.
    """
    if secrets_in_play(game, db, player_id) != 1:
        return set()

    # tour où le secret courant a été posé : sa dernière mise en place
    poses = [
        ev.turn for ev in game.events
        if isinstance(ev, Play) and ev.player_id == player_id
        and game.entities.get(ev.entity_id) is not None
        and game.entities[ev.entity_id].zone == _SECRET_ZONE
    ]
    if not poses:
        return set()
    depuis = max(poses)

    local = game.local_player_id()
    if local is None:
        return set()

    vus: set[str] = set()
    par_tour: dict[int, int] = {}
    for ev in game.events:
        if not isinstance(ev, Play) or ev.player_id != local or ev.turn < depuis:
            continue
        # le tour de la pose ne compte pas : le secret arrive APRÈS nos coups
        if ev.turn == depuis:
            continue
        par_tour[ev.turn] = par_tour.get(ev.turn, 0) + 1
        type_ = (db.by_card_id.get(ev.card_id or "") or {}).get("type")
        if type_ == "SPELL":
            vus.add("spell")
        elif type_ == "MINION":
            vus.add("minion")
    if any(n >= 3 for n in par_tour.values()):
        vus.add("three_cards")
    # un de nos tours s'est terminé après la pose : TURN a avancé de deux crans
    if game.turns >= depuis + 2:
        vus.add("turn_end")
    return vus


def candidates(
    game: Game, db: CardsDb, player_id: int | None, klass: str | None
) -> list[SecretCandidate]:
    """Secrets encore possibles chez l'adversaire, du moins cher au plus cher.

    Les candidats sont ceux de la CLASSE DU SECRET POSÉ (lue sur l'entité, cf.
    ``secret_classes_in_play``), pas ceux de la classe du héros adverse : un
    Chasseur qui pose un secret de Mage doit faire proposer les secrets de
    Mage. Repli sur la classe du héros tant que le jeu n'a pas publié le tag,
    puis sur toutes les classes s'il n'en reste rien.

    Rendu vide s'il n'a aucun secret en jeu : inutile d'encombrer l'écran.
    """
    if player_id is None or secrets_in_play(game, db, player_id) == 0:
        return []

    standard = game.format_type == "FT_STANDARD"
    already = _revealed(game, db, player_id)
    posees = secret_classes_in_play(game, db, player_id)
    if not posees:
        posees = [klass] if klass else []

    def legal(card: dict | None) -> bool:
        return card is not None and (
            not standard or card.get("set") in STANDARD_SETS
        )

    # Trois cas, du plus précis au plus large :
    #   — la classe a des secrets légaux dans le format (Chasseur, Mage en août
    #     2026) : on filtre sur le format, c'est la liste exacte ;
    #   — elle a des secrets mais aucun légal (Paladin, Voleur aujourd'hui) :
    #     le secret vient forcément d'ailleurs (génération aléatoire), donc on
    #     ouvre à tous les sets plutôt que de ne rien proposer ;
    #   — elle n'a aucun secret du tout (Chasseur de démons, ou classe encore
    #     inconnue) : on propose tous ceux du format. Onze candidats valent
    #     mieux qu'aucun quand le secret, lui, est bien là.
    avec_secrets = {
        k for k in posees
        if any((db.by_card_id.get(cid) or {}).get("cardClass") == k
               for cid in db.secret_ids)
    }
    strictes = {
        k for k in avec_secrets
        if any(
            (db.by_card_id.get(cid) or {}).get("cardClass") == k
            and legal(db.by_card_id.get(cid))
            for cid in db.secret_ids
        )
    }
    retenues = avec_secrets
    toutes_classes = not retenues
    declencheurs = _observed_triggers(game, db, player_id)
    out = []
    for card_id in db.secret_ids:
        card = db.by_card_id.get(card_id)
        if card is None:
            continue
        klass_carte = card.get("cardClass")
        if not toutes_classes and klass_carte not in retenues:
            continue
        if (toutes_classes or klass_carte in strictes) and not legal(card):
            continue
        if already.get(card_id, 0) >= 2:  # les deux exemplaires sont partis
            continue
        out.append(
            SecretCandidate(
                name=card.get("name", card_id),
                cost=card.get("cost", 0) or 0,
                card_id=card_id,
                ruled_out=_TRIGGERS.get(card_id, "") in declencheurs
                and card_id in _TRIGGERS,
                card_class=card.get("cardClass", ""),
            )
        )
    # les écartés descendent en bas de liste : ce qui reste possible d'abord ;
    # à plusieurs classes, chacune reste groupée
    return sorted(out, key=lambda c: (c.ruled_out, c.card_class, c.cost, c.name))
