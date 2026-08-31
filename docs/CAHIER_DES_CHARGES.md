# Cahier des charges — Cairn

> **Tracker Hearthstone natif Linux : léger, joli, et qui suit vraiment ce qui se passe dans le deck**
> Il lit les logs du jeu directement depuis le système de fichiers (zéro Wine côté tracker), affiche le deck en direct — y compris **ce qui y entre** (bombes, fléaux, transformations à la Rafaam) — et une **barre de compteurs contextuels** en haut de l'écran.

---

## 0. Fiche projet

| Champ | Valeur |
|---|---|
| **Nom de code** | Cairn (l'âtre = le foyer, *hearth*) |
| **Contexte** | Projet indépendant, écrit par un joueur quotidien sous Arch/KDE |
| **Domaine** | Parsing temps réel · machine à états · UI overlay Wayland · (bonus : introspection mémoire d'un process Wine) |
| **Machine cible** | Portable Linux modeste — i5 mobile, iGPU, 8 Go de RAM, KDE Wayland |
| **Motivation** | Firestone tourne sous Wine mais coûte ~1,5 Go de RAM (6 process Electron) → OOM kill de Hearthstone vécu le 31/07/2026. Un tracker natif fait le cœur du travail pour **< 200 Mo**. |
| **Cadre honnête** | Un **tracker de partie**, PAS une parité Firestone (pas de méta serveur, pas de simulateur BG) |
| **Statut** | **v1.0.0 publiée** — 385 tests, ~170 Mo de mémoire privée. Le détail des étapes qui y ont mené est conservé plus bas, à titre de journal. |

---

## 1. Contexte et problématique

Hearthstone tourne dans un prefix Wine/Proton (chez l'auteur : `~/Games/battle-net`, GE-Proton11-3 via umu/Lutris ; **le chemin n'est plus supposé** — il est détecté, cf. §5). Les trackers Windows (Firestone, HDT) doivent tourner *dans* Wine, avec le coût que ça implique : Firestone standalone = Electron complet émulé, ~1,5 Go de RAM, injection d'overlay fragile.

**L'angle décisif** : Hearthstone écrit tout ce qui se passe en partie dans des **fichiers texte accessibles nativement** :

```
<prefix>/drive_c/Program Files (x86)/Hearthstone/Logs/Hearthstone_<date>/
├── Power.log      ← chaque événement de jeu (tags, zones, entités) — LA source
├── Decks.log      ← noms + deckstrings de tous les decks du joueur
├── LoadingScreen.log ← mode de jeu (ranked, BG, arène…)
└── Hearthstone.log, Asset.log, …
```

Un tracker Linux natif lit ces fichiers en direct **sans toucher à Wine** (polling 0,5 s plutôt qu'inotify : plus fiable à travers Wine). Le prérequis — le fichier `log.config` qui active `Power.log` — est **écrit par Cairn lui-même** (`hs_setup.ensure_log_config`), dans le dossier utilisateur du prefix, dont le nom varie selon l'installateur (`steamuser` sous Proton, le nom de compte sous Lutris).

**Deux pièges découverts à l'usage, absents de toute documentation :**

1. **Hearthstone plafonne chaque journal à 10 Mo par session.** Au-delà il écrit « Truncating log… » puis **ferme le descripteur** (vérifié dans `/proc/<pid>/fd`). Sous Windows sa troncature réussit et le logger continue ; sous Wine elle échoue et le suivi meurt jusqu'au redémarrage du jeu. **Solution : la clé `FileSizeLimit.Int=-1` de `client.config`** (dossier d'installation du jeu), que posent aussi HDT et Firestone — d'où le fait qu'ils ne rencontrent jamais ce problème. Cairn l'écrit automatiquement. À ne PAS tenter : vider le fichier depuis l'extérieur ne réinitialise pas le décalage d'écriture de HS, qui reprend au même endroit et produit un fichier à trous de taille identique (mesuré : 6,7 Mo annoncés pour 20 Ko alloués).
2. **Les tags de l'adversaire sont écrits sous son vrai battletag**, alors que `PlayerName` le désigne « UNKNOWN HUMAN PLAYER » — sans rattrapage, tous ses changements d'état (dont « à qui est le tour ») sont silencieusement perdus.

**Le trou à prendre** : HDT et Firestone = Windows/Wine ; Arena Tracker = natif Linux mais UI datée et projet vieillissant. Aucun tracker Linux moderne, léger et beau n'existe.

---

## 2. Objectifs

### 2.1 Objectif général
Suivre une partie de Hearthstone en temps réel depuis les logs, avec une UI native discrète : **deck vivant** (sorties ET entrées) + **compteurs contextuels** en haut de l'écran.

### 2.2 Objectifs spécifiques
- **O1 — Deck vivant** : liste du deck avec cartes restantes, piochées, jouées, et probabilités de pioche.
- **O2 — Ce qui ENTRE dans le deck** *(demande centrale)* : toute carte ajoutée en cours de partie est affichée dans une section dédiée avec son origine — bombes du Dr Boum, fléaux DK, colifichets, cartes « rembobinées », etc. Cartes inconnues = « ? (ajoutée par X) ».
- **O3 — Détection des transformations de deck** *(l'exemple Rafaam)* : quand un effet **remplace** le deck (Méchant suprême Rafaam → légendaires aléatoires), le tracker bascule l'affichage : deck d'origine archivé, nouveau deck en mode « contenu inconnu, révélé au fil des pioches ».
- **O4 — Compteurs contextuels** *(demande centrale)* : **widgets flottants indépendants** (panneau de compteurs, pastilles de dégâts, secrets), **contextuels** — chaque compteur n'apparaît que si le deck/la partie le justifie.
- **O5 — Import de deck automatique** : lecture de `Decks.log` (deckstrings déjà en clair) + décodage du format deckstring. Aucune saisie manuelle.
- **O6 — Historique local** : chaque partie enregistrée (deck, adversaire, résultat, durée) dans une base SQLite. Winrates par deck.
- **O7 — Sobriété** : < 200 Mo de RAM, < 3 % CPU en partie, démarrage < 2 s.

### 2.3 Hors périmètre (assumé)
- Stats méta / winrates globaux (nécessite une infrastructure serveur → éventuel appel à l'API HSReplay en V3, jamais au cœur).
- Simulateur de combats Battlegrounds.
- Overlay *incrusté dans* la fenêtre du jeu (injection) : l'UI vit dans ses propres fenêtres, HS se joue en fenêtré sans bordure.
- Collection / succès / arène en V1.
- Tout ce qui écrit dans la mémoire du jeu ou automatise des actions — **lecture seule absolue** (ToS).

---

## 3. Positionnement

| Existant | Plateforme | Points forts | Limite pour ce besoin |
|---|---|---|---|
| Firestone standalone | Windows (marche sous Wine) | Très complet, méta, beau | ~1,5 Go RAM → OOM sur 8 Go |
| Hearthstone Deck Tracker | Windows | Référence du parsing | Wine + mono, lourd, UI WPF |
| Arena Tracker | **Linux natif** | Preuve que l'approche logs marche | UI datée, focalisé arène, peu maintenu |
| HSReplay (site) | Web | Stats | Pas de tracking live |
| **Cairn** | **Linux natif** | Léger, contextuel, KDE/Wayland | Périmètre volontairement réduit |

---

## 4. Fonctionnalités

### 4.1 MVP (V1)

**F1 — Watcher de logs**
Détection du dossier `Logs/Hearthstone_<date>` le plus récent (et des nouveaux en cours de session), suivi de `Power.log` en continu (inotify + lecture incrémentale), robuste aux rotations et aux relances du jeu.

**F2 — Parser Power.log → machine à états de partie**
Reconstruction de l'état : entités, zones (DECK / HAND / PLAY / GRAVEYARD / SETASIDE), tours, joueurs, à partir des blocs `GameState`/`PowerTaskList` (`FULL_ENTITY`, `SHOW_ENTITY`, `TAG_CHANGE`, `BLOCK_START/END`). C'est le cœur du projet — testé unitairement sur des Power.log réels archivés.

**F3 — Panneau deck (fenêtre latérale)**
- Liste du deck trié par coût, quantités restantes, cartes piochées grisées.
- **Section « ⤵ Entrées »** : cartes ajoutées au deck en cours de partie, avec origine et position connue/inconnue.
- **Gestion des transformations** : sur un effet de remplacement de deck (Rafaam & co), bandeau « Deck transformé par X », ancien deck repliable, nouveau deck alimenté par les révélations.
- **Section « Atlas de Godfrey »** *(ajout 08/2026)* : file des cartes surpiochées mises de côté par l'Atlas, numérotée dans l'ordre de retour en main et au coût réduit. Présente dans les deux panneaux — Azalina copie les débuts de partie adverses, donc on peut avoir son propre atlas. Même raison pour les compteurs à condition de victoire (Rafaam) : ils se calculent camp par camp, jamais « côté adverse » en dur.
- Probabilité de pioche au prochain tour (top-deck %).

**F4 — Compteurs (widgets flottants)**
Compteurs contextuels, activés automatiquement selon le deck détecté et les événements :

| Compteur | Déclencheur |
|---|---|
| Cartes ajoutées au deck | dès la 1ʳᵉ entrée (ex. bombes) |
| Cartes restantes / fatigue | toujours |
| Cadavres | classe Chevalier de la mort |
| Écoles de magie distinctes | carte qui s'en sert dans le deck |
| Fouilles (excavate) | carte fouille détectée |
| Combo/cartes jouées ce tour | classe Voleur |
| Dégâts des sorts (spell damage) | serviteur +sorts sur le board |
| Main adverse (nb cartes, origine) | toujours |

Architecture ouverte : un compteur = un petit module déclaratif (condition d'activation + source d'événements + rendu), pour en ajouter facilement.

**F5 — Suivi adversaire**
Cartes jouées (groupées, triées par coût), **cartes CONNUES dans sa main** avec la carte qui les a créées, taille de main, **cimetière**, et secrets posés avec la liste des candidats de sa classe (filtrée au format en cours et aux secrets déjà dévoilés ; barrables d'un clic).

**F6 — Historique**
SQLite : deck joué, classe adverse, résultat, durée, date, mode. Winrate par deck et par classe, filtrage par deck, **saisie manuelle** d'une partie, **archivage** d'un deck (repartir de zéro sans perdre les données) et suppression d'une partie ou d'un deck, sous confirmation.

**F7 — Installation autonome**
Détection du prefix Wine/Proton (Lutris, Steam/Proton y compris bibliothèques secondaires, Heroic, Bottles, PlayOnLinux, wine nu), écriture du `log.config`, diagnostic `tools/doctor.py`, bascule FR/EN (interface, noms de cartes et rendus d'images).

### 4.2 V2
- Secrets : **élimination automatique** des candidats selon les actions non déclenchées (comme HDT). Demande une table de déclencheurs par carte, à valider sur de vraies parties — une élimination fausse est pire que pas d'élimination. La V1 se limite aux candidats + barrage manuel.
- Battlegrounds : héros proposés, compos adverses vues au dernier combat, triplets.
- Mulligan helper statique (courbe de mana, conseils simples hors méta).
- Export/partage de l'historique.

### 4.2 bis — Reste à faire avant publication GitHub
- `pyproject.toml`, `cairn.desktop` + icône, README avec captures et installation.
- Repli documenté hors KDE (les règles de fenêtres au-dessus du jeu sont KWin).
- Premier lancement guidé : téléchargement de la base de cartes avec progression.

### 4.2 ter — Passe « niveau Firestone » (04/08/2026)

Comparaison écran par écran avec Firestone tournant sous Wine sur la même
machine. Le verdict était net : **l'écart n'était pas fonctionnel mais visuel**
— Cairn tenait déjà des choses que Firestone n'a pas (viviers de résurrection
exacts, chances de pioche, aide aux secrets, atlas de Godfrey), mais ses listes
étaient des lignes de tableur là où Firestone montre des cartes.

Livré :

- **Illustration en fond de chaque ligne** — tuiles `art.hearthstonejson.com/v1/tiles/`,
  cache disque dans `~/.cache/cairn/tiles` (`tiles.py` sans Qt + `ui/tile_cache.py`
  pour la file de téléchargement à 4 fils). Le deck entier est préchargé dès la
  première vue ; à la deuxième partie tout est local, donc instantané et hors ligne.
  Un dégradé horizontal noie l'art vers la gauche : le nom reste lisible.
  Coût mesuré : +0 Mo notable, 169 Mo pour les 4 fenêtres (budget : 200).
- **Découpage par zone** — *en deck / en main / ailleurs*, dérivé des zones des
  entités (même vérité que le compte du dos du deck) plutôt que des événements,
  donc juste après une transformation ou un vol. Sections repliables d'un clic.
- **Chrono par tour et par joueur** — temps du tour en cours et réflexion cumulée
  de chaque camp, mesurées sur les horodatages du journal (donc justes en rejeu).
- **Familles à cocher** (`families.py`) — les membres sont dérivés de la base
  par motif d'identifiant (`TIME_005(t[1-9])?` = les dix Rafaam), jamais listés
  à la main : une extension qui ajoute une variante l'ajoute toute seule. Rendu
  par `ListView.section`, donc le pont n'a pas à savoir combien de familles
  existent. Vérifié sur archive : l'adversaire du 02/08 avait bien posé 10/10.
- **Haut et fond du deck** — Hearthstone **ne journalise pas l'ordre du deck** :
  toute carte qui y entre reçoit `ZONE_POSITION value=0` (vérifié sur les quatre
  fixtures). La position n'est donc connue que par l'effet qui l'a posée, comme
  chez HDT et Firestone. Plutôt qu'une liste d'identifiants à maintenir, le
  drapeau est **dérivé du texte des cartes au téléchargement** (`cards_fetch.
  deck_position`) et seul un drapeau de quelques octets est conservé : 27 cartes
  « fond », 10 cartes « haut », base inchangée à 3,9 Mo, mise à jour automatique
  à chaque patch. *Limite assumée* : l'information devient fausse si un effet
  mélange le deck ensuite — même limite que la concurrence.
- **Panneaux défilables** — conséquence directe des sections ajoutées : le contenu
  dépasse désormais la hauteur d'écran allouée. Sans `Flickable`, la fin de la
  liste devenait inatteignable. Le déplacement de fenêtre a migré dans l'en-tête,
  qui ne peut pas entrer en conflit avec le défilement.

### 4.3 V3+ — Module « MindVision natif » *(le bonus cyber)*
Lecture mémoire du process `Hearthstone.exe` **depuis Linux** : `process_vm_readv` sur le PID Wine, localisation du runtime Mono/Unity, parsing des structures managées à distance (ce que fait `OverwolfUnitySpy.dll`, réécrit côté Linux). Débloque : contenu exact des découvertes, deck adverse prédit, état complet du board BG. Projet de reverse à part entière, découplé du tracker (le tracker fonctionne à 100 % sans). Lecture seule stricte.

---

## 5. Architecture technique

```
┌────────────────────────────── Cairn (1 process) ──────────────────────────────┐
│                                                                              │
│  log-watcher ──► parser Power.log ──► game-state engine ──► event bus        │
│  (inotify)       (ligne → events)     (entités/zones)        │               │
│                                                              ▼               │
│  decks-reader (Decks.log → deckstrings décodés)      ┌── UI ────────────┐    │
│  cards-db (HearthstoneJSON frFR, cache local)        │ barre compteurs  │    │
│  history (SQLite)                                    │ panneau deck     │    │
│                                                      │ fenêtre stats    │    │
│                                                      └──────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Choix de stack (recommandation, à trancher en phase 0)
- **Recommandé : Python 3.12 + PySide6/QML** — cohérent avec les deux autres projets du portfolio, UI soignée rapide à produire, RAM réaliste ~120-180 Mo. Le parser reste du pur Python testable sans UI.
- **Option ambitieuse : Rust + Slint** — RAM 30-60 Mo, gros plus portfolio, mais coût d'apprentissage. À ne choisir que si l'envie d'apprendre Rust est là.
- La phase 0 tranche avec un prototype de parser dans chaque… ou directement Python si on veut jouer vite.

### UI sous KDE Wayland (point sensible)
- Fenêtres **sans bordure, keep-above**, positionnées par **règles de fenêtre KWin** (fiables, natives KDE). Pas d'injection dans le jeu.
- Hearthstone en **fenêtré sans bordure** (déjà le mode conseillé sous Wine).
- Piste V2 : LayerShellQt pour ancrer le bandeau comme un vrai panneau.
- Thème sombre par défaut, opacité réglable, échelle réglable.

### Données cartes
- **HearthstoneJSON** (`cards.collectible.json`, locale **frFR** — le jeu est en français) téléchargé et mis en cache ; rafraîchi à chaque patch.
- Images de cartes via le CDN HearthstoneJSON, cache disque avec plafond.

---

## 6. Détail du cas central : « ce qui rentre dans le deck »

Trois mécanismes distincts, tous gérés par le game-state engine :

1. **Ajout simple** (bombes du Boum, fléaux, colifichets…) : `FULL_ENTITY`/`SHOW_ENTITY` avec `ZONE=DECK` en cours de partie → la carte apparaît dans « Entrées » avec son créateur (`CREATOR`-tag). Si la carte est cachée, affichage « ? ajoutée par <carte> » — et résolution rétroactive quand elle est révélée à la pioche.
2. **Transformation totale** (Méchant suprême Rafaam) : rafale de changements de zone/remplacements sur toutes les entités du deck → détection par heuristique (N entités du deck remplacées dans le même bloc) **+** règle dédiée par carte connue. Bascule d'affichage (cf. F3).
3. **Mélanges retour** (carte renvoyée dans le deck) : distinction visuelle entre « revient » (déjà connue) et « entre » (nouvelle).

Une table de règles par carte (`card_rules.py` : id carte → comportement) couvre les cas ambigus, extensible à chaque extension du jeu.

---

## 7. Maquette (bandeau + panneau)

```
─────────────────────────── haut de l'écran ───────────────────────────
│ 🂠 23 restantes │ ⤵ 3 entrées │ ☠ 12 cadavres │ ✋ adv : 7 (2 créées) │
───────────────────────────────────────────────────────────────────────

┌─ Cairn — bingo bis ─────────────┐
│ 1 ● Miroir magique          ×2 │
│ 2 ● Attaque mentale         ×1 │   grisé = pioché
│ 3 ● Vol de pensées          ×2 │
│ …                              │
│ ⤵ ENTRÉES ─────────────────────│
│ 🂠 ? — ajoutée par Augure vil   │
│ 💣 Bombe — Dr Boum          ×2 │
│ ────────────────────────────── │
│ top-deck : Bombe 9 %           │
└────────────────────────────────┘
```

---

## 8. Contraintes

| Contrainte | Cible |
|---|---|
| RAM (RSS totale) | **< 200 Mo** (objectif 150) |
| CPU en partie | < 3 % d'un cœur (parsing incrémental, pas de polling) |
| Démarrage | < 2 s |
| Plateforme | Arch Linux, KDE Plasma Wayland (Xwayland pour le jeu) |
| Langue | UI français, cartes frFR |
| Légal | Lecture de fichiers et de mémoire **en lecture seule** ; aucune automatisation de jeu ; pas de données envoyées à un serveur |

---

## 9. Phases

| Phase | Contenu | Critère de sortie |
|---|---|---|
| **0 — Fondations** (2-3 j) | Choix stack ; jouer 2-3 parties pour archiver des `Power.log` réels ; squelette repo + tests | 3 Power.log de référence archivés dans `data/fixtures/` |
| **1 — Parser** (1 sem) | F1 + F2 ; rejouer un Power.log archivé et reconstruire la partie sans UI | tests verts sur les fixtures, état final correct |
| **2 — MVP jouable** (1-2 sem) | F3 + F5 minimal + import Decks.log | une vraie partie suivie en live, deck + entrées corrects |
| **3 — Compteurs & finitions** (1 sem) | F4, thème, règles KWin, F6 | le bandeau vit tout seul pendant une session ranked |
| **4 — Publiable** (02/08/2026) | F7, main adverse connue, cimetière, secrets candidats, probabilité de pioche, FR/EN, licence MIT | s'installe et se diagnostique sur une machine tierce |
| **5 — V2/V3** | secrets dynamiques, BG, MindVision natif | à la carte |

---

## 10. Risques

| Risque | Impact | Parade |
|---|---|---|
| Format Power.log change à un patch HS | parser cassé | fixtures versionnées, parsing défensif, HDT/Firestone open source comme référence de correctifs |
| Overlay au-dessus du jeu plein écran Wayland | bandeau invisible | HS fenêtré sans bordure (documenté dès le README) |
| Cas de deck tordus (Rafaam, Augure, tourists…) | affichage faux | table de règles par carte + section « Entrées » qui assume l'inconnu (« ? ») plutôt que d'inventer |
| Motivation post-MVP | projet mort | MVP volontairement petit (phase 2 = déjà utilisable au quotidien) |
| 8 Go de RAM d'ici la barrette | même le natif gêne | budget 200 Mo = ~13 % de Firestone ; jouable même avant la barrette |

---

## 11. Critères d'acceptation du MVP

1. Je lance HS + Cairn, je joue une partie ranked : le deck s'affiche seul (import `Decks.log`), les pioches se grisent en direct.
2. Le Dr Boum adverse mélange des bombes dans mon deck → elles apparaissent dans « Entrées » avec le bon compte, et le compteur « ⤵ entrées » s'affiche dans le bandeau.
3. Je joue Méchant suprême Rafaam → le panneau bascule en « deck transformé », sans afficher de fausses certitudes.
4. `ps` montre < 200 Mo RSS pour tout Cairn pendant la partie.
5. La partie terminée est dans l'historique avec le bon résultat.
