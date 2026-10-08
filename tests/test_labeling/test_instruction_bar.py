"""The canvas hint bar: styled keycaps, and text that tracks the real state.

Two bugs are pinned here, both visible in the bar right under the menu:

* ``_format_instruction_shortcut`` emitted ``<b>`` markup, which
  ``keycap_html`` escaped (by contract it takes plain keys) — so the tags were
  rendered as literal ``<b>Ctrl</b>+<b>U</b>`` text and the bar's whole styling
  intent was lost.
* Nothing refreshed the bar when a file was loaded (or when the state was
  cleared): it was rendered once at construction, so it kept saying
  "尚未打开图片" while an image was open, and only "fixed itself" on an
  unrelated trigger such as a canvas scroll-range change.
"""

import os
import re
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from anylabeling.views.labeling.label_widget import (
    LabelingWidget,
)  # noqa: E402
from anylabeling.views.labeling.utils.style import keycap_html  # noqa: E402

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)


class _Applier:
    """Shortcut-value stand-in: value -> display text (identity by default)."""

    def __init__(self, mapping=None):
        self._mapping = mapping or {}

    def shortcut_value_to_text(self, value):
        if value is None:
            return ""
        return self._mapping.get(value, value)


def _instruction_stub(filename=None, drawing=False, brush=False):
    """Only what ``get_labeling_instruction`` actually reads."""
    stub = SimpleNamespace(
        filename=filename,
        _config={
            "shortcuts": {
                "open_prev": "A",
                "open_next": "D",
                "create_rectangle": "R",
                "save": "Ctrl+S",
                "open_dir": "Ctrl+U",
            }
        },
        _settings_runtime_applier=_Applier(
            {
                "A": "A",
                "D": "D",
                "R": "R",
                "Ctrl+S": "Ctrl+S",
                "Ctrl+U": "Ctrl+U",
            }
        ),
        tr=lambda text: text,
        canvas=SimpleNamespace(
            is_brush_mode=brush,
            drawing=lambda: drawing,
            create_mode="rectangle",
            current=None,
        ),
    )
    stub._format_instruction_shortcut = (
        LabelingWidget._format_instruction_shortcut.__get__(stub)
    )
    return stub


def _instruction_text(**kwargs):
    return LabelingWidget.get_labeling_instruction(_instruction_stub(**kwargs))


class TestKeycapRendering(unittest.TestCase):
    def test_shortcut_text_is_plain_so_keycap_can_style_it(self):
        stub = _instruction_stub()

        self.assertEqual(
            stub._format_instruction_shortcut("Ctrl+Shift+K"), "Ctrl+Shift+K"
        )
        self.assertEqual(stub._format_instruction_shortcut("A"), "A")

    def test_an_unbound_shortcut_is_a_dash_not_markup(self):
        stub = _instruction_stub()

        self.assertEqual(stub._format_instruction_shortcut(None), "-")
        self.assertEqual(stub._format_instruction_shortcut(""), "-")

    def test_the_bar_has_no_literal_markup(self):
        for kwargs in (
            {"filename": "a.jpg"},
            {},
            {"drawing": True},
            {"brush": True},
        ):
            text = _instruction_text(**kwargs)
            with self.subTest(kwargs=kwargs):
                self.assertNotIn("<b>", text)
                self.assertNotIn("</b>", text)
                self.assertNotIn("&lt;", text, "escaped tags would render too")

    def test_the_bar_styles_its_shortcuts(self):
        text = _instruction_text(filename="a.jpg")

        self.assertIn("<span style=", text, "keycaps are rich text")
        self.assertIn("A", text)
        self.assertIn("R", text)

    def test_keycap_html_escapes_what_the_shortcut_helper_returns(self):
        # The contract between the two helpers: plain in, escaped styled out.
        rendered = keycap_html("Ctrl+U")

        self.assertIn("<span style=", rendered)
        self.assertIn("Ctrl+U", rendered)
        self.assertNotIn("&lt;", rendered)


class TestInstructionFollowsState(unittest.TestCase):
    def test_no_image_asks_for_one(self):
        text = _instruction_text()

        self.assertIn("尚未打开图片", text)
        self.assertIn("打开文件夹", text)

    def test_an_open_image_switches_to_the_editing_hints(self):
        text = _instruction_text(filename="t1.png")

        self.assertNotIn("尚未打开图片", text)
        self.assertIn("切图", text)
        self.assertIn("画框", text)

    def test_drawing_and_brush_modes_have_their_own_hint(self):
        self.assertIn(
            "画笔编辑", _instruction_text(filename="a.jpg", brush=True)
        )
        self.assertIn(
            "矩形", _instruction_text(filename="a.jpg", drawing=True)
        )


class TestTheBarIsRefreshed(unittest.TestCase):
    """Source-level wiring guards: the missing refresh was the bug."""

    @staticmethod
    def _function_body(path, name):
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        start = text.index(f"def {name}(")
        following = re.search(r"\ndef ", text[start + 1 :])
        end = start + 1 + following.start() if following else len(text)
        return text[start:end]

    def test_loading_a_file_refreshes_the_bar(self):
        path = os.path.join(
            REPO_ROOT,
            "anylabeling",
            "views",
            "labeling",
            "utils",
            "file_lifecycle.py",
        )

        body = self._function_body(path, "load_file")

        self.assertIn("widget.update_labeling_instruction()", body)

    def test_clearing_the_state_refreshes_the_bar(self):
        path = os.path.join(
            REPO_ROOT,
            "anylabeling",
            "views",
            "labeling",
            "label_widget.py",
        )

        body = self._function_body(path, "reset_state")

        self.assertIn("self.update_labeling_instruction()", body)


if __name__ == "__main__":
    unittest.main()
