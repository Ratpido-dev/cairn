"""Tests unitaires du tokenizer Power.log — sur des lignes réelles de la fixture."""

from src.cairn.power_log import (
    CreateGame,
    EntityDef,
    GameInfo,
    PlayerName,
    TagChange,
    parse_entity_ref,
    parse_lines,
)

L = "D 00:08:05.1088643 GameState.DebugPrintPower() - "
G = "D 00:08:05.1088643 GameState.DebugPrintGame() - "


def events(*lines):
    return list(parse_lines(lines))


def test_entity_ref_bloc_avec_espaces_dans_le_nom():
    ref = parse_entity_ref(
        "[entityName=Garrosh corrompu id=54 zone=PLAY zonePos=0 cardId=HERO_01b player=1]"
    )
    assert ref.entity_id == 54
    assert ref.name == "Garrosh corrompu"
    assert ref.card_id == "HERO_01b"
    assert ref.player == 1


def test_entity_ref_entier_et_nom_de_joueur():
    assert parse_entity_ref("132").entity_id == 132
    ref = parse_entity_ref("UNKNOWN HUMAN PLAYER")
    assert ref.name == "UNKNOWN HUMAN PLAYER"
    assert ref.entity_id is None


def test_tag_change_avec_tag_numerique():
    (ev,) = events(
        L + "TAG_CHANGE Entity=[entityName=Garrosh corrompu id=54 zone=PLAY "
        "zonePos=0 cardId=HERO_01b player=1] tag=479 value=0 "
    )
    assert isinstance(ev, TagChange)
    assert ev.tag == "479"
    assert ev.ref.entity_id == 54


def test_full_entity_regroupe_ses_tags():
    evs = events(
        L + "FULL_ENTITY - Creating ID=4 CardID=",
        L + "    tag=ZONE value=DECK",
        L + "    tag=CONTROLLER value=1",
        L + "TAG_CHANGE Entity=4 tag=ZONE value=HAND",
    )
    assert len(evs) == 2
    full, tag_change = evs
    assert isinstance(full, EntityDef) and full.kind == "full"
    assert full.entity_id == 4
    assert full.card_id is None
    assert full.tags == {"ZONE": "DECK", "CONTROLLER": "1"}
    assert isinstance(tag_change, TagChange)


def test_show_entity_reference_entiere():
    (ev,) = events(L + "SHOW_ENTITY - Updating Entity=132 CardID=EDR_449e")
    assert isinstance(ev, EntityDef) and ev.kind == "show"
    assert ev.entity_id == 132
    assert ev.card_id == "EDR_449e"


def test_create_game_et_infos_partie():
    evs = events(
        L + "CREATE_GAME",
        G + "GameType=GT_RANKED",
        G + "FormatType=FT_STANDARD",
        G + "PlayerID=2, PlayerName=Joueur#12345",
    )
    assert isinstance(evs[0], CreateGame)
    assert GameInfo(key="GameType", value="GT_RANKED") in evs
    assert PlayerName(player_id=2, name="Joueur#12345") in evs


def test_lignes_non_gamestate_ignorees():
    assert events(
        "D 00:08:05.1 PowerTaskList.DebugPrintPower() - TAG_CHANGE Entity=4 tag=ZONE value=HAND",
        "E 11:39:14.0 PowerProcessor.BuildTaskList(): Hit a SUB_SPELL_END task",
        "n'importe quoi",
    ) == []


# ---- modes sans deck : traversés sans être analysés ------------------------

_G = "D 00:00:00.0000000 GameState.DebugPrintPower() - "
_INFO = "D 00:00:00.0000000 GameState.DebugPrintGame() - "
_TASK = "D 00:00:00.0000000 PowerTaskList.DebugPrintPower() -     "


def test_partie_sans_deck_traversee_sans_etre_analysee():
    """Une partie de Champ de bataille pèse ~86 Mo là où une classée en pèse 5.
    Elle est ignorée partout en aval : l'analyser est du travail pur perte."""
    events = list(parse_lines([
        _G + "CREATE_GAME",
        _INFO + "GameType=GT_BATTLEGROUNDS",
        _G + "TAG_CHANGE Entity=GameEntity tag=TURN value=12",
        _G + "TAG_CHANGE Entity=GameEntity tag=TURN value=13",
    ]))
    assert [type(e).__name__ for e in events] == ["CreateGame", "GameInfo"]


def test_le_doublon_powertasklist_ne_coupe_pas_la_traversee():
    """Hearthstone journalise tout deux fois : GameState puis PowerTaskList.
    Le doublon de CREATE_GAME arrive huit lignes après le GameType — le prendre
    pour la partie suivante coupait le saut aussitôt commencé."""
    events = list(parse_lines([
        _G + "CREATE_GAME",
        _INFO + "GameType=GT_BATTLEGROUNDS",
        _TASK + "CREATE_GAME",                       # le piège
        _G + "TAG_CHANGE Entity=GameEntity tag=TURN value=12",
    ]))
    assert [type(e).__name__ for e in events] == ["CreateGame", "GameInfo"]


def test_la_partie_suivante_est_bien_reprise():
    """Le saut s'arrête au vrai CREATE_GAME : la partie classée qui suit une
    partie de Champ de bataille doit être suivie normalement."""
    events = list(parse_lines([
        _G + "CREATE_GAME",
        _INFO + "GameType=GT_BATTLEGROUNDS",
        _G + "TAG_CHANGE Entity=GameEntity tag=TURN value=12",
        _G + "CREATE_GAME",
        _INFO + "GameType=GT_RANKED",
        _G + "TAG_CHANGE Entity=GameEntity tag=TURN value=3",
    ]))
    assert [type(e).__name__ for e in events] == [
        "CreateGame", "GameInfo", "CreateGame", "GameInfo", "TagChange",
    ]
