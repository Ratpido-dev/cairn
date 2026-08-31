"""Reconnaissance de l'archétype adverse.

Le point de tout l'exercice : un winrate par CLASSE mélange des decks opposés.
Mesuré sur les archives — face au Démoniste, 39 % en moyenne, mais 29 % contre
un Rafaam et 75 % sans.
"""

import pytest

from src.cairn import archetypes
from src.cairn.cards_db import CardsDb
from src.cairn.game_state import GameStateEngine
from src.cairn.paths import CARDS_JSON
from src.cairn.power_log import parse_lines

pytestmark = pytest.mark.skipif(not CARDS_JSON.is_file(), reason="base de cartes absente")

_L = "D 00:00:00.0000000 GameState.DebugPrintPower() - "
_G = "D 00:00:00.0000000 GameState.DebugPrintGame() - "


@pytest.fixture(scope="module")
def db():
    return CardsDb.load()


def _partie(cartes_adverses, creees=()):
    """Partie où l'adversaire (joueur 2) joue les cartes données.

    ``creees`` : les cartes engendrées par un effet, qui ne doivent JAMAIS
    servir de preuve d'archétype.
    """
    lignes = [
        _L + "CREATE_GAME",
        _L + "    GameEntity EntityID=1",
        _L + "    Player EntityID=2 PlayerID=1 GameAccountId=[hi=1 lo=111]",
        _L + "    Player EntityID=3 PlayerID=2 GameAccountId=[hi=1 lo=222]",
        _G + "PlayerID=1, PlayerName=Moi#1",
        _G + "PlayerID=2, PlayerName=UNKNOWN HUMAN PLAYER",
    ]
    eid = 50
    # un créateur en jeu, pour rattacher les cartes « offertes »
    lignes += [_L + "FULL_ENTITY - Creating ID=40 CardID=JAIL_430",
               _L + "    tag=ZONE value=PLAY", _L + "    tag=CONTROLLER value=2"]
    for card_id in cartes_adverses:
        lignes += [_L + f"FULL_ENTITY - Creating ID={eid} CardID={card_id}",
                   _L + "    tag=ZONE value=HAND", _L + "    tag=CONTROLLER value=2",
                   _L + f"TAG_CHANGE Entity={eid} tag=ZONE value=PLAY"]
        eid += 1
    for card_id in creees:
        lignes += [_L + f"FULL_ENTITY - Creating ID={eid} CardID={card_id}",
                   _L + "    tag=ZONE value=HAND", _L + "    tag=CONTROLLER value=2",
                   _L + "    tag=CREATOR value=40",
                   _L + f"TAG_CHANGE Entity={eid} tag=ZONE value=PLAY"]
        eid += 1
    engine = GameStateEngine()
    engine.feed(parse_lines(lignes))
    return engine.games[0]


def test_reconnait_un_rafaam(db):
    g = _partie(["TIME_005"])          # Rafaam, le voleur de temps
    assert archetypes.detect(g, db, 2, "WARLOCK") == "Rafaam"


def test_reconnait_les_maledictions(db):
    g = _partie(["TLC_451"])           # Catacombes maudites
    assert archetypes.detect(g, db, 2, "WARLOCK") == "Malédictions"


def test_une_carte_CREEE_ne_prouve_rien(db):
    """LE garde-fou. Un Rafaam obtenu par Découverte ou volé ne fait pas de son
    porteur un deck Rafaam — sinon ton propre Thief Priest, qui vole tout,
    serait catalogué dans l'archétype de sa victime."""
    g = _partie([], creees=["TIME_005"])
    assert archetypes.detect(g, db, 2, "WARLOCK") == ""


def test_rien_de_montre_reste_inconnu(db):
    """Une concession au tour 2 ne montre rien : on n'invente pas."""
    g = _partie([])
    assert archetypes.detect(g, db, 2, "WARLOCK") == ""


def test_classe_sans_signature_connue(db):
    g = _partie(["TIME_005"])
    assert archetypes.detect(g, db, 2, "MAGE") == ""
    assert archetypes.detect(g, db, 2, None) == ""


def test_priorite_a_la_signature_la_plus_specifique(db):
    """Un deck qui joue les deux paquets est classé sur le premier déclaré."""
    g = _partie(["TLC_451", "TIME_005"])
    assert archetypes.detect(g, db, 2, "WARLOCK") == "Rafaam"


def test_la_teinte_suit_l_entite_pas_son_rang():
    """La couleur ne doit jamais dépendre du classement : sinon « Rafaam »
    change de teinte le jour où il dépasse « Malédictions » en volume, et deux
    captures prises à un mois d'écart ne se comparent plus."""
    assert archetypes.slot("WARLOCK", "Rafaam") == 0
    assert archetypes.slot("WARLOCK", "Malédictions") == 1
    assert archetypes.slot("WARLOCK", "") == -1
    assert archetypes.slot(None, "Rafaam") == -1
    # une LISTE de référence n'a pas d'ordre déclaré : sa teinte vient d'une
    # empreinte du nom, donc elle est stable elle aussi
    a = archetypes.slot("WARLOCK", "Ma liste à moi")
    assert a >= 0 and a == archetypes.slot("WARLOCK", "Ma liste à moi")
    assert archetypes.slot("WARLOCK", "Une autre") != -1


def test_etiquette_lisible():
    assert archetypes.label("WARLOCK", "Rafaam", "Démoniste") == "Démoniste · Rafaam"
    assert archetypes.label("WARLOCK", "", "Démoniste") == "Démoniste"


# ---- listes de référence collées par l'utilisateur --------------------------

def _refs(tmp_path, db, listes):
    """Construit un jeu de listes de référence à partir de sets de card_id."""
    from src.cairn.deck_refs import DeckRef, DeckRefs
    r = DeckRefs(path=tmp_path / "refs.json")
    r.refs = [DeckRef(name=n, klass=k, card_ids=set(c)) for n, k, c in listes]
    return r


def test_appariement_reconnait_sans_carte_signature(db, tmp_path):
    """L'apport des listes : reconnaître un deck dont AUCUNE signature n'est
    tombée. C'est le cas de plus de la moitié des parties archivées."""
    refs = _refs(tmp_path, db, [
        ("Ramp", "WARLOCK", {"A", "B", "C", "D", "E", "F"}),
        ("Aggro", "WARLOCK", {"U", "V", "W", "X", "Y", "Z"}),
    ])
    nom, score = refs.match({"A", "B", "C", "D"}, "WARLOCK")
    assert nom == "Ramp" and score > 0.9


def test_trop_peu_de_cartes_vues_ne_tranche_pas(db, tmp_path):
    """Avec 3 cartes vues, aucune méthode n'est honnête. On se tait."""
    refs = _refs(tmp_path, db, [("Ramp", "WARLOCK", {"A", "B", "C", "D", "E"})])
    assert refs.match({"A", "B", "C"}, "WARLOCK") == ("", 0.0)


def test_deux_listes_a_egalite_restent_ambigues(db, tmp_path):
    """Deux decks qui partagent tout ne se départagent pas : une étiquette
    tirée au sort pollue les statistiques, un « non reconnu » ne coûte rien."""
    commun = {"A", "B", "C", "D", "E"}
    refs = _refs(tmp_path, db, [("L1", "WARLOCK", commun), ("L2", "WARLOCK", commun)])
    nom, _ = refs.match(commun, "WARLOCK")
    assert nom == ""


def test_une_carte_partagee_pese_moins_qu_une_carte_signature(db, tmp_path):
    """Le cœur du score : une carte présente dans TOUTES les listes ne
    discrimine rien, une carte unique départage à elle seule."""
    refs = _refs(tmp_path, db, [
        ("Ramp", "WARLOCK", {"COMMUN1", "COMMUN2", "COMMUN3", "RAMP1", "RAMP2"}),
        ("Aggro", "WARLOCK", {"COMMUN1", "COMMUN2", "COMMUN3", "AGG1", "AGG2"}),
    ])
    # trois cartes communes + une seule carte propre au Ramp
    nom, _ = refs.match({"COMMUN1", "COMMUN2", "COMMUN3", "RAMP1"}, "WARLOCK")
    assert nom == "Ramp", "la carte discriminante doit l'emporter sur les banales"


def test_les_listes_priment_sur_les_signatures(db, tmp_path):
    """Une liste complète est une preuve plus solide qu'une carte isolée."""
    g = _partie(["TIME_005", "AAA", "BBB", "CCC"])   # Rafaam + 3 cartes
    refs = _refs(tmp_path, db, [("Ma liste", "WARLOCK", {"TIME_005", "AAA", "BBB", "CCC"})])
    assert archetypes.detect(g, db, 2, "WARLOCK", refs=refs) == "Ma liste"
    # sans les listes, on retombe sur la signature
    assert archetypes.detect(g, db, 2, "WARLOCK") == "Rafaam"


def test_code_de_deck_illisible_est_refuse_proprement(db, tmp_path):
    from src.cairn.deck_refs import DeckRefs
    r = DeckRefs(path=tmp_path / "refs.json")
    assert "illisible" in r.add("Test", "pas-un-code", db)
    assert "nom" in r.add("", "AAECAQ8=", db)
    assert r.refs == []


# ---- variantes d'un même archétype -----------------------------------------

def test_plusieurs_listes_sous_le_meme_nom(db, tmp_path):
    """Deux joueurs du même deck changent trois cartes : c'est le même
    archétype, pas deux. Ajouter une liste ne doit donc pas écraser la
    précédente."""
    from src.cairn.deck_refs import DeckRef, DeckRefs
    r = DeckRefs(path=tmp_path / "refs.json")
    r.refs = [
        DeckRef(name="Ramp", klass="WARLOCK", card_ids={"A", "B", "C", "D", "E"},
                deckstring="code1"),
        DeckRef(name="Ramp", klass="WARLOCK", card_ids={"A", "B", "C", "X", "Y"},
                deckstring="code2"),
    ]
    assert r.variants("Ramp") == 2
    assert r.archetype_names() == [("Ramp", "WARLOCK", 2, 7)]
    # chaque variante reconnaît SES cartes propres
    assert r.match({"A", "B", "C", "D"}, "WARLOCK")[0] == "Ramp"
    assert r.match({"A", "B", "C", "X"}, "WARLOCK")[0] == "Ramp"


def test_le_coeur_commun_aux_variantes_reste_discriminant(db, tmp_path):
    """LE piège du calcul : si le poids se comptait par VARIANTE, les cartes
    communes aux deux variantes d'un deck passeraient pour peu parlantes —
    alors qu'elles sont précisément son cœur. Le comptage se fait donc par
    archétype."""
    from src.cairn.deck_refs import DeckRef, DeckRefs
    r = DeckRefs(path=tmp_path / "refs.json")
    r.refs = [
        DeckRef(name="Ramp", klass="WARLOCK", card_ids={"CŒUR1", "CŒUR2", "V1"}),
        DeckRef(name="Ramp", klass="WARLOCK", card_ids={"CŒUR1", "CŒUR2", "V2"}),
        DeckRef(name="Aggro", klass="WARLOCK", card_ids={"AGG1", "AGG2", "AGG3"}),
    ]
    nom, score = r.match({"CŒUR1", "CŒUR2", "V1", "V2"}, "WARLOCK")
    assert nom == "Ramp"
    assert score > 0.5, "le cœur commun doit peser, pas être dilué"


def test_un_archetype_vaut_sa_MEILLEURE_variante(db, tmp_path):
    """Pas l'union — sinon l'archétype le mieux documenté gagnerait toujours,
    simplement parce qu'on lui a collé plus de listes."""
    from src.cairn.deck_refs import DeckRef, DeckRefs
    r = DeckRefs(path=tmp_path / "refs.json")
    r.refs = [
        DeckRef(name="Beaucoup", klass="MAGE", card_ids={"A", "B"}),
        DeckRef(name="Beaucoup", klass="MAGE", card_ids={"C", "D"}),
        DeckRef(name="Beaucoup", klass="MAGE", card_ids={"E", "F"}),
        DeckRef(name="Precis", klass="MAGE", card_ids={"A", "B", "C", "D"}),
    ]
    # les 4 cartes vues sont TOUTES dans « Precis », éparpillées chez l'autre
    nom, _ = r.match({"A", "B", "C", "D"}, "MAGE")
    assert nom == "Precis"


def test_meme_code_colle_deux_fois_est_refuse(db, tmp_path):
    from src.cairn.deck_refs import DeckRefs
    from src.cairn.decks_log import parse_queue_events
    from src.cairn.paths import FIXTURES_DIR
    code = next(
        e.deck.deckstring
        for d in FIXTURES_DIR.glob("*/Decks.log")
        for e in parse_queue_events(d.read_text(errors="replace"))
        if e.deck.deckstring
    )
    r = DeckRefs(path=tmp_path / "refs.json")
    assert r.add("Mon deck", code, db) == ""
    assert "déjà" in r.add("Mon deck", code, db)
    assert r.variants("Mon deck") == 1


# ---- collage en masse -------------------------------------------------------

BLOC_REEL = """### Dragon Pirate Warrior
AAECAQcE6IcH69YHstgHq+AHDePmBqr8Bqv8BqWFB9KXB+yyB7XAB5XCB5zCB6bgB6fgB6ngB/vgBwAA
### You can view this deck at https://www.hsguru.com/deck/41746352

 ### Pirate Warrior
AAECAQcEt60H69YHstgHq+AHDePmBqWFB8eHB+iHB9CyB5XCB5vCB5zCB6bgB6fgB6jgB6ngB/vgBwAA
### You can view this deck at https://www.hsguru.com/deck/41738947

 ### Dragon Pirate Warrior
AAECAQcE69YHstgHp+AHq+AHDePmBqr8Bqv8BqWFB+iHB9KXB+yyB7XAB5XCB5zCB6bgB6ngB/vgBwAA
"""


def test_collage_en_masse_lit_les_noms_et_regroupe(db, tmp_path):
    """Le format d'export porte déjà le nom : redemander une saisie par liste
    serait absurde, et ingérable pour huit listes d'affilée."""
    from src.cairn.deck_refs import DeckRefs
    r = DeckRefs(path=tmp_path / "refs.json")
    n, err = r.add_paste(BLOC_REEL, db)
    assert n == 3 and err == ""
    noms = {nom: (kl, variantes) for nom, kl, variantes, _ in r.archetype_names()}
    assert noms["Dragon Pirate Warrior"] == ("WARRIOR", 2)
    assert noms["Pirate Warrior"] == ("WARRIOR", 1)


def test_la_ligne_you_can_view_n_est_pas_un_nom(db, tmp_path):
    """Les exports intercalent « ### You can view this deck at… » : la prendre
    pour un titre créerait un archétype fantôme à chaque collage."""
    from src.cairn.deck_refs import DeckRefs
    assert all("You can view" not in nom
               for nom, _ in DeckRefs.parse_paste(BLOC_REEL))


def test_un_code_nu_utilise_le_nom_saisi(db, tmp_path):
    from src.cairn.deck_refs import DeckRefs
    code = BLOC_REEL.splitlines()[1]
    r = DeckRefs(path=tmp_path / "refs.json")
    n, err = r.add_paste(code, db, defaut="Mon deck")
    assert (n, err) == (1, "")
    assert r.archetype_names()[0][0] == "Mon deck"


def test_deux_archetypes_proches_ne_produisent_jamais_de_faux(db, tmp_path):
    """LE test qui compte. « Dragon Pirate » et « Pirate » partagent 13 cartes.
    Mesuré sur 300 tirages par liste et par taille : jamais une étiquette
    fausse — au pire le silence. Une étiquette erronée pollue durablement les
    statistiques, un « non reconnu » ne coûte rien.
    """
    import random
    from src.cairn.deck_refs import DeckRefs
    r = DeckRefs(path=tmp_path / "refs.json")
    r.add_paste(BLOC_REEL, db)
    random.seed(7)
    faux = 0
    for ref in r.refs:
        for taille in (4, 6, 8):
            for _ in range(60):
                vues = set(random.sample(sorted(ref.card_ids),
                                         min(taille, len(ref.card_ids))))
                nom, _s = r.match(vues, "WARRIOR")
                if nom and nom != ref.name:
                    faux += 1
    assert faux == 0, f"{faux} étiquettes fausses : les seuils ne protègent plus"


def test_pas_de_melange_entre_listes_et_signatures(db, tmp_path):
    """Un même deck ne doit jamais porter deux noms selon ce qu'on a vu.

    Sans ce garde-fou, un Démoniste Rafaam ressortait « XL Rafaamlock » quand
    la liste correspondait et « Rafaam » (signature câblée) sinon : deux lignes
    de statistiques pour le même deck, impossibles à additionner.
    """
    from src.cairn.deck_refs import DeckRef, DeckRefs
    g = _partie(["TIME_005"])          # la signature Rafaam est jouée
    # sans liste pour la classe : la signature s'applique
    vide = DeckRefs(path=tmp_path / "vide.json")
    assert archetypes.detect(g, db, 2, "WARLOCK", refs=vide) == "Rafaam"
    # avec une liste pour la classe, mais qui ne correspond pas : on se tait
    peuple = DeckRefs(path=tmp_path / "plein.json")
    peuple.refs = [DeckRef(name="XL Rafaamlock", klass="WARLOCK",
                           card_ids={"AUTRE1", "AUTRE2", "AUTRE3", "AUTRE4"})]
    assert archetypes.detect(g, db, 2, "WARLOCK", refs=peuple) == ""
    # une classe SANS liste garde son repli de signature
    gd = _partie(["JAIL_872"])         # Chevaucheuse d'araignée, Druide
    assert archetypes.detect(gd, db, 2, "DRUID", refs=peuple) == "Araignées"


def test_contenance_entiere_rattrape_les_ambiguites(db, tmp_path):
    """Un deck qui contient TOUT ce qu'on a vu l'emporte, même à score serré.

    Cas réel mesuré sur les archives : quinze cartes vues, les quinze dans
    « Control Priest » et treize dans « Quest Priest ». La règle de marge
    refusait de trancher alors que la réponse était évidente. On n'accepte pas
    « presque autant » — on exige une couverture ENTIÈRE et unique, ce qui est
    plus sûr qu'abaisser la marge.
    """
    from src.cairn.deck_refs import DeckRef, DeckRefs
    r = DeckRefs(path=tmp_path / "refs.json")
    r.refs = [
        DeckRef(name="Control", klass="PRIEST",
                card_ids={"A", "B", "C", "D", "E", "F"}),
        DeckRef(name="Quest", klass="PRIEST",
                card_ids={"A", "B", "C", "D", "E", "Z"}),
    ]
    # les 6 cartes vues sont TOUTES dans Control, pas toutes dans Quest
    nom, _ = r.match({"A", "B", "C", "D", "E", "F"}, "PRIEST")
    assert nom == "Control"


def test_deux_contenances_restent_ambigues(db, tmp_path):
    """Si DEUX decks contiennent tout ce qu'on a vu, on ne tranche toujours
    pas : la contenance rattrape l'ambiguïté, elle ne l'ignore pas."""
    from src.cairn.deck_refs import DeckRef, DeckRefs
    r = DeckRefs(path=tmp_path / "refs.json")
    commun = {"A", "B", "C", "D", "E"}
    r.refs = [
        DeckRef(name="L1", klass="PRIEST", card_ids=commun | {"X"}),
        DeckRef(name="L2", klass="PRIEST", card_ids=commun | {"Y"}),
    ]
    assert r.match(commun, "PRIEST")[0] == ""
