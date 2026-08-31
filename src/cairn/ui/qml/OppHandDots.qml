import QtQuick

// Pastilles de la MAIN ADVERSE, à poser sous son éventail de cartes.
//
// Le panneau de gauche listait sa main sur dix lignes dont neuf disaient
// « ? carte cachée » : beaucoup de place pour peu d'information, et loin de
// l'endroit où le regard est déjà. Ici, une pastille par carte tenue, en arc
// de cercle comme l'éventail du jeu, avec ce que les journaux savent vraiment :
//
//   • le TOUR d'arrivée en main (« M » = gardée au mulligan) ;
//   • 🎁 quand la carte a été CRÉÉE par un effet — survol : la carte créatrice ;
//   • l'illustration quand son identité est connue — survol : la carte.
//
// Placement : sous Wayland un client ne peut pas se placer lui-même, donc on
// se cale UNE fois à la souris et KWin retient (règle cairn-pos-main, mode
// Remember). Largeur FIXE et pastilles centrées : sans ça, le bandeau
// s'allongerait vers la droite à chaque carte piochée et se décalerait sous
// les yeux du joueur.
FloatingWindow {
    id: hand
    widgetName: "opphand"
    title: "Cairn · main adverse"
    defaultX: Math.round(Screen.width / 2 - 190)
    defaultY: Math.round(Screen.height * 0.11)

    property string hoverCard: ""
    property string hoverNote: ""
    // Index de la pastille survolée, et pas seulement sa carte : deux cartes
    // cachées ont le même aperçu (aucun), donc quitter l'une effacerait le
    // survol de l'autre au passage de la souris.
    property int hoverIndex: -1

    readonly property int dotW: 34
    readonly property int dotH: 26
    readonly property int gap: 4
    // dix emplacements : c'est la main maximale de Hearthstone, et une largeur
    // fixe garde le bandeau centré au lieu de le faire pousser vers la droite à
    // chaque pioche. Rançon assumée : la fenêtre reste sensible à la souris sur
    // toute sa largeur, d'où sa faible hauteur et l'interrupteur du launcher.
    readonly property int innerW: 10 * (dotW + gap)
    // creux de l'arc, en pixels : la carte du milieu descend le plus bas, comme
    // dans l'éventail du jeu. Normalisé sur le nombre de cartes, sinon une main
    // de deux cartes serait plate et une main de dix tomberait de 50 px.
    readonly property real arc: 12
    readonly property int innerH: dotH + 22

    visible: tracker.hsRunning && tracker.inGame && tracker.handDotsEnabled
             && dots.count > 0

    width: innerW * u
    height: innerH * u

    Item {
        id: board
        width: hand.innerW
        height: hand.innerH
        scale: hand.u
        transformOrigin: Item.TopLeft

        // poignée de déplacement : sans surface opaque, il n'y aurait rien à
        // saisir entre deux pastilles
        Rectangle {
            id: handle
            anchors.centerIn: parent
            width: Math.max(60, dots.count * (hand.dotW + hand.gap) + 14)
            height: hand.innerH - 4
            radius: 12
            color: hand.bg
            opacity: 0.34
            border.color: hand.line
            border.width: 1
            DragHandler { target: null; onActiveChanged: hand.grabbed(active) }
        }

        Item {
            id: row
            anchors.horizontalCenter: parent.horizontalCenter
            y: 2
            width: dots.count * (hand.dotW + hand.gap)
            height: hand.innerH

            Repeater {
                id: dots
                model: tracker.oppHandSlotsModel

                delegate: Item {
                    id: dot
                    width: hand.dotW
                    height: hand.dotH
                    x: index * (hand.dotW + hand.gap)
                    // arc : centre bas, extrémités hautes (l'éventail adverse
                    // pivote autour d'un point situé plus haut que l'écran)
                    y: {
                        var c = (dots.count - 1) / 2
                        if (c <= 0)
                            return 0
                        var d = (index - c) / c
                        return Math.round(hand.arc * (1 - d * d))
                    }

                    // ce que le survol doit montrer : la carte si on la
                    // connaît, sinon celle qui l'a créée (mieux que rien —
                    // savoir qu'il tient « quelque chose d'Azalina » oriente
                    // déjà les décisions)
                    readonly property string previewId:
                        model.cardId !== "" ? model.cardId
                        : (model.creatorId !== undefined ? model.creatorId : "")
                    readonly property string note: {
                        var quand = model.badge === "M"
                            ? (tracker.language === "en" ? "kept at mulligan"
                                                         : "gardée au mulligan")
                            : (model.badge === "" ? ""
                               : (tracker.language === "en" ? "arrived turn "
                                                            : "arrivée au tour ")
                                 + model.badge)
                        var qui = model.origin !== ""
                            ? (tracker.language === "en" ? "created by " : "créée par ")
                              + model.origin
                            : ""
                        return [quand, qui].filter(function (s) { return s !== "" })
                                           .join(" · ")
                    }

                    Rectangle {
                        id: pill
                        anchors.fill: parent
                        // pilule et non disque parfait : les tuiles d'art de
                        // HearthstoneJSON sont des bandeaux 256×36, illisibles
                        // dans un rond, et un masque circulaire exigerait un
                        // shader — or aucun shader ne rend dans Cairn
                        radius: 9
                        color: hand.bg
                        opacity: 0.96
                        border.width: 1
                        border.color: model.known ? "#ffbe55"
                                    : (model.created ? "#c07bff" : hand.line)
                        clip: true

                        Image {
                            anchors.fill: parent
                            fillMode: Image.PreserveAspectCrop
                            source: (tracker.tileRevision >= 0 && model.cardId !== "")
                                    ? tracker.tile(model.cardId) : ""
                            visible: status === Image.Ready
                            opacity: 0.75
                        }

                        // voile sombre sous le chiffre : sur une illustration
                        // claire, un « 4 » blanc disparaît
                        Rectangle {
                            anchors.fill: parent
                            color: "#0b0e15"
                            opacity: model.cardId !== "" ? 0.35 : 0.0
                        }

                        // Le TOUR d'arrivée reste au centre même pour une carte
                        // créée : « il tient ça depuis le tour 3 » vaut autant
                        // que « on la lui a donnée ». Le cadeau passe en coin —
                        // les deux informations tiennent ensemble.
                        Text {
                            anchors.centerIn: parent
                            text: model.badge !== "" ? model.badge
                                  : (model.created ? "🎁" : "·")
                            color: model.badge === "M" ? "#8b93a7" : "#e6e9f0"
                            font.pixelSize: 11
                            font.bold: true
                            style: Text.Outline
                            styleColor: Qt.alpha("#000000", 0.85)
                        }

                        Text {
                            visible: model.created && model.badge !== ""
                            text: "🎁"
                            font.pixelSize: 8
                            x: parent.width - width - 2
                            y: 1
                        }

                        HoverHandler {
                            onHoveredChanged: {
                                if (hovered) {
                                    hand.hoverIndex = index
                                    hand.hoverCard = dot.previewId
                                    hand.hoverNote = dot.note
                                } else if (hand.hoverIndex === index) {
                                    hand.hoverIndex = -1
                                    hand.hoverCard = ""
                                    hand.hoverNote = ""
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // ---- aperçu au survol, sous le bandeau --------------------------------
    // Une pastille survolée sans rien à montrer (carte inconnue, pas de
    // créatrice) garde quand même son infobulle : c'est le rôle de `note`.
    CardPreview {
        visible: hand.visible && (hand.hoverCard !== "" || hand.hoverNote !== "")
        title: "Cairn · aperçu main"
        cardId: hand.hoverCard
        note: hand.hoverNote
        opponentSide: true
        x: Math.min(Math.max(0, hand.x), Screen.width - width - 8)
        y: hand.y + hand.height + 6
    }
}
