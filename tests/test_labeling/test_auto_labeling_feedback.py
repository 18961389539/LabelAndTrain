"""What the canvas says after an auto-labeling run.

The run used to end in silence both ways: zero detections left the canvas
unchanged with only a log line about it, and a hit list never reported
how much came back.
"""

import os
import unittest
from types import SimpleNamespace
from unittest import mock

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
        from jllabeling.views.labeling.shape import Shape

        widget, statuses = self._widget_with_image()
        shape = Shape(label="cat", shape_type="rectangle")
        shape.points = [QtCore.QPointF(0, 0), QtCore.QPointF(10, 10)]
        widget.new_shapes_from_auto_labeling(self._result([shape]))
        self.assertEqual(statuses, ["自动标注完成：1 个目标"])

    def _human_shape(self):
        from jllabeling.views.labeling.shape import Shape

        shape = Shape(label="cat", shape_type="rectangle")
        shape.points = [QtCore.QPointF(0, 0), QtCore.QPointF(10, 10)]
        return shape

    def _new_shape(self):
        from jllabeling.views.labeling.shape import Shape

        shape = Shape(label="dog", shape_type="rectangle")
        shape.points = [QtCore.QPointF(0, 0), QtCore.QPointF(10, 10)]
        return shape

    def test_replacing_human_work_asks_first_and_keeps_it_on_no(self):
        from jllabeling.views.labeling.utils import auto_labeling_result

        widget, statuses = self._widget_with_image()
        human = self._human_shape()
        widget.canvas.shapes = [human]

        with mock.patch.object(
            auto_labeling_result, "ask_replace", return_value=False
        ) as asked:
            widget.new_shapes_from_auto_labeling(
                self._result([self._new_shape()])
            )

        asked.assert_called_once()
        self.assertEqual(widget.canvas.shapes, [human])
        self.assertEqual(statuses, ["已保留原有标注（自动标注结果未应用）"])

    def test_replacing_proceeds_when_the_user_accepts(self):
        from jllabeling.views.labeling.utils import auto_labeling_result

        widget, statuses = self._widget_with_image()
        widget.canvas.shapes = [self._human_shape()]

        with mock.patch.object(
            auto_labeling_result, "ask_replace", return_value=True
        ) as asked:
            widget.new_shapes_from_auto_labeling(
                self._result([self._new_shape()])
            )

        asked.assert_called_once()
        self.assertEqual([s.label for s in widget.canvas.shapes], ["dog"])
        self.assertEqual(statuses, ["自动标注完成：1 个目标"])

    def test_model_boxes_are_replaced_without_a_prompt(self):
        from jllabeling.views.labeling.provenance import SOURCE_MODEL
        from jllabeling.views.labeling.utils import auto_labeling_result

        widget, statuses = self._widget_with_image()
        previous = self._human_shape()
        previous.source = SOURCE_MODEL
        widget.canvas.shapes = [previous]

        with mock.patch.object(
            auto_labeling_result, "ask_replace", return_value=False
        ) as asked:
            widget.new_shapes_from_auto_labeling(
                self._result([self._new_shape()])
            )

        asked.assert_not_called()
        self.assertEqual([s.label for s in widget.canvas.shapes], ["dog"])


if __name__ == "__main__":
    unittest.main()
