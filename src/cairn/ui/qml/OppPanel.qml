import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic

// Panneau ADVERSAIRE — côté gauche de l'écran (le panneau joueur est à droite).
Window {
    id: opp
    readonly property real u: tracker.oppScale  // échelle réglée au launcher
    width: 260 * u
    // grandit avec le contenu jusqu'au bas de l'écran, ensuite on défile
    height: Math.min((Screen.height - 120) / u, content.implicitHeight + 24) * u
    x: 24
    y: 80
    visible: tracker.hsRunning && tracker.inGame && tracker.hasGame
             && tracker.oppPanelEnabled && oppList.count > 0
    title: "Cairn · adversaire"
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint

    property string hoverCard: ""
    // texte joint à l'aperçu : le libellé propre d'un effet en jeu, dont
    // l'aperçu montre la carte source
    property string hoverNote: ""
    function setHover(cardId, note) {
        opp.hoverCard = cardId
        opp.hoverNote = cardId === "" ? "" : (note === undefined ? "" : note)
    }

    // palette : voir Theme.qml (source unique du design system)
    readonly property Theme thm: Theme {}
    readonly property color bg: thm.bg
    readonly property color bgSoft: thm.raised
    readonly property color line: thm.lineSolid
    readonly property color text: thm.text
    readonly property color muted: thm.textDim
    readonly property color danger: thm.bad

    // code couleur de rareté HS : gris / bleu / violet / orange
    function rarityColor(r) {
        return r === "LEGENDARY" ? "#ffa030"
             : r === "EPIC" ? "#c07bff"
             : r === "RARE" ? "#4da6ff"
             : "#c2c9d6"
    }

    Rectangle {
        width: 260
        height: opp.height / opp.u
        scale: opp.u
        transformOrigin: Item.TopLeft
        radius: 12
        color: opp.bg
        opacity: 0.96
        border.color: opp.line
        border.width: 1

        ColumnLayout {
            id: content
            anchors.fill: parent
            anchors.margins: 12
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                // le déplacement de fenêtre vit dans l'en-tête : ailleurs il
                // entrerait en conflit avec le défilement du corps
                // (target: null — sinon le contenu dérive dans la fenêtre)
                DragHandler {
                    target: null
                    onActiveChanged: if (active) opp.startSystemMove()
                }
                Rectangle { width: 4; height: 30; radius: 2; color: opp.danger }
                ColumnLayout {
                    spacing: 0
                    Layout.fillWidth: true
                    Text {
                        text: tracker.opponentName
                        color: opp.text
                        font.pixelSize: 14
                        font.bold: true
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    Text {
                        visible: tracker.opponentClass !== ""
                        text: tracker.opponentClass
                              + (tracker.vsClassRecord !== "" ? " · " + tracker.vsClassRecord : "")
                        color: opp.muted
                        font.pixelSize: 11
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: opp.line }

            // corps défilable — même raison que dans DeckPanel : contre un deck
            // bavard, la liste des cartes jouées dépasse la hauteur d'écran
            Flickable {
                id: scroller
                objectName: "oppScroller"
                Layout.fillWidth: true
                Layout.fillHeight: true
                implicitHeight: body.implicitHeight
                contentWidth: width
                contentHeight: body.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar {
                    policy: scroller.contentHeight > scroller.height
                            ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
                    width: 5
                }

                ColumnLayout {
                    id: body
                    width: scroller.width
                    spacing: 8

                Text {
                    text: (tracker.language === "en" ? "CARDS PLAYED (" : "CARTES JOUÉES (")
                          + oppList.count + ")"
                    color: opp.muted
                    font.pixelSize: 10
                    font.bold: true
                    font.letterSpacing: 1
                }

                // ce qu'il lui reste à poser dans une famille (Rafaam…)
                Checklist {
                    model: tracker.oppFamilyModel
                    sectionCount: tracker.oppFamilySections
                    bgSoft: opp.bgSoft
                    onCardHovered: (cardId, note) => opp.setHover(cardId, note)
                }

                // ce qui l'attend dans son atlas, dans l'ordre où il le recevra
                CardList {
                    title: tracker.language === "en" ? "THEIR GODFREY ATLAS" : "SON ATLAS DE GODFREY"
                    model: tracker.oppAtlasModel
                    tint: "#c9a227"
                    maxRows: 8
                    showRank: true
                    onCardHovered: (cardId, note) => opp.setHover(cardId, note)
                }

                // Ce qui pèse sur toute la partie sans être un serviteur.
                // Le survol montre la carte SOURCE de l'effet et son texte :
                // « Âme brisée » seule ne dit pas ce qu'elle fait.
                CardList {
                    title: tracker.language === "en" ? "EFFECTS IN PLAY" : "EFFETS EN JEU"
                    model: tracker.oppEffectsModel
                    tint: opp.danger
                    maxRows: 5
                    showOrigin: true
                    onCardHovered: (cardId, note) => opp.setHover(cardId, note)
                }

                // Ce que rejouerait sa Confrontation des Tol'vir. Affiché dès
                // qu'il est Chasseur, donc AVANT qu'il la pose : c'est le seul
                // moment où l'information sert encore à quelque chose.
                CardList {
                    title: tracker.language === "en" ? "THEIR 1-COST PLAYED"
                                                     : "SES CARTES À (1) JOUÉES"
                    model: tracker.oppReplayModel
                    tint: "#c9a227"
                    maxRows: 10
                    onCardHovered: (cardId, note) => opp.setHover(cardId, note)
                }

                // Ce qu'on a vu de SON deck : un effet a révélé l'identité de
                // quelques cartes qui y dorment encore. Rare, mais décisif.
                CardList {
                    title: tracker.language === "en" ? "KNOWN IN THEIR DECK"
                                                     : "CONNUES DANS SON DECK"
                    model: tracker.oppDeckModel
                    tint: "#c9a227"
                    maxRows: 6
                    showOrigin: true
                    onCardHovered: (cardId, note) => opp.setHover(cardId, note)
                }

                // (La main adverse n'est plus listée ici : elle occupait dix
                // lignes pour dire « ? carte cachée ». Elle vit désormais en
                // pastilles posées sous ses cartes, cf. OppHandDots.qml —
                // même information, à l'endroit où le regard est déjà.)

                CardList {
                    title: (tracker.language === "en" ? "POSSIBLE SECRETS · " : "SECRETS POSSIBLES · ")
                           + tracker.oppSecretCount
                           + (tracker.language === "en" ? " in play" : " en jeu")
                           // classe RÉELLE du secret posé quand le jeu l'a
                           // publiée : elle n'est pas toujours celle du héros
                           // d'en face, et la liste serait sinon incompréhensible
                           + (tracker.oppSecretClasses !== ""
                              ? " · " + tracker.oppSecretClasses : "")
                    model: tracker.secretsModel
                    tint: "#4da6ff"
                    maxRows: 8
                    strikeable: true
                    onCardHovered: (cardId, note) => opp.setHover(cardId, note)
                    onCardClicked: (cardId) => tracker.toggleSecretRuledOut(cardId)
                }

                ListView {
                    id: oppList
                    Layout.fillWidth: true
                    implicitHeight: count * 28
                    model: tracker.oppModel
                    spacing: 2
                    clip: true
                    delegate: CardRow {
                        width: oppList.width
                        cardId: model.cardId
                        label: model.label
                        cost: model.cost
                        rarity: model.rarity
                        count: model.count
                        // D'où vient la carte : icône cadeau + « ← Azalina ».
                        // Sans ça, dix cartes volées se lisaient comme dix
                        // cartes de son deck, et on comptait mal ce qu'il lui
                        // reste. Le mécanisme est le même que pour notre deck.
                        gift: model.gift !== undefined && model.gift
                        origin: model.origin === undefined ? "" : model.origin
                        base: opp.bgSoft
                        accent: opp.danger
                        // panneau plus étroit : on garde plus de fond sombre
                        fadeStart: 0.36
                        onHoveredChanged: (inside) => {
                            if (inside)
                                opp.setHover(model.cardId, "")
                            else if (opp.hoverCard === model.cardId)
                                opp.setHover("", "")
                        }
                    }
                }

                CardList {
                    title: tracker.language === "en" ? "GRAVEYARD" : "CIMETIÈRE"
                    model: tracker.oppGraveyardModel
                    tint: opp.muted
                    onCardHovered: (cardId, note) => opp.setHover(cardId, note)
            }
                }
            }
        }
    }

    // ---- aperçu de carte au survol (à droite du panneau adversaire) -------
    CardPreview {
        visible: opp.visible && opp.hoverCard !== ""
        title: "Cairn · aperçu adversaire"
        cardId: opp.hoverCard
        note: opp.hoverNote
        opponentSide: true
        anchorLeft: false
        x: opp.x + opp.width + 8
        y: Math.min(opp.y + 40, Screen.height - height - 20)
    }
}
