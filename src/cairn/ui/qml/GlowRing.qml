import QtQuick

// Lueur (glow) autour d'un élément, en géométrie pure.
//
// Pas de `MultiEffect` ni de `DropShadow` : sous rendu logiciel (llvmpipe, VM,
// capture offscreen) les effets à shader ne dessinent RIEN — l'élément source
// disparaît purement et simplement, vérifié sur cette machine. On empile donc
// N anneaux d'1 px, chacun un peu plus large et un peu plus transparent : le
// résultat est un halo doux, gratuit en GPU, identique partout.
//
// À poser en enfant de la carte à faire luire :
//     Rectangle { GlowRing { anchors.fill: parent; cornerRadius: 12 } }
// Les anneaux débordent vers l'extérieur, jamais sur le contenu.
Item {
    id: ring

    property color glowColor: "#F59E0B"
    property real cornerRadius: 12
    property int spread: 6            // épaisseur du halo, en pixels
    property real intensity: 0.30     // opacité du premier anneau
    // adoucissement à l'allumage/extinction (survol, état actif)
    Behavior on intensity { NumberAnimation { duration: 140 } }

    Repeater {
        model: ring.spread
        delegate: Rectangle {
            required property int index
            anchors.centerIn: parent
            width: ring.width + 2 * (index + 1)
            height: ring.height + 2 * (index + 1)
            radius: ring.cornerRadius + index + 1
            color: "transparent"
            border.width: 1
            // décroissance quadratique : le halo s'éteint vite, sinon il bave
            border.color: Qt.alpha(
                ring.glowColor,
                ring.intensity * Math.pow(1 - index / ring.spread, 1.8))
        }
    }
}
