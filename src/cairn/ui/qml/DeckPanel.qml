import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic

Window {
    id: root
    readonly property real u: tracker.panelScale  // échelle réglée au launcher
    width: 300 * u
    // grandit avec le contenu jusqu'au bas de l'écran, ensuite on défile
    height: Math.min((Screen.height - 120) / u, content.implicitHeight + 24) * u
    x: Screen.width - width - 24
    y: 80
    visible: tracker.hsRunning && tracker.inGame
    title: "Cairn · deck"
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint

    // carte survolée → aperçu (fenêtre séparée, à gauche du panneau)
    property string hoverCard: ""
    // texte à joindre à l'aperçu : le libellé propre d'un effet en jeu, dont
    // l'aperçu montre la carte source
    property string hoverNote: ""
    function setHover(cardId, note) {
        root.hoverCard = cardId
        root.hoverNote = cardId === "" ? "" : (note === undefined ? "" : note)
    }

    // ---- palette : voir Theme.qml (source unique du design system) ---------
    readonly property Theme thm: Theme {}
    readonly property color bg: thm.bg
    readonly property color bgSoft: thm.raised
    readonly property color line: thm.lineSolid
    readonly property color text: thm.text
    readonly property color muted: thm.textDim
    readonly property color accent: thm.gold   // la braise de l'âtre
    readonly property color good: thm.good
    readonly property color bad: thm.bad

    // code couleur de rareté HS : gris / bleu / violet / orange
    function rarityColor(r) {
        return r === "LEGENDARY" ? "#ffa030"
             : r === "EPIC" ? "#c07bff"
             : r === "RARE" ? "#4da6ff"
             : "#c2c9d6"
    }

    Rectangle {
        width: 300
        height: root.height / root.u
        scale: root.u
        transformOrigin: Item.TopLeft
        radius: 12
        color: root.bg
        opacity: 0.96
        border.color: root.line
        border.width: 1

        ColumnLayout {
            id: content
            anchors.fill: parent
            anchors.margins: 12
            spacing: 8

            // ---- en-tête ---------------------------------------------------
            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                // le déplacement de fenêtre vit ici : ailleurs il entrerait en
                // conflit avec le défilement du corps
                // (target: null — sinon le contenu dérive dans la fenêtre)
                DragHandler {
                    target: null
                    onActiveChanged: if (active) root.startSystemMove()
                }
                Rectangle { width: 4; height: 30; radius: 2; color: root.accent }
                ColumnLayout {
                    spacing: 0
                    Layout.fillWidth: true
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        // Le titre ouvre le choix du deck. Nécessaire hors
                        // des files d'attente (parties amicales) : le jeu n'y
                        // journalise pas la liste choisie, et la déduction par
                        // les cartes ne tranche pas quand deux listes du joueur
                        // se ressemblent trop — deux variantes d'un archétype.
                        Text {
                            id: titreDeck
                            text: tracker.deckName
                                  + (tracker.forcedDeck !== "" ? "  ·" : "")
                            color: choixDeck.hovered ? root.accent : root.text
                            font.pixelSize: 15
                            font.bold: true
                            elide: Text.ElideRight
                            Layout.fillWidth: true

                            HoverHandler {
                                id: choixDeck
                                cursorShape: Qt.PointingHandCursor
                                enabled: tracker.playerDecks.length > 0
                            }
                            TapHandler {
                                enabled: choixDeck.enabled
                                onTapped: menuDecks.popup()
                            }
                            Menu {
                                id: menuDecks
                                Repeater {
                                    model: tracker.playerDecks
                                    delegate: MenuItem {
                                        required property string modelData
                                        text: (modelData === tracker.forcedDeck
                                               ? "\u2713  " : "     ") + modelData
                                        onTriggered: tracker.forceDeck(modelData)
                                    }
                                }
                            }
                        }
                        // bilan du deck : « le deck marche-t-il ? », à côté du
                        // matchup en dessous qui dit « ce duel est-il jouable ? »
                        Text {
                            visible: tracker.deckRecord !== ""
                            text: tracker.deckRecord
                            color: root.muted
                            font.pixelSize: 11
                        }
                    }
                    Text {
                        visible: tracker.opponentName !== ""
                        text: "vs " + tracker.opponentName
                              + (tracker.vsClassRecord !== "" ? " (" + tracker.vsClassRecord + ")" : "")
                        color: root.muted
                        font.pixelSize: 11
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }
                // copier le deckcode : il est en clair dans Decks.log, le
                // joueur n'a sinon aucun moyen de récupérer la liste exacte
                // qu'il vient de jouer sans repasser par le client
                Rectangle {
                    id: copyBtn
                    visible: tracker.hasDeckcode
                    width: 22
                    height: 22
                    radius: 6
                    color: copyHover.hovered ? root.bgSoft : "transparent"
                    border.color: root.line
                    border.width: 1

                    property bool done: false
                    HoverHandler { id: copyHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        onTapped: {
                            tracker.copyDeckcode()
                            copyBtn.done = true
                            copiedTimer.restart()
                        }
                    }
                    // retour visuel : sans lui, rien ne dit que le clic a pris
                    Timer {
                        id: copiedTimer
                        interval: 1200
                        onTriggered: copyBtn.done = false
                    }
                    Text {
                        anchors.centerIn: parent
                        text: copyBtn.done ? "✓" : "⧉"
                        color: copyBtn.done ? root.good : root.muted
                        font.pixelSize: 12
                    }
                }

                Rectangle {
                    visible: tracker.hasGame
                    radius: 10
                    color: tracker.result === "WON" ? root.good
                         : tracker.result === "LOST" ? root.bad : root.bgSoft
                    border.color: root.line
                    width: countText.implicitWidth + 16
                    height: 22
                    Text {
                        id: countText
                        anchors.centerIn: parent
                        readonly property bool en: tracker.language === "en"
                        text: tracker.result === "WON" ? "GG"
                            : tracker.result === "LOST" ? (en ? "loss" : "défaite")
                            : tracker.remainingTotal + (en ? " left" : " au deck")
                        color: tracker.result === "" ? root.text : "#10131a"
                        font.pixelSize: 11
                        font.bold: tracker.result !== ""
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: root.line }

            // Corps défilable : avec les sections « en main », les bouts de
            // deck, l'atlas et le cimetière, une partie longue dépasse la
            // hauteur d'écran allouée — sans
            // Flickable, la fin de la liste devenait tout simplement inatteignable.
            Flickable {
                id: scroller
                objectName: "deckScroller"   // repéré par les tests de non-régression
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

                    // ---- liste du deck --------------------------------------------
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 5
                        Text {
                            text: deckList.visible ? "▾" : "▸"
                            color: root.muted
                            font.pixelSize: 9
                            opacity: 0.8
                        }
                        Text {
                            text: (tracker.language === "en" ? "IN DECK (" : "EN DECK (")
                                  + tracker.remainingTotal + ")"
                            color: root.muted
                            font.pixelSize: 10
                            font.bold: true
                            font.letterSpacing: 1
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: root.line }
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: deckList.visible = !deckList.visible }
                    }

                    ListView {
                        id: deckList
                        Layout.fillWidth: true
                        // ColumnLayout dimensionne sur l'implicitHeight des enfants — et
                        // celui d'une ListView vaut 0 par défaut → fenêtre écrasée sinon.
                        // (déterministe : contentHeight est paresseux tant que la fenêtre
                        // est petite, les delegates n'existant pas encore)
                        implicitHeight: visible ? count * 28 : 0
                        model: tracker.deckModel
                        spacing: 2
                        clip: true
                        delegate: CardRow {
                            width: deckList.width
                            cardId: model.cardId
                            label: model.name
                            cost: model.cost
                            rarity: model.rarity
                            count: model.remaining
                            // un exemplaire restant sur deux : c'est l'info utile, pas « ×1 »
                            showCount: model.remaining > 1
                            spent: model.remaining === 0
                            struck: model.remaining === 0
                            // carte arrivée en cours de partie : icône cadeau,
                            // et la carte qui l'a offerte au bout de la ligne
                            gift: model.gift
                            origin: model.origin
                            unknown: model.cardId === ""
                            base: root.bgSoft
                            accent: root.accent
                            onHoveredChanged: (inside) => {
                                if (inside)
                                    root.setHover(model.cardId, "")
                                else if (root.hoverCard === model.cardId)
                                    root.setHover("", "")
                            }
                        }
                    }

                    // Ce qui pèse sur toute la partie sans être un serviteur :
                    // Protection d'Amara, Atlas, pouvoir héroïque amélioré…
                    // Sinon on découvre l'effet au moment où on le subit.
                    CardList {
                        title: tracker.language === "en" ? "EFFECTS IN PLAY" : "EFFETS EN JEU"
                        model: tracker.myEffectsModel
                        tint: root.accent
                        maxRows: 5
                        showOrigin: true
                        onCardHovered: (cardId, note) => root.setHover(cardId, note)
                    }

                    // (« ENTRÉES » a disparu le 14/08/2026 : les cartes ajoutées
                    // en cours de partie sont désormais DANS la liste du deck,
                    // marquées d'un cadeau — c'est là qu'on les cherche.)

                    // Ce que rejouerait une Confrontation des Tol'vir. Tenue en
                    // permanence : quand la carte tombe, il est trop tard pour
                    // choisir autrement ses cartes à (1).
                    CardList {
                        title: tracker.language === "en" ? "MY 1-COST PLAYED"
                                                         : "MES CARTES À (1) JOUÉES"
                        model: tracker.myReplayModel
                        tint: "#c9a227"
                        maxRows: 8
                        onCardHovered: (cardId, note) => root.setHover(cardId, note)
                    }

                    // Bouts du deck connus : HS masque l'ordre du deck, mais on
                    // sait où un effet a posé sa carte tant que rien n'a mélangé.
                    EntryList {
                        title: tracker.language === "en" ? "TOP OF DECK" : "HAUT DU DECK"
                        glyph: "▲"
                        model: tracker.deckTopModel
                        tint: "#5fb573"
                        bgSoft: root.bgSoft
                        line: root.line
                        onCardHovered: (cardId, note) => root.setHover(cardId, note)
                    }

                    EntryList {
                        title: tracker.language === "en" ? "BOTTOM OF DECK" : "FOND DU DECK"
                        glyph: "▼"
                        model: tracker.deckBottomModel
                        tint: "#6bb6ff"
                        bgSoft: root.bgSoft
                        line: root.line
                        onCardHovered: (cardId, note) => root.setHover(cardId, note)
                    }

                    // ce que je tiens, et ce qui est déjà sorti — le découpage que
                    // Firestone met en avant, et qui manquait à Cairn
                    CardList {
                        visible: tracker.myHandEnabled
                        title: tracker.language === "en" ? "IN HAND" : "EN MAIN"
                        model: tracker.myHandModel
                        tint: "#5fb573"
                        maxRows: 10
                        showOrigin: true
                        onCardHovered: (cardId, note) => root.setHover(cardId, note)
                    }

                    // Ce que J'AI posé, dans la même forme que le panneau
                    // adverse. Sa main, on ne la voit pas ; la sienne, si —
                    // elle est à l'écran, sous les yeux. Ce qui est déjà sorti,
                    // en revanche, ne se relit nulle part une fois le tour
                    // passé.
                    CardList {
                        visible: tracker.myPlaysEnabled
                        title: tracker.language === "en" ? "CARDS I PLAYED"
                                                         : "MES CARTES JOUÉES"
                        model: tracker.myPlaysModel
                        tint: "#5fb573"
                        maxRows: 14
                        showOrigin: true
                        onCardHovered: (cardId, note) => root.setHover(cardId, note)
                    }

                    // familles à cocher : lesquels des dix Rafaam ai-je posés ?
                    Checklist {
                        model: tracker.myFamilyModel
                        sectionCount: tracker.myFamilySections
                        bgSoft: root.bgSoft
                        onCardHovered: (cardId, note) => root.setHover(cardId, note)
                    }

                    // file de MON atlas (Azalina peut avoir copié le Godfrey adverse)
                    CardList {
                        title: tracker.language === "en" ? "MY GODFREY ATLAS" : "MON ATLAS DE GODFREY"
                        model: tracker.myAtlasModel
                        tint: "#c9a227"
                        maxRows: 8
                        showRank: true
                        onCardHovered: (cardId, note) => root.setHover(cardId, note)
                    }

                    CardList {
                        title: tracker.language === "en" ? "MY GRAVEYARD" : "MON CIMETIÈRE"
                        model: tracker.myGraveyardModel
                        tint: root.muted
                        maxRows: 5
                        onCardHovered: (cardId, note) => root.setHover(cardId, note)
                    }

                    // (les cartes adverses vivent dans OppPanel.qml, à gauche de l'écran)
                }
            }
        }
    }

    // ---- aperçu de carte au survol (fenêtre à gauche du panneau) ----------
    CardPreview {
        visible: root.visible && root.hoverCard !== ""
        title: "Cairn · aperçu deck"
        cardId: root.hoverCard
        note: root.hoverNote
        opponentSide: false
        x: root.x - width - 8
        y: Math.min(root.y + 40, Screen.height - height - 20)
    }
}
