# Cairn vs Firestone — ce qui manque encore

Établi le 05/08/2026 à partir des captures de Firestone en partie et de l'état réel du code.
Chaque écart est vérifié : soit la donnée existe déjà dans les journaux (mesurée sur les parties
archivées), soit elle demande autre chose — et c'est dit.

## Déjà au niveau (ne rien refaire)

Liste du deck avec restants et probabilité de pioche · entrées de deck (bombes, Azalina) ·
**fond et haut de deck** · ma main · cimetières des deux camps · atlas de Godfrey ·
candidats secrets avec élimination manuelle · cartes jouées par l'adversaire ·
**main adverse avec tour d'arrivée et origine** · compteurs contextuels · pastilles de dégâts ·
chrono de tour et temps de réflexion par camp · pools de résurrection · familles à cocher ·
historique et statistiques par classe et par deck · **bilan face à la classe adverse dans
l'en-tête** (« 5-3 contre Chasseur ») · aperçu de carte au survol.

Sur trois points Cairn est devant : les entrées de deck en cours de partie, les pools de
résurrection en direct, et l'empreinte mémoire.

---

> **Fait le 05/08/2026** : points 1, 2, 3, 5, 6, 7 et 8 livrés (219 tests verts).
> **Fait le 14/08/2026** : point 4 livré (pastilles flottantes), plus cinq
> corrections nées de l'usage — voir « Retours d'usage du 14/08/2026 » en bas.
> 250 tests verts.

## P1 — écarts réels, la donnée est déjà là

### 1. Combien de cartes reste-t-il à l'adversaire — ✅ FAIT

Firestone l'affiche en permanence ; Cairn ne le montre nulle part. C'est l'information qui dit
quand la **fatigue adverse** arrive, et elle décide des fins de partie longues.

*Donnée* : disponible. Mesuré sur les parties archivées — entre 0 et 21 cartes en zone DECK côté
adversaire, à tout instant.
*Coût* : ~1 h. Un compteur de plus dans `counters.py`, symétrique de `counter_remaining`.

### 2. Winrate du deck dans l'en-tête du panneau — ✅ FAIT

Firestone affiche « Deck's winrate 71.4 % — 5/2 » en haut. Cairn a les chiffres, mais seulement
dans le launcher : en partie on ne voit que le bilan face à la classe.

*Donnée* : disponible, `History` la calcule déjà (`deckStatsModel`).
*Coût* : ~1 h. Une propriété de plus sur le pont, une ligne dans l'en-tête.

### 3. Section « effets en jeu » — ✅ FAIT

Firestone a deux sections, *Global effects* et *Current effects*, qui listent ce qui modifie la
partie en permanence (Azalina, Godfrey, Rafaam murloc, Vereesa…). Cairn n'a rien d'équivalent :
on découvre l'effet quand il se déclenche.

*Donnée* : disponible. Mesuré sur une partie réelle — 12 enchantements en jeu à la fin, dont
« Atlas de Godfrey » des **deux** côtés et « Préparation ».
*Piège évité* : la liste blanche redoutée n'a pas été nécessaire. Hearthstone attache chaque
enchantement à une entité (tag ``ATTACHED``) — collé à un serviteur c'est un buff local, collé au
JOUEUR ou au HÉROS c'est un effet global. Mesuré sur 68 parties : 287 enchantements de serviteur
contre 109 globaux, 18 cartes distinctes, 0 à 3 lignes par partie. **Critère structurel, rien à
maintenir à la prochaine extension.**

### 4. Pastilles de tour EN SURIMPRESSION de la main adverse — ✅ FAIT le 14/08/2026

La version panneau a vécu une semaine et a été jugée insuffisante : dix lignes dont neuf disaient
« ? carte cachée », loin de l'endroit où le regard est déjà. Elle est remplacée par
`OppHandDots.qml` — une pastille par carte tenue, en arc de cercle comme l'éventail du jeu, avec
le tour d'arrivée (« M » = gardée au mulligan), 🎁 pour une carte créée, et l'illustration quand
l'identité est connue. Survol : la carte, ou à défaut celle qui l'a créée.

*Positionnement* : **pas de calcul de géométrie**. Caler un widget sur l'éventail de HS aurait
demandé de modéliser sa mise en page (résolution, taille de main, mode d'affichage) pour un
alignement qui aurait dérivé à la première mise à jour du jeu. Le bandeau se cale **une fois à la
souris** et KWin retient (règle `cairn-pos-main`, mode Remember), comme les cinq autres widgets
flottants. Largeur FIXE de dix emplacements — la main maximale de HS — pour que le bandeau reste
centré au lieu de pousser vers la droite à chaque pioche.

*Ordre* : tag `ZONE_POSITION`, pas l'ordre d'arrivée. Une pastille doit désigner LA carte qui est
au-dessus d'elle.

---

## P2 — confort

### 5. Compteurs en deux colonnes moi / adversaire — ✅ FAIT

Fait : une ligne par compteur, deux colonnes « moi | adv ». Le camp se lit par la POSITION au
lieu d'un préfixe répété à chaque ligne, et le panneau a rétréci de 210×183 à 186×136.
Le regroupement se fait en Python (``_counter_rows``), pas en QML où il serait illisible ; la
table ``_PAIRS`` de ``counters.py`` dit quelle ligne partage quels camps.

### 6. Chrono flottant — ✅ FAIT

Le chrono de tour est aujourd'hui coincé en bas du panneau deck. Firestone en fait un widget
déplaçable. L'infrastructure existe maintenant (`FloatingWindow`), donc c'est presque gratuit.
*Coût* : ~2 h.

### 7. Copier le deckcode — ✅ FAIT

Firestone a des boutons d'export dans l'en-tête. Cairn décode déjà les deckcodes ; le bouton
« copier » manque.
*Coût* : ~1 h.

### 8. Cartes identifiées restant dans le deck adverse — ✅ FAIT

Quand un effet révèle une carte du deck d'en face, Cairn l'oublie.
*Donnée* : maigre mais réelle — **17 parties sur 38** du corpus en contiennent au moins une
(Verr'Minh, Commandante Beatrix, Lardeur…). Deux tests interdisent qu'une carte cachée s'y glisse
déguisée en carte connue.

---

## Cosmétique

- **Icônes d'origine au lieu de « ← Nom »** : Firestone marque les cartes créées d'une petite
  icône. Cairn écrit le nom, plus explicite mais qui mange la largeur et se fait tronquer
  (« ← Briseuse d'âm… »). Une icône + infobulle libérerait ~80 px.
- **Infobulle « type de carte »** au survol. L'aperçu de Cairn montre déjà l'illustration, la
  probabilité de pioche et le pool de résurrection — on est plutôt devant.

---

## Hors périmètre — assumé, pas oublié

Ces points sont écartés par le cahier des charges de Cairn (§4.2, « hors périmètre assumé ») :

- **Battlegrounds**, **Arène**, **Duels**.
- **Winrates communautaires** et **aide au mulligan méta** : ils exigent un serveur de données.
  Firestone en vit ; Cairn est un tracker local sans serveur.
- **Reconstruction complète du deck adverse par archétype** : même raison. Sans base méta, la
  reconstruction se réduirait à « 15 cartes inconnues » — mesuré : **0 carte identifiée** en zone
  DECK adverse sur la plupart des parties. Le point 8 ci-dessus en est la version honnête.
- **Élimination automatique des secrets** : refusée en V1 et toujours refusée — une élimination
  fausse ferait jouer *dans* un secret, ce qui est pire que pas d'élimination.

---

## Retours d'usage du 14/08/2026

Six semaines de parties réelles, six corrections. Toutes viennent du même constat : **une
information qui arrive au moment où la carte est jouée arrive trop tard.**

1. **Confrontation des Tol'vir** (`CATA_560`, Chasseur) rejoue toutes les cartes à (1) jouées
   depuis le début. Cairn tient donc la liste des cartes à (1) des DEUX camps, affichée dès qu'un
   camp est Chasseur ou possède la carte (vol, Découverte, Azalina) — pas quand elle tombe.
2. **Fauteuse de troubles du Lotus** : le décompte des cartes à (2) démarre à l'ARRIVÉE de la
   copie quand elle a été volée ou découverte (« tant que cette carte est dans votre main ou
   votre deck »), et le compteur s'affiche face à tout Voleur. Le coût compté reste celui
   **imprimé** — mesuré, cf. `deck_view.plays_costing`.
3. **Effets en jeu** : le survol montre la carte SOURCE de l'effet (tag `CREATOR`) et son texte.
   Un enchantement n'a aucun rendu d'image et son texte propre n'apprend rien (« PV augmentés. »).
   Les textes de cartes vivent dans un fichier séparé, chargé au premier survol.
4. **Entrées de deck** : elles sont dans la LISTE DU DECK, marquées d'un cadeau, au lieu d'une
   section « ENTRÉES » qu'il fallait consulter en plus.
5. **Secrets** : les candidats suivent la classe du secret POSÉ (tag `CLASS` de l'entité), pas
   celle du héros d'en face — un Chasseur peut poser un secret de Mage.
6. **Main adverse** : point 4 ci-dessus.

## Ce qui reste

Rien de la liste initiale. Les prochains écarts connus sont ceux de la V2 (Battlegrounds,
mulligan hors méta, export de l'historique) — hors périmètre assumé du cahier des charges.
