import QtQuick

// « Secrets possibles » détaché du panneau latéral, à poser contre le héros
// adverse — là où le regard va déjà quand un secret se déclenche.
//
// Les lignes réutilisent CardRow, comme les listes du deck : illustration de
// la carte, gemme de mana, nom. Un nom seul ne se reconnaît pas assez vite au
// milieu d'un tour.
//
// Deux façons d'écarter un candidat, qui se cumulent :
//   — le tracker le grise tout seul quand un déclencheur inconditionnel est
//     passé sans rien faire (cf. secrets.py, volontairement partiel) ;
//   — le joueur le barre d'un clic, et sa déduction prime toujours.
FloatingWindow {
    id: pop
    widgetName: "secrets"
    title: "Cairn · secrets"
    defaultX: Math.round(Screen.width * 0.50)
    defaultY: Math.round(Screen.height * 0.06)

    // carte survolée → aperçu, à droite du popup
    property string hoverCard: ""

    readonly property int innerW: 210
    // pas de secret en jeu, pas de fenêtre : elle n'a rien à dire 95 % du temps
    visible: tracker.hsRunning && tracker.inGame
             && tracker.oppSecretCount > 0 && list.count > 0

    width: innerW * u
    height: (header.height + body.height + 16) * u

    Rectangle {
        width: pop.innerW
        height: header.height + body.height + 16
        scale: pop.u
        transformOrigin: Item.TopLeft
        radius: 8
        color: pop.bg
        opacity: 0.95
        border.color: "#4da6ff"
        border.width: 1

        DragHandler { target: null; onActiveChanged: pop.grabbed(active) }

        Text {
            id: header
            x: 8
            y: 6
            width: parent.width - 16
            height: 16
            // la classe du secret POSÉ quand HS l'a publiée : elle n'est pas
            // toujours celle du héros d'en face (Chasseur qui pose un secret
            // de Mage), et la liste serait sinon incompréhensible
            text: "SECRETS · " + tracker.oppSecretCount
                  + (tracker.oppSecretClasses !== ""
                     ? " · " + tracker.oppSecretClasses : "")
            color: "#4da6ff"
            font.pixelSize: 11
            font.bold: true
            elide: Text.ElideRight
        }

        Column {
            id: body
            x: 6
            y: header.y + header.height + 5
            width: parent.width - 12
            spacing: 2

            Repeater {
                id: list
                model: tracker.secretsModel
                delegate: CardRow {
                    width: body.width
                    implicitHeight: 24
                    cardId: model.cardId
                    label: model.label
                    cost: model.cost
                    // écarté : éteint ET barré, qu'il l'ait été à la main ou
                    // par déduction — dans les deux cas il reste visible
                    spent: model.ruledOut
                    struck: model.ruledOut
                    base: "#171a23"
                    accent: "#4da6ff"
                    showCount: false
                    clickable: true
                    onHoveredChanged: (inside) => pop.hoverCard = inside ? model.cardId : ""
                    onClicked: tracker.toggleSecretRuledOut(model.cardId)
                }
            }
        }
    }

    // ---- aperçu au survol : le rendu officiel de la carte ------------------
    CardPreview {
        visible: pop.visible && pop.hoverCard !== ""
        title: "Cairn · aperçu secret"
        cardId: pop.hoverCard
        opponentSide: true
        anchorLeft: false
        x: pop.x + pop.width + 8
        y: Math.min(pop.y, Screen.height - height - 20)
    }
}
