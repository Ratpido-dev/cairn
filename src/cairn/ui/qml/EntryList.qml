import QtQuick
import QtQuick.Layouts

// Cartes ENTRÉES dans le deck en cours de partie : les entrées quelconques,
// et celles dont on connaît le bout du deck (haut / fond).
//
// Pas de gemme de mana : ce qui compte ici est d'où la carte vient, pas ce
// qu'elle coûte — et une carte cachée n'a de toute façon pas de coût connu.
ColumnLayout {
    id: sec

    property alias model: list.model
    property string title
    property string glyph: "⤵"
    // palette : voir Theme.qml (source unique du design system)
    readonly property Theme thm: Theme {}
    property color tint: thm.gold
    property color bgSoft: thm.raised
    property color line: thm.lineSolid
    property int maxRows: 5
    signal cardHovered(string cardId)

    visible: list.count > 0
    Layout.fillWidth: true
    spacing: 2

    RowLayout {
        Layout.fillWidth: true
        spacing: 6
        Text { text: sec.glyph; color: sec.tint; font.pixelSize: 13; font.bold: true }
        Text {
            text: sec.title + " (" + list.count + ")"
            color: sec.tint
            font.pixelSize: 10
            font.bold: true
            font.letterSpacing: 1
        }
        Rectangle { Layout.fillWidth: true; height: 1; color: sec.line }
    }

    ListView {
        id: list
        Layout.fillWidth: true
        implicitHeight: Math.min(count, sec.maxRows) * 28
        spacing: 2
        clip: true
        interactive: false      // le défilement appartient au panneau entier
        delegate: CardRow {
            width: list.width
            cardId: model.known ? model.cardId : ""
            label: model.known
                ? model.label
                : (tracker.language === "en" ? "? hidden card" : "? carte cachée")
            unknown: !model.known
            cost: -1
            rarity: model.rarity
            count: model.count
            origin: model.origin
            base: sec.bgSoft
            accent: sec.tint
            onHoveredChanged: (inside) => sec.cardHovered(inside ? model.cardId : "")
        }
    }
}
