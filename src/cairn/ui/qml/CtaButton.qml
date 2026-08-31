import QtQuick

// Bouton d'action : dégradé profond, bordure lumineuse, halo au survol,
// enfoncement au clic. Sert autant aux gros CTA Victoire/Défaite qu'aux
// boutons secondaires (`tint` neutre, `strong: false`).
Rectangle {
    id: btn

    readonly property Theme thm: Theme {}
    property string label: ""
    property string glyph: ""              // pictogramme facultatif, à gauche
    property color tint: thm.gold
    property bool strong: true             // false = bouton discret, presque plat
    property int fontSize: 12

    signal clicked()

    readonly property bool hovered: mouse.containsMouse
    readonly property bool down: mouse.containsPress

    implicitHeight: 34
    radius: thm.rMd

    gradient: Gradient {
        GradientStop {
            position: 0.0
            color: Qt.alpha(btn.tint, btn.strong
                ? (btn.down ? 0.40 : btn.hovered ? 0.34 : 0.20)
                : (btn.down ? 0.18 : btn.hovered ? 0.13 : 0.06))
        }
        GradientStop {
            position: 1.0
            color: Qt.alpha(btn.tint, btn.strong
                ? (btn.down ? 0.20 : btn.hovered ? 0.17 : 0.09)
                : (btn.down ? 0.09 : btn.hovered ? 0.06 : 0.03))
        }
    }
    border.width: 1
    border.color: Qt.alpha(btn.tint, btn.strong
        ? (btn.hovered ? 0.85 : 0.50)
        : (btn.hovered ? 0.45 : 0.18))

    GlowRing {
        anchors.fill: parent
        cornerRadius: btn.radius
        glowColor: btn.tint
        spread: 7
        intensity: btn.down ? 0.45 : btn.hovered ? 0.34 : (btn.strong ? 0.12 : 0.0)
    }

    Row {
        anchors.centerIn: parent
        // le contenu s'enfonce d'un pixel au clic : le retour tactile manquait
        anchors.verticalCenterOffset: btn.down ? 1 : 0
        spacing: 7
        Text {
            visible: btn.glyph !== ""
            anchors.verticalCenter: parent.verticalCenter
            text: btn.glyph
            color: btn.strong ? Qt.lighter(btn.tint, 1.15) : btn.thm.textDim
            font.pixelSize: btn.fontSize + 1
            font.bold: true
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: btn.label
            color: btn.strong ? Qt.lighter(btn.tint, 1.15)
                 : (btn.hovered ? btn.thm.text : btn.thm.textDim)
            font.pixelSize: btn.fontSize
            font.bold: btn.strong
            font.letterSpacing: btn.strong ? 0.4 : 0
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: btn.clicked()
    }
}
