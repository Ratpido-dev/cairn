"""Traductions des textes produits par Python (compteurs, pools).

Les libellés purement visuels du QML sont traduits côté QML (``tr()`` dans
``Launcher.qml``) ; ici on ne traite que ce que le moteur fabrique lui-même.

Une entrée = une clé, un couple ``(français, anglais)``. Les valeurs peuvent
contenir des champs de formatage nommés.
"""

from __future__ import annotations

LANGS = ("fr", "en")

_STRINGS: dict[str, tuple[str, str]] = {
    "unknownDeck": ("deck non reconnu", "unidentified deck"),
    # compteurs
    "in_deck": ("{n} au deck", "{n} in deck"),
    "fatigue": ("FATIGUE", "FATIGUE"),
    "fatigue_dmg": ("fatigue {n}", "fatigue {n}"),
    "imbue": ("empreint {n}", "imbue {n}"),
    "the_coin": ("La pièce", "The Coin"),
    "my_hand": ("main : {n}", "hand: {n}"),
    "opp_hand": ("adv : {n}", "opp: {n}"),
    "opp_hand_created": ("adv : {n} ({c} créée{s})", "opp: {n} ({c} created)"),
    "plays_this_turn": ("{n} ce tour", "{n} this turn"),
    "lethal_now": ("LÉTAL ! ({dmg}/{hp})", "LETHAL! ({dmg}/{hp})"),
    "lethal_left": ("létal : reste {n}", "lethal: {n} left"),
    "rafaam": ("Rafaam {n}/9", "Rafaam {n}/9"),
    "rafaam_lethal": ("Rafaam {n}/9 — LÉTAL", "Rafaam {n}/9 — LETHAL"),
    "atlas": ("atlas {n}", "atlas {n}"),
    "shots": ("projectiles {n}", "shots {n}"),
    "replay": ("serviteurs à (1) : {n}", "1-cost minions: {n}"),
    "spells": ("sorts {n}/5", "spells {n}/5"),
    "dragons": ("dragons {n}/8", "dragons {n}/8"),
    "died": ("morts {n}/20", "died {n}/20"),
    "corpses": ("{n} cadavres", "{n} corpses"),
    "side_me": ("moi ", "me "),
    "side_opp": ("adv ", "opp "),
    # familles à cocher (quels membres ont déjà été posés)
    "family_rafaam": ("RAFAAM", "RAFAAMS"),
    "family_windrunner": ("SŒURS COURSEVENT", "WINDRUNNER SISTERS"),
    # pools de résurrection
    "pool_dr_max": ("Râle d’agonie à ({n}) ou moins", "Deathrattle costing ({n}) or less"),
    "pool_dr_min": ("Râle d’agonie à ({n}) ou plus", "Deathrattle costing ({n}) or more"),
    "pool_dr_played": ("Râle d’agonie joué cette partie", "Deathrattle played this game"),
}


LEAGUE_NAMES: dict[str, tuple[str, str]] = {
    "BRONZE": ("Bronze", "Bronze"),
    "SILVER": ("Argent", "Silver"),
    "GOLD": ("Or", "Gold"),
    "PLATINUM": ("Platine", "Platinum"),
    "DIAMOND": ("Diamant", "Diamond"),
    "LEGEND": ("Légende", "Legend"),
}


def league_name(key: str | None, lang: str = "fr") -> str:
    if not key:
        return ""
    return pick(LEAGUE_NAMES.get(key, (key, key)), lang)


# Libellé COURT de chaque ligne du panneau à deux colonnes. Le camp est donné
# par la colonne, donc plus de préfixe « moi »/« adv » à écrire.
ROW_LABELS: dict[str, tuple[str, str]] = {
    "deck": ("au deck", "in deck"),
    "corpses": ("cadavres", "corpses"),
    "imbue": ("empreint", "imbue"),
    "rafaam": ("Rafaam", "Rafaam"),
    "atlas": ("atlas", "atlas"),
    "shots": ("projectiles", "shots"),
    "replay": ("serviteurs à (1)", "1-cost minions"),
    "spells": ("sorts", "spells"),
    "dragons": ("dragons", "dragons"),
    "died": ("morts", "died"),
    "lethal": ("létal", "lethal"),
    "hand": ("main", "hand"),
    "fatigue": ("fatigue", "fatigue"),
    "plays": ("ce tour", "this turn"),
}


def row_label(pair: str, lang: str = "fr") -> str:
    """Libellé de ligne, ou la clé elle-même si elle n'est pas traduite."""
    paire = ROW_LABELS.get(pair)
    return paire[1 if lang == "en" else 0] if paire else pair


# Libellés des add-ons, tels que listés dans le launcher
COUNTER_LABELS: dict[str, tuple[str, str]] = {
    "remaining": ("Cartes restantes", "Cards left"),
    "opp_remaining": ("Cartes restantes chez lui", "Cards left in their deck"),
    "imbue": ("Empreint", "Imbue"),
    "my_damage": ("Mes dégâts possibles", "My possible damage"),
    "opp_damage": ("Ses dégâts possibles", "Their possible damage"),
    "lethal": ("Distance au létal", "Distance to lethal"),
    "fatigue": ("Dégâts de fatigue", "Fatigue damage"),
    "my_hand": ("Ma main", "My hand"),
    "opp_hand": ("Main adverse", "Opponent's hand"),
    "plays_this_turn": ("Cartes jouées ce tour", "Cards played this turn"),
    "rafaam": ("Rafaam n/9", "Rafaam n/9"),
    "atlas": ("Atlas de Godfrey", "Godfrey's Atlas"),
    "troublemaker": ("Projectiles", "Shots"),
    "tolvir": ("Serviteurs à (1) invocables", "Summonable 1-cost minions"),
    "spells_cast": ("Sorts lancés n/5", "Spells cast n/5"),
    "dragons": ("Dragons joués n/8", "Dragons played n/8"),
    "minions_died": ("Serviteurs morts n/20", "Minions died n/20"),
    "my_corpses": ("Mes cadavres", "My corpses"),
    "opp_corpses": ("Ses cadavres", "Their corpses"),
}

# Icône + explication de chaque add-on, pour les fiches du launcher. Le titre
# seul ne suffisait pas — retour utilisateur : « j'ai "entrées" mais je sais
# pas ce que c'est ». Une ligne qui dit à quoi ça sert et quand ça apparaît.
ADDON_INFO: dict[str, tuple[str, str, str]] = {
    "remaining":       ("🂠", "Ce qu'il reste dans ton deck, et l'alerte fatigue.",
                              "What's left in your deck, plus the fatigue warning."),
    "opp_remaining":   ("🂠", "Pareil chez lui : c'est SA fatigue qui se rapproche.",
                              "Same for them: their fatigue is what's coming."),
    "imbue":           ("✧", "Niveau d'Empreint de ton pouvoir héroïque.",
                              "Imbue level of your hero power."),
    "my_damage":       ("⚔", "Dégâts que tu peux encore infliger ce tour.",
                              "Damage you can still deal this turn."),
    "opp_damage":      ("⚔", "Dégâts qu'il peut t'infliger à son tour.",
                              "Damage they can deal on their turn."),
    "lethal":          ("🎯", "Ce qu'il te manque pour tuer — ou LÉTAL.",
                              "How far from killing — or LETHAL."),
    "fatigue":         ("☠", "Dégâts de fatigue déjà encaissés.",
                              "Fatigue damage already taken."),
    "my_hand":         ("✋", "Taille de ta main. Alerte à 9 : à 10 tu brûles.",
                              "Your hand size. Warning at 9: at 10 you burn."),
    "opp_hand":        ("✋", "Taille de sa main, et combien de cartes créées.",
                              "Their hand size, and how many were created."),
    "plays_this_turn": ("▶", "Cartes jouées ce tour — pour les combos du Voleur.",
                              "Cards played this turn — for Rogue combos."),
    "rafaam":          ("⏳", "Rafaam distincts posés. À 9, le héros tombe.",
                              "Distinct Rafaams played. At 9, the hero dies."),
    "atlas":           ("📜", "Cartes en attente dans l'Atlas de Godfrey.",
                              "Cards queued in Godfrey's Atlas."),
    "troublemaker":    ("⇶", "Projectiles de la Fauteuse, dès qu'un camp est Voleur.",
                              "Troublemaker shots, as soon as a side is a Rogue."),
    "tolvir":          ("↻", "Serviteurs à (1) invocables, dès qu'un camp est Chasseur.",
                              "Summonable 1-cost minions, as soon as a side is a Hunter."),
    "spells_cast":     ("✦", "Sorts lancés, pour le cycle qui s'arme à 5.",
                              "Spells cast, for the cycle that arms at 5."),
    "dragons":         ("🐉", "Dragons joués — Zarimi offre un tour à 8.",
                              "Dragons played — Zarimi grants a turn at 8."),
    "minions_died":    ("🕯", "Serviteurs morts, condition d'Aessina.",
                              "Minions died, Aessina's condition."),
    "my_corpses":      ("☠", "Tes cadavres, si tu joues Chevalier de la mort.",
                              "Your corpses, if you play Death Knight."),
    "opp_corpses":     ("☠", "Ses cadavres, face à un Chevalier de la mort.",
                              "Their corpses, against a Death Knight."),
}


def addon_icon(key: str) -> str:
    info = ADDON_INFO.get(key)
    return info[0] if info else "•"


def addon_desc(key: str, lang: str = "fr") -> str:
    info = ADDON_INFO.get(key)
    return info[2 if lang == "en" else 1] if info else ""


CLASS_NAMES: dict[str, tuple[str, str]] = {
    "DEATHKNIGHT": ("Chevalier de la mort", "Death Knight"),
    "DEMONHUNTER": ("Chasseur de démons", "Demon Hunter"),
    "DRUID": ("Druide", "Druid"),
    "HUNTER": ("Chasseur", "Hunter"),
    "MAGE": ("Mage", "Mage"),
    "PALADIN": ("Paladin", "Paladin"),
    "PRIEST": ("Prêtre", "Priest"),
    "ROGUE": ("Voleur", "Rogue"),
    "SHAMAN": ("Chaman", "Shaman"),
    "WARLOCK": ("Démoniste", "Warlock"),
    "WARRIOR": ("Guerrier", "Warrior"),
}


def pick(pair: tuple[str, str], lang: str = "fr") -> str:
    return pair[1 if lang == "en" else 0]


def counter_label(key: str, lang: str = "fr") -> str:
    return pick(COUNTER_LABELS.get(key, (key, key)), lang)


def class_name(key: str | None, lang: str = "fr") -> str:
    if not key:
        return ""
    return pick(CLASS_NAMES.get(key, (key, key)), lang)


def t(key: str, lang: str = "fr", **kw) -> str:
    """Texte traduit. Clé inconnue → la clé elle-même (repérable en UI)."""
    pair = _STRINGS.get(key)
    if pair is None:
        return key
    return pair[1 if lang == "en" else 0].format(**kw)


def plural(n: int, lang: str = "fr") -> str:
    """Marque du pluriel à insérer dans ``{s}`` (l'anglais gère le sien)."""
    return "s" if n > 1 and lang == "fr" else ""
