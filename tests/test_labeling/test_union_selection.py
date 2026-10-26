"""Merging the selection must not drop any of it.

The old implementation kept the largest exterior contour of the polygon
mask, so two disjoint polygons became one and the other disappeared with
the originals. These tests pin the refusal (and its reason), the two
supported unions, the mixed-label question, and the action's enabled
state.
"""

import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtCore, QtWidgets

    from anylabeling.views.labeling.label_widget import LabelingWidget
    from anylabeling.views.labeling.shape import Shape
    from anylabeling.views.labeling.widgets.mode_controller import (
        ModeController,
    )

    QT_AVAILABLE = True
except Exception:  # pragma: no cover - exercised on Qt-less runners
    QT_AVAILABLE = False


def _shape(shape_type, points, label="a", locked=False):
    shape = Shape(label=label, shape_type=shape_type)
    shape.points = [QtCore.QPointF(x, y) for x, y in points]
    shape.locked = locked
    if shape_type != "point":
        shape.close()
    return shape


def _polygon(label="a", locked=False):
    return _shape(
        "polygon",
        [(10, 10), (60, 10), (60, 60), (10, 60)],
        label=label,
        locked=locked,
    )


def _rectangle(label="a", locked=False):
    return _shape(
        "rectangle",
        [(10, 10), (60, 10), (60, 60), (10, 60)],
        label=label,
        locked=locked,
    )


def _area(shape):
    points = [(p.x(), p.y()) for p in shape.points]
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def _bounds(shape):
    xs = [p.x() for p in shape.points]
    ys = [p.y() for p in shape.points]
    return min(xs), min(ys), max(xs), max(ys)


@unittest.skipUnless(QT_AVAILABLE, "PyQt6 is required")
class TestUnionSelection(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])

    def _widget(self, shapes):
        added = []
        statuses = []
        canvas = SimpleNamespace(
            shapes=list(shapes),
            selected_shapes=list(shapes),
            load_shapes=Mock(),
        )
        label_list = Mock()
        widget = SimpleNamespace(
            canvas=canvas,
            label_list=label_list,
            status=lambda message, delay=0: statuses.append(message),
            add_label=lambda shape, **kwargs: added.append(shape),
            _refresh_shape_filters=Mock(),
            _refresh_label_panel=Mock(),
            _no_selection_slot=False,
            set_dirty=Mock(),
            no_shape=Mock(return_value=False),
            actions=SimpleNamespace(on_shapes_present=[]),
        )
        return widget, added, statuses

    def test_disjoint_polygons_are_refused_instead_of_dropping_one(self):
        left = _polygon()
        right = _shape("polygon", [(100, 10), (160, 10), (160, 60), (100, 60)])
        widget, added, statuses = self._widget([left, right])

        LabelingWidget.union_selection(widget)

        self.assertEqual(added, [])
        widget.canvas.load_shapes.assert_not_called()
        widget.label_list.remove_item.assert_not_called()
        self.assertEqual(len(statuses), 1)
        self.assertIn("分离", statuses[0])

    def test_union_enclosing_a_hole_is_refused(self):
        # A U plus the bar across its opening: one exterior ring, one hole.
        u_shape = _shape(
            "polygon",
            [
                (0, 0),
                (10, 0),
                (10, 40),
                (90, 40),
                (90, 0),
                (100, 0),
                (100, 50),
                (0, 50),
            ],
        )
        bar = _shape("polygon", [(0, 0), (100, 0), (100, 10), (0, 10)])
        widget, added, statuses = self._widget([u_shape, bar])

        LabelingWidget.union_selection(widget)

        self.assertEqual(added, [])
        widget.canvas.load_shapes.assert_not_called()
        widget.label_list.remove_item.assert_not_called()
        self.assertEqual(len(statuses), 1)
        self.assertIn("孔洞", statuses[0])

    def test_degenerate_polygon_is_refused(self):
        line = _shape("polygon", [(10, 10), (20, 10)])
        widget, added, statuses = self._widget([_polygon(), line])

        LabelingWidget.union_selection(widget)

        self.assertEqual(added, [])
        widget.canvas.load_shapes.assert_not_called()
        widget.label_list.remove_item.assert_not_called()
        self.assertEqual(len(statuses), 1)
        self.assertIn("3 个顶点", statuses[0])

    def test_mixed_rectangle_and_polygon_are_refused(self):
        widget, added, statuses = self._widget([_rectangle(), _polygon()])

        LabelingWidget.union_selection(widget)

        self.assertEqual(added, [])
        widget.canvas.load_shapes.assert_not_called()
        widget.label_list.remove_item.assert_not_called()
        self.assertEqual(len(statuses), 1)
        self.assertIn("矩形", statuses[0])

    def test_other_shape_types_are_refused(self):
        point = _shape("point", [(20, 20)])
        widget, added, statuses = self._widget(
            [_rectangle(), _rectangle(), point]
        )

        LabelingWidget.union_selection(widget)

        self.assertEqual(added, [])
        widget.canvas.load_shapes.assert_not_called()
        widget.label_list.remove_item.assert_not_called()
        self.assertEqual(len(statuses), 1)

    def test_locked_or_single_selections_are_left_alone(self):
        for shapes in (
            [_rectangle(), _rectangle(locked=True)],
            [_rectangle()],
        ):
            widget, added, statuses = self._widget(shapes)
            LabelingWidget.union_selection(widget)
            self.assertEqual(added, [])
            widget.canvas.load_shapes.assert_not_called()
            widget.label_list.remove_item.assert_not_called()
            self.assertEqual(statuses, [])

    def test_rectangles_merge_to_their_common_bounds(self):
        first = _rectangle(label="a")
        second = _shape(
            "rectangle",
            [(40, 40), (100, 40), (100, 100), (40, 100)],
            label="a",
        )
        widget, added, _ = self._widget([first, second])

        LabelingWidget.union_selection(widget)

        self.assertEqual(len(added), 1)
        merged = added[0]
        self.assertEqual(merged.shape_type, "rectangle")
        self.assertEqual(merged.label, "a")
        self.assertEqual(_bounds(merged), (10, 10, 100, 100))
        self.assertEqual(len(merged.points), 4)
        widget.canvas.load_shapes.assert_called_once_with([added[0]])
        self.assertEqual(widget.label_list.remove_item.call_count, 2)

    def test_overlapping_polygons_merge_to_one_covering_polygon(self):
        first = _polygon()
        second = _shape(
            "polygon",
            [(40, 40), (100, 40), (100, 100), (40, 100)],
        )
        widget, added, _ = self._widget([first, second])

        LabelingWidget.union_selection(widget)

        self.assertEqual(len(added), 1)
        merged = added[0]
        self.assertEqual(merged.shape_type, "polygon")
        xmin, ymin, xmax, ymax = _bounds(merged)
        for actual, expected in zip(
            (xmin, ymin, xmax, ymax), (10, 10, 100, 100)
        ):
            self.assertAlmostEqual(actual, expected, delta=1.5)
        self.assertGreater(_area(merged), 5500)
        self.assertLess(_area(merged), 5800)
        widget.canvas.load_shapes.assert_called_once_with([added[0]])
        self.assertEqual(widget.label_list.remove_item.call_count, 2)

    def test_different_labels_are_confirmed_and_keep_the_last_one(self):
        first = _rectangle(label="cat")
        second = _rectangle(label="dog")
        widget, added, _ = self._widget([first, second])

        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.No,
        ):
            LabelingWidget.union_selection(widget)
        self.assertEqual(added, [])
        widget.canvas.load_shapes.assert_not_called()
        widget.label_list.remove_item.assert_not_called()

        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ) as question:
            LabelingWidget.union_selection(widget)
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0].label, "dog")
        prompt = question.call_args.args[2]
        self.assertIn("cat", prompt)
        self.assertIn("dog", prompt)


@unittest.skipUnless(QT_AVAILABLE, "PyQt6 is required")
class TestUnionActionState(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])

    def _widget(self):
        actions = [
            "delete",
            "duplicate",
            "copy",
            "edit",
            "edit_mode",
            "copy_coordinates",
            "edit_brush_mode",
            "union_selection",
            "undo",
            "undo_last_point",
        ]
        return SimpleNamespace(
            canvas=SimpleNamespace(
                is_brush_mode=False,
                _brush_target_shape=None,
                selected_shapes=[],
                _active_group_shapes=Mock(return_value=[]),
            ),
            label_list=Mock(),
            actions=SimpleNamespace(**{name: Mock() for name in actions}),
            _no_selection_slot=False,
            attributes=None,
            refresh_shape_lock_action=Mock(),
            set_text_editing=Mock(),
            hide_attributes_panel=Mock(),
            update_labeling_instruction=Mock(),
        )

    def _state(self, shapes):
        widget = self._widget()
        widget.label_list.find_item_by_shape.return_value = None
        LabelingWidget.shape_selection_changed(widget, shapes)
        return widget.actions.union_selection.setEnabled.call_args.args[0]

    def test_two_rectangles_enable_the_action(self):
        self.assertTrue(self._state([_rectangle(), _rectangle()]))

    def test_two_polygons_enable_the_action(self):
        self.assertTrue(self._state([_polygon(), _polygon()]))

    def test_a_point_in_the_selection_disables_the_action(self):
        self.assertFalse(
            self._state(
                [_rectangle(), _rectangle(), _shape("point", [(1, 1)])]
            )
        )

    def test_mixed_shape_types_disable_the_action(self):
        self.assertFalse(self._state([_rectangle(), _polygon()]))

    def test_a_locked_shape_disables_the_action(self):
        self.assertFalse(self._state([_rectangle(), _rectangle(locked=True)]))

    def test_leaving_draw_mode_recomputes_the_action_from_the_selection(self):
        widget = self._widget()
        widget.canvas.selected_shapes = [_rectangle()]
        ModeController(widget).toggle_drawing_sensitive(False)
        widget.actions.union_selection.setEnabled.assert_called_once_with(
            False
        )

        widget.actions.union_selection.setEnabled.reset_mock()
        widget.canvas.selected_shapes = [_rectangle(), _rectangle()]
        ModeController(widget).toggle_drawing_sensitive(False)
        widget.actions.union_selection.setEnabled.assert_called_once_with(True)


if __name__ == "__main__":
    unittest.main()
