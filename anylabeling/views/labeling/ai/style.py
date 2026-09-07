from typing import Dict

from anylabeling.views.labeling.ai.config import BORDER_RADIUS
from anylabeling.views.labeling.utils.theme import get_theme


class SliderStyle:
    """Horizontal QSlider QSS.

    Shared by the auto-labeling panel, the compare view and the navigator
    zoom control. Formerly named ``ChatbotDialogStyle``: it carried 27 other
    chatbot/LLM panel style helpers that had no callers, so they were removed
    and the class was renamed to match what is actually left.
    """

    def get_slider_style(theme: Dict[str, str] = None):
        theme = theme or get_theme()
        return f"""
        QSlider {{
            height: 20px;
        }}

        QSlider::groove:horizontal {{
            border: none;
            height: 4px;
            background: {theme["border"]};
            margin: 0px;
            border-radius: 2px;
        }}

        QSlider::handle:horizontal {{
            background: {theme["primary"]};
            border: none;
            width: 16px;
            height: 16px;
            margin: -6px 0;
            border-radius: {BORDER_RADIUS};
        }}

        QSlider::sub-page:horizontal {{
            background: {theme["primary"]};
            border-radius: 2px;
        }}
        """
