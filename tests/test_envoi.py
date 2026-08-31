"""Envoi automatique des parties partagées : file d'attente et reprise.

Ce qui doit tenir, dans l'ordre d'importance :

1. **Rien ne part sans point de collecte.** C'est l'état par défaut, et il doit
   se comporter exactement comme avant l'existence de ce module.
2. **Un échec ne perd jamais une partie.** Réseau coupé, serveur en panne,
   machine éteinte : la session reste dans l'outbox et repart plus tard.
3. **Un échec ne martèle pas non plus.** L'attente croît, et un refus définitif
   du serveur arrête les frais.
4. **Ce qui est parti est effacé** — l'outbox n'est pas un historique.
"""

import json
import tarfile
import io

import pytest

from src.cairn import envoi


@pytest.fixture
def outbox(tmp_path, monkeypatch):
    """Une outbox contenant une session prête à partir."""
    monkeypatch.delenv("CAIRN_SHARE_ENDPOINT", raising=False)
    dest = tmp_path / "outbox"
    session = dest / "Hearthstone_2026_08_01_00_06_06"
    session.mkdir(parents=True)
    (session / "Power.log").write_text("CREATE_GAME\n", encoding="utf-8")
    (session / "meta.json").write_text('{"schema": 1}', encoding="utf-8")
    return dest


def _session(outbox):
    return next(d for d in outbox.iterdir() if d.is_dir())


# ---- l'état par défaut : rien ne part ----------------------------------------

def test_sans_endpoint_rien_ne_part(outbox):
    envoyees, restantes = envoi.envoyer_en_attente(dest=outbox)
    assert (envoyees, restantes) == (0, 1)
    assert _session(outbox).is_dir()          # toujours là, intacte
    assert not (_session(outbox) / envoi.ETAT).exists()  # pas même un échec noté


def test_endpoint_lu_dans_l_environnement(monkeypatch):
    monkeypatch.setenv("CAIRN_SHARE_ENDPOINT", "  https://exemple.test/depot  ")
    assert envoi.endpoint() == "https://exemple.test/depot"


# ---- l'archive envoyée -------------------------------------------------------

def test_archive_contient_la_session_sans_son_etat(outbox):
    session = _session(outbox)
    envoi._noter(session, tentatives=3)       # ne doit PAS voyager
    with tarfile.open(fileobj=io.BytesIO(envoi.archive(session))) as tar:
        noms = sorted(m.name for m in tar.getmembers())
    assert noms == [f"{session.name}/Power.log", f"{session.name}/meta.json"]


def test_archive_compresse(outbox):
    session = _session(outbox)
    (session / "Power.log").write_text("CREATE_GAME\n" * 5000, encoding="utf-8")
    brut = (session / "Power.log").stat().st_size
    assert len(envoi.archive(session)) < brut / 10


# ---- succès ------------------------------------------------------------------

def test_session_envoyee_puis_effacee(outbox, monkeypatch):
    recu = {}

    def _faux_envoi(session, url, install_id, timeout=envoi.TIMEOUT):
        recu["url"] = url
        recu["install"] = install_id
        recu["octets"] = len(envoi.archive(session))
        return True, "", False

    monkeypatch.setattr(envoi, "envoyer_session", _faux_envoi)
    envoyees, restantes = envoi.envoyer_en_attente(
        url="https://exemple.test/depot", install_id="abc", dest=outbox
    )
    assert (envoyees, restantes) == (1, 0)
    assert recu["install"] == "abc" and recu["octets"] > 0
    assert not list(outbox.iterdir())      # l'outbox n'est pas un historique


# ---- échecs ------------------------------------------------------------------

def test_echec_conserve_la_session_et_note_la_raison(outbox, monkeypatch):
    monkeypatch.setattr(envoi, "envoyer_session",
                        lambda *a, **k: (False, "pas de réseau", False))
    envoyees, restantes = envoi.envoyer_en_attente(
        url="https://exemple.test/depot", dest=outbox, maintenant=1000.0
    )
    assert (envoyees, restantes) == (0, 1)
    e = envoi.etat(_session(outbox))
    assert e["tentatives"] == 1
    assert e["derniere_erreur"] == "pas de réseau"
    assert e["prochain_essai"] == 1000.0 + envoi.BACKOFF[0]
    assert not e["abandonne"]


def test_l_attente_croit_a_chaque_echec(outbox, monkeypatch):
    monkeypatch.setattr(envoi, "envoyer_session",
                        lambda *a, **k: (False, "boum", False))
    session = _session(outbox)
    attentes = []
    for n in range(3):
        envoi._noter(session, prochain_essai=0)   # on force l'essai
        envoi.envoyer_en_attente(url="https://x.test", dest=outbox, maintenant=0.0)
        attentes.append(envoi.etat(session)["prochain_essai"])
    assert attentes == sorted(attentes) and len(set(attentes)) == 3


def test_pas_de_nouvel_essai_avant_l_heure(outbox, monkeypatch):
    envoi._noter(_session(outbox), prochain_essai=5000.0)
    monkeypatch.setattr(envoi, "envoyer_session",
                        lambda *a, **k: pytest.fail("essai prématuré"))
    assert envoi.envoyer_en_attente(url="https://x.test", dest=outbox,
                                    maintenant=4999.0) == (0, 1)


def test_refus_definitif_arrete_les_frais(outbox, monkeypatch):
    """Un 400 ne se réparera pas tout seul : inutile de le rejouer chaque jour."""
    monkeypatch.setattr(envoi, "envoyer_session",
                        lambda *a, **k: (False, "HTTP 400", True))
    envoi.envoyer_en_attente(url="https://x.test", dest=outbox, maintenant=0.0)
    session = _session(outbox)
    assert envoi.etat(session)["abandonne"] is True
    assert envoi.a_essayer(session, maintenant=10**9) is False
    assert envoi.bloquees(outbox) == [(session.name, "HTTP 400")]


def test_abandon_apres_le_dernier_palier(outbox, monkeypatch):
    monkeypatch.setattr(envoi, "envoyer_session",
                        lambda *a, **k: (False, "boum", False))
    session = _session(outbox)
    for _ in range(len(envoi.BACKOFF) + 1):
        envoi._noter(session, prochain_essai=0, abandonne=False)
        envoi.envoyer_en_attente(url="https://x.test", dest=outbox, maintenant=0.0)
    assert envoi.etat(session)["abandonne"] is True
    assert session.is_dir()      # abandonnée, mais JAMAIS supprimée


def test_session_trop_volumineuse_refusee_sans_reseau(outbox, monkeypatch):
    monkeypatch.setattr(envoi, "TAILLE_MAX", 10)
    def _jamais(*a, **k):
        pytest.fail("le réseau a été touché pour une session hors gabarit")
    monkeypatch.setattr(envoi.urllib.request, "urlopen", _jamais)
    ok, message, definitif = envoi.envoyer_session(
        _session(outbox), "https://x.test"
    )
    assert (ok, definitif) == (False, True)
    assert "trop volumineuse" in message


# ---- codes HTTP --------------------------------------------------------------

class _Reponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.parametrize("code, attendu", [(200, True), (201, True), (204, True)])
def test_2xx_vaut_succes(outbox, monkeypatch, code, attendu):
    monkeypatch.setattr(envoi.urllib.request, "urlopen",
                        lambda *a, **k: _Reponse(code))
    ok, _, _ = envoi.envoyer_session(_session(outbox), "https://x.test")
    assert ok is attendu


@pytest.mark.parametrize("code, definitif", [
    (400, True), (403, True), (404, True),   # le serveur refuse : inutile d'insister
    (408, False), (429, False),              # « reviens plus tard » : on revient
    (500, False), (503, False),              # panne serveur : on revient
])
def test_les_erreurs_temporaires_sont_distinguees_des_refus(
    outbox, monkeypatch, code, definitif
):
    def _erreur(*a, **k):
        raise envoi.urllib.error.HTTPError("https://x.test", code, "non", {}, None)

    monkeypatch.setattr(envoi.urllib.request, "urlopen", _erreur)
    ok, message, def_ = envoi.envoyer_session(_session(outbox), "https://x.test")
    assert ok is False and def_ is definitif and message == f"HTTP {code}"


def test_reseau_coupe_ne_leve_jamais(outbox, monkeypatch):
    def _boum(*a, **k):
        raise envoi.urllib.error.URLError("pas de route vers l'hôte")

    monkeypatch.setattr(envoi.urllib.request, "urlopen", _boum)
    ok, message, definitif = envoi.envoyer_session(_session(outbox), "https://x.test")
    assert (ok, definitif) == (False, False) and message


def test_etat_illisible_ne_casse_rien(outbox):
    (_session(outbox) / envoi.ETAT).write_text("{ tronqué", encoding="utf-8")
    assert envoi.etat(_session(outbox)) == {}
    assert envoi.a_essayer(_session(outbox)) is True


def test_l_etat_reste_du_json_valide(outbox):
    """Pas d'``Infinity`` : le fichier doit rester relisible par n'importe quoi."""
    session = _session(outbox)
    for _ in range(len(envoi.BACKOFF) + 2):
        envoi._reporter(session, "boum", 0.0)
    json.loads((session / envoi.ETAT).read_text(encoding="utf-8"))
