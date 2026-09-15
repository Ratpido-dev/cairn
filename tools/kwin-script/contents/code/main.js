// Les overlays de Cairn doivent naître sur le bureau ET l'écran de Hearthstone.
//
// Le bureau. Sans ça : une partie démarre pendant qu'on est sur un autre
// bureau, les fenêtres s'ouvrent SOUS LES YEUX, sur le mauvais bureau, et il
// faut les traîner à la main sur le bon. KWin ne sait pas exprimer « le même
// bureau qu'une autre fenêtre » dans une règle — d'où ce script.
//
// Ce qu'on ne casse surtout pas : la séparation par bureau. C'est elle qui
// fait qu'un Alt+Tab vers Chrome, sur l'autre bureau, ne traîne pas le
// tracker avec lui. On déplace les overlays VERS Hearthstone, on ne les rend
// jamais « sur tous les bureaux ».
//
// L'écran (issue #1). Sous Wayland un client ne choisit ni son écran ni sa
// position : les x/y du QML sont ignorés, et les règles KWin posent des
// coordonnées ABSOLUES, calculées à l'installation pour un seul écran. Sur un
// poste à deux écrans, tout Cairn s'ouvrait donc sur l'écran de ces
// coordonnées, même quand Hearthstone était sur l'autre ; et un aperçu de
// carte ne suivait jamais son panneau. Seul le compositeur connaît les
// écrans et la vraie position des fenêtres : c'est ici qu'on corrige.

// Qui veut garder ses panneaux sur un AUTRE écran que le jeu (tracker sur le
// second écran, façon HDT) désactive ce suivi ; les aperçus suivent alors
// toujours leur panneau.
//   kwriteconfig6 --file kwinrc --group Script-cairn-follow \
//                 --key suivreEcranDeHearthstone false
var SUIVRE_ECRAN = String(readConfig("suivreEcranDeHearthstone", true)) !== "false";

// Chaque aperçu et le panneau qui l'ouvre, avec le côté où il s'affiche et
// son décalage vertical — les mêmes que dans le QML, qui ne peut pas les
// imposer lui-même sous Wayland.
var APERCUS = {
    "Cairn · aperçu deck":       { parent: "Cairn · deck",         cote: "gauche",  dy: 40 },
    "Cairn · aperçu adversaire": { parent: "Cairn · adversaire",   cote: "droite",  dy: 40 },
    "Cairn · aperçu main":       { parent: "Cairn · main adverse", cote: "dessous", dy: 6 },
    "Cairn · aperçu secret":     { parent: "Cairn · secrets",      cote: "droite",  dy: 0 }
};
var ECART = 8;

function estOverlayCairn(w) {
    if (!w || String(w.resourceClass) !== "cairn") return false;
    // « Cairn · … » (point médian) = overlay. Le launcher, lui, s'appelle
    // « Cairn — launcher » (tiret cadratin) et reste où l'utilisateur l'ouvre.
    return String(w.caption).indexOf("Cairn · ") === 0;
}

function estApercu(w) {
    return APERCUS.hasOwnProperty(String(w.caption));
}

function fenetreParTitre(titre) {
    var ws = workspace.windowList();
    for (var i = 0; i < ws.length; i++) {
        if (String(ws[i].caption) === titre) return ws[i];
    }
    return null;
}

function fenetreHearthstone() {
    // La classe « steam_app_default » est partagée avec Battle.net :
    // le titre est le seul discriminant fiable.
    return fenetreParTitre("Hearthstone");
}

function borner(v, min, max) {
    return Math.max(min, Math.min(v, max));
}

function memeEcran(a, b) {
    return !!a && !!b && String(a.name) === String(b.name);
}

function poserSurLeBureauDeHS(w, hs) {
    if (!hs || hs.onAllDesktops) return;      // HS absent : on ne touche à rien
    if (!hs.desktops || hs.desktops.length === 0) return;
    w.desktops = hs.desktops;
}

// Déplace w sur l'écran cible en gardant sa place RELATIVE : un panneau collé
// au bord droit du portable reste collé au bord droit de l'autre écran, même
// si les deux n'ont pas la même résolution.
function versEcran(w, cible) {
    var src = w.output;
    if (!src || !cible || memeEcran(src, cible)) return;
    var g = w.frameGeometry, s = src.geometry, c = cible.geometry;
    var fx = borner((g.x - s.x) / Math.max(1, s.width - g.width), 0, 1);
    var fy = borner((g.y - s.y) / Math.max(1, s.height - g.height), 0, 1);
    w.frameGeometry = {
        x: Math.round(c.x + fx * Math.max(0, c.width - g.width)),
        y: Math.round(c.y + fy * Math.max(0, c.height - g.height)),
        width: g.width, height: g.height
    };
}

// Colle un aperçu à SON panneau, là où le panneau se trouve vraiment, et le
// garde dans l'écran du panneau. Rend false si le panneau est introuvable.
function placerApercu(w) {
    var def = APERCUS[String(w.caption)];
    var p = (w.transientFor && estOverlayCairn(w.transientFor)) ? w.transientFor
                                                                : fenetreParTitre(def.parent);
    if (!p || !p.output) return false;
    var g = w.frameGeometry, pg = p.frameGeometry, c = p.output.geometry;
    var x, y;
    if (def.cote === "dessous") {
        x = pg.x;
        y = pg.y + pg.height + def.dy;
        if (y + g.height > c.y + c.height) y = pg.y - def.dy - g.height;  // pas la place : au-dessus
    } else {
        var aGauche = pg.x - ECART - g.width;
        var aDroite = pg.x + pg.width + ECART;
        var gauche = def.cote === "gauche";
        // Le côté prévu, sinon l'autre quand le panneau est collé au bord.
        if (gauche && aGauche < c.x) gauche = false;
        else if (!gauche && aDroite + g.width > c.x + c.width) gauche = true;
        x = gauche ? aGauche : aDroite;
        y = pg.y + def.dy;
    }
    var geo = {
        x: Math.round(borner(x, c.x, c.x + c.width - g.width)),
        y: Math.round(borner(y, c.y, c.y + c.height - g.height)),
        width: g.width, height: g.height
    };
    if (geo.x !== g.x || geo.y !== g.y) w.frameGeometry = geo;
    return true;
}

function traiter(w) {
    if (!estOverlayCairn(w)) return;
    var hs = fenetreHearthstone();
    poserSurLeBureauDeHS(w, hs);
    if (estApercu(w)) {
        // Panneau introuvable (vieille version sans le titre attendu) : au
        // moins sur l'écran du jeu.
        if (!placerApercu(w) && hs) versEcran(w, hs.output);
        return;
    }
    if (hs && SUIVRE_ECRAN) versEcran(w, hs.output);
}

function replacerTousLesOverlays() {
    var ws = workspace.windowList(), apercus = [];
    // Les panneaux d'abord : les aperçus se calent ensuite sur leur position.
    for (var i = 0; i < ws.length; i++) {
        if (!estOverlayCairn(ws[i])) continue;
        if (estApercu(ws[i])) apercus.push(ws[i]);
        else traiter(ws[i]);
    }
    for (var j = 0; j < apercus.length; j++) traiter(apercus[j]);
}

// Un aperçu grandit quand son image arrive : il faut le recaler, sinon il
// déborde sous l'écran. Garde-fou contre la réentrance, puisque le recaler
// change lui-même sa géométrie.
var recalageEnCours = false;
function recalerApercu(w) {
    if (recalageEnCours || !estApercu(w)) return;
    recalageEnCours = true;
    try { placerApercu(w); } finally { recalageEnCours = false; }
}

function suivreHearthstone(hs) {
    // Hearthstone change de bureau ou d'écran → les overlays le suivent.
    hs.desktopsChanged.connect(replacerTousLesOverlays);
    if (hs.outputChanged) hs.outputChanged.connect(replacerTousLesOverlays);
}

workspace.windowAdded.connect(function (w) {
    if (String(w.caption) === "Hearthstone") {
        suivreHearthstone(w);
        replacerTousLesOverlays();
        return;
    }
    traiter(w);
    // Certaines fenêtres reçoivent leur titre APRÈS leur création : sans ce
    // second passage, l'overlay serait encore anonyme au moment du test.
    w.captionChanged.connect(function () { traiter(w); });
    w.frameGeometryChanged.connect(function () { recalerApercu(w); });
});

var hsAuDemarrage = fenetreHearthstone();
if (hsAuDemarrage) suivreHearthstone(hsAuDemarrage);

// Les fenêtres déjà ouvertes au chargement du script.
var existantes = workspace.windowList();
for (var k = 0; k < existantes.length; k++) {
    (function (w) {
        if (estApercu(w)) w.frameGeometryChanged.connect(function () { recalerApercu(w); });
    })(existantes[k]);
}
replacerTousLesOverlays();
