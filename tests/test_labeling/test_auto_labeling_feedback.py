"""What the canvas says after an auto-labeling run.

The run used to end in silence both ways: zero detections left the canvas
unchanged with only a log line about it, and a hit list never reported
how much came back.
"""

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtCore

    from tests.test_labeling.test_tooltips import _WidgetCase

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestAutoLabelingFeedback(_WidgetCase):
    def _widget_with_image(self):
        widget = self.widget
        widget.filename = os.path.join(self.folder, "b.png")
        widget.image = object()
        widget.image_path = widget.filename
        statuses = []
        widget.status = lambda message, delay=5000: statuses.append(message)
        widget.set_dirty = lambda: None
        return widget, statuses

    def _result(self, shapes, replace=True):
        return SimpleNamespace(shapes=shapes, replace=replace, image_path=None)

    def test_an_empty_run_says_so(self):
        widget, statuses = self._widget_with_image()
        widget.new_shapes_from_auto_labeling(self._result([]))
        self.assertEqual(statuses, ["本图未检测到目标"])

    def test_an_empty_run_that_keeps_annotations_says_that(self):
        widget, statuses = self._widget_with_image()
        widget.canvas.shapes = [SimpleNamespace(locked=False)]
        widget.new_shapes_from_auto_labeling(self._result([]))
        self.assertEqual(statuses, ["本图未检测到目标，已保留原有标注"])

    def test_a_result_reports_how_many(self):
        from anylabeling.views.labeling.shape import Shape

        widget, statuses = self._widget_with_image()
        shape = Shape(label="cat", shape_type="rectangle")
        shape.points = [QtCore.QPointF(0, 0), QtCore.QPointF(10, 10)]
        widget.new_shapes_from_auto_labeling(self._result([shape]))
        self.assertEqual(statuses, ["自动标注完成：1 个目标"])


if __name__ == "__main__":
    unittest.main()
