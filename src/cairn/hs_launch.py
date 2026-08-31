"""Trouver comment lancer Hearthstone, et le lancer.

Il n'existe pas UNE façon de lancer Hearthstone sous Linux : Lutris, Steam +
Proton, Bottles, Heroic, ou un script maison. Deviner le jeu par son nom serait
fragile — « battle-net », « Battle.net », « Hearthstone », « hs »…

La clé est ailleurs : **Cairn connaît déjà le prefix**, puisque c'est là qu'il
lit les journaux. On ne cherche donc pas un jeu qui *s'appelle* Hearthstone, on
cherche celui qui *habite le prefix qu'on suit*. C'est un rapprochement par
identité de chemin, pas une heuristique sur des chaînes.

Ordre de résolution — le premier qui répond gagne :

1. la commande explicite de la configuration (elle gagne toujours) ;
2. Lutris, par correspondance de répertoire ;
3. une entrée ``.desktop`` dont l'``Exec`` référence le prefix.

Et surtout : **le point 1 est le vrai mécanisme, les autres ne sont que des
raccourcis.** Quelqu'un qui lance le jeu par un script maison, Bottles ou un
``umu-run`` bricolé ne sera trouvé par aucune détection — la fonctionnalité est
donc construite autour du champ manuel, la détection n'étant qu'un confort pour
les cas courants. L'inverse marcherait chez son auteur et frustrerait les autres.

Steam n'est volontairement pas géré : ses jeux non-Steam vivent dans un
``shortcuts.vdf`` binaire, et l'auteur n'avait aucun fichier de ce genre pour
vérifier son parseur. Du code binaire non testé vaut moins que rien ici — la
commande manuelle couvre le cas en attendant.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LaunchMethod:
    """Une façon de lancer le jeu, prête à être exécutée et à être MONTRÉE."""

    source: str  # "config" | "lutris" | "desktop"
    label: str  # ce qu'on affiche à l'utilisateur
    argv: list[str]

    @property
    def command(self) -> str:
        """La commande telle qu'on la montre. Le launcher l'affiche toujours :
        un bouton qui lance un processus sans dire lequel est une boîte noire."""
        return shlex.join(self.argv)


def _same_place(a: Path, b: Path) -> bool:
    """Deux chemins qui désignent le même endroit, l'un pouvant contenir l'autre.

    Lutris pointe la racine du prefix, Cairn parfois un sous-dossier (ou
    l'inverse selon l'installation) : l'égalité stricte raterait la moitié des
    cas. On resout les liens symboliques, sinon un prefix rangé derrière un lien
    ne correspondrait jamais.
    """
    try:
        a, b = a.resolve(), b.resolve()
    except OSError:
        return False
    return a == b or a in b.parents or b in a.parents


def _from_config(command: str) -> LaunchMethod | None:
    command = (command or "").strip()
    if not command:
        return None
    try:
        argv = shlex.split(command)
    except ValueError:  # guillemet non fermé
        return None
    if not argv:
        return None
    return LaunchMethod(source="config", label="commande personnalisée", argv=argv)


def _from_lutris(prefix: Path) -> LaunchMethod | None:
    """Jeu Lutris dont le répertoire est le prefix qu'on suit."""
    try:
        out = subprocess.run(
            ["lutris", "-l", "--json"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    try:
        jeux = json.loads(out.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(jeux, list):
        return None
    for jeu in jeux:
        if not isinstance(jeu, dict):
            continue
        rep = jeu.get("directory")
        slug = jeu.get("slug")
        if not rep or not slug:
            continue
        if _same_place(Path(rep), prefix):
            nom = jeu.get("name") or slug
            return LaunchMethod(
                source="lutris",
                label=f"Lutris — {nom}",
                argv=["lutris", f"lutris:rungame/{slug}"],
            )
    return None


def _desktop_dirs() -> list[Path]:
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    dirs = [data_home / "applications"]
    for base in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":"):
        if base:
            dirs.append(Path(base) / "applications")
    return dirs


def _from_desktop(prefix: Path) -> LaunchMethod | None:
    """Entrée ``.desktop`` dont la ligne Exec mentionne le prefix.

    Lutris, Bottles et Heroic en posent une quand l'utilisateur le demande.
    On ignore les nôtres : ``cairn.desktop`` parle du prefix lui aussi, et se
    lancerait soi-même.
    """
    try:
        cible = str(prefix.resolve())
    except OSError:
        cible = str(prefix)
    for repertoire in _desktop_dirs():
        if not repertoire.is_dir():
            continue
        for fichier in sorted(repertoire.glob("*.desktop")):
            if fichier.stem in ("cairn", "firestone"):
                continue
            try:
                texte = fichier.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            exec_line = ""
            nom = fichier.stem
            for ligne in texte.splitlines():
                if ligne.startswith("Exec=") and not exec_line:
                    exec_line = ligne[5:].strip()
                elif ligne.startswith("Name=") and nom == fichier.stem:
                    nom = ligne[5:].strip()
            if not exec_line or cible not in exec_line:
                continue
            # les codes de champ (%u, %f…) ne veulent rien dire hors d'un bureau
            argv = [a for a in shlex.split(exec_line) if not (len(a) == 2 and a[0] == "%")]
            if argv:
                return LaunchMethod(source="desktop", label=f"Raccourci — {nom}", argv=argv)
    return None


def resolve(prefix: Path | str | None, command: str = "") -> LaunchMethod | None:
    """La façon de lancer le jeu, ou None si on n'en connaît aucune."""
    explicite = _from_config(command)
    if explicite is not None:
        return explicite
    if prefix is None:
        return None
    prefix = Path(prefix)
    if not prefix.exists():
        return None
    return _from_lutris(prefix) or _from_desktop(prefix)


def launch(method: LaunchMethod) -> tuple[bool, str]:
    """Lance le jeu, détaché de Cairn. Rend (succès, message).

    ``start_new_session`` est indispensable : sans lui le jeu meurt avec Cairn,
    et fermer le tracker fermerait Hearthstone.
    """
    try:
        subprocess.Popen(
            method.argv,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return False, f"introuvable : {method.argv[0]}"
    except (OSError, subprocess.SubprocessError) as err:
        return False, str(err)
    return True, method.command
