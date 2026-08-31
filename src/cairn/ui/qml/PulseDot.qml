import QtQuick

// Pastille d'état, avec onde qui pulse quand la connexion est vivante.
// Vert = Hearthstone détecté, orange = en attente, gris = inconnu.
Item {
    id: dot

    property color tint: "#10B981"
    property bool pulsing: true
    property real coreSize: 7

    implicitWidth: coreSize * 2.6
    implicitHeight: coreSize * 2.6

    // onde : un anneau qui grandit et s'efface, redémarré en boucle
    Rectangle {
        id: wave
        anchors.centerIn: parent
        width: dot.coreSize
        height: width
        radius: width / 2
        color: "transparent"
        border.width: 1.5
        border.color: dot.tint
        visible: dot.pulsing
        opacity: 0

        SequentialAnimation on opacity {
            running: dot.pulsing
            loops: Animation.Infinite
            NumberAnimation { from: 0.55; to: 0; duration: 1600; easing.type: Easing.OutQuad }
            PauseAnimation { duration: 200 }
        }
        SequentialAnimation on width {
            running: dot.pulsing
            loops: Animation.Infinite
            NumberAnimation {
                from: dot.coreSize
                to: dot.coreSize * 2.6
                duration: 1600
                easing.type: Easing.OutQuad
            }
            PauseAnimation { duration: 200 }
        }
    }

    // halo fixe, pour que la pastille « brille » même à l'arrêt de l'onde
    Rectangle {
        anchors.centerIn: parent
        width: dot.coreSize + 5
        height: width
        radius: width / 2
        color: Qt.alpha(dot.tint, 0.18)
    }

    Rectangle {
        anchors.centerIn: parent
        width: dot.coreSize
        height: width
        radius: width / 2
        color: dot.tint
    }
}
