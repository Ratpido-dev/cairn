"""Tests de la vue deck — synthétiques + intégration sur la session réelle."""

import re

import pytest

from src.cairn.cards_db import CardsDb
from src.cairn.decks_log import PlayerDeck, QueueEvent, parse_queue_events
from src.cairn.deck_view import compute_deck_view, pick_queued_deck
from src.cairn.game_state import Game, replay_file
from src.cairn.paths import CARDS_JSON, FIXTURES_DIR

FIXTURE_DIR = FIXTURES_DIR / "Hearthstone_2026_08_01_00_06_06"

pytestmark = pytest.mark.skipif(
    not (FIXTURE_DIR / "Power.log").is_file() or not CARDS_JSON.is_file(),
    reason="fixture ou base de cartes absente",
)


@pytest.fixture(scope="module")
def db():
    return CardsDb.load()


@pytest.fixture(scope="module")
def games():
    return replay_file(FIXTURE_DIR / "Power.log")


@pytest.fixture(scope="module")
def queue_events():
    return parse_queue_events(
        (FIXTURE_DIR / "Decks.log").read_text(encoding="utf-8", errors="replace")
    )


def test_queue_events_lus(queue_events):
    # 4 mises en file dans la session (la 4e : re-file après l'annulation)
    assert len(queue_events) == 4
    assert all(q.deck.name == "Thief Priest" for q in queue_events)
    assert queue_events[0].ts.startswith("00:07:54")


def test_pick_deck_par_horodatage(queue_events, games):
    for game in games:
        deck = pick_queued_deck(queue_events, game)
        assert deck is not None and deck.name == "Thief Priest"


def test_vue_partie_1(db, games, queue_events):
    game = games[0]
    view = compute_deck_view(game, pick_queued_deck(queue_events, game), db)

    assert view.deck_name == "Thief Priest"
    # Le battletag de l'adversaire n'est pas écrit en dur : c'est la donnée
    # personnelle d'un tiers, et la fixture peut être pseudonymisée.
    assert re.fullmatch(r"[^\s#]+#\d+", view.opponent_name)
    assert view.result == "WON"

    # deck de 20 cartes : total des lignes DE DÉPART = 20. Les cartes arrivées
    # en cours de partie sont dans la même liste, marquées « gift » — c'est
    # bien dans le deck qu'elles sont (cf. la section « ENTRÉES » supprimée).
    base = [r for r in view.rows if not r.gift]
    assert sum(r.total for r in base) == 20
    assert any(r.gift for r in view.rows), "Azalina ajoute des cartes au deck"
    assert all(r.origin for r in view.rows if r.gift and r.name == "?")
    # partie de 29 tours : le deck est très entamé, jamais négatif
    assert 0 <= sum(r.remaining for r in base) <= 10
    assert all(0 <= r.remaining <= r.total for r in view.rows)
    # l'adversaire a joué des cartes identifiées
    assert len(view.opponent_plays) >= 5
    # tri par coût croissant, les coûts inconnus (cartes cachées) en dernier
    costs = [r.cost if r.cost >= 0 else 99 for r in view.rows]
    assert costs == sorted(costs)
    # rareté renseignée sur chaque ligne (code couleur du panneau)
    # (une entrée cachée n'a pas de rareté connue : elle ne compte pas ici)
    rarities = {r.rarity for r in view.rows if r.rarity}
    assert rarities <= {"FREE", "COMMON", "RARE", "EPIC", "LEGENDARY"}
    assert "LEGENDARY" in rarities  # Azalina est dans Thief Priest
    assert any(p.rarity in {"COMMON", "RARE", "EPIC", "LEGENDARY"} for p in view.opponent_plays)


def test_vue_partie_tronquee_sans_crash(db, games, queue_events):
    game = games[2]  # interrompue au mulligan
    view = compute_deck_view(game, pick_queued_deck(queue_events, game), db)
    assert view.result == ""
    base = [r for r in view.rows if not r.gift]
    assert sum(r.total for r in base) == 20
    # mulligan seul : au plus la main de départ est sortie du deck
    assert sum(r.remaining for r in base) >= 20 - 5


def test_vue_sans_deck_connu(db, games):
    view = compute_deck_view(games[0], None, db)
    # sans deckstring il ne reste que les cartes ARRIVÉES en cours de partie
    assert all(r.gift for r in view.rows)
    # le reste fonctionne quand même
    assert re.fullmatch(r"[^\s#]+#\d+", view.opponent_name)


# ---- main adverse connue, cimetières -----------------------------------------

def test_main_adverse_connue_sur_partie_reelle(db, games, queue_events):
    """HS ne révèle l'id que de certaines cartes en main adverse : on doit les
    lister avec, quand elle existe, la carte qui les a créées."""
    game = games[1]
    view = compute_deck_view(game, pick_queued_deck(queue_events, game), db)

    assert view.opponent_hand, "au moins une carte adverse était révélée"
    card = view.opponent_hand[0]
    assert card.label == "Deuxième portail vers Argus"
    assert card.origin == "Ur’zul en fuite"      # créateur retrouvé
    assert card.count >= 1 and card.card_id


def test_cimetieres_separes_par_camp(db, games, queue_events):
    game = games[0]
    view = compute_deck_view(game, pick_queued_deck(queue_events, game), db)

    assert view.my_graveyard and view.opp_graveyard
    # tri du plus cher au moins cher : ce qu'on veut voir face aux résurrections
    couts = [d.cost for d in view.opp_graveyard]
    assert couts == sorted(couts, reverse=True)
    # les doublons sont regroupés, jamais dupliqués
    assert len({d.card_id for d in view.opp_graveyard}) == len(view.opp_graveyard)
    assert all(d.count >= 1 for d in view.opp_graveyard)
    # aucun serviteur ne peut appartenir aux deux cimetières via la même entité
    assert all(d.label for d in view.my_graveyard)


def test_partie_au_mulligan_sans_morts(db, games, queue_events):
    game = games[2]  # interrompue au mulligan
    view = compute_deck_view(game, pick_queued_deck(queue_events, game), db)
    assert view.my_graveyard == [] and view.opp_graveyard == []


# ---- ma main ---------------------------------------------------------------

def test_ma_main(db, games, queue_events):
    game = games[0]
    view = compute_deck_view(game, pick_queued_deck(queue_events, game), db)

    assert view.my_hand, "la main du joueur local doit être connue"
    # une main HS ne dépasse jamais 10 cartes (comptées avec leurs doublons)
    assert sum(c.count for c in view.my_hand) <= 10
    assert all(c.label and c.card_id for c in view.my_hand)
    # tri par coût croissant, comme la liste du deck
    couts = [c.cost for c in view.my_hand]
    assert couts == sorted(couts)


def test_ma_main_ne_contient_ni_heros_ni_pouvoir(db, games, queue_events):
    """Le héros et son pouvoir vivent en PLAY toute la partie. C'est ce qui a
    condamné l'ancienne section « ailleurs » : elle affichait « Tyrande
    Murmevent » au milieu des cartes du joueur. Rien de tel ne doit revenir."""
    game = games[0]
    view = compute_deck_view(game, pick_queued_deck(queue_events, game), db)
    types = {db.by_card_id.get(c.card_id, {}).get("type") for c in view.my_hand}
    assert "HERO" not in types and "HERO_POWER" not in types


def test_section_ailleurs_supprimee():
    """Section retirée le 05/08/2026 : elle mélangeait le héros du joueur, ses
    jetons de Préparation et ses sorts déjà lancés, sans usage identifiable."""
    from src.cairn.deck_view import DeckView

    assert not hasattr(DeckView(), "my_elsewhere")


# ---- bouts du deck connus (haut / fond) ------------------------------------
#
# Hearthstone ne publie pas l'ordre du deck de façon exploitable. La position
# n'est donc connue que par l'effet qui l'a posée — d'où ces tests synthétiques :
# aucune fixture archivée ne contient de carte « au fond du deck ».

from src.cairn.cards_fetch import deck_position  # noqa: E402
from src.cairn.game_state import GameStateEngine  # noqa: E402
from src.cairn.power_log import parse_lines  # noqa: E402

_L = "D 00:00:00.0000000 GameState.DebugPrintPower() - "
_G = "D 00:00:00.0000000 GameState.DebugPrintGame() - "


class _FakeDb:
    """Base minimale : deux cartes, dont une qui pose au fond du deck."""

    def __init__(self):
        self.by_card_id = {
            "SEMEUR": {"id": "SEMEUR", "name": "Semeur", "cost": 3, "rarity": "RARE"},
            "GRAINE": {"id": "GRAINE", "name": "Graine", "cost": 1, "rarity": "COMMON"},
            "BANAL": {"id": "BANAL", "name": "Banal", "cost": 2, "rarity": "COMMON"},
        }
        self.by_dbf_id = {}
        self.deck_bottom_ids = {"SEMEUR"}
        self.deck_top_ids = set()

    def localized_name(self, card_id, lang="fr"):
        card = self.by_card_id.get(card_id or "")
        return card["name"] if card else ""


def _partie_avec_entree(creator_card_id: str, entree: str = "GRAINE"):
    """Une carte entre dans le deck du joueur 1, créée par ``creator``.

    ``entree=""`` reproduit le cas courant d'une carte engendrée dont HS ne
    publie jamais l'identité : la ligne FULL_ENTITY n'a pas de CardID.
    """
    lignes = [
        _L + "CREATE_GAME",
        _L + "    GameEntity EntityID=1",
        _L + "    Player EntityID=2 PlayerID=1 GameAccountId=[hi=1 lo=2]",
        _L + "    Player EntityID=3 PlayerID=2 GameAccountId=[hi=1 lo=3]",
        # le créateur, en jeu
        _L + f"FULL_ENTITY - Creating ID=20 CardID={creator_card_id}",
        _L + "    tag=ZONE value=PLAY",
        _L + "    tag=CONTROLLER value=1",
        # une pioche révélée : c'est ce qui désigne le joueur local
        _L + "FULL_ENTITY - Creating ID=30 CardID=BANAL",
        _L + "    tag=ZONE value=DECK",
        _L + "    tag=CONTROLLER value=1",
        _L + "TAG_CHANGE Entity=[entityName=x id=2 zone=PLAY zonePos=0 cardId= player=1] "
             "tag=MULLIGAN_STATE value=DONE",
        _L + "TAG_CHANGE Entity=30 tag=ZONE value=HAND",
        # la carte posée dans le deck par le créateur
        _L + f"FULL_ENTITY - Creating ID=40 CardID={entree}",
        _L + "    tag=ZONE value=DECK",
        _L + "    tag=CONTROLLER value=1",
        _L + "    tag=CREATOR value=20",
    ]
    engine = GameStateEngine()
    engine.feed(parse_lines(lignes))
    return engine.games[0]


def test_carte_posee_au_fond_du_deck():
    db = _FakeDb()
    view = compute_deck_view(_partie_avec_entree("SEMEUR"), None, db)
    assert [e.label for e in view.deck_bottom] == ["Graine"]
    assert view.deck_bottom[0].origin == "Semeur"
    assert view.deck_top == []
    # elle NE doit PAS réapparaître dans les entrées génériques : deux lignes
    # feraient croire à deux exemplaires
    assert all(e.label != "Graine" for e in view.entries)


def test_entree_ordinaire_reste_dans_les_entrees():
    db = _FakeDb()
    view = compute_deck_view(_partie_avec_entree("BANAL"), None, db)
    assert view.deck_bottom == [] and view.deck_top == []
    assert [e.label for e in view.entries] == ["Graine"]


def test_entree_ordinaire_apparait_dans_la_liste_du_deck():
    """Une carte ajoutée en cours de partie EST dans le deck : elle s'affiche
    avec les autres, marquée d'un cadeau, au lieu d'une section séparée qu'il
    fallait aller consulter en plus de la liste."""
    db = _FakeDb()
    view = compute_deck_view(_partie_avec_entree("BANAL"), None, db)
    cadeaux = [r for r in view.rows if r.gift]
    assert [(r.name, r.origin, r.remaining) for r in cadeaux] == [("Graine", "Banal", 1)]
    # une entrée localisée (fond/haut de deck) garde sa section : elle porte
    # une information de plus, la POSITION, que la liste du deck ne rend pas
    localisee = compute_deck_view(_partie_avec_entree("SEMEUR"), None, db)
    assert [r.name for r in localisee.rows if r.gift] == []


def test_carte_cachee_ajoutee_au_deck_sans_cout():
    """Carte entrée dans le deck sans identité : ni gemme de mana (coût -1) ni
    illustration, mais toujours son origine — c'est tout ce qu'on en sait."""
    db = _FakeDb()
    game = _partie_avec_entree("BANAL", entree="")   # identité jamais publiée
    ligne = [r for r in compute_deck_view(game, None, db).rows if r.gift][0]
    assert (ligne.name, ligne.cost, ligne.card_id) == ("?", -1, "")
    assert ligne.origin == "Banal"


def test_base_ancienne_sans_drapeau_pos():
    """Base de cartes antérieure au drapeau : le suivi se tait, sans planter."""
    db = _FakeDb()
    db.deck_bottom_ids = set()
    view = compute_deck_view(_partie_avec_entree("SEMEUR"), None, db)
    assert view.deck_bottom == []
    assert [e.label for e in view.entries] == ["Graine"]


@pytest.mark.parametrize(
    "texte, attendu",
    [
        ("<b>Râle d’agonie :</b> place un arpenteur au fond de votre deck.", "bottom"),
        ("Place un serviteur adverse au fond de votre deck.", "bottom"),
        ("Place cette carte sur le dessus de votre deck.", "top"),
        ("place un serviteur au-dessus de son deck", "top"),
        ("Inflige 3 points de dégâts.", ""),
        (None, ""),
    ],
)
def test_lecture_du_bout_de_deck_dans_le_texte(texte, attendu):
    assert deck_position(texte) == attendu


# ---- origine et identité publiées après coup --------------------------------
#
# Deux tags, un même piège : HS ne dit pas tout au moment où la carte entre dans
# le deck. Les copies d'Azalina n'ont que DISPLAYED_CREATOR (CREATOR n'arrive
# qu'à la révélation), et les jetons engendrés arrivent sans CardID. La vue
# étant recalculée à chaque poll, elle doit relire l'état courant.


def _partie_creation_tardive(tag: str, revele_apres: bool):
    """Entrée dans le deck dont l'origine (et l'identité) arrivent plus tard."""
    lignes = [
        _L + "CREATE_GAME",
        _L + "    GameEntity EntityID=1",
        _L + "    Player EntityID=2 PlayerID=1 GameAccountId=[hi=1 lo=2]",
        _L + "    Player EntityID=3 PlayerID=2 GameAccountId=[hi=1 lo=3]",
        _L + "FULL_ENTITY - Creating ID=20 CardID=SEMEUR",
        _L + "    tag=ZONE value=PLAY",
        _L + "    tag=CONTROLLER value=1",
        _L + "FULL_ENTITY - Creating ID=30 CardID=BANAL",
        _L + "    tag=ZONE value=DECK",
        _L + "    tag=CONTROLLER value=1",
        _L + "TAG_CHANGE Entity=[entityName=x id=2 zone=PLAY zonePos=0 cardId= player=1] "
             "tag=MULLIGAN_STATE value=DONE",
        _L + "TAG_CHANGE Entity=30 tag=ZONE value=HAND",
        # la carte entre dans le deck SANS identité ni CREATOR
        _L + "FULL_ENTITY - Creating ID=40 CardID=",
        _L + "    tag=ZONE value=DECK",
        _L + "    tag=CONTROLLER value=1",
        # …l'origine n'est publiée qu'ensuite, et via l'autre tag
        _L + f"TAG_CHANGE Entity=40 tag={tag} value=20",
    ]
    if revele_apres:
        lignes.append(
            _L + "SHOW_ENTITY - Updating Entity=[entityName=x id=40 zone=DECK "
                 "zonePos=0 cardId= player=1] CardID=GRAINE"
        )
    engine = GameStateEngine()
    engine.feed(parse_lines(lignes))
    return engine.games[0]


@pytest.mark.parametrize("tag", ["CREATOR", "DISPLAYED_CREATOR"])
def test_origine_publiee_apres_l_entree(tag):
    """DISPLAYED_CREATOR compte autant que CREATOR : c'est le seul tag posé sur
    les 20 copies d'Azalina, et sans lui le fond de deck reste vide."""
    view = compute_deck_view(_partie_creation_tardive(tag, False), None, _FakeDb())
    assert [e.origin for e in view.deck_bottom] == ["Semeur"]


def test_identite_publiee_apres_l_entree():
    """Un jeton entre anonyme puis se révèle : la ligne doit le nommer."""
    view = compute_deck_view(_partie_creation_tardive("CREATOR", True), None, _FakeDb())
    assert [(e.label, e.known) for e in view.deck_bottom] == [("Graine", True)]


def test_entree_restee_cachee_affiche_un_point_d_interrogation():
    view = compute_deck_view(_partie_creation_tardive("CREATOR", False), None, _FakeDb())
    assert [(e.label, e.known) for e in view.deck_bottom] == [("?", False)]


# ---- main adverse : tour d'arrivée et origine --------------------------------


def _partie_main_adverse():
    """L'adversaire garde une carte du mulligan et en reçoit une au tour 3."""
    lignes = [
        _L + "CREATE_GAME",
        _L + "    GameEntity EntityID=1",
        _L + "    Player EntityID=2 PlayerID=1 GameAccountId=[hi=1 lo=2]",
        _L + "    Player EntityID=3 PlayerID=2 GameAccountId=[hi=1 lo=3]",
        # carte adverse de la main de départ
        _L + "FULL_ENTITY - Creating ID=50 CardID=",
        _L + "    tag=ZONE value=DECK",
        _L + "    tag=CONTROLLER value=2",
        _L + "TAG_CHANGE Entity=50 tag=ZONE value=HAND",
        # notre pioche révélée : désigne le joueur local
        _L + "FULL_ENTITY - Creating ID=30 CardID=BANAL",
        _L + "    tag=ZONE value=DECK",
        _L + "    tag=CONTROLLER value=1",
        _L + "TAG_CHANGE Entity=[entityName=x id=2 zone=PLAY zonePos=0 cardId= player=1] "
             "tag=MULLIGAN_STATE value=DONE",
        _L + "TAG_CHANGE Entity=30 tag=ZONE value=HAND",
        _L + "TAG_CHANGE Entity=1 tag=TURN value=3",
        # le créateur adverse, puis la carte qu'il donne en main
        _L + "FULL_ENTITY - Creating ID=60 CardID=SEMEUR",
        _L + "    tag=ZONE value=PLAY",
        _L + "    tag=CONTROLLER value=2",
        _L + "FULL_ENTITY - Creating ID=61 CardID=GRAINE",
        _L + "    tag=ZONE value=HAND",
        _L + "    tag=CONTROLLER value=2",
        _L + "    tag=CREATOR value=60",
    ]
    engine = GameStateEngine()
    engine.feed(parse_lines(lignes))
    return engine.games[0]


def test_main_adverse_tour_d_arrivee_et_origine():
    view = compute_deck_view(_partie_main_adverse(), None, _FakeDb())
    slots = view.opponent_hand_slots
    assert len(slots) == 2

    depart, tardive = slots
    # la carte du mulligan reste cachée mais on sait qu'il la garde depuis le début
    assert (depart.known, depart.from_mulligan, depart.cost) == (False, True, -1)
    assert depart.label == "?"
    # celle-là est connue, datée, et rattachée à son créateur. TURN=3 côté HS
    # (un tour par camp) = manche 2 telle que le joueur la compte.
    assert (tardive.label, tardive.turn, tardive.origin) == ("Graine", 2, "Semeur")
    assert tardive.from_mulligan is False


def test_main_adverse_ordonnee_comme_son_eventail():
    """Les pastilles se posent sous SES cartes : l'ordre doit être celui de sa
    main (tag ZONE_POSITION), pas l'ordre d'arrivée — sinon chaque pastille
    désigne la mauvaise carte."""
    game = _partie_main_adverse()
    engine = GameStateEngine()
    engine.games.append(game)
    engine._game = game
    # la carte donnée par le créateur est glissée EN TÊTE de sa main
    engine.feed(parse_lines([
        _L + "TAG_CHANGE Entity=50 tag=ZONE_POSITION value=2",
        _L + "TAG_CHANGE Entity=61 tag=ZONE_POSITION value=1",
    ]))
    slots = compute_deck_view(game, None, _FakeDb()).opponent_hand_slots
    assert [s.label for s in slots] == ["Graine", "?"]
    assert [s.pos for s in slots] == [1, 2]
    # l'identité de la créatrice suit, pour l'aperçu au survol de la pastille
    assert slots[0].creator_card_id == "SEMEUR"


def test_carte_jouee_quitte_les_emplacements_de_main():
    """Une carte posée sort de la main ET perd sa date : si elle y revient plus
    tard, c'est une nouvelle arrivée qu'il faut redater."""
    game = _partie_main_adverse()
    engine = GameStateEngine()
    engine.games.append(game)
    engine._game = game
    engine.feed(parse_lines([_L + "TAG_CHANGE Entity=61 tag=ZONE value=PLAY"]))

    view = compute_deck_view(game, None, _FakeDb())
    assert [s.label for s in view.opponent_hand_slots] == ["?"]
    assert game.entities[61].hand_turn is None


# ---- cartes identifiées dans le deck adverse -------------------------------

def test_deck_adverse_ne_montre_que_les_cartes_revelees(db, games, queue_events):
    """HS ne révèle l'identité d'une carte du deck d'en face que si un effet
    l'a montrée. La section doit donc rester courte, et surtout ne jamais
    contenir de carte cachée déguisée en carte connue."""
    for game in games:
        view = compute_deck_view(game, pick_queued_deck(queue_events, game), db)
        assert len(view.opp_deck_known) <= 8, "section noyée : ce n'est pas un deck complet"
        for carte in view.opp_deck_known:
            assert carte.card_id, "une carte sans identité n'a rien à faire ici"
            assert carte.label and carte.label != "?"


def test_deck_adverse_vide_au_mulligan(db, games, queue_events):
    game = games[2]  # partie interrompue au mulligan
    view = compute_deck_view(game, pick_queued_deck(queue_events, game), db)
    assert view.opp_deck_known == []


# ---- la pièce adverse, par déduction ---------------------------------------

def _partie_avec_piece(premier: int, piece_jouee: bool = False):
    """Partie synthétique : qui commence, et l'adversaire a-t-il joué sa pièce."""
    from src.cairn.game_state import Draw, Entity, Game

    g = Game(player_names={1: "moi", 2: "adv"}, player_entity={1: 10, 2: 11})
    g.turns = 3
    for eid, pid in ((10, "1"), (11, "2")):
        tags = {"CONTROLLER": pid, "CARDTYPE": "PLAYER"}
        if int(pid) == premier:
            tags["FIRST_PLAYER"] = "1"
        g.entities[eid] = Entity(entity_id=eid, tags=tags)
    # main de départ adverse : trois cartes, la pièce est la dernière créée
    for eid in (200, 201, 202):
        e = Entity(entity_id=eid, tags={"CONTROLLER": "2", "ZONE": "HAND"})
        e.hand_from_mulligan = True
        g.entities[eid] = e
    if piece_jouee:
        g.entities[300] = Entity(
            entity_id=300, card_id="EDR_COIN2",
            tags={"CONTROLLER": "2", "ZONE": "GRAVEYARD", "COIN_CARD": "1"},
        )
    g.events.append(Draw(player_id=1, entity_id=1, card_id="X", during_mulligan=True))
    return g


def test_la_piece_adverse_est_deduite(db):
    """HS ne révèle jamais la main adverse. Mais la pièce va à celui qui joue
    en SECOND et arrive après le mulligan : c'est sa dernière carte de départ."""
    view = compute_deck_view(_partie_avec_piece(premier=1), None, db)
    pieces = [s for s in view.opponent_hand_slots if s.label == "La pièce"]
    assert len(pieces) == 1 and pieces[0].known


def test_pas_de_piece_si_l_adversaire_commence(db):
    view = compute_deck_view(_partie_avec_piece(premier=2), None, db)
    assert not [s for s in view.opponent_hand_slots if s.label == "La pièce"]


def test_la_piece_disparait_une_fois_jouee(db):
    """Sinon elle resterait affichée toute la partie — pire que rien."""
    view = compute_deck_view(_partie_avec_piece(premier=1, piece_jouee=True), None, db)
    assert not [s for s in view.opponent_hand_slots if s.label == "La pièce"]


def _partie_deck_adverse_revele():
    """Deux cartes du deck adverse révélées ; il en joue une, garde l'autre.

    C'est le scénario d'Azalina ou d'un Découvre qui montre le fond du deck :
    l'identité est connue AVANT que la carte soit jouable, et c'est justement
    l'intervalle où l'information vaut quelque chose.
    """
    lignes = [
        _L + "CREATE_GAME",
        _L + "    GameEntity EntityID=1",
        _L + "    Player EntityID=2 PlayerID=1 GameAccountId=[hi=1 lo=2]",
        _L + "    Player EntityID=3 PlayerID=2 GameAccountId=[hi=1 lo=3]",
        # deux exemplaires anonymes dans son deck
        _L + "FULL_ENTITY - Creating ID=70 CardID=",
        _L + "    tag=ZONE value=DECK",
        _L + "    tag=CONTROLLER value=2",
        _L + "FULL_ENTITY - Creating ID=71 CardID=",
        _L + "    tag=ZONE value=DECK",
        _L + "    tag=CONTROLLER value=2",
        # un effet révèle les deux, toujours au deck
        _L + "SHOW_ENTITY - Updating Entity=70 CardID=SEMEUR",
        _L + "SHOW_ENTITY - Updating Entity=71 CardID=SEMEUR",
        # nos propres pioches, révélées : c'est ce qui désigne le joueur local
        # (cf. Game.local_player_id). Il en faut plus que de pioches adverses
        # révélées, sinon Azalina nous ferait changer de camp.
        _L + "FULL_ENTITY - Creating ID=30 CardID=BANAL",
        _L + "    tag=ZONE value=DECK",
        _L + "    tag=CONTROLLER value=1",
        _L + "FULL_ENTITY - Creating ID=31 CardID=GRAINE",
        _L + "    tag=ZONE value=DECK",
        _L + "    tag=CONTROLLER value=1",
        _G + "PlayerID=1, PlayerName=Moi#1111",
        _G + "PlayerID=2, PlayerName=UNKNOWN HUMAN PLAYER",
        _L + "TAG_CHANGE Entity=[entityName=x id=2 zone=PLAY zonePos=0 cardId= player=1] "
             "tag=MULLIGAN_STATE value=DONE",
        _L + "TAG_CHANGE Entity=30 tag=ZONE value=HAND",
        _L + "TAG_CHANGE Entity=31 tag=ZONE value=HAND",
    ]
    engine = GameStateEngine()
    engine.feed(parse_lines(lignes))
    return engine


def test_carte_revelee_reste_affichee_barree_une_fois_jouee():
    """LE point de la section : une carte révélée puis jouée ne doit pas
    disparaître. Avant, elle s'effaçait à la seconde où l'adversaire la posait
    — donc à l'instant précis où l'information devenait vérifiable."""
    engine = _partie_deck_adverse_revele()
    game = engine.games[0]

    vue = compute_deck_view(game, None, _FakeDb())
    assert [(c.label, c.count, c.struck) for c in vue.opp_deck_known] == [
        ("Semeur", 2, False)
    ], "les deux exemplaires dorment encore dans le deck"

    # il en pioche un et le joue
    engine.feed(parse_lines([
        _L + "TAG_CHANGE Entity=70 tag=ZONE value=HAND",
        _L + "TAG_CHANGE Entity=70 tag=ZONE value=PLAY",
    ]))
    vue = compute_deck_view(game, None, _FakeDb())

    assert [(c.label, c.count, c.struck) for c in vue.opp_deck_known] == [
        ("Semeur", 1, False),   # celui qui reste, en clair
        ("Semeur", 1, True),    # celui qui est sorti, barré
    ], "deux lignes distinctes : sinon le compteur ment sur ce qui dort encore"


def test_carte_jamais_revelee_reste_absente():
    """Le garde-fou : la marque ne doit venir QUE d'une identité connue au
    deck, jamais d'une carte anonyme ni d'une carte de notre propre camp."""
    engine = _partie_deck_adverse_revele()
    game = engine.games[0]
    engine.feed(parse_lines([
        _L + "FULL_ENTITY - Creating ID=80 CardID=",
        _L + "    tag=ZONE value=DECK",
        _L + "    tag=CONTROLLER value=2",
        _L + "TAG_CHANGE Entity=80 tag=ZONE value=HAND",
    ]))
    vue = compute_deck_view(game, None, _FakeDb())
    assert all(c.card_id for c in vue.opp_deck_known)
    assert sum(c.count for c in vue.opp_deck_known) == 2, "l'anonyme ne s'invite pas"


# ---- d'où viennent les cartes que l'adversaire joue -------------------------

def test_cartes_jouees_par_l_adversaire_portent_leur_origine(db, games, queue_events):
    """Distinguer ce qui sort de son deck de ce qu'un effet lui a donné.

    Mesuré sur les archives : **29 % des cartes jouées par l'adversaire sont
    créées** (Azalina, Atlas de Godfrey, Bénédiction de la lune, Découvertes,
    vols…). Sans cette distinction, un adversaire qui enchaîne dix cartes
    volées se lit comme un deck de dix cartes qu'il n'a jamais eu — ce qui
    fausse le seul calcul qui compte en fin de partie : ce qu'il lui reste.
    """
    trouve = False
    for game in games:
        view = compute_deck_view(game, pick_queued_deck(queue_events, game), db)
        for p in view.opponent_plays:
            # cohérence : « créée » et « origine nommée » vont ensemble
            if p.origin:
                assert p.created, f"{p.label} a une origine mais n'est pas marquée créée"
            if p.created:
                trouve = True
        # une carte sortie du deck ne doit pas être marquée comme offerte
        sans_origine = [p for p in view.opponent_plays if not p.created]
        assert all(p.origin == "" for p in sans_origine)
    assert trouve, "aucune carte créée détectée : la fixture contient Azalina"


def test_deck_et_cadeaux_ne_se_confondent_pas_dans_le_compteur(db, games, queue_events):
    """Deux exemplaires, un du deck et un offert, font DEUX lignes.

    Les regrouper masquerait exactement l'information recherchée : combien il
    en avait vraiment, et combien on lui a données.
    """
    for game in games:
        view = compute_deck_view(game, pick_queued_deck(queue_events, game), db)
        cles = [(p.label, p.origin) for p in view.opponent_plays]
        assert len(cles) == len(set(cles)), "deux lignes identiques non fusionnées"
    # le tri met ce qui vient de son deck EN PREMIER : c'est ça qu'on lit pour
    # savoir ce qu'il lui reste, les cadeaux ne sont qu'un commentaire
    for game in games:
        view = compute_deck_view(game, pick_queued_deck(queue_events, game), db)
        crees = [p.created for p in view.opponent_plays]
        assert crees == sorted(crees), "les cartes offertes doivent finir la liste"


# ---- deck joué : ce qu'on peut savoir, et ce qu'on ne peut pas -------------

def _queue(ts: str, nom: str) -> QueueEvent:
    return QueueEvent(ts=ts, deck=PlayerDeck(name=nom, deck_id=1, deckstring=""))


def test_partie_amicale_aucun_deck_devine():
    """Un défi direct n'est pas une mise en file : Hearthstone n'écrit aucun
    « Finding Game With Deck ». Se rabattre sur la dernière mise en file connue
    affichait le deck de la partie classée précédente, winrate compris."""
    game = Game(ts="20:00:00.0000000", game_type="GT_VS_FRIEND")
    assert pick_queued_deck([_queue("14:00:00.0000000", "Thief Priest")], game) is None


def test_partie_classee_prend_la_mise_en_file_precedente():
    """Le comportement normal ne doit pas bouger."""
    game = Game(ts="20:00:00.0000000", game_type="GT_RANKED")
    events = [_queue("14:00:00.0000000", "Thief Priest"), _queue("19:59:00.0000000", "Attack Druid")]
    deck = pick_queued_deck(events, game)
    assert deck is not None and deck.name == "Attack Druid"


# Deux listes RÉELLES de la même classe (même héros : « AAECAZirBA… »), donc
# seules les cartes peuvent les départager — c'est ce que le test vérifie.
DECKSTRING_A = ("AAECAZirBAjDgwf1pQfRpgeIvgeRxgeqyQek2QeU2wcL"
                "s4cH+ZsHi7EH1rIHhsQHksQHrMYHndkHk9oHrdoH+d4HAAA=")
DECKSTRING_B = ("AAECAZirBAaXoASzhweIvgfXwweRxgeT2gcM/Z4EheYGx4cHn5YH"
                "6KUHi7EH1rIH1rwHhsQHksQHm8QHrMYHAAA=")


# ---- reconnaissance du deck sans mise en file (partie amicale) -------------

@pytest.fixture(scope="module")
def _db_cartes():
    from src.cairn.cards_db import CardsDb
    return CardsDb.load()


def _partie_avec(db, deckstring: str, piochees: int, hero_class: str = None):
    """Une partie où le joueur 1 pioche les N premières cartes d'une liste."""
    from src.cairn.deckstring import decode_deckstring
    from src.cairn.game_state import Draw, Entity

    d = decode_deckstring(deckstring)
    game = Game(ts="10:00:00.0000000")
    game.player_names = {1: "moi", 2: "lui"}
    game.player_entity = {1: 1, 2: 2}
    # héros : donne sa classe au joueur local
    heros = db.by_dbf_id.get(d.heroes[0], {})
    game.entities[99] = Entity(
        entity_id=99, card_id=heros.get("id"),
        tags={"CARDTYPE": "HERO", "CONTROLLER": "1"},
    )
    for i, (dbf, _n) in enumerate(d.cards[:piochees]):
        carte = db.by_dbf_id.get(dbf, {})
        game.events.append(Draw(player_id=1, entity_id=100 + i,
                                card_id=carte.get("id"), during_mulligan=False))
    return game


def test_deck_reconnu_par_les_cartes_qui_en_sortent(_db_cartes):
    """Le cas qui manquait : en amical, aucune mise en file n'est journalisée,
    mais les listes du joueur sont connues — on reconnaît la sienne."""
    from src.cairn.deck_view import identifier_deck
    from src.cairn.decks_log import PlayerDeck

    a = PlayerDeck(name="A", deck_id=1, deckstring=DECKSTRING_A)
    b = PlayerDeck(name="B", deck_id=2, deckstring=DECKSTRING_B)
    game = _partie_avec(_db_cartes, DECKSTRING_A, piochees=6)
    trouve = identifier_deck(game, [a, b], _db_cartes)
    assert trouve is not None and trouve.name == "A"


def test_aucun_deck_rendu_tant_que_le_doute_subsiste(_db_cartes):
    """Deux listes candidates et rien de discriminant : on se tait plutôt que
    d'afficher un deck au hasard."""
    from src.cairn.deck_view import identifier_deck
    from src.cairn.decks_log import PlayerDeck

    a = PlayerDeck(name="A", deck_id=1, deckstring=DECKSTRING_A)
    meme = PlayerDeck(name="A bis", deck_id=2, deckstring=DECKSTRING_A)
    game = _partie_avec(_db_cartes, DECKSTRING_A, piochees=4)
    assert identifier_deck(game, [a, meme], _db_cartes) is None


def test_sans_liste_connue_rien_n_est_invente(_db_cartes):
    from src.cairn.deck_view import identifier_deck
    game = _partie_avec(_db_cartes, DECKSTRING_A, piochees=6)
    assert identifier_deck(game, [], _db_cartes) is None
