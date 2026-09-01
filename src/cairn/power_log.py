"""Tokenizer de Power.log : lignes brutes → événements typés.

On ne lit que le flux ``GameState`` (la vérité du jeu, ce que parse aussi
Firestone), pas ``PowerTaskList`` (le même contenu, resynchronisé pour
l'animation).

Formats observés (fixture du 01/08/2026) :

    D 00:08:05.1088643 GameState.DebugPrintPower() - CREATE_GAME
    D … DebugPrintPower() -     GameEntity EntityID=1
    D … DebugPrintPower() -         tag=CARDTYPE value=GAME
    D … DebugPrintPower() -     Player EntityID=2 PlayerID=1 GameAccountId=[…]
    D … DebugPrintPower() - FULL_ENTITY - Creating ID=4 CardID=
    D … DebugPrintPower() - SHOW_ENTITY - Updating Entity=132 CardID=EDR_449e
    D … DebugPrintPower() - TAG_CHANGE Entity=[entityName=Garrosh corrompu id=54
        zone=PLAY zonePos=0 cardId=HERO_01b player=1] tag=ATK value=0
    D … DebugPrintPower() - TAG_CHANGE Entity=Joueur#12345 tag=MULLIGAN_STATE value=INPUT
    D … DebugPrintPower() - BLOCK_START BlockType=TRIGGER Entity=38 …
    D … DebugPrintPower() -     SHUFFLE_DECK PlayerID=1
    D … DebugPrintGame() - GameType=GT_RANKED
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator, Union

_LINE = re.compile(
    r"^[DIWE] (?P<ts>[\d:.]+) GameState\.DebugPrint(?P<chan>Power|Game)\(\) -(?P<body>.*)$"
)
_ENTITY_BLOCK = re.compile(
    r"\[entityName=(?P<name>.*?) id=(?P<id>\d+) zone=(?P<zone>\w*) "
    r"zonePos=(?P<zone_pos>-?\d+) cardId=(?P<card_id>\S*) player=(?P<player>\d+)\]"
)
_TAG_CHANGE = re.compile(r"^TAG_CHANGE Entity=(?P<ref>.+?) tag=(?P<tag>\S+) value=(?P<value>\S+)")
_FULL_ENTITY = re.compile(r"^FULL_ENTITY - Creating ID=(?P<id>\d+) CardID=(?P<card_id>\S*)$")
_SHOW_ENTITY = re.compile(r"^SHOW_ENTITY - Updating Entity=(?P<ref>.+?) CardID=(?P<card_id>\S*)$")
_HIDE_ENTITY = re.compile(r"^HIDE_ENTITY - Entity=(?P<ref>.+?) tag=(?P<tag>\S+) value=(?P<value>\S+)")
_TAG_LINE = re.compile(r"^tag=(?P<tag>\S+) value=(?P<value>\S+)\s*$")
_GAME_ENTITY = re.compile(r"^GameEntity EntityID=(?P<id>\d+)$")
# Le « lo » du GameAccountId est le seul identifiant STABLE d'un joueur d'une
# partie à l'autre. Il était capturé puis jeté ; c'est lui qui permet de savoir
# qu'on regarde la partie de quelqu'un d'autre (cf. Game.is_spectated).
_PLAYER_ENTITY = re.compile(
    r"^Player EntityID=(?P<id>\d+) PlayerID=(?P<player_id>\d+)"
    r"(?: GameAccountId=\[hi=\d+ lo=(?P<account>\d+)\])?"
)
_BLOCK_START = re.compile(r"^BLOCK_START BlockType=(?P<block_type>\S+) Entity=(?P<ref>.*?) EffectCardId=")
_SHUFFLE = re.compile(r"^SHUFFLE_DECK PlayerID=(?P<player_id>\d+)$")
_GAME_INFO = re.compile(r"^(?P<key>GameType|FormatType)=(?P<value>\S+)$")
_PLAYER_NAME = re.compile(r"^PlayerID=(?P<player_id>\d+), PlayerName=(?P<name>.+)$")

# Modes qui ne se jouent pas avec un deck construit. Comparés par PRÉFIXE :
# Blizzard décline le Champ de bataille en duo, en amical et contre l'IA, et
# une liste exacte serait à refaire à chaque variante.
MODES_SANS_DECK = ("GT_BATTLEGROUNDS", "GT_MERCENARIES")


@dataclass
class EntityRef:
    """Référence d'entité telle qu'écrite dans le log — au plus un champ rempli."""

    entity_id: int | None = None
    name: str | None = None  # nom de joueur (« Joueur#12345 ») ou entityName
    is_game: bool = False
    card_id: str | None = None
    player: int | None = None


def parse_entity_ref(raw: str) -> EntityRef:
    raw = raw.strip()
    if raw == "GameEntity":
        return EntityRef(is_game=True)
    if raw.isdigit():
        return EntityRef(entity_id=int(raw))
    m = _ENTITY_BLOCK.search(raw)
    if m:
        return EntityRef(
            entity_id=int(m["id"]),
            name=m["name"] or None,
            card_id=m["card_id"] or None,
            player=int(m["player"]),
        )
    return EntityRef(name=raw)  # nom de joueur, « UNKNOWN HUMAN PLAYER »…


# ---- événements ------------------------------------------------------------

@dataclass
class CreateGame:
    ts: str


@dataclass
class EntityDef:
    """GameEntity / Player / FULL_ENTITY / SHOW_ENTITY + ses lignes tag=."""

    kind: str  # "game" | "player" | "full" | "show"
    entity_id: int | None
    card_id: str | None = None
    player_id: int | None = None  # pour kind="player"
    account: str | None = None  # pour kind="player" : le « lo » du GameAccountId
    ref: EntityRef | None = None  # pour kind="show" (référence d'origine)
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class TagChange:
    ref: EntityRef
    tag: str
    value: str
    ts: str = ""  # horodatage de la ligne — sert à mesurer la durée de partie


@dataclass
class BlockStart:
    block_type: str
    ref: EntityRef


@dataclass
class BlockEnd:
    pass


@dataclass
class ShuffleDeck:
    player_id: int


@dataclass
class GameInfo:
    key: str  # GameType | FormatType
    value: str


@dataclass
class PlayerName:
    player_id: int
    name: str


Event = Union[CreateGame, EntityDef, TagChange, BlockStart, BlockEnd, ShuffleDeck, GameInfo, PlayerName]


class IncrementalParser:
    """Parser alimenté ligne à ligne — nécessaire au suivi live.

    Les lignes ``tag=… value=…`` sont rattachées au dernier EntityDef ouvert
    (elles arrivent toujours immédiatement après lui) ; l'EntityDef est émis
    dès la première ligne qui ne lui appartient plus — muter ``pending.tags``
    après émission resterait visible, d'où l'émission différée.
    """

    def __init__(self) -> None:
        self._pending: EntityDef | None = None
        self._saut = False  # partie sans deck en cours : on la traverse sans la lire

    def feed(self, raw: str) -> list[Event]:
        if self._saut:
            # Une partie de Champ de bataille pèse ~86 Mo là où une partie
            # classée en pèse 5 : 675 000 lignes sur les 830 000 d'une session
            # mesurée ici. Comme ces modes n'ont pas de deck et sont ignorés
            # partout en aval, les analyser est du travail pur perte. On les
            # traverse avec une recherche de sous-chaîne — sans regex, qui est
            # justement ce qui coûte cher — jusqu'à la partie suivante.
            if "CREATE_GAME" not in raw:
                return []
            # Hearthstone journalise tout DEUX fois, sur GameState et sur
            # PowerTaskList ; seul le premier canal compte (cf. _LINE). Le
            # doublon arrive huit lignes après le GameType, et le prendre pour
            # la partie suivante coupait le saut aussitôt commencé.
            m = _LINE.match(raw)
            if m is None or m["body"].lstrip() != "CREATE_GAME":
                return []
            self._saut = False
            self._pending = None

        m = _LINE.match(raw)
        if not m:
            return []
        body = m["body"].lstrip()
        if not body:
            return []

        out: list[Event] = []
        if self._pending is not None:
            t = _TAG_LINE.match(body)
            if t:
                self._pending.tags[t["tag"]] = t["value"]
                return []
            out.append(self._pending)
            self._pending = None

        if m["chan"] == "Game":
            g = _GAME_INFO.match(body)
            if g:
                out.append(GameInfo(key=g["key"], value=g["value"]))
                if g["key"] == "GameType" and g["value"].startswith(MODES_SANS_DECK):
                    # Le GameType arrive quelques centaines de lignes après le
                    # CREATE_GAME : la partie existe déjà côté moteur, avec son
                    # type — assez pour que l'affichage et l'historique
                    # l'écartent. Tout ce qui suit ne sert à personne.
                    self._saut = True
                return out
            p = _PLAYER_NAME.match(body)
            if p:
                out.append(PlayerName(player_id=int(p["player_id"]), name=p["name"].strip()))
            return out

        if body == "CREATE_GAME":
            out.append(CreateGame(ts=m["ts"]))
        elif body == "BLOCK_END":
            out.append(BlockEnd())
        elif (t := _TAG_CHANGE.match(body)) is not None:
            out.append(TagChange(ref=parse_entity_ref(t["ref"]), tag=t["tag"],
                                 value=t["value"], ts=m["ts"]))
        elif (f := _FULL_ENTITY.match(body)) is not None:
            self._pending = EntityDef(kind="full", entity_id=int(f["id"]), card_id=f["card_id"] or None)
        elif (s := _SHOW_ENTITY.match(body)) is not None:
            ref = parse_entity_ref(s["ref"])
            self._pending = EntityDef(kind="show", entity_id=ref.entity_id, card_id=s["card_id"] or None, ref=ref)
        elif (h := _HIDE_ENTITY.match(body)) is not None:
            out.append(TagChange(ref=parse_entity_ref(h["ref"]), tag=h["tag"], value=h["value"]))
        elif (ge := _GAME_ENTITY.match(body)) is not None:
            self._pending = EntityDef(kind="game", entity_id=int(ge["id"]))
        elif (pe := _PLAYER_ENTITY.match(body)) is not None:
            self._pending = EntityDef(
                kind="player",
                entity_id=int(pe["id"]),
                player_id=int(pe["player_id"]),
                account=pe["account"],
            )
        elif (b := _BLOCK_START.match(body)) is not None:
            out.append(BlockStart(block_type=b["block_type"], ref=parse_entity_ref(b["ref"])))
        elif (sh := _SHUFFLE.match(body)) is not None:
            out.append(ShuffleDeck(player_id=int(sh["player_id"])))
        # le reste (META_DATA, SUB_SPELL, Info[…], options…) : ignoré en phase 1
        return out

    def flush(self) -> list[Event]:
        """À appeler en fin de fichier (lecture batch) — pas en live."""
        if self._pending is None:
            return []
        out = [self._pending]
        self._pending = None
        return out

    def reset(self) -> None:
        self._pending = None
        self._saut = False


def parse_lines(lines) -> Iterator[Event]:
    """Flux de lignes brutes → flux d'événements (lecture batch)."""
    parser = IncrementalParser()
    for raw in lines:
        yield from parser.feed(raw)
    yield from parser.flush()


def _jusqu_a_la_casse(lignes) -> Iterator[str]:
    """Lit tant que ça se lit, puis s'arrête sans crier.

    Une archive est écrite par membres gzip successifs (cf. ``archive.py``) : si
    le processus meurt en plein milieu du dernier, Python refuse de relire le
    fichier ENTIER (« Compressed file ended before the end-of-stream marker »).
    Pour un journal, c'est le mauvais arbitrage — les parties déjà écrites sont
    intactes et parfaitement exploitables. On rend donc tout ce qui se décode,
    et on s'arrête à la première cassure.
    """
    try:
        for ligne in lignes:
            yield ligne
    except (EOFError, OSError):
        return  # dernier bloc incomplet : le reste a déjà été rendu


def parse_file(path) -> Iterator[Event]:
    """Rejoue un journal, compressé ou non.

    Les sessions archivées par Cairn sont des ``.gz`` (×18 sur un Power.log) :
    les rejouer doit être aussi simple que de rejouer un journal brut, sinon
    l'archive ne sert à rien.
    """
    if str(path).endswith(".gz"):
        import gzip

        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
            yield from parse_lines(_jusqu_a_la_casse(f))
        return
    with open(path, encoding="utf-8", errors="replace") as f:
        yield from parse_lines(f)
