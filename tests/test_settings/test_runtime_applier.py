import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtGui, QtWidgets

    from anylabeling.views.labeling.settings.runtime_applier import (
        SettingsRuntimeApplier,
    )

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required for runtime tests")
class TestSettingsRuntimeApplier(unittest.TestCase):

    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        self.original_font = QtGui.QFont(self.app.font())
        self.app._xanylabeling_default_font = QtGui.QFont(self.original_font)

    def tearDown(self):
        self.app.setFont(self.original_font)
        self.app._xanylabeling_default_font = QtGui.QFont(self.original_font)

    def test_font_family_applies_and_restores_without_restart(self):
        families = QtGui.QFontDatabase.families()
        if not families:
            self.skipTest("No font families are available")
        widget = QtWidgets.QWidget()
        applier = SettingsRuntimeApplier(widget)

        applier.apply_change("font_family", families[0])
        self.app.processEvents()
        self.assertEqual(self.app.font().family(), families[0])
        self.assertEqual(widget.font().family(), families[0])
        self.assertEqual(
            self.app.font().pointSizeF(), self.original_font.pointSizeF()
        )

        applier.apply_change("font_family", None)
        self.app.processEvents()
        self.assertEqual(self.app.font().family(), self.original_font.family())


class _StubCanvas:
    """Just the attributes the canvas-rendering branches write."""

    def __init__(self):
        self.attr_background_color = None
        self.attr_border_color = None
        self.attr_text_color = None
        self.brush_point_distance = 0.0
        self.brush_simplify_epsilon_px = 0.0
        self._brush_max_undo_steps = 0
        self._brush_max_undo_bytes = 0
        self.updates = 0

    def update(self):
        self.updates += 1


class _StubWidget:
    def __init__(self, config):
        self.canvas = _StubCanvas()
        self._config = config


def _canvas_config():
    return {
        "canvas": {
            "attributes": {
                "background_color": [1, 2, 3, 4],
                "border_color": [5, 6, 7, 8],
                "text_color": [9, 10, 11, 12],
            },
            "brush": {
                "point_distance": 12.5,
                "simplify_epsilon": 1.5,
                "max_undo_steps": 7,
                "max_undo_memory_mb": 64,
            },
        }
    }


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required for runtime tests")
class TestCanvasKnobRuntimeApply(unittest.TestCase):
    """Editing the five former rc-only knobs must reach the live canvas."""

    def test_attribute_colors_apply_and_repaint(self):
        widget = _StubWidget(_canvas_config())
        applier = SettingsRuntimeApplier(widget)
        applier.apply_change(
            "canvas.attributes.background_color", [1, 2, 3, 4]
        )
        self.assertEqual(widget.canvas.attr_background_color, [1, 2, 3, 4])
        self.assertEqual(widget.canvas.attr_border_color, [5, 6, 7, 8])
        self.assertEqual(widget.canvas.attr_text_color, [9, 10, 11, 12])
        self.assertEqual(widget.canvas.updates, 1)

    def test_brush_undo_limits_apply(self):
        widget = _StubWidget(_canvas_config())
        applier = SettingsRuntimeApplier(widget)
        applier.apply_change("canvas.brush.max_undo_steps", 7)
        self.assertEqual(widget.canvas._brush_max_undo_steps, 7)
        self.assertEqual(widget.canvas._brush_max_undo_bytes, 64 * 1024 * 1024)
        self.assertEqual(widget.canvas.brush_point_distance, 12.5)


if __name__ == "__main__":
    unittest.main()
