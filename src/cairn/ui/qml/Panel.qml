import QtQuick

// Surface de base des panneaux : dégradé vertical très court (le plat absolu
// fait « boîte de dialogue système »), filet d'1 px en blanc dilué, micro-
// arrondi, halo optionnel. Les enfants s'y ajoutent comme dans un Rectangle.
Rectangle {
    id: panel

    readonly property Theme thm: Theme {}
    property color glowTint: thm.gold
    property real glowIntensity: 0.0
    property color borderTint: thm.hairline

    radius: thm.rLg
    gradient: Gradient {
        GradientStop { position: 0.0; color: Qt.lighter(panel.thm.surface, 1.12) }
        GradientStop { position: 1.0; color: panel.thm.surface }
    }
    border.width: 1
    border.color: borderTint

    GlowRing {
        anchors.fill: parent
        cornerRadius: panel.radius
        glowColor: panel.glowTint
        spread: 7
        intensity: panel.glowIntensity
    }
}
