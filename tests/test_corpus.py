"""L'autre moitié du contrat de collecte : relire le corpus qu'on a alimenté.

Le worker tourne chez Cloudflare et ne peut pas être exécuté ici ; ces tests
montent un serveur qui répond **comme lui** — même forme d'index, même
pagination par curseur, mêmes clés — et vérifient que ``tools/corpus.py``
rapatrie l'ensemble.

Ce qui est réellement verrouillé ici, c'est la promesse du README : ce qui est
parti peut revenir, sans compte et sans clé. Une pagination cassée ferait
silencieusement rendre la première page seulement, et personne ne le verrait.
"""

import gzip
import http.server
import importlib.util
import json
import socketserver
import tarfile
import threading
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location("corpus", RACINE / "tools" / "corpus.py")
corpus = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(corpus)

INSTALL = "0f8c3a21-4e5b-4c7d-9a10-2b6e5d4c3f21"
NOMS = [f"Hearthstone_2026_08_0{n}_00_06_06" for n in range(1, 6)]


def _archive(nom: str) -> bytes:
    """Un tar.gz de session minimal, dans la forme que le worker exige."""
    import io

    tampon = io.BytesIO()
    with tarfile.open(fileobj=tampon, mode="w:gz",
                      format=tarfile.USTAR_FORMAT) as tar:
        contenu = b"GameState.DebugPrint(Power) - CREATE_GAME\n"
        info = tarfile.TarInfo(f"{nom}/Power.log")
        info.size = len(contenu)
        tar.addfile(info, io.BytesIO(contenu))
    return tampon.getvalue()


@pytest.fixture
def depot():
    """Un point de collecte jetable : index paginé deux par deux, et archives.

    La page est volontairement plus petite que le corpus — c'est le seul moyen
    de vérifier que le client suit le curseur au lieu de s'arrêter à la
    première réponse.
    """
    objets = {f"{INSTALL}/{nom}.tar.gz": _archive(nom) for nom in NOMS}
    cles = sorted(objets)
    appels = {"index": 0}

    class Poignee(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _rendre(self, code, corps, type_mime):
            self.send_response(code)
            self.send_header("Content-Type", type_mime)
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        def do_GET(self):
            from urllib.parse import parse_qs, urlparse

            u = urlparse(self.path)
            if u.path == "/parties":
                appels["index"] += 1
                q = parse_qs(u.query)
                debut = int(q.get("curseur", ["0"])[0])
                tranche = cles[debut:debut + 2]
                suite = debut + len(tranche)
                charge = {
                    "sessions": [
                        {"cle": c, "octets": len(objets[c]), "recu": "2026-08-20"}
                        for c in tranche
                    ],
                    "curseur": str(suite) if suite < len(cles) else None,
                }
                return self._rendre(200, json.dumps(charge).encode(),
                                    "application/json")
            if u.path.startswith("/parties/"):
                cle = u.path[len("/parties/"):]
                if cle not in objets:
                    return self._rendre(404, b"inconnue\n", "text/plain")
                return self._rendre(200, objets[cle], "application/gzip")
            self._rendre(404, b"inconnue\n", "text/plain")

        def log_message(self, *a):
            pass

    serveur = socketserver.TCPServer(("127.0.0.1", 0), Poignee)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{serveur.server_address[1]}", objets, appels
    serveur.shutdown()
    serveur.server_close()


def test_l_index_est_suivi_jusqu_au_bout(depot):
    base, objets, appels = depot
    sessions = corpus.index(base)
    assert [s["cle"] for s in sessions] == sorted(objets)
    assert appels["index"] == 3, "pagination : 2 + 2 + 1"


def test_tout_le_corpus_revient_et_se_deballe(depot, tmp_path):
    base, objets, _ = depot
    for cle in objets:
        chemin = corpus.telecharger(base, cle, tmp_path)
        assert chemin is not None
        assert gzip.decompress(chemin.read_bytes())[:5] != b""
        corpus.extraire(chemin, tmp_path)
    for nom in NOMS:
        assert (tmp_path / nom / "Power.log").is_file()


def test_une_session_deja_la_n_est_pas_retelechargee(depot, tmp_path):
    """Le corpus grandit ; on le resynchronise, on ne le recopie pas."""
    base, objets, _ = depot
    cle = next(iter(objets))
    assert corpus.telecharger(base, cle, tmp_path) is not None
    assert corpus.telecharger(base, cle, tmp_path) is None


def test_une_session_absente_ne_fait_pas_tomber_le_script(depot, tmp_path):
    import urllib.error

    base, _, _ = depot
    with pytest.raises(urllib.error.HTTPError):
        corpus.telecharger(base, f"{INSTALL}/Hearthstone_2026_01_01_00_00_00.tar.gz",
                           tmp_path)


# ---- ce qu'on télécharge vient d'inconnus ------------------------------------
#
# Le corpus est ouvert : n'importe qui peut y déposer une session, donc
# n'importe qui peut y déposer un piège. C'est le seul endroit du projet où
# Cairn consomme des données que personne n'a filtrées, et ces trois tests sont
# ce qui sépare « je relis le corpus » de « j'exécute ce qu'on m'envoie ».

def _tar_gz(membres: dict[str, bytes], taille_annoncee: int | None = None) -> bytes:
    import io

    tampon = io.BytesIO()
    with tarfile.open(fileobj=tampon, mode="w:gz",
                      format=tarfile.USTAR_FORMAT) as tar:
        for nom, contenu in membres.items():
            info = tarfile.TarInfo(nom)
            info.size = len(contenu)
            tar.addfile(info, __import__("io").BytesIO(contenu))
    return tampon.getvalue()


def test_une_archive_qui_sort_du_dossier_est_refusee(tmp_path):
    """« ../../.ssh/authorized_keys » : le classique, et il doit rester lettre morte."""
    archive = tmp_path / "piege.tar.gz"
    archive.write_bytes(_tar_gz({"../evade.txt": b"pwned"}))
    # le filtre refuse bruyamment plutôt que d'ignorer le membre : une archive
    # piégée est une information, pas un détail à avaler en silence
    with pytest.raises(tarfile.TarError):
        corpus.extraire(archive, tmp_path / "sortie")
    assert not (tmp_path / "evade.txt").exists(), "écriture hors du dossier de destination"


def test_une_bombe_de_decompression_est_refusee(tmp_path):
    """500 Ko qui se déballent en gigaoctets : le filtre de noms ne voit rien,
    seul le total annoncé le dit."""
    archive = tmp_path / "bombe.tar.gz"
    archive.write_bytes(_tar_gz({"Hearthstone_2026_08_01_00_06_06/Power.log":
                                 b"\0" * (corpus.DEBALLE_MAX + 1)}))
    with pytest.raises(corpus.Refus):
        corpus.extraire(archive, tmp_path / "sortie")
    assert not (tmp_path / "sortie").exists() or not any(
        (tmp_path / "sortie").rglob("*")
    ), "rien ne doit être écrit avant la vérification"


def test_une_reponse_sans_fin_ne_vide_pas_la_memoire(tmp_path):
    """Un serveur hostile — ou un --url mal choisi — ne doit pas pouvoir faire
    lire un flux illimité."""
    class Poignee(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/gzip")
            self.end_headers()
            try:
                for _ in range(64):
                    self.wfile.write(b"\0" * 1024 * 1024)
            except OSError:
                pass   # le client a raccroché : c'est le comportement attendu

        def log_message(self, *a):
            pass

    serveur = socketserver.TCPServer(("127.0.0.1", 0), Poignee)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    try:
        with pytest.raises(corpus.Refus):
            corpus._lire(f"http://127.0.0.1:{serveur.server_address[1]}/x",
                         plafond=1024 * 1024)
    finally:
        serveur.shutdown()
        serveur.server_close()
