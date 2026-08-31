import QtQuick

// Médaillon de classe : disque teinté aux couleurs de la classe, anneau
// lumineux, monogramme au centre.
//
// Aucune image : Cairn n'embarque pas de portraits de héros (et n'a pas à
// télécharger 11 PNG pour une liste de statistiques). Le monogramme est tiré
// de la CLÉ de classe, donc stable en français comme en anglais.
Item {
    id: avatar

    readonly property Theme thm: Theme {}
    property string classKey: ""
    property int size: 26
    property bool highlighted: false

    readonly property color tint: thm.classColor(classKey)

    implicitWidth: size
    implicitHeight: size

    Rectangle {
        id: disc
        anchors.fill: parent
        radius: width / 2
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.alpha(avatar.tint, 0.30) }
            GradientStop { position: 1.0; color: Qt.alpha(avatar.tint, 0.08) }
        }
        border.width: 1
        border.color: Qt.alpha(avatar.tint, avatar.highlighted ? 0.85 : 0.45)

        GlowRing {
            anchors.fill: parent
            cornerRadius: disc.radius
            glowColor: avatar.tint
            spread: 5
            intensity: avatar.highlighted ? 0.38 : 0.18
        }

        Text {
            anchors.centerIn: parent
            text: avatar.thm.classMono(avatar.classKey)
            color: avatar.tint
            font.pixelSize: Math.round(avatar.size * 0.38)
            font.bold: true
            font.letterSpacing: 0.5
        }
    }
}
