import QtQuick

// Aperçu de carte dessiné DANS le panneau qui l'ouvre (option « aperçu dans
// le panneau »), au lieu d'une fenêtre à côté.
//
// Pourquoi : sous Niri, Hyprland ou Sway, chaque nouvelle fenêtre reçoit le
// focus et réorganise la mosaïque. Le panneau perdait le survol, l'aperçu se
// fermait, le panneau le regagnait… et ça bouclait. Ici, pas de fenêtre à
// créer : rien ne bouge sous la souris.
//
// À poser en DERNIER enfant du fond du panneau, en anchors.fill. L'aperçu se
// place du côté où il a le plus de place — au-dessus ou au-dessous de la
// ligne survolée, jamais dessus — et rétrécit s'il ne tient pas. Quand le
// panneau est trop court, neededHeight dit au panneau de quelle hauteur
// grandir (vers le bas : la ligne survolée ne bouge pas).
Item {
    id: inline

    property string cardId: ""
    property bool opponentSide: false
    property string note: ""
    readonly property bool active: tracker.previewInPanel
                                   && (cardId !== "" || note !== "")

    // demi-hauteur d'une ligne : l'aperçu ne recouvre jamais celle survolée
    readonly property real gap: 18
    readonly property real margin: 6
    readonly property real cursorY: souris.point.position.y
    readonly property real above: cursorY - gap - margin
    readonly property real below: height - cursorY - gap - margin
    readonly property bool downward: below >= above
    // Hauteur minimale du panneau pour que l'aperçu tienne en entier sous la
    // souris — 0 s'il tient déjà au-dessus. Ne dépend pas de `height` : pas
    // de boucle de liaison quand le panneau grandit.
    readonly property real neededHeight:
        active && above < body.implicitHeight
            ? cursorY + gap + body.implicitHeight + margin : 0

    // Repère la souris sur tout le panneau sans rien intercepter : les
    // HoverHandler des lignes en dessous reçoivent toujours le survol.
    HoverHandler { id: souris }

    CardPreviewBody {
        id: body
        visible: inline.active
        cardId: inline.cardId
        opponentSide: inline.opponentSide
        note: inline.note
        x: (inline.width - width) / 2
        y: inline.downward ? inline.cursorY + inline.gap
                           : inline.cursorY - inline.gap - height
        transformOrigin: inline.downward ? Item.Top : Item.Bottom
        scale: Math.min(1, (inline.width - 2 * inline.margin) / width,
                        Math.max(40, inline.downward ? inline.below : inline.above)
                            / Math.max(1, implicitHeight))
    }
}
