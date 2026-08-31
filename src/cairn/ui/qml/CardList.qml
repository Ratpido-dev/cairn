import QtQuick
import QtQuick.Layouts

// Section repliée d'une liste de cartes (main adverse, cimetière, secrets…).
// Invisible tant qu'elle est vide : les panneaux ne s'allongent qu'utilement.
ColumnLayout {
    id: sec

    property string title
    property alias model: list.model
    // palette : voir Theme.qml (source unique du design system)
    readonly property Theme thm: Theme {}
    property color tint: thm.textDim
    property int maxRows: 6
    property bool showOrigin: false
    property bool showRank: false            // file ordonnée (atlas) : 1., 2., 3.…
    property bool showBadge: false           // pastille de gauche (tour d'arrivée)
    property bool strikeable: false          // secrets : barrer d'un clic
    property bool collapsed: false           // repliée d'un clic sur le titre
    // « note » : texte à montrer sous l'aperçu (libellé propre d'un effet en
    // jeu, dont l'aperçu affiche la carte SOURCE). Un gestionnaire qui n'en
    // veut pas peut déclarer moins de paramètres, QML l'accepte.
    signal cardHovered(string cardId, string note)
    signal cardClicked(string cardId)

    readonly property color bgSoft: thm.raised
    readonly property color muted: thm.textDim
    readonly property color text: thm.text

    function rarityColor(r) {
        return r === "LEGENDARY" ? "#ffa030"
             : r === "EPIC" ? "#c07bff"
             : r === "RARE" ? "#4da6ff"
             : "#c2c9d6"
    }

    visible: list.count > 0
    Layout.fillWidth: true
    spacing: 2

    // titre cliquable : replier une section libère de la hauteur d'écran sans
    // rien perdre — le compte reste affiché
    RowLayout {
        Layout.fillWidth: true
        spacing: 5
        Text {
            text: sec.collapsed ? "▸" : "▾"
            color: sec.tint
            font.pixelSize: 9
            opacity: 0.8
        }
        Text {
            text: sec.title + " (" + list.count + ")"
            color: sec.tint
            font.pixelSize: 10
            font.bold: true
            font.letterSpacing: 1
        }
        Rectangle { Layout.fillWidth: true; height: 1; color: "#262b38" }

        HoverHandler { cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: sec.collapsed = !sec.collapsed }
    }

    ListView {
        id: list
        Layout.fillWidth: true
        visible: !sec.collapsed
        implicitHeight: sec.collapsed ? 0 : Math.min(count, sec.maxRows) * 26
        spacing: 2
        clip: true
        delegate: CardRow {
            width: list.width
            implicitHeight: 24
            cardId: model.cardId
            label: model.label
            cost: model.cost === undefined ? -1 : model.cost
            rarity: model.rarity === undefined ? "" : model.rarity
            count: model.count === undefined ? 1 : model.count
            rank: (sec.showRank && model.rank !== undefined) ? model.rank : 0
            origin: (sec.showOrigin && model.origin !== undefined) ? model.origin : ""
            badge: (sec.showBadge && model.badge !== undefined) ? model.badge : ""
            unknown: model.known !== undefined && !model.known
            // Deux raisons d'être barrée, sans rapport l'une avec l'autre :
            // un secret écarté par déduction (cliquable), ou une carte connue
            // du deck adverse qui vient d'en sortir. Les modèles qui n'ont pas
            // le rôle « struck » gardent exactement l'ancien comportement.
            spent: (sec.strikeable && model.ruledOut)
                   || (model.struck !== undefined && model.struck)
            struck: (sec.strikeable && model.ruledOut)
                    || (model.struck !== undefined && model.struck)
            base: sec.bgSoft
            accent: sec.tint
            clickable: sec.strikeable
            onHoveredChanged: (inside) => sec.cardHovered(
                inside ? model.cardId : "",
                (inside && model.note !== undefined) ? model.note : "")
            onClicked: sec.cardClicked(model.cardId)
        }
    }
}
