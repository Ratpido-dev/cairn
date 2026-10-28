"""Configuration : persistance de la position des widgets flottants.

Depuis l'éclatement du bandeau en widgets indépendants, chacun doit retrouver
sa place d'une partie à l'autre et d'un lancement à l'autre. Sous Wayland c'est
la règle KWin ``cairn-pos-*`` (Remember) qui fait foi ; ce fichier couvre le
repli côté application, utilisé sous X11 et hors KDE.
"""

from src.cairn.config import Config


def test_position_absente_par_defaut():
    assert Config().pos_of("counters") is None


def test_position_retenue_et_relue(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config()
    cfg.set_pos("counters", 1200, 96)
    cfg.set_pos("attack_mine", 800, 720)
    cfg.save(path)

    relu = Config.load(path)
    assert relu.pos_of("counters") == (1200, 96)
    assert relu.pos_of("attack_mine") == (800, 720)
    assert relu.pos_of("secrets") is None


def test_position_negative_ramenee_a_zero():
    """Un écran débranché renvoie des coordonnées négatives : les retenir
    condamnerait le widget hors de l'écran, sans moyen d'aller le rechercher."""
    cfg = Config()
    cfg.set_pos("counters", -40, -12)
    assert cfg.pos_of("counters") == (0, 0)


def test_entree_corrompue_ignoree(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        '{"widget_pos": {"counters": {"x": "abc", "y": 3}, '
        '"secrets": "n\'importe quoi", "attack_opp": {"x": 10, "y": 20}}}',
        encoding="utf-8",
    )
    cfg = Config.load(path)
    # les entrées illisibles disparaissent sans emporter les bonnes
    assert cfg.pos_of("counters") is None
    assert cfg.pos_of("secrets") is None
    assert cfg.pos_of("attack_opp") == (10, 20)


def test_config_illisible_ne_plante_pas(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ pas du json", encoding="utf-8")
    assert Config.load(path).pos_of("counters") is None


def test_choix_xwayland_relu(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config.load(path)
    assert cfg.xwayland is None          # automatique par défaut
    cfg.xwayland = False
    cfg.save(path)
    assert Config.load(path).xwayland is False


def test_xwayland_automatique_sous_gnome_seulement():
    """#11 : sous GNOME Wayland, les overlays ne peuvent ni rester au-dessus du
    jeu ni se placer ; XWayland le permet. Ailleurs, les compositeurs ont leurs
    règles (KWin, Sway, Hyprland, Niri) : on ne touche à rien."""
    from src.cairn.app import wants_xwayland

    gnome = {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0",
             "XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}
    assert wants_xwayland(None, gnome)
    assert not wants_xwayland(False, gnome)                 # choix de l'utilisateur
    assert not wants_xwayland(None, {**gnome, "XDG_CURRENT_DESKTOP": "KDE"})
    assert not wants_xwayland(None, {**gnome, "XDG_CURRENT_DESKTOP": "sway"})
    assert wants_xwayland(True, {**gnome, "XDG_CURRENT_DESKTOP": "sway"})
    assert not wants_xwayland(True, {**gnome, "DISPLAY": ""})          # pas de X
    assert not wants_xwayland(True, {**gnome, "QT_QPA_PLATFORM": "wayland"})
    assert not wants_xwayland(True, {"DISPLAY": ":0"})                 # déjà X11
