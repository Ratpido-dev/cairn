# Recevoir les parties partagées

Cairn sait préparer et **envoyer** les parties que les joueurs acceptent de
partager (`src/cairn/envoi.py`). Ce qu'il ne fournit pas, c'est le point de
collecte : `envoi.ENDPOINT_DEFAUT` est vide, et tant qu'il l'est, les parties
restent dans l'outbox, sur la machine du joueur. Ce document explique comment
en monter un.

## Le problème de fond : l'URL sera publique

Cairn est un logiciel libre, distribué avec ses sources. Quelle que soit la
façon dont l'URL de collecte est « cachée » — constante, variable
d'environnement, fichier de configuration, chaîne obscurcie — elle est lisible
par quiconque installe l'application. Un webhook Discord ou une adresse SMTP
avec identifiants sont donc **hors de question** : le premier venu pourrait
inonder le canal ou usurper l'expéditeur.

La conséquence est simple : **c'est au serveur de se défendre**, pas à un secret
embarqué de faire semblant d'en être un. Ce que le serveur doit faire :

- refuser tout corps de plus de quelques mégaoctets ;
- limiter le débit par `X-Cairn-Install` **et** par adresse IP ;
- n'accepter que `POST`, `Content-Type: application/gzip` ;
- répondre lui-même de la lecture, s'il ouvre le corpus (voir plus bas) : R2
  exposé en direct n'a ni quota ni contrôle de forme des clés ;
- répondre `4xx` sur ce qu'il refuse — le client cesse alors de réessayer, ce
  qui vous protège du bruit autant que lui.

## La solution recommandée : Cloudflare Worker + R2

Gratuit à cette échelle (100 000 requêtes/jour, 10 Go de stockage), déjà
protégé contre les inondations, et rien à administrer. Une session pèse environ
**500 Ko compressée** : dix mille parties tiennent dans le palier gratuit.

Le service est écrit et prêt à déployer dans **[`../collecte/`](../collecte/)** :
worker, configuration `wrangler`, et les commandes exactes. Trois minutes de
mise en route.

Il ne se contente pas d'accepter ce qu'on lui donne : il vérifie la méthode, le
type, la taille **réelle** du corps (l'en-tête `Content-Length` peut mentir), la
forme des en-têtes d'identification, puis **décompresse le premier bloc de
l'archive** pour s'assurer qu'il s'agit bien d'une session Cairn et non d'un
blob quelconque de 8 Mo. Le quota par installation passe par KV ; la limitation
par IP se règle dans le tableau de bord Cloudflare, sans toucher au code.

## Écriture seule, ou corpus ouvert ?

Le worker sait faire les deux, et c'est `OUVERT` dans `wrangler.toml` qui
tranche. Par défaut il vaut `"oui"` : n'importe qui peut lister le corpus
(`GET /parties`) et retélécharger n'importe quelle session.

Ce n'est pas un arbitrage de sécurité. Ce qui arrive ici est **déjà**
pseudonymisé sur la machine du joueur, inconditionnellement : refermer le dépôt
ne protégerait plus rien, puisqu'il n'y a plus rien à protéger une fois que
c'est parti. Ce que la fermeture change, c'est le marché proposé au joueur —
« donne tes parties à quelqu'un » au lieu de « donne tes parties à tout le
monde, toi compris ». Le premier est celui des trackers propriétaires, et le
second est la raison d'être de cette fonction. L'argumentaire complet est dans
la section « Pourquoi le corpus est ouvert » du [README](../README.md).

Deux conséquences à assumer avant d'ouvrir :

- l'`install_id` **regroupe** les parties d'une même installation. C'est ce qui
  rend le corpus exploitable, et c'est aussi ce qui permet de dire « ces 400
  parties viennent de la même personne » — sans jamais pouvoir dire laquelle,
  le sel de pseudonymisation étant propre à chaque installation ;
- **publier ne se reprend pas.** Honorer une demande de suppression vide le
  dépôt, pas les copies déjà téléchargées. Le consentement affiché par Cairn le
  dit avant le clic, pas après.

Une troisième conséquence, technique celle-là : **relire le corpus, c'est
consommer des données qu'aucun humain n'a filtrées.** N'importe qui peut y
déposer une session, donc n'importe qui peut y déposer un piège. C'est le seul
endroit du projet où Cairn traite de l'inconnu, et `tools/corpus.py` s'en
protège explicitement — plafond de lecture HTTP, refus des archives qui sortent
de leur dossier (`filter="data"`), refus des bombes de décompression (le total
déballé est vérifié avant la première écriture). Ces trois protections ont leurs
trois tests. Si tu déballes à la main, `tar xzf` n'en offre aucune des deux
dernières.

Côté client, `tools/corpus.py` rapatrie l'ensemble — index paginé, reprise sans
retéléchargement, extraction. Aucune clé, aucun compte.

```bash
python tools/corpus.py --url https://collecte.exemple.workers.dev --extraire
python tools/corpus.py --url … --installation <mon-id>   # mes propres envois
```

Ensuite, côté Cairn, une seule ligne à remplir :

```python
# src/cairn/envoi.py
ENDPOINT_DEFAUT = "https://collecte.exemple.workers.dev/"
```

Pour essayer sans rien déployer, la variable d'environnement l'emporte :

```bash
CAIRN_SHARE_ENDPOINT=http://127.0.0.1:8000/depot cairn
```

## Ce que le client garantit déjà

- **Pseudonymisation inconditionnelle** avant tout départ (`sharing.preparer`) :
  aucun battletag ne quitte la machine, ni celui du joueur ni celui de son
  adversaire. C'est ce qui rend un corpus ouvert défendable : ce qui est publié
  a déjà été nettoyé, il n'y a pas de « version brute » quelque part.
- **Jamais pendant une partie** : l'outbox n'est alimentée qu'entre deux parties.
- **Jamais bloquant** : préparation et envoi tournent dans un fil de fond, et
  aucune erreur réseau ne remonte à l'interface.
- **Reprise avec attente croissante** : 1 min, 5, 30, 2 h, 12 h, 24 h, puis
  abandon — la session reste visible dans le launcher, et le bouton « envoyer
  maintenant » force toujours le passage.
- **Un `tar.gz` par session**, ~500 Ko, avec `meta.json` (rang déclaré, type de
  partie, version de Cairn, identifiant d'installation).
- **Effacement après accusé de réception** : l'outbox n'est pas un historique,
  les journaux complets sont archivés séparément.

L'`install_id` est un UUID local, sans lien avec le joueur. Il ne sert qu'à
dédupliquer les envois et à honorer une demande de suppression : sans lui,
« effacez mes données » serait impossible à traiter.
