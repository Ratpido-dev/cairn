#!/bin/bash
# Règle KWin « Cairn au-dessus » : garde le panneau et le bandeau au-dessus
# du jeu (app_id « cairn », posé par tools/panel.py via setDesktopFileName).
# Idempotent. Annulation : Paramètres KDE → Gestion des fenêtres → Règles.
set -euo pipefail

# --reset-pos : réécrit les positions par défaut des widgets flottants. Sous
# Wayland c'est KWin qui RETIENT où l'utilisateur les a posés (mode Remember) ;
# effacer la configuration de Cairn ne suffit donc pas à les ramener — il faut
# repasser par la règle. C'est ce que déclenche « Replacer les widgets ».
FORCE_POS=0
[ "${1:-}" = "--reset-pos" ] && FORCE_POS=1

RULES_FILE="$HOME/.config/kwinrulesrc"
RULE_ID="cairn-keep-above"

rules=$(kreadconfig6 --file kwinrulesrc --group General --key rules 2>/dev/null || true)

add_rule() {  # ajoute l'id à la liste General/rules s'il n'y est pas
    case ",$rules," in
        *",$1,"*) ;;
        *) rules="${rules:+$rules,}$1"
           kwriteconfig6 --file kwinrulesrc --group General --key rules "$rules" ;;
    esac
}

if ! grep -q "$RULE_ID" "$RULES_FILE" 2>/dev/null; then
    add_rule "$RULE_ID"
    kwriteconfig6 --file kwinrulesrc --group "$RULE_ID" --key Description "Cairn au-dessus du jeu"
    kwriteconfig6 --file kwinrulesrc --group "$RULE_ID" --key wmclass "cairn"
    kwriteconfig6 --file kwinrulesrc --group "$RULE_ID" --key wmclassmatch 1   # exact
    kwriteconfig6 --file kwinrulesrc --group "$RULE_ID" --key above true
    kwriteconfig6 --file kwinrulesrc --group "$RULE_ID" --key aboverule 2      # forcer
fi

# Hearthstone en « fenêtré sans bordure » forcé : HS réglé en mode fenêtré
# dans ses options devient visuellement identique au plein écran (sans le
# crop du bas), et les fenêtres Cairn restent au-dessus — ce qu'un vrai plein
# écran ne permet pas (le compositeur le remet devant à chaque clic).
HS_RULE="cairn-hs-borderless"
RES_W=$(kscreen-doctor -o 2>/dev/null | grep -oP '\d+x\d+@' | head -1 | grep -oP '^\d+') ; RES_W=${RES_W:-1920}
RES_H=$(kscreen-doctor -o 2>/dev/null | grep -oP '\d+x\d+@' | head -1 | grep -oP 'x\K\d+') ; RES_H=${RES_H:-1080}
if ! grep -q "$HS_RULE" "$RULES_FILE" 2>/dev/null; then
    add_rule "$HS_RULE"
    kwriteconfig6 --file kwinrulesrc --group "$HS_RULE" --key Description "Hearthstone sans bordure plein écran"
    kwriteconfig6 --file kwinrulesrc --group "$HS_RULE" --key wmclass "hearthstone"
    kwriteconfig6 --file kwinrulesrc --group "$HS_RULE" --key wmclassmatch 2   # sous-chaîne
    kwriteconfig6 --file kwinrulesrc --group "$HS_RULE" --key noborder true
    kwriteconfig6 --file kwinrulesrc --group "$HS_RULE" --key noborderrule 2
    kwriteconfig6 --file kwinrulesrc --group "$HS_RULE" --key position "0,0"
    kwriteconfig6 --file kwinrulesrc --group "$HS_RULE" --key positionrule 2
    kwriteconfig6 --file kwinrulesrc --group "$HS_RULE" --key size "${RES_W},${RES_H}"
    kwriteconfig6 --file kwinrulesrc --group "$HS_RULE" --key sizerule 2
fi

# Overlays au-dessus MÊME du vrai plein écran : la couche « overlay » de KWin
# (règle « layer », Plasma ≥ 6.0) bat la couche « fullscreen actif » — le
# borderless devient un simple secours. Scopé par TITRE (« Cairn · … ») pour ne
# pas épingler le launcher au-dessus de tout le bureau.
OV_RULE="cairn-overlay"
if ! grep -q "$OV_RULE" "$RULES_FILE" 2>/dev/null; then
    add_rule "$OV_RULE"
    kwriteconfig6 --file kwinrulesrc --group "$OV_RULE" --key Description "Cairn overlays au-dessus du plein écran"
    kwriteconfig6 --file kwinrulesrc --group "$OV_RULE" --key wmclass "cairn"
    kwriteconfig6 --file kwinrulesrc --group "$OV_RULE" --key wmclassmatch 1  # exact
    kwriteconfig6 --file kwinrulesrc --group "$OV_RULE" --key title "^Cairn · "
    kwriteconfig6 --file kwinrulesrc --group "$OV_RULE" --key titlematch 3    # regex
    kwriteconfig6 --file kwinrulesrc --group "$OV_RULE" --key layer "overlay"
    kwriteconfig6 --file kwinrulesrc --group "$OV_RULE" --key layerrule 2     # forcer
fi

# Les overlays ne doivent apparaître NI dans l'Alt+Tab, NI dans la barre des
# tâches, NI dans le sélecteur de bureaux. C'est ce que fait Firestone, et
# c'est la seule chose qui clochait vraiment : dix fenêtres sans bordure au
# milieu de l'Alt+Tab rendent le sélecteur inutilisable.
#
# Écrit à CHAQUE passage, hors du « if » de création : la règle existe déjà sur
# les installations antérieures, et un bloc conditionnel ne l'aurait jamais
# rattrapée. Le launcher, lui, garde sa place dans l'Alt+Tab — il s'appelle
# « Cairn — launcher » (tiret cadratin) et ne correspond pas à « ^Cairn · ».
for prop in skiptaskbar skipswitcher skippager; do
    kwriteconfig6 --file kwinrulesrc --group "$OV_RULE" --key "$prop" true
    kwriteconfig6 --file kwinrulesrc --group "$OV_RULE" --key "${prop}rule" 2  # forcer
done

# Positions par défaut : sous Wayland un client ne peut PAS se placer lui-même
# (les x/y du QML sont ignorés) → sans règle, KWin pose les fenêtres au milieu.
# Remember (4) : position initiale = la nôtre, puis KWin retient où
# l'utilisateur les a déplacées. Apply (3) pour les aperçus (non déplaçables).
add_pos_rule() {  # id, titre exact, "x,y", règle (3=Apply 4=Remember)
    local id="$1" title="$2" pos="$3" mode="$4"
    if [ "$FORCE_POS" = 1 ] && grep -q "^\[$id\]" "$RULES_FILE" 2>/dev/null; then
        kwriteconfig6 --file kwinrulesrc --group "$id" --key position "$pos"
        kwriteconfig6 --file kwinrulesrc --group "$id" --key positionrule "$mode"
        return
    fi
    if ! grep -q "^\[$id\]" "$RULES_FILE" 2>/dev/null; then
        add_rule "$id"
        kwriteconfig6 --file kwinrulesrc --group "$id" --key Description "Position $title"
        kwriteconfig6 --file kwinrulesrc --group "$id" --key wmclass "cairn"
        kwriteconfig6 --file kwinrulesrc --group "$id" --key wmclassmatch 1
        kwriteconfig6 --file kwinrulesrc --group "$id" --key title "$title"
        kwriteconfig6 --file kwinrulesrc --group "$id" --key titlematch 1     # exact
        kwriteconfig6 --file kwinrulesrc --group "$id" --key position "$pos"
        kwriteconfig6 --file kwinrulesrc --group "$id" --key positionrule "$mode"
    fi
}
DECK_X=$((RES_W - 300 - 24))
add_pos_rule "cairn-pos-deck"       "Cairn · deck"               "${DECK_X},80"          4
add_pos_rule "cairn-pos-adversaire" "Cairn · adversaire"         "24,80"                 4
add_pos_rule "cairn-pos-ap-deck"    "Cairn · aperçu deck"        "$((DECK_X - 248)),100" 3
add_pos_rule "cairn-pos-ap-adv"     "Cairn · aperçu adversaire"  "292,100"               3
# Widgets flottants : une règle CHACUN, sinon ils partageraient une position et
# se superposeraient. Remember (4) = KWin retient où l'utilisateur les pose, et
# les y remet à chaque partie comme à chaque redémarrage — c'est le mécanisme
# qui rend la disposition permanente sous Wayland, où le client ne peut pas se
# placer lui-même.
add_pos_rule "cairn-pos-compteurs"  "Cairn · compteurs"          "$((RES_W*66/100)),96"  4
add_pos_rule "cairn-pos-atk-moi"    "Cairn · mes dégâts"         "$((RES_W*62/100)),$((RES_H*72/100))" 4
add_pos_rule "cairn-pos-atk-adv"    "Cairn · dégâts adverses"    "$((RES_W*62/100)),$((RES_H*20/100))" 4
add_pos_rule "cairn-pos-secrets"    "Cairn · secrets"            "$((RES_W/2)),$((RES_H*6/100))"       4
add_pos_rule "cairn-pos-chrono"     "Cairn · chrono"             "$((RES_W*66/100)),$((RES_H*74/100))" 4
# pastilles de la main adverse : sous son éventail, donc en haut au centre —
# c'est une position à caler UNE fois à la souris, KWin retient ensuite
add_pos_rule "cairn-pos-main"       "Cairn · main adverse"       "$((RES_W/2 - 190)),$((RES_H*11/100))" 4
add_pos_rule "cairn-pos-ap-main"    "Cairn · aperçu main"        "$((RES_W/2 - 190)),$((RES_H*20/100))" 3
add_pos_rule "cairn-pos-ap-secret"  "Cairn · aperçu secret"      "$((RES_W/2 + 220)),$((RES_H*6/100))"  3

# count doit suivre la liste (le KCM s'y fie pour l'affichage)
n=$(awk -F, '{print NF}' <<<"$rules")
kwriteconfig6 --file kwinrulesrc --group General --key count "$n"

qdbus6 org.kde.KWin /KWin org.kde.KWin.reconfigure 2>/dev/null \
    || echo "(KWin sera rechargé à la prochaine session)"
echo "Règles KWin installées : Cairn au-dessus + overlay plein écran + HS sans bordure ${RES_W}×${RES_H}."
echo "→ Hearthstone peut rester en PLEIN ÉCRAN : les fenêtres Cairn passent en couche overlay."
