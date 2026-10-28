"""Fond du deck et L'Étendue infinie (#5).

Scénarios reconstruits d'après un Power.log réel envoyé avec l'issue (Guerrier
Finley, Sphère de sapience, Menace des profondeurs, L'Étendue infinie) :
mêmes lignes, mêmes tags, réduits à l'essentiel.
"""

import base64

from src.cairn.counters import CounterContext, counter_ceaseless
from src.cairn.deck_view import DeckView, compute_deck_view
from src.cairn.decks_log import PlayerDeck
from src.cairn.game_state import (
    DeckBottom,
    Draw,
    Entity,
    Game,
    GameStateEngine,
    Play,
)
from src.cairn.power_log import parse_lines

_L = "D 00:00:00.0000000 GameState.DebugPrintPower() - "
_EFFET = " EffectCardId=System.Collections.Generic.List`1[System.String] EffectIndex=0 Target=0 SubOption=-1"


class _FakeDb:
    def __init__(self):
        cartes = [
            ("CARTE_A", "Carte A", 101, 2),
            ("CARTE_B", "Carte B", 102, 3),
            ("TSC_908", "Sir Finley, guide maritime", 103, 1),
            ("SCH_259", "Sphère de sapience", 104, 1),
            ("GDB_142", "L'Étendue infinie", 105, 100),
        ]
        self.by_card_id = {
            cid: {"id": cid, "name": nom, "dbfId": dbf, "cost": cout, "rarity": "COMMON"}
            for cid, nom, dbf, cout in cartes
        }
        self.by_dbf_id = {c["dbfId"]: c for c in self.by_card_id.values()}
        self.deck_bottom_ids = set()
        self.deck_top_ids = set()

    def localized_name(self, card_id, lang="fr"):
        card = self.by_card_id.get(card_id or "")
        return card["name"] if card else ""


def _varint(n):
    out = bytearray()
    while True:
        octet = n & 0x7F
        n >>= 7
        out.append(octet | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _deckstring(*dbf_ids):
    """Deckstring minimal : un exemplaire de chaque carte."""
    corps = b"\x00\x01" + _varint(2) + _varint(1) + _varint(7)
    corps += _varint(len(dbf_ids)) + b"".join(_varint(d) for d in dbf_ids)
    corps += _varint(0) + _varint(0)
    return base64.b64encode(corps).decode()


DECK = PlayerDeck(name="Finley", deck_id=1, deckstring=_deckstring(101, 102, 103, 104))


def _ref(eid, card_id, zone="HAND"):
    return f"[entityName=x id={eid} zone={zone} zonePos=1 cardId={card_id} player=1]"


def _partie(*suite):
    """Partie du joueur 1 : quatre cartes au deck, mulligan fait, A et B en main."""
    lignes = [
        _L + "CREATE_GAME",
        _L + "    GameEntity EntityID=1",
        _L + "    Player EntityID=2 PlayerID=1 GameAccountId=[hi=1 lo=2]",
        _L + "    Player EntityID=3 PlayerID=2 GameAccountId=[hi=1 lo=3]",
    ]
    for eid in (30, 31, 32, 33):
        lignes += [_L + f"FULL_ENTITY - Creating ID={eid} CardID=",
                   _L + "    tag=ZONE value=DECK",
                   _L + "    tag=CONTROLLER value=1"]
    lignes += [
        _L + "TAG_CHANGE Entity=[entityName=x id=2 zone=PLAY zonePos=0 cardId= player=1] "
             "tag=MULLIGAN_STATE value=DONE",
        _L + "TAG_CHANGE Entity=GameEntity tag=TURN value=1",
        _L + "SHOW_ENTITY - Updating Entity=[entityName=UNKNOWN ENTITY [cardType=INVALID] "
             "id=30 zone=DECK zonePos=0 cardId= player=1] CardID=CARTE_A",
        _L + "    tag=ZONE value=HAND",
        _L + "SHOW_ENTITY - Updating Entity=[entityName=UNKNOWN ENTITY [cardType=INVALID] "
             "id=31 zone=DECK zonePos=0 cardId= player=1] CardID=CARTE_B",
        _L + "    tag=ZONE value=HAND",
        *suite,
    ]
    engine = GameStateEngine()
    engine.feed(parse_lines(lignes))
    return engine.games[0]


FINLEY = [
    _L + "BLOCK_START BlockType=POWER Entity=" + _ref(32, "TSC_908") + _EFFET,
    _L + "    TAG_CHANGE Entity=" + _ref(30, "CARTE_A") + " tag=ZONE value=DECK",
    _L + "    TAG_CHANGE Entity=" + _ref(31, "CARTE_B") + " tag=ZONE value=DECK",
    _L + "BLOCK_END",
]


def _fond(view):
    return [(e.label, e.origin, e.count) for e in view.deck_bottom]


def test_finley_envoie_la_main_au_fond_du_deck():
    db = _FakeDb()
    view = compute_deck_view(_partie(*FINLEY), DECK, db)
    assert _fond(view) == [("Carte A", "Sir Finley, guide maritime", 1),
                           ("Carte B", "Sir Finley, guide maritime", 1)]
    # toujours comptées dans le deck : le fond ne dit que leur place
    restantes = {r.name: r.remaining for r in view.rows}
    assert restantes["Carte A"] == 1 and restantes["Carte B"] == 1


def test_carte_tiree_du_fond_quitte_la_section():
    db = _FakeDb()
    game = _partie(*FINLEY, _L + "TAG_CHANGE Entity=" + _ref(30, "CARTE_A", "DECK")
                   + " tag=ZONE value=HAND")
    assert _fond(compute_deck_view(game, DECK, db)) == [
        ("Carte B", "Sir Finley, guide maritime", 1)]


def test_un_melange_efface_le_fond_connu():
    db = _FakeDb()
    game = _partie(*FINLEY, _L + "SHUFFLE_DECK PlayerID=1")
    assert _fond(compute_deck_view(game, DECK, db)) == []


def _sphere(type_de_bloc="TRIGGER", porteur=50):
    """La Sphère montre la carte du dessus (entité 33) par une copie ; choisir
    « Un nouveau destin » lui coûte 1 point de durabilité."""
    return [
        _L + "FULL_ENTITY - Creating ID=50 CardID=SCH_259",
        _L + "    tag=ZONE value=PLAY",
        _L + "    tag=CONTROLLER value=1",
        _L + "    tag=CARDTYPE value=WEAPON",
        _L + f"BLOCK_START BlockType={type_de_bloc} Entity="
             + _ref(porteur, "SCH_259" if porteur == 50 else "HERO_01", "PLAY") + _EFFET,
        _L + "    FULL_ENTITY - Creating ID=60 CardID=CARTE_A",
        _L + "        tag=ZONE value=SETASIDE",
        _L + "        tag=CONTROLLER value=1",
        _L + "        tag=CREATOR value=50",
        _L + "    TAG_CHANGE Entity=60 tag=COPIED_FROM_ENTITY_ID value=33",
        _L + "    TAG_CHANGE Entity=" + _ref(50, "SCH_259", "PLAY") + " tag=DAMAGE value=1",
        _L + "BLOCK_END",
    ]


def test_sphere_de_sapience_glisse_la_carte_du_dessus_au_fond():
    db = _FakeDb()
    game = _partie(*_sphere())
    (bas,) = [e for e in game.events if isinstance(e, DeckBottom)]
    assert (bas.entity_id, bas.card_id) == (33, "CARTE_A")
    assert _fond(compute_deck_view(game, DECK, db)) == [
        ("Carte A", "Sphère de sapience", 1)]


def test_sphere_abimee_en_attaquant_ne_deplace_rien():
    game = _partie(*_sphere(type_de_bloc="ATTACK", porteur=2))
    assert not [e for e in game.events if isinstance(e, DeckBottom)]


# ---- L'Étendue infinie ------------------------------------------------------

def _etendue(zone, cout=None, evenements=()):
    g = Game(player_names={1: "moi", 2: "adv"}, player_entity={1: 10, 2: 11})
    tags = {"ZONE": zone, "CONTROLLER": "1"}
    if cout is not None:
        tags["COST"] = str(cout)
    g.entities[70] = Entity(entity_id=70, card_id="GDB_142", tags=tags)
    # une pioche révélée désigne le joueur local
    g.entities[71] = Entity(entity_id=71, card_id="CARTE_A",
                            tags={"ZONE": "HAND", "CONTROLLER": "1"})
    g.events = [Draw(player_id=1, entity_id=71, card_id="CARTE_A",
                     during_mulligan=False, turn=0), *evenements]
    return CounterContext(game=g, view=DeckView(), db=_FakeDb())


def test_etendue_au_deck_compte_pioches_et_cartes_jouees_des_deux_camps():
    """Vérifié sur la partie de l'issue : le coût en main suit, tour après
    tour, les pioches hors mulligan et les cartes jouées des deux camps."""
    evenements = [
        Draw(player_id=1, entity_id=80, card_id=None, during_mulligan=False, turn=0),
        Draw(player_id=1, entity_id=81, card_id=None, during_mulligan=False, turn=1),
        Draw(player_id=2, entity_id=82, card_id=None, during_mulligan=False, turn=2),
        Play(player_id=2, entity_id=82, card_id="CARTE_B", turn=2),
    ]
    (compteur,) = counter_ceaseless(_etendue("DECK", evenements=evenements))
    assert compteur.short == "(97)"     # les pioches du tour 0 ne comptent pas


def test_etendue_en_main_prend_le_cout_publie_par_le_jeu():
    """En main, le tag COST dit tout, réductions annexes comprises (Menace
    des profondeurs retire 3 de plus aux cartes du fond)."""
    (compteur,) = counter_ceaseless(_etendue("HAND", cout=42))
    assert compteur.short == "(42)" and compteur.alert is False
    (compteur,) = counter_ceaseless(_etendue("HAND", cout=4))
    assert compteur.alert
