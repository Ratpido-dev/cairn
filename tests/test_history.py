"""Tests de l'historique SQLite — sur les parties réelles de la fixture."""

import re

import pytest

from src.cairn.decks_log import parse_queue_events
from src.cairn.deck_view import pick_queued_deck
from src.cairn.game_state import replay_file
from src.cairn.history import History
from src.cairn.paths import FIXTURES_DIR

FIXTURE_DIR = FIXTURES_DIR / "Hearthstone_2026_08_01_00_06_06"

pytestmark = pytest.mark.skipif(
    not (FIXTURE_DIR / "Power.log").is_file(), reason="fixture absente"
)


@pytest.fixture()
def history(tmp_path):
    h = History(path=tmp_path / "history.sqlite")
    yield h
    h.close()


@pytest.fixture(scope="module")
def games_and_queue():
    games = replay_file(FIXTURE_DIR / "Power.log")
    queue = parse_queue_events(
        (FIXTURE_DIR / "Decks.log").read_text(encoding="utf-8", errors="replace")
    )
    return games, queue


def test_enregistre_les_parties_completes(history, games_and_queue):
    games, queue = games_and_queue
    session = FIXTURE_DIR.name
    recorded = [
        history.record(session, i, g, pick_queued_deck(queue, g))
        for i, g in enumerate(games)
    ]
    # 2 complètes enregistrées, la tronquée refusée
    assert recorded == [True, True, False]

    stats = history.deck_stats()
    assert len(stats) == 1
    assert stats[0].deck_name == "Thief Priest"
    assert stats[0].games == 2
    assert stats[0].wins == 1
    assert stats[0].winrate == 0.5


def test_dedoublonnage(history, games_and_queue):
    games, queue = games_and_queue
    session = FIXTURE_DIR.name
    deck = pick_queued_deck(queue, games[0])
    assert history.record(session, 0, games[0], deck) is True
    assert history.record(session, 0, games[0], deck) is False  # déjà connue
    assert history.deck_stats()[0].games == 1


def test_date_et_adversaire(history, games_and_queue):
    games, queue = games_and_queue
    history.record(
        FIXTURE_DIR.name, 0, games[0], pick_queued_deck(queue, games[0]),
        opponent_class="WARRIOR",
    )
    (row,) = history.recent(limit=1)
    (played_on, _ts, deck_name, opponent, result, turns, klass,
     session, idx, duration, conceded, conceded_turn) = row
    assert (session, idx) == (FIXTURE_DIR.name, 0)  # clé de suppression
    assert duration and duration > 0  # durée mesurée dans le journal
    assert played_on == "2026-08-01"
    assert re.fullmatch(r"[^\s#]+#\d+", opponent)  # battletag, pas en dur
    assert result == "WON"
    assert turns == 29
    assert klass == "WARRIOR"


def test_stats_par_classe(history, games_and_queue):
    games, queue = games_and_queue
    history.record(FIXTURE_DIR.name, 0, games[0], None, opponent_class="WARRIOR")
    history.record(FIXTURE_DIR.name, 1, games[1], None, opponent_class="ROGUE")
    # (classe, parties, victoires, durée moyenne en s)
    guerrier = next(r for r in history.class_stats() if r[0] == "WARRIOR")
    assert guerrier[:3] == ("WARRIOR", 1, 1)
    assert history.vs_class("ROGUE") == (0, 1)
    assert history.vs_class("MAGE") == (0, 0)


def test_duree_moyenne_par_classe_et_par_deck(history, games_and_queue):
    """La durée dit ce que le winrate tait : ce que coûte un matchup.

    Elle est calculée sur les seules parties CHRONOMÉTRÉES — compter une partie
    sans durée comme zéro tirerait la moyenne vers le bas sans prévenir, et
    c'est le genre d'erreur qu'on ne voit pas dans un chiffre plausible.
    """
    games, queue = games_and_queue
    history.record(FIXTURE_DIR.name, 0, games[0], None, opponent_class="WARRIOR")
    history.record(FIXTURE_DIR.name, 1, games[1], None, opponent_class="WARRIOR")

    (_, parties, _, moyenne), = [r for r in history.class_stats() if r[0] == "WARRIOR"]
    attendues = [g.duration_seconds() for g in games[:2]]
    chrono = [d for d in attendues if d]
    assert parties == 2
    if chrono:
        assert moyenne == pytest.approx(sum(chrono) / len(chrono), abs=1)
    else:
        assert moyenne == 0, "sans partie chronométrée, on ne prétend rien"

    # même contrat côté decks
    stats = history.deck_stats()
    assert all(hasattr(d, "avg_duration_s") for d in stats)
    assert all(d.avg_duration_s >= 0 for d in stats)


# ---- saisie manuelle, archivage, suppression -------------------------------

def test_partie_manuelle_compte_dans_les_stats(tmp_path):
    from src.cairn.history import History

    h = History(path=tmp_path / "h.sqlite")
    h.add_manual("Thief Priest", "PRIEST", won=True)
    h.add_manual("Thief Priest", "PRIEST", won=False)
    h.add_manual("Thief Priest", "MAGE", won=True)

    assert h.overall() == (3, 2)
    stats = {s.deck_name: (s.games, s.wins) for s in h.deck_stats()}
    assert stats["Thief Priest"] == (3, 2)
    assert h.vs_class("PRIEST") == (1, 1)
    # les index ne se marchent pas dessus
    assert len(h.recent(limit=10)) == 3


def test_archivage_remet_le_winrate_a_zero_sans_perdre_les_donnees(tmp_path):
    from src.cairn.history import History

    h = History(path=tmp_path / "h.sqlite")
    for won in (False, False, True):
        h.add_manual("Neuf", "MAGE", won=won)
    assert h.overall() == (3, 1)

    assert h.archive_deck("Neuf") == 3
    assert h.overall() == (0, 0)          # stats repartent de zéro
    assert h.deck_stats() == []
    assert h.vs_class("MAGE") == (0, 0)
    # …mais les lignes sont toujours là
    n = h._conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    assert n == 3

    # on rejoue après archivage : le nouveau winrate est propre
    h.add_manual("Neuf", "MAGE", won=True)
    assert h.overall() == (1, 1)


def test_suppression_efface_vraiment(tmp_path):
    from src.cairn.history import History

    h = History(path=tmp_path / "h.sqlite")
    h.add_manual("A", "MAGE", won=True)
    h.add_manual("B", "MAGE", won=True)
    assert h.delete_deck("A") == 1
    assert h._conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1
    assert [s.deck_name for s in h.deck_stats()] == ["B"]


def test_migration_archived_sur_base_existante(tmp_path):
    """Une base créée par une version antérieure doit s'ouvrir et rester juste."""
    import sqlite3

    path = tmp_path / "old.sqlite"
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE games (
        session TEXT NOT NULL, game_index INTEGER NOT NULL, played_on TEXT NOT NULL,
        game_ts TEXT, deck_name TEXT, deck_id INTEGER, opponent TEXT, result TEXT,
        turns INTEGER, game_type TEXT, format_type TEXT,
        PRIMARY KEY (session, game_index))""")
    con.execute("INSERT INTO games VALUES ('s',0,'2026-08-01',NULL,'Vieux',NULL,"
                "'x','WON',10,'GT_RANKED','FT_STANDARD')")
    con.commit()
    con.close()

    from src.cairn.history import History

    h = History(path=path)
    assert h.overall() == (1, 1)          # archived défaut 0 → toujours compté
    h.add_manual("Vieux", "MAGE", won=False)
    assert h.overall() == (2, 1)


def test_suppression_d_un_match_precis(tmp_path):
    from src.cairn.history import History

    h = History(path=tmp_path / "h.sqlite")
    h.add_manual("A", "MAGE", won=True)
    h.add_manual("A", "DRUID", won=False)
    h.add_manual("A", "ROGUE", won=True)
    assert h.overall() == (3, 2)

    # recent() expose maintenant la clé (session, game_index) de chaque partie
    rows = h.recent(limit=10)
    assert len(rows[0]) == 12       # + concession et son tour
    session, index = rows[0][7], rows[0][8]

    assert h.delete_game(session, index) is True
    assert h.overall() == (2, 1) or h.overall() == (2, 2)
    assert len(h.recent(limit=10)) == 2
    # une clé inconnue ne casse rien
    assert h.delete_game("inexistante", 99) is False


def test_saisie_manuelle_refuse_un_libelle_traduit(tmp_path):
    """« Chaman » n'est pas une clé de classe, « SHAMAN » l'est.

    Régression réelle : une saisie du 05/08/2026 avait stocké le libellé
    français. Les statistiques montraient DEUX lignes « Chaman » — 15/17 et
    1/1 — indistinguables à l'œil, puisque les deux s'affichent pareil.
    """
    h = History(path=tmp_path / "h.sqlite")
    h.add_manual("mon deck", "Chaman", True)      # libellé : refusé
    h.add_manual("mon deck", "SHAMAN", True)      # clé : acceptée
    cles = {r[0] for r in h.class_stats()}
    assert "Chaman" not in cles, "un libellé traduit ne doit jamais servir de clé"
    assert "SHAMAN" in cles


def test_concession_enregistree_et_exclue_des_moyennes(tmp_path, games_and_queue):
    """Une partie concédée au tour 1 n'est pas une partie courte : c'est une
    non-partie. La compter dans les durées moyennes les tire vers le bas sans
    que rien ne le signale — d'où son exclusion, et son étiquette.

    Le signal vient de Hearthstone (``PLAYSTATE=CONCEDED``), pas d'un seuil de
    durée : une défaite rapide et un abandon immédiat ne se confondent pas.
    """
    from src.cairn.game_state import Game
    h = History(path=tmp_path / "h.sqlite")

    def partie(nom_local, concede_par, tour, duree_ts):
        g = Game(ts="00:00:00.0000000", last_ts=duree_ts, complete=True)
        g.player_names = {1: nom_local, 2: "Adv#1"}
        g.results = {nom_local: "WON", "Adv#1": "LOST"}
        g.events = []
        g.conceded_by = concede_par
        g.conceded_turn = tour
        g.turns = tour
        return g

    from src.cairn.game_state import Draw
    def avec_local(g, nom):
        g.events = [Draw(player_id=1, entity_id=1, card_id="X", during_mulligan=False)]
        g.player_names[1] = nom
        return g

    h.record("s", 0, avec_local(partie("Moi#1", "Adv#1", 1, "00:00:12.0"), "Moi#1"),
             None, opponent_class="MAGE")
    h.record("s", 1, avec_local(partie("Moi#1", "", 0, "00:20:00.0"), "Moi#1"),
             None, opponent_class="MAGE")

    lignes = {r[8]: r for r in h.recent(limit=10)}
    assert lignes[0][10] == "opp" and lignes[0][11] == 1, "concession adverse notée"
    assert lignes[1][10] == "", "partie normale : pas de concession"

    # la moyenne ignore l'abandon immédiat (12 s) et ne garde que les 20 min
    (_klass, _n, _v, moyenne), = h.class_stats()
    assert moyenne > 600, f"moyenne polluée par la concession : {moyenne} s"


def test_session_qui_franchit_minuit(history, games_and_queue):
    """Le nom de session est celui du LANCEMENT du jeu. Une partie jouée à
    00h08 dans une session commencée à 22h30 a eu lieu le LENDEMAIN — la dater
    de la veille la triait comme la plus ancienne de sa journée, et elle
    disparaissait de la liste des parties récentes alors qu'elle venait de
    finir."""
    games, queue = games_and_queue
    assert games[0].ts.startswith("00:08")  # la fixture est bien nocturne

    history.record("Hearthstone_2026_08_01_22_30_54", 0, games[0], None)
    (row,) = history.recent(limit=1)
    assert row[0] == "2026-08-02"


def test_session_de_jour_inchangee(history, games_and_queue):
    """Une partie postérieure à l'heure de lancement garde la date du nom."""
    games, queue = games_and_queue
    history.record("Hearthstone_2026_08_01_00_06_06", 0, games[0], None)
    (row,) = history.recent(limit=1)
    assert row[0] == "2026-08-01"


def test_forme_des_victoires_et_des_defaites(history, games_and_queue):
    """Un deck qui gagne court et perd long ne se joue pas comme celui qui fait
    l'inverse. Le winrate ne dit jamais ça — d'où les moyennes séparées."""
    games, queue = games_and_queue
    deck = pick_queued_deck(queue, games[0])
    history.record(FIXTURE_DIR.name, 0, games[0], deck)

    (stats,) = [s for s in history.deck_stats() if s.games]
    gagnee = games[0].results.get(games[0].player_names[games[0].local_player_id()]) == "WON"
    if gagnee:
        assert stats.avg_rounds_win > 0 and stats.avg_duration_win_s > 0
        assert stats.avg_rounds_loss == 0   # aucune défaite enregistrée
    else:
        assert stats.avg_rounds_loss > 0 and stats.avg_duration_loss_s > 0
        assert stats.avg_rounds_win == 0


def test_concession_de_depart_exclue_des_moyennes(history, games_and_queue):
    """Un adversaire qui abandonne au tour 2 n'a pas joué : compter cette
    partie tirerait toutes les moyennes vers le bas et ferait passer un deck
    lent pour un deck rapide."""
    games, queue = games_and_queue
    g = games[0]
    g.conceded_by = next(iter(g.results))
    g.conceded_turn = 2
    history.record(FIXTURE_DIR.name, 0, g, pick_queued_deck(queue, g))

    (stats,) = [s for s in history.deck_stats() if s.games]
    assert stats.avg_rounds_win == 0 and stats.avg_rounds_loss == 0
    assert stats.avg_duration_win_s == 0 and stats.avg_duration_loss_s == 0
