"""Tests du suivi live : tailer, bascule de session, équivalence live == batch."""

import pytest

from src.cairn.game_state import DeckEntry, Draw, Play, replay_file
from src.cairn.log_watcher import LiveTracker, LogTailer
from src.cairn.paths import FIXTURES_DIR

FIXTURE = FIXTURES_DIR / "Hearthstone_2026_08_01_00_06_06" / "Power.log"

L = "D 00:00:00.0000000 GameState.DebugPrintPower() - "


# ---- LogTailer -------------------------------------------------------------

def test_tailer_fichier_absent_puis_cree(tmp_path):
    path = tmp_path / "Power.log"
    tailer = LogTailer(path)
    assert tailer.poll() == []
    path.write_text("ligne1\nligne2\n")
    assert tailer.poll() == ["ligne1", "ligne2"]
    assert tailer.poll() == []


def test_tailer_ligne_partielle_gardee_en_tampon(tmp_path):
    path = tmp_path / "Power.log"
    path.write_text("complète\nincom")
    tailer = LogTailer(path)
    assert tailer.poll() == ["complète"]
    with open(path, "a") as f:
        f.write("plète\nsuivante\n")
    assert tailer.poll() == ["incomplète", "suivante"]


def test_tailer_fichier_remplace_repart_du_debut(tmp_path):
    # Cas réel HS : le fichier est recréé, jamais réécrit en place.
    path = tmp_path / "Power.log"
    path.write_text("a\nb\n")
    tailer = LogTailer(path)
    tailer.poll()
    path.unlink()
    path.write_text("nouveau\n")
    assert tailer.poll() == ["nouveau"]


def test_tailer_fichier_remplace_avec_inode_recycle(tmp_path):
    """Journal recréé alors que le système a RECYCLÉ l'inode du précédent.

    Ce cas a fait rougir la CI sans jamais échouer en local : ext4 et tmpfs
    réattribuent l'inode libéré immédiatement, si bien que le fichier neuf
    porte celui de l'ancien. La taille ne trahit rien non plus dès que le
    nouveau journal a dépassé l'ancien décalage — le tailer relisait donc le
    nouveau fichier depuis le décalage de l'ancien et rendait « eau » pour
    « nouveau », en perdant le début de la session.

    On reproduit la situation de façon déterministe, sans dépendre du système
    de fichiers : réécriture EN PLACE (même inode) d'un contenu PLUS LONG.
    Seule la tête du fichier peut alors révéler le remplacement.
    """
    path = tmp_path / "Power.log"
    path.write_text("a\nb\n")
    tailer = LogTailer(path)
    tailer.poll()

    inode = path.stat().st_ino
    path.write_text("nouveau journal\n")   # mode « w » : tronque en place
    assert path.stat().st_ino == inode, "sans inode identique, le test ne teste rien"
    assert path.stat().st_size > 4, "le test suppose un contenu plus long qu'avant"

    assert tailer.poll() == ["nouveau journal"]


def test_tailer_troncature_plus_courte_detectee(tmp_path):
    path = tmp_path / "Power.log"
    path.write_text("aaaa\nbbbb\n")
    tailer = LogTailer(path)
    tailer.poll()
    path.write_text("x\n")  # même inode mais plus court : détecté par la taille
    assert tailer.poll() == ["x"]


def test_tailer_from_start_false_ignore_l_existant(tmp_path):
    path = tmp_path / "Power.log"
    path.write_text("ancien\n")
    tailer = LogTailer(path, from_start=False)
    assert tailer.poll() == []
    with open(path, "a") as f:
        f.write("nouveau\n")
    assert tailer.poll() == ["nouveau"]


# ---- LiveTracker sur arborescence simulée ----------------------------------

def _fake_logs(tmp_path, name="Hearthstone_2099_01_01_00_00_00"):
    session = tmp_path / name
    session.mkdir()
    return session


def test_live_tracker_detecte_session_et_partie(tmp_path):
    session = _fake_logs(tmp_path)
    tracker = LiveTracker(logs_root=tmp_path)

    update = tracker.poll()
    assert update.session_switched == session

    (session / "Power.log").write_text(
        L + "CREATE_GAME\n"
        + L + "    GameEntity EntityID=1\n"
        + L + "    Player EntityID=2 PlayerID=1 GameAccountId=[hi=1 lo=2]\n"
    )
    update = tracker.poll()
    assert len(update.new_games) == 1
    assert tracker.current_game is not None


def test_live_tracker_bascule_vers_nouvelle_session(tmp_path):
    old = _fake_logs(tmp_path, "Hearthstone_2099_01_01_00_00_00")
    (old / "Power.log").write_text(L + "CREATE_GAME\n")
    tracker = LiveTracker(logs_root=tmp_path)
    tracker.poll()

    new = _fake_logs(tmp_path, "Hearthstone_2099_01_02_00_00_00")
    update = tracker.poll()
    assert update.session_switched == new


def test_live_tracker_emet_les_evenements_au_fil_de_l_eau(tmp_path):
    session = _fake_logs(tmp_path)
    power = session / "Power.log"
    tracker = LiveTracker(logs_root=tmp_path)

    power.write_text(
        L + "CREATE_GAME\n"
        + L + "FULL_ENTITY - Creating ID=10 CardID=\n"
        + L + "    tag=ZONE value=DECK\n"
        + L + "    tag=CONTROLLER value=1\n"
    )
    tracker.poll()

    with open(power, "a") as f:
        f.write(L + "TAG_CHANGE Entity=10 tag=ZONE value=HAND\n")
    update = tracker.poll()
    assert len(update.events) == 1
    assert isinstance(update.events[0], Draw)


# ---- équivalence live == batch sur la fixture réelle -----------------------

@pytest.mark.skipif(not FIXTURE.is_file(), reason="fixture absente")
def test_live_par_morceaux_equivaut_au_batch(tmp_path):
    """Nourrir le tracker par petits blocs = tout relire d'un coup."""
    batch_games = replay_file(FIXTURE)

    session = _fake_logs(tmp_path)
    power = session / "Power.log"
    tracker = LiveTracker(logs_root=tmp_path)
    tracker.poll()

    content = FIXTURE.read_bytes()
    total_events = 0
    chunk = 64 * 1024  # blocs arbitraires, coupant des lignes en plein milieu
    with open(power, "ab") as f:
        for i in range(0, len(content), chunk):
            f.write(content[i:i + chunk])
            f.flush()
            total_events += len(tracker.poll().events)

    live_games = tracker.engine.games
    assert len(live_games) == len(batch_games)
    for live, batch in zip(live_games, batch_games):
        assert live.results == batch.results
        assert live.complete == batch.complete
        assert live.turns == batch.turns
        for kind in (Draw, Play, DeckEntry):
            assert (
                sum(1 for e in live.events if isinstance(e, kind))
                == sum(1 for e in batch.events if isinstance(e, kind))
            ), f"désaccord sur {kind.__name__}"
    assert total_events == sum(len(g.events) for g in batch_games)


# ---- rotation du journal (contournement de la limite 10 Mo de HS) -----------

def _session(tmp_path, name="Hearthstone_2026_08_02_00_00_00"):
    d = tmp_path / name
    d.mkdir()
    (d / "Power.log").write_text("", encoding="utf-8")
    return d


def test_rotation_desactivee_par_defaut(tmp_path):
    """Mesuré sur la vraie machine : HS n'écrit pas en mode ajout, la rotation
    ne fait que produire des fichiers à trous. Elle doit rester inactive."""
    from src.cairn.log_watcher import LiveTracker

    sess = _session(tmp_path)
    (sess / "Power.log").write_text("x\n" * 200_000, encoding="utf-8")
    tracker = LiveTracker(logs_root=tmp_path)
    tracker.poll()
    assert tracker.rotation_broken is True
    assert tracker.maybe_rotate(threshold=100_000) is False
    assert (sess / "Power.log").stat().st_size > 0   # journal intact


def test_fichier_a_trous_detecte(tmp_path):
    """Un journal presque vide en blocs alloués mais énorme en taille = HS a
    réécrit après la fin ; il ne faut surtout pas continuer à tourner."""
    from src.cairn.log_watcher import LiveTracker

    sess = _session(tmp_path)
    power = sess / "Power.log"
    with open(power, "wb") as f:      # 8 Mo annoncés, presque rien d'alloué
        f.truncate(8_000_000)
        f.seek(8_000_000)
        f.write(b"D 00:00:01.0 GameState.DebugPrintPower() - CREATE_GAME\n")
    assert LiveTracker._is_sparse(power) is True

    tracker = LiveTracker(logs_root=tmp_path)
    tracker.rotation_broken = False   # comme si l'utilisateur l'avait activée
    tracker.poll()
    assert tracker.maybe_rotate(threshold=100_000) is False
    assert tracker.rotation_broken is True


def test_rotation_si_activee_vide_le_log_et_garde_l_etat(tmp_path):
    """Chemin conservé pour un système où HS écrirait bien en mode ajout."""
    from src.cairn.log_watcher import LiveTracker

    sess = _session(tmp_path)
    power = sess / "Power.log"
    header = "D 00:00:01.0 GameState.DebugPrintPower() - CREATE_GAME\n"
    power.write_text(header + "x\n" * 200_000, encoding="utf-8")

    mirror = tmp_path / "mirror"
    tracker = LiveTracker(logs_root=tmp_path, mirror_dir=mirror)
    tracker.rotation_broken = False   # activation explicite
    tracker.poll()
    assert len(tracker.engine.games) == 1
    taille = power.stat().st_size

    # seuil explicite : inutile d'écrire 6 Mo pour tester la mécanique
    assert tracker.maybe_rotate(threshold=100_000) is True
    assert power.stat().st_size == 0          # HS repart de zéro : plus de limite
    assert len(tracker.engine.games) == 1     # l'état de jeu survit
    # le contenu est archivé, rien n'est perdu pour les fixtures
    archive = mirror / f"{sess.name}.Power.log"
    assert archive.stat().st_size == taille

    # HS continue d'écrire dans le fichier vidé : on enchaîne sans rien manquer
    with open(power, "a", encoding="utf-8") as f:
        f.write("D 00:00:02.0 GameState.DebugPrintPower() - CREATE_GAME\n")
    tracker.poll()
    assert len(tracker.engine.games) == 2


def test_pas_de_rotation_sous_le_seuil(tmp_path):
    from src.cairn.log_watcher import LiveTracker

    sess = _session(tmp_path)
    (sess / "Power.log").write_text("court\n", encoding="utf-8")
    tracker = LiveTracker(logs_root=tmp_path)
    tracker.rotation_broken = False
    tracker.poll()
    assert tracker.maybe_rotate() is False
    assert (sess / "Power.log").stat().st_size > 0


def test_rotation_refusee_si_tout_n_est_pas_lu(tmp_path):
    """Vider un fichier pas encore lu perdrait des lignes : interdit."""
    from src.cairn.log_watcher import LiveTracker

    sess = _session(tmp_path)
    power = sess / "Power.log"
    tracker = LiveTracker(logs_root=tmp_path)
    tracker.rotation_broken = False
    tracker.poll()                                  # position = 0
    power.write_text("y\n" * 400_000, encoding="utf-8")   # arrivé APRÈS le poll
    assert tracker.maybe_rotate(threshold=100_000) is False
    assert power.stat().st_size > 0


def test_rotation_inefficace_se_desactive(tmp_path):
    """Si le fichier retrouve sa taille aussitôt (écriture à trous), on renonce."""
    from src.cairn.log_watcher import LiveTracker

    sess = _session(tmp_path)
    power = sess / "Power.log"
    power.write_text("z\n" * 400_000, encoding="utf-8")
    tracker = LiveTracker(logs_root=tmp_path)
    tracker.rotation_broken = False
    tracker.poll()
    assert tracker.maybe_rotate(threshold=100_000) is True

    power.write_bytes(b"\0" * 8_000_000)   # HS a réécrit à son ancien offset
    tracker.poll()                          # le contrôle d'efficacité s'exécute
    assert tracker.rotation_broken is True
    assert tracker.maybe_rotate(threshold=100_000) is False


# ---- libération du nom Power.log (parade à la limite des 10 Mo) -------------

def test_liberation_du_nom_sans_perte(tmp_path):
    """Renommer ne perturbe ni le contenu ni l'écrivain : c'est tout l'intérêt
    face à la troncature, qui produisait un fichier à trous."""
    import os
    from src.cairn.log_watcher import LiveTracker

    sess = _session(tmp_path)
    power = sess / "Power.log"
    entete = "D 00:00:01.0 GameState.DebugPrintPower() - CREATE_GAME\n"
    power.write_text(entete + "avant\n" * 100_000, encoding="utf-8")

    tracker = LiveTracker(logs_root=tmp_path)
    tracker.poll()
    assert len(tracker.engine.games) == 1

    # un écrivain garde son descripteur ouvert, comme Hearthstone
    ecrivain = open(power, "a", encoding="utf-8")
    assert tracker.free_log_name(threshold=100_000) is True
    assert tracker.renames == 1

    # le NOM est libre et vide : c'est ce que mesurerait HS par chemin
    assert power.stat().st_size == 0
    sidecar = sess / "Power.log.cairn1"
    assert sidecar.is_file()

    # l'écrivain continue dans le MÊME fichier, sans trou ni octet nul
    ecrivain.write("D 00:00:02.0 GameState.DebugPrintPower() - CREATE_GAME\n")
    ecrivain.flush()
    st = os.stat(sidecar)
    assert st.st_blocks * 512 >= st.st_size // 2      # pas de trou
    assert sidecar.read_bytes().count(0) == 0          # aucun octet nul

    # et le suivi continue sans rien relire ni rien manquer
    tracker.poll()
    assert len(tracker.engine.games) == 2


def test_liberation_pas_repetee(tmp_path):
    """Une fois le nom libre, inutile de recommencer à chaque poll."""
    from src.cairn.log_watcher import LiveTracker

    sess = _session(tmp_path)
    (sess / "Power.log").write_text("x\n" * 100_000, encoding="utf-8")
    tracker = LiveTracker(logs_root=tmp_path)
    tracker.poll()
    assert tracker.free_log_name(threshold=10_000) is True
    assert tracker.free_log_name(threshold=10_000) is False
    assert tracker.renames == 1


def test_suit_le_journal_si_hs_le_rouvre(tmp_path):
    """Si HS repart sur un Power.log neuf, on doit basculer dessus."""
    from src.cairn.log_watcher import LiveTracker

    sess = _session(tmp_path)
    power = sess / "Power.log"
    power.write_text("y\n" * 100_000, encoding="utf-8")
    tracker = LiveTracker(logs_root=tmp_path)
    tracker.poll()
    tracker.free_log_name(threshold=10_000)
    assert tracker._tailer.path.name == "Power.log.cairn1"

    power.write_text("D 00:00:03.0 GameState.DebugPrintPower() - CREATE_GAME\n",
                     encoding="utf-8")
    tracker.poll()
    assert tracker._tailer.path == power
    assert len(tracker.engine.games) >= 1


def test_tailer_lit_par_tranches_sans_rien_perdre(tmp_path, monkeypatch):
    """Un journal plus gros qu'une tranche est rendu en plusieurs passes, dans
    l'ordre et sans perte : c'est ce qui évite de figer l'interface au démarrage
    sur un Power.log de 100 Mo (534 Mo de pointe avant, 155 après)."""
    monkeypatch.setattr(LogTailer, "_TAILLE_BLOC", 64)
    path = tmp_path / "Power.log"
    attendu = [f"ligne{i}" for i in range(200)]
    path.write_text("\n".join(attendu) + "\n")

    tailer = LogTailer(path)
    lues, passes = [], 0
    while True:
        lot = tailer.poll()
        if not lot:
            break
        lues.extend(lot)
        passes += 1

    assert lues == attendu
    assert passes > 1, "tout a été lu d'un coup : la tranche n'est pas appliquée"
    assert tailer.en_retard is False


def test_tailer_signale_le_retard_pendant_le_rattrapage(tmp_path, monkeypatch):
    """``en_retard`` pilote la cadence du QTimer : faux à tort, l'interface
    attend 500 ms entre deux tranches et le rattrapage traîne."""
    monkeypatch.setattr(LogTailer, "_TAILLE_BLOC", 32)
    path = tmp_path / "Power.log"
    path.write_text("\n".join(f"ligne{i}" for i in range(50)) + "\n")

    tailer = LogTailer(path)
    tailer.poll()
    assert tailer.en_retard is True
    while tailer.poll():
        pass
    assert tailer.en_retard is False
