import QtQuick

// Retient où l'on a posé une fenêtre, et l'y remet au lancement suivant.
// À déclarer DANS la fenêtre : PositionMemory { window: root; name: "deck" }.
//
// Sert sous X11 et XWayland (GNOME, cf. option « Passer par XWayland ») : là
// le client se place lui-même. Sous Wayland natif, Qt ne connaît pas la
// position de ses fenêtres — x/y ne bougent jamais, rien n'est écrit, et
// c'est KWin qui retient (règles cairn-pos-*).
//
// Pourquoi écouter x/y plutôt que le relâché du glisser : startSystemMove()
// confie le déplacement au gestionnaire de fenêtres, qui prend la souris. Le
// DragHandler est annulé AVANT que la fenêtre ait bougé, et l'on retenait la
// position de départ — chaque lancement ramenait les widgets au même endroit
// (#9, #11). La vraie position n'arrive qu'après, par le compositeur.
Timer {
    id: memo

    required property Window window
    required property string name
    property bool armed: false

    // un seul enregistrement une fois la fenêtre posée, pas un par pixel
    interval: 600
    onTriggered: tracker.rememberPos(name, window.x, window.y)

    Component.onCompleted: {
        var p = tracker.savedPos(name)
        if (p.x !== undefined) {
            window.x = p.x
            window.y = p.y
        }
        armed = true
    }

    readonly property Connections watch: Connections {
        target: memo.window
        function onXChanged() { if (memo.armed && memo.window.visible) memo.restart() }
        function onYChanged() { if (memo.armed && memo.window.visible) memo.restart() }
    }
}
