"""Whole-UI scale factor, applied before QApplication is constructed.

Qt reads ``QT_SCALE_FACTOR`` once at startup, so this setting deliberately
says "restart to apply": scaling the app after widgets exist would have to
multiply every hard-coded QSS pixel by hand.
"""

import os


def scale_percent_to_factor(value) -> float:
    text = str(value or "100%").strip().rstrip("%")
    try:
        percent = float(text)
    except (TypeError, ValueError):
        return 1.0
    if percent <= 0:
        return 1.0
    return percent / 100.0


def apply_ui_scale_env(value, environ=None) -> float:
    """Set QT_SCALE_FACTOR from a ``"125%"`` style config value."""
    env = os.environ if environ is None else environ
    factor = scale_percent_to_factor(value)
    if factor == 1.0:
        env.pop("QT_SCALE_FACTOR", None)
    else:
        env["QT_SCALE_FACTOR"] = f"{factor:g}"
    return factor
