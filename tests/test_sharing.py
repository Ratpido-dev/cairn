"""Partage volontaire : consentement, pseudonymisation, file d'attente."""

import re

import pytest

from src.cairn.cards_db import CardsDb
from src.cairn.config import Config
from src.cairn.deck_view import compute_deck_view, opponent_class
from src.cairn.game_state import replay_file
from src.cairn.paths import CARDS_JSON, FIXTURES_DIR
from src.cairn.sharing import (
    Pseudonymiseur,
    preparer,
    taille_outbox,
    vider_outbox,
)

FIXTURE = FIXTURES_DIR / "Hearthstone_2026_08_01_00_06_06"

pytestmark = pytest.mark.skipif(
    not (FIXTURE / "Power.log").is_file() or not CARDS_JSON.is_file(),
    reason="fixture ou base de cartes absente",
)


def battletags_de_la_fixture() -> set[str]:
    """Battletags réellement présents dans la fixture.

    Relus au lieu d'être écrits en dur : un battletag est une donnée
    personnelle — celle de l'adversaire comprise, qui n'a rien demandé — et
    n'a donc rien à faire dans un dépôt public. C'est tout l'objet du module
    testé ici, autant ne pas le contredire dans ses propres tests.
    """
    texte = (FIXTURE / "Power.log").read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r"Entity=([^\s\[\]]+#\d+)", texte))


# ---- consentement ----------------------------------------------------------

def test_consentement_pas_pose_par_defaut():
    """Trois états : sans eux, impossible de distinguer « a refusé » de
    « n'a pas encore vu la question » — et la fenêtre reviendrait sans fin."""
    c = Config()
    assert c.share_games == ""
    assert c.consent_asked is False
    assert c.share_enabled is False


@pytest.mark.parametrize("reponse, actif", [("yes", True), ("no", False)])
def test_consentement_persiste(tmp_path, reponse, actif):
    chemin = tmp_path / "config.json"
    c = Config()
    c.share_games = reponse
    c.save(chemin)
    relu = Config.load(chemin)
    assert relu.share_games == reponse
    assert relu.consent_asked is True       # la question ne sera plus reposée
    assert relu.share_enabled is actif


def test_valeur_de_partage_invalide_retombe_sur_non_pose(tmp_path):
    chemin = tmp_path / "config.json"
    chemin.write_text('{"share_games": "peut-etre"}', encoding="utf-8")
    assert Config.load(chemin).share_games == ""


def test_anonymisation_non_desactivable():
    """Il ne doit RESTER aucun moyen d'envoyer des journaux bruts.

    Ni réglage en config, ni paramètre de ``preparer`` : le consentement de
    l'utilisateur ne couvre pas son adversaire, qui apparaît dans le même
    fichier sans avoir rien accepté.
    """
    import inspect

    from src.cairn import sharing

    assert not hasattr(Config(), "share_anonymise")
    assert "anonymiser" not in inspect.signature(sharing.preparer).parameters


# ---- pseudonymisation ------------------------------------------------------

def test_identifiants_remplaces():
    p = Pseudonymiseur(sel="sel")
    sortie = p.texte(
        "PlayerName=Joueur#12345 "
        "GameAccountId=[hi=144115198130930503 lo=103736218]"
    )
    assert "Joueur#12345" not in sortie
    assert "103736218" not in sortie
    assert "144115198130930503" not in sortie
    # la forme reste celle d'un battletag : le parseur n'a rien à savoir
    assert "#" in sortie and "PlayerName=" in sortie


def test_jeton_stable_dans_un_meme_flux():
    """Deux mentions du même joueur doivent donner le MÊME jeton, sinon le
    moteur ne relie plus ses événements entre eux."""
    p = Pseudonymiseur(sel="sel")
    a = p.texte("Entity=Adversaire#67890")
    b = p.texte("Entity=Adversaire#67890")
    assert a == b


def test_sel_different_jeton_different():
    """Sans sel, un même battletag donnerait le même jeton chez tout le monde,
    et recouper les envois de plusieurs utilisateurs redeviendrait possible."""
    a = Pseudonymiseur(sel="alice").texte("Adversaire#67890")
    b = Pseudonymiseur(sel="bob").texte("Adversaire#67890")
    assert a != b


def test_joueurs_distincts_jetons_distincts():
    p = Pseudonymiseur(sel="sel")
    sortie = p.texte("A=Joueur#12345 B=Adversaire#67890")
    jetons = {m for m in sortie.split() }
    assert len(jetons) == 2
    assert p.joueurs_remplaces == 2


def test_nom_sans_discriminant_remplace_aussi():
    """Hearthstone écrit parfois le joueur sans son numéro — c'est la fuite qui
    survivait à la pseudonymisation, et un pseudo seul suffit à identifier."""
    p = Pseudonymiseur(sel="sel")
    sortie = p.texte(
        "PlayerName=Adversaire#67890\n"
        "FULL_ENTITY - Updating Adversaire CardID=\n"
    )
    assert "Adversaire" not in sortie
    # le lien entre les deux lignes doit survivre : même joueur, même jeton
    lignes = sortie.splitlines()
    assert lignes[1].split("Updating ")[1].split(" ")[0] == \
        lignes[0].split("=")[1].split("#")[0]


def test_nom_nu_ne_mord_pas_dans_un_mot_plus_long():
    """Un joueur nommé « Kobo » ne doit pas transformer « Kobold » : le
    remplacement est ancré sur des frontières de mot, sinon il abîmerait des
    noms de cartes."""
    p = Pseudonymiseur(sel="sel")
    sortie = p.texte("Entity=Kobo#11111 CardID=Kobold entityName=Kobo")
    assert "Kobold" in sortie
    assert "=Kobo " not in sortie and not sortie.endswith("Kobo")


def test_non_joueurs_intacts():
    """« UNKNOWN HUMAN PLAYER » n'est pas quelqu'un : le remplacer casserait
    la détection du joueur local sans rien protéger."""
    p = Pseudonymiseur(sel="sel")
    assert "UNKNOWN" in p.texte("PlayerName=UNKNOWN")
    assert p.joueurs_remplaces == 0


# ---- la propriété qui décide de tout ---------------------------------------

def test_partie_pseudonymisee_se_rejoue_a_l_identique(tmp_path):
    """LE test : si la pseudonymisation changeait quoi que ce soit au rejeu,
    elle coûterait quelque chose. Elle ne coûte rien — c'est l'argument."""
    db = CardsDb.load()

    def resume(dossier):
        return [
            (
                opponent_class(g, db),
                compute_deck_view(g, None, db).result,
                g.turns,
                len(compute_deck_view(g, None, db).my_graveyard),
            )
            for g in replay_file(dossier / "Power.log")
        ]

    sortie = preparer(FIXTURE, sel="sel", dest=tmp_path)
    assert resume(sortie) == resume(FIXTURE)

    texte = (sortie / "Power.log").read_text(encoding="utf-8")
    for tag in battletags_de_la_fixture():
        assert tag not in texte, f"{tag} a survécu à la pseudonymisation"


def test_une_vieille_config_ne_reactive_rien(tmp_path):
    """Un ``config.json`` d'avant portant « share_anonymise: false » ne doit pas
    ressusciter le comportement : la clé est simplement ignorée."""
    chemin = tmp_path / "config.json"
    chemin.write_text('{"share_games": "yes", "share_anonymise": false}',
                      encoding="utf-8")
    cfg = Config.load(chemin)
    assert cfg.share_enabled is True
    assert not hasattr(cfg, "share_anonymise")

    sortie = preparer(FIXTURE, sel="sel", dest=tmp_path / "out")
    texte = (sortie / "Power.log").read_text(encoding="utf-8")
    for tag in battletags_de_la_fixture():
        assert tag not in texte


# ---- file d'attente --------------------------------------------------------

def test_outbox_comptee_puis_videe(tmp_path):
    assert taille_outbox(tmp_path) == (0, 0)
    preparer(FIXTURE, sel="sel", dest=tmp_path)
    sessions, octets = taille_outbox(tmp_path)
    assert sessions == 1 and octets > 0
    assert vider_outbox(tmp_path) == 1
    assert taille_outbox(tmp_path) == (0, 0)


def test_preparer_idempotent(tmp_path):
    """Appelée à chaque fin de partie d'une même session, sans empiler."""
    preparer(FIXTURE, sel="sel", dest=tmp_path)
    preparer(FIXTURE, sel="sel", dest=tmp_path)
    assert taille_outbox(tmp_path)[0] == 1


def test_session_sans_power_log_ignoree(tmp_path):
    vide = tmp_path / "Hearthstone_vide"
    vide.mkdir()
    assert preparer(vide, sel="sel", dest=tmp_path / "out") is None


# ---- le comportement « une seule fois », vu depuis l'UI --------------------

def test_consentement_ne_se_pose_quune_fois(tmp_path, monkeypatch):
    """Exigence centrale : la fenêtre s'ouvre au premier lancement, jamais après.

    On passe par le pont, pas seulement par Config : c'est « consentAsked »
    qui pilote la visibilité de la fenêtre côté QML.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    pytest.importorskip("PySide6")
    from src.cairn.ui.bridge import TrackerBridge

    pont = TrackerBridge(logs_root=tmp_path / "logs", poll_ms=10_000_000,
                         history_path=tmp_path / "h.sqlite")
    try:
        assert pont.consentAsked is False     # la fenêtre s'affiche
        assert pont.shareGames is False       # rien n'est coché d'avance

        pont.answerConsent(True)
        assert pont.consentAsked is True      # elle ne reviendra plus
        assert pont.shareGames is True

        # un nouveau lancement relit la config : toujours pas de question
        autre = TrackerBridge(logs_root=tmp_path / "logs", poll_ms=10_000_000,
                              history_path=tmp_path / "h.sqlite")
        try:
            assert autre.consentAsked is True
            assert autre.shareGames is True
        finally:
            autre.shutdown()

        # et le réglage reste révocable à tout moment
        pont.setShareGames(False)
        assert pont.shareGames is False
        assert pont.consentAsked is True      # sans reposer la question
    finally:
        pont.shutdown()


def test_refuser_efface_ce_qui_attendait(tmp_path, monkeypatch):
    """Couper le partage doit vider la file : sinon des parties resteraient
    prêtes à partir alors que l'utilisateur vient de dire non."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("CAIRN_DATA_DIR", str(tmp_path / "data"))
    pytest.importorskip("PySide6")
    from src.cairn import sharing
    from src.cairn.ui.bridge import TrackerBridge

    sharing.preparer(FIXTURE, sel="sel")
    assert taille_outbox()[0] == 1

    pont = TrackerBridge(logs_root=tmp_path / "logs", poll_ms=10_000_000,
                         history_path=tmp_path / "h.sqlite")
    try:
        pont.setShareGames(False)
        assert taille_outbox()[0] == 0
    finally:
        pont.shutdown()


# ---- rang déclaré ----------------------------------------------------------
#
# Hearthstone n'écrit le rang dans AUCUN de ses journaux : vérifié sur toutes
# les sessions disponibles (ni LEAGUE_ID, ni STAR_LEVEL, ni MEDAL, ni le moindre
# nom de ligue). Firestone et HDT le lisent dans la mémoire du jeu. Il est donc
# déclaré par le joueur — d'où ces tests sur la persistance et le libellé.

def test_aucun_rang_dans_les_journaux():
    """Garde-fou documentaire : si un patch de HS se mettait à écrire le rang,
    ce test casserait et signalerait qu'on peut enfin l'automatiser."""
    texte = (FIXTURE / "Power.log").read_text(encoding="utf-8", errors="replace")
    for tag in ("LEAGUE_ID", "STAR_LEVEL", "LEGEND_RANK", "MEDAL", "PLAYER_RANK"):
        assert f"tag={tag} " not in texte


def test_rang_persiste_et_saffiche(tmp_path):
    from src.cairn.config import LEAGUES

    assert "GOLD" in LEAGUES
    chemin = tmp_path / "config.json"
    c = Config()
    c.rank_league, c.rank_level = "GOLD", 7
    c.save(chemin)
    relu = Config.load(chemin)
    assert (relu.rank_league, relu.rank_level) == ("GOLD", 7)


def test_ligue_inconnue_ignoree(tmp_path):
    chemin = tmp_path / "config.json"
    chemin.write_text('{"rank_league": "ADAMANTIUM", "rank_level": 99}', encoding="utf-8")
    relu = Config.load(chemin)
    assert relu.rank_league == ""
    assert relu.rank_level == 10        # borné, jamais 99


def test_rang_voyage_dans_les_metadonnees(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    pytest.importorskip("PySide6")
    import json

    from src.cairn.ui.bridge import TrackerBridge
    from src.cairn.sharing import metadonnees

    pont = TrackerBridge(logs_root=tmp_path / "logs", poll_ms=10_000_000,
                         history_path=tmp_path / "h.sqlite")
    try:
        pont.setRank(3, 7)                       # index 3 = GOLD
        assert pont.rankLabel == "Or 7"
        assert pont.rankHasLevel is True

        meta = metadonnees([], install_id="uuid", rang=pont._rang_brut())
        assert meta["rang_declare"] == "GOLD 7"
        json.dumps(meta)                          # doit rester sérialisable

        pont.setRank(6, 5)                        # index 6 = LEGEND
        assert pont.rankLabel == "Légende"
        assert pont.rankHasLevel is False         # pas de palier 10 → 1

        pont.setRank(0, 0)                        # « non renseigné »
        assert pont.rankLabel == ""
        assert pont._rang_brut() == ""
    finally:
        pont.shutdown()


def test_mode_de_partie_recopie_dans_les_metadonnees():
    """GameType/FormatType SONT dans le journal : une analyse par rang doit
    pouvoir écarter le classique et l'arène sans tout rejouer."""
    from src.cairn.game_state import replay_file

    parties = replay_file(FIXTURE / "Power.log")
    assert any(g.game_type == "GT_RANKED" for g in parties)
    assert any(g.format_type == "FT_STANDARD" for g in parties)


def test_loadingscreen_inclus_dans_le_partage(tmp_path):
    """Il distingue construit / arène / Battlegrounds."""
    from src.cairn.sharing import FICHIERS

    assert "LoadingScreen.log" in FICHIERS
    sortie = preparer(FIXTURE, sel="sel", dest=tmp_path)
    if (FIXTURE / "LoadingScreen.log").is_file():
        assert (sortie / "LoadingScreen.log").is_file()
