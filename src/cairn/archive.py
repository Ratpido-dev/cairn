"""Archivage des journaux de session — garder ce que Hearthstone efface.

Le jeu ne conserve qu'une poignée de dossiers ``Logs/Hearthstone_<date>/`` et
supprime les plus anciens sans prévenir. Or l'historique SQLite de Cairn ne
retient qu'un RÉSUMÉ par partie (deck, classe, résultat, durée) : dès que le
``Power.log`` disparaît, plus personne ne peut dire quelles cartes ont été
jouées, ni pourquoi la partie a basculé. Mesuré le 18/08/2026 : 163 parties en
base, 53 encore accompagnées de leur journal.

Deux principes :

- **compression** — un ``Power.log`` de 14,8 Mo tombe à 827 Ko (×18) en 80 ms.
  Une session coûte donc moins d'un mégaoctet : la question de la place ne se
  pose plus, et l'archivage peut rester actif en permanence ;
- **écriture par membres gzip successifs** — chaque bloc est un flux gzip
  complet, et `gzip` relit une concaténation de membres de façon transparente.
  Un processus tué en pleine partie ne perd donc que le dernier bloc, pas
  l'archive entière (ce qui arriverait avec un flux unique laissé ouvert).
"""

from __future__ import annotations

import gzip
import shutil
from dataclasses import dataclass
from pathlib import Path

# Taille de texte accumulée avant d'écrire un membre gzip. 1 Mo ≈ 20 s de jeu :
# assez gros pour que la compression reste excellente, assez petit pour qu'un
# arrêt brutal ne coûte presque rien.
CHUNK = 1 << 20

# En dessous, un Power.log ne contient qu'une erreur interne de HS : pas de
# CREATE_GAME, donc rien à archiver (cf. les journaux écrits sans log.config).
MIN_UTILE = 4096


@dataclass
class ArchivedSession:
    name: str
    path: Path
    size: int


class SessionArchive:
    """Copie compressée et incrémentale des journaux de session."""

    def __init__(self, root: Path, chunk_bytes: int = CHUNK):
        self.root = Path(root)
        self.chunk_bytes = chunk_bytes
        self._name: str | None = None   # session en cours d'archivage
        self._buf: list[str] = []
        self._pending = 0               # octets de texte en attente d'écriture

    # ---- session courante --------------------------------------------------

    def start(self, session: Path, from_start: bool = True) -> None:
        """Bascule sur une nouvelle session (l'ancienne est vidée d'abord).

        ``from_start`` : le lecteur va-t-il rejouer ce journal DEPUIS LE DÉBUT ?
        C'est le cas normal du tracker, et ça change tout — relancer Cairn au
        milieu d'une session ferait sinon écrire une deuxième fois les parties
        déjà archivées, et l'archive rejouée montrerait chaque partie en double.
        On repart donc d'une archive vide : le journal de la session courante
        est encore sur le disque de HS, la réécrire est sans risque.
        """
        self.flush()
        self._name = session.name
        if from_start:
            self.path_for(session.name).unlink(missing_ok=True)
        self._copy_decks(session)

    def feed(self, lines: list[str]) -> None:
        """Accumule les lignes LUES par le suiveur.

        On archive ce que le tracker a réellement consommé, pas le fichier brut :
        l'archive rejouée redonne donc exactement l'état que Cairn a vu — et la
        ligne incomplète en fin de fichier, gardée en tampon par le tailer,
        arrive au tour suivant sans être coupée en deux.
        """
        if self._name is None or not lines:
            return
        for line in lines:
            self._buf.append(line)
            self._pending += len(line) + 1
        if self._pending >= self.chunk_bytes:
            self.flush()

    def flush(self) -> None:
        """Écrit le tampon comme un membre gzip supplémentaire."""
        if self._name is None or not self._buf:
            return
        texte = "\n".join(self._buf) + "\n"
        self._buf.clear()
        self._pending = 0
        cible = self.path_for(self._name)
        try:
            cible.parent.mkdir(parents=True, exist_ok=True)
            with open(cible, "ab") as f:
                f.write(gzip.compress(texte.encode("utf-8"), 6))
        except OSError:
            pass  # l'archivage est un confort, jamais un blocage du suivi

    def close(self) -> None:
        self.flush()
        self._name = None

    # ---- rattrapage --------------------------------------------------------

    def backfill(self, *sources: Path | None) -> list[str]:
        """Archive les sessions déjà présentes sur le disque et pas encore prises.

        À appeler au démarrage : ce sont les sessions que HS n'a pas encore
        effacées, et celles que l'outbox de partage a sauvées par accident. La
        session EN COURS est exclue — le suiveur la lit depuis le début et
        l'archive au fil de l'eau, l'ajouter ici la dupliquerait.
        """
        faites = self._absorber_ancien_miroir()
        for source in sources:
            if source is None or not Path(source).is_dir():
                continue
            for dossier in sorted(Path(source).iterdir()):
                if not dossier.is_dir() or not dossier.name.startswith("Hearthstone_"):
                    continue
                if dossier.name == self._name or self.path_for(dossier.name).exists():
                    continue
                if self._archive_complet(dossier):
                    faites.append(dossier.name)
        return faites

    def _absorber_ancien_miroir(self) -> list[str]:
        """Reprend les journaux à plat laissés par l'ancien miroir de rotation.

        Jusqu'au 02/08/2026, la copie de session était un effet de bord de la
        rotation des journaux (``LiveTracker.maybe_rotate``), sous la forme
        ``<session>.Power.log`` non compressé posé à la racine. La rotation
        ayant été désactivée, ces fichiers sont orphelins — mais ils contiennent
        des sessions que Hearthstone a effacées depuis. On les convertit ; on ne
        les SUPPRIME pas, c'est à l'utilisateur de le faire.
        """
        if not self.root.is_dir():
            return []
        faits = []
        for plat in sorted(self.root.glob("*.Power.log")):
            nom = plat.name[: -len(".Power.log")]
            if self.path_for(nom).exists():
                continue
            try:
                if plat.stat().st_size < MIN_UTILE:
                    continue
            except OSError:
                continue
            cible = self.path_for(nom)
            partiel = cible.with_suffix(".part")
            try:
                cible.parent.mkdir(parents=True, exist_ok=True)
                with open(plat, "rb") as src, gzip.open(partiel, "wb", 6) as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
                partiel.replace(cible)
                faits.append(nom)
            except OSError:
                partiel.unlink(missing_ok=True)
        return faits

    def _archive_complet(self, session: Path) -> bool:
        """Compresse un Power.log entier d'un coup (session déjà terminée)."""
        source = session / "Power.log"
        try:
            if not source.is_file() or source.stat().st_size < MIN_UTILE:
                return False
        except OSError:
            return False
        cible = self.path_for(session.name)
        partiel = cible.with_suffix(".part")
        try:
            cible.parent.mkdir(parents=True, exist_ok=True)
            # écriture atomique : une archive à moitié écrite serait prise pour
            # complète au lancement suivant et la session serait perdue
            with open(source, "rb") as src, gzip.open(partiel, "wb", 6) as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            partiel.replace(cible)
        except OSError:
            partiel.unlink(missing_ok=True)
            return False
        self._copy_decks(session)
        return True

    def _copy_decks(self, session: Path) -> None:
        """``Decks.log`` accompagne le journal : sans lui, plus de nom de deck
        ni de deckcode à la relecture. Quelques kilo-octets, recopiés tels quels
        et réécrits à chaque bascule (des decks sont mis en file en cours de
        session)."""
        src = session / "Decks.log"
        if not src.is_file():
            return
        try:
            dossier = self.root / session.name
            dossier.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dossier / "Decks.log")
        except OSError:
            pass

    # ---- lecture -----------------------------------------------------------

    def path_for(self, name: str) -> Path:
        return self.root / name / "Power.log.gz"

    def sessions(self) -> list[ArchivedSession]:
        """Sessions archivées, de la plus ancienne à la plus récente."""
        if not self.root.is_dir():
            return []
        out = []
        for dossier in sorted(self.root.iterdir()):
            journal = dossier / "Power.log.gz"
            if not journal.is_file():
                continue
            try:
                out.append(
                    ArchivedSession(dossier.name, journal, journal.stat().st_size)
                )
            except OSError:
                continue
        return out

    def total_size(self) -> int:
        return sum(s.size for s in self.sessions())
