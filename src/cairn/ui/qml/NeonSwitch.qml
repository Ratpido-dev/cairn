import QtQuick
import QtQuick.Controls.Basic

// Interrupteur « néon » : piste en dégradé, halo à l'état actif, pastille qui
// glisse. Remplace le Switch système, dont l'indicateur gris cassait le fond
// sombre. Le comportement (checked/toggled) reste celui de Switch.
Switch {
    id: control

    readonly property Theme thm: Theme {}
    // couleur de la piste allumée / éteinte : l'interrupteur d'anonymisation
    // s'en sert pour être vert allumé mais ROUGE éteint (l'état éteint y est
    // un danger, pas une simple absence)
    property color onTint: thm.gold
    property color offTint: thm.raised
    property bool offIsWarning: false      // pastille sombre même éteint

    padding: 0
    implicitWidth: 42
    implicitHeight: 22

    indicator: Rectangle {
        id: track
        implicitWidth: 42
        implicitHeight: 22
        radius: height / 2
        anchors.verticalCenter: parent.verticalCenter

        gradient: Gradient {
            GradientStop {
                position: 0.0
                color: control.checked ? Qt.lighter(control.onTint, 1.18)
                                       : Qt.lighter(control.offTint, 1.10)
            }
            GradientStop {
                position: 1.0
                color: control.checked ? Qt.darker(control.onTint, 1.10)
                                       : control.offTint
            }
        }
        border.width: 1
        border.color: control.checked ? Qt.alpha(control.onTint, 0.85)
                    : control.offIsWarning ? Qt.alpha(control.offTint, 0.85)
                    : control.thm.hairline

        // lueur : allumée en continu, renforcée au survol
        GlowRing {
            anchors.fill: parent
            cornerRadius: track.radius
            glowColor: control.checked ? control.onTint : control.offTint
            spread: 5
            intensity: control.checked || control.offIsWarning
                     ? (control.hovered ? 0.42 : 0.26)
                     : (control.hovered ? 0.14 : 0.0)
        }

        Rectangle {
            id: knob
            width: 16
            height: 16
            radius: 8
            y: 3
            x: control.checked ? track.width - width - 3 : 3
            color: control.checked || control.offIsWarning
                 ? control.thm.knob : control.thm.textDim
            Behavior on x {
                NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
            }
            Behavior on color { ColorAnimation { duration: 140 } }
        }
    }

    // pas de libellé : le texte vit dans la ligne qui porte l'interrupteur
    contentItem: Item {}
}
