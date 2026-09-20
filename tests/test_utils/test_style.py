import unittest

from anylabeling.views.labeling.utils.style import (
    get_instruction_bar_style,
    keycap_html,
)
from anylabeling.views.labeling.utils.theme import get_theme, init_theme


class TestInstructionBarStyle(unittest.TestCase):

    def test_style_targets_instruction_bar_only(self):
        init_theme("light")
        qss = get_instruction_bar_style()
        self.assertIn("QLabel#LabelInstructionBar", qss)
        self.assertIn("border-radius", qss)

    def test_style_follows_active_theme(self):
        init_theme("light")
        light_qss = get_instruction_bar_style()
        light_surface = get_theme()["surface"]
        init_theme("dark")
        dark_qss = get_instruction_bar_style()
        dark_surface = get_theme()["surface"]

        self.assertIn(light_surface, light_qss)
        self.assertIn(dark_surface, dark_qss)
        self.assertNotEqual(light_qss, dark_qss)
        self.assertNotEqual(light_surface, dark_surface)


class TestKeycapHtml(unittest.TestCase):

    def test_wraps_shortcut_in_highlighted_span(self):
        init_theme("light")
        rendered = keycap_html("Ctrl+S")
        t = get_theme()
        self.assertTrue(
            rendered.startswith(
                f'<span style="color:{t["highlight_text"]};font-weight:600;">'
            ),
            rendered,
        )
        self.assertIn("Ctrl+S", rendered)
        self.assertTrue(rendered.endswith("</span>"))

    def test_escapes_html_characters(self):
        self.assertIn("&lt;b&gt;", keycap_html("<b>"))
        self.assertNotIn("<b>", keycap_html("<b>"))

    def test_empty_value_is_safe(self):
        self.assertIn("</span>", keycap_html(""))

    def test_non_string_value_is_coerced(self):
        self.assertIn("12", keycap_html(12))


if __name__ == "__main__":
    unittest.main()