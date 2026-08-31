"""Import des sessions envoyées par un autre joueur (zips du collecteur Windows)."""

import zipfile

import pytest

from src.cairn.game_state import replay_file
from src.cairn.paths import FIXTURES_DIR
from tools.import_zips import main, parties, sessions_du_zip

FIXTURE = FIXTURES_DIR / "Hearthstone_2026_08_01_00_06_06"

pytestmark = pytest.mark.skipif(
    not (FIXTURE / "Power.log").is_file(), reason="fixture absente"
)


def _zip_de_session(dest, nom=FIXTURE.name, source=FIXTURE):
    """Reproduit ce que produit Compress-Archive : les journaux à plat."""
    chemin = dest / f"{nom}.zip"
    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        for f in ("Power.log", "Decks.log"):
            if (source / f).is_file():
                z.write(source / f, f)
    return chemin


def test_compte_de_parties_egale_le_rejeu():
    """CREATE_GAME apparaît deux fois par partie (GameState + PowerTaskList) :
    le compte annoncé à l'utilisateur doit suivre le moteur, pas le texte brut."""
    power = (FIXTURE / "Power.log").read_bytes()
    assert parties(power) == len(replay_file(FIXTURE / "Power.log"))
    # garde-fou explicite contre la régression « compter les deux flux »
    assert power.count(b"CREATE_GAME") == 2 * parties(power)


def test_import_puis_rejeu(tmp_path):
    source = tmp_path / "recu"
    source.mkdir()
    _zip_de_session(source)
    dest = tmp_path / "dest"

    assert main([str(p) for p in source.glob("*.zip")] + ["-d", str(dest)]) == 0
    session = dest / FIXTURE.name
    assert (session / "Power.log").is_file()
    # la session importée doit être rejouable telle quelle
    assert len(replay_file(session / "Power.log")) == 3


def test_import_idempotent(tmp_path):
    source = tmp_path / "recu"
    source.mkdir()
    _zip_de_session(source)
    dest = tmp_path / "dest"
    zips = [str(p) for p in source.glob("*.zip")]

    main(zips + ["-d", str(dest)])
    avant = (dest / FIXTURE.name / "Power.log").stat().st_mtime_ns
    main(zips + ["-d", str(dest)])   # ne doit pas réécrire
    assert (dest / FIXTURE.name / "Power.log").stat().st_mtime_ns == avant


def test_session_sans_partie_refusee(tmp_path):
    """Sans log.config, HS écrit un Power.log qui ne contient que ses erreurs
    internes : l'importer serait un piège pour les tests."""
    source = tmp_path / "recu"
    source.mkdir()
    with zipfile.ZipFile(source / "Hearthstone_2026_01_01_00_00_00.zip", "w") as z:
        z.writestr("Power.log", "erreur interne\n" * 20)
    dest = tmp_path / "dest"
    main([str(source / "Hearthstone_2026_01_01_00_00_00.zip"), "-d", str(dest)])
    assert not dest.exists() or not any(dest.iterdir())


def test_archive_corrompue_sans_crash(tmp_path, capsys):
    source = tmp_path / "recu"
    source.mkdir()
    (source / "casse.zip").write_bytes(b"pas un zip")
    assert main([str(source / "casse.zip"), "-d", str(tmp_path / "dest")]) == 0
