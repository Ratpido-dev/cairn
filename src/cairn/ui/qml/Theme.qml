import QtQuick

// Design system « Dark Gaming Premium » — source unique de la palette.
//
// Pourquoi un objet instancié plutôt qu'un singleton : un singleton QML exige
// un fichier `qmldir` dans ce dossier, et dès qu'un qmldir existe il devient
// LA liste des types du répertoire — il faudrait y déclarer CardRow, CardList,
// EntryList… sous peine de casser l'import implicite dont dépendent déjà les
// panneaux. Un `Theme { id: T }` par fenêtre ne coûte rien (que des constantes)
// et n'a aucun effet de bord.
//
// Usage : chaque fenêtre instancie `Theme { id: T }` puis réexpose les noms
// historiques (bg, bgSoft, line, accent…) en alias — les centaines de
// références existantes continuent de fonctionner telles quelles.
QtObject {
    id: theme

    // ---- fonds ------------------------------------------------------------
    readonly property color bgDeep:    "#070A11"   // pourtour, le plus profond
    readonly property color bg:        "#0B0F17"   // obsidienne, fond principal
    readonly property color bgHalo:    "#16203A"   // centre du dégradé radial
    readonly property color surface:   "#131C2E"   // cartes et panneaux
    readonly property color surfaceHi: "#1B2740"   // carte survolée / active
    readonly property color raised:    "#1E293B"   // champs, pistes, pastilles
    readonly property color sunken:    "#0C121D"   // creux : fond de piste
    readonly property color knob:      "#080C14"   // pastille d'interrupteur allumé

    // ---- traits : jamais de gris système, seulement du blanc très dilué ----
    readonly property color hairline:     Qt.rgba(1, 1, 1, 0.08)
    readonly property color hairlineSoft: Qt.rgba(1, 1, 1, 0.05)
    readonly property color hairlineHi:   Qt.rgba(1, 1, 1, 0.14)
    readonly property color goldLine:     Qt.rgba(0.961, 0.620, 0.043, 0.22)
    readonly property color goldLineHi:   Qt.rgba(0.961, 0.620, 0.043, 0.55)
    // Équivalent OPAQUE de `hairline`, pour les fenêtres de jeu : elles sont
    // posées sur un fond transparent, un filet alpha y laisserait passer le
    // plateau et disparaîtrait sur les zones claires.
    readonly property color lineSolid:    "#242D40"

    // ---- texte ------------------------------------------------------------
    readonly property color text:      "#E6EDF7"
    readonly property color textDim:   "#94A3B8"
    readonly property color textFaint: "#64748B"

    // ---- accents ----------------------------------------------------------
    readonly property color gold:    "#F59E0B"   // légendaire — titres, actifs
    readonly property color goldHi:  "#FBBF24"
    readonly property color blue:    "#3B82F6"   // mana — liens, jauges
    readonly property color blueHi:  "#60A5FA"
    readonly property color good:    "#10B981"   // victoire
    readonly property color goodHi:  "#34D399"
    readonly property color bad:     "#EF4444"   // défaite
    readonly property color badHi:   "#F87171"

    // ---- alias historiques (ne rien renommer côté appelants) --------------
    readonly property color bgSoft: raised
    readonly property color bgCard: surface
    readonly property color line:   hairline
    readonly property color muted:  textDim
    readonly property color accent: gold
    readonly property color danger: bad

    // ---- rayons et rythme -------------------------------------------------
    readonly property int rSm: 8
    readonly property int rMd: 10
    readonly property int rLg: 12
    readonly property int rXl: 16

    // ---- couleurs de classe (identité Hearthstone, en version saturée) ----
    readonly property var classColors: ({
        "DEATHKNIGHT":  "#5FA8D3",
        "DEMONHUNTER":  "#2ECC71",
        "DRUID":        "#FF7D0A",
        "HUNTER":       "#A9D06B",
        "MAGE":         "#69CCF0",
        "PALADIN":      "#F58CBA",
        "PRIEST":       "#CBD5E1",
        "ROGUE":        "#EFE05A",
        "SHAMAN":       "#2E7FE8",
        "WARLOCK":      "#9482C9",
        "WARRIOR":      "#C79C6E"
    })
    // Monogrammes indépendants de la langue : « Chasseur » et « Chasseur de
    // démons » partagent leur initiale en français, pas leur clé.
    readonly property var classMonos: ({
        "DEATHKNIGHT": "DK", "DEMONHUNTER": "DH", "DRUID": "DR",
        "HUNTER": "HU", "MAGE": "MA", "PALADIN": "PA", "PRIEST": "PR",
        "ROGUE": "RO", "SHAMAN": "SH", "WARLOCK": "WK", "WARRIOR": "WR"
    })

    function classColor(key) {
        var c = classColors[key]
        return c === undefined ? theme.textFaint : c
    }
    function classMono(key) {
        var m = classMonos[key]
        return m === undefined ? "?" : m
    }

    // Vert au-dessus de la parité, rouge en dessous, neutre pile à 50 %.
    function pctColor(pct) {
        return pct > 50 ? theme.good : pct < 50 ? theme.bad : theme.textDim
    }
}
