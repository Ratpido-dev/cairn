"""Tests du moteur d'état sur des scénarios synthétiques (pioche, entrée de deck)."""

from src.cairn.game_state import (
    DeckEntry,
    Draw,
    GameStateEngine,
    Play,
    learn_own_account,
)
from src.cairn.power_log import parse_lines

L = "D 00:00:00.0000000 GameState.DebugPrintPower() - "


def run(*lines):
    engine = GameStateEngine()
    engine.feed(parse_lines(lines))
    return engine.games


BASE = [
    L + "CREATE_GAME",
    L + "    GameEntity EntityID=1",
    L + "    Player EntityID=2 PlayerID=1 GameAccountId=[hi=1 lo=2]",
    L + "    Player EntityID=3 PlayerID=2 GameAccountId=[hi=1 lo=3]",
    L + "FULL_ENTITY - Creating ID=10 CardID=",
    L + "    tag=ZONE value=DECK",
    L + "    tag=CONTROLLER value=1",
]
MULLIGAN_DONE = L + "TAG_CHANGE Entity=[entityName=x id=2 zone=PLAY zonePos=0 cardId= player=1] tag=MULLIGAN_STATE value=DONE"


def test_pioche_pendant_et_apres_mulligan():
    games = run(
        *BASE,
        L + "TAG_CHANGE Entity=10 tag=ZONE value=HAND",   # main de départ
        MULLIGAN_DONE,
        L + "FULL_ENTITY - Creating ID=11 CardID=",
        L + "    tag=ZONE value=DECK",  # ← ne compte PAS : déjà créée… non, créée après → entrée
    )
    (game,) = games
    draws = [e for e in game.events if isinstance(e, Draw)]
    assert len(draws) == 1
    assert draws[0].during_mulligan is True
    assert draws[0].entity_id == 10


def test_entree_de_deck_carte_creee():
    games = run(
        *BASE,
        MULLIGAN_DONE,
        L + "FULL_ENTITY - Creating ID=20 CardID=GVG_110t",  # bombe créée en deck
        L + "    tag=ZONE value=DECK",
        L + "    tag=CONTROLLER value=1",
        L + "    tag=CREATOR value=15",
    )
    (game,) = games
    entries = [e for e in game.events if isinstance(e, DeckEntry)]
    assert len(entries) == 1
    assert entries[0].created is True
    assert entries[0].card_id == "GVG_110t"


def test_retour_au_deck_carte_initiale():
    games = run(
        *BASE,
        L + "TAG_CHANGE Entity=10 tag=ZONE value=HAND",
        MULLIGAN_DONE,
        L + "TAG_CHANGE Entity=10 tag=ZONE value=DECK",  # renvoyée dans le deck
    )
    (game,) = games
    entries = [e for e in game.events if isinstance(e, DeckEntry)]
    assert len(entries) == 1
    assert entries[0].created is False  # carte du deck d'origine : « revient »


def test_jouer_une_carte():
    games = run(
        *BASE,
        L + "TAG_CHANGE Entity=10 tag=ZONE value=HAND",
        MULLIGAN_DONE,
        L + "TAG_CHANGE Entity=10 tag=ZONE value=PLAY",
    )
    (game,) = games
    plays = [e for e in game.events if isinstance(e, Play)]
    assert len(plays) == 1


def test_resultat_et_fin_de_partie():
    games = run(
        *BASE,
        L + "TAG_CHANGE Entity=alice#123 tag=PLAYSTATE value=WON ",
        L + "TAG_CHANGE Entity=bob#456 tag=PLAYSTATE value=LOST ",
        L + "TAG_CHANGE Entity=GameEntity tag=STATE value=COMPLETE ",
    )
    (game,) = games
    assert game.results == {"alice#123": "WON", "bob#456": "LOST"}
    assert game.complete is True


def test_deux_parties_dans_le_meme_log():
    games = run(*BASE, *BASE)
    assert len(games) == 2


# ---- chrono par tour et par joueur -----------------------------------------

def _at(ts: str) -> str:
    """Même préfixe de ligne que L, mais à l'horodatage voulu."""
    return f"D {ts} GameState.DebugPrintPower() - "


def _turn(ts: str, n: int) -> str:
    return _at(ts) + f"TAG_CHANGE Entity=GameEntity tag=TURN value={n} "


def _current(ts: str, entity_id: int) -> str:
    return _at(ts) + f"TAG_CHANGE Entity={entity_id} tag=CURRENT_PLAYER value=1 "


def test_temps_par_joueur_et_par_tour():
    # J1 réfléchit 10 s (tour 1), J2 en réfléchit 30 (tour 2), puis J1 reprend
    games = run(
        *BASE,
        _current("00:00:00.0000000", 2),   # entity 2 = PlayerID 1
        _turn("00:00:10.0000000", 2),
        _current("00:00:10.0000000", 3),   # entity 3 = PlayerID 2
        _turn("00:00:40.0000000", 3),
        _current("00:00:40.0000000", 2),
        _at("00:00:45.0000000") + "TAG_CHANGE Entity=GameEntity tag=STATE value=RUNNING ",
    )
    (game,) = games
    assert game.turns == 3
    # tour en cours : 5 s écoulées depuis le début du tour 3
    assert game.turn_seconds() == 5
    # J1 : 10 s du tour 1 + les 5 s du tour courant ; J2 : ses 30 s
    assert game.player_seconds(1) == 15
    assert game.player_seconds(2) == 30
    # la somme rend bien la durée de partie
    assert game.player_seconds(1) + game.player_seconds(2) == game.duration_seconds()


def test_chrono_sans_changement_de_tour():
    """Avant le premier TURN, tout le temps est au crédit du joueur courant."""
    games = run(
        *BASE,
        _current("00:00:00.0000000", 2),
        _at("00:00:12.0000000") + "TAG_CHANGE Entity=GameEntity tag=STATE value=RUNNING ",
    )
    (game,) = games
    assert game.player_seconds(1) == 12
    assert game.player_seconds(2) == 0


# ---- numéro de manche ------------------------------------------------------

def test_numero_de_manche_suit_le_mana():
    """HS compte un tour par CAMP : le tag TURN vaut le double de la manche.

    Régression vécue : le chrono affichait « tour 10 » alors que le joueur
    avait 5 cristaux. Le mana est le repère de tout le monde, c'est lui qui
    fait foi.
    """
    from src.cairn.game_state import round_number

    assert round_number(1) == 1 and round_number(2) == 1   # 1re manche
    assert round_number(3) == 2 and round_number(4) == 2
    assert round_number(9) == 5 and round_number(10) == 5  # 5 cristaux
    assert round_number(0) == 0                            # avant le 1er tour


def test_manche_coherente_avec_une_vraie_partie():
    """Sur une partie réelle, la manche vaut bien la moitié du tag TURN."""
    import pytest

    from src.cairn.game_state import replay_file, round_number
    from src.cairn.paths import FIXTURES_DIR

    logs = sorted(FIXTURES_DIR.glob("*/Power.log"))
    if not logs:
        pytest.skip("aucune fixture archivée")
    partie = max(replay_file(logs[0]), key=lambda g: g.turns)
    assert partie.turns > 1
    assert round_number(partie.turns) == (partie.turns + 1) // 2
    # une partie de 29 tours HS, c'est 15 manches pour le joueur
    assert round_number(29) == 15


# ---- mode spectateur --------------------------------------------------------

_P = "D 00:00:00.0000000 GameState.DebugPrintPower() - "


def _partie(compte_a: str, compte_b: str):
    """Partie minimale entre deux comptes donnés."""
    engine = GameStateEngine()
    engine.feed(parse_lines([
        _P + "CREATE_GAME",
        _P + "    GameEntity EntityID=1",
        _P + f"    Player EntityID=2 PlayerID=1 GameAccountId=[hi=144 lo={compte_a}]",
        _P + f"    Player EntityID=3 PlayerID=2 GameAccountId=[hi=144 lo={compte_b}]",
    ]))
    return engine.games[0]


def test_compte_du_joueur_capture():
    """Le « lo » du GameAccountId était parsé puis jeté : c'est pourtant le
    seul identifiant stable d'un joueur d'une partie à l'autre."""
    game = _partie("90443508", "12345")
    assert game.player_accounts == {1: "90443508", 2: "12345"}
    assert game.accounts() == {"90443508", "12345"}


def test_partie_spectateur_reconnue():
    """Aucun des deux comptes n'est le nôtre : on regarde quelqu'un d'autre."""
    mienne = _partie("90443508", "12345")
    regardee = _partie("60731110", "67366134")

    assert mienne.is_spectated("90443508") is False
    assert regardee.is_spectated("90443508") is True


def test_sans_compte_connu_on_ne_filtre_rien():
    """Tant que le compte n'est pas appris, ne rien casser prime sur filtrer :
    un faux positif ferait disparaître de vraies parties de l'historique."""
    assert _partie("60731110", "67366134").is_spectated(None) is False
    assert _partie("60731110", "67366134").is_spectated("") is False


def test_joueur_local_par_le_compte_et_non_par_les_pioches():
    """En spectateur les pioches des DEUX camps sont révélées, donc le
    décompte de pioches tranche sur un écart de hasard. Le compte, lui, est
    une identité."""
    game = _partie("90443508", "12345")
    assert game.local_player_id("90443508") == 1
    assert game.local_player_id("12345") == 2


def test_compte_appris_par_majorite():
    """On est dans toutes ses parties et dans aucune de celles qu'on regarde."""
    parties = [
        _partie("90443508", "111"),
        _partie("90443508", "222"),
        _partie("333", "90443508"),
        _partie("60731110", "67366134"),   # une session spectateur
    ]
    assert learn_own_account(parties) == "90443508"


def test_apprentissage_refuse_de_deviner():
    """Deux garde-fous : trop peu de parties, ou une égalité en tête. Une
    déduction fausse est pire que pas de déduction."""
    assert learn_own_account([_partie("1", "2")]) is None          # 1 partie
    assert learn_own_account([_partie("1", "2")] * 2, minimum=2) is None  # égalité
