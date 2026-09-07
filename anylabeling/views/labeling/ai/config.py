import os

from anylabeling.config import get_work_directory
from anylabeling.views.labeling.utils.theme import get_theme


def get_models_config_path():
    return os.path.join(
        get_work_directory(), "xanylabeling_data", "ai", "models.json"
    )


def get_providers_config_path():
    return os.path.join(
        get_work_directory(), "xanylabeling_data", "ai", "providers.json"
    )


# Global design system
BORDER_RADIUS = "8px"
FONT_SIZE_TINY = "9px"
FONT_SIZE_SMALL = "11px"
FONT_SIZE_NORMAL = "13px"
FONT_SIZE_LARGE = "16px"
DEFAULT_FIXED_HEIGHT = 32
DEFAULT_COMPONENT_HEIGHT = 32
PANEL_SIZE = 600
ICON_SIZE_NORMAL = (32, 32)
ICON_SIZE_SMALL = (16, 16)
MESSAGE_ACTION_BUTTON_SIZE = (20, 20)

# Theme configuration — derived from the central theme at import time
THEME = get_theme()

# Button color schemes
BUTTON_COLORS = {
    "primary": {
        "background": THEME["primary"],
        "hover": THEME["primary_hover"],
        "pressed": THEME["primary_pressed"],
        "text": "white",
    },
    "secondary": {
        "background": THEME["surface"],
        "hover": THEME["surface_hover"],
        "pressed": THEME["surface_pressed"],
        "text": THEME["text"],
        "border": THEME["border_light"],
    },
    "success": {
        "background": "#10b981",
        "hover": "#059669",
        "pressed": "#047857",
        "text": "white",
    },
    "danger": {
        "background": "#dc2626",
        "hover": "#b91c1c",
        "pressed": "#991b1b",
        "text": "white",
    },
}

# AI Assistant
