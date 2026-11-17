import QtQuick

// Mes points d'attaque — par défaut sous le plateau, côté joueur.
AttackBadge {
    side: "good"
    widgetName: "attack_mine"
    title: "Cairn · mes dégâts"
    defaultX: Math.round(tracker.gameScreen.width * 0.62)
    defaultY: Math.round(tracker.gameScreen.height * 0.72)
}
