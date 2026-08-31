// Les overlays de Cairn doivent naître sur le bureau de Hearthstone.
//
// Sans ça : une partie démarre pendant qu'on est sur un autre bureau, les
// fenêtres s'ouvrent SOUS LES YEUX, sur le mauvais bureau, et il faut les
// traîner à la main sur le bon. KWin ne sait pas exprimer « le même bureau
// qu'une autre fenêtre » dans une règle — d'où ce script.
//
// Ce qu'on ne casse surtout pas : la séparation par bureau. C'est elle qui
// fait qu'un Alt+Tab vers Chrome, sur l'autre bureau, ne traîne pas le
// tracker avec lui. On déplace les overlays VERS Hearthstone, on ne les rend
// jamais « sur tous les bureaux ».

function estOverlayCairn(w) {
    if (!w || String(w.resourceClass) !== "cairn") return false;
    // « Cairn · … » (point médian) = overlay. Le launcher, lui, s'appelle
    // « Cairn — launcher » (tiret cadratin) et reste où l'utilisateur l'ouvre.
    return String(w.caption).indexOf("Cairn · ") === 0;
}

function fenetreHearthstone() {
    var ws = workspace.windowList();
    for (var i = 0; i < ws.length; i++) {
        // La classe « steam_app_default » est partagée avec Battle.net :
        // le titre est le seul discriminant fiable.
        if (String(ws[i].caption) === "Hearthstone") return ws[i];
    }
    return null;
}

function poserSurLeBureauDeHS(w) {
    if (!estOverlayCairn(w)) return;
    var hs = fenetreHearthstone();
    if (!hs || hs.onAllDesktops) return;      // HS absent : on ne touche à rien
    if (!hs.desktops || hs.desktops.length === 0) return;
    w.desktops = hs.desktops;
}

function replacerTousLesOverlays() {
    var ws = workspace.windowList();
    for (var i = 0; i < ws.length; i++) poserSurLeBureauDeHS(ws[i]);
}

workspace.windowAdded.connect(function (w) {
    poserSurLeBureauDeHS(w);
    // Certaines fenêtres reçoivent leur titre APRÈS leur création : sans ce
    // second passage, l'overlay serait encore anonyme au moment du test.
    w.captionChanged.connect(function () { poserSurLeBureauDeHS(w); });
});

// Hearthstone change de bureau → les overlays le suivent.
workspace.windowAdded.connect(function (w) {
    if (String(w.caption) !== "Hearthstone") return;
    w.desktopsChanged.connect(replacerTousLesOverlays);
});
var hs = fenetreHearthstone();
if (hs) hs.desktopsChanged.connect(replacerTousLesOverlays);

replacerTousLesOverlays();
