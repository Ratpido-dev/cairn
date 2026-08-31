import QtQuick

// Badge « pilule » : un chiffre, une couleur, une lecture instantanée.
// Renseigner `pct` colore tout seul (vert au-dessus de la parité, rouge en
// dessous, neutre à 50 %) ; sinon on passe `label` et `tint` à la main.
Rectangle {
    id: pill

    readonly property Theme thm: Theme {}
    property int pct: -1                       // -1 = badge libre
    property string label: pct >= 0 ? pct + " %" : ""
    property color tint: pct >= 0 ? thm.pctColor(pct) : thm.textDim
    property bool glowing: false               // halo sur les valeurs saillantes
    property int fontSize: 11

    implicitWidth: txt.implicitWidth + 16
    implicitHeight: 20
    radius: height / 2
    color: Qt.alpha(tint, 0.13)
    border.width: 1
    border.color: Qt.alpha(tint, 0.32)

    GlowRing {
        anchors.fill: parent
        cornerRadius: pill.radius
        glowColor: pill.tint
        spread: 5
        intensity: pill.glowing ? 0.28 : 0.0
    }

    Text {
        id: txt
        anchors.centerIn: parent
        text: pill.label
        color: pill.tint
        font.pixelSize: pill.fontSize
        font.bold: true
    }
}
