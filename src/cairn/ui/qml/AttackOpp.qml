import QtQuick

// Les points d'attaque d'en face — par défaut au-dessus du plateau.
AttackBadge {
    side: "bad"
    widgetName: "attack_opp"
    title: "Cairn · dégâts adverses"
    defaultX: Math.round(tracker.gameScreen.width * 0.62)
    defaultY: Math.round(tracker.gameScreen.height * 0.20)
}
