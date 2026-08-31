import QtQuick

// Aperçu de carte au survol : le rendu officiel, plus — pour les cartes à
// résurrection — la liste EXACTE de ce qu'elles peuvent ramener (calculée sur
// les serviteurs réellement morts/joués cette partie, cf. pools.py).
//
// Quand le rendu officiel n'existe pas (jetons internes, et surtout les
// ENCHANTEMENTS qui portent les « effets en jeu »), on dessine une fiche de
// repli avec le nom et le TEXTE DE RÈGLES de la carte : sans elle, survoler
// « Âme brisée » ne donnait rien du tout.
Window {
    id: preview

    property string cardId: ""
    property bool opponentSide: false
    property bool anchorLeft: true   // aperçu posé à gauche de son panneau ?
    property var pool: emptyPool
    property string draw: ""
    // Texte à afficher SOUS la carte : le libellé propre d'un effet en jeu,
    // quand l'aperçu montre déjà sa carte source.
    property string note: ""

    readonly property var emptyPool: ({ "label": "", "entries": [] })
    readonly property var emptyInfo: ({ "name": "", "text": "", "cost": -1 })
    property var info: emptyInfo
    readonly property int cardHeight: 336
    readonly property bool hasPool: pool.label !== "" && pool.entries.length > 0

    // recalculé à chaque survol : le pool bouge à mesure que des serviteurs meurent
    onCardIdChanged: {
        pool = cardId !== "" ? tracker.poolFor(cardId, opponentSide) : emptyPool
        draw = (cardId !== "" && !opponentSide) ? tracker.drawChance(cardId) : ""
        info = cardId !== "" ? tracker.cardInfo(cardId) : emptyInfo
    }

    width: 240
    readonly property bool hasDraw: draw !== ""
    readonly property bool hasNote: note !== ""
    // le rendu officiel a-t-il abouti ? sinon, fiche de repli
    readonly property bool artOk: art.status === Image.Ready
    // Le rendu officiel vient du RÉSEAU : entre l'ouverture de la fenêtre et
    // l'arrivée de l'image, il s'écoule un aller-retour. Sans cet état, la
    // hauteur retombait à zéro pendant ce temps et la fenêtre s'affichait en
    // filet de quelques pixels — d'où des aperçus qui « marchaient une fois
    // sur deux » selon que l'image arrivait avant ou après le survol.
    readonly property bool artLoading: cardId !== "" && art.status === Image.Loading
    readonly property bool hasFallback: !artOk && !artLoading && cardId !== ""
                                        && (info.name !== "" || info.text !== "")
    // jamais 0 : une fenêtre sans hauteur n'est pas mappée par le compositeur
    height: Math.max(1, head.height + (hasNote ? noteBox.height + 6 : 0)
                        + (hasPool ? poolBox.height + 8 : 0) + (hasDraw ? 26 : 0))
    color: "transparent"
    title: "Cairn · aperçu"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
           | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus

    Item {
        id: head
        width: parent.width
        // On RÉSERVE la hauteur de la carte dès qu'un survol commence, sans
        // attendre l'image : mieux vaut un cadre vide pendant 200 ms qu'une
        // fenêtre invisible. Elle se rabat sur la fiche de repli si le rendu
        // n'existe pas (jetons, enchantements).
        height: (preview.artOk || preview.artLoading) ? preview.cardHeight
              : (preview.hasFallback ? fallback.height : 0)

        Image {
            id: art
            anchors.fill: parent
            fillMode: Image.PreserveAspectFit
            // rendu officiel HearthstoneJSON, en français, mis en cache par Qt
            source: preview.cardId !== ""
                ? "https://art.hearthstonejson.com/v1/render/latest/"
                  + tracker.cardLocale + "/256x/" + preview.cardId + ".png"
                : ""
            asynchronous: true
            visible: preview.artOk
        }

        // ---- fiche de repli : nom + texte de règles -------------------------
        Rectangle {
            id: fallback
            visible: preview.hasFallback
            width: parent.width
            height: fbCol.implicitHeight + 20
            radius: 10
            color: "#0f1117"
            opacity: 0.97
            border.color: "#4a5163"
            border.width: 1

            Column {
                id: fbCol
                anchors.fill: parent
                anchors.margins: 10
                spacing: 6

                Row {
                    spacing: 6
                    Rectangle {
                        visible: preview.info.cost >= 0
                        width: 18; height: 18; radius: 9
                        color: "#2b4d8f"
                        Text {
                            anchors.centerIn: parent
                            text: preview.info.cost
                            color: "white"
                            font.pixelSize: 10
                            font.bold: true
                        }
                    }
                    Text {
                        text: preview.info.name
                        color: "#e6e9f0"
                        font.pixelSize: 13
                        font.bold: true
                        width: fbCol.width - 24
                        wrapMode: Text.WordWrap
                    }
                }
                Text {
                    visible: preview.info.text !== ""
                    text: preview.info.text
                    color: "#c2c9d6"
                    font.pixelSize: 11
                    width: fbCol.width
                    wrapMode: Text.WordWrap
                }
            }
        }
    }

    // ---- libellé de l'effet en jeu, sous sa carte source -------------------
    Rectangle {
        id: noteBox
        visible: preview.hasNote
        anchors.top: head.bottom
        anchors.topMargin: 6
        width: parent.width
        height: noteText.implicitHeight + 12
        radius: 8
        color: "#0f1117"
        opacity: 0.97
        border.color: "#e08a2e"
        Text {
            id: noteText
            anchors.fill: parent
            anchors.margins: 6
            text: preview.note
            color: "#e6e9f0"
            font.pixelSize: 10
            wrapMode: Text.WordWrap
        }
    }

    Rectangle {
        id: drawBox
        visible: preview.hasDraw
        anchors.top: preview.hasNote ? noteBox.bottom : head.bottom
        anchors.topMargin: 4
        width: parent.width
        height: 22
        radius: 8
        color: "#0f1117"
        opacity: 0.97
        border.color: "#262b38"
        Text {
            anchors.centerIn: parent
            text: (tracker.language === "en" ? "next draw: " : "prochaine pioche : ")
                  + preview.draw
            color: "#8b93a7"
            font.pixelSize: 10
        }
    }

    Rectangle {
        id: poolBox
        visible: preview.hasPool
        anchors.top: preview.hasDraw ? drawBox.bottom
                   : (preview.hasNote ? noteBox.bottom : head.bottom)
        anchors.topMargin: 8
        width: parent.width
        height: poolCol.implicitHeight + 16
        radius: 10
        color: "#0f1117"
        opacity: 0.97
        border.color: "#e08a2e"
        border.width: 1

        Column {
            id: poolCol
            anchors.fill: parent
            anchors.margins: 8
            spacing: 3

            Text {
                text: (tracker.language === "en" ? "CAN RESURRECT — " : "PEUT RESSUSCITER — ")
                      + preview.pool.label
                color: "#e08a2e"
                font.pixelSize: 9
                font.bold: true
                font.letterSpacing: 1
                width: parent.width
                wrapMode: Text.WordWrap
            }

            Repeater {
                model: preview.pool.entries
                delegate: Row {
                    spacing: 6
                    Rectangle {
                        width: 16; height: 16; radius: 4
                        color: "#2b4d8f"
                        Text {
                            anchors.centerIn: parent
                            text: modelData.cost
                            color: "white"
                            font.pixelSize: 9
                            font.bold: true
                        }
                    }
                    Text {
                        text: modelData.name + (modelData.count > 1
                                                ? " ×" + modelData.count : "")
                        color: "#e6e9f0"
                        font.pixelSize: 11
                    }
                }
            }
        }
    }
}
