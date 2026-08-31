"""Test d'intégration : rejoue la fixture réelle du 01/08/2026 (3 parties ranked)."""

import pytest

from src.cairn.game_state import DeckEntry, Draw, replay_file
from src.cairn.paths import FIXTURES_DIR

FIXTURE = FIXTURES_DIR / "Hearthstone_2026_08_01_00_06_06" / "Power.log"

pytestmark = pytest.mark.skipif(not FIXTURE.is_file(), reason="fixture absente")


@pytest.fixture(scope="module")
def games():
    return replay_file(FIXTURE)


def test_trois_parties_ranked_standard(games):
    assert len(games) == 3
    for game in games:
        assert game.game_type == "GT_RANKED"
        assert game.format_type == "FT_STANDARD"


def test_joueur_local_identifie(games):
    for game in games:
        local = game.local_player_id()
        assert local is not None
        # le joueur local est nommé (l'adversaire peut rester UNKNOWN au début)
        assert game.player_names.get(local, "") != "UNKNOWN HUMAN PLAYER"


def test_heros_local_est_pretre(games):
    # les 3 parties ont été jouées avec « Thief Priest »
    for game in games:
        hero = game.hero_card_id(game.local_player_id())
        assert hero is not None
        assert hero.startswith("HERO_09"), f"héros inattendu : {hero}"


def test_deux_parties_completes_une_tronquee(games):
    # La partie 3 s'interrompt au mulligan (log gelé à 00:42:09) : le parser
    # doit la restituer partiellement, sans crash — c'est un cas nominal.
    assert [g.complete for g in games] == [True, True, False]


def test_resultats_des_parties_completes(games):
    for game in (g for g in games if g.complete):
        assert set(game.results.values()) <= {"WON", "LOST", "TIED"}
        assert len(game.results) == 2
    # Vérité terrain de la session du 01/08 : une victoire puis une défaite.
    # Le résultat est relu par l'identifiant du joueur LOCAL, pas par un
    # battletag en dur : une fixture pseudonymisée (cf. ``sharing``) doit
    # passer les mêmes tests que le journal brut.
    def resultat_local(game):
        moi = game.player_names[game.local_player_id()]
        return game.results[moi]

    assert resultat_local(games[0]) == "WON"
    assert resultat_local(games[1]) == "LOST"


def test_pioches_plausibles(games):
    for game in (g for g in games if g.complete):
        local = game.local_player_id()
        draws = [
            e for e in game.events
            if isinstance(e, Draw) and e.player_id == local and not e.during_mulligan
        ]
        # fourchette large mais non triviale (parties de 17 et 29 tours)
        assert 3 <= len(draws) <= 60


def test_thief_priest_genere_des_entrees_ou_pas(games):
    # Pas d'assertion forte (dépend des parties) : on vérifie seulement que
    # les entrées éventuelles sont bien formées.
    for game in games:
        for entry in (e for e in game.events if isinstance(e, DeckEntry)):
            assert entry.entity_id > 0
            assert entry.created in (True, False)
