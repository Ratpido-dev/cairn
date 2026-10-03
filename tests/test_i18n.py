"""Traductions : chaque table doit être complète dans TOUTES les langues.

Ajouter une langue à ``LANGS`` sans compléter les tuples laisserait passer un
``IndexError`` au premier affichage — ou pire, un libellé muet. Ces tests le
disent tout de suite, table par table, plutôt qu'au milieu d'une partie.

La terminologie chinoise suit les noms officiels de Hearthstone (zhCN) :
« 潜行者 » pour Rogue, « 灌注 » pour Imbue, « 亡语 » pour Deathrattle.
"""

from src.cairn import i18n
from src.cairn.counters import COUNTER_DEFS


def _rempli(cellule: str) -> bool:
    """Une cellule vide (ou blanchie) vaut une traduction manquante."""
    return bool(cellule and cellule.strip())


def test_toutes_les_tables_ont_une_colonne_par_langue():
    """Une colonne manquante = un IndexError en pleine partie, pas au démarrage."""
    tables = {
        "_STRINGS": i18n._STRINGS,
        "LEAGUE_NAMES": i18n.LEAGUE_NAMES,
        "ROW_LABELS": i18n.ROW_LABELS,
        "COUNTER_LABELS": i18n.COUNTER_LABELS,
        "CLASS_NAMES": i18n.CLASS_NAMES,
    }
    for nom, table in tables.items():
        for cle, ligne in table.items():
            assert len(ligne) == len(i18n.LANGS), (
                f"{nom}[{cle!r}] a {len(ligne)} colonnes, "
                f"il en faut {len(i18n.LANGS)} ({i18n.LANGS})"
            )
            for i, cellule in enumerate(ligne):
                assert _rempli(cellule), (
                    f"{nom}[{cle!r}] : colonne {i} ({i18n.LANGS[i]}) vide"
                )


def test_addon_info_a_icone_plus_une_colonne_par_langue():
    """``ADDON_INFO`` = icône en colonne 0, puis une colonne par langue."""
    for cle, ligne in i18n.ADDON_INFO.items():
        assert len(ligne) == len(i18n.LANGS) + 1, (
            f"ADDON_INFO[{cle!r}] a {len(ligne)} colonnes, "
            f"il en faut {len(i18n.LANGS) + 1} (icône + {i18n.LANGS})"
        )
        assert ligne[0], f"ADDON_INFO[{cle!r}] sans icône"
        for i, langue in enumerate(i18n.LANGS):
            assert i18n.addon_desc(cle, langue), (
                f"ADDON_INFO[{cle!r}] sans explication en {langue}"
            )


def test_chaque_addon_est_traduit_en_chinois():
    """Les fiches du launcher sont ce que l'utilisateur lit AVANT de jouer :
    une icône sans explication chinoise est un add-on qu'il n'activera pas."""
    for cdef in COUNTER_DEFS:
        assert i18n.counter_label(cdef.key, "zh"), f"{cdef.key} sans titre chinois"
        assert i18n.addon_desc(cdef.key, "zh"), f"{cdef.key} sans explication chinoise"


def test_classes_traduites_en_chinois():
    attendu = {
        "ROGUE": "潜行者",
        "WARLOCK": "术士",
        "DEATHKNIGHT": "死亡骑士",
        "DRUID": "德鲁伊",
    }
    for cle, mot in attendu.items():
        assert i18n.class_name(cle, "zh") == mot


def test_langue_inconnue_retombe_sur_le_francais():
    """Une config écrite à la main avec ``"language": "de"`` ne doit pas planter."""
    assert i18n.lang_index("de") == 0
    assert i18n.locale_of("de") == "frFR"
    assert i18n.counter_label("remaining", "de") == i18n.counter_label("remaining", "fr")
    assert i18n.t("fatigue", "de") == i18n.t("fatigue", "fr")


def test_locale_hearthstonejson():
    assert i18n.locale_of("zh") == "zhCN"
    assert i18n.locale_of("en") == "enUS"
    assert i18n.locale_of("fr") == "frFR"


def test_pluriel_seulement_en_francais():
    """L'anglais et le chinois portent la marque dans leur propre gabarit."""
    assert i18n.plural(2, "fr") == "s"
    assert i18n.plural(1, "fr") == ""
    assert i18n.plural(2, "en") == ""
    assert i18n.plural(2, "zh") == ""


def test_texte_chinois_avec_champ_de_formatage():
    """Les gabarits chinois gardent les champs nommés du français."""
    assert i18n.t("in_deck", "zh", n=28) == "牌库中 28 张"
    assert i18n.t("lethal_now", "zh", dmg=12, hp=8) == "斩杀！(12/8)"
    assert i18n.t("my_hand", "zh", n=5) == "手牌：5"
