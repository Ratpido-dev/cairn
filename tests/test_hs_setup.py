"""Détection du prefix Hearthstone et activation des journaux du jeu.

Tout se joue sur des faux prefixes en tmp_path : ces tests doivent passer sur
une machine où Hearthstone n'est pas installé (CI comprise).
"""

import pytest

from src.cairn import hs_setup
from src.cairn.hs_setup import (
    PREFIX_ENV,
    detect_prefix,
    ensure_log_config,
    find_log_config,
    find_prefixes,
    has_hearthstone,
    log_config_status,
    log_config_target,
)


def make_prefix(root, name="prefix", user="steamuser", with_logs=None, log_config=None):
    """Faux prefix Wine : dossier du jeu + dossier utilisateur."""
    prefix = root / name
    (prefix / hs_setup.HS_SUBPATH / "Logs").mkdir(parents=True)
    (prefix / "drive_c/users" / user / "AppData/Local/Blizzard/Hearthstone").mkdir(
        parents=True
    )
    for session in with_logs or []:
        (prefix / hs_setup.HS_SUBPATH / "Logs" / session).mkdir()
    if log_config is not None:
        target = (
            prefix / "drive_c/users" / user
            / "AppData/Local/Blizzard/Hearthstone/log.config"
        )
        target.write_text(log_config, encoding="utf-8")
    return prefix


# ---- détection --------------------------------------------------------------

def test_reconnait_un_prefix_valide(tmp_path):
    prefix = make_prefix(tmp_path)
    assert has_hearthstone(prefix)
    assert not has_hearthstone(tmp_path / "rien")


def test_variable_d_environnement_prioritaire(tmp_path, monkeypatch):
    prefix = make_prefix(tmp_path)
    monkeypatch.setenv(PREFIX_ENV, str(prefix))
    assert detect_prefix() == prefix


def test_override_prioritaire_sur_l_environnement(tmp_path, monkeypatch):
    a = make_prefix(tmp_path, "a")
    b = make_prefix(tmp_path, "b")
    monkeypatch.setenv(PREFIX_ENV, str(a))
    assert detect_prefix(override=str(b)) == b


def test_override_invalide_ignore(tmp_path, monkeypatch):
    """Un chemin faux ne doit pas empêcher la détection normale de prendre le relais."""
    prefix = make_prefix(tmp_path)
    monkeypatch.setenv(PREFIX_ENV, str(tmp_path / "nexiste_pas"))
    monkeypatch.setattr(hs_setup, "find_prefixes", lambda: [prefix])
    assert detect_prefix() == prefix


def test_aucun_prefix_rend_none(tmp_path, monkeypatch):
    monkeypatch.delenv(PREFIX_ENV, raising=False)
    monkeypatch.setattr(hs_setup, "iter_candidate_prefixes", lambda: iter(()))
    assert find_prefixes() == []
    assert detect_prefix() is None


def test_departage_par_journal_le_plus_recent(tmp_path, monkeypatch):
    """Deux installations (ex. un prefix de sauvegarde) : on prend la vivante."""
    import os
    import time

    vieux = make_prefix(tmp_path, "vieux", with_logs=["Hearthstone_2020_01_01_00_00_00"])
    recent = make_prefix(tmp_path, "recent", with_logs=["Hearthstone_2026_08_02_00_00_00"])
    old_time = time.time() - 86_400
    os.utime(vieux / hs_setup.HS_SUBPATH / "Logs/Hearthstone_2020_01_01_00_00_00",
             (old_time, old_time))

    monkeypatch.setattr(hs_setup, "iter_candidate_prefixes", lambda: iter([vieux, recent]))
    assert find_prefixes()[0] == recent
    monkeypatch.delenv(PREFIX_ENV, raising=False)
    assert detect_prefix() == recent


# ---- log.config -------------------------------------------------------------

BON = "[Power]\nFilePrinting=true\n\n[Decks]\nFilePrinting=true\n"


def test_log_config_absent(tmp_path):
    prefix = make_prefix(tmp_path)
    status = log_config_status(prefix)
    assert status.state == "missing" and not status.ready
    # on sait quand même OÙ l'écrire
    assert log_config_target(prefix) is not None


def test_log_config_complet_reconnu(tmp_path):
    prefix = make_prefix(tmp_path, log_config=BON)
    assert log_config_status(prefix).ready


def test_log_config_incomplet_detecte(tmp_path):
    """Power seul (ou désactivé) ne suffit pas : il manque Decks."""
    prefix = make_prefix(tmp_path, log_config="[Power]\nFilePrinting=true\n")
    assert log_config_status(prefix).state == "incomplete"

    prefix2 = make_prefix(
        tmp_path, "p2", log_config="[Power]\nFilePrinting=false\n\n[Decks]\nFilePrinting=true\n"
    )
    assert log_config_status(prefix2).state == "incomplete"


def test_ecriture_du_log_config(tmp_path):
    prefix = make_prefix(tmp_path)
    status = ensure_log_config(prefix)
    assert status.ready
    text = status.path.read_text(encoding="utf-8")
    assert "[Power]" in text and "[Decks]" in text
    # exactement deux loggers : chaque logger en plus rapproche la limite des 10 Mo
    assert text.count("FilePrinting=true") == 2


def test_config_existante_sauvegardee_avant_reecriture(tmp_path):
    """Le log.config peut venir d'un autre tracker : on ne l'écrase pas sans copie."""
    ancien = "[Power]\nFilePrinting=true\n\n[Zone]\nFilePrinting=true\n"
    prefix = make_prefix(tmp_path, log_config=ancien)
    status = ensure_log_config(prefix)

    assert status.ready
    backup = status.path.with_suffix(".config.bak")
    assert backup.is_file() and backup.read_text(encoding="utf-8") == ancien


def test_config_deja_bonne_laissee_intacte(tmp_path):
    prefix = make_prefix(tmp_path, log_config=BON)
    path = find_log_config(prefix)
    avant = path.read_text(encoding="utf-8")
    ensure_log_config(prefix)
    assert path.read_text(encoding="utf-8") == avant     # pas touché
    assert not path.with_suffix(".config.bak").exists()  # pas de sauvegarde inutile


def test_dossier_utilisateur_non_standard(tmp_path):
    """Sous Lutris le dossier porte le vrai nom de compte, pas « steamuser »."""
    prefix = make_prefix(tmp_path, user="ratpido", log_config=BON)
    status = log_config_status(prefix)
    assert status.ready and "ratpido" in str(status.path)


def test_sans_prefix_pas_de_plantage():
    assert log_config_status(None).state == "no_prefix"


# ---- secrets ----------------------------------------------------------------

def test_secrets_candidats(tmp_path):
    """Les candidats sont filtrés par classe, format et secrets déjà dévoilés."""
    from src.cairn.cards_db import CardsDb
    from src.cairn.game_state import Entity, Game
    from src.cairn.paths import CARDS_JSON
    from src.cairn.secrets import STANDARD_SETS, candidates, secrets_in_play

    if not CARDS_JSON.is_file():
        pytest.skip("base de cartes absente")
    db = CardsDb.load()

    game = Game(player_names={1: "moi", 2: "adv"}, format_type="FT_STANDARD")
    # un secret posé face cachée : l'entité n'a pas de cardId
    game.entities[50] = Entity(entity_id=50, tags={"ZONE": "SECRET", "CONTROLLER": "2"})
    assert secrets_in_play(game, db, 2) == 1

    mage = candidates(game, db, 2, "MAGE")
    assert mage, "un Mage a des secrets"
    assert all(db.by_card_id[c.card_id]["set"] in STANDARD_SETS for c in mage)
    assert all(db.by_card_id[c.card_id]["cardClass"] == "MAGE" for c in mage)
    couts = [c.cost for c in mage]
    assert couts == sorted(couts)

    # Une classe sans secret propose TOUS ceux du format, pas rien : un secret
    # peut avoir été découvert ou volé. Vu en partie — un Voleur avait posé un
    # secret de Mage et la liste restait vide. Le prix est du bruit quand un
    # Sigil de Chasseur de démons traîne dans la zone SECRET ; onze candidats
    # valent mieux qu'aucun quand le secret est réel.
    autres = candidates(game, db, 2, "DEMONHUNTER")
    assert autres and {db.by_card_id[c.card_id]["cardClass"] for c in autres} > {"MAGE"}
    # sans secret en jeu, pas de liste
    game.entities[50].tags["ZONE"] = "GRAVEYARD"
    assert candidates(game, db, 2, "MAGE") == []


def test_quete_dans_la_zone_secret_ignoree(tmp_path):
    """La zone SECRET accueille aussi les quêtes : elles ne doivent pas compter."""
    from src.cairn.cards_db import CardsDb
    from src.cairn.game_state import Entity, Game
    from src.cairn.paths import CARDS_JSON
    from src.cairn.secrets import secrets_in_play

    if not CARDS_JSON.is_file():
        pytest.skip("base de cartes absente")
    db = CardsDb.load()
    game = Game(player_names={1: "moi", 2: "adv"})
    # TLC_817t = « Dissipation des ténèbres », une QUÊTE observée en zone SECRET
    game.entities[60] = Entity(entity_id=60, card_id="TLC_817t",
                               tags={"ZONE": "SECRET", "CONTROLLER": "2"})
    assert secrets_in_play(game, db, 2) == 0


# ---- plafond des journaux (client.config) ------------------------------------

def test_plafond_leve_par_client_config(tmp_path):
    """La clé FileSizeLimit.Int=-1 est ce qui empêche HS de couper son logger."""
    from src.cairn.hs_setup import (
        client_config_ok, client_config_path, ensure_client_config,
    )

    prefix = make_prefix(tmp_path)
    assert client_config_ok(prefix) is False
    assert ensure_client_config(prefix) is True
    assert client_config_ok(prefix) is True

    text = client_config_path(prefix).read_text(encoding="utf-8")
    assert "[Log]" in text and "FileSizeLimit.Int=-1" in text


def test_client_config_existant_preserve(tmp_path):
    """Le fichier peut contenir des réglages Blizzard : on n'en perd aucun."""
    from src.cairn.hs_setup import client_config_path, ensure_client_config

    prefix = make_prefix(tmp_path)
    path = client_config_path(prefix)
    path.write_text("Aurora.ClientCheck=false\nLocalization.Locale=frFR\n",
                    encoding="utf-8")

    assert ensure_client_config(prefix) is True
    text = path.read_text(encoding="utf-8")
    assert "Aurora.ClientCheck=false" in text
    assert "Localization.Locale=frFR" in text
    assert "FileSizeLimit.Int=-1" in text
    # copie de sécurité de l'original
    assert path.with_suffix(".config.bak").is_file()


def test_valeur_de_plafond_erronee_corrigee(tmp_path):
    """Une limite déjà posée mais finie doit être remplacée, pas dupliquée."""
    from src.cairn.hs_setup import client_config_ok, client_config_path, ensure_client_config

    prefix = make_prefix(tmp_path)
    path = client_config_path(prefix)
    path.write_text("[Log]\nFileSizeLimit.Int=10000\n", encoding="utf-8")
    assert client_config_ok(prefix) is False

    assert ensure_client_config(prefix) is True
    text = path.read_text(encoding="utf-8")
    assert text.count("FileSizeLimit.Int") == 1
    assert "FileSizeLimit.Int=-1" in text


def test_deja_leve_laisse_intact(tmp_path):
    from src.cairn.hs_setup import client_config_path, ensure_client_config

    prefix = make_prefix(tmp_path)
    path = client_config_path(prefix)
    path.write_text("[Log]\nFileSizeLimit.Int=-1\n", encoding="utf-8")
    avant = path.read_text(encoding="utf-8")
    assert ensure_client_config(prefix) is True
    assert path.read_text(encoding="utf-8") == avant
    assert not path.with_suffix(".config.bak").exists()
