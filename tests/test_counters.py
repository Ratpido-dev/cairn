"""Tests des compteurs contextuels — sur la session réelle."""

import pytest

from src.cairn.cards_db import CardsDb
from src.cairn.counters import compute_counters
from src.cairn.decks_log import parse_queue_events
from src.cairn.deck_view import compute_deck_view, pick_queued_deck
from src.cairn.game_state import replay_file
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
def setup(db):
    games = replay_file(FIXTURE_DIR / "Power.log")
    queue = parse_queue_events(
        (FIXTURE_DIR / "Decks.log").read_text(encoding="utf-8", errors="replace")
    )
    return games, queue


def _counters_for(games, queue, db, idx):
    game = games[idx]
    view = compute_deck_view(game, pick_queued_deck(queue, game), db)
    return compute_counters(game, view, db)


def test_partie_1_compteurs_de_base(setup, db):
    games, queue = setup
    counters = _counters_for(games, queue, db, 0)
    by_icon = {c.icon: c for c in counters}
    # restantes : toujours là (deck connu)
    assert "🂠" in by_icon
    # thief priest partie 1 : des entrées vivaient encore en fin de partie ?
    # (pas d'assertion forte — dépend de la partie — mais si présent, bien formé)
    if "⤵" in by_icon:
        assert "entrée" in by_icon["⤵"].text
    # prêtre ≠ voleur : pas de compteur combo
    assert "▶" not in by_icon


def test_partie_1_main_adverse_plausible(setup, db):
    games, queue = setup
    counters = _counters_for(games, queue, db, 0)
    hand = next((c for c in counters if c.icon == "✋"), None)
    if hand is not None:  # en toute fin de partie la main peut être vidée/cachée
        n = int(hand.text.split(":")[1].split()[0])
        assert 0 <= n <= 10


def test_partie_tronquee_compteurs_sans_crash(setup, db):
    games, queue = setup
    counters = _counters_for(games, queue, db, 2)
    # au mulligan : le deck est plein, aucune alerte fatigue
    remaining = next(c for c in counters if c.icon == "🂠")
    assert not remaining.alert


def test_degats_vert_rouge_au_mulligan(setup, db):
    # partie tronquée au mulligan : les deux héros sont en jeu → les deux
    # pastilles ⚔ existent, avec leur camp (vert = moi, rouge = adversaire)
    games, queue = setup
    counters = _counters_for(games, queue, db, 2)
    swords = [c for c in counters if c.icon == "⚔"]
    assert {c.kind for c in swords} == {"good", "bad"}
    assert all(c.text.isdigit() for c in swords)


def test_degats_fin_de_partie_sans_crash(setup, db):
    # fin de partie : un héros peut être au cimetière — pas de crash, et les
    # pastilles présentes restent des entiers ≥ 0
    games, queue = setup
    counters = _counters_for(games, queue, db, 0)
    for c in counters:
        if c.icon == "⚔":
            assert c.kind in ("good", "bad") and c.text.isdigit()


def test_mal_invocation_synthetique():
    from src.cairn.counters import _attacks_left
    from src.cairn.game_state import Entity

    fresh = Entity(entity_id=1, tags={"CARDTYPE": "MINION", "ATK": "4",
                                      "NUM_TURNS_IN_PLAY": "0"})
    # posé ce tour : ne peut pas attaquer À SON tour…
    assert _attacks_left(fresh, ready_now=True) == 0
    # …mais compte comme menace pour le tour suivant
    assert _attacks_left(fresh, ready_now=False) == 1
    # charge : attaque immédiatement
    fresh.tags["CHARGE"] = "1"
    assert _attacks_left(fresh, ready_now=True) == 1
    # sur le board depuis 1 tour : prêt, et fureur des vents = 2 attaques
    ready = Entity(entity_id=2, tags={"CARDTYPE": "MINION", "ATK": "3",
                                      "NUM_TURNS_IN_PLAY": "1", "WINDFURY": "1"})
    assert _attacks_left(ready, ready_now=True) == 2
    ready.tags["NUM_ATTACKS_THIS_TURN"] = "1"
    assert _attacks_left(ready, ready_now=True) == 1
    # gelé : ne compte jamais (il manquera sa prochaine attaque)
    ready.tags["FROZEN"] = "1"
    assert _attacks_left(ready, ready_now=False) == 0


def test_alerte_fatigue_synthetique(db, setup):
    from src.cairn.counters import CounterContext, counter_remaining
    from src.cairn.deck_view import DeckView, CardRow

    games, _ = setup
    view = DeckView(rows=[CardRow(1, "x", 1, 2, 0)], remaining_total=0)
    ctx = CounterContext(game=games[0], view=view, db=db)
    counter = counter_remaining(ctx)
    assert counter is not None and counter.alert and counter.text == "FATIGUE"


# ---- compteurs contextuels à déclencheur -----------------------------------

def _fake_game(local_cards=(), opp_cards=(), plays=(), deaths=()):
    """Partie synthétique minimale : entités révélées + événements."""
    from src.cairn.game_state import Death, Entity, Game, Play

    g = Game(player_names={1: "moi", 2: "adv"}, player_entity={1: 10, 2: 11})
    g.entities[10] = Entity(entity_id=10, tags={"CONTROLLER": "1"})
    g.entities[11] = Entity(entity_id=11, tags={"CONTROLLER": "2"})
    eid = 100
    for cards, controller in ((local_cards, "1"), (opp_cards, "2")):
        for cid in cards:
            g.entities[eid] = Entity(entity_id=eid, card_id=cid,
                                     tags={"CONTROLLER": controller})
            eid += 1
    # le joueur local se reconnaît à ses pioches révélées
    from src.cairn.game_state import Draw
    g.events.append(Draw(player_id=1, entity_id=1, card_id="X", during_mulligan=True))
    for pid, cid in plays:
        g.events.append(Play(player_id=pid, entity_id=eid, card_id=cid))
        eid += 1
    for pid, cid in deaths:
        g.events.append(Death(player_id=pid, entity_id=eid, card_id=cid))
        eid += 1
    return g


def test_rafaam_muet_sans_rafaam(db):
    from src.cairn.deck_view import DeckView

    game = _fake_game(opp_cards=["EX1_001"])
    icons = {c.icon for c in compute_counters(game, DeckView(), db)}
    assert "⏳" not in icons


def test_rafaam_arme_et_compte_les_distincts(db):
    from src.cairn.deck_view import DeckView

    # 3 Rafaam distincts joués (dont un doublon) + la carte mère qui ne compte pas
    game = _fake_game(
        opp_cards=["TIME_005t1"],
        plays=[(2, "TIME_005t1"), (2, "TIME_005t2"), (2, "TIME_005t2"),
               (2, "TIME_005t3"), (2, "TIME_005")],
    )
    counter = next(c for c in compute_counters(game, DeckView(), db) if c.icon == "⏳")
    assert counter.text == "Rafaam 3/9" and counter.kind == "bad"


def test_rafaam_alerte_a_neuf(db):
    from src.cairn.deck_view import DeckView

    plays = [(2, f"TIME_005t{i}") for i in range(1, 10)]
    game = _fake_game(opp_cards=["TIME_005t1"], plays=plays)
    counter = next(c for c in compute_counters(game, DeckView(), db) if c.icon == "⏳")
    assert "LÉTAL" in counter.text and counter.alert


def test_pool_resurrection_chasseur_corrompu(db):
    """EDR_891 ne ramène que des râles d'agonie alliés à (4) ou moins."""
    from src.cairn.pools import pool_for

    game = _fake_game(deaths=[
        (2, "EDR_841"),   # Corruptrice âmeffroi, 4 mana, râle d'agonie  → OUI
        (2, "BT_509"),    # Invocatrice gangrenée, 6 mana, râle          → non (coût)
        (2, "EX1_001"),   # sans râle d'agonie                            → non
        (1, "EDR_841"),   # même carte mais côté adverse                  → non
    ])
    label, entries = pool_for(game, db, "EDR_891", player_id=2)
    assert "(4) ou moins" in label
    assert [(e.name, e.count) for e in entries] == [("Corruptrice âmeffroi", 1)]

    # la carte à 7 mana prend l'autre moitié du pool
    _, entries7 = pool_for(game, db, "EDR_892", player_id=2)
    assert [e.name for e in entries7] == ["Invocatrice gangrenée"]


def test_pool_vide_pour_carte_ordinaire(db):
    from src.cairn.pools import pool_for

    assert pool_for(_fake_game(), db, "EX1_001", player_id=2) == ("", [])


# ---- bascule de langue ------------------------------------------------------

def test_noms_de_cartes_traduits(db):
    """Le survol doit afficher le nom anglais quand la langue est EN."""
    assert db.localized_name("EDR_891", "fr") == "Chasseur corrompu vorace"
    assert db.localized_name("EDR_891", "en") == "Ravenous Felhunter"
    assert db.localized_name("EDR_892", "en") == "Ferocious Felbat"
    # carte au nom identique dans les deux langues
    assert db.localized_name("EX1_572", "en") == db.localized_name("EX1_572", "fr")
    # id inconnu : on ne plante pas
    assert db.localized_name("PAS_UNE_CARTE", "en") == "PAS_UNE_CARTE"
    assert db.localized_name(None, "en") == "?"


def test_compteurs_et_pools_traduits(db):
    from src.cairn.deck_view import DeckView
    from src.cairn.pools import pool_for

    game = _fake_game(
        opp_cards=["TIME_005t1"],
        plays=[(2, "TIME_005t1"), (2, "TIME_005t2")],
        deaths=[(2, "EDR_841")],
    )
    fr = {c.icon: c.text for c in compute_counters(game, DeckView(), db, lang="fr")}
    en = {c.icon: c.text for c in compute_counters(game, DeckView(), db, lang="en")}
    assert fr["⏳"] == en["⏳"] == "Rafaam 2/9"   # identique, c'est un nom propre

    label_fr, entries_fr = pool_for(game, db, "EDR_891", 2, lang="fr")
    label_en, entries_en = pool_for(game, db, "EDR_891", 2, lang="en")
    assert "Râle d’agonie" in label_fr and "Deathrattle" in label_en
    assert entries_fr[0].name == "Corruptrice âmeffroi"
    assert entries_en[0].name == "Dreadsoul Corrupter"


# ---- deck adverse : son compte, donc sa fatigue -----------------------------

def _partie_avec_deck_adverse(n: int, turns: int = 4):
    """Partie synthétique : ``n`` cartes cachées dans la zone DECK adverse."""
    from src.cairn.game_state import Draw, Entity, Game

    g = Game(player_names={1: "moi", 2: "adv"}, player_entity={1: 10, 2: 11})
    g.turns = turns
    g.entities[10] = Entity(entity_id=10, tags={"CONTROLLER": "1"})
    g.entities[11] = Entity(entity_id=11, tags={"CONTROLLER": "2"})
    for i in range(n):
        # cartes adverses : jamais d'identité, mais bien comptables
        g.entities[200 + i] = Entity(
            entity_id=200 + i, tags={"CONTROLLER": "2", "ZONE": "DECK"}
        )
    g.events.append(Draw(player_id=1, entity_id=1, card_id="X", during_mulligan=True))
    return g


def test_deck_adverse_compte_les_cartes_cachees(db):
    """On ne connaît pas ses cartes, mais on connaît leur nombre."""
    from src.cairn.counters import CounterContext, counter_opp_remaining
    from src.cairn.deck_view import DeckView

    ctx = CounterContext(game=_partie_avec_deck_adverse(15), view=DeckView(), db=db)
    counter = counter_opp_remaining(ctx)
    assert counter is not None
    assert counter.text == "adv 15 au deck"
    assert counter.kind == "bad" and not counter.alert


def test_deck_adverse_alerte_quand_la_fatigue_approche(db):
    from src.cairn.counters import CounterContext, counter_opp_remaining
    from src.cairn.deck_view import DeckView

    ctx = CounterContext(game=_partie_avec_deck_adverse(3), view=DeckView(), db=db)
    assert counter_opp_remaining(ctx).alert


def test_deck_adverse_vide_annonce_la_fatigue(db):
    from src.cairn.counters import CounterContext, counter_opp_remaining
    from src.cairn.deck_view import DeckView

    ctx = CounterContext(game=_partie_avec_deck_adverse(0), view=DeckView(), db=db)
    counter = counter_opp_remaining(ctx)
    assert counter is not None and counter.alert
    assert "FATIGUE" in counter.text


def test_deck_adverse_muet_avant_le_premier_tour(db):
    """Au mulligan les entités du deck adverse ne sont pas encore posées :
    annoncer « adv FATIGUE » à chaque début de partie serait absurde."""
    from src.cairn.counters import CounterContext, counter_opp_remaining
    from src.cairn.deck_view import DeckView

    ctx = CounterContext(game=_partie_avec_deck_adverse(0, turns=0),
                         view=DeckView(), db=db)
    assert counter_opp_remaining(ctx) is None


# ---- vignette + chiffre + infobulle ----------------------------------------

def test_chaque_compteur_porte_une_vignette_et_un_chiffre(setup, db):
    """Depuis le passage « image + chiffre », un compteur sans illustration ni
    valeur courte se réduirait à une phrase dans une case de 176 px."""
    games, queue = setup
    compteurs = _counters_for(games, queue, db, 0)
    assert compteurs

    for c in compteurs:
        if c.group == "attack":
            continue  # la pastille de dégâts n'affiche que son nombre
        assert c.short, f"pas de valeur courte : {c.text!r}"
        assert c.text, "l'infobulle ne peut pas être vide"
        assert c.card_id, f"pas de vignette : {c.text!r}"


def test_vignette_de_la_carte_declencheuse(db):
    """Un compteur armé par une carte précise porte SON illustration, pas le
    portrait du héros — c'est ce qui rend Rafaam reconnaissable d'un coup."""
    from src.cairn.counters import CounterContext, counter_rafaam
    from src.cairn.deck_view import DeckView

    game = _fake_game(local_cards=["TIME_005t2"], plays=[(1, "TIME_005t2")])
    ctx = CounterContext(game=game, view=DeckView(), db=db)
    compteurs = counter_rafaam(ctx)
    assert compteurs
    assert compteurs[0].card_id == "TIME_005t2"
    assert compteurs[0].short == "1/9"


def test_compteur_sans_carte_prend_le_portrait_du_heros(db):
    """« 28 au deck » et « adv 13 au deck » ne désignent aucune carte : sans le
    portrait ils seraient deux lignes identiques une fois le texte parti."""
    from src.cairn.counters import CounterContext, counter_opp_remaining
    from src.cairn.deck_view import DeckView
    from src.cairn.game_state import Entity

    game = _partie_avec_deck_adverse(9)
    # le héros adverse, tel que le moteur le repère (PLAY + CARDTYPE=HERO)
    game.entities[500] = Entity(
        entity_id=500, card_id="HERO_09a",
        tags={"CONTROLLER": "2", "ZONE": "PLAY", "CARDTYPE": "HERO"},
    )
    ctx = CounterContext(game=game, view=DeckView(), db=db)
    counter = counter_opp_remaining(ctx)
    assert counter.card_id == "HERO_09a"
    assert counter.short == "9"
    assert counter.text == "adv 9 au deck"  # la phrase reste, pour l'infobulle


# ---- Empreint (mot-clé Imbue) ----------------------------------------------

def _partie_avec_empreint(niveau_moi=0, niveau_adv=0, hp="EDR_449p"):
    """Le pouvoir héroïque empreint porte son niveau dans TAG_SCRIPT_DATA_NUM_1."""
    from src.cairn.game_state import Draw, Entity, Game

    g = Game(player_names={1: "moi", 2: "adv"}, player_entity={1: 10, 2: 11})
    g.turns = 8
    g.entities[10] = Entity(entity_id=10, tags={"CONTROLLER": "1"})
    g.entities[11] = Entity(entity_id=11, tags={"CONTROLLER": "2"})
    for eid, (ctrl, niv) in enumerate(((("1"), niveau_moi), (("2"), niveau_adv)), 300):
        if niv <= 0:
            continue
        g.entities[eid] = Entity(
            entity_id=eid, card_id=hp,
            tags={"CONTROLLER": ctrl, "ZONE": "PLAY", "CARDTYPE": "HERO_POWER",
                  "TAG_SCRIPT_DATA_NUM_1": str(niv)},
        )
    g.events.append(Draw(player_id=1, entity_id=1, card_id="X", during_mulligan=True))
    return g


def test_empreint_lit_le_niveau_du_pouvoir_heroique(db):
    """C'est le seul endroit où le niveau existe : rien ne l'affiche en jeu."""
    from src.cairn.counters import CounterContext, counter_imbue
    from src.cairn.deck_view import DeckView

    ctx = CounterContext(game=_partie_avec_empreint(niveau_moi=3), view=DeckView(),
                         db=db)
    compteurs = counter_imbue(ctx)
    assert [c.text for c in compteurs] == ["moi empreint 3"]
    assert compteurs[0].kind == "good"


def test_empreint_compte_les_deux_camps(db):
    from src.cairn.counters import CounterContext, counter_imbue
    from src.cairn.deck_view import DeckView

    ctx = CounterContext(game=_partie_avec_empreint(niveau_moi=2, niveau_adv=5),
                         view=DeckView(), db=db)
    assert [c.text for c in counter_imbue(ctx)] == ["moi empreint 2", "adv empreint 5"]


def test_empreint_muet_sur_un_pouvoir_de_base(db):
    """Un pouvoir héroïque de base ne porte PAS de niveau — c'est le niveau
    lui-même qui sert de détecteur, pas une liste de cartes : « Bénédiction du
    Vol de bronze » et « Force de Minh » n'étaient dans aucune liste et
    laissaient l'adversaire sans compteur dès qu'il n'était pas Prêtre."""
    from src.cairn.counters import CounterContext, counter_imbue
    from src.cairn.deck_view import DeckView

    ctx = CounterContext(game=_partie_avec_empreint(niveau_moi=0),
                         view=DeckView(), db=db)
    assert counter_imbue(ctx) == []


def test_empreint_marche_hors_pretre(db):
    """« Bénédiction du Vol de bronze » (Druide) n'est marquée IMBUE nulle part
    dans la base de cartes ; son niveau, lui, est bien là."""
    from src.cairn.counters import CounterContext, counter_imbue
    from src.cairn.deck_view import DeckView

    ctx = CounterContext(game=_partie_avec_empreint(niveau_adv=4, hp="END_000p"),
                         view=DeckView(), db=db)
    compteurs = counter_imbue(ctx)
    assert [c.text for c in compteurs] == ["adv empreint 4"]


def test_les_pouvoirs_empreints_sont_deduits_de_la_base(db):
    """Drapeau dérivé de referencedTags au téléchargement, pas une liste en dur :
    la prochaine extension en ajoutera sans qu'on touche au code."""
    assert "EDR_449p" in db.imbued_hero_powers        # Bénédiction de la lune
    assert "CS1h_001_H1" not in db.imbued_hero_powers  # Soins inférieurs
    assert len(db.imbued_hero_powers) >= 6


# ---- mise en colonnes moi / adversaire -------------------------------------

def test_les_deux_camps_partagent_une_ligne(db, setup):
    """« 28 au deck » et « adv 20 au deck » sont le MÊME compteur : deux
    colonnes, une ligne. C'est tout l'intérêt de la disposition."""
    from src.cairn.ui.bridge import _counter_rows
    from src.cairn.counters import Counter

    lignes = _counter_rows(
        [
            Counter(icon="🂠", text="28 au deck", short="28", pair="deck", side="me"),
            Counter(icon="🂠", text="adv 20 au deck", short="20", pair="deck",
                    side="opp", kind="bad"),
        ],
        "fr",
    )
    assert len(lignes) == 1
    ligne = lignes[0]
    assert ligne["label"] == "au deck"
    assert (ligne["meText"], ligne["oppText"]) == ("28", "20")
    # l'infobulle garde les deux phrases complètes
    assert "28 au deck" in ligne["tip"] and "adv 20 au deck" in ligne["tip"]


def test_compteur_d_un_seul_camp_laisse_l_autre_colonne_vide(db):
    from src.cairn.ui.bridge import _counter_rows
    from src.cairn.counters import Counter

    lignes = _counter_rows(
        [Counter(icon="✧", text="moi empreint 2", short="2", pair="imbue",
                 side="me", kind="good")],
        "fr",
    )
    assert lignes[0]["meText"] == "2" and lignes[0]["oppText"] == ""


def test_l_ordre_des_lignes_est_stable(db, setup):
    """Une ligne qui saute de place à chaque tour serait illisible : l'ordre
    suit la première apparition, du plus général au plus contextuel."""
    games, queue = setup
    from src.cairn.ui.bridge import _counter_rows

    lignes = _counter_rows(_counters_for(games, queue, db, 0), "fr")
    assert [x["label"] for x in lignes] == [
        x["label"] for x in _counter_rows(_counters_for(games, queue, db, 0), "fr")
    ]
    assert lignes and lignes[0]["label"] == "au deck"


def test_les_pastilles_de_degats_restent_hors_du_panneau(db, setup):
    """Elles ont leur propre fenêtre : les remettre dans le tableau annulerait
    la séparation faite exprès."""
    games, queue = setup
    from src.cairn.ui.bridge import _counter_rows

    lignes = _counter_rows(_counters_for(games, queue, db, 0), "fr")
    assert all(x["label"] not in ("⚔", "attack") for x in lignes)
