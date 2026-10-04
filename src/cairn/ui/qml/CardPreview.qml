import QtQuick

// Aperçu de carte au survol, dans sa propre fenêtre posée à côté du panneau.
// Le contenu vit dans CardPreviewBody.qml : avec l'option « aperçu dans le
// panneau », les panneaux l'affichent chez eux et cette fenêtre reste cachée.
Window {
    id: preview

    property string cardId: ""
    property bool opponentSide: false
    property bool anchorLeft: true   // aperçu posé à gauche de son panneau ?
    property string note: ""

    width: body.width
    // jamais 0 : une fenêtre sans hauteur n'est pas mappée par le compositeur
    height: Math.max(1, body.implicitHeight)
    color: "transparent"
    title: "Cairn · aperçu"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
           | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus

    CardPreviewBody {
        id: body
        cardId: preview.cardId
        opponentSide: preview.opponentSide
        note: preview.note
    }
}
