/**
 * Point de collecte des parties partagées par Cairn.
 *
 * Reçoit un `tar.gz` par session (~500 Ko), le vérifie, le range dans R2 — et
 * le **rend à qui le demande**. Le dépôt n'est pas un silo : les joueurs qui
 * alimentent le corpus peuvent le retélécharger en entier, et n'importe qui
 * d'autre aussi (`OUVERT = "oui"` dans `wrangler.toml`, voir plus bas).
 *
 * L'URL de ce service est publique — Cairn est un logiciel libre, elle est
 * dans ses sources. Toute la défense est donc ici, et aucune ne repose sur le
 * secret : plafond de taille, forme des en-têtes, validation du contenu réel,
 * quota par installation.
 *
 * Pourquoi la lecture est ouverte, alors qu'un dépôt en écriture seule serait
 * plus simple à défendre : ce qui arrive ici est déjà pseudonymisé côté client,
 * inconditionnellement (`src/cairn/sharing.py`), donc il n'y a rien à protéger
 * qui ne l'ait pas déjà été avant le départ. Garder ce corpus fermé
 * n'ajouterait aucune sécurité — cela ne ferait que demander aux joueurs de
 * donner leurs parties à quelqu'un plutôt qu'à tout le monde, ce qui est
 * exactement le marché que les autres trackers proposent déjà.
 *
 * Routes :
 *   POST /                              dépôt d'une session (le client Cairn)
 *   GET  /sante                         sonde de déploiement
 *   GET  /parties                       index JSON paginé du corpus
 *   GET  /parties/<install>/<session>.tar.gz    une session
 *   GET  /                              mode d'emploi, en texte
 *
 * Contrat avec le client (`src/cairn/envoi.py`) :
 *   - 2xx        → la session est livrée, le client l'efface de son outbox ;
 *   - 408 / 429  → « reviens plus tard », le client réessaie avec attente
 *                  croissante (1 min → 24 h) ;
 *   - autres 4xx → refus définitif, le client cesse de réessayer ;
 *   - 5xx        → panne, le client réessaie.
 * Se tromper de code a donc des conséquences : un 400 rendu pour une panne
 * passagère fait perdre la partie pour de bon.
 */

const MAX_OCTETS = 8 * 1024 * 1024;   // une session pèse ~500 Ko
const QUOTA_PAR_JOUR = 50;            // large : ~50 sessions = une très grosse journée
const ID = /^[A-Za-z0-9_-]{8,64}$/;                 // UUID d'installation
const SESSION = /^Hearthstone_[0-9_]{8,40}$/;       // nom de dossier de HS

const TAR_BLOC = 512;
const TAR_MAGIE = 257;   // décalage du « ustar » dans l'en-tête tar

const PAGE_MAX = 1000;   // sessions par page d'index (plafond de R2.list)
// Une session ne change jamais après son dépôt : elle peut être mise en cache
// longtemps. L'index, lui, bouge à chaque partie reçue.
const CACHE_SESSION = "public, max-age=31536000, immutable";
const CACHE_INDEX = "public, max-age=300";

// Clé R2 d'une session : « <install>/<session>.tar.gz », et rien d'autre. On
// revalide la forme À LA LECTURE plutôt que de faire confiance à ce qui a été
// écrit : une route qui sert des clés arbitraires est une route qui sert un
// jour la mauvaise.
function cleValide(install, session) {
  return ID.test(install) && SESSION.test(session);
}

function refus(code, raison) {
  return new Response(`${raison}\n`, {
    status: code,
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}

/**
 * Les 512 premiers octets décompressés, ou `null` si ça n'est pas du gzip.
 *
 * Le client écrit ses archives au format USTAR justement pour que ce premier
 * bloc décrive directement un vrai fichier, sans en-tête PAX à sauter.
 */
async function premierBloc(octets) {
  try {
    const flux = new Response(octets).body.pipeThrough(
      new DecompressionStream("gzip"),
    );
    const lecteur = flux.getReader();
    const bloc = new Uint8Array(TAR_BLOC);
    let rempli = 0;
    while (rempli < TAR_BLOC) {
      const { done, value } = await lecteur.read();
      if (done) break;
      const prendre = Math.min(value.length, TAR_BLOC - rempli);
      bloc.set(value.subarray(0, prendre), rempli);
      rempli += prendre;
    }
    lecteur.cancel();
    return rempli === TAR_BLOC ? bloc : null;
  } catch {
    return null;   // pas du gzip, ou tronqué
  }
}

/** Le contenu est-il bien une archive de session Cairn ? */
async function contenuPlausible(octets, session) {
  const bloc = await premierBloc(octets);
  if (bloc === null) return false;
  const texte = new TextDecoder("latin1");
  if (!texte.decode(bloc.subarray(TAR_MAGIE, TAR_MAGIE + 5)).startsWith("ustar")) {
    return false;
  }
  // le premier fichier doit appartenir à la session annoncée dans l'en-tête :
  // sinon on stockerait sous une clé qui ne décrit pas le contenu
  const nom = texte.decode(bloc.subarray(0, 100)).replace(/\0.*$/, "");
  return nom.startsWith(`${session}/`);
}

/**
 * Quota approximatif par installation et par jour.
 *
 * KV est à cohérence différée : deux requêtes simultanées peuvent lire le même
 * compteur. C'est sans importance — il s'agit d'écrêter un envoi en boucle, pas
 * de compter juste. La protection par IP se règle à côté, dans les « Rate
 * limiting rules » du tableau de bord, sans toucher à ce code.
 *
 * Sans espace KV lié, le quota est simplement inactif.
 */
async function quotaDepasse(env, install) {
  if (!env.QUOTAS) return false;
  const jour = new Date().toISOString().slice(0, 10);
  const cle = `q:${install}:${jour}`;
  const compte = Number(await env.QUOTAS.get(cle)) || 0;
  if (compte >= QUOTA_PAR_JOUR) return true;
  await env.QUOTAS.put(cle, String(compte + 1), { expirationTtl: 172800 });
  return false;
}


// ---- lecture du corpus -------------------------------------------------------

/**
 * Index paginé. Rend les clés, leur taille et leur date, jamais le contenu.
 *
 * `?curseur=` reprend là où la page précédente s'est arrêtée, `?installation=`
 * ne liste que les sessions d'une installation — c'est ce qui permet à un
 * joueur de retrouver ses propres envois, et à une analyse de traiter la suite
 * de parties d'un même joueur comme une suite.
 */
async function servirIndex(env, url) {
  const params = url.searchParams;
  const installation = params.get("installation") || "";
  if (installation && !ID.test(installation)) return refus(400, "installation");
  const demande = Number(params.get("par_page")) || PAGE_MAX;

  const page = await env.PARTIES.list({
    prefix: installation ? `${installation}/` : undefined,
    cursor: params.get("curseur") || undefined,
    limit: Math.min(Math.max(demande, 1), PAGE_MAX),
    include: ["customMetadata"],
  });

  return Response.json(
    {
      sessions: page.objects.map((o) => ({
        cle: o.key,
        octets: o.size,
        recu: o.customMetadata?.recu || o.uploaded,
        cairn: o.customMetadata?.version || "",
      })),
      // `truncated` faux = c'est la dernière page ; le curseur devient inutile
      curseur: page.truncated ? page.cursor : null,
    },
    { headers: { "Cache-Control": CACHE_INDEX } },
  );
}

/** Une session, telle qu'elle est arrivée. */
async function servirSession(env, install, nom, avecCorps) {
  if (!cleValide(install, nom)) return refus(400, "cle");
  const cle = `${install}/${nom}.tar.gz`;
  const objet = avecCorps ? await env.PARTIES.get(cle) : await env.PARTIES.head(cle);
  if (objet === null) return refus(404, "inconnue");
  const entetes = new Headers({
    "Content-Type": "application/gzip",
    "Content-Length": String(objet.size),
    "Cache-Control": CACHE_SESSION,
    ETag: objet.httpEtag,
  });
  return new Response(avecCorps ? objet.body : null, { headers: entetes });
}

/** Ce qu'un humain trouve en ouvrant l'URL dans son navigateur. */
function accueil(ouvert) {
  const corps = ouvert
    ? [
        "cairn-collecte — corpus de parties Hearthstone partagées",
        "",
        "Les journaux sont pseudonymisés sur la machine du joueur avant tout",
        "envoi : ni battletag ni identifiant de compte n'arrivent jusqu'ici.",
        "Le corpus est ouvert — sers-toi.",
        "",
        "  GET /parties                                  index JSON",
        "  GET /parties?curseur=…                        page suivante",
        "  GET /parties?installation=<id>                une installation",
        "  GET /parties/<install>/<session>.tar.gz       une session",
        "",
        "Rejouer une session : tar xzf <session>.tar.gz",
        "                      python tools/replay.py <session>/",
        "",
        "Cairn : https://github.com/ratpido/cairn",
      ]
    : [
        "cairn-collecte",
        "",
        "Ce dépôt-ci est en écriture seule (OUVERT != \"oui\").",
        "",
        "Cairn : https://github.com/ratpido/cairn",
      ];
  return new Response(`${corps.join("\n")}\n`, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": CACHE_INDEX,
    },
  });
}

export default {
  async fetch(requete, env) {
    const url = new URL(requete.url);

    // Sonde de déploiement. Ne révèle rien de ce qui a été reçu — juste que le
    // service répond et que le dépôt est bien lié.
    if (requete.method === "GET" && url.pathname === "/sante") {
      return Response.json({
        service: "cairn-collecte",
        depot: Boolean(env.PARTIES),
        ouvert: env.OUVERT === "oui",
      });
    }

    // Lecture du corpus. Fermée tant que `OUVERT` ne vaut pas « oui » : celui
    // qui héberge décide, et son choix ne dépend pas d'une modification du
    // code — donc pas d'une divergence à maintenir.
    const lecture = requete.method === "GET" || requete.method === "HEAD";
    if (lecture && !env.PARTIES) return refus(503, "depot non lie");
    if (lecture && url.pathname === "/") return accueil(env.OUVERT === "oui");
    if (lecture && url.pathname === "/parties") {
      if (env.OUVERT !== "oui") return refus(404, "corpus ferme");
      return servirIndex(env, url);
    }
    if (lecture && url.pathname.startsWith("/parties/")) {
      if (env.OUVERT !== "oui") return refus(404, "corpus ferme");
      const chemin = url.pathname.slice("/parties/".length).split("/");
      if (chemin.length !== 2 || !chemin[1].endsWith(".tar.gz")) {
        return refus(404, "inconnue");
      }
      return servirSession(
        env, chemin[0], chemin[1].slice(0, -".tar.gz".length),
        requete.method === "GET",
      );
    }

    if (requete.method !== "POST") return refus(405, "methode");
    if (!env.PARTIES) return refus(503, "depot non lie");

    const type = (requete.headers.get("Content-Type") || "").split(";")[0].trim();
    if (type !== "application/gzip") return refus(415, "type");

    const annoncee = Number(requete.headers.get("Content-Length") || 0);
    if (!annoncee) return refus(411, "longueur manquante");
    if (annoncee > MAX_OCTETS) return refus(413, "taille");

    const install = requete.headers.get("X-Cairn-Install") || "";
    const session = requete.headers.get("X-Cairn-Session") || "";
    if (!ID.test(install) || !SESSION.test(session)) return refus(400, "entetes");

    const octets = await requete.arrayBuffer();
    // Content-Length peut mentir : c'est la taille RÉELLE qui décide
    if (octets.byteLength === 0 || octets.byteLength > MAX_OCTETS) {
      return refus(413, "taille");
    }
    if (!(await contenuPlausible(octets, session))) return refus(400, "contenu");

    if (await quotaDepasse(env, install)) return refus(429, "quota");

    // La clé porte l'installation : personne ne peut écraser la session d'un
    // autre, au pire la sienne — ce qui est exactement ce qu'on veut quand un
    // accusé de réception s'est perdu et que le client réessaie.
    await env.PARTIES.put(`${install}/${session}.tar.gz`, octets, {
      httpMetadata: { contentType: "application/gzip" },
      customMetadata: {
        version: (requete.headers.get("X-Cairn-Version") || "").slice(0, 32),
        recu: new Date().toISOString(),
      },
    });
    return new Response(null, { status: 204 });
  },
};
