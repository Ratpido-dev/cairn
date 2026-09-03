"""Historique local des parties (F6) — SQLite, données dans ~/.local/share/cairn/.

Dédoublonnage par ``(session, game_index)`` : le bridge relit toute la session
au démarrage (from_start=True), chaque partie ne doit être comptée qu'une fois.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .decks_log import PlayerDeck
from .game_state import Game, round_number

_SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    session     TEXT NOT NULL,
    game_index  INTEGER NOT NULL,
    played_on   TEXT NOT NULL,   -- date ISO (jour de la session)
    game_ts     TEXT,            -- heure du CREATE_GAME
    deck_name   TEXT,
    deck_id     INTEGER,
    opponent    TEXT,
    result      TEXT,            -- WON / LOST / TIED
    turns       INTEGER,
    game_type   TEXT,
    format_type TEXT,
    PRIMARY KEY (session, game_index)
);
"""


def default_db_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "cairn" / "history.sqlite"


@dataclass
class DeckStats:
    deck_name: str
    games: int
    wins: int
    # Durée moyenne d'une partie, en secondes. 0 = aucune partie chronométrée.
    avg_duration_s: int = 0
    # Les mêmes, séparées par issue. Une victoire et une défaite n'ont pas la
    # même forme : un deck agressif gagne court et perd long, un deck de
    # contrôle l'inverse. La moyenne des deux mélangées ne dit rien de ça, et
    # c'est pourtant ce qui indique comment le deck perd ses parties.
    # En MANCHES telles que le joueur les compte (cf. round_number), pas en
    # tours bruts : le tag TURN de Hearthstone en compte deux par manche.
    avg_rounds_win: int = 0
    avg_rounds_loss: int = 0
    avg_duration_win_s: int = 0
    avg_duration_loss_s: int = 0

    @property
    def winrate(self) -> float:
        return self.wins / self.games if self.games else 0.0


class History:
    def __init__(self, path: Path | None = None):
        self.path = path or default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute(_SCHEMA)
        # migration : colonne classe adverse (ajoutée le 01/08/2026)
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(games)")}
        if "opponent_class" not in cols:
            self._conn.execute("ALTER TABLE games ADD COLUMN opponent_class TEXT")
        # archived : parties conservées mais exclues des stats — « repartir de
        # zéro » sur un deck qu'on vient de crafter sans perdre l'historique
        if "archived" not in cols:
            self._conn.execute("ALTER TABLE games ADD COLUMN archived INTEGER DEFAULT 0")
        if "duration_s" not in cols:
            self._conn.execute("ALTER TABLE games ADD COLUMN duration_s INTEGER")
        # Archétype du deck adverse (29/08/2026). Le winrate par CLASSE mélange
        # des decks opposés : 39 % face au Démoniste, mais 29 % contre un Rafaam
        # et 75 % sans. Vide = rien de reconnaissable n'a été montré, jamais une
        # supposition (cf. archetypes.py).
        # Concession, et à quel tour. Hearthstone la journalise explicitement
        # (PLAYSTATE=CONCEDED) : une partie abandonnée au tour 1 n'est pas une
        # partie courte, c'est une non-partie, et la confondre avec l'autre
        # fausse toutes les durées moyennes.
        if "conceded" not in cols:
            self._conn.execute("ALTER TABLE games ADD COLUMN conceded TEXT DEFAULT ''")
            self._conn.execute("ALTER TABLE games ADD COLUMN conceded_turn INTEGER DEFAULT 0")
        if "opponent_archetype" not in cols:
            self._conn.execute(
                "ALTER TABLE games ADD COLUMN opponent_archetype TEXT DEFAULT ''")
        self._conn.commit()

    # ---- saisie manuelle ---------------------------------------------------

    CLASS_KEYS = frozenset({
        "DEATHKNIGHT", "DEMONHUNTER", "DRUID", "HUNTER", "MAGE", "PALADIN",
        "PRIEST", "ROGUE", "SHAMAN", "WARLOCK", "WARRIOR",
    })

    def add_manual(self, deck_name: str, opponent_class: str, won: bool) -> None:
        """Partie saisie à la main (journal HS coupé, partie hors suivi…).

        Rangée dans une session « manual » avec un index qui suit, pour ne
        jamais entrer en collision avec les parties lues dans les logs.

        La classe doit être une CLÉ interne (« SHAMAN »), jamais un libellé
        traduit. Une saisie du 05/08/2026 avait enregistré « Chaman » : les
        statistiques affichaient alors deux lignes « Chaman » distinctes, l'une
        de 17 parties et l'autre d'une seule, sans que rien ne le signale. Un
        libellé qui passe pour une clé est invisible jusqu'à ce qu'on compte.
        """
        if opponent_class and opponent_class not in self.CLASS_KEYS:
            opponent_class = ""   # inconnue plutôt que fausse
        row = self._conn.execute(
            "SELECT COALESCE(MAX(game_index), -1) FROM games WHERE session = 'manual'"
        ).fetchone()
        now = date.today().isoformat()
        self._conn.execute(
            """INSERT INTO games
               (session, game_index, played_on, deck_name, result, game_type,
                opponent_class, archived)
               VALUES (?,?,?,?,?,?,?,0)""",
            (
                "manual",
                row[0] + 1,
                now,
                deck_name or None,
                "WON" if won else "LOST",
                "MANUAL",
                opponent_class or None,
            ),
        )
        self._conn.commit()

    # ---- gestion des decks -------------------------------------------------

    def archive_deck(self, deck_name: str) -> int:
        """Sort les parties d'un deck des stats sans les détruire."""
        cur = self._conn.execute(
            "UPDATE games SET archived = 1 WHERE deck_name = ? AND archived = 0",
            (deck_name,),
        )
        self._conn.commit()
        return cur.rowcount

    def delete_deck(self, deck_name: str) -> int:
        """Supprime définitivement les parties d'un deck."""
        cur = self._conn.execute("DELETE FROM games WHERE deck_name = ?", (deck_name,))
        self._conn.commit()
        return cur.rowcount

    def delete_game(self, session: str, game_index: int) -> bool:
        """Supprime UNE partie, désignée par sa clé primaire."""
        cur = self._conn.execute(
            "DELETE FROM games WHERE session = ? AND game_index = ?",
            (session, int(game_index)),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def record(
        self,
        session: str,
        game_index: int,
        game: Game,
        deck: PlayerDeck | None,
        opponent_class: str | None = None,
        opponent_archetype: str = "",
    ) -> bool:
        """Enregistre une partie TERMINÉE. Rend False si déjà connue."""
        if not game.complete:
            return False
        local = game.local_player_id()
        local_name = game.player_names.get(local, "") if local is not None else ""
        opponent = next((n for n in game.results if n != local_name), None)
        # Jour extrait du nom de session « Hearthstone_2026_08_01_00_06_06 ».
        # Ce nom est celui du LANCEMENT du jeu : une session commencée à 22h30
        # et poursuivie après minuit garderait la date de la veille pour ses
        # parties du petit matin. Elles étaient alors triées comme les plus
        # ANCIENNES de leur journée — reléguées hors des quinze parties
        # récentes affichées, donc invisibles alors qu'elles venaient de finir.
        # Une heure de partie antérieure à l'heure de lancement signifie qu'on
        # a franchi minuit.
        parts = session.split("_")
        played_on = date.today().isoformat()
        if len(parts) >= 7:
            try:
                jour = date(int(parts[1]), int(parts[2]), int(parts[3]))
                if (game.ts or "")[:8] < f"{parts[4]}:{parts[5]}:{parts[6]}":
                    jour += timedelta(days=1)
                played_on = jour.isoformat()
            except ValueError:
                pass
        elif len(parts) >= 4:
            played_on = f"{parts[1]}-{parts[2]}-{parts[3]}"
        # colonnes nommées : la table en a gagné (opponent_class, archived) et
        # un INSERT positionnel casserait à chaque migration
        cur = self._conn.execute(
            """INSERT OR IGNORE INTO games
               (session, game_index, played_on, game_ts, deck_name, deck_id,
                opponent, result, turns, game_type, format_type, opponent_class,
                duration_s, opponent_archetype, conceded, conceded_turn)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                session,
                game_index,
                played_on,
                game.ts,
                deck.name if deck else None,
                deck.deck_id if deck else None,
                opponent,
                game.results.get(local_name),
                game.turns,
                game.game_type,
                game.format_type,
                opponent_class,
                game.duration_seconds(),
                opponent_archetype or "",
                ("me" if game.conceded_by == local_name
                 else "opp" if game.conceded_by else ""),
                game.conceded_turn,
            ),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def class_stats(
        self, deck_name: str | None = None
    ) -> list[tuple[str, int, int, int]]:
        """[(classe adverse, parties, victoires, durée moyenne en s)].

        La durée dit quelque chose que le winrate ne dit pas : contre quoi les
        parties s'éternisent. Deux matchups à 50 % ne coûtent pas le même temps,
        et c'est ce qui décide quoi jouer quand on a une heure devant soi.

        Moyenne calculée sur les seules parties CHRONOMÉTRÉES (``duration_s``
        peut manquer sur une partie interrompue) : compter les autres pour zéro
        tirerait la moyenne vers le bas sans prévenir.
        """
        where = "AND deck_name = ?" if deck_name else ""
        params = (deck_name,) if deck_name else ()
        return [
            (r[0] or "?", r[1], r[2] or 0, int(r[3] or 0))
            for r in self._conn.execute(
                f"""SELECT opponent_class, COUNT(*),
                           SUM(CASE WHEN result = 'WON' THEN 1 ELSE 0 END),
                           AVG(CASE WHEN duration_s > 0 AND NOT (conceded != '' AND conceded_turn <= 2)
                                    THEN duration_s END)
                    FROM games WHERE archived = 0 {where}
                    GROUP BY opponent_class ORDER BY COUNT(*) DESC""",
                params,
            )
        ]

    def overall(self) -> tuple[int, int]:
        """(parties, victoires) toutes confondues."""
        row = self._conn.execute(
            """SELECT COUNT(*), SUM(CASE WHEN result = 'WON' THEN 1 ELSE 0 END)
               FROM games WHERE archived = 0"""
        ).fetchone()
        return (row[0] or 0, row[1] or 0)

    def vs_class(self, opponent_class: str) -> tuple[int, int]:
        """(victoires, défaites) contre une classe donnée."""
        row = self._conn.execute(
            """SELECT SUM(CASE WHEN result = 'WON' THEN 1 ELSE 0 END),
                      SUM(CASE WHEN result = 'LOST' THEN 1 ELSE 0 END)
               FROM games WHERE archived = 0 AND opponent_class = ?""",
            (opponent_class,),
        ).fetchone()
        return (row[0] or 0, row[1] or 0)

    def deck_stats(self) -> list[DeckStats]:
        # « vraie partie » : chronométrée, et pas une concession de départ.
        # Sans ce filtre, un adversaire qui abandonne au tour 2 tire toutes les
        # moyennes vers le bas et fait passer un deck lent pour un deck rapide.
        vraie = "duration_s > 0 AND NOT (conceded != '' AND conceded_turn <= 2)"
        rows = self._conn.execute(
            f"""SELECT COALESCE(deck_name, '?'), COUNT(*),
                      SUM(CASE WHEN result = 'WON' THEN 1 ELSE 0 END),
                      AVG(CASE WHEN {vraie} THEN duration_s END),
                      AVG(CASE WHEN result = 'WON'  AND turns > 0 AND {vraie} THEN turns END),
                      AVG(CASE WHEN result = 'LOST' AND turns > 0 AND {vraie} THEN turns END),
                      AVG(CASE WHEN result = 'WON'  AND {vraie} THEN duration_s END),
                      AVG(CASE WHEN result = 'LOST' AND {vraie} THEN duration_s END)
               FROM games WHERE archived = 0
               GROUP BY deck_name ORDER BY COUNT(*) DESC"""
        ).fetchall()
        return [
            DeckStats(deck_name=r[0], games=r[1], wins=r[2] or 0,
                      avg_duration_s=int(r[3] or 0),
                      avg_rounds_win=round_number(int(r[4])) if r[4] else 0,
                      avg_rounds_loss=round_number(int(r[5])) if r[5] else 0,
                      avg_duration_win_s=int(r[6] or 0),
                      avg_duration_loss_s=int(r[7] or 0))
            for r in rows
        ]

    def recent(self, limit: int = 20, deck_name: str | None = None) -> list[tuple]:
        where = "AND deck_name = ?" if deck_name else ""
        params = (deck_name, limit) if deck_name else (limit,)
        return self._conn.execute(
            f"""SELECT played_on, game_ts, deck_name, opponent, result, turns,
                       opponent_class, session, game_index, duration_s,
                       conceded, conceded_turn
                FROM games WHERE archived = 0 {where}
                ORDER BY played_on DESC, game_ts DESC LIMIT ?""",
            params,
        ).fetchall()

    def close(self) -> None:
        self._conn.close()

    def archetype_stats(
        self, deck_name: str | None = None, opponent_class: str | None = None
    ) -> list[tuple[str, int, int, int]]:
        """[(archétype, parties, victoires, durée moyenne)] pour une classe.

        C'est LA statistique que les autres trackers ne donnent pas depuis TES
        parties : ils tirent leurs winrates par archétype de leur propre corpus.
        Ici tout vient de ton historique, à ton palier.

        Les parties sans archétype reconnu ressortent sous ``""`` — elles ne
        sont pas jetées : les compter ailleurs fausserait le total de la classe.
        """
        conds, params = ["archived = 0"], []
        if deck_name:
            conds.append("deck_name = ?"); params.append(deck_name)
        if opponent_class:
            conds.append("opponent_class = ?"); params.append(opponent_class)
        where = " AND ".join(conds)
        return [
            (r[0] or "", r[1], r[2] or 0, int(r[3] or 0))
            for r in self._conn.execute(
                f"""SELECT opponent_archetype, COUNT(*),
                           SUM(CASE WHEN result = 'WON' THEN 1 ELSE 0 END),
                           AVG(CASE WHEN duration_s > 0 AND NOT (conceded != '' AND conceded_turn <= 2)
                                    THEN duration_s END)
                    FROM games WHERE {where}
                    GROUP BY opponent_archetype ORDER BY COUNT(*) DESC""",
                params,
            )
        ]

    def set_concede(self, session: str, game_index: int, qui: str, tour: int) -> None:
        """Renseigne la concession d'une partie déjà enregistrée (rattrapage)."""
        self._conn.execute(
            "UPDATE games SET conceded = ?, conceded_turn = ? "
            "WHERE session = ? AND game_index = ?",
            (qui or "", tour or 0, session, game_index),
        )
        self._conn.commit()

    def set_archetype(self, session: str, game_index: int, archetype: str) -> None:
        """Renseigne l'archétype d'une partie déjà enregistrée (rattrapage)."""
        self._conn.execute(
            "UPDATE games SET opponent_archetype = ? WHERE session = ? AND game_index = ?",
            (archetype or "", session, game_index),
        )
        self._conn.commit()
