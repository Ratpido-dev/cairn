"""Base de cartes HearthstoneJSON, indexée par dbfId et par cardId.

La base principale est le **frFR** : c'est la seule qui porte les mécaniques,
races, `pos` et `imbue` dont le moteur a besoin. Les autres langues (en, zh)
n'ajoutent qu'une table ``id → nom`` et un fichier de textes de règles,
chargés à la demande — cf. ``localized_name`` et ``text``.

Le JSON est téléchargé par ``cairn-cards`` (cf. ``cards_fetch``) et mis en
cache dans ``data/cards/``. Ce module ne fait aucune requête réseau.
"""

from __future__ import annotations

import json
from pathlib import Path

from .paths import (
    CARDS_JSON,
    CARDS_JSON_EN,
    CARDS_JSON_ZH,
    CARDS_TEXT,
    CARDS_TEXT_EN,
    CARDS_TEXT_ZH,
)

# Locales secondaires : une simple table id → nom, chargée à la première
# demande. La base principale (frFR) reste celle qui porte les mécaniques.
#
# Les chemins sont résolus à CHAQUE appel, pas figés à l'import : c'est ce que
# fait déjà le reste du projet (cards_fetch, app…), et ça permet aux tests de
# remplacer les constantes par monkeypatch — cf. tests/test_card_text.py, qui
# vérifie le repli du texte anglais sur le français.
def _names_path(lang: str):
    """Fichier id → nom d'une langue secondaire, ou None si la base frFR suffit."""
    return {"en": CARDS_JSON_EN, "zh": CARDS_JSON_ZH}.get(lang)


def _text_path(lang: str):
    """Fichier des textes de règles d'une langue."""
    return {"fr": CARDS_TEXT, "en": CARDS_TEXT_EN, "zh": CARDS_TEXT_ZH}.get(lang)


# Seuls champs utilisés par le tracker — le JSON complet en contient des
# dizaines d'autres (textes, flavor, mechanics…) qui tripleraient la RAM.
_KEPT_FIELDS = ("id", "dbfId", "name", "cost", "cardClass", "type", "rarity", "set",
                "collectible")


class CardsDb:
    def __init__(self, cards: list[dict]):
        slim = [{k: c[k] for k in _KEPT_FIELDS if k in c} for c in cards]
        self.by_dbf_id: dict[int, dict] = {c["dbfId"]: c for c in slim if "dbfId" in c}
        self.by_card_id: dict[str, dict] = {c["id"]: c for c in slim if "id" in c}
        # Mécaniques : un set d'ids coûte bien moins de RAM qu'un champ par carte
        # (la liste `mechanics` complète triplerait l'empreinte, cf. _KEPT_FIELDS).
        self.deathrattle_ids: set[str] = {
            c["id"] for c in cards
            if "id" in c and "DEATHRATTLE" in (c.get("mechanics") or ())
        }
        self.secret_ids: set[str] = {
            c["id"] for c in cards
            if "id" in c and c.get("collectible")
            and "SECRET" in (c.get("mechanics") or ())
        }
        self.dragon_ids: set[str] = {
            c["id"] for c in cards
            if "id" in c and "DRAGON" in ((c.get("races") or []) + [c.get("race") or ""])
        }
        # Cartes qui placent quelque chose à un bout du deck — le drapeau « pos »
        # est calculé au téléchargement (cf. cards_fetch.deck_position). Vide sur
        # une base antérieure à cette version : le suivi du fond de deck se tait
        # simplement, jusqu'au prochain `cairn-cards all`.
        self.deck_bottom_ids: set[str] = {
            c["id"] for c in cards if c.get("pos") == "bottom" and "id" in c
        }
        self.deck_top_ids: set[str] = {
            c["id"] for c in cards if c.get("pos") == "top" and "id" in c
        }

        # Pouvoirs héroïques « empreints » : leur niveau vit dans le tag
        # TAG_SCRIPT_DATA_NUM_1 de l'entité en jeu (vu jusqu'à 8).
        self.imbued_hero_powers: set[str] = {
            c["id"] for c in cards if c.get("imbue") and "id" in c
        }

        # noms des locales secondaires (en, zh), par langue — à la demande
        self._names: dict[str, dict[str, str]] = {}
        # textes de règles, par langue — chargés au premier survol seulement
        self._texts: dict[str, dict[str, str]] = {}

    def localized_name(self, card_id: str | None, lang: str = "fr") -> str:
        """Nom de carte dans la langue voulue.

        Les langues autres que le frFR viennent d'un fichier séparé
        (id → name, ~1,8 Mo) chargé à la première demande : inutile de doubler
        la base complète en mémoire. Retombe sur le nom français si la locale
        n'a pas de table, ou si la carte n'y figure pas.
        """
        card = self.by_card_id.get(card_id or "")
        fr = card.get("name", card_id or "?") if card else (card_id or "?")
        chemin = _names_path(lang)
        if chemin is None:
            return fr
        table = self._names.get(lang)
        if table is None:
            try:
                with open(chemin, encoding="utf-8") as f:
                    table = {c["id"]: c["name"] for c in json.load(f) if "id" in c}
            except (OSError, json.JSONDecodeError):
                table = {}
            self._names[lang] = table
        return table.get(card_id or "", fr)

    def text(self, card_id: str | None, lang: str = "fr") -> str:
        """Texte de règles d'une carte — vide si la base n'en a pas.

        C'est ce qui rend les « effets en jeu » lisibles : un enchantement
        (Protection d'Amara, Âme brisée…) n'a AUCUN rendu de carte à afficher,
        seulement un nom — sans son texte, l'effet reste une devinette.

        Fichier séparé chargé à la première demande, comme les noms : les
        textes pèsent autant que toute la base élaguée, et une partie sur deux
        se joue sans jamais survoler un effet.
        """
        if not card_id:
            return ""
        cle = lang if _text_path(lang) else "fr"
        table = self._texts.get(cle)
        if table is None:
            try:
                with open(_text_path(cle), encoding="utf-8") as f:
                    table = json.load(f)
            except (OSError, json.JSONDecodeError):
                table = {}
            self._texts[cle] = table
        texte = table.get(card_id, "")
        # base antérieure aux textes, ou carte sans texte dans cette langue :
        # le français vaut mieux que rien
        if not texte and cle != "fr":
            texte = self.text(card_id, "fr")
        return texte

    def has_deathrattle(self, card_id: str | None) -> bool:
        return bool(card_id) and card_id in self.deathrattle_ids

    def is_dragon(self, card_id: str | None) -> bool:
        return bool(card_id) and card_id in self.dragon_ids

    def is_secret(self, card_id: str | None) -> bool:
        return bool(card_id) and card_id in self.secret_ids

    @classmethod
    def load(cls, path: Path = CARDS_JSON) -> "CardsDb":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def name(self, dbf_id: int) -> str:
        card = self.by_dbf_id.get(dbf_id)
        return card["name"] if card else f"dbfId:{dbf_id}"

    def cost(self, dbf_id: int) -> int | None:
        card = self.by_dbf_id.get(dbf_id)
        return card.get("cost") if card else None

    def __len__(self) -> int:
        return len(self.by_dbf_id)
