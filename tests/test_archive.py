"""Archivage des sessions — ce qui doit survivre à Hearthstone.

Le jeu supprime ses vieux dossiers de journaux, et l'historique SQLite ne garde
qu'un résumé par partie. Ces tests verrouillent la seule propriété qui compte :
**une archive doit se rejouer exactement comme le journal d'origine**.
"""

import gzip

import pytest

from src.cairn.archive import MIN_UTILE, SessionArchive
from src.cairn.game_state import replay_file
from src.cairn.log_watcher import LiveTracker
from src.cairn.paths import FIXTURES_DIR

FIXTURE = FIXTURES_DIR / "Hearthstone_2026_08_01_00_06_06" / "Power.log"

pytestmark = pytest.mark.skipif(
    not FIXTURE.is_file(), reason="fixture absente"
)


@pytest.fixture(scope="module")
def lignes():
    """Une partie entière, mais pas tout le journal : les tests restent rapides."""
    brut = FIXTURE.read_text(encoding="utf-8", errors="replace").splitlines()
    debuts = [i for i, l in enumerate(brut) if l.endswith("CREATE_GAME")]
    return brut[: debuts[1]] if len(debuts) > 1 else brut


def _session(tmp_path, lignes, nom="Hearthstone_2026_08_01_00_06_06"):
    session = tmp_path / "Logs" / nom
    session.mkdir(parents=True)
    (session / "Power.log").write_text("\n".join(lignes) + "\n", encoding="utf-8")
    (session / "Decks.log").write_text("### Thief Priest\n", encoding="utf-8")
    return session


def test_l_archive_se_rejoue_comme_l_original(tmp_path, lignes):
    session = _session(tmp_path, lignes)
    archive = SessionArchive(tmp_path / "archives")
    archive.start(session)
    archive.feed(lignes)
    archive.close()

    attendu = replay_file(session / "Power.log")
    obtenu = replay_file(archive.path_for(session.name))
    assert len(obtenu) == len(attendu) >= 1
    assert [g.player_names for g in obtenu] == [g.player_names for g in attendu]
    assert [len(g.events) for g in obtenu] == [len(g.events) for g in attendu]


def test_plusieurs_blocs_se_relisent_d_un_seul_tenant(tmp_path, lignes):
    """Chaque bloc est un membre gzip complet : gzip relit la concaténation.
    C'est ce qui fait qu'un processus tué ne coûte que le dernier bloc."""
    session = _session(tmp_path, lignes)
    archive = SessionArchive(tmp_path / "archives", chunk_bytes=4096)
    archive.start(session)
    for i in range(0, len(lignes), 50):
        archive.feed(lignes[i:i + 50])
    archive.close()

    with gzip.open(archive.path_for(session.name), "rt", encoding="utf-8") as f:
        relu = f.read().splitlines()
    assert relu == lignes


def test_un_bloc_final_tronque_ne_perd_que_lui(tmp_path, lignes):
    """Simulation d'un arrêt brutal : le dernier membre est coupé. Les parties
    déjà archivées doivent rester lisibles — c'est tout l'intérêt des membres."""
    session = _session(tmp_path, lignes)
    archive = SessionArchive(tmp_path / "archives")
    archive.start(session)
    archive.feed(lignes)
    archive.flush()
    cible = archive.path_for(session.name)
    complet = cible.read_bytes()
    archive.feed(["D 00:00:00.0 GameState.DebugPrintPower() - BLOCK_END"] * 200)
    archive.flush()
    # on ampute la fin du fichier au milieu du second membre
    cible.write_bytes(complet + cible.read_bytes()[len(complet):][:20])

    parties = replay_file(cible)
    assert parties and parties[0].player_names


def test_rattrapage_des_sessions_deja_sur_le_disque(tmp_path, lignes):
    _session(tmp_path, lignes, "Hearthstone_2026_08_01_00_06_06")
    _session(tmp_path, lignes, "Hearthstone_2026_08_02_00_00_00")
    archive = SessionArchive(tmp_path / "archives")

    faites = archive.backfill(tmp_path / "Logs")
    assert faites == ["Hearthstone_2026_08_01_00_06_06",
                      "Hearthstone_2026_08_02_00_00_00"]
    # rejouable, et le Decks.log a suivi (sans lui : plus de nom de deck)
    assert replay_file(archive.path_for(faites[0]))
    assert (archive.root / faites[0] / "Decks.log").is_file()
    # deuxième passage : rien à refaire, et surtout rien à dupliquer
    assert archive.backfill(tmp_path / "Logs") == []


def test_la_session_en_cours_est_exclue_du_rattrapage(tmp_path, lignes):
    """Elle est lue depuis le début par le suiveur, qui l'archive au fil de
    l'eau : la rattraper aussi doublerait toutes ses parties."""
    session = _session(tmp_path, lignes)
    archive = SessionArchive(tmp_path / "archives")
    archive.start(session)
    assert archive.backfill(tmp_path / "Logs") == []


def test_relancer_le_tracker_ne_double_pas_la_session(tmp_path, lignes):
    """Le cas qui arrive vraiment : on relance Cairn au milieu d'une session.
    Le suiveur relit le journal depuis le début — l'archive doit repartir de
    zéro, sinon chaque partie s'y retrouve en double."""
    session = _session(tmp_path, lignes)
    racine = tmp_path / "archives"
    attendu = len(replay_file(session / "Power.log"))

    for _ in range(3):   # trois lancements successifs
        archive = SessionArchive(racine)
        tracker = LiveTracker(logs_root=tmp_path / "Logs", archive=archive)
        tracker.poll()
        archive.close()

    assert len(replay_file(archive.path_for(session.name))) == attendu


def test_suivi_depuis_la_fin_preserve_l_archive(tmp_path, lignes):
    """``from_start=False`` (outil qui se branche en cours de route) : là, le
    lecteur ne relit rien, donc effacer l'archive perdrait tout."""
    session = _session(tmp_path, lignes)
    archive = SessionArchive(tmp_path / "archives")
    archive.start(session)
    archive.feed(lignes)
    archive.flush()
    taille = archive.path_for(session.name).stat().st_size

    archive.start(session, from_start=False)
    assert archive.path_for(session.name).stat().st_size == taille


def test_journal_vide_ou_minuscule_ignore(tmp_path):
    """HS écrit un Power.log même sans log.config : quelques octets d'erreur
    interne, aucun CREATE_GAME. Rien à archiver."""
    session = tmp_path / "Logs" / "Hearthstone_2026_08_03_00_00_00"
    session.mkdir(parents=True)
    (session / "Power.log").write_text("x" * (MIN_UTILE - 1), encoding="utf-8")
    archive = SessionArchive(tmp_path / "archives")
    assert archive.backfill(tmp_path / "Logs") == []
    assert not archive.path_for(session.name).exists()


def test_aucun_fichier_partiel_ne_survit(tmp_path, lignes):
    _session(tmp_path, lignes)
    archive = SessionArchive(tmp_path / "archives")
    archive.backfill(tmp_path / "Logs")
    assert list(archive.root.rglob("*.part")) == []


def test_les_journaux_a_plat_de_l_ancien_miroir_sont_repris(tmp_path, lignes):
    """Avant le 02/08/2026, la copie de session était un effet de bord de la
    rotation : des ``<session>.Power.log`` non compressés traînent à la racine,
    et ils contiennent des sessions que HS a effacées depuis."""
    racine = tmp_path / "archives"
    racine.mkdir()
    plat = racine / "Hearthstone_2026_08_01_22_37_55.Power.log"
    plat.write_text("\n".join(lignes) + "\n", encoding="utf-8")

    archive = SessionArchive(racine)
    assert archive.backfill() == ["Hearthstone_2026_08_01_22_37_55"]
    assert replay_file(archive.path_for("Hearthstone_2026_08_01_22_37_55"))
    # l'original n'est PAS supprimé : effacer les données de l'utilisateur ne
    # fait pas partie du contrat
    assert plat.is_file()
    assert archive.backfill() == []   # pas de reprise en boucle


def test_taille_et_inventaire(tmp_path, lignes):
    _session(tmp_path, lignes)
    archive = SessionArchive(tmp_path / "archives")
    archive.backfill(tmp_path / "Logs")
    sessions = archive.sessions()
    assert len(sessions) == 1 and sessions[0].size > 0
    assert archive.total_size() == sessions[0].size
    # la compression est le seul argument qui rend l'archivage permanent
    brut = (tmp_path / "Logs" / sessions[0].name / "Power.log").stat().st_size
    assert sessions[0].size < brut / 5


def test_le_suiveur_archive_ce_qu_il_lit(tmp_path, lignes):
    """Bout en bout : LiveTracker → archive → rejeu identique."""
    session = _session(tmp_path, lignes)
    archive = SessionArchive(tmp_path / "archives")
    tracker = LiveTracker(logs_root=tmp_path / "Logs", archive=archive)
    tracker.poll()
    archive.close()

    parties = replay_file(archive.path_for(session.name))
    assert len(parties) == len(tracker.engine.games)
    assert parties[0].player_names == tracker.engine.games[0].player_names


def test_sans_archiveur_le_suiveur_fonctionne_pareil(tmp_path, lignes):
    """L'archivage est un confort : il ne doit jamais devenir une condition."""
    _session(tmp_path, lignes)
    tracker = LiveTracker(logs_root=tmp_path / "Logs")
    assert tracker.poll().new_games
