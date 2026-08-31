import QtQuick
import QtQuick.Shapes

// Fond de fenêtre : obsidienne avec une très légère lueur radiale haute.
//
// `QtQuick.Shapes` plutôt qu'un effet graphique : le dégradé radial y est
// natif et rend correctement même en logiciel (contrairement aux shaders de
// QtQuick.Effects, qui ne dessinent rien dans ce cas). Zéro image embarquée.
Item {
    id: backdrop

    readonly property Theme thm: Theme {}
    property color inner: thm.bgHalo
    property color outer: thm.bg
    // le foyer est haut et centré : la lueur monte derrière l'en-tête, là où
    // se trouve la marque, et laisse le bas de la liste au calme
    property real focusX: 0.5
    property real focusY: 0.18
    property real spreadFactor: 1.15

    Shape {
        anchors.fill: parent
        ShapePath {
            strokeWidth: 0
            strokeColor: "transparent"
            fillGradient: RadialGradient {
                centerX: backdrop.width * backdrop.focusX
                centerY: backdrop.height * backdrop.focusY
                centerRadius: Math.max(backdrop.width, backdrop.height * 0.75)
                              * backdrop.spreadFactor
                focalX: backdrop.width * backdrop.focusX
                focalY: backdrop.height * backdrop.focusY
                GradientStop { position: 0.0; color: backdrop.inner }
                GradientStop { position: 0.55; color: backdrop.outer }
                GradientStop { position: 1.0; color: backdrop.thm.bgDeep }
            }
            startX: 0
            startY: 0
            PathLine { x: backdrop.width; y: 0 }
            PathLine { x: backdrop.width; y: backdrop.height }
            PathLine { x: 0; y: backdrop.height }
            PathLine { x: 0; y: 0 }
        }
    }
}
