"""Vue du deck local pour l'UI : une fonction pure, recalculée à chaque poll.

Plutôt qu'un état incrémental fragile (les événements peuvent arriver avant
que le joueur local soit identifiable), on dérive TOUT de ``(Game, deck,
CardsDb)`` à chaque rafraîchissement — une partie fait quelques centaines
d'événements, le recalcul est négligeable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import atlas
from .atlas import AtlasCard
from .cards_db import CardsDb
from .decks_log import PlayerDeck, QueueEvent
from .effects import Effect, global_effects
from .deckstring import DeckstringError, decode_deckstring
from .game_state import (
    DECK,
    Death,
    DeckEntry,
    DeckLeave,
    Draw,
    Entity,
    Game,
    Play,
    round_number,
)
from .i18n import t


@dataclass
class CardRow:
    dbf_id: int
    name: str
    cost: int
    total: int
    remaining: int
    card_id: str = ""  # pour l'aperçu au survol
    rarity: str = ""  # COMMON/RARE/EPIC/LEGENDARY — code couleur du panneau
    # Carte ARRIVÉE en cours de partie (copie, cadeau, bombe…). Elle s'affiche
    # dans la liste du deck avec une icône de cadeau plutôt que dans une section
    # à part : c'est bien dans le deck qu'elle est, et c'est là qu'on la cherche
    # au moment de compter ce qu'il reste à piocher.
    gift: bool = False
    origin: str = ""  # carte qui l'a créée (« ← Azalina »), vide sinon


CLASS_FR = {
    "DEATHKNIGHT": "Chevalier de la mort", "DEMONHUNTER": "Chasseur de démons",
    "DRUID": "Druide", "HUNTER": "Chasseur", "MAGE": "Mage", "PALADIN": "Paladin",
    "PRIEST": "Prêtre", "ROGUE": "Voleur", "SHAMAN": "Chaman",
    "WARLOCK": "Démoniste", "WARRIOR": "Guerrier",
}


def player_class(game: Game, db: CardsDb, player_id: int | None) -> str | None:
    """Classe du héros d'un camp (« ROGUE »…), dès qu'elle est connue."""
    hero = game.hero_card_id(player_id) if player_id is not None else None
    card = db.by_card_id.get(hero or "")
    return card.get("cardClass") if card else None


def opponent_class(game: Game, db: CardsDb) -> str | None:
    """Classe du héros adverse (« ROGUE »…), dès qu'elle est connue."""
    local = game.local_player_id()
    if local is None:
        return None
    return player_class(game, db, next((p for p in game.player_names if p != local), None))


# « Confrontation des Tol'vir » (Chasseur) invoque tous les SERVITEURS à
# 1 cristal joués depuis le début de la partie. Sa valeur se construit dix tours
# avant qu'elle ne soit posée : quand elle tombe, il est déjà trop tard pour en
# tenir compte. D'où une liste tenue en permanence, des deux côtés.
#
# Le patch du 18/08/2026 l'a réécrite : elle « rejouait chaque CARTE à (1) », elle
# « invoque chaque SERVITEUR à (1) ». Les sorts et les armes ne comptent donc
# plus — d'où ``TOLVIR_TYPES``. Sans ce filtre le compteur surévalue la menace,
# et c'est le pire sens de l'erreur : on joue autour d'un rejeu qui n'arrivera pas.
TOLVIR = "CATA_560"
TOLVIR_COST = 1
TOLVIR_TYPES = ("MINION",)


def _tolvir_relevant(game: Game, db: CardsDb, player_id: int | None, rows) -> bool:
    """Faut-il tenir la liste des cartes à 1 cristal pour ce camp ?

    Deux façons d'en avoir une : jouer Chasseur (c'est sa carte, et la question
    se pose AVANT qu'elle soit posée — c'est tout l'intérêt), ou l'avoir
    obtenue autrement (Découverte, vol, Azalina), auquel cas on l'a vue passer.
    """
    if player_id is None:
        return False
    if player_class(game, db, player_id) == "HUNTER":
        return True
    if any(r.card_id == TOLVIR for r in rows):
        return True
    return any(
        e.card_id == TOLVIR and e.controller == player_id
        for e in game.entities.values()
    )


def plays_costing(
    game: Game, db: CardsDb, player_id: int | None, cost: int, since: int = 0,
    types: tuple[str, ...] | None = None,
) -> list["ZoneCard"]:
    """Cartes d'un coût donné jouées par un camp, dans l'ordre, groupées.

    ``types`` restreint aux types de cartes voulus (« MINION »…). Les deux
    cartes qui utilisent cette liste ne comptent PAS la même chose : la Fauteuse
    de troubles tire sur toutes les cartes à (2), la Confrontation des Tol'vir
    n'invoque que les serviteurs à (1). Un filtre par défaut serait faux dans un
    cas comme dans l'autre.

    **Le coût compté est celui IMPRIMÉ sur la carte, pas celui payé** — c'est
    contre-intuitif, et c'est mesuré. Sur la partie du 02/08 12:07 le jeu a
    tiré 6 projectiles de Fauteuse de troubles, soit exactement 1 + les 5
    cartes à (2) de la base de cartes : un « Fouet de Patte Noire » imprimé à
    (3) et joué pour 2 n'a PAS compté, un « Rite du Crépuscule » imprimé à (2)
    et joué pour 0 a compté. Compter le coût réellement payé
    (``TAG_LAST_KNOWN_COST_IN_HAND``) donnerait 7, et serait faux.

    ``since`` : tour à partir duquel compter, pour les cartes qui ne comptent
    que depuis leur arrivée (cf. ``counters._troublemaker_since``).
    """
    if player_id is None:
        return []
    rows = []
    for ev in game.events:
        if not isinstance(ev, Play) or ev.player_id != player_id or not ev.card_id:
            continue
        if ev.turn < since:
            continue
        if ((db.by_card_id.get(ev.card_id) or {}).get("cost") or 0) != cost:
            continue
        card = db.by_card_id.get(ev.card_id)
        if card is None:
            continue
        if types is not None and card.get("type") not in types:
            continue
        rows.append(
            ZoneCard(
                label=card.get("name", ev.card_id),
                origin="",
                cost=cost,
                card_id=ev.card_id,
                rarity=card.get("rarity", ""),
            )
        )
    return _group(rows, key=lambda r: r.card_id)


@dataclass
class EntryRow:
    """Cartes actuellement DANS le deck, arrivées en cours de partie (groupées)."""

    label: str  # nom de la carte, ou "?" si cachée
    origin: str  # nom de la carte créatrice ("" si inconnu)
    known: bool
    count: int = 1
    card_id: str = ""  # pour l'aperçu au survol
    rarity: str = ""
    # "" | "bottom" | "top" — bout du deck où l'effet créateur l'a posée
    pos: str = ""


@dataclass
class OppPlay:
    label: str
    count: int
    cost: int = 0
    card_id: str = ""  # pour l'aperçu au survol
    rarity: str = ""
    # D'OÙ vient la carte qu'il vient de jouer : nom de la carte qui la lui a
    # donnée, "" si elle sortait simplement de son deck. Sans ça, un adversaire
    # qui enchaîne dix cartes grâce à Azalina, une Découverte ou un vol se lit
    # comme un deck de dix cartes qu'il n'a jamais eu — c'est la différence
    # entre « il lui en reste » et « il ne lui en reste plus ».
    origin: str = ""
    created: bool = False  # vrai dès qu'un effet l'a engendrée


@dataclass
class OppHandCard:
    """Carte CONNUE dans la main adverse : découverte, créée par un effet, ou
    renvoyée en main après avoir été vue. C'est l'information que les autres
    trackers mettent en avant — savoir *ce qu'il tient*, pas seulement combien."""

    label: str
    origin: str  # carte qui l'a créée ("" si simplement révélée)
    count: int = 1
    cost: int = 0
    card_id: str = ""
    rarity: str = ""


@dataclass
class OppHandSlot:
    """UNE carte de la main adverse, connue ou non, avec ce qu'on sait d'elle.

    Complète ``OppHandCard`` (qui ne liste que l'identité des cartes révélées)
    en gardant une ligne par carte tenue, dans l'ordre de la main. On y met les
    deux informations qui se déduisent des journaux même quand la carte reste
    cachée : le tour où elle est arrivée, et l'effet qui l'a produite. Savoir
    « il tient depuis le tour 1 une carte qu'il n'a pas jouée » ou « il a pioché
    quelque chose grâce à Azalina » suffit souvent à décider — c'est ce que
    Firestone affiche en pastille sous chaque carte adverse.
    """

    label: str  # nom de la carte, ou "?" si cachée
    known: bool
    origin: str = ""  # carte créatrice ("" si inconnue ou venue du deck)
    creator_card_id: str = ""  # id de la créatrice, pour l'aperçu au survol
    cost: int = 0  # -1 quand la carte est cachée : le coût l'est aussi
    card_id: str = ""
    rarity: str = ""
    turn: int | None = None  # manche d'arrivée en main, telle que le joueur la compte
    from_mulligan: bool = False  # arrivée par la main de départ
    # Rang dans SON éventail (tag ZONE_POSITION, 1 = la plus à gauche). C'est
    # ce qui permet de poser une pastille sous CHAQUE carte, dans le bon ordre.
    pos: int = 0


@dataclass
class ZoneCard:
    """Carte du joueur local repérée par sa zone — aujourd'hui : sa main.

    Dérivée des zones plutôt que des événements : c'est la même vérité que le
    compte du dos du deck, exacte même après une transformation ou un vol.

    Une section « ailleurs » (tout ce qui a quitté le deck) a existé et a été
    RETIRÉE : elle mélangeait le héros du joueur, ses jetons de Préparation et
    ses sorts déjà lancés, sans qu'on sache quoi en faire. Le cimetière et le
    plateau disent déjà ce qui compte.
    """

    label: str
    origin: str  # carte qui l'a créée ("" si elle vient du deck)
    count: int = 1
    cost: int = 0
    card_id: str = ""
    rarity: str = ""
    struck: bool = False  # a quitté la zone d'où on la connaissait (deck adverse)


@dataclass
class DeadMinion:
    """Serviteur mort — cimetière, et vivier des effets de résurrection."""

    label: str
    count: int = 1
    cost: int = 0
    card_id: str = ""
    rarity: str = ""


@dataclass
class DeckView:
    deck_name: str = ""
    rows: list[CardRow] = field(default_factory=list)
    entries: list[EntryRow] = field(default_factory=list)
    # Entrées dont on connaît le bout du deck. Hearthstone ne publie pas l'ordre
    # du deck de façon exploitable : la position n'est connue que par l'effet
    # qui l'a posée, et elle reste vraie tant qu'aucun mélange n'intervient —
    # même limite que chez HDT et Firestone.
    deck_bottom: list[EntryRow] = field(default_factory=list)
    deck_top: list[EntryRow] = field(default_factory=list)
    opponent_plays: list[OppPlay] = field(default_factory=list)
    opponent_hand: list[OppHandCard] = field(default_factory=list)
    # une ligne par carte tenue par l'adversaire, cachée comprise
    opponent_hand_slots: list[OppHandSlot] = field(default_factory=list)
    my_hand: list[ZoneCard] = field(default_factory=list)
    # effets globaux actifs (Protection d'Amara, Atlas…), par camp
    my_effects: list[Effect] = field(default_factory=list)
    opp_effects: list[Effect] = field(default_factory=list)
    # Cartes à 1 cristal déjà jouées — ce que rejouerait une « Confrontation
    # des Tol'vir ». Remplies seulement quand le camp peut en avoir une
    # (Chasseur, ou carte déjà vue chez lui), sinon la section reste muette.
    my_replay: list[ZoneCard] = field(default_factory=list)
    opp_replay: list[ZoneCard] = field(default_factory=list)
    # Cartes de son deck dont un effet a révélé l'identité. Rare (0 à 4 par
    # partie sur le corpus) mais décisif quand ça arrive : savoir qu'il lui
    # reste SA carte clé change tout le plan de fin de partie.
    opp_deck_known: list[ZoneCard] = field(default_factory=list)
    my_graveyard: list[DeadMinion] = field(default_factory=list)
    opp_graveyard: list[DeadMinion] = field(default_factory=list)
    # files de l'Atlas de Godfrey, dans l'ordre de retour en main
    my_atlas: list[AtlasCard] = field(default_factory=list)
    opp_atlas: list[AtlasCard] = field(default_factory=list)
    opponent_name: str = ""
    remaining_total: int = 0
    result: str = ""  # "", "WON", "LOST", "TIED"


def pick_queued_deck(queue_events: list[QueueEvent], game: Game) -> PlayerDeck | None:
    """Le deck joué = dernière mise en file avant le CREATE_GAME de la partie.

    Comparaison sur HH:MM:SS (même journée) ; si l'horodatage manque ou si la
    partie précède toute mise en file connue, on prend la dernière connue.
    """
    if not queue_events:
        return None
    if game.ts is None:
        return queue_events[-1].deck
    before = [q for q in queue_events if q.ts <= game.ts]
    return (before[-1] if before else queue_events[-1]).deck


def _group(rows: list, key=lambda r: (r.card_id, getattr(r, "origin", ""))) -> list:
    """Regroupe des lignes identiques en incrémentant leur compteur."""
    grouped: dict = {}
    for row in rows:
        k = key(row)
        if k in grouped:
            grouped[k].count += 1
        else:
            grouped[k] = row
    return list(grouped.values())


def _int_tag(ent: Entity, tag: str, default: int = 0) -> int:
    raw = ent.tags.get(tag)
    return int(raw) if raw is not None and raw.lstrip("-").isdigit() else default


def _creator_card_id(game: Game, entity_id: int) -> str:
    """Carte créatrice d'une entité, relue dans l'état courant.

    À refaire ici plutôt qu'à se fier au champ figé de l'événement : HS ne pose
    ``CREATOR`` qu'au moment où la carte est révélée, souvent longtemps après
    son entrée en jeu ou dans le deck. Comme la vue est recalculée à chaque
    poll, une origine qui arrive en retard finit par s'afficher.
    """
    ent = game.entities.get(entity_id)
    creator = game.entities.get(ent.creator_entity_id or -1) if ent else None
    return (creator.card_id or "") if creator else ""


def _live_card_id(game: Game, entity_id: int, fallback: str | None) -> str:
    """Identité courante d'une entité, à défaut celle vue à l'événement.

    Même raison que ``_creator_card_id`` : une carte engendrée dans le deck
    arrive sans identité, et HS ne la publie qu'après coup (SHOW_ENTITY). Sans
    cette relecture, un Sbire du gang des diablotins laisse « ? » au fond du
    deck alors que le journal dit « Grand-mère diablotin ».
    """
    ent = game.entities.get(entity_id)
    return (ent.card_id if ent and ent.card_id else fallback) or ""


def _opponent_coin_entity(game: Game, opp_id: int | None) -> int | None:
    """Entité de la pièce dans la main adverse — par déduction, pas par lecture.

    Hearthstone ne révèle jamais l'identité des cartes de la main adverse, la
    pièce comprise. Mais elle est distribuée à celui qui joue EN SECOND, et
    elle arrive après le mulligan : c'est donc la dernière carte de sa main de
    départ. Firestone l'affiche pour la même raison. On s'abstient dès qu'une
    pièce a déjà été jouée, et dès que le premier joueur n'est pas connu.
    """
    if opp_id is None:
        return None
    premier = next(
        (pid for pid, eid in game.player_entity.items()
         if (game.entities.get(eid) or Entity(0)).tags.get("FIRST_PLAYER") == "1"),
        None,
    )
    if premier is None or premier == opp_id:
        return None  # premier joueur, ou départ inconnu : pas de pièce
    for ent in game.entities.values():
        if ent.controller == opp_id and ent.tags.get("COIN_CARD") == "1":
            return None  # sa pièce est déjà sortie
    depart = [
        e for e in game.entities.values()
        if e.controller == opp_id and e.zone == "HAND" and e.hand_from_mulligan
    ]
    return max(depart, key=lambda e: e.entity_id).entity_id if depart else None


def _opponent_hand_slots(game: Game, db: CardsDb, local: int) -> list[OppHandSlot]:
    """Toute la main adverse, une ligne par carte, cachées comprises."""
    opp_id = next((p for p in game.player_names if p != local), None)
    piece = _opponent_coin_entity(game, opp_id)
    # Ce que son atlas de Godfrey a montré reste connu une fois la carte
    # revenue en main : HS cache l'entité réelle, mais la copie révélée de
    # l'atlas la nomme toujours (cf. atlas.revealed).
    par_atlas = atlas.revealed(game, opp_id)
    slots = []
    for ent in game.entities.values():
        if ent.zone != "HAND" or ent.controller in (None, local):
            continue
        card_id = ent.card_id or par_atlas.get(ent.entity_id, "")
        card = db.by_card_id.get(card_id)
        creator_id = _creator_card_id(game, ent.entity_id)
        creator = db.by_card_id.get(creator_id)
        if card is None and ent.entity_id == piece:
            card = {"name": t("the_coin", "fr"), "cost": 0, "rarity": ""}
        slots.append(
            OppHandSlot(
                label=card["name"] if card else "?",
                known=card is not None,
                origin=creator["name"] if creator else "",
                creator_card_id=creator_id if creator else "",
                cost=(card.get("cost", 0) or 0) if card else -1,
                card_id=card_id,
                rarity=(card.get("rarity", "") if card else ""),
                turn=None if ent.hand_turn is None else round_number(ent.hand_turn),
                from_mulligan=ent.hand_from_mulligan,
                pos=_int_tag(ent, "ZONE_POSITION"),
            )
        )
    # Tri sur la POSITION DANS SA MAIN : les pastilles se posent sous son
    # éventail, une par carte, et l'ordre doit donc être le sien. Repli
    # chronologique (puis le nom, pour que l'ordre soit stable d'un poll à
    # l'autre) quand HS n'a pas encore publié la position.
    slots.sort(key=lambda s: (s.pos or 99, s.turn if s.turn is not None else -1, s.label))
    return slots


def _known_opponent_hand(game: Game, db: CardsDb, local: int) -> list[OppHandCard]:
    """Cartes de la main adverse dont on connaît l'identité.

    HS ne révèle l'id que dans certains cas (carte créée, découverte, ou
    renvoyée en main après avoir été vue) — c'est précisément ce qu'un joueur
    ne peut pas retenir de tête sur une longue partie.
    """
    opp_id = next((p for p in game.player_names if p != local), None)
    par_atlas = atlas.revealed(game, opp_id)
    rows = []
    for ent in game.entities.values():
        if ent.zone != "HAND" or ent.controller in (None, local):
            continue
        # une surpioche de son atlas est cachée par HS, mais la copie révélée
        # de l'atlas continue de la nommer
        card_id = ent.card_id or par_atlas.get(ent.entity_id, "")
        if not card_id:
            continue
        card = db.by_card_id.get(card_id)
        if card is None:
            continue
        creator_card = db.by_card_id.get(_creator_card_id(game, ent.entity_id))
        rows.append(
            OppHandCard(
                label=card.get("name", card_id),
                origin=creator_card["name"] if creator_card else "",
                cost=card.get("cost", 0) or 0,
                card_id=card_id,
                rarity=card.get("rarity", ""),
            )
        )
    return sorted(_group(rows), key=lambda r: (r.cost, r.label))



def _revealed_deck(game: Game, db: CardsDb, player_id: int | None) -> list[ZoneCard]:
    """Cartes dont on a vu l'identité dans le deck d'un camp, jouées comprises.

    On liste les entités marquées ``revealed_in_deck`` plutôt que le contenu
    courant de la zone DECK. La différence est tout l'intérêt de la section :
    une carte révélée puis jouée reste affichée, barrée. Auparavant elle
    s'effaçait à la seconde où l'adversaire la posait, donc au moment où elle
    devenait utile à savoir.

    Le regroupement inclut ``struck`` : deux exemplaires dont un seul a été
    joué se lisent sur deux lignes, une barrée et une non — sinon le compteur
    mentirait sur ce qui dort encore dans le deck.
    """
    if player_id is None:
        return []
    rows = []
    for ent in game.entities.values():
        if not ent.revealed_in_deck or ent.controller != player_id or not ent.card_id:
            continue
        card = db.by_card_id.get(ent.card_id)
        if card is None or card.get("type") == "HERO_POWER":
            continue
        creator_card = db.by_card_id.get(_creator_card_id(game, ent.entity_id))
        rows.append(
            ZoneCard(
                label=card.get("name", ent.card_id),
                origin=creator_card["name"] if creator_card else "",
                cost=card.get("cost", 0) or 0,
                card_id=ent.card_id,
                rarity=card.get("rarity", ""),
                struck=ent.zone != DECK,
            )
        )
    grouped = _group(rows, key=lambda r: (r.card_id, r.origin, r.struck))
    return sorted(grouped, key=lambda r: (r.struck, r.cost, r.label))


def _in_zones(
    game: Game, db: CardsDb, player_id: int | None, zones: tuple[str, ...]
) -> list[ZoneCard]:
    """Cartes d'un camp actuellement dans l'une des zones données."""
    if player_id is None:
        return []
    rows = []
    for ent in game.entities.values():
        if ent.zone not in zones or ent.controller != player_id or not ent.card_id:
            continue
        card = db.by_card_id.get(ent.card_id)
        if card is None or card.get("type") == "HERO_POWER":
            continue
        creator_card = db.by_card_id.get(_creator_card_id(game, ent.entity_id))
        rows.append(
            ZoneCard(
                label=card.get("name", ent.card_id),
                origin=creator_card["name"] if creator_card else "",
                cost=card.get("cost", 0) or 0,
                card_id=ent.card_id,
                rarity=card.get("rarity", ""),
            )
        )
    return sorted(_group(rows), key=lambda r: (r.cost, r.label))


def _graveyard(game: Game, db: CardsDb, player_id: int | None) -> list[DeadMinion]:
    """Serviteurs d'un camp morts pendant la partie (les plus chers d'abord :
    c'est ce qu'on veut voir en premier face aux effets de résurrection)."""
    rows = []
    for ev in game.events:
        if not isinstance(ev, Death) or ev.player_id != player_id or not ev.card_id:
            continue
        card = db.by_card_id.get(ev.card_id)
        if card is None:
            continue
        rows.append(
            DeadMinion(
                label=card.get("name", ev.card_id),
                cost=card.get("cost", 0) or 0,
                card_id=ev.card_id,
                rarity=card.get("rarity", ""),
            )
        )
    return sorted(_group(rows, key=lambda r: r.card_id), key=lambda r: (-r.cost, r.label))


def compute_deck_view(game: Game, deck: PlayerDeck | None, db: CardsDb) -> DeckView:
    view = DeckView()
    local = game.local_player_id()

    # --- adversaire ---------------------------------------------------------
    if local is not None:
        opp_names = [n for p, n in game.player_names.items() if p != local]
        # en fin de partie le vrai battletag adverse apparaît dans results
        local_name = game.player_names.get(local, "")
        for name in game.results:
            if name != local_name:
                opp_names.insert(0, name)
        opponent = next((n for n in opp_names if n != "UNKNOWN HUMAN PLAYER"), None)
        if opponent is None:
            # battletag révélé seulement en fin de partie → en attendant, son héros
            opp_id = next((p for p in game.player_names if p != local), None)
            hero = game.hero_card_id(opp_id) if opp_id is not None else None
            card = db.by_card_id.get(hero or "")
            opponent = card["name"] if card else "adversaire ?"
        view.opponent_name = opponent
        view.result = game.results.get(local_name, "")

    # --- composition de départ ---------------------------------------------
    counts: dict[int, int] = {}
    if deck is not None:
        view.deck_name = deck.name
        try:
            for dbf_id, count in decode_deckstring(deck.deckstring).cards:
                counts[dbf_id] = counts.get(dbf_id, 0) + count
        except DeckstringError:
            pass
    remaining = dict(counts)

    def dbf_of(card_id: str | None) -> int | None:
        if not card_id:
            return None
        card = db.by_card_id.get(card_id)
        return card.get("dbfId") if card else None

    # --- rejouer les événements du point de vue du deck local ---------------
    # entrées vivantes : entity_id → EntryRow (retirées quand la carte ressort)
    live_entries: dict[int, EntryRow] = {}
    opp_counts: dict[str, OppPlay] = {}

    for ev in game.events:
        mine = local is None or ev.player_id == local
        if isinstance(ev, (Draw, DeckLeave)) and mine:
            if ev.entity_id in live_entries:
                live_entries.pop(ev.entity_id)  # une carte « entrée » ressort
                continue
            dbf = dbf_of(ev.card_id)
            if dbf is not None and remaining.get(dbf, 0) > 0:
                remaining[dbf] -= 1
        elif isinstance(ev, DeckEntry) and mine:
            if not ev.created:
                dbf = dbf_of(ev.card_id)
                if dbf is not None and dbf in counts:
                    # carte du deck qui revient (mulligan ou renvoi)
                    remaining[dbf] = min(counts[dbf], remaining.get(dbf, 0) + 1)
                    continue
            if ev.created or not ev.during_mulligan:
                # les créations comptent TOUJOURS (Azalina ajoute avant la fin
                # du mulligan) ; seuls les retours de mulligan sont exclus
                # identité et origine relues maintenant : au moment de l'entrée
                # dans le deck, HS n'a souvent encore rien publié (cf.
                # _live_card_id et _creator_card_id)
                card_id = _live_card_id(game, ev.entity_id, ev.card_id)
                card = db.by_card_id.get(card_id)
                creator_id = (
                    _creator_card_id(game, ev.entity_id) or ev.creator_card_id or ""
                )
                creator = db.by_card_id.get(creator_id)
                live_entries[ev.entity_id] = EntryRow(
                    label=card["name"] if card else "?",
                    origin=creator["name"] if creator else "",
                    known=card is not None,
                    card_id=card_id,
                    rarity=(card.get("rarity", "") if card else ""),
                    pos=("bottom" if creator_id in db.deck_bottom_ids
                         else "top" if creator_id in db.deck_top_ids else ""),
                )
        elif isinstance(ev, Play) and not mine and local is not None:
            card = db.by_card_id.get(ev.card_id or "")
            if card:
                # La carte créatrice se lit sur l'entité, tags CREATOR puis
                # DISPLAYED_CREATOR (cf. Entity.creator_entity_id) — ce dernier
                # est le seul posé sur les copies qu'Azalina range dans le deck.
                createur_id = _creator_card_id(game, ev.entity_id)
                createur = db.by_card_id.get(createur_id)
                origine = createur["name"] if createur else ""
                # On regroupe par (carte, origine) : deux exemplaires dont un
                # sorti du deck et un offert par un effet doivent se lire sur
                # deux lignes, sinon l'information se perd dans le compteur.
                key = (card["name"], origine)
                if key in opp_counts:
                    opp_counts[key].count += 1
                else:
                    opp_counts[key] = OppPlay(
                        label=card["name"],
                        count=1,
                        cost=card.get("cost", 0) or 0,
                        card_id=card.get("id", ""),
                        rarity=card.get("rarity", ""),
                        origin=origine,
                        created=bool(createur_id),
                    )

    # --- assemblage ---------------------------------------------------------
    for dbf_id, total in counts.items():
        card = db.by_dbf_id.get(dbf_id, {})
        view.rows.append(
            CardRow(
                dbf_id=dbf_id,
                name=card.get("name", f"dbfId:{dbf_id}"),
                cost=card.get("cost", 0) or 0,
                total=total,
                remaining=remaining.get(dbf_id, 0),
                card_id=card.get("id", ""),
                rarity=card.get("rarity", ""),
            )
        )
    # entrées groupées : « ? ← Azalina ×20 » plutôt que 20 lignes
    # (dict ordonné : les cartes posées au fond restent dans l'ordre de pose)
    grouped: dict[tuple[str, str, str], EntryRow] = {}
    for entry in live_entries.values():
        key = (entry.label, entry.origin, entry.pos)
        if key in grouped:
            grouped[key].count += 1
        else:
            grouped[key] = entry
    # les entrées localisées sortent de la liste générique : les montrer deux
    # fois ferait croire à deux exemplaires
    view.entries = [e for e in grouped.values() if not e.pos]
    view.deck_bottom = [e for e in grouped.values() if e.pos == "bottom"]
    view.deck_top = [e for e in grouped.values() if e.pos == "top"]

    # Les entrées quelconques rejoignent la LISTE DU DECK, marquées d'un cadeau.
    # Elles vivaient dans une section « ENTRÉES » à part, ce qui obligeait à
    # regarder à deux endroits pour savoir ce qu'il reste à piocher — alors
    # qu'une copie créée est une carte du deck comme une autre. Ligne SÉPARÉE
    # et non fusionnée avec l'exemplaire d'origine : « 2 Puits de lune » ne dit
    # pas la même chose que « 1 Puits de lune + 1 copie offerte ».
    for entry in view.entries:
        card = db.by_card_id.get(entry.card_id) if entry.known else None
        view.rows.append(
            CardRow(
                dbf_id=(card or {}).get("dbfId", 0),
                name=entry.label,
                # carte cachée : coût inconnu, donc pas de gemme de mana
                cost=(card.get("cost") or 0) if card else -1,
                total=entry.count,
                remaining=entry.count,
                card_id=entry.card_id if entry.known else "",
                rarity=entry.rarity,
                gift=True,
                origin=entry.origin,
            )
        )
    # les coûts inconnus (-1) finissent la liste : ils ne se rangent nulle part
    view.rows.sort(key=lambda r: (99 if r.cost < 0 else r.cost, r.name))

    # Ce qui sort de son deck d'abord, ce qu'un effet lui a donné ensuite :
    # la première liste dit ce qu'il lui reste, la seconde ce qu'il a volé.
    view.opponent_plays = sorted(
        opp_counts.values(), key=lambda p: (p.created, p.cost, p.label)
    )

    if local is not None:
        view.opponent_hand = _known_opponent_hand(game, db, local)
        view.opponent_hand_slots = _opponent_hand_slots(game, db, local)
        view.my_hand = _in_zones(game, db, local, ("HAND",))
        view.my_graveyard = _graveyard(game, db, local)
        opp_id = next((p for p in game.player_names if p != local), None)
        view.my_effects = global_effects(game, db, local)
        view.opp_effects = global_effects(game, db, opp_id)
        view.opp_deck_known = _revealed_deck(game, db, opp_id)
        view.opp_graveyard = _graveyard(game, db, opp_id) if opp_id is not None else []
        view.my_atlas = atlas.queue(game, db, local)
        view.opp_atlas = atlas.queue(game, db, opp_id)
        if _tolvir_relevant(game, db, local, view.rows):
            view.my_replay = plays_costing(game, db, local, TOLVIR_COST,
                                           types=TOLVIR_TYPES)
        if _tolvir_relevant(game, db, opp_id, ()):
            view.opp_replay = plays_costing(game, db, opp_id, TOLVIR_COST,
                                            types=TOLVIR_TYPES)

    # total = VÉRITÉ DES ZONES : ce que HS affiche sur le dos du deck, exact
    # même quand des cartes inconnues y entrent (retour utilisateur du 01/08)
    if local is not None:
        view.remaining_total = sum(
            1 for e in game.entities.values()
            if e.zone == "DECK" and e.controller == local
        )
    else:
        view.remaining_total = sum(remaining.values()) + sum(e.count for e in view.entries)
    return view
