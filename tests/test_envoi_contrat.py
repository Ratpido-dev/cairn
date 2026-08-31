"""Contrat entre le client d'envoi et le point de collecte.

Le point de collecte (``collecte/src/worker.js``) tourne chez Cloudflare et ne
peut pas être exécuté ici. Ce que ces tests vérifient, c'est le **contrat** des
deux côtés de la frontière, sur de vraies requêtes HTTP :

1. l'archive produite par le client passe les contrôles que le worker applique
   — même plafond de taille, même forme d'en-têtes, même inspection du premier
   bloc de l'archive ;
2. le client réagit correctement à chaque code de retour, et notamment
   distingue « reviens plus tard » (429) de « je refuse » (400) — s'y tromper
   fait perdre une partie pour de bon, ou en fait réessayer une indéfiniment.

Les règles ci-dessous sont recopiées du worker. Si l'une des deux moitiés
change, ce fichier doit changer aussi : c'est justement ce qu'on veut d'un test
de contrat.
"""

import gzip
import http.server
import re
import shutil
import socketserver
import threading

import pytest

from src.cairn import envoi
from src.cairn.paths import FIXTURES_DIR

FIXTURE = FIXTURES_DIR / "Hearthstone_2026_08_01_00_06_06"

# ---- les règles du worker, recopiées -----------------------------------------
MAX_OCTETS = 8 * 1024 * 1024
ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
SESSION = re.compile(r"^Hearthstone_[0-9_]{8,40}$")
TAR_BLOC = 512
TAR_MAGIE = 257

pytestmark = pytest.mark.skipif(
    not (FIXTURE / "Power.log").is_file(), reason="fixture absente"
)


@pytest.fixture
def outbox(tmp_path, monkeypatch):
    """Une outbox contenant une VRAIE session, telle qu'elle partirait."""
    monkeypatch.delenv("CAIRN_SHARE_ENDPOINT", raising=False)
    dest = tmp_path / "outbox"
    session = dest / FIXTURE.name
    session.mkdir(parents=True)
    for fichier in FIXTURE.glob("*.log"):
        shutil.copy2(fichier, session / fichier.name)
    (session / "meta.json").write_text('{"schema": 1}', encoding="utf-8")
    return dest


@pytest.fixture
def serveur():
    """Un serveur HTTP jetable qui rend le code qu'on lui demande."""
    recu = {}
    consigne = {"code": 204}

    class Poignee(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            recu["corps"] = self.rfile.read(int(self.headers["Content-Length"]))
            recu["entetes"] = dict(self.headers)
            recu["appels"] = recu.get("appels", 0) + 1
            code = consigne["code"]
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass

    serveur = socketserver.TCPServer(("127.0.0.1", 0), Poignee)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{serveur.server_address[1]}/depot"
    yield url, recu, consigne
    serveur.shutdown()
    serveur.server_close()


# ---- 1. ce que le client produit passe les contrôles du worker ---------------

def test_l_archive_passe_les_controles_du_worker(outbox, serveur):
    url, recu, _ = serveur
    session = next(d for d in outbox.iterdir() if d.is_dir())
    assert envoi.envoyer_en_attente(
        url=url, install_id="0f8c3a21-4e5b-4c7d-9a10-2b6e5d4c3f21", dest=outbox
    ) == (1, 0)

    corps, entetes = recu["corps"], recu["entetes"]

    # plafond de taille
    assert 0 < len(corps) <= MAX_OCTETS
    assert int(entetes["Content-Length"]) == len(corps)
    assert entetes["Content-Type"] == "application/gzip"

    # forme des en-têtes attendue par le worker
    assert ID.match(entetes["X-Cairn-Install"])
    assert SESSION.match(entetes["X-Cairn-Session"])

    # inspection du premier bloc, exactement comme le worker
    bloc = gzip.decompress(corps)[:TAR_BLOC]
    assert len(bloc) == TAR_BLOC
    assert bloc[TAR_MAGIE:TAR_MAGIE + 5] == b"ustar", "en-tête PAX : le worker refuserait"
    nom = bloc[:100].split(b"\0", 1)[0].decode()
    assert nom.startswith(f"{session.name}/")


def test_une_session_reelle_reste_tres_en_dessous_du_plafond(outbox):
    session = next(d for d in outbox.iterdir() if d.is_dir())
    brut = sum(f.stat().st_size for f in session.iterdir())
    compresse = len(envoi.archive(session))
    assert compresse < MAX_OCTETS / 4     # marge confortable
    assert compresse < brut / 10          # le gzip fait son travail


# ---- 2. le client réagit correctement à chaque code --------------------------

@pytest.mark.parametrize("code", [200, 201, 204])
def test_succes_efface_la_session(outbox, serveur, code):
    url, _, consigne = serveur
    consigne["code"] = code
    assert envoi.envoyer_en_attente(url=url, install_id="i" * 12, dest=outbox) == (1, 0)
    assert not list(outbox.iterdir())


@pytest.mark.parametrize("code", [400, 413, 415])
def test_un_refus_definitif_arrete_les_frais(outbox, serveur, code):
    """Le worker rend ces codes quand le contenu ne passera jamais. Réessayer
    chaque jour ne ferait que remplir ses journaux — et les nôtres."""
    url, recu, consigne = serveur
    consigne["code"] = code
    assert envoi.envoyer_en_attente(url=url, install_id="i" * 12,
                                    dest=outbox, maintenant=0.0) == (0, 1)
    session = next(d for d in outbox.iterdir() if d.is_dir())
    assert envoi.etat(session)["abandonne"] is True

    # un second passage ne doit plus toucher au réseau
    envoi.envoyer_en_attente(url=url, install_id="i" * 12, dest=outbox,
                             maintenant=10**9)
    assert recu["appels"] == 1


@pytest.mark.parametrize("code", [429, 408, 500, 503])
def test_un_refus_temporaire_conserve_la_partie(outbox, serveur, code):
    """429 = quota du worker atteint, 5xx = panne. Dans les deux cas la partie
    doit survivre et repartir plus tard."""
    url, _, consigne = serveur
    consigne["code"] = code
    assert envoi.envoyer_en_attente(url=url, install_id="i" * 12,
                                    dest=outbox, maintenant=0.0) == (0, 1)
    session = next(d for d in outbox.iterdir() if d.is_dir())
    etat = envoi.etat(session)
    assert not etat["abandonne"]
    assert etat["prochain_essai"] == envoi.BACKOFF[0]
    assert (session / "Power.log").is_file()   # rien n'a été perdu


def test_le_quota_puis_la_reprise(outbox, serveur):
    """Le scénario réel d'un 429 : refusé maintenant, accepté au tour suivant."""
    url, _, consigne = serveur
    consigne["code"] = 429
    assert envoi.envoyer_en_attente(url=url, install_id="i" * 12,
                                    dest=outbox, maintenant=0.0) == (0, 1)
    consigne["code"] = 204
    session = next(d for d in outbox.iterdir() if d.is_dir())
    apres = envoi.etat(session)["prochain_essai"]
    assert envoi.envoyer_en_attente(url=url, install_id="i" * 12,
                                    dest=outbox, maintenant=apres) == (1, 0)


def test_serveur_injoignable_ne_perd_rien(outbox):
    """Port fermé : le cas le plus courant, et le plus important à ne pas rater."""
    assert envoi.envoyer_en_attente(
        url="http://127.0.0.1:1/depot", install_id="i" * 12,
        dest=outbox, maintenant=0.0,
    ) == (0, 1)
    session = next(d for d in outbox.iterdir() if d.is_dir())
    assert not envoi.etat(session)["abandonne"]
    assert (session / "Power.log").is_file()
