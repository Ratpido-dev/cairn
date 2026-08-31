import QtQuick
import QtQuick.Layouts

// Familles à cocher : les dix Rafaam, les trois sœurs Coursevent…
//
// Un compteur « 7/9 » dit combien ; ici on voit LESQUELS sont déjà posés —
// les joués sont éteints et barrés, ceux qui restent gardent leur couleur.
// Une seule liste porte toutes les familles, découpées par ListView.section :
// le pont n'a pas à savoir combien de familles existent.
ColumnLayout {
    id: sec

    property alias model: list.model
    property int sectionCount: 0     // nombre d'en-têtes, fourni par le pont
    // palette : voir Theme.qml (source unique du design system)
    readonly property Theme thm: Theme {}
    property color tint: thm.gold
    property color bgSoft: thm.raised
    signal cardHovered(string cardId)

    visible: list.count > 0
    Layout.fillWidth: true
    spacing: 2

    ListView {
        id: list
        Layout.fillWidth: true
        // hauteur des lignes + un en-tête par famille présente
        implicitHeight: count * 26 + sec.sectionCount * 18
        spacing: 2
        clip: true
        interactive: false      // le défilement appartient au panneau entier

        section.property: "title"
        section.criteria: ViewSection.FullString
        section.delegate: RowLayout {
            width: list.width
            spacing: 5
            Text {
                text: section
                color: sec.tint
                font.pixelSize: 10
                font.bold: true
                font.letterSpacing: 1
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#262b38" }
        }

        delegate: CardRow {
            width: list.width
            implicitHeight: 24
            cardId: model.cardId
            label: model.label
            cost: model.cost
            rarity: model.rarity
            showCount: false
            spent: model.played
            struck: model.played
            base: sec.bgSoft
            accent: sec.tint
            onHoveredChanged: (inside) => sec.cardHovered(inside ? model.cardId : "")
        }
    }
}
