"""Shape creation modes (rectangle, polygon, brush, cuboid, ...).

Split out of ``action_builder.build_actions`` (the function was 1757
lines); the body is moved verbatim and returns its locals so the
caller can publish them under the historical action names.
"""

import functools

from PyQt6.QtCore import QCoreApplication

from jllabeling.views.labeling import utils


def build(widget):
    """Create the draw actions and return them by name."""
    action = functools.partial(utils.new_action, widget)
    shortcuts = widget._config["shortcuts"]
    # These six existed only as config keys: the shortcuts-help dialog
    # advertised them, but no QAction ever bound them, so the shapes were
    # reachable through the digit-shortcut manager alone.
    create_cuboid_mode = action(
        QCoreApplication.translate("LabelingWidget", "创建立方体"),
        lambda: widget.toggle_draw_mode(False, create_mode="cuboid"),
        shortcuts["create_cuboid"],
        None,
        QCoreApplication.translate("LabelingWidget", "开始画立方体"),
        enabled=False,
    )
    create_rotation_mode = action(
        QCoreApplication.translate("LabelingWidget", "创建旋转框"),
        lambda: widget.toggle_draw_mode(False, create_mode="rotation"),
        shortcuts["create_rotation"],
        None,
        QCoreApplication.translate("LabelingWidget", "开始画旋转框"),
        enabled=False,
    )
    create_quadrilateral_mode = action(
        QCoreApplication.translate("LabelingWidget", "创建四边形"),
        lambda: widget.toggle_draw_mode(False, create_mode="quadrilateral"),
        shortcuts["create_quadrilateral"],
        None,
        QCoreApplication.translate("LabelingWidget", "开始画四边形"),
        enabled=False,
    )
    create_circle_mode = action(
        QCoreApplication.translate("LabelingWidget", "创建圆"),
        lambda: widget.toggle_draw_mode(False, create_mode="circle"),
        shortcuts["create_circle"],
        None,
        QCoreApplication.translate("LabelingWidget", "开始画圆"),
        enabled=False,
    )
    create_line_mode = action(
        QCoreApplication.translate("LabelingWidget", "创建线段"),
        lambda: widget.toggle_draw_mode(False, create_mode="line"),
        shortcuts["create_line"],
        None,
        QCoreApplication.translate("LabelingWidget", "开始画线段"),
        enabled=False,
    )
    create_linestrip_mode = action(
        QCoreApplication.translate("LabelingWidget", "创建折线"),
        lambda: widget.toggle_draw_mode(False, create_mode="linestrip"),
        shortcuts["create_linestrip"],
        None,
        QCoreApplication.translate("LabelingWidget", "开始画折线"),
        enabled=False,
    )
    digit_shortcut_0 = action(
        QCoreApplication.translate("LabelingWidget", "Digit Shortcut 0"),
        lambda: widget.create_digit_mode(0),
        "0",
        "digit0",
        enabled=False,
    )
    digit_shortcut_1 = action(
        QCoreApplication.translate("LabelingWidget", "Digit Shortcut 1"),
        lambda: widget.create_digit_mode(1),
        "1",
        "digit1",
        enabled=False,
    )
    digit_shortcut_2 = action(
        QCoreApplication.translate("LabelingWidget", "Digit Shortcut 2"),
        lambda: widget.create_digit_mode(2),
        "2",
        "digit2",
        enabled=False,
    )
    digit_shortcut_3 = action(
        QCoreApplication.translate("LabelingWidget", "Digit Shortcut 3"),
        lambda: widget.create_digit_mode(3),
        "3",
        "digit3",
        enabled=False,
    )
    digit_shortcut_4 = action(
        QCoreApplication.translate("LabelingWidget", "Digit Shortcut 4"),
        lambda: widget.create_digit_mode(4),
        "4",
        "digit4",
        enabled=False,
    )
    digit_shortcut_5 = action(
        QCoreApplication.translate("LabelingWidget", "Digit Shortcut 5"),
        lambda: widget.create_digit_mode(5),
        "5",
        "digit5",
        enabled=False,
    )
    digit_shortcut_6 = action(
        QCoreApplication.translate("LabelingWidget", "Digit Shortcut 6"),
        lambda: widget.create_digit_mode(6),
        "6",
        "digit6",
        enabled=False,
    )
    digit_shortcut_7 = action(
        QCoreApplication.translate("LabelingWidget", "Digit Shortcut 7"),
        lambda: widget.create_digit_mode(7),
        "7",
        "digit7",
        enabled=False,
    )
    digit_shortcut_8 = action(
        QCoreApplication.translate("LabelingWidget", "Digit Shortcut 8"),
        lambda: widget.create_digit_mode(8),
        "8",
        "digit8",
        enabled=False,
    )
    digit_shortcut_9 = action(
        QCoreApplication.translate("LabelingWidget", "Digit Shortcut 9"),
        lambda: widget.create_digit_mode(9),
        "9",
        "digit9",
        enabled=False,
    )
    edit_mode = action(
        QCoreApplication.translate("LabelingWidget", "Edit Object"),
        widget.set_edit_mode,
        shortcuts["edit_polygon"],
        "edit",
        QCoreApplication.translate(
            "LabelingWidget", "Move and edit the selected polygons"
        ),
        enabled=False,
    )
    edit_brush_mode = action(
        QCoreApplication.translate("LabelingWidget", "Edit Brush"),
        lambda checked: widget.toggle_brush_mode(checked),
        shortcuts.get("edit_brush_mode", "Shift+B"),
        "brush",
        QCoreApplication.translate(
            "LabelingWidget",
            "Select one polygon, then paint to add, hold Ctrl to erase, "
            "and scroll to resize the brush",
        ),
        enabled=False,
        checkable=True,
        checked=False,
    )
    group_selected_shapes = action(
        QCoreApplication.translate("LabelingWidget", "Group Selected Shapes"),
        widget.group_selected_shapes,
        shortcuts["group_selected_shapes"],
        None,
        QCoreApplication.translate(
            "LabelingWidget", "Group shapes by assigning a same group_id"
        ),
        enabled=True,
    )
    ungroup_selected_shapes = action(
        QCoreApplication.translate(
            "LabelingWidget", "Ungroup Selected Shapes"
        ),
        widget.ungroup_selected_shapes,
        shortcuts["ungroup_selected_shapes"],
        None,
        QCoreApplication.translate("LabelingWidget", "Ungroup shapes"),
        enabled=True,
    )
    return locals()
