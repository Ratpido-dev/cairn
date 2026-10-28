import QtQuick

// Base de tous les widgets flottants : sans bordure, au-dessus du jeu,
// déplaçable, et qui retient où on l'a posé.
//
// Persistance : sous Wayland un client ne peut ni se placer ni connaître sa
// position — c'est la règle KWin « cairn-pos-<widget> » en mode Remember (4)
// qui fait le travail, et elle le fait très bien (cf. tools/install_kwin_rule.sh).
// PositionMemory est le repli pour X11 et XWayland : là, le QML se place
// lui-même au démarrage. Les deux mécanismes se recouvrent sans se
// contredire — celui qui répond en premier gagne, et il donne la même réponse.
Window {
    id: win

    // clé de persistance ET suffixe de la règle KWin ; doit rester stable
    required property string widgetName
    property int defaultX: 0
    property int defaultY: 0
    readonly property real u: tracker.barScale

    color: "transparent"
    // Qt.Tool a été essayé ici pour sortir les overlays de l'Alt+Tab, puis
    // RETIRÉ : sous Wayland il n'a aucun effet sur le compositeur (KWin
    // continue de voir « type=0, utility=false », vérifié par script), mais il
    // change côté Qt la gestion du focus et des événements de survol — les
    // widgets devenaient difficiles à viser à la souris.
    // C'est la règle KWin « cairn-overlay » (skipswitcher/skiptaskbar/skippager)
    // qui fait tout le travail, et elle le fait bien. Ne pas le remettre.
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint

    // palette commune (braise sur ardoise, cf. cahier des charges)
    // palette : voir Theme.qml (source unique du design system)
    readonly property Theme thm: Theme {}
    readonly property color bg: thm.bg
    readonly property color line: thm.lineSolid
    readonly property color text: thm.text
    readonly property color muted: thm.textDim
    readonly property color accent: thm.gold
    readonly property color good: thm.good
    readonly property color bad: thm.bad

    x: defaultX
    y: defaultY
    // position retenue : la remet au lancement, la note quand elle change
    PositionMemory { window: win; name: win.widgetName }

    // Le déplacement est confié au compositeur ; la nouvelle position est
    // retenue par PositionMemory quand elle arrive, pas ici (cf. #9).
    function grabbed(active) {
        if (active)
            win.startSystemMove()
    }
}
