import QtQuick
import QtQuick.Layouts

// Ligne de carte illustrée — la brique commune des trois panneaux.
//
// L'art de la carte (tuile 256×36 de HearthstoneJSON) occupe toute la ligne,
// puis un dégradé le noie vers la gauche : le nom reste lisible sur le fond
// sombre, l'illustration donne l'identité de la carte d'un coup d'œil. C'est
// exactement ce qui manquait aux lignes plates de la première version.
Item {
    id: row

    // ---- contenu -----------------------------------------------------------
    property string cardId: ""
    property string label: ""
    property int cost: -1                 // < 0 : pas de gemme de mana
    property int count: 1
    property string rarity: ""
    property string origin: ""            // « ← Azalina », créatrice de la carte
    property int rank: 0                  // > 0 : file ordonnée (atlas)
    // Pastille de gauche, texte libre : sert au tour d'arrivée en main adverse
    // (« M » = gardée au mulligan, « 4 » = arrivée au tour 4). Savoir depuis
    // quand l'adversaire tient une carte vaut souvent autant que son nom.
    property string badge: ""
    // Carte ARRIVÉE en cours de partie (copie, découverte, cadeau d'un effet).
    // Elle vit dans la liste du deck comme les autres — c'est bien là qu'elle
    // est — mais l'icône dit d'où elle sort, sans quoi on croirait avoir mal
    // compté sa propre liste.
    property bool gift: false
    property bool spent: false            // piochée / sortie du deck : éteinte
    property bool struck: false           // barrée (secret écarté)
    property bool unknown: false          // carte cachée : nom en italique
    property bool showCount: true
    property bool clickable: false        // main pointeuse au survol

    // ---- réglages ----------------------------------------------------------
    // palette : voir Theme.qml (source unique du design system)
    readonly property Theme thm: Theme {}
    property color base: thm.raised        // fond de la ligne, sous l'art
    property color accent: thm.gold
    property real artOpacity: 0.62
    // Part de la ligne restée sombre à gauche. Les panneaux étroits ont besoin
    // de plus de place pour le texte que les larges.
    property real fadeStart: 0.42
    property real fadeEnd: 0.88

    signal hoveredChanged(bool inside)
    signal clicked()

    implicitHeight: 26

    function rarityColor(r) {
        return r === "LEGENDARY" ? "#ffbe55"
             : r === "EPIC" ? "#c78bff"
             : r === "RARE" ? "#6bb6ff"
             : "#d8dde8"
    }

    Rectangle {
        id: frame
        anchors.fill: parent
        radius: 3
        color: row.base
        clip: true
        opacity: row.spent ? 0.42 : 1.0
        Behavior on opacity { NumberAnimation { duration: 120 } }

        // ---- illustration --------------------------------------------------
        Image {
            id: art
            anchors.fill: parent
            fillMode: Image.PreserveAspectCrop
            // tileRevision : la liaison doit se réévaluer quand la tuile finit
            // d'arriver sur disque (sinon la ligne reste nue jusqu'au prochain
            // rebond de modèle)
            source: (tracker.tileRevision >= 0 && row.cardId !== "")
                    ? tracker.tile(row.cardId) : ""
            // fichier local de 30 Ko : le chargement synchrone évite le
            // clignotement d'une ligne qui s'illustre après coup
            asynchronous: false
            cache: true
            visible: status === Image.Ready
            // les cartes déjà sorties s'effacent : l'œil ne s'y accroche plus
            opacity: row.spent ? row.artOpacity * 0.45 : row.artOpacity
        }

        // ---- fondu vers la gauche, pour la lisibilité du nom ----------------
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: row.base }
                GradientStop { position: row.fadeStart; color: row.base }
                // Qt.alpha garde la même teinte : un fondu vers "transparent"
                // passerait par du noir et salirait l'art
                GradientStop { position: row.fadeEnd; color: Qt.alpha(row.base, 0.30) }
                // jamais tout à fait nu : un voile résiduel garde les badges
                // du bord droit lisibles quelle que soit l'illustration
                GradientStop { position: 1.0; color: Qt.alpha(row.base, 0.18) }
            }
        }

        // liseré de rareté à gauche : le code couleur reste lisible même quand
        // l'illustration tire le nom vers le clair
        Rectangle {
            visible: row.rarity === "LEGENDARY" || row.rarity === "EPIC"
            width: 2
            height: parent.height
            color: row.rarityColor(row.rarity)
            opacity: 0.9
        }

        // ---- survol ---------------------------------------------------------
        Rectangle {
            anchors.fill: parent
            color: "white"
            opacity: hover.hovered ? 0.07 : 0.0
            Behavior on opacity { NumberAnimation { duration: 90 } }
        }
    }

    HoverHandler {
        id: hover
        cursorShape: row.clickable ? Qt.PointingHandCursor : Qt.ArrowCursor
        onHoveredChanged: row.hoveredChanged(hovered)
    }
    TapHandler { enabled: row.clickable; onTapped: row.clicked() }

    // ---- contenu textuel ----------------------------------------------------
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 5
        anchors.rightMargin: 6
        spacing: 6
        opacity: row.spent ? 0.55 : 1.0

        Text {
            visible: row.rank > 0
            text: row.rank + "."
            color: "#8b93a7"
            font.pixelSize: 10
            font.bold: true
            Layout.minimumWidth: 11
        }

        // pastille de tour (main adverse)
        Rectangle {
            visible: row.badge !== ""
            Layout.preferredWidth: 17
            Layout.preferredHeight: 15
            radius: 3
            color: Qt.alpha("#0b0e15", 0.8)
            border.color: Qt.alpha("#8b93a7", 0.5)
            border.width: 1
            Text {
                anchors.centerIn: parent
                text: row.badge
                color: "#c2c9d6"
                font.pixelSize: 9
                font.bold: true
            }
        }

        // gemme de mana
        Rectangle {
            visible: row.cost >= 0
            Layout.preferredWidth: 19
            Layout.preferredHeight: 19
            radius: width / 2
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#4a7fd4" }
                GradientStop { position: 1.0; color: "#1f3f80" }
            }
            border.color: "#0d1526"
            border.width: 1
            Text {
                anchors.centerIn: parent
                text: row.cost
                color: "white"
                font.pixelSize: 11
                font.bold: true
                style: Text.Outline
                styleColor: "#0d1526"
            }
        }

        // cadeau : carte entrée dans le deck en cours de partie
        Text {
            visible: row.gift
            text: "🎁"
            font.pixelSize: 11
            Layout.minimumWidth: 13
        }

        Text {
            text: row.label
            color: row.unknown ? "#8b93a7" : row.rarityColor(row.rarity)
            font.pixelSize: 12
            font.bold: true
            font.italic: row.unknown
            font.strikeout: row.struck
            elide: Text.ElideRight
            Layout.fillWidth: true
            // l'art passe sous le texte : un liseré sombre garantit le contraste
            style: Text.Outline
            styleColor: Qt.alpha("#000000", 0.75)
        }

        Text {
            visible: row.origin !== ""
            text: "← " + row.origin
            color: "#a9b1c2"
            font.pixelSize: 9
            elide: Text.ElideRight
            Layout.maximumWidth: 78
            style: Text.Outline
            styleColor: Qt.alpha("#000000", 0.75)
        }

        // étoile des légendaires, comme en jeu
        Text {
            visible: row.rarity === "LEGENDARY" && (!row.showCount || row.count <= 1)
            text: "★"
            color: "#ffbe55"
            font.pixelSize: 12
            style: Text.Outline
            styleColor: Qt.alpha("#000000", 0.75)
        }

        // badge de compte
        Rectangle {
            visible: row.showCount && row.count > 1
            Layout.preferredWidth: 18
            Layout.preferredHeight: 17
            radius: 3
            color: Qt.alpha("#0b0e15", 0.8)
            border.color: Qt.alpha(row.accent, 0.55)
            border.width: 1
            Text {
                anchors.centerIn: parent
                text: row.count
                color: row.accent
                font.pixelSize: 11
                font.bold: true
            }
        }
    }
}
