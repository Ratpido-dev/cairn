import QtQuick

// Pastille de points d'attaque — un seul chiffre, posé où le joueur veut.
//
// Séparée du panneau de compteurs à dessein : c'est la valeur qu'on relit dix
// fois par tour en calculant un échange. Noyée dans une liste avec Rafaam et
// les cadavres, elle devient illisible ; et le bandeau unique qui la portait
// mangeait toute la largeur de l'écran.
FloatingWindow {
    id: badge

    // "good" = mes dégâts (vert), "bad" = ceux d'en face (rouge)
    required property string side

    readonly property string value: side === "good" ? tracker.attackMine
                                                    : tracker.attackOpp
    readonly property color tint: side === "good" ? badge.good : badge.bad

    visible: tracker.hsRunning && tracker.inGame && value !== ""
    width: 62 * u
    height: 34 * u

    Rectangle {
        width: 62
        height: 34
        scale: badge.u
        transformOrigin: Item.TopLeft
        radius: 17
        color: badge.bg
        opacity: 0.94
        border.color: badge.tint
        border.width: 1

        // target: null — sinon le contenu dérive dans la fenêtre à chaque
        // déplacement jusqu'à sortir du cadre
        DragHandler { target: null; onActiveChanged: badge.grabbed(active) }

        Row {
            anchors.centerIn: parent
            spacing: 6

            // Épée dessinée, pas U+2694 : le glyphe manque de la plupart des
            // polices de la machine et sort en « tofu » (vérifié au rendu).
            Item {
                width: 12
                height: 14
                anchors.verticalCenter: parent.verticalCenter
                Rectangle {  // lame
                    x: 5; y: 0
                    width: 2
                    height: 10
                    color: badge.tint
                }
                Rectangle {  // garde
                    x: 2; y: 9
                    width: 8
                    height: 2
                    color: badge.tint
                }
                Rectangle {  // poignée
                    x: 5; y: 11
                    width: 2
                    height: 3
                    color: badge.tint
                }
            }

            Text {
                text: badge.value
                color: badge.tint
                font.pixelSize: 16
                font.bold: true
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }
}
