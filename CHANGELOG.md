# Journal des versions

Les versions suivent [SemVer](https://semver.org/lang/fr/). Ce fichier dit ce qui
change **pour qui utilise Cairn** ; le détail des décisions est dans
[`docs/CAHIER_DES_CHARGES.md`](docs/CAHIER_DES_CHARGES.md).

## [Unreleased]

### Interface en chinois (zhCN)

- Troisième langue d'interface : **中文**. Le sélecteur du launcher passe de
  `FR | EN` à `FR | EN | 中`, et `"language": "zh"` est accepté dans
  `~/.config/cairn/config.json`.
- Tout suit : libellés, compteurs, noms de classes, ligues, fiches d'add-ons,
  noms de cartes et textes de règles (HearthstoneJSON `zhCN`), et le rendu des
  cartes au survol.
- La base principale reste le **frFR** : c'est la seule qui porte les mécaniques,
  `races`, `pos` et `imbue`. Comme l'anglais, le chinois n'ajoute qu'une table
  `id → nom` (`cards.zhCN.json`) et un fichier de textes
  (`cards.text.zhCN.json`), chargés à la demande. Repli sur le français quand
  une carte manque — cf. `CardsDb.localized_name` et `CardsDb.text`.
- `cairn-cards` télécharge désormais les trois locales, y compris sur une
  première installation (`app.ensure_cards` boucle sur `cards_fetch.TARGETS`
  au lieu de nommer frFR et enUS en dur). `cairn-doctor` contrôle aussi les
  noms chinois.
- Terminologie alignée sur les noms officiels du jeu : « 潜行者 » (Voleur),
  « 灌注 » (Empreint), « 亡语 » (Râle d'agonie), « 高弗雷 » (Godfrey).

## [1.0.4] — 2026-10-01

### Versions natives de Hearthstone (issue #2)

- Nouvelle variable `CAIRN_HS_LOGS` (et clé de configuration `hs_logs`) : elle vise
  directement le dossier `Logs/` du jeu, sans prefix Wine. Pour les portages natifs
  comme hearthstone-linux-gui, Bottles ou les montages exotiques.
- Nouveau réglage « Vérifier que Hearthstone est lancé », à couper pour ces versions
  natives : sans `Hearthstone.exe`, le jeu n'était jamais détecté et les panneaux
  restaient cachés.
- `cairn-doctor` fonctionne sans prefix au lieu de sortir en erreur.
- Le message « Hearthstone introuvable » mentionne `CAIRN_HS_LOGS`.

### Suivi de partie

- **Secrets en double en Wild** (issue #3) : chaque secret apparaissait une fois par
  réimpression (Barrière de glace trois fois). Il n'apparaît plus qu'une fois, les
  cartes du format Classique sont exclues du Wild, et les exemplaires déjà joués
  sont comptés quelle que soit leur version. Les secrets Paladin et Voleur étaient
  aussi en double en Standard.
- **Cartes piochées** (issue #4) : nouveau réglage « Masquer les cartes piochées » pour
  retirer de la liste une carte dont le dernier exemplaire a quitté le deck, au lieu
  de la griser. Désactivé par défaut.

### Installation

- KDE hors Arch (Fedora…) : `install.sh` ne rechargeait pas le script KWin
  `cairn-follow`, faute de trouver `qdbus6`. Il essaie désormais tous les clients
  D-Bus, et demande de fermer la session si aucun n'aboutit au lieu d'annoncer une
  réussite.

## [1.0.3] — 2026-09-15

### Double écran (issue #1)

- Les panneaux et widgets s'ouvrent désormais **sur l'écran de Hearthstone**, à la même
  place relative, et le suivent s'il change d'écran. Sous Wayland, une application ne
  choisit pas son écran : c'est le script KWin `cairn-follow` qui s'en charge.
- Les **aperçus de cartes** se collent à leur panneau réel, du côté prévu (de l'autre
  s'il n'y a pas la place), au lieu d'une position fixe. Ça sert aussi avec un seul
  écran : un aperçu suit maintenant un panneau qu'on a déplacé.
- Pour garder ses panneaux sur un autre écran que le jeu :
  `kwriteconfig6 --file kwinrc --group Script-cairn-follow --key suivreEcranDeHearthstone false`.
- `install.sh` recharge le script KWin : une mise à jour prend effet sans fermer la session.

### Suivi de partie

- **Reconnexion** : après une déconnexion, Hearthstone réécrit toute la partie comme si
  elle commençait. Cairn la reconnaît (même graine de partie) et reprend là où il en
  était, au lieu de repartir d'un deck intact au milieu de la partie.
- Une partie coupée par une déconnexion ne laisse plus ses panneaux flotter sur le menu.
- **Choix manuel du deck** d'un clic sur le titre du panneau, quand la déduction ne
  tranche pas.
- Panneau du deck : section « mes cartes jouées », et « Ma main » masquable à part.

### Statistiques

- Forme des victoires et des défaites par deck (manches et durée moyennes), dans
  l'infobulle.
- Les parties d'une session qui franchit minuit sont datées du bon jour.

### Divers

- Pseudonymisation des parties partagées par blocs : l'interface ne gèle plus
  (1150 ms → 21 ms).
- Lancer Cairn une seconde fois ne réveille plus que le launcher.
- Le numéro de version envoyé avec les parties partagées était resté à `0.0.1` : il suit
  désormais celui du paquet.

## [1.0.2] — 2026-09-01

- Règles KWin : chemins système, pour une installation par paquet ; premier PKGBUILD.

## [1.0.1] — 2026-09-01

- Les parties sans deck sont traversées sans être analysées : démarrage environ 10 fois
  plus fluide.
- README : capture en jeu en tête.

## [1.0.0] — 2026-08-30

Première version publique. Un tracker Hearthstone **natif Linux** : il lit les journaux
que le jeu écrit lui-même depuis le prefix Wine, sans second prefix, sans injection et
sans lecture mémoire. 386 tests, mesuré à ~170 Mo de mémoire privée.

### Suivi de partie

- Deck en direct : cartes restantes, piochées, probabilité de pioche, et **ce qui entre
  dans le deck en cours de partie** (bombes, fléaux, cadeaux de Rafaam, copies d'Azalina).
- Haut et fond de deck déduits du **texte des cartes**, sans liste à maintenir.
- Compteurs contextuels et symétriques : ils n'apparaissent que si la carte qui les
  justifie a été vue, ou si la classe adverse peut la jouer.
- Main adverse (tour d'arrivée et origine de chaque carte), candidats secrets de la
  classe du secret posé, pools de résurrection réels au survol, file de l'Atlas de
  Godfrey des deux côtés.
- Chrono de partie et de tour, temps de réflexion par joueur, dégâts possibles de chaque
  camp — mal d'invocation compris.
- **Mode spectateur** : les parties regardées sont affichées mais **jamais enregistrées**,
  sinon elles fausseraient les winrates.

### Statistiques

- Historique local (SQLite), winrates par deck et par classe, import automatique des
  decks depuis `Decks.log`.
- **Rang déclaré** : Hearthstone ne l'écrit dans aucun journal (les autres trackers le
  lisent dans la mémoire du jeu), il est donc saisi à la main dans le launcher — ligue et
  palier 10 → 1, la Légende sans palier — et joint aux métadonnées des parties partagées,
  où il conditionne toute lecture sérieuse du corpus.
- **Winrate par archétype adverse** : les listes de référence collées par l'utilisateur
  (codes de deck) d'abord, les cartes-signatures câblées en repli. 82 % des parties
  archivées étiquetées, 0 % de faux positifs sur 6 000 tirages simulés. Une carte créée
  ne prouve jamais un archétype ; sans preuve, l'étiquette reste « inconnu ».

### Les deux obstacles Linux, résolus

- **Plafond de 10 Mo des journaux** : au-delà, Hearthstone ferme le descripteur et le
  suivi devient définitivement aveugle sous Wine. Cairn pose `FileSizeLimit.Int=-1` dans
  le `client.config` du dossier d'installation (bouton du launcher ou `cairn-doctor --fix`),
  en fusion non destructive des clés Blizzard existantes.
- **Placement des fenêtres sous Wayland** : règles KWin `cairn-pos-*` en mode *Remember*,
  plus une règle `layer=overlay` — la seule couche qui passe au-dessus d'un jeu en plein
  écran exclusif. Ailleurs, titres stables et app_id `cairn` pour cibler les fenêtres.

### Entretien automatique

- Base de cartes vérifiée à chaque lancement contre l'empreinte HTTP de HearthstoneJSON
  (`HEAD`, 12 h d'intervalle au plus) et retéléchargée après un patch.
- Alerte quand un patch **reformule une carte dont le code suppose l'effet** :
  `cairn-doctor` garde le signalement visible jusqu'à traitement.
- Archivage compressé des sessions (×18 mesuré), parce que Hearthstone efface ses vieux
  journaux sans prévenir.

### Vie privée et partage

- Ni compte, ni télémétrie, ni serveur. Seules requêtes réseau : la base de cartes et les
  illustrations.
- Partage de parties **refusé par défaut**, question posée une fois, réversible à tout
  moment — et **pseudonymisation inconditionnelle** : aucun réglage ne permet d'envoyer un
  journal brut, parce que l'adversaire n'était pas là pour donner son avis.
- Point de collecte fourni (Cloudflare Worker + R2) et **corpus public en lecture** ;
  `tools/corpus.py` le rapatrie sans compte ni clé, avec plafonds de taille et filtrage
  d'archive contre les chemins hostiles.
- `envoi.ENDPOINT_DEFAUT` est **vide** dans cette version : rien ne part tant qu'aucun
  point de collecte n'est déployé et renseigné.

### Installation et développement

- `install.sh` sans `sudo`, tout dans `~/.local` (XDG) : venv isolé, base de cartes,
  configuration de Hearthstone, raccourci et icône. `--desktop`, `--uninstall`.
- Commandes `cairn`, `cairn-doctor [--fix]`, `cairn-cards`.
- Interface bilingue FR/EN.
- Intégration continue sur Python 3.10 et 3.13, avec garde-fou : la CI **échoue si trop
  de tests se sautent**, faute de quoi un « vert » signifierait seulement que la moitié
  de la suite n'a pas tourné.
- Parties de référence versionnées compressées et pseudonymisées (1,3 Mo au lieu de 21) :
  la suite tourne entière sur un clone neuf.
- `tools/windows/` : scripts de collecte des journaux **depuis une machine Windows**
  (archivage en `.zip`, tâche planifiée, désinstallation) — Hearthstone efface ses vieux
  dossiers de session, et le corpus n'a aucune raison d'être limité aux joueurs Linux.

### Hors périmètre, assumé

Pas de données méta communautaires, pas d'aide au mulligan, pas de Battlegrounds, pas de
gestion de collection, pas d'arène. L'angle est le tracker Linux léger qui lit les
journaux — le reste viendra si ce socle tient.
