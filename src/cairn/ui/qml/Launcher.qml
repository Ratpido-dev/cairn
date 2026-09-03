import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic

// Launcher de Cairn : options des add-ons, échelles, stats et historique.
// C'est la fenêtre « maison » — les panneaux de jeu n'apparaissent qu'en partie.
Window {
    id: home
    width: 560
    height: 720
    minimumWidth: 420
    visible: true
    title: "Cairn — launcher"
    // le fond réel est peint par RadialBackdrop : la couleur de fenêtre ne sert
    // qu'aux quelques millisecondes qui précèdent le premier rendu
    color: thm.bgDeep

    // ---- design system « Dark Gaming Premium » -----------------------------
    // Toute la palette vit dans Theme.qml : une seule définition pour le
    // launcher, les panneaux de jeu et les widgets flottants.
    readonly property Theme thm: Theme {}

    // lueur radiale discrète derrière tout le contenu
    RadialBackdrop { anchors.fill: parent }

    // ---- traduction : tr("clé") suit tracker.language ----------------------
    readonly property bool en: tracker.language === "en"
    readonly property var strings: ({
        "tagline":   ["tracker Hearthstone natif Linux", "native Linux Hearthstone tracker"],
        "hsOn":      ["● Hearthstone détecté", "● HS running"],
        "hsOff":     ["○ en attente de HS", "○ HS not running"],
        "addons":    ["ADD-ONS DU BANDEAU", "COUNTER BAR ADD-ONS"],
        "windows":   ["FENÊTRES", "WINDOWS"],
        "sharing":   ["PARTAGE DE PARTIES", "GAME SHARING"],
        "shareOn":   ["Envoyer mes parties au corpus public",
                      "Send my games to the public corpus"],
        "shareHint": ["Facultatif. Sert à corriger le lecteur de journaux et à nourrir d'autres projets. Le corpus est ouvert : tout le monde peut le retélécharger, toi compris.",
                      "Optional. Used to fix the log parser and feed other projects. The corpus is open: anyone can download it back, you included."],
        "anonymAlways": ["Ton pseudo et celui de l'adversaire sont toujours remplacés par des jetons anonymes avant l'envoi. Ce n'est pas un réglage.",
                      "Your battletag and your opponent's are always replaced by anonymous tokens before sending. This is not a setting."],
        "rank":      ["Mon rang", "My rank"],
        "rankHint":  ["Hearthstone ne l'écrit dans aucun journal : il ne peut être que déclaré. Facultatif.",
                      "Hearthstone writes it in no log file, so it can only be declared. Optional."],
        "queued":    ["En attente : ", "Queued: "],
        "installId": ["Mon identifiant :", "My identifier:"],
        "installIdHint": ["Il regroupe tes envois. Sert à les retrouver dans le corpus, ou à en demander la suppression. Aucun lien avec ton compte Blizzard.",
                          "It groups your uploads. Use it to find them back in the corpus, or to request their deletion. Unrelated to your Blizzard account."],
        "copied":    ["copié", "copied"],
        "copy":      ["copier", "copy"],
        "archives":  ["ARCHIVES DE PARTIES", "GAME ARCHIVES"],
        "archiveOn": ["Archiver les journaux de session", "Archive session logs"],
        "archiveHint": ["Hearthstone efface ses vieux journaux ; l'historique ne garde qu'un résumé. Compressé ×18 : moins d'1 Mo par session.",
                        "Hearthstone deletes its old logs; history keeps only a summary. Compressed ×18: under 1 MB per session."],
        "archived":  ["Archivé : ", "Archived: "],
        "seeQueue":  ["voir le dossier", "open folder"],
        "clearQueue":["tout effacer", "clear"],
        "sendNow":   ["envoyer maintenant", "send now"],
        "noEndpoint":["Aucun point de collecte n'est configuré dans cette version : les parties restent ici, sur ta machine.",
                      "No collection endpoint is configured in this build: games stay here, on your machine."],
        "oppPanel":  ["Panneau adversaire (à gauche)", "Opponent panel (left)"],
        "handDots":  ["Pastilles sous la main adverse", "Dots under opponent's hand"],
        "myHand":    ["Ma main dans le panneau", "My hand in the panel"],
        "myPlays":   ["Mes cartes jouées dans le panneau", "Cards I played, in the panel"],
        "handDotsHint": ["Tour d'arrivée, cadeau, vignette. À caler une fois sous son éventail : la position est retenue.",
                         "Arrival turn, gift, tile. Drag it once under their hand: the position is remembered."],
        "sizeDeck":  ["Taille — mon deck", "Size — my deck"],
        "sizeOpp":   ["Taille — adversaire", "Size — opponent"],
        "sizeBar":   ["Taille — widgets flottants", "Size — floating widgets"],
        "resetPos":  ["Replacer les widgets", "Reset widget positions"],
        "resetPosHint": ["Compteurs, dégâts et secrets retournent à leur place d'origine",
                         "Counters, damage and secrets return to their default spot"],
        "myDecks":   ["MES DECKS", "MY DECKS"],
        "overall":   ["Bilan global : ", "Overall: "],
        "noGames":   ["Aucune partie enregistrée — joue avec Cairn ouvert.",
                      "No games recorded yet — play with the tracker open."],
        "clickDeck": ["clique un deck pour filtrer les classes et les parties",
                      "click a deck to filter classes and games"],
        "game1":     [" partie", " game"],
        "games":     [" parties", " games"],
        "archive":   ["archiver", "archive"],
        "addTitle":  ["AJOUTER UNE PARTIE À LA MAIN", "ADD A GAME MANUALLY"],
        "addHint":   ["Quand le journal de Hearthstone a lâché en pleine partie.",
                      "For when Hearthstone's log died mid-game."],
        "deck":      ["Deck", "Deck"],
        "opponent":  ["Adversaire", "Opponent"],
        "win":       ["✓ Victoire", "✓ Win"],
        "loss":      ["✗ Défaite", "✗ Loss"],
        "added":     ["Partie ajoutée.", "Game added."],
        "vsClasses": ["CONTRE LES CLASSES", "AGAINST CLASSES"],
        "recent":    ["DERNIÈRES PARTIES", "RECENT GAMES"],
        "vs":        ["vs ", "vs "],
        "warnTitle": ["Attention — action irréversible", "Warning — this cannot be undone"],
        "no":        ["Non, annuler", "No, cancel"],
        "yes":       ["Oui, supprimer", "Yes, delete"],
        "noPrefix":  ["⚠ Hearthstone est introuvable. Indique le dossier qui contient « drive_c » (variable CAIRN_HS_PREFIX) puis relance Cairn — ou lance « python tools/doctor.py » pour un diagnostic.",
                      "⚠ Hearthstone not found. Point Cairn at the folder containing “drive_c” (CAIRN_HS_PREFIX) and restart — or run “python tools/doctor.py” to diagnose."],
        "logsOff":   ["⚠ Hearthstone n'écrit pas ses journaux : Cairn ne peut rien suivre. Un clic active l'enregistrement, puis REDÉMARRE le jeu.",
                      "⚠ Hearthstone isn't writing its logs, so Cairn can't track anything. One click enables them, then RESTART the game."],
        "logCapped": ["⚠ Hearthstone plafonne ses journaux à 10 Mo : il cesse d'écrire en pleine session et Cairn devient aveugle. Un clic lève le plafond, puis REDÉMARRE le jeu.",
                      "⚠ Hearthstone caps its logs at 10 MB: it stops writing mid-session and Cairn goes blind. One click lifts the cap, then RESTART the game."],
        "enableLogs":["Activer les journaux du jeu", "Enable game logs"],
        "liftCap":   ["Lever le plafond des journaux", "Lift the log size cap"],
        "prefixFound":["Jeu détecté : ", "Game found at: "],
        "archetypes":["Ses decks", "Their decks"],
        "refDecks":["Listes de référence", "Reference lists"],
        "refName":["nom", "name"],
        "refCode":["colle un ou plusieurs decks ici (### Nom + code)",
                   "paste one or more decks here (### Name + code)"],
        "archetypeHint":["Déduit des cartes venues de son deck. « Deck non reconnu » = rien de\nreconnaissable n\u2019a été montré — jamais une supposition.",
                         "Inferred from cards played out of their deck. \u201cUnidentified\u201d\nmeans nothing recognisable was shown \u2014 never a guess."],
        "launchHs":["Lancer Hearthstone", "Launch Hearthstone"],
        "launchUnknown":["Aucun lanceur détecté. Colle ci-dessous la commande "
                         + "qui lance Hearthstone chez toi.",
                         "No launcher detected. Paste the command that starts "
                         + "Hearthstone on your machine below."],
        "launchCmdHint":["Commande de lancement (si la détection échoue)",
                         "Launch command (if detection fails)"],
        "logFull":   ["⚠ Le journal de Hearthstone est plein (limite Blizzard : 10 Mo par session) — le suivi est aveugle. REDÉMARRE HEARTHSTONE pour reprendre le tracking.",
                      "⚠ Hearthstone's log is full (Blizzard limit: 10 MB per session) — tracking is blind. RESTART HEARTHSTONE to resume."]
    })
    function tr(key) {
        var pair = strings[key]
        return pair === undefined ? key : pair[en ? 1 : 0]
    }

    // Menu déroulant habillé de bout en bout. Le style Basic ne peint QUE le
    // champ : sans redéfinir `popup` et `delegate`, la liste qui s'ouvre reste
    // blanche et hors sujet au milieu d'un panneau sombre.
    component StyledCombo: ComboBox {
        id: combo
        implicitHeight: 28

        background: Rectangle {
            id: comboBg
            radius: home.thm.rSm
            gradient: Gradient {
                GradientStop {
                    position: 0.0
                    color: Qt.lighter(home.thm.raised, combo.hovered ? 1.25 : 1.08)
                }
                GradientStop { position: 1.0; color: home.thm.sunken }
            }
            border.width: 1
            border.color: combo.popup.visible ? home.thm.goldLineHi
                        : combo.hovered ? home.thm.hairlineHi : home.thm.hairline
            GlowRing {
                anchors.fill: parent
                cornerRadius: comboBg.radius
                glowColor: home.thm.gold
                spread: 6
                intensity: combo.popup.visible ? 0.30 : (combo.hovered ? 0.16 : 0.0)
            }
        }
        contentItem: Text {
            leftPadding: 10
            rightPadding: 26
            text: combo.displayText
            color: home.thm.text
            font.pixelSize: 12
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        indicator: Text {
            x: combo.width - width - 9
            y: combo.height / 2 - height / 2
            text: "▾"
            color: combo.popup.visible ? home.thm.gold : home.thm.textDim
            font.pixelSize: 11
        }

        delegate: ItemDelegate {
            width: combo.width
            height: 28
            highlighted: combo.highlightedIndex === index
            background: Rectangle {
                color: highlighted ? Qt.alpha(home.thm.gold, 0.18) : "transparent"
            }
            contentItem: Item {
                anchors.fill: parent
                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 10
                    anchors.right: coche.left
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData !== undefined ? modelData : model[combo.textRole]
                    color: highlighted ? home.thm.gold : home.thm.text
                    font.pixelSize: 12
                    elide: Text.ElideRight
                }
                Text {   // la valeur courante est cochée, pas seulement surlignée
                    id: coche
                    anchors.right: parent.right
                    anchors.rightMargin: 9
                    anchors.verticalCenter: parent.verticalCenter
                    visible: combo.currentIndex === index
                    text: "✓"
                    color: home.thm.gold
                    font.pixelSize: 11
                    font.bold: true
                }
            }
        }

        popup: Popup {
            y: combo.height + 3
            width: combo.width
            // au-delà de dix entrées la liste défile au lieu de sortir de l'écran
            implicitHeight: Math.min(contentItem.implicitHeight + 8, 10 * 28 + 8)
            padding: 4
            background: Rectangle {
                id: popBg
                radius: home.thm.rMd
                color: home.thm.surfaceHi
                border.width: 1
                border.color: home.thm.goldLine
                GlowRing {
                    anchors.fill: parent
                    cornerRadius: popBg.radius
                    glowColor: home.thm.gold
                    spread: 8
                    intensity: 0.26
                }
            }
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: combo.popup.visible ? combo.delegateModel : null
                currentIndex: combo.highlightedIndex
                ScrollIndicator.vertical: ScrollIndicator { }
            }
        }
    }

    // Titre de section, repliable au clic quand ``section`` est renseigné.
    // L'état est retenu dans la configuration : les add-ons se règlent une
    // fois puis ne bougent plus, les garder dépliés obligeait à faire défiler
    // toute la grille pour atteindre les statistiques.
    component SectionTitle: RowLayout {
        id: titre
        property string label
        property string section: ""          // "" = section non repliable
        property string badge: ""            // compte affiché à droite du titre
        readonly property bool repliable: section !== ""
        property bool collapsed: repliable
                                 && tracker.sectionCollapsed(section, section === "addons")

        Layout.fillWidth: true
        Layout.topMargin: 10
        spacing: 8
        // liseré de section : dégradé or + halo, il sert de repère visuel quand
        // on fait défiler vite
        Rectangle {
            width: 3
            height: 15
            radius: 1.5
            gradient: Gradient {
                GradientStop { position: 0.0; color: home.thm.goldHi }
                GradientStop { position: 1.0; color: home.thm.gold }
            }
            GlowRing {
                anchors.fill: parent
                cornerRadius: 1.5
                glowColor: home.thm.gold
                spread: 5
                intensity: 0.35
            }
        }
        Text {
            visible: titre.repliable
            text: titre.collapsed ? "▸" : "▾"
            color: home.thm.gold
            font.pixelSize: 10
        }
        Text {
            text: titre.label
            color: titreHover.hovered ? home.thm.goldHi : home.thm.text
            font.pixelSize: 11
            font.bold: true
            font.letterSpacing: 2
        }
        StatPill {
            visible: titre.badge !== ""
            label: titre.badge
            tint: home.thm.gold
            fontSize: 9
            implicitHeight: 17
        }
        // filet qui s'évanouit vers la droite : une barre pleine coupait la
        // page en deux et faisait « tableau »
        Rectangle {
            Layout.fillWidth: true
            height: 1
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: home.thm.hairlineHi }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }

        HoverHandler {
            id: titreHover
            enabled: titre.repliable
            cursorShape: Qt.PointingHandCursor
        }
        TapHandler {
            enabled: titre.repliable
            onTapped: {
                titre.collapsed = !titre.collapsed
                tracker.setSectionCollapsed(titre.section, titre.collapsed)
            }
        }
    }

    Flickable {
        id: scroller
        objectName: "launcherScroller"   // repéré par les tests et les captures
        anchors.fill: parent
        anchors.margins: 16
        contentHeight: column.implicitHeight
        clip: true
        // barre de défilement fine et sombre : celle du style Basic est un
        // rectangle gris clair qui trouait le fond
        ScrollBar.vertical: ScrollBar {
            id: vbar
            width: 8
            policy: ScrollBar.AsNeeded
            contentItem: Rectangle {
                implicitWidth: 5
                radius: 2.5
                color: vbar.pressed ? home.thm.gold
                     : vbar.hovered ? Qt.alpha(home.thm.gold, 0.55)
                     : Qt.rgba(1, 1, 1, 0.16)
                Behavior on color { ColorAnimation { duration: 120 } }
            }
            background: Rectangle { color: "transparent" }
        }

        ColumnLayout {
            id: column
            width: parent.width - 12
            spacing: 10

            // ---- en-tête ---------------------------------------------------
            RowLayout {
                Layout.fillWidth: true
                Layout.bottomMargin: 2
                spacing: 11
                // marque : trois pierres empilées — un cairn balise le chemin
                Item {
                    width: 30; height: 32
                    Rectangle {
                        width: 24; height: 9; radius: 4.5
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 20
                        color: home.thm.textFaint
                    }
                    Rectangle {
                        width: 17; height: 8; radius: 4
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 11
                        color: home.thm.textDim
                    }
                    Rectangle {   // la pierre de faîte, en braise — elle rayonne
                        width: 11; height: 7; radius: 3.5
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 3
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: home.thm.goldHi }
                            GradientStop { position: 1.0; color: home.thm.gold }
                        }
                        GlowRing {
                            anchors.fill: parent
                            cornerRadius: 3.5
                            glowColor: home.thm.gold
                            spread: 7
                            intensity: 0.42
                        }
                    }
                }
                ColumnLayout {
                    spacing: 1
                    Text {
                        text: "Cairn"
                        color: home.thm.text
                        font.pixelSize: 23
                        font.bold: true
                        font.letterSpacing: 0.5
                    }
                    Text {
                        text: home.tr("tagline")
                        color: home.thm.textFaint
                        font.pixelSize: 10
                        font.letterSpacing: 0.4
                    }
                }
                Item { Layout.fillWidth: true }

                // bascule de langue : segmenté FR | EN, la case active éclairée
                Rectangle {
                    width: 62
                    height: 24
                    radius: 12
                    color: home.thm.sunken
                    border.width: 1
                    border.color: home.thm.hairline
                    Row {
                        anchors.centerIn: parent
                        spacing: 0
                        Repeater {
                            model: ["fr", "en"]
                            delegate: Rectangle {
                                id: langCase
                                required property string modelData
                                readonly property bool actif:
                                    tracker.language === modelData
                                width: 29; height: 20; radius: 10
                                color: actif ? Qt.alpha(home.thm.gold, 0.20)
                                             : "transparent"
                                border.width: 1
                                border.color: actif ? home.thm.goldLine : "transparent"
                                GlowRing {
                                    anchors.fill: parent
                                    cornerRadius: 10
                                    glowColor: home.thm.gold
                                    spread: 4
                                    intensity: langCase.actif ? 0.22 : 0.0
                                }
                                Text {
                                    anchors.centerIn: parent
                                    text: langCase.modelData.toUpperCase()
                                    color: langCase.actif ? home.thm.goldHi
                                                          : home.thm.textFaint
                                    font.pixelSize: 10
                                    font.bold: langCase.actif
                                    font.letterSpacing: 0.5
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: tracker.setLanguage(langCase.modelData)
                                }
                            }
                        }
                    }
                }

                // statut de connexion : pastille qui pulse tant que le jeu est
                // là, fixe et éteinte sinon — repérable du coin de l'œil
                Rectangle {
                    id: hsBadge
                    readonly property color tint:
                        tracker.hsRunning ? home.thm.good : home.thm.gold
                    width: hsRow.implicitWidth + 20
                    height: 26
                    radius: 13
                    color: Qt.alpha(tint, tracker.hsRunning ? 0.12 : 0.07)
                    border.width: 1
                    border.color: Qt.alpha(tint, tracker.hsRunning ? 0.45 : 0.25)
                    GlowRing {
                        anchors.fill: parent
                        cornerRadius: 13
                        glowColor: hsBadge.tint
                        spread: 6
                        intensity: tracker.hsRunning ? 0.26 : 0.10
                    }
                    Row {
                        id: hsRow
                        anchors.centerIn: parent
                        spacing: 7
                        PulseDot {
                            anchors.verticalCenter: parent.verticalCenter
                            tint: hsBadge.tint
                            pulsing: tracker.hsRunning
                            coreSize: 7
                        }
                        Text {
                            id: hsStatus
                            anchors.verticalCenter: parent.verticalCenter
                            // le point décoratif du libellé ferait doublon avec
                            // la pastille : on ne garde que les mots
                            text: home.tr(tracker.hsRunning ? "hsOn" : "hsOff")
                                      .replace(/^[●○]\s*/, "")
                            color: tracker.hsRunning ? home.thm.goodHi
                                                     : home.thm.textDim
                            font.pixelSize: 10
                            font.bold: tracker.hsRunning
                            font.letterSpacing: 0.3
                        }
                    }
                }
            }

            Text {
                visible: tracker.logStatus !== ""
                text: tracker.logStatus
                color: tracker.logFull ? home.thm.badHi : home.thm.textFaint
                font.pixelSize: 10
                Layout.fillWidth: true
            }

            // ---- lancer Hearthstone --------------------------------------
            // Panneau à part, et surtout PAS dans celui de l'installation
            // incomplète : ce dernier ne s'affiche qu'en cas de problème, donc
            // le bouton y restait invisible sur une installation saine.
            Panel {
                visible: !tracker.hsRunning
                Layout.fillWidth: true
                implicitHeight: playCol.implicitHeight + 20
                ColumnLayout {
                    id: playCol
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 6

                    CtaButton {
                        visible: tracker.canLaunchHs
                        Layout.fillWidth: true
                        implicitHeight: 34
                        tint: home.thm.good
                        label: home.tr("launchHs")
                        onClicked: launchError.text = tracker.launchHs()
                    }
                    Text {
                        // On montre TOUJOURS la commande qui sera exécutée : un
                        // bouton qui démarre un processus sans dire lequel est
                        // une boîte noire.
                        visible: tracker.canLaunchHs
                        text: tracker.hsLaunchLabel + " · " + tracker.hsLaunchCommand
                        color: home.thm.textDim
                        font.pixelSize: 10
                        Layout.fillWidth: true
                        elide: Text.ElideMiddle
                    }
                    Text {
                        // seulement quand la détection a VRAIMENT conclu
                        visible: tracker.hsLaunchResolved && !tracker.canLaunchHs
                        text: home.tr("launchUnknown")
                        color: home.thm.textDim
                        font.pixelSize: 11
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        id: launchError
                        visible: text !== ""
                        color: home.thm.badHi
                        font.pixelSize: 11
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                    }

                    // Repli universel : aucune détection ne trouvera un script
                    // maison, Bottles ou un umu-run bricolé. C'est ce champ, et
                    // pas la détection, qui fait marcher la fonctionnalité pour
                    // tout le monde.
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        TextField {
                            id: cmdField
                            Layout.fillWidth: true
                            text: tracker.hsLaunchCustom
                            placeholderText: home.tr("launchCmdHint")
                            color: home.thm.text
                            font.pixelSize: 11
                            background: Rectangle {
                                radius: 6
                                color: Qt.alpha(home.thm.text, 0.05)
                                border.width: 1
                                border.color: Qt.alpha(home.thm.text, 0.15)
                            }
                            onEditingFinished: tracker.setHsLaunchCommand(text)
                        }
                        IconButton {
                            glyph: "✓"
                            onClicked: {
                                tracker.setHsLaunchCommand(cmdField.text)
                                launchError.text = ""
                            }
                        }
                    }
                }
            }

            // ---- installation incomplète (prefix / journaux) --------------
            Panel {
                visible: tracker.setupProblem !== ""
                Layout.fillWidth: true
                implicitHeight: setupCol.implicitHeight + 20
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.alpha(home.thm.bad, 0.16) }
                    GradientStop { position: 1.0; color: Qt.alpha(home.thm.bad, 0.07) }
                }
                borderTint: Qt.alpha(home.thm.bad, 0.55)
                glowTint: home.thm.bad
                glowIntensity: 0.22

                ColumnLayout {
                    id: setupCol
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 8

                    Text {
                        text: home.tr(tracker.setupProblem === "no_prefix" ? "noPrefix"
                                    : tracker.setupProblem === "log_capped" ? "logCapped"
                                    : "logsOff")
                        color: home.thm.badHi
                        font.pixelSize: 12
                        font.bold: true
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        visible: tracker.hsPrefix !== ""
                        text: home.tr("prefixFound") + tracker.hsPrefix
                        color: home.thm.textDim
                        font.pixelSize: 10
                        Layout.fillWidth: true
                        elide: Text.ElideMiddle
                    }
                    CtaButton {
                        visible: tracker.setupProblem === "logs_off"
                                 || tracker.setupProblem === "log_capped"
                        Layout.fillWidth: true
                        implicitHeight: 32
                        tint: home.thm.gold
                        label: home.tr(tracker.setupProblem === "log_capped"
                                       ? "liftCap" : "enableLogs")
                        onClicked: tracker.enableGameLogs()
                    }

                }
            }

            // ---- alerte : log HS saturé (limite Blizzard 10 Mo) -----------
            Panel {
                visible: tracker.logFull
                Layout.fillWidth: true
                implicitHeight: logFullText.implicitHeight + 20
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.alpha(home.thm.bad, 0.16) }
                    GradientStop { position: 1.0; color: Qt.alpha(home.thm.bad, 0.07) }
                }
                borderTint: Qt.alpha(home.thm.bad, 0.55)
                glowTint: home.thm.bad
                glowIntensity: 0.22
                Text {
                    id: logFullText
                    anchors.fill: parent
                    anchors.margins: 10
                    text: home.tr("logFull")
                    color: home.thm.badHi
                    font.pixelSize: 12
                    font.bold: true
                    wrapMode: Text.WordWrap
                }
            }

            // ---- add-ons ---------------------------------------------------
            SectionTitle {
                id: addonsTitle
                label: home.tr("addons")
                section: "addons"
                badge: tracker.addonsBadge
            }
            // Fiches en grille plutôt qu'une liste de cases à cocher : dix-sept
            // lignes identiques ne se parcourent pas, et le titre seul ne disait
            // pas à quoi servait l'add-on (« j'ai "entrées" mais je sais pas ce
            // que c'est »). Chaque fiche porte son icône, son rôle et son
            // interrupteur.
            Grid {
                id: addonsGrid
                visible: !addonsTitle.collapsed
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 8
                rowSpacing: 8
                // Largeur des fiches déduite de la FENÊTRE, pas de la grille :
                // la calculer sur `width` bouclait (la grille se dimensionne sur
                // ses enfants, qui se dimensionnaient sur elle) et le QML partait
                // en boucle de liaisons — chargement figé, vérifié.
                readonly property int cardW:
                    Math.max(160, Math.floor((home.width - 2 * 16 - 12 - columnSpacing) / 2))

                Repeater {
                    model: tracker.addonsModel
                    delegate: Rectangle {
                        id: card
                        width: addonsGrid.cardW
                        height: 76
                        radius: home.thm.rMd
                        // fiche allumée = teintée d'or ; éteinte = surface nue.
                        // Le dégradé évite l'aplat, qui « à plat » ne distingue
                        // pas les deux états d'assez loin.
                        gradient: Gradient {
                            GradientStop {
                                position: 0.0
                                color: model.enabled
                                    ? Qt.alpha(home.thm.gold, cardHover.hovered ? 0.16 : 0.11)
                                    : Qt.lighter(home.thm.surface,
                                                 cardHover.hovered ? 1.30 : 1.12)
                            }
                            GradientStop {
                                position: 1.0
                                color: model.enabled ? Qt.alpha(home.thm.gold, 0.04)
                                                     : home.thm.surface
                            }
                        }
                        border.width: 1
                        border.color: model.enabled
                            ? (cardHover.hovered ? home.thm.goldLineHi : home.thm.goldLine)
                            : (cardHover.hovered ? home.thm.hairlineHi : home.thm.hairline)

                        GlowRing {
                            anchors.fill: parent
                            cornerRadius: card.radius
                            glowColor: home.thm.gold
                            spread: 6
                            intensity: model.enabled
                                ? (cardHover.hovered ? 0.34 : 0.16)
                                : (cardHover.hovered ? 0.12 : 0.0)
                        }

                        // toute la fiche bascule l'add-on : viser un petit
                        // interrupteur à la souris n'apporte rien
                        HoverHandler { id: cardHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler {
                            onTapped: tracker.setAddonEnabled(model.key, !model.enabled)
                        }

                        Rectangle {   // pastille d'icône
                            id: badge
                            x: 9
                            y: 9
                            width: 28
                            height: 28
                            radius: home.thm.rSm
                            gradient: Gradient {
                                GradientStop {
                                    position: 0.0
                                    color: model.enabled ? Qt.alpha(home.thm.gold, 0.26)
                                                         : Qt.lighter(home.thm.raised, 1.15)
                                }
                                GradientStop {
                                    position: 1.0
                                    color: model.enabled ? Qt.alpha(home.thm.gold, 0.10)
                                                         : home.thm.sunken
                                }
                            }
                            border.width: 1
                            border.color: model.enabled ? home.thm.goldLineHi
                                                        : home.thm.hairline
                            GlowRing {
                                anchors.fill: parent
                                cornerRadius: badge.radius
                                glowColor: home.thm.gold
                                spread: 4
                                intensity: model.enabled ? 0.24 : 0.0
                            }
                            Text {
                                anchors.centerIn: parent
                                text: model.icon
                                color: model.enabled ? home.thm.goldHi : home.thm.textFaint
                                font.pixelSize: 14
                            }
                        }

                        Text {
                            id: cardTitle
                            anchors.left: badge.right
                            anchors.leftMargin: 9
                            anchors.right: knob.left
                            anchors.rightMargin: 6
                            y: 10
                            text: model.label
                            color: model.enabled ? home.thm.text : home.thm.textDim
                            font.pixelSize: 12
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        Text {
                            anchors.left: badge.right
                            anchors.leftMargin: 9
                            anchors.right: parent.right
                            anchors.rightMargin: 9
                            anchors.top: cardTitle.bottom
                            anchors.topMargin: 3
                            text: model.desc
                            color: model.enabled ? home.thm.textDim : home.thm.textFaint
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                            maximumLineCount: 2
                            elide: Text.ElideRight
                        }

                        // interrupteur miniature — même langage visuel que
                        // NeonSwitch, mais sans zone cliquable propre : c'est
                        // la fiche entière qui bascule
                        Rectangle {
                            id: knob
                            anchors.right: parent.right
                            anchors.rightMargin: 9
                            y: 11
                            width: 32
                            height: 17
                            radius: 8.5
                            gradient: Gradient {
                                GradientStop {
                                    position: 0.0
                                    color: model.enabled ? home.thm.goldHi
                                                         : Qt.lighter(home.thm.raised, 1.1)
                                }
                                GradientStop {
                                    position: 1.0
                                    color: model.enabled ? home.thm.gold : home.thm.sunken
                                }
                            }
                            border.width: 1
                            border.color: model.enabled ? Qt.alpha(home.thm.gold, 0.85)
                                                        : home.thm.hairline
                            GlowRing {
                                anchors.fill: parent
                                cornerRadius: 8.5
                                glowColor: home.thm.gold
                                spread: 4
                                intensity: model.enabled ? 0.30 : 0.0
                            }
                            Rectangle {
                                width: 13
                                height: 13
                                radius: 6.5
                                y: 2
                                x: model.enabled ? parent.width - width - 2 : 2
                                color: model.enabled ? home.thm.knob : home.thm.textDim
                                Behavior on x {
                                    NumberAnimation { duration: 140; easing.type: Easing.OutCubic }
                                }
                                Behavior on color { ColorAnimation { duration: 140 } }
                            }
                        }
                    }
                }
            }

            // ---- fenêtres & échelles --------------------------------------
            SectionTitle { label: home.tr("windows") }
            Panel {
                Layout.fillWidth: true
                implicitHeight: winCol.implicitHeight + 24
                ColumnLayout {
                    id: winCol
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 7

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: home.tr("oppPanel")
                            color: home.thm.text
                            font.pixelSize: 12
                            Layout.fillWidth: true
                        }
                        NeonSwitch {
                            checked: tracker.oppPanelEnabled
                            onToggled: tracker.setOppPanelEnabled(checked)
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: home.tr("myHand")
                            color: home.thm.text
                            font.pixelSize: 12
                            Layout.fillWidth: true
                        }
                        NeonSwitch {
                            checked: tracker.myHandEnabled
                            onToggled: tracker.setMyHandEnabled(checked)
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: home.tr("myPlays")
                            color: home.thm.text
                            font.pixelSize: 12
                            Layout.fillWidth: true
                        }
                        NeonSwitch {
                            checked: tracker.myPlaysEnabled
                            onToggled: tracker.setMyPlaysEnabled(checked)
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        ColumnLayout {
                            spacing: 1
                            Layout.fillWidth: true
                            Text {
                                text: home.tr("handDots")
                                color: home.thm.text
                                font.pixelSize: 12
                            }
                            Text {
                                Layout.fillWidth: true
                                text: home.tr("handDotsHint")
                                color: home.thm.textDim
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }
                        }
                        NeonSwitch {
                            checked: tracker.handDotsEnabled
                            onToggled: tracker.setHandDotsEnabled(checked)
                        }
                    }

                    Rectangle {   // séparateur discret avant les jauges
                        Layout.fillWidth: true
                        Layout.topMargin: 2
                        height: 1
                        color: home.thm.hairlineSoft
                    }

                    component ScaleRow: RowLayout {
                        property string label
                        property string which
                        property real current: 1.0
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: label
                            color: home.thm.text
                            font.pixelSize: 12
                            Layout.preferredWidth: 150
                        }
                        NeonSlider {
                            id: slider
                            from: 0.7; to: 1.8; stepSize: 0.05
                            value: current
                            Layout.fillWidth: true
                            onMoved: tracker.setScale(which, value)
                        }
                        // la valeur est un badge : elle s'aligne et se lit d'un
                        // coup d'œil au lieu de flotter au bout de la ligne
                        StatPill {
                            label: Math.round(slider.value * 100) + " %"
                            tint: home.thm.gold
                            fontSize: 10
                            implicitWidth: 46
                            implicitHeight: 19
                        }
                    }
                    ScaleRow { label: home.tr("sizeDeck"); which: "panel_scale"; current: tracker.panelScale }
                    ScaleRow { label: home.tr("sizeOpp"); which: "opp_scale"; current: tracker.oppScale }
                    ScaleRow { label: home.tr("sizeBar"); which: "bar_scale"; current: tracker.barScale }

                    // Filet de sécurité : un widget poussé hors écran (écran
                    // débranché, changement de résolution) est irrattrapable
                    // à la souris — il faut un moyen de tout ramener.
                    CtaButton {
                        Layout.fillWidth: true
                        Layout.topMargin: 6
                        implicitHeight: 32
                        strong: false
                        tint: home.thm.blue
                        // ↺ et non ⟲ : ce dernier est tracé si finement qu'à
                        // 13 px il se réduit à deux points illisibles
                        glyph: "↺"
                        label: home.tr("resetPos")
                        onClicked: tracker.resetPositions()
                    }
                    Text {
                        Layout.fillWidth: true
                        text: home.tr("resetPosHint")
                        color: home.thm.textDim
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                    }
                }
            }

            // ---- partage volontaire (le consentement se pose au 1er lancement)
            SectionTitle { label: home.tr("sharing") }
            Panel {
                Layout.fillWidth: true
                implicitHeight: partageCol.implicitHeight + 24
                ColumnLayout {
                    id: partageCol
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 9

                    RowLayout {
                        Layout.fillWidth: true
                        ColumnLayout {
                            spacing: 1
                            Layout.fillWidth: true
                            Text {
                                text: home.tr("shareOn")
                                color: home.thm.text
                                font.pixelSize: 12
                            }
                            Text {
                                text: home.tr("shareHint")
                                color: home.thm.textDim
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                        NeonSwitch {
                            checked: tracker.shareGames
                            onToggled: tracker.setShareGames(checked)
                        }
                    }

                    Rectangle {
                        visible: tracker.shareGames
                        Layout.fillWidth: true; height: 1; color: home.thm.hairlineSoft
                    }

                    // L'anonymisation n'est PAS un interrupteur : elle est
                    // inconditionnelle. Le consentement de l'utilisateur ne
                    // couvre que lui, jamais son adversaire, qui apparaît dans
                    // le même journal sans avoir rien accepté. Reste une ligne
                    // qui dit ce qui part — la rassurance vaut mieux que le
                    // silence, mais elle ne se coche pas.
                    RowLayout {
                        visible: tracker.shareGames
                        Layout.fillWidth: true
                        spacing: 6
                        Text {
                            text: "🔒"
                            font.pixelSize: 12
                        }
                        Text {
                            text: home.tr("anonymAlways")
                            color: home.thm.good
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }

                    Rectangle {
                        visible: tracker.shareGames
                        Layout.fillWidth: true; height: 1; color: home.thm.hairlineSoft
                    }

                    // Identifiant d'installation. Il voyage avec chaque envoi
                    // depuis toujours ; ce qui manquait, c'était de pouvoir le
                    // LIRE. Sans lui, « retrouve mes parties dans le corpus »
                    // et « efface mes données » sont deux demandes que
                    // personne ne peut formuler.
                    ColumnLayout {
                        visible: tracker.shareGames
                        Layout.fillWidth: true
                        spacing: 4
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            Text {
                                text: home.tr("installId")
                                color: home.thm.text
                                font.pixelSize: 12
                            }
                            Text {
                                text: tracker.installId
                                color: home.thm.textDim
                                font.pixelSize: 10
                                font.family: "monospace"
                                elide: Text.ElideMiddle
                                Layout.fillWidth: true
                            }
                            Text {
                                id: copieLien
                                property bool fait: false
                                text: copieLien.fait ? home.tr("copied") : home.tr("copy")
                                color: copieSouris.containsMouse ? home.thm.blueHi
                                                                 : home.thm.textDim
                                font.pixelSize: 11
                                font.underline: !copieLien.fait
                                MouseArea {
                                    id: copieSouris
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        tracker.copyInstallId()
                                        copieLien.fait = true
                                        retourCopie.restart()
                                    }
                                }
                                Timer {
                                    id: retourCopie
                                    interval: 1800
                                    onTriggered: copieLien.fait = false
                                }
                            }
                        }
                        Text {
                            text: home.tr("installIdHint")
                            color: home.thm.textDim
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }

                    Rectangle {
                        visible: tracker.shareGames
                        Layout.fillWidth: true; height: 1; color: home.thm.hairlineSoft
                    }

                    // Rang déclaré : introuvable dans les journaux du jeu
                    // (Firestone le lit en mémoire), donc saisi à la main.
                    ColumnLayout {
                        visible: tracker.shareGames
                        Layout.fillWidth: true
                        spacing: 4
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            Text {
                                text: home.tr("rank")
                                color: home.thm.text
                                font.pixelSize: 12
                                Layout.preferredWidth: 64
                            }
                            StyledCombo {
                                id: ligueBox
                                objectName: "rankLeagueCombo"
                                model: tracker.rankLeagues
                                currentIndex: tracker.rankLeagueIndex
                                Layout.fillWidth: true
                                // Le palier se lit dans le MODÈLE, pas dans l'index :
                                // le modèle descend de 10 à 1, donc l'index 0 vaut le
                                // palier 10. Passer « index + 1 » inversait l'échelle et
                                // changeait le palier à chaque changement de ligue
                                // (Or 5 devenait Platine 6).
                                onActivated: tracker.setRank(currentIndex, niveauBox.palier)
                            }
                            StyledCombo {
                                id: niveauBox
                                objectName: "rankLevelCombo"
                                visible: tracker.rankHasLevel
                                model: [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
                                currentIndex: tracker.rankLevel > 0 ? 10 - tracker.rankLevel : 0
                                // Le palier réellement affiché, quel que soit le chemin
                                // par lequel l'index a été posé. Une seule définition,
                                // partagée par les deux listes.
                                readonly property int palier: model[currentIndex]
                                Layout.preferredWidth: 70
                                onActivated: tracker.setRank(ligueBox.currentIndex, palier)
                            }
                        }
                        Text {
                            text: home.tr("rankHint")
                            color: home.thm.textDim
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }

                    RowLayout {
                        visible: tracker.shareGames && tracker.outboxSummary !== ""
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: home.tr("queued") + tracker.outboxSummary
                            color: home.thm.textDim
                            font.pixelSize: 11
                            Layout.fillWidth: true
                        }
                        component Lien: Text {
                            property string libelle
                            signal active()
                            text: libelle
                            // bleu mana pour tout ce qui est lien, comme le
                            // veut le design system
                            color: lienSouris.containsMouse ? home.thm.blueHi
                                                            : home.thm.textDim
                            font.pixelSize: 11
                            font.underline: true
                            MouseArea {
                                id: lienSouris
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: active()
                            }
                        }
                        // L'envoi se fait tout seul entre deux parties ; ce
                        // lien sert quand on veut forcer le passage (réseau
                        // rebranché, session abandonnée après trop d'échecs).
                        Lien {
                            visible: tracker.shareConfigured
                            libelle: home.tr("sendNow")
                            onActive: tracker.sendOutboxNow()
                        }
                        Lien { libelle: home.tr("seeQueue"); onActive: tracker.openOutbox() }
                        Lien { libelle: home.tr("clearQueue"); onActive: tracker.clearOutbox() }
                    }

                    // Sans point de collecte configuré, rien ne partira jamais :
                    // le dire vaut mieux qu'un compteur qui monte sans fin.
                    Text {
                        visible: tracker.shareGames && !tracker.shareConfigured
                                 && tracker.outboxSummary !== ""
                        text: home.tr("noEndpoint")
                        color: home.thm.textDim
                        font.pixelSize: 10
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }

            // ---- archives de sessions --------------------------------------
            // Hearthstone efface ses vieux dossiers de journaux sans prévenir,
            // et l'historique ne garde qu'un résumé par partie : sans archive,
            // « quelles cartes ont été jouées » devient définitivement
            // irrécupérable au bout de quelques jours.
            SectionTitle { label: home.tr("archives") }
            Panel {
                Layout.fillWidth: true
                implicitHeight: arcCol.implicitHeight + 24
                ColumnLayout {
                    id: arcCol
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 7

                    RowLayout {
                        Layout.fillWidth: true
                        ColumnLayout {
                            spacing: 1
                            Layout.fillWidth: true
                            Text {
                                text: home.tr("archiveOn")
                                color: home.thm.text
                                font.pixelSize: 12
                            }
                            Text {
                                Layout.fillWidth: true
                                text: home.tr("archiveHint")
                                color: home.thm.textDim
                                font.pixelSize: 10
                                wrapMode: Text.WordWrap
                            }
                        }
                        NeonSwitch {
                            checked: tracker.archiveEnabled
                            onToggled: tracker.setArchiveEnabled(checked)
                        }
                    }

                    RowLayout {
                        visible: tracker.archiveSummary !== ""
                        Layout.fillWidth: true
                        spacing: 10
                        Text {
                            text: home.tr("archived") + tracker.archiveSummary
                            color: home.thm.textDim
                            font.pixelSize: 11
                            Layout.fillWidth: true
                        }
                        Text {
                            text: home.tr("seeQueue")
                            color: arcSouris.containsMouse ? home.thm.blueHi
                                                           : home.thm.textDim
                            font.pixelSize: 11
                            font.underline: true
                            MouseArea {
                                id: arcSouris
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: tracker.openArchive()
                            }
                        }
                    }
                }
            }

            // ---- winrates par deck (cliquer = filtrer les sections) -------
            SectionTitle { label: home.tr("myDecks") }
            Text {
                visible: tracker.overallSummary !== ""
                text: home.tr("overall") + tracker.overallSummary
                color: home.thm.textDim
                font.pixelSize: 11
            }
            Panel {
                Layout.fillWidth: true
                implicitHeight: deckStatsCol.implicitHeight + 20
                ColumnLayout {
                    id: deckStatsCol
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 3
                    Text {
                        visible: deckRepeater.count === 0
                        text: home.tr("noGames")
                        color: home.thm.textFaint
                        font.pixelSize: 11
                        font.italic: true
                    }
                    Text {
                        visible: deckRepeater.count > 0
                        text: home.tr("clickDeck")
                        color: home.thm.textFaint
                        font.pixelSize: 10
                        font.italic: true
                        Layout.bottomMargin: 3
                    }
                    Repeater {
                        id: deckRepeater
                        model: tracker.deckStatsModel
                        delegate: Rectangle {
                            id: deckRow
                            readonly property bool selected: tracker.selectedDeck === model.name
                            readonly property color wrTint: home.thm.pctColor(model.pct)
                            Layout.fillWidth: true
                            implicitHeight: 30
                            radius: home.thm.rSm
                            color: deckRow.selected ? Qt.alpha(home.thm.gold, 0.13)
                                 : deckMouse.containsMouse ? Qt.rgba(1, 1, 1, 0.05)
                                 : "transparent"
                            border.width: 1
                            border.color: deckRow.selected ? home.thm.goldLine : "transparent"
                            clip: true

                            // jauge de fond proportionnelle au winrate : la
                            // comparaison entre decks se fait à l'œil, sans
                            // lire les chiffres un par un
                            Rectangle {
                                anchors.left: parent.left
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                width: parent.width * Math.min(model.pct, 100) / 100
                                radius: parent.radius
                                gradient: Gradient {
                                    orientation: Gradient.Horizontal
                                    GradientStop {
                                        position: 0.0
                                        color: Qt.alpha(deckRow.wrTint, 0.16)
                                    }
                                    GradientStop {
                                        position: 1.0
                                        color: Qt.alpha(deckRow.wrTint, 0.03)
                                    }
                                }
                            }

                            GlowRing {
                                anchors.fill: parent
                                cornerRadius: deckRow.radius
                                glowColor: home.thm.gold
                                spread: 5
                                intensity: deckRow.selected ? 0.24 : 0.0
                            }

                            MouseArea {
                                id: deckMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: tracker.selectDeck(model.name)

                                // Forme des parties : un deck qui gagne court
                                // et perd long ne se joue pas comme celui qui
                                // fait l'inverse, et le winrate seul ne le dit
                                // jamais. En infobulle plutôt qu'en colonne :
                                // on le consulte, on ne le parcourt pas.
                                ToolTip.visible: containsMouse
                                                 && (model.shapeWin !== ""
                                                     || model.shapeLoss !== "")
                                ToolTip.delay: 350
                                ToolTip.text:
                                    (model.shapeWin !== ""
                                     ? (tracker.language === "en" ? "Wins: " : "Victoires : ")
                                       + model.shapeWin : "")
                                    + (model.shapeWin !== "" && model.shapeLoss !== ""
                                       ? "\n" : "")
                                    + (model.shapeLoss !== ""
                                       ? (tracker.language === "en" ? "Losses: " : "Défaites : ")
                                         + model.shapeLoss : "")
                            }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 9
                                anchors.rightMargin: 8
                                spacing: 8

                                Text {
                                    text: model.name
                                    color: deckRow.selected ? home.thm.goldHi : home.thm.text
                                    font.pixelSize: 12
                                    font.bold: deckRow.selected
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                // durée moyenne d'une partie avec ce deck :
                                // le winrate dit si on gagne, pas ce que ça coûte
                                Text {
                                    visible: model.duration !== ""
                                    text: model.duration
                                    color: home.thm.textDim
                                    font.pixelSize: 11
                                }
                                Text {
                                    text: model.games
                                           + home.tr(model.games === 1 ? "game1" : "games")
                                    color: home.thm.textFaint
                                    font.pixelSize: 10
                                    horizontalAlignment: Text.AlignRight
                                    Layout.preferredWidth: 62
                                }
                                // bilan brut : victoires en vert, défaites en
                                // rouge, séparées — « 13-6 » en gris ne disait
                                // pas lequel des deux chiffres était lequel
                                Row {
                                    Layout.preferredWidth: 46
                                    Text {
                                        text: model.wins
                                        color: home.thm.good
                                        font.pixelSize: 12
                                        font.bold: true
                                    }
                                    Text {
                                        text: " – "
                                        color: home.thm.textFaint
                                        font.pixelSize: 11
                                    }
                                    Text {
                                        text: model.games - model.wins
                                        color: home.thm.bad
                                        font.pixelSize: 12
                                        font.bold: true
                                    }
                                }
                                StatPill {
                                    pct: model.pct
                                    glowing: deckRow.selected
                                    implicitWidth: 48
                                }
                                // archiver : repart de zéro en gardant les données
                                IconButton {
                                    label: home.tr("archive")
                                    tint: home.thm.blue
                                    implicitWidth: 56
                                    onClicked: tracker.archiveDeck(model.name)
                                }
                                // supprimer : destructif → confirmation explicite
                                IconButton {
                                    glyph: "✕"
                                    tint: home.thm.bad
                                    onClicked: confirm.askDeck(model.name, model.games)
                                }
                            }
                        }
                    }
                }
            }

            // ---- saisie manuelle d'une partie -----------------------------
            SectionTitle { label: home.tr("addTitle") }
            Panel {
                Layout.fillWidth: true
                implicitHeight: manualCol.implicitHeight + 24

                ColumnLayout {
                    id: manualCol
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 9

                    Text {
                        text: home.tr("addHint")
                        color: home.thm.textFaint
                        font.pixelSize: 10
                        font.italic: true
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                    }

                    component PickerRow: RowLayout {
                        property string label
                        property var choices: []
                        // liaison directe : un signal émis à Component.onCompleted
                        // n'atteignait pas l'instance, et « current » restait vide
                        // tant qu'on n'avait pas déroulé la liste (partie manuelle
                        // enregistrée sans classe adverse)
                        readonly property string current: box.currentText
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            text: label
                            color: home.thm.text
                            font.pixelSize: 12
                            Layout.preferredWidth: 64
                        }
                        StyledCombo {
                            id: box
                            model: choices
                            Layout.fillWidth: true
                        }
                    }

                    PickerRow {
                        id: deckPick
                        label: home.tr("deck")
                        choices: tracker.knownDecks
                    }
                    PickerRow {
                        id: classPick
                        label: home.tr("opponent")
                        choices: tracker.classNames
                    }

                    // Deux gros CTA distincts : c'est le geste le plus fréquent
                    // de cette section, il mérite des cibles larges et une
                    // couleur qui ne laisse aucun doute sur ce qu'on enregistre.
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: 2
                        spacing: 10
                        component ResultButton: CtaButton {
                            property bool win: true
                            Layout.fillWidth: true
                            implicitHeight: 40
                            fontSize: 13
                            tint: win ? home.thm.good : home.thm.bad
                            glyph: win ? "✓" : "✗"
                            onClicked: {
                                tracker.addManualGame(
                                    deckPick.current,
                                    tracker.classKey(classPick.current),
                                    win)
                                added.restart()
                            }
                        }
                        // les libellés traduits portent déjà leur pictogramme,
                        // qui ferait doublon avec celui du bouton
                        ResultButton {
                            label: home.tr("win").replace(/^[✓✗]\s*/, "")
                            win: true
                        }
                        ResultButton {
                            label: home.tr("loss").replace(/^[✓✗]\s*/, "")
                            win: false
                        }
                    }

                    Text {
                        id: addedMsg
                        visible: false
                        text: home.tr("added")
                        color: home.thm.goodHi
                        font.pixelSize: 10
                        font.bold: true
                    }
                    Timer {
                        id: added
                        interval: 2000
                        onTriggered: addedMsg.visible = false
                        onRunningChanged: if (running) addedMsg.visible = true
                    }
                }
            }

            // ---- winrates par classe adverse ------------------------------
            SectionTitle {
                label: home.tr("vsClasses")
                      + (tracker.selectedDeck !== "" ? " — " + tracker.selectedDeck : "")
            }
            Panel {
                Layout.fillWidth: true
                implicitHeight: classCol.implicitHeight + 20
                ColumnLayout {
                    id: classCol
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 3
                    Repeater {
                        model: tracker.classStatsModel
                        delegate: Rectangle {
                            id: classRow
                            readonly property int total: model.wins + model.losses
                            Layout.fillWidth: true
                            implicitHeight: 32
                            radius: home.thm.rSm
                            color: tracker.selectedClass === model.key
                                 ? Qt.alpha(home.thm.gold, 0.11)
                                 : classHover.hovered ? Qt.rgba(1, 1, 1, 0.05)
                                                      : "transparent"
                            border.width: 1
                            border.color: tracker.selectedClass === model.key
                                        ? home.thm.goldLine : "transparent"
                            HoverHandler { id: classHover }
                            // second niveau de filtre : deck → classe → archétypes
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: tracker.selectClass(model.key)
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 5
                                anchors.rightMargin: 8
                                spacing: 9

                                // médaillon aux couleurs de la classe : la
                                // ligne se repère à la teinte avant même
                                // d'avoir lu le nom
                                ClassAvatar {
                                    classKey: model.key
                                    size: 24
                                    highlighted: classHover.hovered
                                }
                                Text {
                                    text: model.label
                                    color: tracker.selectedClass === model.key
                                         ? home.thm.goldHi : home.thm.text
                                    font.pixelSize: 12
                                    font.bold: tracker.selectedClass === model.key
                                    elide: Text.ElideRight
                                    Layout.preferredWidth: 130
                                }
                                // combien de temps dure une partie CONTRE cette
                                // classe : deux matchups à 50 % ne coûtent pas
                                // le même temps, et c'est ce qui décide quoi
                                // jouer quand on n'a qu'une heure devant soi.
                                Text {
                                    visible: model.duration !== ""
                                    text: model.duration
                                    color: home.thm.textDim
                                    font.pixelSize: 11
                                    horizontalAlignment: Text.AlignRight
                                    Layout.preferredWidth: 46
                                }
                                // barre victoires / défaites : deux segments
                                // proportionnels, lisibles d'un seul regard.
                                // Les défaites y sont plus discrètes que les
                                // victoires — sinon la barre devient un damier
                                // rouge/vert qu'on ne lit plus.
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 6
                                    radius: 3
                                    color: home.thm.sunken
                                    border.width: 1
                                    border.color: home.thm.hairlineSoft

                                    // fond rouge sur toute la longueur, barre
                                    // verte par-dessus : superposer plutôt que
                                    // juxtaposer garde les deux extrémités
                                    // arrondies (le clip de Qt est carré)
                                    Rectangle {
                                        anchors.fill: parent
                                        radius: parent.radius
                                        color: Qt.alpha(home.thm.bad,
                                                        classRow.total ? 0.42 : 0)
                                    }
                                    Rectangle {
                                        width: parent.width
                                             * (classRow.total ? model.wins / classRow.total : 0)
                                        height: parent.height
                                        radius: parent.radius
                                        gradient: Gradient {
                                            orientation: Gradient.Horizontal
                                            GradientStop {
                                                position: 0.0
                                                color: Qt.alpha(home.thm.good, 0.75)
                                            }
                                            GradientStop { position: 1.0; color: home.thm.goodHi }
                                        }
                                    }
                                }
                                Row {
                                    Layout.preferredWidth: 44
                                    Text {
                                        text: model.wins
                                        color: home.thm.good
                                        font.pixelSize: 12
                                        font.bold: true
                                    }
                                    Text {
                                        text: " – "
                                        color: home.thm.textFaint
                                        font.pixelSize: 11
                                    }
                                    Text {
                                        text: model.losses
                                        color: home.thm.bad
                                        font.pixelSize: 12
                                        font.bold: true
                                    }
                                }
                                StatPill {
                                    pct: model.pct
                                    implicitWidth: 48
                                    glowing: classHover.hovered
                                }
                            }
                        }
                    }
                }
            }

            // ---- archétypes de la classe sélectionnée ---------------------
            //
            // Le niveau que les autres trackers n'offrent pas DEPUIS TES parties :
            // ils tirent leurs winrates par archétype de leur propre corpus.
            // Mesuré ici : 39 % face au Démoniste en moyenne, mais 29 % contre un
            // Rafaam et 75 % sans. La moyenne par classe cachait deux matchups
            // opposés.
            SectionTitle {
                visible: tracker.selectedClass !== ""
                label: home.tr("archetypes")
            }
            Panel {
                id: archPanel
                visible: tracker.selectedClass !== ""
                Layout.fillWidth: true
                Layout.bottomMargin: 14
                implicitHeight: Math.max(archCol.implicitHeight, 150) + 20

                // Amener la section sous les yeux au clic, plutôt que de la
                // laisser apparaître hors champ : la fenêtre ne grandit pas,
                // donc sans ça on cliquerait sans rien voir se passer.
                onVisibleChanged: if (visible) scrollTimer.restart()
                Timer {
                    id: scrollTimer
                    interval: 60          // laisse la mise en page se poser
                    onTriggered: {
                        var y = archPanel.mapToItem(column, 0, 0).y
                        var cible = Math.min(y - 8,
                                    Math.max(0, scroller.contentHeight - scroller.height))
                        scrollAnim.to = Math.max(0, cible)
                        scrollAnim.restart()
                    }
                }
                NumberAnimation {
                    id: scrollAnim
                    target: scroller
                    property: "contentY"
                    duration: 260
                    easing.type: Easing.OutCubic
                }
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 16

                    // --- l'anneau ---
                    Canvas {
                        id: beignet
                        Layout.preferredWidth: 132
                        Layout.preferredHeight: 132
                        Layout.alignment: Qt.AlignVCenter
                        readonly property var teintes: [
                            home.thm.gold, home.thm.blue, home.thm.good,
                            home.thm.bad, home.thm.textDim
                        ]
                        Connections {
                            target: tracker
                            function onChanged() { beignet.requestPaint() }
                        }
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.reset()
                            var m = tracker.archetypeModel
                            var n = m.rowCount()
                            if (n === 0) return
                            var cx = width / 2, cy = height / 2
                            var re = Math.min(cx, cy) - 4, ri = re * 0.58
                            var a = -Math.PI / 2
                            for (var i = 0; i < n; i++) {
                                var idx = m.index(i, 0)
                                var part = m.data(idx, Qt.UserRole + 4)   // share
                                var connu = m.data(idx, Qt.UserRole + 6)  // known
                                var slot = m.data(idx, Qt.UserRole + 7)   // teinte stable
                                var da = (part / 100) * Math.PI * 2
                                ctx.beginPath()
                                ctx.arc(cx, cy, re, a, a + da)
                                ctx.arc(cx, cy, ri, a + da, a, true)
                                ctx.closePath()
                                // un deck non reconnu reste gris : ce n'est pas
                                // une catégorie, c'est une absence d'information
                                ctx.fillStyle = (connu && slot >= 0)
                                              ? beignet.teintes[slot % 5]
                                              : home.thm.lineSolid
                                ctx.fill()
                                // 2 px de fond entre les parts, jamais de trait
                                ctx.strokeStyle = home.thm.surface
                                ctx.lineWidth = 2
                                ctx.stroke()
                                a += da
                            }
                        }
                    }

                    // --- la légende, qui porte les chiffres ---
                    ColumnLayout {
                        id: archCol
                        Layout.fillWidth: true
                        spacing: 4
                        Repeater {
                            model: tracker.archetypeModel
                            delegate: RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Rectangle {
                                    width: 10; height: 10; radius: 2
                                    Layout.alignment: Qt.AlignVCenter
                                    color: (model.known && model.slot >= 0)
                                         ? [home.thm.gold, home.thm.blue, home.thm.good,
                                            home.thm.bad, home.thm.textDim][model.slot % 5]
                                         : home.thm.lineSolid
                                }
                                Text {
                                    text: model.label
                                    color: model.known ? home.thm.text : home.thm.textFaint
                                    font.pixelSize: 12
                                    font.italic: !model.known
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Text {
                                    text: model.duration
                                    color: home.thm.textFaint
                                    font.pixelSize: 11
                                }
                                Text {
                                    text: model.wins + "/" + model.games
                                    color: home.thm.textDim
                                    font.pixelSize: 11
                                }
                                Text {
                                    text: model.pct + " %"
                                    color: home.thm.pctColor(model.pct)
                                    font.pixelSize: 12
                                    font.bold: true
                                    horizontalAlignment: Text.AlignRight
                                    Layout.preferredWidth: 38
                                }
                            }
                        }
                        Text {
                            text: home.tr("archetypeHint")
                            color: home.thm.textFaint
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                            Layout.topMargin: 4
                        }

                        // ---- listes de référence -----------------------
                        // Coller un code de deck depuis un site de méta fait
                        // reconnaître les parties où AUCUNE carte-signature
                        // n'est tombée : on compare tout ce qu'on a vu, pas
                        // une carte précise.
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.topMargin: 8
                            implicitHeight: 1
                            color: home.thm.hairline
                        }
                        Text {
                            text: home.tr("refDecks")
                            color: home.thm.textDim
                            font.pixelSize: 11
                            font.bold: true
                            Layout.topMargin: 4
                        }
                        Repeater {
                            model: tracker.deckRefModel
                            delegate: RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Text {
                                    text: model.name
                                    color: home.thm.text
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Text {
                                    // « Démoniste · 2 listes · 41 cartes »
                                    text: model.klass + " · "
                                        + model.variants
                                        + (model.variants > 1 ? " listes" : " liste")
                                        + " · " + model.cards
                                    color: home.thm.textFaint
                                    font.pixelSize: 10
                                }
                                IconButton {
                                    glyph: "✕"
                                    onClicked: tracker.removeDeckRef(model.name)
                                }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.topMargin: 2
                            spacing: 6
                            TextField {
                                id: refName
                                Layout.preferredWidth: 108
                                placeholderText: home.tr("refName")   // utile seulement pour un code nu
                                color: home.thm.text
                                font.pixelSize: 11
                                background: Rectangle {
                                    radius: 5
                                    color: Qt.alpha(home.thm.text, 0.05)
                                    border.width: 1
                                    border.color: Qt.alpha(home.thm.text, 0.14)
                                }
                            }
                            // zone MULTILIGNE : on colle tout un lot de listes
                            // d'un coup, avec leurs en-têtes « ### Nom ».
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 44
                                radius: 5
                                color: Qt.alpha(home.thm.text, 0.05)
                                border.width: 1
                                border.color: Qt.alpha(home.thm.text, 0.14)
                                clip: true
                                Flickable {
                                    anchors.fill: parent
                                    anchors.margins: 4
                                    contentWidth: width
                                    contentHeight: refCode.implicitHeight
                                    TextArea {
                                        id: refCode
                                        width: parent.width
                                        placeholderText: home.tr("refCode")
                                        color: home.thm.text
                                        font.pixelSize: 10
                                        wrapMode: TextArea.WrapAnywhere
                                        background: null
                                    }
                                }
                            }
                            IconButton {
                                glyph: "+"
                                onClicked: {
                                    refErr.text = tracker.addDeckRef(refName.text, refCode.text)
                                    if (refErr.text === "") {
                                        refName.text = ""; refCode.text = ""
                                    }
                                }
                            }
                        }
                        Text {
                            id: refErr
                            visible: text !== ""
                            color: home.thm.badHi
                            font.pixelSize: 10
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                }
            }

            // ---- dernières parties ----------------------------------------
            SectionTitle {
                label: home.tr("recent")
                      + (tracker.selectedDeck !== "" ? " — " + tracker.selectedDeck : "")
            }
            Panel {
                Layout.fillWidth: true
                Layout.bottomMargin: 14
                implicitHeight: recentCol.implicitHeight + 20
                ColumnLayout {
                    id: recentCol
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 3
                    Repeater {
                        model: tracker.recentModel
                        delegate: Rectangle {
                            id: gameRow
                            readonly property color tint: model.won ? home.thm.good
                                                                    : home.thm.bad
                            Layout.fillWidth: true
                            implicitHeight: 30
                            radius: home.thm.rSm
                            color: gameHover.hovered ? Qt.rgba(1, 1, 1, 0.05) : "transparent"
                            clip: true
                            HoverHandler { id: gameHover }

                            // liseré de résultat à gauche : vert ou rouge, il
                            // donne le bilan de la session en la survolant du
                            // regard, sans lire une seule ligne
                            Rectangle {
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                                width: 3
                                height: parent.height - 8
                                radius: 1.5
                                color: gameRow.tint
                                opacity: 0.9
                            }

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 11
                                anchors.rightMargin: 8
                                spacing: 8

                                Text {
                                    text: model.won ? "✓" : "✗"
                                    color: gameRow.tint
                                    font.pixelSize: 12
                                    font.bold: true
                                    Layout.preferredWidth: 12
                                }
                                Text {
                                    text: model.deck
                                    color: home.thm.text
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                ClassAvatar {
                                    classKey: model.vsKey
                                    size: 20
                                    highlighted: gameHover.hovered
                                }
                                Text {
                                    text: model.vsClass
                                    color: home.thm.textDim
                                    font.pixelSize: 11
                                    elide: Text.ElideRight
                                    Layout.preferredWidth: 108
                                }
                                // Concession immédiate : le chrono ne veut rien
                                // dire (« 0:12 »), c'est le fait qui compte.
                                // Hearthstone la journalise explicitement, donc
                                // ce n'est pas une déduction sur la durée.
                                Text {
                                    text: model.quickConcede
                                        ? (model.conceded === "me" ? "concédée" : "concédé")
                                        : (model.duration !== "" ? "⏱ " + model.duration : "")
                                    color: model.quickConcede ? home.thm.gold
                                                              : home.thm.textFaint
                                    font.pixelSize: 10
                                    font.italic: model.quickConcede
                                    horizontalAlignment: Text.AlignRight
                                    Layout.preferredWidth: 58
                                }
                                Text {
                                    text: model.date
                                    color: home.thm.textFaint
                                    font.pixelSize: 10
                                    horizontalAlignment: Text.AlignRight
                                    Layout.preferredWidth: 92
                                }
                                // suppression : n'apparaît qu'au survol de la
                                // ligne, pour ne pas mitrailler la liste de
                                // croix rouges
                                IconButton {
                                    glyph: "✕"
                                    tint: home.thm.bad
                                    implicitWidth: 20
                                    implicitHeight: 18
                                    // opacité seulement, jamais `visible` : le
                                    // retirer de la mise en page ferait sauter
                                    // toute la ligne au passage de la souris
                                    opacity: gameHover.hovered ? 1 : 0
                                    Behavior on opacity { NumberAnimation { duration: 120 } }
                                    onClicked: confirm.askGame(
                                        model.session, model.gameIndex,
                                        model.deck + " vs " + model.vsClass
                                        + " (" + model.date + ")")
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // ---- confirmation des suppressions (irréversibles) --------------------
    Rectangle {
        id: confirm
        objectName: "confirmDialog"   // ciblé par les captures QA
        anchors.fill: parent
        z: 100
        visible: false
        color: Qt.rgba(0, 0, 0, 0.72)

        property string kind: ""       // "deck" | "game"
        property string message: ""
        property string deckName: ""
        property string session: ""
        property int gameIndex: -1

        function askDeck(name, games) {
            kind = "deck"
            deckName = name
            message = "Voulez-vous vraiment supprimer « " + name + " » et ses "
                    + games + (games > 1 ? " parties" : " partie") + " ?"
            visible = true
        }
        function askGame(s, i, label) {
            kind = "game"
            session = s
            gameIndex = i
            message = "Voulez-vous vraiment supprimer cette partie ?\n" + label
            visible = true
        }
        function accept() {
            if (kind === "deck")
                tracker.deleteDeck(deckName)
            else if (kind === "game")
                tracker.deleteGame(session, gameIndex)
            visible = false
        }

        // avale les clics et la touche Échap tant que la boîte est ouverte
        MouseArea { anchors.fill: parent }
        Keys.onEscapePressed: confirm.visible = false
        focus: visible
        onVisibleChanged: if (visible) forceActiveFocus()

        Panel {
            anchors.centerIn: parent
            width: Math.min(parent.width - 48, 380)
            height: boxCol.implicitHeight + 36
            radius: home.thm.rXl
            gradient: Gradient {
                GradientStop { position: 0.0; color: home.thm.surfaceHi }
                GradientStop { position: 1.0; color: home.thm.surface }
            }
            borderTint: Qt.alpha(home.thm.bad, 0.55)
            glowTint: home.thm.bad
            glowIntensity: 0.30

            ColumnLayout {
                id: boxCol
                anchors.fill: parent
                anchors.margins: 16
                spacing: 12

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 9
                    // pastille d'alerte : le pictogramme seul se noyait dans
                    // le texte du titre
                    Rectangle {
                        width: 28; height: 28; radius: 14
                        color: Qt.alpha(home.thm.bad, 0.16)
                        border.width: 1
                        border.color: Qt.alpha(home.thm.bad, 0.5)
                        GlowRing {
                            anchors.fill: parent
                            cornerRadius: 14
                            glowColor: home.thm.bad
                            spread: 5
                            intensity: 0.30
                        }
                        Text {
                            anchors.centerIn: parent
                            text: "⚠"
                            color: home.thm.badHi
                            font.pixelSize: 14
                        }
                    }
                    Text {
                        text: home.tr("warnTitle")
                        color: home.thm.badHi
                        font.pixelSize: 13
                        font.bold: true
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                    }
                }

                Text {
                    text: confirm.message
                    color: home.thm.text
                    font.pixelSize: 12
                    lineHeight: 1.25
                    Layout.fillWidth: true
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 2
                    spacing: 10

                    CtaButton {
                        Layout.fillWidth: true
                        implicitHeight: 34
                        strong: false
                        tint: home.thm.textDim
                        label: home.tr("no")
                        onClicked: confirm.visible = false
                    }
                    CtaButton {
                        Layout.fillWidth: true
                        implicitHeight: 34
                        tint: home.thm.bad
                        label: home.tr("yes")
                        onClicked: confirm.accept()
                    }
                }
            }
        }
    }
}
