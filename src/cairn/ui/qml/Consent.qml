import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic

// Consentement au partage de parties — posé UNE SEULE FOIS.
//
// Trois règles tenues ici :
//   · rien n'est coché d'avance : refuser est aussi facile qu'accepter, et
//     le refus est le comportement par défaut si la fenêtre est fermée ;
//   · on dit exactement ce qui part, ce qui n'en part pas, et ce qui est
//     retiré des fichiers avant l'envoi ;
//   · la décision est révocable à tout instant depuis le launcher, et c'est
//     écrit ici, pas caché dans une politique de confidentialité.
Window {
    id: consent

    // ne s'ouvre que si la question n'a jamais été posée
    visible: !tracker.consentAsked
    width: 520
    height: Math.min(Screen.height - 80, contenu.implicitHeight + 48)
    x: (Screen.width - width) / 2
    y: (Screen.height - height) / 2
    title: "Cairn — partage de parties"
    color: "transparent"
    flags: Qt.Dialog | Qt.FramelessWindowHint

    readonly property bool en: tracker.language === "en"
    // palette : voir Theme.qml (source unique du design system)
    readonly property Theme thm: Theme {}
    readonly property color bg: thm.bg
    readonly property color bgSoft: thm.raised
    readonly property color line: thm.lineSolid
    readonly property color text: thm.text
    readonly property color muted: thm.textDim
    readonly property color accent: thm.gold
    readonly property color good: thm.good

    function t(fr, enTxt) { return consent.en ? enTxt : fr }

    Rectangle {
        anchors.fill: parent
        radius: 14
        color: consent.bg
        border.color: consent.line
        border.width: 1

        DragHandler { target: null; onActiveChanged: if (active) consent.startSystemMove() }

        ColumnLayout {
            id: contenu
            anchors.fill: parent
            anchors.margins: 24
            spacing: 14

            // ---- en-tête -----------------------------------------------
            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                Rectangle { width: 4; height: 38; radius: 2; color: consent.accent }
                ColumnLayout {
                    spacing: 2
                    Layout.fillWidth: true
                    Text {
                        text: consent.t("Aider à améliorer Cairn ?",
                                        "Help improve Cairn?")
                        color: consent.text
                        font.pixelSize: 19
                        font.bold: true
                    }
                    Text {
                        text: consent.t("Une seule question, posée une seule fois.",
                                        "One question, asked once.")
                        color: consent.muted
                        font.pixelSize: 12
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: consent.line }

            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: consent.text
                font.pixelSize: 13
                lineHeight: 1.35
                text: consent.t(
                    "Cairn peut envoyer les journaux de tes parties à un corpus " +
                    "public, pour corriger le lecteur de journaux et nourrir d'autres " +
                    "projets autour de Hearthstone. C'est facultatif : Cairn " +
                    "fonctionne exactement pareil si tu refuses.",
                    "Cairn can send your game logs to a public corpus, to fix the log " +
                    "parser and feed other Hearthstone projects. This is optional: " +
                    "Cairn works exactly the same if you decline.")
            }

            // ---- ce qui part, ce qui ne part pas ------------------------
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: detail.implicitHeight + 24
                radius: 10
                color: consent.bgSoft
                border.color: consent.line

                ColumnLayout {
                    id: detail
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 8

                    component Ligne: RowLayout {
                        property string glyphe
                        property color teinte
                        property string contenuTexte
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            text: glyphe
                            color: teinte
                            font.pixelSize: 13
                            font.bold: true
                            Layout.alignment: Qt.AlignTop
                        }
                        Text {
                            text: contenuTexte
                            color: consent.text
                            font.pixelSize: 12
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }

                    Ligne {
                        glyphe: "✓"; teinte: consent.good
                        contenuTexte: consent.t(
                            "Le déroulé des parties : cartes jouées, tours, résultat, " +
                            "et le nom de tes decks.",
                            "The course of your games: cards played, turns, result, " +
                            "and your deck names.")
                    }
                    Ligne {
                        glyphe: "✓"; teinte: consent.good
                        contenuTexte: consent.t(
                            "Les identifiants de joueurs — le tien comme celui de " +
                            "l'adversaire — sont remplacés par des jetons anonymes " +
                            "AVANT de quitter ta machine.",
                            "Player identifiers — yours and your opponent's — are " +
                            "replaced by anonymous tokens BEFORE anything leaves " +
                            "your machine.")
                    }
                    Ligne {
                        // le dire ICI et pas dans une politique de
                        // confidentialité : « qui reçoit » est la question
                        // qu'on doit se poser avant de cliquer, pas après
                        glyphe: "↓"; teinte: consent.accent
                        contenuTexte: consent.t(
                            "Le corpus est PUBLIC : ce que tu partages, tout le monde " +
                            "peut le retélécharger — toi le premier. Ce n'est pas une " +
                            "base privée.",
                            "The corpus is PUBLIC: whatever you share, anyone can " +
                            "download back — you first. It is not a private database.")
                    }
                    Ligne {
                        glyphe: "✕"; teinte: consent.muted
                        contenuTexte: consent.t(
                            "Jamais : ton compte Blizzard, ta collection, ton or, " +
                            "ton adresse e-mail, ni quoi que ce soit hors de Hearthstone.",
                            "Never: your Blizzard account, collection, gold, email, " +
                            "or anything outside Hearthstone.")
                    }
                    Ligne {
                        // ↺ et non ⟲ : le second est si fin qu'à 12 px il se
                        // réduit à deux points et passe pour un caractère absent
                        glyphe: "↺"; teinte: consent.accent
                        contenuTexte: consent.t(
                            "Réversible à tout moment depuis le launcher, et ce qui " +
                            "attendait d'être envoyé est alors effacé.",
                            "Reversible at any time from the launcher; anything still " +
                            "queued is deleted.")
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                color: consent.muted
                font.pixelSize: 11
                text: consent.t(
                    "Tu peux voir exactement ce qui est prêt à partir depuis le " +
                    "launcher, avant tout envoi.",
                    "You can inspect exactly what is queued from the launcher, " +
                    "before anything is sent.")
            }

            // ---- les deux boutons, de poids égal ------------------------
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 4
                spacing: 10

                component Bouton: Rectangle {
                    property string libelle
                    property bool primaire: false
                    signal active()
                    Layout.fillWidth: true
                    implicitHeight: 40
                    radius: 8
                    color: primaire
                        ? (souris.containsMouse ? Qt.lighter(consent.accent, 1.12) : consent.accent)
                        : (souris.containsMouse ? consent.line : consent.bgSoft)
                    border.color: primaire ? consent.accent : consent.line
                    Text {
                        anchors.centerIn: parent
                        text: libelle
                        color: primaire ? "#10131a" : consent.text
                        font.pixelSize: 13
                        font.bold: primaire
                    }
                    MouseArea {
                        id: souris
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: active()
                    }
                }

                Bouton {
                    libelle: consent.t("Non merci", "No thanks")
                    onActive: tracker.answerConsent(false)
                }
                Bouton {
                    libelle: consent.t("Oui, j'envoie mes parties", "Yes, share my games")
                    primaire: true
                    onActive: tracker.answerConsent(true)
                }
            }
        }
    }
}
