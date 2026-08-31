"""Téléchargement de la base de cartes HearthstoneJSON.

Dans le paquet (et non dans ``tools/``) pour que le premier lancement d'une
installation normale puisse la récupérer tout seul — et pour que chaque
lancement suivant vérifie, à peu de frais, qu'un patch d'équilibrage n'a pas
rendu la base périmée (cf. ``update_if_stale``).
"""

from __future__ import annotations

import email.utils
import json
import re
import sys
import time
import urllib.error
import urllib.request

from .paths import (
    CARDS_JSON,
    CARDS_JSON_EN,
    CARDS_META,
    CARDS_TEXT,
    CARDS_TEXT_EN,
)

URL = "https://api.hearthstonejson.com/v1/latest/{locale}/cards.json"
TARGETS = {"frFR": CARDS_JSON, "enUS": CARDS_JSON_EN}
# Textes de règles, écrits à part : ils pèsent autant que toute la base élaguée
# et ne servent qu'à l'infobulle de survol, donc on ne les charge qu'à la
# demande (cf. CardsDb.text).
TEXT_TARGETS = {"frFR": CARDS_TEXT, "enUS": CARDS_TEXT_EN}

# ---- cartes dont le CODE connaît l'effet -------------------------------------
#
# Un patch d'équilibrage change deux choses : les données (coût, mécaniques,
# texte) et, parfois, ce que fait vraiment la carte. Le premier se répare tout
# seul en retéléchargeant ; le second casse silencieusement une logique câblée
# ici — le 18/08/2026 « Confrontation des Tol'vir » est passée de « rejoue
# chaque CARTE à (1) » à « invoque chaque SERVITEUR à (1) », ce qu'aucune mise à
# jour de JSON ne pouvait corriger.
#
# D'où cette liste : toute carte dont un module suppose l'effet. Au
# téléchargement, on compare son texte à celui d'avant et on prévient si le jeu
# l'a reformulée. Le test ``test_cards_update`` vérifie qu'aucun identifiant de
# carte cité dans ``src/`` n'en est absent.
LOGIQUE_CABLEE = {
    "CATA_560": "Confrontation des Tol'vir (compteur des cartes à 1)",
    "EDR_430": "compteur dédié",
    "EDR_891": "pool de découverte",
    "EDR_892": "pool de découverte",
    "END_024": "secret",
    "JAIL_470": "compteur dédié",
    "JAIL_509": "Godfrey (atlas)",
    "MIS_102": "pool de découverte",
    "TIME_005": "Rafaam (compteur)",
    "TOY_385": "compteur dédié",
    "YOG_411": "compteur dédié",
    "YOG_518": "compteur dédié",
    "YOG_521": "compteur dédié",
    "YOG_528": "compteur dédié",
    # --- signatures d'archétype (cf. archetypes.py) ---
    # Ces cartes ne servent pas à un effet mais à IDENTIFIER un deck adverse.
    # Elles courent le même risque : une rotation ou un changement de classe et
    # la signature ne reconnaît plus rien, en silence. D'où leur présence ici.
    "CATA_308": "signature Prêtre Medivh",
    "CATA_496": "signature Démoniste Malédictions",
    "FIR_907": "signature Druide Amirdrassil",
    "JAIL_430": "signature Prêtre Azalina",
    "JAIL_440": "signature Chevalier de la mort Goules",
    "JAIL_511": "signature Démoniste Malédictions",
    "JAIL_872": "signature Druide Araignées",
    "JAIL_881": "signature Chasseur Arcanes",
    "TIME_609": "signature Chasseur Bêtes",
    "TIME_890": "signature Prêtre Medivh",
    "TLC_436": "signature Chevalier de la mort Pterreurdactyle",
    "TLC_451": "signature Démoniste Malédictions",
    "TLC_830": "signature Chasseur Bêtes",
}


# ---- version de la base ------------------------------------------------------
#
# HearthstoneJSON sert ``latest`` derrière un CDN qui renvoie un ETag stable :
# une requête HEAD (zéro octet de corps, ~200 ms) suffit à savoir si la base a
# bougé. On garde l'empreinte de ce qu'on a téléchargé, la date du dernier
# contrôle — pour ne pas interroger le CDN à chaque lancement — et les alertes
# de reformulation, que ``cairn-doctor`` réaffiche.

INTERVALLE_H = 12.0  # entre deux contrôles, en heures


def meta() -> dict:
    """Contenu de ``meta.json`` — ``{}`` s'il manque ou s'il est illisible."""
    try:
        with open(CARDS_META, encoding="utf-8") as f:
            charge = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return charge if isinstance(charge, dict) else {}


def _write_meta(patch: dict) -> None:
    fusion = meta() | patch
    CARDS_META.parent.mkdir(parents=True, exist_ok=True)
    CARDS_META.write_text(
        json.dumps(fusion, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def _reformulations(locale: str, nouveaux: dict[str, str]) -> list[dict]:
    """Cartes de ``LOGIQUE_CABLEE`` dont le texte vient de changer.

    Comparé AVANT écriture : une fois le fichier remplacé, l'ancien texte est
    perdu et la reformulation passe inaperçue — c'est exactement ce qui s'est
    produit en août 2026.
    """
    try:
        with open(TEXT_TARGETS[locale], encoding="utf-8") as f:
            anciens = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []  # première installation : rien à comparer
    alertes = []
    for cid, role in LOGIQUE_CABLEE.items():
        avant, apres = anciens.get(cid, ""), nouveaux.get(cid, "")
        if avant and apres and avant != apres:
            alertes.append(
                {"id": cid, "role": role, "avant": avant, "apres": apres,
                 "vu": time.strftime("%Y-%m-%d")}
            )
    return alertes


def _sans_doublons(alertes: list[dict]) -> list[dict]:
    """Une alerte par carte, la plus récente l'emporte."""
    par_carte = {a["id"]: a for a in alertes if "id" in a}
    return list(par_carte.values())


def remote_changed(locale: str, timeout: float = 8.0) -> bool | None:
    """La base en ligne diffère-t-elle de la locale ? ``None`` si indécidable.

    ``None`` (réseau coupé, CDN muet, en-têtes absents) n'est PAS ``False`` :
    l'appelant doit réessayer au lancement suivant plutôt que de considérer la
    base à jour.
    """
    dest = TARGETS[locale]
    if not dest.is_file():
        return True
    req = urllib.request.Request(
        URL.format(locale=locale), method="HEAD", headers={"User-Agent": "cairn"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            etag = resp.headers.get("ETag") or ""
            modifie = resp.headers.get("Last-Modified") or ""
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return None
    connu = (meta().get("locales") or {}).get(locale) or {}
    if etag and connu.get("etag"):
        return etag != connu["etag"]
    # Base téléchargée par une version antérieure (aucune empreinte gardée) :
    # on se rabat sur les dates, ce qui évite un retéléchargement gratuit à la
    # première mise à jour de Cairn.
    if modifie:
        try:
            distant = email.utils.parsedate_to_datetime(modifie).timestamp()
        except (TypeError, ValueError):
            return None
        return distant > dest.stat().st_mtime
    return None

# ---- effets qui placent une carte à un bout du deck --------------------------
#
# Hearthstone ne journalise PAS l'ordre du deck : une carte qui y entre reçoit
# toujours ``ZONE_POSITION value=0``. La seule façon de savoir qu'une carte est
# au fond est donc de connaître l'effet qui l'y a mise — c'est exactement ce que
# font HDT et Firestone. Plutôt qu'une liste d'identifiants à maintenir à chaque
# extension, on lit le TEXTE des cartes une fois, au téléchargement, et on n'en
# garde qu'un drapeau : la base reste petite et se met à jour toute seule.
# « du deck » sans possessif est fréquent (« placées au fond du deck ») ; le
# deck de l'adversaire est en revanche explicitement exclu — un effet qui pose
# une carte chez l'adversaire n'a rien à faire dans NOTRE fond de deck.
_OWN_DECK = (
    r"(?:de\s+(?:votre|son|leur|ce|cette)|du|de\s+la)\s+"
    r"(?:deck|paquet)(?!\s+(?:de\s+votre\s+adversaire|adverse))"
)
_BOTTOM = re.compile(r"(?:en[- ]dessous|au\s+fond)\s+" + _OWN_DECK, re.I)
_TOP = re.compile(r"(?:au[- ]dessus|sur\s+le\s+dessus)\s+" + _OWN_DECK, re.I)


# ---- texte de règles, nettoyé -----------------------------------------------
#
# HearthstoneJSON écrit le texte tel que le jeu le met en forme : balises de
# gras, préfixe de mise en page « [x] », marqueurs « $ » / « # » devant les
# nombres qui varient avec les dégâts des sorts, et variantes séparées par
# « @ » (texte de base @ texte quand la condition est en cours @ texte quand
# elle est remplie). L'infobulle veut la phrase, pas le balisage.
_TAGS = re.compile(r"</?[a-zA-Z][^>]*>")
_LAYOUT = re.compile(r"^\[x\]\s*")


def plain_text(raw: str | None) -> str:
    """Texte de règles lisible : sans balises, sans marqueurs de gabarit."""
    if not raw:
        return ""
    texte = _TAGS.sub("", raw)
    # les variantes conditionnelles viennent APRÈS le texte de base
    texte = texte.split("@", 1)[0]
    # « [x] » signale un texte dont les retours à la ligne sont de la mise en
    # page pure (césures calculées pour la largeur de la carte) : les garder
    # hacherait l'infobulle en tronçons de quatre mots.
    cesures = bool(_LAYOUT.match(texte))
    texte = _LAYOUT.sub("", texte)
    texte = re.sub(r"[$#](?=\d)", "", texte)
    lignes = [ligne.strip() for ligne in texte.replace(" ", " ").split("\n")]
    return (" " if cesures else "\n").join(l for l in lignes if l).strip()


def texts(cards: list[dict], with_bg: bool = False) -> dict[str, str]:
    """``{id: texte}`` pour les cartes qui en ont un."""
    if not with_bg:
        cards = [c for c in cards if c.get("set") not in SKIPPED_SETS]
    out = {}
    for card in cards:
        texte = plain_text(card.get("text"))
        if texte and "id" in card:
            out[card["id"]] = texte
    return out


def is_imbued_hero_power(card: dict) -> bool:
    """Pouvoir héroïque « empreint » (mot-clé Imbue).

    Repéré par ``referencedTags``, que l'on jette ensuite : six pouvoirs
    aujourd'hui, mais le jeu en ajoutera — mieux vaut le déduire à chaque
    téléchargement qu'entretenir une liste d'identifiants à la main.
    """
    return card.get("type") == "HERO_POWER" and "IMBUE" in (
        card.get("referencedTags") or ()
    )


def deck_position(text: str | None) -> str:
    """« bottom » / « top » / "" — d'après le texte français de la carte."""
    if not text:
        return ""
    if _BOTTOM.search(text):
        return "bottom"
    if _TOP.search(text):
        return "top"
    return ""

# doit couvrir _KEPT_FIELDS de cards_db + ce qui alimente ses index de mécaniques
KEPT = ("id", "dbfId", "name", "cost", "cardClass", "type", "rarity", "set",
        "mechanics", "races", "race", "collectible")
# Modes hors périmètre du tracker (cf. cahier des charges : pas de BG, pas de
# Mercenaires) — 35 % des cartes pour zéro usage en construit. HERO_SKINS est
# gardé : c'est là que vivent TOUS les héros, donc la détection des classes.
SKIPPED_SETS = {"LETTUCE", "BATTLEGROUNDS"}


def slim(cards: list[dict], locale: str, with_bg: bool = False) -> list[dict]:
    """Réduit le JSON AVANT écriture : le fichier complet coûte ~58 Mo à parser
    au démarrage (35 000 dicts d'une trentaine de clés) pour une dizaine de
    champs réellement utilisés — cf. budget RAM du cahier des charges."""
    if locale == "enUS":
        return [{"id": c["id"], "name": c["name"]} for c in cards if "id" in c]
    if not with_bg:
        cards = [c for c in cards if c.get("set") not in SKIPPED_SETS]
    slimmed = []
    for c in cards:
        row = {k: c[k] for k in KEPT if k in c}
        # dérivé du texte AVANT de le jeter : « pos » pèse quelques octets,
        # le texte complet doublerait le fichier et la RAM
        pos = deck_position(c.get("text"))
        if pos:
            row["pos"] = pos
        if is_imbued_hero_power(c):
            row["imbue"] = True
        slimmed.append(row)
    return slimmed


def fetch(locale: str, with_bg: bool = False, verbose: bool = True) -> int:
    """Télécharge et écrit une locale. Rend le nombre de cartes conservées."""
    dest = TARGETS[locale]
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = URL.format(locale=locale)
    if verbose:
        print(f"Téléchargement {url} …", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "cairn"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        empreinte = {
            "etag": resp.headers.get("ETag") or "",
            "last_modified": resp.headers.get("Last-Modified") or "",
        }
        cards = json.load(resp)
    textes = texts(cards, with_bg=with_bg)
    alertes = _reformulations(locale, textes)
    cards = slim(cards, locale, with_bg=with_bg)
    dest.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    TEXT_TARGETS[locale].write_text(
        json.dumps(textes, ensure_ascii=False), encoding="utf-8"
    )
    _write_meta({
        "locales": (meta().get("locales") or {}) | {locale: empreinte | {
            "cartes": len(cards), "le": time.strftime("%Y-%m-%d %H:%M"),
        }},
        # Les alertes s'accumulent jusqu'à ce qu'on les efface à la main
        # (`cairn-cards --vu`) : un patch traité à la va-vite se rappelle ainsi
        # au bon souvenir du prochain `cairn-doctor`. Une seule par carte, en
        # revanche — la même reformulation est vue une fois par locale, et la
        # question posée est la même : « ce code est-il encore juste ? »
        "alertes": _sans_doublons((meta().get("alertes") or []) + alertes),
    })
    if verbose:
        print(f"OK : {len(cards)} cartes → {dest}")
        print(f"     {len(textes)} textes → {TEXT_TARGETS[locale]}")
        for a in alertes:
            print(f"\n⚠ {a['id']} ({a['role']}) a été reformulée :\n"
                  f"    avant : {a['avant']}\n"
                  f"    après : {a['apres']}\n"
                  f"  Le JSON est à jour, mais la logique câblée pour cette "
                  f"carte est peut-être à revoir.", file=sys.stderr)
    return len(cards)


def update_if_stale(
    intervalle_h: float = INTERVALLE_H, force: bool = False, verbose: bool = True
) -> bool:
    """Retélécharge la base si HearthstoneJSON a publié une version plus récente.

    Appelée à chaque lancement de Cairn. Coût normal : une requête HEAD toutes
    les ``intervalle_h`` heures, et rien du tout entre-temps. Rend ``True`` si
    quelque chose a été retéléchargé.
    """
    horloge = time.time()
    if not force and horloge - (meta().get("verifie_le") or 0) < intervalle_h * 3600:
        return False
    etats = {loc: remote_changed(loc) for loc in TARGETS}
    if not any(etats.values()):
        # Rien à faire — mais on ne note le contrôle QUE s'il a abouti :
        # sinon un lancement hors ligne interdirait toute vérification
        # pendant douze heures.
        if None not in etats.values():
            _write_meta({"verifie_le": horloge})
        return False
    if verbose:
        print("Patch Hearthstone détecté : mise à jour de la base de cartes …",
              flush=True)
    for locale, change in etats.items():
        if change:
            fetch(locale, verbose=verbose)
    _write_meta({"verifie_le": horloge})
    return True


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    with_bg = "--with-bg" in argv          # garde Battlegrounds/Mercenaires

    if "--vu" in argv:                     # alertes de reformulation traitées
        _write_meta({"alertes": []})
        print("Alertes effacées.")
        return 0

    if "--check" in argv:                  # dit, sans rien télécharger
        for locale in TARGETS:
            etat = remote_changed(locale)
            dit = {True: "mise à jour disponible",
                   False: "à jour",
                   None: "indéterminé (réseau ?)"}[etat]
            print(f"{locale} : {dit}")
        return 0

    if "--auto" in argv:                   # ce que fait le lancement de Cairn
        return 0 if update_if_stale(force="--force" in argv) is not None else 1

    args = [a for a in argv if not a.startswith("-")]
    arg = args[0] if args else "all"
    for locale in (["frFR", "enUS"] if arg == "all" else [arg]):
        fetch(locale, with_bg=with_bg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
