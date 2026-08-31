"""Moteur d'état : flux d'événements Power.log → parties reconstruites.

Produit, par partie, les événements de haut niveau du tracker :
pioches, cartes jouées, et surtout les **entrées de deck** (cartes ajoutées
en cours de partie — bombes, fléaux, Rafaam…), cœur du cahier des charges.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .power_log import (
    BlockEnd,
    BlockStart,
    CreateGame,
    EntityDef,
    Event,
    GameInfo,
    PlayerName,
    ShuffleDeck,
    TagChange,
)

# Zones (tag ZONE)
DECK, HAND, PLAY, GRAVEYARD, SECRET, SETASIDE = (
    "DECK", "HAND", "PLAY", "GRAVEYARD", "SECRET", "SETASIDE",
)


@dataclass
class Entity:
    entity_id: int
    card_id: str | None = None
    name: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
    # Tour où la carte est entrée dans la main de son contrôleur, et si elle y
    # est arrivée par la main de départ. C'est LA donnée que Firestone affiche
    # sous chaque carte adverse : savoir qu'un adversaire garde une carte depuis
    # le tour 1 (une pièce non jouée, par exemple) change les décisions.
    # Suivi par le moteur plutôt que lu dans NUM_TURNS_IN_HAND : le tag n'est
    # posé qu'au tick suivant et vaut 0 pendant tout le tour d'arrivée.
    hand_turn: int | None = None
    hand_from_mulligan: bool = False
    # Vrai dès qu'on a connu l'identité de cette carte ALORS qu'elle était dans
    # le deck (Découvre qui révèle, Azalina, fouille…). On garde la marque même
    # après qu'elle a quitté le deck : sans elle, la carte disparaissait de la
    # section « connues dans son deck » au moment précis où l'adversaire la
    # joue — c'est-à-dire à l'instant où l'information devient vérifiable.
    revealed_in_deck: bool = False

    @property
    def zone(self) -> str | None:
        return self.tags.get("ZONE")

    @property
    def controller(self) -> int | None:
        raw = self.tags.get("CONTROLLER")
        return int(raw) if raw is not None and raw.isdigit() else None

    @property
    def creator_entity_id(self) -> int | None:
        """Entité qui a engendré celle-ci, via CREATOR ou DISPLAYED_CREATOR.

        HS pose ``CREATOR`` sur les cartes engendrées par un effet en jeu, mais
        seulement ``DISPLAYED_CREATOR`` sur celles dont l'origine doit être
        MONTRÉE au joueur — typiquement les 20 copies d'Azalina ajoutées au deck
        pendant le mulligan. ``CREATOR`` n'y arrive qu'au moment où la carte est
        révélée (pioche), bien trop tard pour l'événement d'entrée dans le deck.
        Sans ce repli, toutes les entrées de deck d'un Thief Priest sont
        orphelines et la section « fond de deck » reste vide.
        """
        for tag in ("CREATOR", "DISPLAYED_CREATOR"):
            raw = self.tags.get(tag)
            if raw is not None and raw.isdigit() and raw != "0":
                return int(raw)
        return None


@dataclass
class Draw:
    """DECK → HAND (pendant le mulligan : main de départ)."""
    player_id: int | None
    entity_id: int
    card_id: str | None
    during_mulligan: bool
    turn: int = 0


@dataclass
class Play:
    """HAND → PLAY/SECRET/GRAVEYARD (serviteur, secret, sort)."""
    player_id: int | None
    entity_id: int
    card_id: str | None
    turn: int = 0


@dataclass
class DeckEntry:
    """Carte ENTRÉE dans le deck en cours de partie — la demande centrale.

    ``created=True`` : n'existait pas au mulligan (bombe, fléau…).
    ``created=False`` : carte connue renvoyée/mélangée dans le deck.
    ``during_mulligan=True`` : carte reposée pendant le mulligan.
    """
    player_id: int | None
    entity_id: int
    card_id: str | None
    creator_card_id: str | None
    created: bool
    during_mulligan: bool = False


@dataclass
class Death:
    """Serviteur mort (PLAY → GRAVEYARD) — alimente les pools de résurrection."""
    player_id: int | None
    entity_id: int
    card_id: str | None
    turn: int = 0


@dataclass
class DeckLeave:
    """Carte sortie du deck SANS être piochée (dredge, burn, mill, transform)."""
    player_id: int | None
    entity_id: int
    card_id: str | None
    to_zone: str


def round_number(turn: int) -> int:
    """Manche telle que le joueur la compte, à partir du tag TURN de HS.

    HS compte UN tour par camp : TURN vaut 1 et 2 pendant la première manche,
    3 et 4 pendant la deuxième… Afficher le tag brut donnait « tour 10 » quand
    le joueur avait 5 cristaux — le nombre de mana est le repère de tout le
    monde, c'est donc lui qui fait foi.

    Le brut reste utilisé partout ailleurs (comparaisons d'événements,
    historique) : seuls les affichages convertissent.
    """
    return (turn + 1) // 2


def _elapsed(start: str, end: str) -> float:
    """Secondes entre deux horodatages du journal, minuit compris."""
    delta = _ts_seconds(end) - _ts_seconds(start)
    return delta + 86400 if delta < 0 else delta


def _ts_seconds(ts: str) -> float:
    """« 00:08:05.1088643 » → secondes depuis minuit."""
    try:
        h, m, rest = ts.split(":", 2)
        return int(h) * 3600 + int(m) * 60 + float(rest)
    except (ValueError, AttributeError):
        return 0.0


@dataclass
class Game:
    ts: str | None = None  # horodatage du CREATE_GAME (HH:MM:SS.fffffff)
    last_ts: str | None = None  # dernier horodatage vu → durée de la partie
    game_type: str | None = None
    format_type: str | None = None
    player_names: dict[int, str] = field(default_factory=dict)
    player_entity: dict[int, int] = field(default_factory=dict)  # PlayerID → entity_id
    player_accounts: dict[int, str] = field(default_factory=dict)  # PlayerID → compte
    results: dict[str, str] = field(default_factory=dict)  # nom joueur → WON/LOST/TIED
    # Nom du joueur qui a CONCÉDÉ, "" sinon. Hearthstone le journalise
    # explicitement (``PLAYSTATE value=CONCEDED``) : inutile de le deviner à
    # partir d'une durée ou d'un nombre de tours, ce qui confondrait une
    # concession de départ avec une partie perdue vite.
    conceded_by: str = ""
    conceded_turn: int = 0   # tour HS où la concession a eu lieu
    entities: dict[int, Entity] = field(default_factory=dict)
    events: list = field(default_factory=list)
    turns: int = 0
    complete: bool = False
    # PlayerID dont c'est le tour. Suivi ici plutôt que relu des tags : au
    # changement de tour HS émet CURRENT_PLAYER=0 puis =1 sur DEUX lignes, et
    # un poll qui tombe entre les deux ne verrait plus personne de courant.
    current_player: int | None = None
    # chrono : début du tour courant, et temps cumulé par joueur. Mesurés sur
    # les horodatages du journal, donc justes même en rejeu d'archive.
    turn_started_ts: str | None = None
    time_by_player: dict[int, float] = field(default_factory=dict)
    # entités présentes dans le deck à la création (avant mulligan)
    _initial_deck_ids: set[int] = field(default_factory=set)
    _mulligan_done: bool = False

    # ---- helpers d'analyse (post-parse) ------------------------------------

    def accounts(self) -> set[str]:
        return set(self.player_accounts.values())

    def is_spectated(self, own_account: str | None) -> bool:
        """Vrai si cette partie est celle de quelqu'un d'autre, qu'on regarde.

        En spectateur, HS écrit le journal EXACTEMENT comme d'habitude : un
        joueur nommé ``UNKNOWN HUMAN PLAYER``, l'autre par son battletag, et
        les pioches des DEUX camps révélées. Aucune heuristique de contenu ne
        peut donc distinguer les deux cas — c'est ce qui faisait que Cairn
        adoptait le deck d'un inconnu et l'enregistrait dans l'historique.

        Le compte du joueur est le seul discriminant : s'il n'est ni l'un ni
        l'autre, on n'est pas dans la partie. Tant qu'on ne connaît pas son
        propre compte on répond False — ne rien casser prime sur filtrer.
        """
        if not own_account or not self.player_accounts:
            return False
        return own_account not in self.player_accounts.values()

    def local_player_id(self, own_account: str | None = None) -> int | None:
        """Le joueur local = celui dont on voit les cartes piochées.

        Les pioches adverses restent ``card_id=None`` dans GameState ; un seul
        camp a des cartes révélées à la pioche.

        Sauf en spectateur, où les deux camps sont révélés et où ce décompte
        départage sur un écart de hasard. D'où le compte en priorité quand on
        le connaît : c'est une identité, pas une statistique.
        """
        if own_account:
            for pid, account in self.player_accounts.items():
                if account == own_account:
                    return pid
        revealed: dict[int, int] = {}
        for ev in self.events:
            if isinstance(ev, Draw) and ev.player_id is not None and ev.card_id:
                revealed[ev.player_id] = revealed.get(ev.player_id, 0) + 1
        if not revealed:
            return None
        return max(revealed, key=lambda p: revealed[p])

    def duration_seconds(self) -> int | None:
        """Durée de la partie, mesurée dans le journal (donc juste même si le
        tracker a démarré en retard ou rejoue une session archivée)."""
        if not self.ts or not self.last_ts:
            return None
        return int(_elapsed(self.ts, self.last_ts))

    def close_turn(self, ts: str | None) -> None:
        """Solde le tour qui vient de finir au crédit de celui qui le jouait."""
        if ts:
            if self.turn_started_ts is not None and self.current_player is not None:
                self.time_by_player[self.current_player] = (
                    self.time_by_player.get(self.current_player, 0.0)
                    + _elapsed(self.turn_started_ts, ts)
                )
            self.turn_started_ts = ts

    def turn_seconds(self) -> int | None:
        """Temps écoulé dans le tour en cours — la corde, en somme."""
        if not self.turn_started_ts or not self.last_ts:
            return None
        return int(_elapsed(self.turn_started_ts, self.last_ts))

    def player_seconds(self, player_id: int | None) -> int:
        """Temps de réflexion cumulé d'un joueur, tour courant compris."""
        if player_id is None:
            return 0
        total = self.time_by_player.get(player_id, 0.0)
        if player_id == self.current_player:
            total += self.turn_seconds() or 0
        return int(total)

    def hero_card_id(self, player_id: int) -> str | None:
        for ent in self.entities.values():
            if (
                ent.card_id
                and ent.card_id.startswith("HERO_")
                and ent.tags.get("CARDTYPE") == "HERO"
                and ent.controller == player_id
            ):
                return ent.card_id
        return None


class GameStateEngine:
    """Consomme le flux d'événements et reconstruit la liste des parties."""

    def __init__(self) -> None:
        self.games: list[Game] = []
        self._game: Game | None = None
        # PlayerID (1/2) ↔ entity_id du joueur, rempli par les EntityDef "player"
        self._player_entity: dict[int, int] = {}
        # profondeur de blocs : le deck INITIAL est créé hors de tout bloc ;
        # tout FULL_ENTITY vers le deck DANS un bloc est un ajout (même en
        # début de partie — cf. Azalina, trigger START_OF_GAME avant la fin
        # du mulligan dans les logs)
        self._block_depth = 0

    # ---- entrée principale -------------------------------------------------

    def feed(self, events) -> None:
        for event in events:
            self._apply(event)

    # ---- interne -----------------------------------------------------------

    def _apply(self, event: Event) -> None:
        if isinstance(event, CreateGame):
            self._game = Game(ts=event.ts, turn_started_ts=event.ts)
            self._player_entity = {}
            self._block_depth = 0
            self.games.append(self._game)
            return
        if self._game is None:
            return
        game = self._game

        if isinstance(event, GameInfo):
            if event.key == "GameType":
                game.game_type = event.value
            else:
                game.format_type = event.value
        elif isinstance(event, PlayerName):
            game.player_names[event.player_id] = event.name
        elif isinstance(event, EntityDef):
            self._apply_entity_def(game, event)
        elif isinstance(event, TagChange):
            self._apply_tag_change(game, event)
        elif isinstance(event, BlockStart):
            self._block_depth += 1
        elif isinstance(event, BlockEnd):
            self._block_depth = max(0, self._block_depth - 1)
        elif isinstance(event, ShuffleDeck):
            pass

    def _apply_entity_def(self, game: Game, ed: EntityDef) -> None:
        if ed.kind == "player" and ed.player_id is not None and ed.entity_id is not None:
            self._player_entity[ed.player_id] = ed.entity_id
            game.player_entity[ed.player_id] = ed.entity_id
            if ed.account:
                game.player_accounts[ed.player_id] = ed.account

        if ed.entity_id is None:
            return
        ent = game.entities.setdefault(ed.entity_id, Entity(entity_id=ed.entity_id))
        old_zone = ent.zone
        if ed.card_id:
            ent.card_id = ed.card_id
        ent.tags.update(ed.tags)
        self._note_deck_reveal(ent)

        new_zone = ed.tags.get("ZONE")
        if ed.kind == "full" and new_zone:
            self._stamp_hand(game, ent, old_zone, new_zone)
        if ed.kind == "full":
            if new_zone == DECK and not game._mulligan_done and self._block_depth == 0:
                game._initial_deck_ids.add(ed.entity_id)
            elif new_zone == DECK:
                self._record_deck_entry(
                    game, ent, created=True, during_mulligan=not game._mulligan_done
                )
        elif ed.kind == "show" and new_zone and new_zone != old_zone:
            # SHOW_ENTITY peut aussi déplacer (révélation + changement de zone)
            self._zone_transition(game, ent, old_zone, new_zone)

    def _apply_tag_change(self, game: Game, tc: TagChange) -> None:
        if tc.ts:
            game.last_ts = tc.ts
        ent = self._resolve(game, tc.ref)

        # fin de partie / résultat — portés par des refs "nom de joueur"
        if tc.tag == "PLAYSTATE" and tc.value in ("WON", "LOST", "TIED") and tc.ref.name:
            game.results[tc.ref.name] = tc.value
            return
        if tc.tag == "PLAYSTATE" and tc.value == "CONCEDED" and tc.ref.name:
            # Première concession seulement : HS repose parfois le tag.
            if not game.conceded_by:
                game.conceded_by = tc.ref.name
                game.conceded_turn = game.turns
            return
        if tc.tag == "STATE" and tc.value == "COMPLETE":
            game.complete = True
            return
        if tc.tag == "TURN" and tc.value.isdigit():
            if int(tc.value) > game.turns:
                game.close_turn(tc.ts)
            game.turns = max(game.turns, int(tc.value))
        if tc.tag == "MULLIGAN_STATE" and tc.value == "DONE":
            game._mulligan_done = True

        if ent is None:
            return
        if tc.tag == "ZONE":
            old_zone = ent.zone
            ent.tags["ZONE"] = tc.value
            self._note_deck_reveal(ent)
            if tc.value != old_zone:
                self._zone_transition(game, ent, old_zone, tc.value)
        else:
            ent.tags[tc.tag] = tc.value
            if tc.tag == "CURRENT_PLAYER" and tc.value == "1":
                for pid, eid in game.player_entity.items():
                    if eid == ent.entity_id:
                        game.current_player = pid
                        break

    def _stamp_hand(self, game: Game, ent: Entity, old: str | None, new: str) -> None:
        """Date l'arrivée en main, et l'efface au départ.

        Appelé aussi bien sur un changement de zone que sur une entité créée
        DIRECTEMENT en main (Découverte, carte offerte) : celle-là ne passe par
        aucune transition, et resterait sans date.
        """
        if new == HAND and old != HAND:
            ent.hand_turn = game.turns
            ent.hand_from_mulligan = not game._mulligan_done
        elif new != HAND and old == HAND:
            ent.hand_turn = None
            ent.hand_from_mulligan = False

    @staticmethod
    def _note_deck_reveal(ent: Entity) -> None:
        """Marque une carte dont on connaît l'identité pendant qu'elle est au deck.

        Une entité du deck adverse n'a pas de ``card_id`` tant que rien ne l'a
        révélée : la seule présence du champ, dans la zone DECK, EST la preuve
        de la révélation. Pas besoin de reconnaître chaque effet un par un.
        """
        if ent.card_id and ent.zone == DECK:
            ent.revealed_in_deck = True

    def _zone_transition(self, game: Game, ent: Entity, old: str | None, new: str) -> None:
        self._stamp_hand(game, ent, old, new)

        if old == DECK and new == HAND:
            game.events.append(
                Draw(
                    player_id=ent.controller,
                    entity_id=ent.entity_id,
                    card_id=ent.card_id,
                    during_mulligan=not game._mulligan_done,
                    turn=game.turns,
                )
            )
        elif old == DECK and new != HAND:
            # dredge, burn, mill, transformation : la carte quitte le deck
            game.events.append(
                DeckLeave(
                    player_id=ent.controller,
                    entity_id=ent.entity_id,
                    card_id=ent.card_id,
                    to_zone=new,
                )
            )
        elif old == PLAY and new == GRAVEYARD and ent.tags.get("CARDTYPE") == "MINION":
            game.events.append(
                Death(
                    player_id=ent.controller,
                    entity_id=ent.entity_id,
                    card_id=ent.card_id,
                    turn=game.turns,
                )
            )
        elif old == HAND and new in (PLAY, SECRET, GRAVEYARD):
            game.events.append(
                Play(
                    player_id=ent.controller,
                    entity_id=ent.entity_id,
                    card_id=ent.card_id,
                    turn=game.turns,
                )
            )
        elif new == DECK:
            created = ent.entity_id not in game._initial_deck_ids
            self._record_deck_entry(
                game, ent, created=created, during_mulligan=not game._mulligan_done
            )

    def _record_deck_entry(
        self, game: Game, ent: Entity, created: bool, during_mulligan: bool = False
    ) -> None:
        creator_id = ent.creator_entity_id
        creator = game.entities.get(creator_id) if creator_id else None
        game.events.append(
            DeckEntry(
                player_id=ent.controller,
                entity_id=ent.entity_id,
                card_id=ent.card_id,
                creator_card_id=creator.card_id if creator else None,
                created=created,
                during_mulligan=during_mulligan,
            )
        )

    def _resolve(self, game: Game, ref) -> Entity | None:
        if ref.entity_id is not None:
            ent = game.entities.setdefault(ref.entity_id, Entity(entity_id=ref.entity_id))
            if ref.card_id and not ent.card_id:
                ent.card_id = ref.card_id
            if ref.name and not ent.name:
                ent.name = ref.name
            return ent
        if ref.is_game:
            return None  # les tags du GameEntity qu'on suit passent par tag/value dédiés
        if ref.name:
            # nom de joueur → entité joueur correspondante
            for pid, name in game.player_names.items():
                if name == ref.name and pid in self._player_entity:
                    return game.entities.get(self._player_entity[pid])
            # HS nomme l'adversaire « UNKNOWN HUMAN PLAYER » dans les PlayerName
            # mais utilise son VRAI battletag dans les TAG_CHANGE : sans ce
            # rattrapage, tous ses tags (dont CURRENT_PLAYER) étaient PERDUS.
            # Un seul joueur peut rester non apparié → on le lie définitivement.
            if "#" in ref.name:
                unbound = [
                    pid for pid in self._player_entity
                    if game.player_names.get(pid) in (None, "UNKNOWN HUMAN PLAYER")
                ]
                if len(unbound) == 1:
                    pid = unbound[0]
                    game.player_names[pid] = ref.name  # battletag réel, dès maintenant
                    return game.entities.get(self._player_entity[pid])
            return None
        return None


def replay_file(path) -> list[Game]:
    """Rejoue un Power.log complet et rend les parties reconstruites."""
    from .power_log import parse_file

    engine = GameStateEngine()
    engine.feed(parse_file(path))
    return engine.games


def learn_own_account(games: Iterable[Game], minimum: int = 3) -> str | None:
    """Déduit le compte du joueur : celui présent dans le plus de parties.

    On est dans TOUTES ses parties et dans aucune de celles qu'on regarde —
    donc le compte le plus fréquent est le sien, sans rien demander à
    l'utilisateur ni lire de fichier de compte (Hearthstone n'écrit son
    identifiant nulle part ailleurs que dans les lignes ``Player`` du
    Power.log : vérifié, il n'apparaît dans aucun autre journal).

    Deux garde-fous, parce qu'une déduction fausse est pire que pas de
    déduction : il faut au moins ``minimum`` parties, et le meneur doit être
    strictement devant. En dessous, on répond None et tout continue comme
    avant — l'apprentissage réessaiera à la session suivante.
    """
    seen: dict[str, int] = {}
    total = 0
    for game in games:
        comptes = game.accounts()
        if not comptes:
            continue
        total += 1
        for compte in comptes:
            seen[compte] = seen.get(compte, 0) + 1
    if total < minimum or not seen:
        return None
    classement = sorted(seen.items(), key=lambda kv: -kv[1])
    if len(classement) > 1 and classement[0][1] == classement[1][1]:
        return None  # égalité : on ne tranche pas à pile ou face
    return classement[0][0]
