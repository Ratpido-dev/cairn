"""Traductions des textes produits par Python (compteurs, pools).

Les libellés purement visuels du QML sont traduits côté QML (``tr()`` dans
``Launcher.qml``) ; ici on ne traite que ce que le moteur fabrique lui-même.

Une entrée = une clé, un triplet ``(français, anglais, chinois)``. **L'ordre des
colonnes est celui de ``LANGS``** : ajouter une langue = l'ajouter à ``LANGS``
et compléter chaque tuple à la même place. Les valeurs peuvent contenir des
champs de formatage nommés.

Terminologie chinoise : noms officiels de Hearthstone (zhCN) — « 高弗雷 » et
non « 戈弗雷 », « 艾森娜 », « 托维尔 », « 潜行者 » pour Rogue, « 灌注 » pour
Imbue, « 亡语 » pour Deathrattle. Vérifié sur ``cards.zhCN.json``.
"""

from __future__ import annotations

# Colonnes de CHAQUE table ci-dessous, dans cet ordre. 0 = langue par défaut.
LANGS = ("fr", "en", "zh")


def lang_index(lang: str) -> int:
    """Colonne de ``lang`` ; toute langue inconnue retombe sur le français."""
    try:
        return LANGS.index(lang)
    except ValueError:
        return 0


def locale_of(lang: str) -> str:
    """Code de locale HearthstoneJSON correspondant à une langue d'interface.

    Sert aux noms de cartes, aux textes de règles et aux rendus d'images.
    """
    return {"en": "enUS", "zh": "zhCN"}.get(lang, "frFR")


_STRINGS: dict[str, tuple[str, str, str]] = {
    "unknownDeck": ("deck non reconnu", "unidentified deck", "未知套牌"),
    # compteurs
    "in_deck": ("{n} au deck", "{n} in deck", "牌库中 {n} 张"),
    "fatigue": ("FATIGUE", "FATIGUE", "疲劳"),
    "fatigue_dmg": ("fatigue {n}", "fatigue {n}", "疲劳 {n}"),
    "imbue": ("empreint {n}", "imbue {n}", "灌注 {n}"),
    "the_coin": ("La pièce", "The Coin", "幸运币"),
    "my_hand": ("main : {n}", "hand: {n}", "手牌：{n}"),
    "opp_hand": ("adv : {n}", "opp: {n}", "对手：{n}"),
    "opp_hand_created": ("adv : {n} ({c} créée{s})", "opp: {n} ({c} created)",
                         "对手：{n}（衍生 {c} 张）"),
    "plays_this_turn": ("{n} ce tour", "{n} this turn", "本回合 {n}"),
    "lethal_now": ("LÉTAL ! ({dmg}/{hp})", "LETHAL! ({dmg}/{hp})",
                   "斩杀！({dmg}/{hp})"),
    "lethal_left": ("létal : reste {n}", "lethal: {n} left", "距斩杀：{n}"),
    "rafaam": ("Rafaam {n}/9", "Rafaam {n}/9", "拉法姆 {n}/9"),
    "rafaam_lethal": ("Rafaam {n}/9 — LÉTAL", "Rafaam {n}/9 — LETHAL",
                      "拉法姆 {n}/9 — 斩杀"),
    "atlas": ("atlas {n}", "atlas {n}", "图册 {n}"),
    "shots": ("projectiles {n}", "shots {n}", "弹幕 {n}"),
    "replay": ("serviteurs à (1) : {n}", "1-cost minions: {n}", "1 费随从：{n}"),
    "spells": ("sorts {n}/5", "spells {n}/5", "法术 {n}/5"),
    "dragons": ("dragons {n}/8", "dragons {n}/8", "龙牌 {n}/8"),
    "died": ("morts {n}/20", "died {n}/20", "阵亡 {n}/20"),
    "corpses": ("{n} cadavres", "{n} corpses", "{n} 具尸体"),
    "side_me": ("moi ", "me ", "我方 "),
    "side_opp": ("adv ", "opp ", "敌方 "),
    # familles à cocher (quels membres ont déjà été posés)
    "family_rafaam": ("RAFAAM", "RAFAAMS", "拉法姆"),
    "family_windrunner": ("SŒURS COURSEVENT", "WINDRUNNER SISTERS", "风行者姐妹"),
    # pools de résurrection
    "pool_dr_max": ("Râle d’agonie à ({n}) ou moins",
                    "Deathrattle costing ({n}) or less",
                    "费用 ({n}) 或更低的亡语"),
    "pool_dr_min": ("Râle d’agonie à ({n}) ou plus",
                    "Deathrattle costing ({n}) or more",
                    "费用 ({n}) 或更高的亡语"),
    "pool_dr_played": ("Râle d’agonie joué cette partie",
                       "Deathrattle played this game",
                       "本局已使用的亡语"),
}


LEAGUE_NAMES: dict[str, tuple[str, str, str]] = {
    "BRONZE": ("Bronze", "Bronze", "青铜"),
    "SILVER": ("Argent", "Silver", "白银"),
    "GOLD": ("Or", "Gold", "黄金"),
    "PLATINUM": ("Platine", "Platinum", "铂金"),
    "DIAMOND": ("Diamant", "Diamond", "钻石"),
    "LEGEND": ("Légende", "Legend", "传说"),
}


def league_name(key: str | None, lang: str = "fr") -> str:
    if not key:
        return ""
    return pick(LEAGUE_NAMES.get(key, (key, key, key)), lang)


# Libellé COURT de chaque ligne du panneau à deux colonnes. Le camp est donné
# par la colonne, donc plus de préfixe « moi »/« adv » à écrire.
ROW_LABELS: dict[str, tuple[str, str, str]] = {
    "deck": ("au deck", "in deck", "牌库"),
    "corpses": ("cadavres", "corpses", "尸体"),
    "imbue": ("empreint", "imbue", "灌注"),
    "rafaam": ("Rafaam", "Rafaam", "拉法姆"),
    "atlas": ("atlas", "atlas", "图册"),
    "shots": ("projectiles", "shots", "弹幕"),
    "replay": ("serviteurs à (1)", "1-cost minions", "1 费随从"),
    "spells": ("sorts", "spells", "法术"),
    "dragons": ("dragons", "dragons", "龙牌"),
    "died": ("morts", "died", "阵亡"),
    "lethal": ("létal", "lethal", "斩杀"),
    "hand": ("main", "hand", "手牌"),
    "fatigue": ("fatigue", "fatigue", "疲劳"),
    "plays": ("ce tour", "this turn", "本回合"),
}


def row_label(pair: str, lang: str = "fr") -> str:
    """Libellé de ligne, ou la clé elle-même si elle n'est pas traduite."""
    paire = ROW_LABELS.get(pair)
    return pick(paire, lang) if paire else pair


# Libellés des add-ons, tels que listés dans le launcher
COUNTER_LABELS: dict[str, tuple[str, str, str]] = {
    "remaining": ("Cartes restantes", "Cards left", "剩余卡牌"),
    "opp_remaining": ("Cartes restantes chez lui", "Cards left in their deck",
                      "对手剩余卡牌"),
    "imbue": ("Empreint", "Imbue", "灌注"),
    "my_damage": ("Mes dégâts possibles", "My possible damage", "我的潜在伤害"),
    "opp_damage": ("Ses dégâts possibles", "Their possible damage", "对手潜在伤害"),
    "lethal": ("Distance au létal", "Distance to lethal", "距斩杀还差"),
    "fatigue": ("Dégâts de fatigue", "Fatigue damage", "疲劳伤害"),
    "my_hand": ("Ma main", "My hand", "我的手牌"),
    "opp_hand": ("Main adverse", "Opponent's hand", "对手手牌"),
    "plays_this_turn": ("Cartes jouées ce tour", "Cards played this turn",
                        "本回合已出牌"),
    "rafaam": ("Rafaam n/9", "Rafaam n/9", "拉法姆 n/9"),
    "atlas": ("Atlas de Godfrey", "Godfrey's Atlas", "高弗雷图册"),
    "troublemaker": ("Projectiles", "Shots", "弹幕"),
    "tolvir": ("Serviteurs à (1) invocables", "Summonable 1-cost minions",
               "可召唤的 1 费随从"),
    "spells_cast": ("Sorts lancés n/5", "Spells cast n/5", "已施放法术 n/5"),
    "dragons": ("Dragons joués n/8", "Dragons played n/8", "已使用龙牌 n/8"),
    "minions_died": ("Serviteurs morts n/20", "Minions died n/20", "随从阵亡 n/20"),
    "my_corpses": ("Mes cadavres", "My corpses", "我的尸体"),
    "opp_corpses": ("Ses cadavres", "Their corpses", "对手尸体"),
}

# Icône + explication de chaque add-on, pour les fiches du launcher. Le titre
# seul ne suffisait pas — retour utilisateur : « j'ai "entrées" mais je sais
# pas ce que c'est ». Une ligne qui dit à quoi ça sert et quand ça apparaît.
# Colonnes : icône, puis UNE COLONNE PAR LANGUE de ``LANGS`` (décalage +1).
ADDON_INFO: dict[str, tuple[str, ...]] = {
    "remaining":       ("🂠", "Ce qu'il reste dans ton deck, et l'alerte fatigue.",
                              "What's left in your deck, plus the fatigue warning.",
                              "你的牌库还剩什么，以及疲劳预警。"),
    "opp_remaining":   ("🂠", "Pareil chez lui : c'est SA fatigue qui se rapproche.",
                              "Same for them: their fatigue is what's coming.",
                              "对手同理：逼近的是他的疲劳。"),
    "imbue":           ("✧", "Niveau d'Empreint de ton pouvoir héroïque.",
                              "Imbue level of your hero power.",
                              "你英雄技能的灌注等级。"),
    "my_damage":       ("⚔", "Dégâts que tu peux encore infliger ce tour.",
                              "Damage you can still deal this turn.",
                              "本回合你还能造成的伤害。"),
    "opp_damage":      ("⚔", "Dégâts qu'il peut t'infliger à son tour.",
                              "Damage they can deal on their turn.",
                              "对手在他的回合能对你造成的伤害。"),
    "lethal":          ("🎯", "Ce qu'il te manque pour tuer — ou LÉTAL.",
                              "How far from killing — or LETHAL.",
                              "离击杀还差多少 —— 或者已经斩杀。"),
    "fatigue":         ("☠", "Dégâts de fatigue déjà encaissés.",
                              "Fatigue damage already taken.",
                              "已经承受的疲劳伤害。"),
    "my_hand":         ("✋", "Taille de ta main. Alerte à 9 : à 10 tu brûles.",
                              "Your hand size. Warning at 9: at 10 you burn.",
                              "你的手牌数。9 张预警：满 10 张就开始烧牌。"),
    "opp_hand":        ("✋", "Taille de sa main, et combien de cartes créées.",
                              "Their hand size, and how many were created.",
                              "对手的手牌数，以及其中多少张是衍生牌。"),
    "plays_this_turn": ("▶", "Cartes jouées ce tour — pour les combos du Voleur.",
                              "Cards played this turn — for Rogue combos.",
                              "本回合已出牌数 —— 用于潜行者的连击。"),
    "rafaam":          ("⏳", "Rafaam distincts posés. À 9, le héros tombe.",
                              "Distinct Rafaams played. At 9, the hero dies.",
                              "已登场的不同拉法姆。到 9 个，英雄就倒下。"),
    "atlas":           ("📜", "Cartes en attente dans l'Atlas de Godfrey.",
                              "Cards queued in Godfrey's Atlas.",
                              "高弗雷图册中待发的牌。"),
    "troublemaker":    ("⇶", "Projectiles de la Fauteuse, dès qu'un camp est Voleur.",
                              "Troublemaker shots, as soon as a side is a Rogue.",
                              "只要有任一方是潜行者，就显示捣蛋鬼的飞弹数。"),
    "tolvir":          ("↻", "Serviteurs à (1) invocables, dès qu'un camp est Chasseur.",
                              "Summonable 1-cost minions, as soon as a side is a Hunter.",
                              "只要有任一方是猎人，就显示可召唤的 1 费随从。"),
    "spells_cast":     ("✦", "Sorts lancés, pour le cycle qui s'arme à 5.",
                              "Spells cast, for the cycle that arms at 5.",
                              "已施放的法术数 —— 到 5 触发循环。"),
    "dragons":         ("🐉", "Dragons joués — Zarimi offre un tour à 8.",
                              "Dragons played — Zarimi grants a turn at 8.",
                              "已使用的龙牌数 —— 到 8 张扎里米给一个额外回合。"),
    "minions_died":    ("🕯", "Serviteurs morts, condition d'Aessina.",
                              "Minions died, Aessina's condition.",
                              "随从阵亡数，艾森娜的触发条件。"),
    "my_corpses":      ("☠", "Tes cadavres, si tu joues Chevalier de la mort.",
                              "Your corpses, if you play Death Knight.",
                              "你玩死亡骑士时的尸体数。"),
    "opp_corpses":     ("☠", "Ses cadavres, face à un Chevalier de la mort.",
                              "Their corpses, against a Death Knight.",
                              "面对死亡骑士时，对手的尸体数。"),
}


def addon_icon(key: str) -> str:
    info = ADDON_INFO.get(key)
    return info[0] if info else "•"


def addon_desc(key: str, lang: str = "fr") -> str:
    """Explication d'un add-on : colonne 0 = icône, donc langue = index + 1."""
    info = ADDON_INFO.get(key)
    return info[lang_index(lang) + 1] if info else ""


CLASS_NAMES: dict[str, tuple[str, str, str]] = {
    "DEATHKNIGHT": ("Chevalier de la mort", "Death Knight", "死亡骑士"),
    "DEMONHUNTER": ("Chasseur de démons", "Demon Hunter", "恶魔猎手"),
    "DRUID": ("Druide", "Druid", "德鲁伊"),
    "HUNTER": ("Chasseur", "Hunter", "猎人"),
    "MAGE": ("Mage", "Mage", "法师"),
    "PALADIN": ("Paladin", "Paladin", "圣骑士"),
    "PRIEST": ("Prêtre", "Priest", "牧师"),
    "ROGUE": ("Voleur", "Rogue", "潜行者"),
    "SHAMAN": ("Chaman", "Shaman", "萨满祭司"),
    "WARLOCK": ("Démoniste", "Warlock", "术士"),
    "WARRIOR": ("Guerrier", "Warrior", "战士"),
}


def pick(pair: tuple[str, ...], lang: str = "fr") -> str:
    """Colonne ``lang`` d'un tuple de traduction."""
    return pair[lang_index(lang)]


def counter_label(key: str, lang: str = "fr") -> str:
    return pick(COUNTER_LABELS.get(key, (key, key, key)), lang)


def class_name(key: str | None, lang: str = "fr") -> str:
    if not key:
        return ""
    return pick(CLASS_NAMES.get(key, (key, key, key)), lang)


def t(key: str, lang: str = "fr", **kw) -> str:
    """Texte traduit. Clé inconnue → la clé elle-même (repérable en UI)."""
    pair = _STRINGS.get(key)
    if pair is None:
        return key
    return pick(pair, lang).format(**kw)


def plural(n: int, lang: str = "fr") -> str:
    """Marque du pluriel à insérer dans ``{s}``.

    Seul le français en a une, et seulement au-delà de un : l'anglais et le
    chinois écrivent la marque directement dans leur propre gabarit.
    """
    return "s" if n > 1 and lang == "fr" else ""
