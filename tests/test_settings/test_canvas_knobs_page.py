"""The five former rc-only canvas knobs must be usable from the settings page."""

import copy
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets

    from anylabeling.views.labeling.settings.controller import (
        SettingsController,
    )
    from anylabeling.views.labeling.settings.dialog import SettingsDialog
    from anylabeling.views.labeling.settings.editors import ColorRgbaEditor
    from anylabeling.views.labeling.settings.schema import load_template_config

    PYQT_AVAILABLE = True
except Exception:  # pragma: no cover - mirrors sibling settings tests
    PYQT_AVAILABLE = False


KNOBS = {
    "canvas.attributes.background_color": "属性背景色",
    "canvas.attributes.border_color": "属性边框色",
    "canvas.attributes.text_color": "属性文字色",
    "canvas.brush.max_undo_steps": "画笔撤销步数",
    "canvas.brush.max_undo_memory_mb": "画笔撤销内存上限 (MB)",
}


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestCanvasKnobsPage(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        self.applied = []
        config = copy.deepcopy(load_template_config())
        self.controller = SettingsController(
            config=config,
            apply_callback=lambda key, value: self.applied.append(
                (key, copy.deepcopy(value))
            ),
            save_callback=lambda _config: True,
            save_delay_ms=10000,
        )
        self.dialog = SettingsDialog(None, self.controller)
        self.dialog._confirm_discard_unsaved = lambda: True
        self.dialog.show()
        self.dialog._render_primary("Canvas")
        self.app.processEvents()

    def tearDown(self):
        self.controller.flush()
        self.dialog.close()
        self.app.processEvents()

    def _row(self, label):
        for row in self.dialog.content_body.findChildren(QtWidgets.QWidget):
            texts = [
                item.text() for item in row.findChildren(QtWidgets.QLabel)
            ]
            if label in texts:
                return row
        return None

    def test_all_five_are_rendered_with_their_labels(self):
        labels = {
            item.text()
            for item in self.dialog.content_body.findChildren(QtWidgets.QLabel)
        }
        for key, label in KNOBS.items():
            self.assertIn(key, self.dialog._bindings)
            self.assertIn(label, labels)

    def test_all_five_are_findable_by_their_visible_label(self):
        for key, label in KNOBS.items():
            matches = self.dialog._search_matches(label)
            self.assertTrue(
                any(field.key == key for field in matches),
                f"{key} not found by {label!r}",
            )

    def test_editing_brush_step_limit_reaches_the_controller_and_runtime(self):
        row = self._row("画笔撤销步数")
        spinbox = row.findChild(QtWidgets.QSpinBox)
        self.assertIsNotNone(spinbox)

        spinbox.setValue(7)
        self.app.processEvents()

        self.assertEqual(
            self.controller.get_value("canvas.brush.max_undo_steps"), 7
        )
        self.assertIn(("canvas.brush.max_undo_steps", 7), self.applied)

    def test_editing_an_attribute_color_reaches_the_controller_and_runtime(
        self,
    ):
        row = self._row("属性背景色")
        editor = row.findChild(ColorRgbaEditor)
        self.assertIsNotNone(editor)

        editor.findChildren(QtWidgets.QSpinBox)[0].setValue(10)
        self.app.processEvents()

        value = self.controller.get_value("canvas.attributes.background_color")
        self.assertEqual(value[0], 10)
        self.assertIn(
            ("canvas.attributes.background_color", value), self.applied
        )


if __name__ == "__main__":
    unittest.main()
