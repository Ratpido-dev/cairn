#!/usr/bin/env bash
# Installation de Cairn — indépendante de la distribution.
#
#   ./install.sh              installe (ou met à jour) pour l'utilisateur courant
#   ./install.sh --desktop    idem, en posant aussi une icône sur le bureau
#   ./install.sh --uninstall  retire proprement le raccourci et le programme
#
# Rien n'est écrit hors du dossier personnel, aucun sudo n'est demandé : tout va
# dans ~/.local (norme XDG, respectée par tous les bureaux Linux).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}"
VENV="$PREFIX/cairn/venv"
BIN="$HOME/.local/bin"
APPS="$PREFIX/applications"
ICONS="$PREFIX/icons/hicolor/scalable/apps"

say()  { printf '\033[1m›\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

# ---- désinstallation --------------------------------------------------------
if [[ "${1:-}" == "--uninstall" ]]; then
    rm -rf "$PREFIX/cairn/venv" "$APPS/cairn.desktop" "$ICONS/cairn.svg"
    # cache d'illustrations : purement reconstructible, il part avec le reste
    rm -rf "${XDG_CACHE_HOME:-$HOME/.cache}/cairn"
    rm -f "$BIN/cairn" "$BIN/cairn-doctor" "$BIN/cairn-cards"
    command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
    say "Cairn retiré. Tes parties et réglages sont conservés :"
    echo "    $PREFIX/cairn/history.sqlite   et   ${XDG_CONFIG_HOME:-$HOME/.config}/cairn/"
    exit 0
fi

# ---- prérequis --------------------------------------------------------------
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)'; then
            PY="$candidate"; break
        fi
    fi
done
[[ -n "$PY" ]] || die "Python 3.10 ou plus récent est requis (installe le paquet python3 de ta distribution)."
say "Python : $($PY --version) — $(command -v "$PY")"

if ! "$PY" -c 'import venv' 2>/dev/null; then
    die "Le module venv manque. Installe-le : python3-venv (Debian/Ubuntu), python3-virtualenv (Fedora), python (Arch)."
fi

# ---- environnement isolé ----------------------------------------------------
say "Installation dans $VENV"
mkdir -p "$(dirname "$VENV")" "$BIN" "$APPS" "$ICONS"
[[ -d "$VENV" ]] || "$PY" -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
say "Récupération des dépendances (Qt/PySide6, ~100 Mo la première fois)…"
"$VENV/bin/python" -m pip install --quiet "$ROOT"

# ---- commandes accessibles au PATH -----------------------------------------
for cmd in cairn cairn-doctor cairn-cards; do
    ln -sf "$VENV/bin/$cmd" "$BIN/$cmd"
done
case ":$PATH:" in
    *":$BIN:"*) ;;
    *) warn "$BIN n'est pas dans ton PATH — ajoute ceci à ton ~/.bashrc ou ~/.zshrc :"
       echo "        export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

# ---- raccourci de bureau ----------------------------------------------------
install -m644 "$ROOT/packaging/cairn.svg" "$ICONS/cairn.svg"
# Un thème d'icônes utilisateur sans index.theme n'est pas reconnu : sans ce
# fichier, « Icon=cairn » ne résout rien et le raccourci reste une page blanche.
if [[ ! -f "$PREFIX/icons/hicolor/index.theme" ]]; then
    cat > "$PREFIX/icons/hicolor/index.theme" <<'THEME'
[Icon Theme]
Name=Hicolor
Comment=Fallback icon theme
Directories=scalable/apps

[scalable/apps]
Size=48
Type=Scalable
MinSize=8
MaxSize=512
Context=Applications
THEME
fi
# … et par sécurité on pointe AUSSI l'icône par chemin absolu : ça marche même
# si le cache du bureau n'est pas rafraîchi ou si le thème est ignoré.
sed -e "s|^Exec=cairn$|Exec=$VENV/bin/cairn|" \
    -e "s|^Icon=cairn$|Icon=$ICONS/cairn.svg|" \
    "$ROOT/packaging/cairn.desktop" > "$APPS/cairn.desktop"
chmod 644 "$APPS/cairn.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -qtf "$PREFIX/icons/hicolor" 2>/dev/null || true
command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
say "Raccourci installé : Cairn apparaît dans ton menu d'applications."

# Icône sur le bureau, à la demande (--desktop) : KDE et GNOME exigent que le
# fichier soit exécutable pour l'accepter comme lanceur.
if [[ "${1:-}" == "--desktop" ]]; then
    DESK="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
    if [[ -d "$DESK" ]]; then
        install -m755 "$APPS/cairn.desktop" "$DESK/cairn.desktop"
        say "Raccourci posé sur le bureau : $DESK"
    fi
fi

# ---- base de cartes ---------------------------------------------------------
say "Base de cartes…"
"$VENV/bin/cairn-cards" all >/dev/null || warn "Téléchargement échoué — relance « cairn-cards all » plus tard."

# ---- configuration du jeu ---------------------------------------------------
say "Configuration de Hearthstone…"
"$VENV/bin/cairn-doctor" --fix || warn "Configuration incomplète — relance « cairn-doctor » après avoir lancé Hearthstone une fois."

# ---- fenêtres au-dessus du jeu (KDE seulement) ------------------------------
if [[ "${XDG_CURRENT_DESKTOP:-}" == *KDE* ]] && command -v kwriteconfig6 >/dev/null 2>&1; then
    bash "$ROOT/tools/install_kwin_rule.sh" >/dev/null && \
        say "Règles KWin posées : les panneaux restent au-dessus du jeu, même en plein écran."
    # copie conservée : « Replacer les widgets » (launcher) la rejoue avec
    # --reset-pos, et une installation ne garde pas l'arborescence du dépôt
    install -Dm755 "$ROOT/tools/install_kwin_rule.sh" "$PREFIX/cairn/install_kwin_rule.sh"

    # Script KWin : ouvre les overlays sur le bureau virtuel de Hearthstone.
    # Une règle KWin ne sait pas dire « le même bureau qu'une autre fenêtre »,
    # d'où un script. Sans lui, une partie qui démarre pendant qu'on est sur un
    # autre bureau fait apparaître les fenêtres sous les yeux, au mauvais
    # endroit, et il faut les traîner à la main.
    KS="$HOME/.local/share/kwin/scripts/cairn-follow"
    if [ -d "$ROOT/tools/kwin-script" ]; then
        mkdir -p "$KS" && cp -r "$ROOT/tools/kwin-script/." "$KS"/
        kwriteconfig6 --file kwinrc --group Plugins --key cairn-followEnabled true
        qdbus6 org.kde.KWin /KWin org.kde.KWin.reconfigure >/dev/null 2>&1 \
            || gdbus call --session --dest org.kde.KWin --object-path /KWin \
                 --method org.kde.KWin.reconfigure >/dev/null 2>&1 || true
        say "Overlays épinglés au bureau de Hearthstone."
    fi
else
    warn "Bureau non-KDE (${XDG_CURRENT_DESKTOP:-inconnu}) : configure toi-même « toujours au-dessus »"
    warn "pour les fenêtres dont le titre commence par « Cairn · » (cf. README)."
fi

echo
say "Terminé. Lance Cairn depuis ton menu d'applications, ou tape « cairn »."
