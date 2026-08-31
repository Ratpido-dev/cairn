import QtQuick

// Mes points d'attaque — par défaut sous le plateau, côté joueur.
AttackBadge {
    side: "good"
    widgetName: "attack_mine"
    title: "Cairn · mes dégâts"
    defaultX: Math.round(Screen.width * 0.62)
    defaultY: Math.round(Screen.height * 0.72)
}
