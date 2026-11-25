"""Editing, clipboard, managers, navigation and training entry.

Split out of ``action_builder.build_actions`` (the function was 1757
lines); the body is moved verbatim and returns its locals so the
caller can publish them under the historical action names.
"""

import functools

from PyQt6.QtCore import QCoreApplication

from jllabeling.views.labeling import utils


def build(widget):
    """Create the edit actions and return them by name."""
    action = functools.partial(utils.new_action, widget)
    shortcuts = widget._config["shortcuts"]
    delete = action(
        QCoreApplication.translate("LabelingWidget", "Delete"),
        widget.delete_selected_shape,
        shortcuts["delete_polygon"],
        "cancel",
        QCoreApplication.translate(
            "LabelingWidget", "Delete the selected polygons"
        ),
        enabled=False,
    )
    duplicate = action(
        QCoreApplication.translate("LabelingWidget", "Duplicate Polygons"),
        widget.duplicate_selected_shape,
        shortcuts["duplicate_polygon"],
        "copy",
        QCoreApplication.translate(
            "LabelingWidget", "Create a duplicate of the selected polygons"
        ),
        enabled=False,
    )
    copy = action(
        QCoreApplication.translate("LabelingWidget", "Copy Object"),
        widget.copy_selected_shape,
        shortcuts["copy_polygon"],
        "copy",
        QCoreApplication.translate(
            "LabelingWidget", "Copy selected polygons to clipboard"
        ),
        enabled=False,
    )
    paste = action(
        QCoreApplication.translate("LabelingWidget", "Paste Object"),
        widget.paste_selected_shape,
        shortcuts["paste_polygon"],
        "paste",
        QCoreApplication.translate("LabelingWidget", "Paste copied polygons"),
        enabled=widget._config["system_clipboard"],
    )
    select_all = action(
        QCoreApplication.translate("LabelingWidget", "Select All Shapes"),
        widget.select_all_shapes,
        shortcuts["select_all"],
        None,
        QCoreApplication.translate(
            "LabelingWidget", "Select every annotation on this image"
        ),
        enabled=True,
    )
    undo_last_point = action(
        QCoreApplication.translate("LabelingWidget", "Undo last point"),
        widget.canvas.undo_last_point,
        shortcuts["undo_last_point"],
        "undo",
        QCoreApplication.translate("LabelingWidget", "Undo last drawn point"),
        enabled=False,
    )
    remove_point = action(
        text=QCoreApplication.translate(
            "LabelingWidget", "Remove Selected Point"
        ),
        slot=widget.remove_selected_point,
        shortcut=shortcuts["remove_selected_point"],
        icon="edit",
        tip=QCoreApplication.translate(
            "LabelingWidget", "Remove selected point from polygon"
        ),
        enabled=False,
    )

    undo = action(
        QCoreApplication.translate("LabelingWidget", "Undo"),
        widget.undo_shape_edit,
        shortcuts["undo"],
        "undo",
        QCoreApplication.translate(
            "LabelingWidget", "Undo last add and edit of shape"
        ),
        enabled=False,
    )
    redo = action(
        QCoreApplication.translate("LabelingWidget", "Redo"),
        widget.redo_shape_edit,
        shortcuts.get("redo", "Ctrl+Shift+Z"),
        "redo",
        QCoreApplication.translate(
            "LabelingWidget", "Redo the last undone edit of shape"
        ),
        enabled=False,
    )
    hide_selected_polygons = action(
        QCoreApplication.translate("LabelingWidget", "Hide Selected Polygons"),
        widget.hide_selected_polygons,
        shortcuts["hide_selected_polygons"],
        None,
        QCoreApplication.translate("LabelingWidget", "Hide selected polygons"),
        enabled=True,
    )
    show_hidden_polygons = action(
        QCoreApplication.translate("LabelingWidget", "Show Hidden Polygons"),
        widget.show_hidden_polygons,
        shortcuts["show_hidden_polygons"],
        None,
        QCoreApplication.translate("LabelingWidget", "Show hidden polygons"),
        enabled=True,
    )

    overview = action(
        QCoreApplication.translate("LabelingWidget", "Overview"),
        widget.overview,
        shortcuts["show_overview"],
        icon="overview",
        tip=QCoreApplication.translate(
            "LabelingWidget", "Show annotations statistics"
        ),
    )
    save_crop = action(
        QCoreApplication.translate("LabelingWidget", "Save Cropped Image"),
        lambda: utils.save_crop(widget),
        icon="crop",
        tip=QCoreApplication.translate(
            "LabelingWidget",
            "Save cropped image. (Support rectangle/rotation/polygon shape_type)",
        ),
    )
    save_visualization_image = action(
        QCoreApplication.translate(
            "LabelingWidget", "Save Visualization Image"
        ),
        lambda: utils.save_visualization(widget),
        icon="file",
        tip=QCoreApplication.translate(
            "LabelingWidget", "Save visualization image"
        ),
    )
    digit_shortcut_manager = action(
        QCoreApplication.translate("LabelingWidget", "Digit Shortcut Manager"),
        widget.digit_shortcut_manager,
        shortcuts["edit_digit_shortcut"],
        icon="edit",
        tip=QCoreApplication.translate(
            "LabelingWidget",
            "Manage Digit Shortcuts: Assign Drawing Modes and Labels to Number Keys",
        ),
    )
    label_manager = action(
        QCoreApplication.translate("LabelingWidget", "Label Manager"),
        widget.label_manager,
        shortcuts["edit_labels"],
        icon="edit",
        tip=QCoreApplication.translate(
            "LabelingWidget",
            "Manage Labels: Rename, Delete, Hide/Show, Adjust Color",
        ),
    )
    shortcuts_help = action(
        QCoreApplication.translate("LabelingWidget", "快捷键速查"),
        widget.show_shortcuts_help,
        shortcuts["show_shortcuts_help"],
        icon="search",
        tip=QCoreApplication.translate(
            "LabelingWidget", "查看所有可用快捷键，可按快捷键或功能搜索"
        ),
    )
    gid_manager = action(
        QCoreApplication.translate("LabelingWidget", "Group ID Manager"),
        widget.gid_manager,
        shortcuts["edit_group_id"],
        icon="edit",
        tip=QCoreApplication.translate("LabelingWidget", "Manage Group ID"),
    )
    shape_manager = action(
        QCoreApplication.translate("LabelingWidget", "Shape Manager"),
        widget.shape_manager,
        shortcuts["edit_shapes"],
        icon="edit",
        tip=QCoreApplication.translate(
            "LabelingWidget", "Manage Shapes: Add, Delete, Remove"
        ),
        enabled=False,
    )
    copy_coordinates = action(
        QCoreApplication.translate("LabelingWidget", "Copy Coordinates"),
        widget.copy_shape_coordinates,
        icon="copy",
        tip=QCoreApplication.translate(
            "LabelingWidget", "Copy shape coordinates to clipboard"
        ),
        enabled=False,
    )
    union_selection = action(
        QCoreApplication.translate("LabelingWidget", "Union Selection"),
        widget.union_selection,
        shortcuts["union_selected_shapes"],
        icon="union",
        tip=QCoreApplication.translate(
            "LabelingWidget", "Union multiple selected rectangle shapes"
        ),
        enabled=False,
    )
    toggle_shape_lock = action(
        QCoreApplication.translate("LabelingWidget", "Lock Shape"),
        widget.toggle_selected_shapes_lock,
        tip=QCoreApplication.translate(
            "LabelingWidget",
            "Prevent changes to the selected shapes' coordinates",
        ),
        checkable=True,
        enabled=False,
    )
    shape_converter = action(
        QCoreApplication.translate("LabelingWidget", "Shape Converter"),
        lambda: utils.open_shape_converter(widget),
        shortcut=shortcuts["shape_converter"],
        icon="convert",
        tip=QCoreApplication.translate(
            "LabelingWidget", "Open shape converter"
        ),
    )

    loop_thru_labels = action(
        QCoreApplication.translate("LabelingWidget", "Loop Through Labels"),
        widget.loop_thru_labels,
        shortcut=shortcuts["loop_thru_labels"],
        icon="loop",
        tip=QCoreApplication.translate(
            "LabelingWidget", "Loop through labels"
        ),
        enabled=False,
    )
    loop_select_labels = action(
        QCoreApplication.translate("LabelingWidget", "Loop Select Labels"),
        widget.loop_select_labels,
        shortcut=shortcuts["loop_select_labels"],
        icon="circle-selection",
        tip=QCoreApplication.translate("LabelingWidget", "Loop select labels"),
        enabled=False,
    )
    select_toggle_shapes = action(
        QCoreApplication.translate(
            "LabelingWidget", "Toggle Shapes Visibility"
        ),
        widget.toggle_select_all,
        shortcut=shortcuts["select_toggle_shapes"],
        icon="eye",
        tip=QCoreApplication.translate("LabelingWidget", "Hide all shapes"),
        enabled=False,
    )
    widget.select_toggle_action = select_toggle_shapes

    ultralytics_train = action(
        "打开训练面板",
        lambda: widget.start_training("ultralytics"),
        icon="ultralytics",
    )
    run_history = action(
        QCoreApplication.translate("LabelingWidget", "实验历史"),
        widget.show_run_history,
    )
    return locals()
