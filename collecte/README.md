# cairn-collecte

Point de collecte des parties que les joueurs acceptent de partager. Un
Cloudflare Worker de deux cents lignes qui reçoit un `tar.gz` par session
(~500 Ko), le range dans R2 — et le **rend à qui le demande**. Le corpus est
ouvert par défaut : ce qui arrive ici est déjà pseudonymisé côté client, donc
le fermer ne protégerait personne, cela demanderait seulement aux joueurs de
donner leurs parties à quelqu'un plutôt qu'à tout le monde.

Pour un dépôt en écriture seule : `OUVERT = "non"` dans `wrangler.toml`.

Le raisonnement — pourquoi cette architecture plutôt qu'un webhook — est dans
[`../docs/COLLECTE.md`](../docs/COLLECTE.md).

## Déployer

Il faut un compte Cloudflare (gratuit) et Node installé.

```bash
cd collecte
npm install                                  # installe wrangler
npm install-scripts approve esbuild workerd  # npm >= 12 seulement : sans ça, pas de binaire
npx wrangler login
npx wrangler r2 bucket create cairn-parties   # le dépôt
npx wrangler deploy
```

`deploy` affiche l'URL du service, de la forme
`https://cairn-collecte.<ton-compte>.workers.dev`.

### Sans Node : tout depuis le tableau de bord

Wrangler ne fait qu'une chose, téléverser un fichier — et le tableau de bord
sait le faire aussi. Aucun paquet à installer, et c'est la seule voie ouverte
sur une machine où l'on ne veut pas d'un environnement Node.

1. **R2** → *Create bucket* → nom `cairn-parties`.
2. **Workers & Pages** → *Create* → *Start from Hello World!* → nom
   `cairn-collecte` → *Deploy*.
3. *Edit code* → tout sélectionner, remplacer par le contenu de
   [`src/worker.js`](src/worker.js) → *Deploy*.
4. **Settings → Bindings** → *Add* → *R2 bucket* :
   nom de variable `PARTIES`, bucket `cairn-parties`. **C'est l'étape qu'on
   oublie** : sans elle le worker répond `503 depot non lie` à tout.
5. **Settings → Variables and Secrets** → *Add* : `OUVERT` = `oui`
   (corpus ouvert en lecture) — ou `non` pour un dépôt en écriture seule.
6. Facultatif, le quota : **KV** → *Create namespace* `QUOTAS`, puis
   *Bindings* → *KV namespace*, variable `QUOTAS`.

L'URL s'affiche en haut de la page du worker. Vérifie avec `/sante` :

```bash
curl https://cairn-collecte.<ton-compte>.workers.dev/sante
# {"service":"cairn-collecte","depot":true,"ouvert":true}
```

`depot: false` veut dire que l'étape 4 manque.

### Quota par installation (recommandé, facultatif)

```bash
npx wrangler kv namespace create QUOTAS
```

La commande rend un identifiant : décommente le bloc `[[kv_namespaces]]` de
`wrangler.toml`, colle-le, puis `npx wrangler deploy`. Sans ce bloc le worker
fonctionne, le quota est simplement inactif.

La limitation par **adresse IP**, elle, se règle dans le tableau de bord
Cloudflare (Security → *Rate limiting rules*), sans toucher au code.

## Brancher Cairn dessus

Une seule ligne, dans `src/cairn/envoi.py` :

```python
ENDPOINT_DEFAUT = "https://cairn-collecte.ton-compte.workers.dev/"
```

Pour essayer avant de figer quoi que ce soit, la variable d'environnement
l'emporte :

```bash
# terminal 1
npx wrangler dev
# terminal 2
CAIRN_SHARE_ENDPOINT=http://127.0.0.1:8787/ cairn
```

## Lire le corpus

Sans clé, sans compte, tant que `OUVERT = "oui"` :

```bash
curl https://cairn-collecte.ton-compte.workers.dev/parties
# {"sessions":[{"cle":"<install>/<session>.tar.gz","octets":508213,…}],"curseur":…}

curl -O https://cairn-collecte.ton-compte.workers.dev/parties/<install>/<session>.tar.gz
```

| Route | Rend |
|---|---|
| `GET /` | le mode d'emploi, en texte |
| `GET /parties` | l'index JSON, 1000 sessions par page |
| `GET /parties?curseur=…` | la page suivante |
| `GET /parties?installation=<id>` | les sessions d'une seule installation |
| `GET /parties/<install>/<session>.tar.gz` | la session |

Une session ne changeant jamais après son dépôt, elle est servie
`immutable` — le cache de Cloudflare absorbe les reprises. L'index, lui, tient
5 minutes.

Côté client, `tools/corpus.py` fait tout ça d'un coup (pagination suivie,
sessions déjà présentes sautées, extraction optionnelle) :

```bash
python tools/corpus.py --url https://cairn-collecte.ton-compte.workers.dev --extraire
```

## Vérifier que ça tourne

```bash
curl https://cairn-collecte.ton-compte.workers.dev/sante
# {"service":"cairn-collecte","depot":true,"ouvert":true}

npx wrangler r2 object list cairn-parties     # ce qui est arrivé
npx wrangler tail                             # les requêtes en direct
```

Les archives sont rangées sous `<install_id>/<session>.tar.gz`. Pour en rejouer
une :

```bash
npx wrangler r2 object get cairn-parties/<install>/<session>.tar.gz \
    --file partie.tar.gz
tar xzf partie.tar.gz
python tools/replay.py <session>/
```

## Ce que le worker refuse, et ce que ça déclenche côté client

Le code de retour n'est pas décoratif : le client s'en sert pour décider s'il
réessaie. Un `400` rendu pour une panne passagère fait perdre la partie
définitivement.

| Code | Cas | Réaction du client |
|---|---|---|
| `204` | reçu et rangé | efface la session de son outbox |
| `400` | en-têtes ou contenu invalides | abandonne cette session |
| `405` / `411` / `413` / `415` | méthode, longueur, taille, type | abandonne cette session |
| `429` | quota de l'installation atteint | réessaie plus tard |
| `503` | dépôt R2 non lié | réessaie plus tard |

Contrôles appliqués, dans l'ordre : méthode, `Content-Type`, `Content-Length`
annoncée, forme de `X-Cairn-Install` et `X-Cairn-Session`, **taille réelle** du
corps (l'en-tête peut mentir), puis inspection du premier bloc de l'archive —
qui doit être un en-tête `ustar` dont le premier fichier appartient à la session
annoncée. Un blob quelconque de 8 Mo est donc rejeté avant d'atteindre R2.

Les deux moitiés de ce contrat sont verrouillées par
`tests/test_envoi_contrat.py`, côté Python.

## Coût

Palier gratuit : 100 000 requêtes/jour, 10 Go de stockage R2, 1 000 écritures
KV/jour. À 500 Ko la session, dix mille parties tiennent dans le gratuit. Une
règle de cycle de vie R2 (« supprimer après 90 jours ») garde le volume stable
si le service dure.
