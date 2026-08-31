"""Compteurs contextuels du bandeau (F4) — le « petit compteur en haut ».

Architecture déclarative : un compteur = une fonction ``(ctx) -> Counter | None``.
``None`` = pas affiché (c'est ça, le côté contextuel). Pour en ajouter un,
écrire la fonction et l'inscrire dans ``ALL_COUNTERS``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .atlas import ATLAS_ENCHANTMENT, GODFREY
from .cards_db import CardsDb
from .deck_view import TOLVIR, TOLVIR_COST, DeckView, plays_costing
from .game_state import DECK, Death, Entity, Game, HAND, PLAY, Play, SECRET
from .i18n import plural, t


def _int_tag(ent: Entity, tag: str, default: int = 0) -> int:
    raw = ent.tags.get(tag)
    return int(raw) if raw is not None and raw.lstrip("-").isdigit() else default


@dataclass
class Counter:
    icon: str
    text: str
    alert: bool = False  # accentué en braise (situation à surveiller)
    kind: str = ""  # "" | "good" (vert, mon camp) | "bad" (rouge, adversaire)
    # Où l'afficher : "panel" dans le panneau de compteurs (qui s'agrandit au
    # fur et à mesure), "attack" en pastille flottante isolée. Les points
    # d'attaque se lisent d'un coup d'œil pendant qu'on calcule un échange :
    # les noyer dans une liste avec Rafaam et les cadavres les rend illisibles.
    group: str = "panel"  # "panel" | "attack"
    # Illustration de la carte qui justifie le compteur : le panneau l'affiche
    # à la place de l'émoji quand elle existe. Une vignette de Rafaam se
    # reconnaît plus vite qu'une ligne de texte — et surtout elle ne s'écrit
    # pas, ce qui laisse la place au seul chiffre qui compte.
    card_id: str = ""
    # Ce qui s'affiche à côté de la vignette. Vide = on affiche ``text``.
    # ``text`` reste la phrase complète, reversée dans l'infobulle : sans elle
    # une vignette seule serait une devinette.
    short: str = ""
    # Mise en colonnes « moi | adversaire » : ``pair`` désigne la LIGNE (les
    # deux camps d'un même compteur la partagent), ``side`` la colonne. Remplis
    # centralement par ``compute_counters`` d'après la table ``_PAIRS`` — pas
    # par chaque compteur, qui n'a pas à connaître la mise en page.
    pair: str = ""
    side: str = ""  # "me" | "opp"


@dataclass
class CounterContext:
    game: Game
    view: DeckView
    db: CardsDb
    lang: str = "fr"
    local: int | None = None
    local_class: str | None = None
    opponent: int | None = None
    opponent_class: str | None = None
    _seen: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.local = self.game.local_player_id()
        self.local_class = self._class_of(self.local)
        self.opponent = next(
            (p for p in self.game.player_names if p != self.local), None
        ) if self.local is not None else None
        self.opponent_class = self._class_of(self.opponent)

    def _class_of(self, player_id: int | None) -> str | None:
        if player_id is None:
            return None
        hero = self.game.hero_card_id(player_id)
        card = self.db.by_card_id.get(hero or "")
        return card.get("cardClass") if card else None

    def player(self, of_local: bool) -> int | None:
        return self.local if of_local else self.opponent

    def seen_cards(self, of_local: bool) -> set[str]:
        """Cartes RÉVÉLÉES d'un camp : tout ce dont on connaît l'id (jouées, en
        jeu, au cimetière…) plus, pour moi, la liste complète de mon deck.

        C'est la base des compteurs contextuels : un compteur ne s'affiche que
        si la carte qui le justifie a vraiment été vue (le classement par
        classe ne suffit pas — un Démoniste sur deux ne joue pas Rafaam)."""
        if of_local in self._seen:
            return self._seen[of_local]
        ids = set()
        if self.local is not None:
            for e in self.game.entities.values():
                if (
                    e.card_id
                    and e.controller is not None
                    and (e.controller == self.local) == of_local
                ):
                    ids.add(e.card_id)
        if of_local:
            ids |= {r.card_id for r in self.view.rows if r.card_id}
        self._seen[of_local] = ids
        return ids

    def has_seen(self, of_local: bool, prefixes: tuple[str, ...]) -> bool:
        return any(
            cid.startswith(p) for cid in self.seen_cards(of_local) for p in prefixes
        )

    def class_of(self, of_local: bool) -> str | None:
        return self.local_class if of_local else self.opponent_class

    def relevant(
        self, of_local: bool, prefixes: tuple[str, ...], klass: str | None = None
    ) -> bool:
        """Le compteur a-t-il un sens pour ce camp ?

        Voir la carte suffit, mais arrive trop tard pour celles qui se
        préparent des tours à l'avance : la Confrontation des Tol'vir rejoue ce
        qu'on a joué à (1) depuis le début, la Fauteuse de troubles compte les
        cartes à (2). Quand le compteur ne sert QU'À une classe, la classe
        adverse suffit donc à l'armer — c'est le seul moyen d'anticiper au lieu
        de constater.
        """
        return self.has_seen(of_local, prefixes) or (
            klass is not None and self.class_of(of_local) == klass
        )


def _hero_card(ctx: CounterContext, of_local: bool) -> str:
    """Portrait du héros d'un camp — la vignette des compteurs sans carte.

    « 28 au deck » et « adv 13 au deck » ne désignent aucune carte précise ;
    sans image ils se ressemblent trop une fois le texte parti. Le portrait dit
    d'un coup d'œil de quel camp on parle, mieux que la couleur seule.
    """
    pid = ctx.player(of_local)
    return ctx.game.hero_card_id(pid) or "" if pid is not None else ""


# ---- les compteurs ---------------------------------------------------------

def counter_remaining(ctx: CounterContext) -> Counter | None:
    """Cartes restantes / fatigue imminente — toujours affiché."""
    n = ctx.view.remaining_total
    if not ctx.view.rows:
        return None
    if n == 0:
        return Counter(icon="🂠", card_id=_hero_card(ctx, True),
                       text=t("fatigue", ctx.lang),
                       short=t("fatigue", ctx.lang), alert=True)
    return Counter(icon="🂠", card_id=_hero_card(ctx, True),
                   text=t("in_deck", ctx.lang, n=n), short=str(n), alert=n <= 4)


def counter_opp_remaining(ctx: CounterContext) -> Counter | None:
    """Cartes restantes dans le deck ADVERSE — sa fatigue à lui.

    On ne connaît pas ses cartes, mais on connaît leur NOMBRE : les entités de
    sa zone DECK sont créées dès le début de partie, cachées mais comptables.
    C'est ce qui dit quand la fatigue tombe en face, et ça décide des parties
    longues — Firestone l'affiche en permanence.
    """
    if ctx.opponent is None:
        return None
    n = sum(
        1 for e in ctx.game.entities.values()
        if e.zone == DECK and e.controller == ctx.opponent
    )
    if n == 0:
        # pas de deck adverse = partie pas encore commencée ; ne rien dire tant
        # qu'aucune carte n'y a jamais été vue, sinon on annonce FATIGUE au
        # mulligan de chaque partie
        if not ctx.game.turns:
            return None
        return Counter(icon="🂠", card_id=_hero_card(ctx, False),
                       text=t("side_opp", ctx.lang) + t("fatigue", ctx.lang),
                       short=t("fatigue", ctx.lang), alert=True, kind="bad")
    return Counter(icon="🂠", card_id=_hero_card(ctx, False),
                   text=t("side_opp", ctx.lang) + t("in_deck", ctx.lang, n=n),
                   short=str(n), alert=n <= 4, kind="bad")


def counter_imbue(ctx: CounterContext) -> list[Counter]:
    """Niveau d'« Empreint » du pouvoir héroïque, de chaque côté qui en a un.

    Le mot-clé Imbue remplace le pouvoir héroïque par une version qui se
    renforce à chaque nouvel Empreint — chez le Prêtre, la carte ajoutée coûte
    1 cristal de moins au premier niveau, 2 au deuxième, etc. Le niveau n'est
    écrit nulle part à l'écran : il vit dans ``TAG_SCRIPT_DATA_NUM_1`` de
    l'entité du pouvoir héroïque (vu jusqu'à 8 sur les parties archivées).

    Les pouvoirs concernés sont repérés par le drapeau ``imbue`` de la base de
    cartes, dérivé de ``referencedTags`` au téléchargement — pas par une liste
    d'identifiants qui périmerait à la prochaine extension.
    """
    if ctx.local is None:
        return []
    out = []
    for of_local in (True, False):
        pid = ctx.player(of_local)
        niveau = 0
        for e in ctx.game.entities.values():
            if (
                e.zone == PLAY
                and e.controller == pid
                and e.tags.get("CARDTYPE") == "HERO_POWER"
            ):
                # Le NIVEAU lui-même sert de détecteur : les pouvoirs de base
                # n'ont pas ce tag, seuls les améliorés le portent. Le drapeau
                # `imbue` de la base de cartes ne couvrait que six pouvoirs
                # marqués IMBUE — « Bénédiction du Vol de bronze » (Druide) et
                # « Force de Minh » (Chaman) n'y étaient pas, et l'adversaire
                # restait sans compteur dès qu'il n'était pas Prêtre.
                niveau = max(niveau, _int_tag(e, "TAG_SCRIPT_DATA_NUM_1"))
        if niveau <= 0:
            continue
        out.append(
            Counter(
                icon="✧",
                card_id=_hero_card(ctx, of_local),
                text=t("side_me" if of_local else "side_opp", ctx.lang)
                     + t("imbue", ctx.lang, n=niveau),
                short=str(niveau),
                kind="good" if of_local else "bad",
            )
        )
    return out


def counter_my_hand(ctx: CounterContext) -> Counter | None:
    """Taille de MA main. Elle est sous les yeux, mais la compter en plein
    calcul de tour coûte une seconde d'attention — et la colonne « moi » de la
    ligne « main » restait vide sans elle."""
    if ctx.local is None:
        return None
    n = sum(
        1 for e in ctx.game.entities.values()
        if e.zone == HAND and e.controller == ctx.local
    )
    if n == 0:
        return None
    return Counter(icon="✋", card_id=_hero_card(ctx, True),
                   text=t("my_hand", ctx.lang, n=n), short=str(n),
                   alert=n >= 9)  # à 10 on brûle ce qu'on pioche


def counter_opp_hand(ctx: CounterContext) -> Counter | None:
    """Taille de la main adverse + cartes créées (pas piochées du deck)."""
    if ctx.local is None:
        return None
    in_hand = [
        e for e in ctx.game.entities.values()
        if e.zone == HAND and e.controller is not None and e.controller != ctx.local
    ]
    if not in_hand:
        return None
    created = sum(1 for e in in_hand if e.creator_entity_id is not None)
    if created:
        text = t("opp_hand_created", ctx.lang, n=len(in_hand), c=created,
                 s=plural(created, ctx.lang))
    else:
        text = t("opp_hand", ctx.lang, n=len(in_hand))
    return Counter(icon="✋", card_id=_hero_card(ctx, False), text=text,
                   short=f"{len(in_hand)}" + (f" ({created})" if created else ""))


def counter_plays_this_turn(ctx: CounterContext) -> Counter | None:
    """Cartes jouées ce tour — contextuel Voleur (combo)."""
    if ctx.local_class != "ROGUE" or ctx.local is None:
        return None
    turn = ctx.game.turns
    n = sum(
        1 for e in ctx.game.events
        if isinstance(e, Play) and e.player_id == ctx.local and e.turn == turn
    )
    return Counter(icon="▶", card_id=_hero_card(ctx, True),
                   text=t("plays_this_turn", ctx.lang, n=n), short=str(n))


def _board_minions(ctx: CounterContext, of_local: bool) -> list[Entity]:
    return [
        e for e in ctx.game.entities.values()
        if e.zone == PLAY
        and e.tags.get("CARDTYPE") == "MINION"
        and e.controller is not None
        and ctx.local is not None
        and ((e.controller == ctx.local) == of_local)
    ]


def counter_my_damage(ctx: CounterContext) -> Counter | None:
    """⚔ vert : dégâts que JE peux encore infliger ce tour (serviteurs
    capables d'attaquer + héros/arme, attaques restantes comprises)."""
    if ctx.local is None or _hero(ctx, of_local=True) is None:
        return None
    return Counter(icon="⚔", text=str(_side_damage(ctx, of_local=True)),
                   kind="good", group="attack")


def counter_opp_damage(ctx: CounterContext) -> Counter | None:
    """⚔ rouge : dégâts que l'ADVERSAIRE peut infliger — seulement ce qui
    peut réellement attaquer (gelé, dormant, incapable d'attaquer exclus)."""
    if ctx.local is None or _hero(ctx, of_local=False) is None:
        return None
    return Counter(icon="⚔", text=str(_side_damage(ctx, of_local=False)),
                   kind="bad", group="attack")


def _plays(ctx: CounterContext, of_local: bool) -> list[Play]:
    pid = ctx.player(of_local)
    return [
        ev for ev in ctx.game.events
        if isinstance(ev, Play) and ev.player_id == pid and ev.card_id
    ]


def _seen_card(ctx: CounterContext, of_local: bool, prefixes: tuple[str, ...]) -> str:
    """Id EXACT de la carte déclencheuse vue chez ce camp, pour sa vignette.

    Les compteurs s'arment sur des préfixes (« TIME_005 » couvre les dix
    Rafaam) ; l'illustration, elle, demande un identifiant précis. On prend le
    plus court des identifiants vus, qui est la carte de base plutôt qu'un de
    ses jetons.
    """
    vus = [
        cid for cid in ctx.seen_cards(of_local)
        for p in prefixes if cid.startswith(p)
    ]
    return min(vus, key=lambda c: (len(c), c)) if vus else ""


# ---- compteurs contextuels : n'apparaissent que si LA carte est vue ---------

RAFAAM_PREFIX = "TIME_005"


def counter_rafaam(ctx: CounterContext) -> list[Counter]:
    """Rafaam, le voleur de temps : son deck de 40 contient 10 Rafaam, et sa
    condition létale est d'avoir joué les 9 AUTRES. On compte donc les Rafaam
    distincts déjà posés — « 9/9 » = le héros d'en face peut être détruit.

    Compté des DEUX côtés : « Briseuse d'âme Azalina » copie le début de
    partie adverse, donc un Prêtre Azalina hérite du deck de 40 Rafaam et de
    sa condition de victoire. En miroir les deux compteurs s'affichent, avec
    leur camp en préfixe (seuls, ils gardent le libellé court)."""
    out = []
    for of_local in (True, False):
        if not ctx.has_seen(of_local, (RAFAAM_PREFIX,)):
            continue
        played = {
            ev.card_id for ev in _plays(ctx, of_local)
            if ev.card_id.startswith(RAFAAM_PREFIX) and ev.card_id != RAFAAM_PREFIX
        }
        n = min(len(played), 9)
        out.append(
            Counter(
                icon="⏳",
                card_id=_seen_card(ctx, of_local, (RAFAAM_PREFIX,)),
                text=t("rafaam_lethal" if n >= 9 else "rafaam", ctx.lang, n=n),
                short=f"{n}/9",
                alert=n >= 8,
                kind="good" if of_local else "bad",
            )
        )
    if len(out) == 2:
        for counter, of_local in zip(out, (True, False)):
            counter.text = t("side_me" if of_local else "side_opp", ctx.lang) + counter.text
    return out


def counter_atlas(ctx: CounterContext) -> list[Counter]:
    """Cartes en attente dans l'Atlas de Godfrey, de chaque côté qui en a un.

    Le détail (quoi, dans quel ordre) vit dans les panneaux ; ici on ne donne
    que la taille de la file, muette tant qu'elle est vide."""
    out = []
    for of_local, cards in ((True, ctx.view.my_atlas), (False, ctx.view.opp_atlas)):
        if not cards:
            continue
        out.append(
            Counter(
                icon="📜",
                card_id=GODFREY,
                text=t("side_me" if of_local else "side_opp", ctx.lang)
                     + t("atlas", ctx.lang, n=len(cards)),
                short=str(len(cards)),
                kind="good" if of_local else "bad",
            )
        )
    return out


# Cycle « si vous avez lancé 5 sorts ou plus pendant cette partie »
FIVE_SPELLS = ("YOG_521", "YOG_528", "YOG_518", "YOG_411")


def counter_spells_cast(ctx: CounterContext) -> Counter | None:
    """Sorts lancés / 5 — pour le cycle qui s'active à 5 sorts."""
    for of_local in (True, False):
        if not ctx.has_seen(of_local, FIVE_SPELLS):
            continue
        n = sum(
            1 for ev in _plays(ctx, of_local)
            if (ctx.db.by_card_id.get(ev.card_id) or {}).get("type") == "SPELL"
        )
        return Counter(
            icon="✦",
            card_id=_seen_card(ctx, of_local, FIVE_SPELLS),
            text=t("side_me" if of_local else "side_opp", ctx.lang)
                 + t("spells", ctx.lang, n=min(n, 5)),
            short=f"{min(n, 5)}/5",
            alert=n >= 5,
            kind="good" if of_local else "bad",
        )
    return None


# « Fauteuse de troubles du Lotus » : Cri de guerre, 1 dégât à un serviteur
# adverse au hasard, tiré autant de fois qu'on a joué de cartes coûtant
# INITIALEMENT (2) tant qu'elle attendait en main ou dans le deck, + 1.
TROUBLEMAKER = ("JAIL_470",)
TROUBLEMAKER_COST = 2


def _troublemaker_tag(ctx: CounterContext, of_local: bool) -> int | None:
    """Nombre de projectiles annoncé par le jeu, pour une copie en attente.

    Le jeu tient le compte dans ``TAG_SCRIPT_DATA_NUM_1`` sur la carte
    elle-même. Utilisable pour MES copies (je les vois en main et dans mon
    deck) ; côté adverse la valeur n'arrive qu'au moment où il la joue —
    trop tard — puis retombe à 1, d'où le calcul de secours ci-dessous.
    """
    pid = ctx.player(of_local)
    waiting = [
        e for e in ctx.game.entities.values()
        if e.card_id in TROUBLEMAKER and e.controller == pid and e.zone in (HAND, DECK)
    ]
    if not waiting:
        return None
    # tag absent = compteur encore à son minimum (la carte tire 1 fois)
    return max(max(_int_tag(e, "TAG_SCRIPT_DATA_NUM_1"), 1) for e in waiting)


def _troublemaker_since(ctx: CounterContext, of_local: bool) -> int:
    """Tour à partir duquel les cartes à (2) comptent pour ce camp.

    La carte ne compte que « tant qu'elle est dans votre main ou votre deck » :
    une copie VOLÉE ou DÉCOUVERTE en cours de partie ne récupère pas ce qui a
    été joué avant son arrivée. C'était la cause des chiffres gonflés côté
    Azalina — un Prêtre qui vole une Fauteuse au tour 8 se voyait créditer des
    cartes à (2) jouées au tour 2.

    Copie encore invisible (le cas normal en face) : on suppose qu'elle est là
    depuis le début, ce qui est vrai dès qu'elle vient de son propre deck.
    """
    pid = ctx.player(of_local)
    copies = [
        e for e in ctx.game.entities.values()
        if e.card_id in TROUBLEMAKER and e.controller == pid
    ]
    if not copies:
        return 0
    arrivees = []
    for e in copies:
        if e.entity_id in ctx.game._initial_deck_ids or e.hand_turn is None:
            return 0  # présente depuis le mulligan : toute la partie compte
        arrivees.append(e.hand_turn)
    return min(arrivees)


def counter_troublemaker(ctx: CounterContext) -> list[Counter]:
    """Projectiles que tirerait une Fauteuse de troubles du Lotus, par camp.

    Le décompte déduit — 1 + cartes jouées à (2) — a été validé sur la partie
    du 02/08 12:07 : le jeu a bien tiré 6 projectiles pour l'adversaire (6
    cartes à (2) jouées avant, moins celles d'après) et affichait 9 sur ma
    copie en main. Il vaut pour une copie présente depuis le début ; une copie
    volée ou créée en cours de route compte à partir de son arrivée, et c'est
    là que le tag du jeu (mes copies) reprend la main.

    Deux corrections du 14/08/2026 : le décompte démarre à l'ARRIVÉE de la
    copie quand elle a été volée ou découverte (cf. ``_troublemaker_since``),
    et face à un Voleur le compteur s'affiche AVANT qu'il pose sa Fauteuse —
    sans quoi on apprend le nombre de projectiles au moment où on les prend.
    """
    out = []
    for of_local in (True, False):
        if not ctx.relevant(of_local, TROUBLEMAKER, "ROGUE"):
            continue
        played = sum(
            c.count for c in plays_costing(
                ctx.game, ctx.db, ctx.player(of_local), TROUBLEMAKER_COST,
                since=_troublemaker_since(ctx, of_local),
            )
        )
        exact = _troublemaker_tag(ctx, of_local) if of_local else None
        n = exact if exact is not None else played + 1
        out.append(
            Counter(
                icon="⇶",
                # vignette de la carte même quand on ne l'a pas encore vue :
                # c'est elle qui explique le chiffre
                card_id=_seen_card(ctx, of_local, TROUBLEMAKER) or TROUBLEMAKER[0],
                text=t("side_me" if of_local else "side_opp", ctx.lang)
                     + t("shots", ctx.lang, n=n),
                short=str(n),
                alert=not of_local and n >= 5,
                kind="good" if of_local else "bad",
            )
        )
    return out


def counter_tolvir(ctx: CounterContext) -> list[Counter]:
    """Cartes à (1) déjà jouées — ce que rejouerait une Confrontation des Tol'vir.

    Le détail (lesquelles) vit dans les panneaux ; ici, le nombre. Armé par la
    CLASSE et pas seulement par la carte vue : contre un Chasseur, savoir à
    l'avance qu'il rejouera dix cartes à (1) change la façon de jouer les
    siennes — l'apprendre au moment où il la pose ne sert plus à rien.
    """
    out = []
    for of_local, cards in ((True, ctx.view.my_replay), (False, ctx.view.opp_replay)):
        if not ctx.relevant(of_local, (TOLVIR,), "HUNTER"):
            continue
        n = sum(c.count for c in cards)
        out.append(
            Counter(
                icon="↻",
                card_id=_seen_card(ctx, of_local, (TOLVIR,)) or TOLVIR,
                text=t("side_me" if of_local else "side_opp", ctx.lang)
                     + t("replay", ctx.lang, n=n),
                short=str(n),
                alert=not of_local and n >= 6,
                kind="good" if of_local else "bad",
            )
        )
    return out


ZARIMI = ("TOY_385",)


def counter_dragons(ctx: CounterContext) -> Counter | None:
    """Dragons joués / 8 — Zarimi offre un tour supplémentaire à 8."""
    for of_local in (True, False):
        if not ctx.has_seen(of_local, ZARIMI):
            continue
        n = sum(1 for ev in _plays(ctx, of_local) if ctx.db.is_dragon(ev.card_id))
        return Counter(
            icon="🐉",
            card_id=_seen_card(ctx, of_local, ZARIMI),
            text=t("side_me" if of_local else "side_opp", ctx.lang)
                 + t("dragons", ctx.lang, n=min(n, 8)),
            short=f"{min(n, 8)}/8",
            alert=n >= 8,
            kind="good" if of_local else "bad",
        )
    return None


AESSINA = ("EDR_430",)


def counter_minions_died(ctx: CounterContext) -> Counter | None:
    """Serviteurs alliés morts / 20 — condition d'Aessina."""
    for of_local in (True, False):
        if not ctx.has_seen(of_local, AESSINA):
            continue
        pid = ctx.player(of_local)
        n = sum(
            1 for ev in ctx.game.events
            if isinstance(ev, Death) and ev.player_id == pid
        )
        return Counter(
            icon="🕯",
            card_id=_seen_card(ctx, of_local, AESSINA),
            text=t("side_me" if of_local else "side_opp", ctx.lang)
                 + t("died", ctx.lang, n=min(n, 20)),
            short=f"{min(n, 20)}/20",
            alert=n >= 20,
            kind="good" if of_local else "bad",
        )
    return None


def _corpses(ctx: CounterContext, of_local: bool) -> int | None:
    pid = ctx.player(of_local)
    ent_id = ctx.game.player_entity.get(pid) if pid is not None else None
    ent = ctx.game.entities.get(ent_id) if ent_id else None
    if ent is None or "CORPSES" not in ent.tags:
        return None
    return _int_tag(ent, "CORPSES")


def counter_my_corpses(ctx: CounterContext) -> Counter | None:
    """Cadavres disponibles — Chevalier de la mort seulement."""
    if ctx.local_class != "DEATHKNIGHT":
        return None
    n = _corpses(ctx, of_local=True)
    return None if n is None else Counter(
        icon="☠", card_id=_hero_card(ctx, True),
        text=t("corpses", ctx.lang, n=n), short=str(n), kind="good")


def counter_opp_corpses(ctx: CounterContext) -> Counter | None:
    """Cadavres de l'adversaire CDM — de quoi anticiper ses gros paiements."""
    if ctx.opponent_class != "DEATHKNIGHT":
        return None
    n = _corpses(ctx, of_local=False)
    return None if n is None else Counter(
        icon="☠", card_id=_hero_card(ctx, False),
        text=t("side_opp", ctx.lang) + t("corpses", ctx.lang, n=n),
        short=str(n), kind="bad")


def counter_fatigue_damage(ctx: CounterContext) -> Counter | None:
    """Dégâts de fatigue subis (tag FATIGUE) — dès la première morsure."""
    if ctx.local is None:
        return None
    ent_id = ctx.game.player_entity.get(ctx.local)
    ent = ctx.game.entities.get(ent_id) if ent_id else None
    raw = ent.tags.get("FATIGUE") if ent else None
    if raw is None or not raw.isdigit() or int(raw) == 0:
        return None
    return Counter(icon="☠", text=t("fatigue_dmg", ctx.lang, n=raw),
                   short=str(raw), alert=True)


def _hero(ctx: CounterContext, of_local: bool) -> Entity | None:
    for e in ctx.game.entities.values():
        if (
            e.zone == PLAY
            and e.tags.get("CARDTYPE") == "HERO"
            and e.controller is not None
            and ctx.local is not None
            and ((e.controller == ctx.local) == of_local)
        ):
            return e
    return None


def _current_player(ctx: CounterContext) -> int | None:
    """PlayerID dont c'est le tour (suivi par le moteur, cf. Game)."""
    if ctx.game.current_player is not None:
        return ctx.game.current_player
    for pid, ent_id in ctx.game.player_entity.items():
        ent = ctx.game.entities.get(ent_id)
        if ent is not None and _int_tag(ent, "CURRENT_PLAYER"):
            return pid
    return None


def _attacks_left(e: Entity, ready_now: bool) -> int:
    """Attaques restantes d'une unité — 0 si elle ne peut pas attaquer.

    ``ready_now=False`` (camp dont ce n'est pas le tour) : ses compteurs
    seront remis à zéro à son tour, seuls gelé/dormant/incapable comptent —
    un serviteur posé ce tour-ci attaquera bien au tour suivant.

    ``ready_now=True`` : mal d'invocation. ``NUM_TURNS_IN_PLAY`` s'incrémente
    à CHAQUE changement de tour (les deux camps) et n'est posé qu'au tick
    suivant la pose — donc, pendant le tour de son contrôleur, un serviteur
    arrivé ce tour-ci vaut 0 et un serviteur réveillé vaut ≥ 2. Vérifié sur
    les logs réels. (``EXHAUSTED`` serait tentant mais reste à 1 pendant tout
    le tour adverse après une attaque : faux positifs au changement de tour.)
    Charge et Ruée passent outre — Ruée ne vise pas le héros, mais ces
    dégâts restent infligeables, c'est le compteur de létal qui tranche.
    """
    if _int_tag(e, "CANT_ATTACK") or _int_tag(e, "FROZEN") or _int_tag(e, "DORMANT"):
        return 0
    max_attacks = 2 if _int_tag(e, "WINDFURY") else 1
    attacks_done = _int_tag(e, "NUM_ATTACKS_THIS_TURN")
    if not ready_now:
        return max_attacks
    if (
        e.tags.get("CARDTYPE") == "MINION"
        and _int_tag(e, "NUM_TURNS_IN_PLAY") == 0
        and not (_int_tag(e, "CHARGE") or _int_tag(e, "RUSH"))
    ):
        return 0
    return max(0, max_attacks - attacks_done)


def _weapon_atk(ctx: CounterContext, of_local: bool) -> int:
    for e in ctx.game.entities.values():
        if (
            e.zone == PLAY
            and e.tags.get("CARDTYPE") == "WEAPON"
            and e.controller is not None
            and ctx.local is not None
            and ((e.controller == ctx.local) == of_local)
        ):
            return _int_tag(e, "ATK")
    return 0


def _side_damage(ctx: CounterContext, of_local: bool) -> int:
    """Dégâts qu'un camp peut infliger avec ce qui PEUT attaquer ce tour :
    serviteurs (× attaques restantes) + héros (arme comprise)."""
    if ctx.local is None:
        return 0
    side_pid = ctx.local if of_local else next(
        (p for p in ctx.game.player_names if p != ctx.local), None
    )
    cur = _current_player(ctx)
    ready_now = (cur == side_pid) if cur is not None and side_pid is not None else of_local

    total = sum(
        _int_tag(e, "ATK") * _attacks_left(e, ready_now)
        for e in _board_minions(ctx, of_local=of_local)
    )
    hero = _hero(ctx, of_local=of_local)
    if hero is not None:
        atk = max(_int_tag(hero, "ATK"), _weapon_atk(ctx, of_local))
        if atk > 0:
            total += atk * _attacks_left(hero, ready_now)
    return total


def _lethal_for(ctx: CounterContext, of_local: bool) -> Counter | None:
    """Distance au létal d'un camp : PV de sa cible moins ses dégâts prêts."""
    cible = _hero(ctx, of_local=not of_local)
    if cible is None:
        return None
    hp = (
        _int_tag(cible, "HEALTH", 30)
        - _int_tag(cible, "DAMAGE")
        + _int_tag(cible, "ARMOR")
    )
    ready = _side_damage(ctx, of_local=of_local)
    if ready <= 0:
        return None
    kind = "good" if of_local else "bad"
    if ready >= hp:
        return Counter(icon="🎯", card_id=_hero_card(ctx, not of_local),
                       text=t("side_me" if of_local else "side_opp", ctx.lang)
                            + t("lethal_now", ctx.lang, dmg=ready, hp=hp),
                       short=f"{ready}/{hp}", alert=True, kind=kind)
    return Counter(icon="🎯", card_id=_hero_card(ctx, not of_local),
                   text=t("side_me" if of_local else "side_opp", ctx.lang)
                        + t("lethal_left", ctx.lang, n=hp - ready),
                   short=str(hp - ready), kind=kind)


def counter_lethal(ctx: CounterContext) -> list[Counter]:
    """Distance au létal DES DEUX CÔTÉS.

    Savoir de combien on est loin de tuer ne vaut que si l'on sait aussi de
    combien on est loin de mourir : c'est la même décision, vue des deux bouts.
    """
    if ctx.local is None:
        return []
    return [c for c in (_lethal_for(ctx, True), _lethal_for(ctx, False)) if c]


@dataclass
class CounterDef:
    """Un add-on du bandeau — visible dans le launcher, activable.

    ``fn`` rend ``None`` (rien à montrer), un ``Counter``, ou une liste quand
    la même carte peut concerner les deux camps.

    ``triggers`` : préfixes d'id de carte qui ARMENT le compteur. Tant qu'aucune
    n'a été vue en jeu, le compteur reste muet — c'est ce qui évite d'afficher
    « Rafaam 0/9 » contre les Démonistes qui jouent un tout autre deck.
    ``side`` : chez qui chercher le déclencheur (« me », « opp », « any »).
    ``klass`` : classe qui arme le compteur À ELLE SEULE, pour les cartes dont
    la valeur se construit longtemps avant qu'on les voie (Confrontation des
    Tol'vir, Fauteuse de troubles) — là, attendre de voir la carte revient à
    n'afficher le compteur qu'une fois qu'il ne sert plus.
    """

    key: str
    label: str
    fn: object
    triggers: tuple[str, ...] = ()
    side: str = "any"
    klass: str | None = None

    def armed(self, ctx: CounterContext) -> bool:
        if not self.triggers and self.klass is None:
            return True
        sides = {"me": (True,), "opp": (False,), "any": (True, False)}[self.side]
        return any(
            ctx.relevant(of_local, self.triggers, self.klass) for of_local in sides
        )


COUNTER_DEFS = [
    CounterDef("remaining", "Cartes restantes / fatigue", counter_remaining),
    CounterDef("opp_remaining", "🂠 Cartes restantes chez l'adversaire",
               counter_opp_remaining),
    CounterDef("my_damage", "⚔ Mes dégâts possibles ce tour (vert)", counter_my_damage),
    CounterDef("opp_damage", "⚔ Dégâts adverses possibles (rouge)", counter_opp_damage),
    CounterDef("lethal", "Distance au létal", counter_lethal),
    CounterDef("fatigue", "Dégâts de fatigue", counter_fatigue_damage),
    CounterDef("imbue", "✧ Empreint — niveau du pouvoir héroïque",
               counter_imbue),
    CounterDef("my_hand", "Ma main", counter_my_hand),
    CounterDef("opp_hand", "Main adverse (+ cartes créées)", counter_opp_hand),
    CounterDef("plays_this_turn", "Cartes jouées ce tour (Voleur)", counter_plays_this_turn),
    # --- contextuels : armés par la présence d'une carte précise -------------
    CounterDef(
        "rafaam", "⏳ Rafaam n/9 (des deux côtés)", counter_rafaam,
        triggers=(RAFAAM_PREFIX,), side="any",
    ),
    CounterDef(
        "atlas", "📜 Atlas de Godfrey (file d'attente)", counter_atlas,
        triggers=(GODFREY, ATLAS_ENCHANTMENT), side="any",
    ),
    CounterDef(
        "troublemaker", "⇶ Projectiles (Fauteuse de troubles du Lotus)",
        counter_troublemaker, triggers=TROUBLEMAKER, side="any", klass="ROGUE",
    ),
    CounterDef(
        "tolvir", "↻ Cartes à (1) rejouables (Confrontation des Tol'vir)",
        counter_tolvir, triggers=(TOLVIR,), side="any", klass="HUNTER",
    ),
    CounterDef(
        "spells_cast", "✦ Sorts lancés n/5 (cycle Yogg)", counter_spells_cast,
        triggers=FIVE_SPELLS, side="any",
    ),
    CounterDef(
        "dragons", "🐉 Dragons joués n/8 (Zarimi)", counter_dragons,
        triggers=ZARIMI, side="any",
    ),
    CounterDef(
        "minions_died", "🕯 Serviteurs morts n/20 (Aessina)", counter_minions_died,
        triggers=AESSINA, side="any",
    ),
    CounterDef("my_corpses", "☠ Mes cadavres (Chevalier de la mort)", counter_my_corpses),
    CounterDef("opp_corpses", "☠ Cadavres adverses (vs CDM)", counter_opp_corpses),
]


# Ligne partagée par les deux camps d'un même compteur, et camp par défaut
# quand la couleur ne le dit pas (``kind`` vide). La clé est celle du
# CounterDef ; la ligne porte le libellé court affiché à gauche.
_PAIRS: dict[str, tuple[str, str]] = {
    #  clé du compteur   ligne        camp par défaut
    "remaining":        ("deck",      "me"),
    "opp_remaining":    ("deck",      "opp"),
    "my_corpses":       ("corpses",   "me"),
    "opp_corpses":      ("corpses",   "opp"),
    "imbue":            ("imbue",     ""),
    "rafaam":           ("rafaam",    ""),
    "atlas":            ("atlas",     ""),
    "troublemaker":     ("shots",     ""),
    "tolvir":           ("replay",    ""),
    "spells_cast":      ("spells",    ""),
    "dragons":          ("dragons",   ""),
    "minions_died":     ("died",      ""),
    "lethal":           ("lethal",    "opp"),
    "my_hand":          ("hand",      "me"),
    "opp_hand":         ("hand",      "opp"),
    "fatigue":          ("fatigue",   "me"),
    "plays_this_turn":  ("plays",     "me"),
}


def compute_counters(
    game: Game, view: DeckView, db: CardsDb, enabled: set[str] | None = None,
    lang: str = "fr",
) -> list[Counter]:
    ctx = CounterContext(game=game, view=view, db=db, lang=lang)
    out = []
    for cdef in COUNTER_DEFS:
        if enabled is not None and cdef.key not in enabled:
            continue
        if not cdef.armed(ctx):
            continue
        # un compteur rend un Counter, None, ou PLUSIEURS (cas des miroirs :
        # Rafaam ou l'atlas des deux côtés à la fois — cf. Azalina)
        produced = cdef.fn(ctx)
        if produced is None:
            continue
        pair, defaut = _PAIRS.get(cdef.key, (cdef.key, ""))
        for counter in (produced if isinstance(produced, list) else [produced]):
            counter.pair = pair
            # la couleur dit déjà le camp quand elle est posée ; sinon on
            # retombe sur le défaut de la table
            counter.side = ("me" if counter.kind == "good"
                            else "opp" if counter.kind == "bad" else defaut)
            out.append(counter)
    return out
