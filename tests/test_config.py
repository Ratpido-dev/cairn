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
