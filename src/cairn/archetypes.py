"""Reconnaître l'archétype du deck adverse à partir des cartes qu'il a jouées.

Pourquoi ça existe. Un taux de victoire par CLASSE mélange des decks qui n'ont
rien à voir. Mesuré sur les archives : face au Démoniste, 39 % en moyenne — mais
**29 % contre un Rafaam et 75 % sans**. La moyenne par classe cachait donc deux
matchups opposés, et c'est exactement l'information qui manque partout ailleurs.

Ce que les autres trackers ne font pas. Firestone et HSReplay donnent des
statistiques par archétype tirées de LEUR corpus, pas du tien. Ici tout vient de
tes propres parties : « mon » winrate contre ce deck-là, à mon palier.

## Le choix de nommage, et pourquoi

**L'étiquette est la carte-signature, jamais un nom d'archétype du méta.**
« Démoniste · Rafaam », pas « Rafaamlock ». Trois raisons :

1. C'est vérifiable. L'étiquette dit littéralement ce qui a été vu en jeu.
2. Ça ne périme pas. Les noms de la communauté changent d'un mois à l'autre et
   d'une langue à l'autre ; une carte, non.
3. Ça ne demande aucune veille. Ajouter un archétype = ajouter une ligne à
   ``SIGNATURES``, sans avoir à trancher comment « on » appelle ce deck.

## Les limites, assumées

- **Une signature non vue = archétype inconnu**, jamais deviné. Un adversaire qui
  concède au tour 2 n'a rien montré : il compte dans la classe, pas dans un
  archétype. Prétendre le contraire fausserait précisément le chiffre qu'on
  cherche.
- **Les cartes CRÉÉES ne comptent pas.** Un Rafaam obtenu par Découverte ne fait
  pas de son porteur un deck Rafaam. Seules les cartes venues de son deck valent
  preuve — d'où le filtre sur le créateur.
- L'ordre dans ``SIGNATURES`` fait la priorité : la première signature trouvée
  gagne. Les paquets les plus spécifiques sont donc placés en premier.
"""

from __future__ import annotations

from .cards_db import CardsDb
from .game_state import Game, Play

# classe → [(étiquette, {card_id, …}), …], du plus spécifique au plus général.
#
# Les identifiants sont stables et non traduits ; les noms en commentaire sont
# là pour la relecture. Cette table est SEEDÉE sur les parties réellement
# archivées (août 2026) — elle n'essaie pas de couvrir le méta entier, seulement
# ce qu'on a vu. Un archétype absent d'ici ressort « inconnu », ce qui est
# préférable à une étiquette inventée.
SIGNATURES: dict[str, list[tuple[str, set[str]]]] = {
    "WARLOCK": [
        ("Rafaam", {
            "TIME_005",   # Rafaam, le voleur de temps
            "JAIL_509",   # Godfrey, le traître
        }),
        ("Malédictions", {
            "TLC_451",    # Catacombes maudites
            "CATA_496",   # Chaînes maudites
            "JAIL_511",   # Flèche de la Solitude
        }),
    ],
    "PRIEST": [
        ("Azalina", {"JAIL_430"}),          # Briseuse d'âme Azalina — le miroir
        ("Medivh", {"TIME_890", "CATA_308"}),
    ],
    "HUNTER": [
        ("Arcanes", {"JAIL_881"}),          # Fil-piège à arcanes
        ("Bêtes", {"TLC_830", "TIME_609"}),  # La chaîne alimentaire, Sylvanas
        ("Tol'vir", {"CATA_560"}),
    ],
    "DRUID": [
        ("Araignées", {"JAIL_872"}),        # Chevaucheuse d'araignée
        ("Amirdrassil", {"FIR_907"}),
    ],
    "DEATHKNIGHT": [
        ("Pterreurdactyle", {"TLC_436"}),
        ("Goules", {"JAIL_440"}),
    ],
}

INCONNU = ""  # jamais None : simplifie le passage en base et au QML


def _creator_tag(game: Game, entity_id: int) -> bool:
    """La carte a-t-elle été ENGENDRÉE par un effet plutôt que tirée du deck ?"""
    ent = game.entities.get(entity_id)
    return bool(ent and ent.creator_entity_id)


def deck_card_ids(game: Game, player_id: int | None) -> set[str]:
    """Cartes qu'un camp a jouées ET qui venaient de son deck.

    Le filtre sur le créateur est le cœur de la fiabilité : sans lui, un Rafaam
    volé par un Prêtre ferait passer ce Prêtre pour un Démoniste Rafaam.
    """
    if player_id is None:
        return set()
    vues: set[str] = set()
    for ev in game.events:
        if not isinstance(ev, Play) or ev.player_id != player_id or not ev.card_id:
            continue
        if _creator_tag(game, ev.entity_id):
            continue
        vues.add(ev.card_id)
    return vues


def detect(game: Game, db: CardsDb, player_id: int | None, klass: str | None,
           refs=None) -> str:
    """Étiquette d'archétype, ou ``""`` si rien de reconnaissable n'a été montré.

    Deux méthodes, dans cet ordre :

    1. **Listes de référence** collées par l'utilisateur (``deck_refs``), quand
       il y en a. Elles comparent TOUT ce qu'on a vu sortir de son deck, donc
       elles reconnaissent des parties où aucune carte-signature n'est tombée.
    2. **Signatures câblées** (``SIGNATURES``) en repli : elles ne demandent
       qu'une carte, ce qui sauve les parties où l'on a très peu vu.

    L'ordre compte : une liste complète est une preuve plus solide qu'une carte
    isolée, qui peut appartenir à plusieurs decks de la même classe.
    """
    if not klass:
        return INCONNU
    jouees = deck_card_ids(game, player_id)
    if not jouees:
        return INCONNU
    if refs is not None:
        nom, _score = refs.match(jouees, klass, db)
        if nom:
            return nom
        # Dès qu'une classe a des listes de référence, on NE retombe PAS sur
        # les signatures pour elle. Sinon le même deck porte deux noms selon ce
        # qu'on a vu — « Rafaam » quand seule la signature tombe, « XL
        # Rafaamlock » quand la liste correspond — et les statistiques se
        # scindent en deux lignes qu'on ne peut plus additionner.
        if refs.for_class(klass):
            return INCONNU
    for etiquette, signatures in SIGNATURES.get(klass, ()):
        if jouees & signatures:
            return etiquette
    return INCONNU


def label(klass: str | None, archetype: str, class_label: str) -> str:
    """« Démoniste · Rafaam », ou « Démoniste » quand rien n'a été reconnu."""
    return f"{class_label} · {archetype}" if archetype else class_label


def slot(klass: str | None, archetype: str) -> int:
    """Indice de teinte STABLE pour un archétype, indépendant de son rang.

    La couleur doit suivre l'entité, jamais son classement : sinon « Rafaam »
    change de teinte le jour où il passe devant « Malédictions » en nombre de
    parties, et deux captures d'écran prises à un mois d'écart ne se comparent
    plus. On prend donc l'ordre de déclaration dans ``SIGNATURES``, qui ne bouge
    pas ; un archétype inconnu vaut -1 et se peint en gris.
    """
    if not archetype or not klass:
        return -1
    for i, (etiquette, _) in enumerate(SIGNATURES.get(klass, [])):
        if etiquette == archetype:
            return i
    # Liste de référence : pas d'ordre déclaré, donc une empreinte du NOM.
    # Stable par construction — le même nom donne toujours la même teinte,
    # quel que soit son rang ou le nombre de listes.
    return 2 + (sum(ord(c) for c in archetype) % 3)
