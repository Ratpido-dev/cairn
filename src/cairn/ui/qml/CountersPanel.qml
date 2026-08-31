import QtQuick
import QtQuick.Controls.Basic

// Panneau de compteurs : UNE boîte déplaçable qui grandit quand un compteur
// s'arme, au lieu du bandeau pleine largeur qui masquait le haut du plateau.
//
// Deux colonnes moi / adversaire, comme Firestone : le même compteur des deux
// camps tient sur une ligne, et le camp se lit par la POSITION plutôt que par
// un préfixe « moi »/« adv » répété à chaque ligne.
//
// Les points d'attaque n'y sont pas (cf. AttackBadge) : ici vivent les
// compteurs qu'on consulte, pas ceux qu'on relit sans arrêt.
FloatingWindow {
    id: panel
    widgetName: "counters"
    title: "Cairn · compteurs"
    defaultX: Math.round(Screen.width * 0.66)
    defaultY: 96

    // replié : on garde le titre sous la main sans le contenu
    property bool collapsed: false

    readonly property int rows: list.count
    visible: tracker.hsRunning && tracker.inGame && rows > 0

    readonly property int innerW: 186
    readonly property int colW: 46      // largeur d'une colonne de valeur
    width: innerW * u
    height: (header.height + (collapsed ? 0 : body.height + 8) + 12) * u

    Rectangle {
        width: panel.innerW
        height: header.height + (panel.collapsed ? 0 : body.height + 8) + 12
        scale: panel.u
        transformOrigin: Item.TopLeft
        radius: 10
        color: panel.bg
        opacity: 0.94
        border.color: panel.line
        border.width: 1

        // target: null — sinon le contenu dérive dans la fenêtre à chaque
        // déplacement jusqu'à sortir du cadre
        DragHandler { target: null; onActiveChanged: panel.grabbed(active) }

        Item {
            id: header
            x: 6
            y: 6
            width: parent.width - 12
            height: 30

            Text {
                anchors.left: parent.left
                y: 0
                text: tracker.language === "en" ? "COUNTERS" : "COMPTEURS"
                color: panel.muted
                font.pixelSize: 11
                font.bold: true
            }
            Text {
                anchors.right: parent.right
                y: 0
                text: panel.collapsed ? "▾" : "▴"
                color: panel.muted
                font.pixelSize: 11
                TapHandler { onTapped: panel.collapsed = !panel.collapsed }
            }

            // en-têtes de colonnes : ils remplacent les préfixes de chaque ligne
            Text {
                visible: !panel.collapsed
                x: parent.width - 2 * panel.colW
                y: 17
                width: panel.colW
                horizontalAlignment: Text.AlignHCenter
                text: tracker.language === "en" ? "me" : "moi"
                color: panel.good
                font.pixelSize: 9
                font.bold: true
            }
            Text {
                visible: !panel.collapsed
                x: parent.width - panel.colW
                y: 17
                width: panel.colW
                horizontalAlignment: Text.AlignHCenter
                text: tracker.language === "en" ? "opp" : "adv"
                color: panel.bad
                font.pixelSize: 9
                font.bold: true
            }
        }

        Column {
            id: body
            x: 6
            y: header.y + header.height + 2
            width: parent.width - 12
            spacing: 2
            visible: !panel.collapsed

            Repeater {
                id: list
                model: tracker.countersModel
                delegate: Rectangle {
                    id: row
                    width: body.width
                    height: 20
                    radius: 5
                    // la ligne s'allume dès qu'un des deux camps est en alerte
                    readonly property bool alerte: model.meAlert || model.oppAlert
                    color: alerte ? Qt.alpha(panel.accent, 0.12) : "transparent"
                    border.color: panel.accent
                    border.width: alerte ? 1 : 0

                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 6
                        anchors.right: cellMoi.left
                        anchors.verticalCenter: parent.verticalCenter
                        text: model.label
                        color: row.alerte ? panel.accent : panel.muted
                        font.pixelSize: 11
                        elide: Text.ElideRight
                    }

                    Text {
                        id: cellMoi
                        x: parent.width - 2 * panel.colW
                        width: panel.colW
                        anchors.verticalCenter: parent.verticalCenter
                        horizontalAlignment: Text.AlignHCenter
                        text: model.meText
                        color: model.meAlert ? panel.accent : panel.good
                        font.pixelSize: 11
                        font.bold: true
                        elide: Text.ElideRight
                    }
                    Text {
                        x: parent.width - panel.colW
                        width: panel.colW
                        anchors.verticalCenter: parent.verticalCenter
                        horizontalAlignment: Text.AlignHCenter
                        text: model.oppText
                        color: model.oppAlert ? panel.accent : panel.bad
                        font.pixelSize: 11
                        font.bold: true
                        elide: Text.ElideRight
                    }

                    // Infobulle : les phrases complètes des deux camps. Le
                    // libellé court suffit à l'œil, pas toujours à la mémoire.
                    HoverHandler { id: rowHover }
                    ToolTip.visible: rowHover.hovered && model.tip !== ""
                    ToolTip.text: model.tip
                    ToolTip.delay: 350
                }
            }
        }
    }
}
