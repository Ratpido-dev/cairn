import QtQuick

// Petit bouton de ligne (archiver, supprimer…). Discret au repos, il ne
// s'allume qu'au survol : dans une liste de decks, dix boutons colorés en
// permanence tirent l'œil plus fort que les statistiques qu'ils accompagnent.
Rectangle {
    id: btn

    readonly property Theme thm: Theme {}
    property string glyph: ""
    property string label: ""
    property color tint: thm.textDim

    signal clicked()

    readonly property bool hovered: mouse.containsMouse

    implicitWidth: Math.max(20, content.implicitWidth + 14)
    implicitHeight: 20
    radius: 6
    color: hovered ? Qt.alpha(tint, mouse.containsPress ? 0.32 : 0.20)
                   : Qt.rgba(1, 1, 1, 0.04)
    border.width: 1
    border.color: hovered ? Qt.alpha(tint, 0.65) : btn.thm.hairline
    Behavior on color { ColorAnimation { duration: 110 } }

    GlowRing {
        anchors.fill: parent
        cornerRadius: btn.radius
        glowColor: btn.tint
        spread: 4
        intensity: btn.hovered ? 0.28 : 0.0
    }

    Text {
        id: content
        anchors.centerIn: parent
        text: btn.glyph !== "" ? btn.glyph : btn.label
        color: btn.hovered ? Qt.lighter(btn.tint, 1.2) : btn.thm.textFaint
        font.pixelSize: btn.glyph !== "" ? 10 : 9
        font.bold: btn.hovered
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: btn.clicked()
    }
}
