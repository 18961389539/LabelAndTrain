import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from anylabeling.views.labeling.label_widget import LabelingWidget
    from anylabeling.views.labeling.shape import Shape
    from anylabeling.views.labeling.utils.shortcuts_help import (
        SHORTCUT_GROUPS,
    )

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


CREATE_ACTION_NAMES = (
    "create_mode",
    "create_rectangle_mode",
    "create_point_mode",
    "create_cuboid_mode",
    "create_rotation_mode",
    "create_quadrilateral_mode",
    "create_circle_mode",
    "create_line_mode",
    "create_linestrip_mode",
    "create_brush_polygon_mode",
    "edit_mode",
    "edit_brush_mode",
    "union_selection",
)


def make_widget():
    actions = SimpleNamespace(
        **{name: Mock(name=name) for name in CREATE_ACTION_NAMES}
    )
    actions.digit_shortcut_actions = ()
    canvas = Mock()
    canvas.is_brush_mode = False
    widget = SimpleNamespace(
        actions=actions,
        canvas=canvas,
        auto_labeling_widget=Mock(auto_labeling_mode=None),
        clear_auto_labeling_marks=Mock(),
        hide_attributes_panel=Mock(),
        update_labeling_instruction=Mock(),
    )
    widget._create_mode_actions = lambda: LabelingWidget._create_mode_actions(
        widget
    )
    widget._enable_create_mode_actions = (
        lambda: LabelingWidget._enable_create_mode_actions(widget)
    )
    return widget


@unittest.skipUnless(
    PYQT_AVAILABLE, "PyQt6 is required for draw mode shortcut tests"
)
class TestDrawModeActions(unittest.TestCase):

    def test_mapping_covers_every_supported_shape(self):
        widget = make_widget()
        mapping = LabelingWidget._create_mode_actions(widget)
        self.assertEqual(
            set(mapping),
            set(Shape.get_supported_shape()),
            "a supported shape must be reachable by an action",
        )

    def test_advertised_create_shortcuts_are_all_reachable(self):
        widget = make_widget()
        mapping = LabelingWidget._create_mode_actions(widget)
        advertised = {
            key[len("create_") :]
            for group_title, entries in SHORTCUT_GROUPS
            if group_title == "创建标注"
            for key, _description in entries
        }
        # "brush_polygon" is a modifier on polygon mode, not a create mode.
        self.assertTrue(
            advertised - {"brush_polygon"} <= set(mapping),
            f"advertised but unbound: {sorted(advertised - set(mapping))}",
        )

    def test_each_mode_disables_only_itself(self):
        for mode in sorted(LabelingWidget._create_mode_actions(make_widget())):
            with self.subTest(mode=mode):
                widget = make_widget()
                mapping = LabelingWidget._create_mode_actions(widget)

                LabelingWidget.toggle_draw_mode(
                    widget, edit=False, create_mode=mode
                )

                mapping[mode].setEnabled.assert_called_with(False)
                for other_mode, other in mapping.items():
                    if other_mode != mode:
                        other.setEnabled.assert_called_with(True)
                self.assertEqual(widget.canvas.create_mode, mode)

    def test_unknown_mode_raises(self):
        widget = make_widget()
        with self.assertRaises(ValueError):
            LabelingWidget.toggle_draw_mode(
                widget, edit=False, create_mode="hexagon"
            )

    def test_edit_mode_rearms_every_create_action(self):
        widget = make_widget()
        mapping = LabelingWidget._create_mode_actions(widget)

        LabelingWidget.toggle_draw_mode(widget, edit=True)

        for action in mapping.values():
            action.setEnabled.assert_called_with(True)
        widget.actions.create_brush_polygon_mode.setEnabled.assert_called_with(
            True
        )


if __name__ == "__main__":
    unittest.main()
