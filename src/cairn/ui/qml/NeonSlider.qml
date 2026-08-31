import QtQuick
import QtQuick.Controls.Basic

// Curseur « néon » : piste creusée, remplissage en dégradé or, poignée
// auréolée qui grossit au survol. Comportement identique au Slider standard.
Slider {
    id: control

    readonly property Theme thm: Theme {}
    property color tint: thm.gold

    implicitHeight: 22

    background: Rectangle {
        x: control.leftPadding
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: control.availableWidth
        height: 6
        radius: 3
        color: control.thm.sunken
        border.width: 1
        border.color: control.thm.hairlineSoft

        // partie parcourue : dégradé horizontal, du mana vers l'or, pour que
        // la course du curseur se lise même sans regarder le pourcentage
        Rectangle {
            width: control.visualPosition * parent.width
            height: parent.height
            radius: parent.radius
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Qt.alpha(control.thm.blue, 0.85) }
                GradientStop { position: 1.0; color: control.tint }
            }
        }
    }

    handle: Rectangle {
        id: knob
        x: control.leftPadding
           + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: control.pressed ? 18 : (control.hovered ? 17 : 15)
        height: width
        radius: width / 2
        color: control.thm.text
        border.width: 2
        border.color: control.tint
        Behavior on width { NumberAnimation { duration: 110 } }

        GlowRing {
            anchors.fill: parent
            cornerRadius: knob.radius
            glowColor: control.tint
            spread: 6
            intensity: control.pressed ? 0.55 : (control.hovered ? 0.40 : 0.22)
        }
    }
}
