"""UI scale config becomes a Qt scale factor before app startup."""

from jllabeling.views.labeling.utils.ui_scale import (
    apply_ui_scale_env,
    scale_percent_to_factor,
)


def test_percent_parsing():
    assert scale_percent_to_factor("100%") == 1.0
    assert scale_percent_to_factor("125%") == 1.25
    assert scale_percent_to_factor(150) == 1.5


def test_invalid_values_fall_back_to_one():
    assert scale_percent_to_factor(None) == 1.0
    assert scale_percent_to_factor("abc") == 1.0
    assert scale_percent_to_factor("0%") == 1.0


def test_environment_is_set_and_cleared():
    env = {}
    assert apply_ui_scale_env("125%", env) == 1.25
    assert env["QT_SCALE_FACTOR"] == "1.25"

    assert apply_ui_scale_env("100%", env) == 1.0
    assert "QT_SCALE_FACTOR" not in env
