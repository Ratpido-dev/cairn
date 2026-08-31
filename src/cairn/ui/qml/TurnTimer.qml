import QtQuick

// Chrono de tour, sorti du panneau deck pour devenir déplaçable.
//
// Il était coincé tout en bas du panneau, donc invisible dès qu'une partie
// s'allongeait et poussait les sections sous la ligne de flottaison — alors
// que c'est précisément en partie longue qu'on surveille le temps de réflexion.
FloatingWindow {
    id: clock
    widgetName: "timer"
    title: "Cairn · chrono"
    defaultX: Math.round(Screen.width * 0.66)
    defaultY: Math.round(Screen.height * 0.74)

    visible: tracker.hsRunning && tracker.inGame && tracker.gameDuration !== ""

    readonly property int innerW: 150
    width: innerW * u
    height: 46 * u

    Rectangle {
        width: clock.innerW
        height: 46
        scale: clock.u
        transformOrigin: Item.TopLeft
        radius: 8
        color: clock.bg
        opacity: 0.94
        border.color: clock.line
        border.width: 1

        DragHandler { target: null; onActiveChanged: clock.grabbed(active) }

        // Ancrages plutôt qu'un Row à ressort : la durée de partie est calée à
        // DROITE, sans quoi elle sortait du cadre dès qu'elle passait l'heure
        // (« 6:3 » au lieu de « 6:35 », vu au rendu).
        Column {
            anchors.centerIn: parent
            width: parent.width - 16
            spacing: 3

            Item {
                width: parent.width
                height: 14

                Row {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 5
                    Text {
                        text: (tracker.language === "en" ? "Turn " : "Tour ")
                              + tracker.turnCount
                        color: clock.text
                        font.pixelSize: 11
                        font.bold: true
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    // pastille : à qui de jouer, visible du coin de l'œil
                    Rectangle {
                        width: 7
                        height: 7
                        radius: 3.5
                        color: tracker.myTurn ? clock.good : clock.bad
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: tracker.turnDuration
                        color: clock.muted
                        font.pixelSize: 11
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                Text {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    text: tracker.gameDuration
                    color: clock.muted
                    font.pixelSize: 11
                    font.bold: true
                }
            }

            // temps de réflexion cumulé : qui traîne, et de combien
            Item {
                width: parent.width
                height: 13

                Row {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4
                    Text {
                        text: tracker.language === "en" ? "me" : "moi"
                        color: clock.good
                        font.pixelSize: 10
                    }
                    Text {
                        text: tracker.myThinkTime
                        color: clock.muted
                        font.pixelSize: 10
                        font.bold: true
                    }
                }
                Row {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4
                    Text {
                        text: tracker.oppThinkTime
                        color: clock.muted
                        font.pixelSize: 10
                        font.bold: true
                    }
                    Text {
                        text: tracker.language === "en" ? "them" : "lui"
                        color: clock.bad
                        font.pixelSize: 10
                    }
                }
            }
        }
    }
}
