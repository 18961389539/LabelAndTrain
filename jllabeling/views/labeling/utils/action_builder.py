"""Action, menu and toolbar assembly for the labeling window.

Split batches 24 and 25: the action definitions moved out of
``label_widget.py`` first (1757 lines), then the four families moved into
``file_actions`` / ``draw_actions`` / ``edit_actions`` / ``view_actions``.
What stays here is the part that cannot be local to one family: the
``widget.actions`` namespace (a single 130-field Struct, the names the
settings runtime and the menus resolve), the grouped tuples built from
those names, and the menu / toolbar assembly that reads them.

The docstring of the old function claimed menus live here because they
consume ~80 action handles; that is still true, but those handles are now
reached through ``widget.actions`` instead of closure variables, which is
what let the four families leave.
"""

import functools

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import QCoreApplication, Qt

from jllabeling.views.labeling import utils

from . import device_menu, help_menu, project_view, smart_tools_menu
from . import draw_actions, edit_actions, file_actions, view_actions

#: Action field -> local variable name used by the four builder modules.
#: Frozen from the single ``utils.Struct(...)`` call the split replaced;
#: the seven grouped fields (``editMenu`` and friends) are rebuilt from
#: these names by ``_grouped_actions``, so a missing key fails loudly at
#: build time instead of leaving a menu short of an entry.
_FIELD_TO_VAR = {
    "data_audit": "data_audit",
    "smart_review": "smart_review",
    "smart_propagate": "smart_propagate",
    "smart_stale_audit": "smart_stale_audit",
    "smart_calibrate": "smart_calibrate",
    "smart_analysis": "smart_analysis",
    "smart_missing_scan": "smart_missing_scan",
    "smart_iteration": "smart_iteration",
    "smart_archive": "smart_archive",
    "smart_advice": "smart_advice",
    "smart_template": "smart_template",
    "smart_restore_backup": "smart_restore_backup",
    "fill_drawing": "fill_drawing",
    "shape_converter": "shape_converter",
    "run_history": "run_history",
    "shortcuts_help": "shortcuts_help",
    "save_crop": "save_crop",
    "ultralytics_train": "ultralytics_train",
    "save_auto": "save_auto",
    "save_with_image_data": "save_with_image_data",
    "change_output_dir": "change_output_dir",
    "save": "save",
    "save_as": "save_as",
    "open": "open_",
    "open_dir": "opendir",
    "open_project": "open_project",
    "close": "close",
    "delete_file": "delete_file",
    "delete_image_file": "delete_image_file",
    "toggle_annotation_checked": "toggle_annotation_checked",
    "mark_checked_and_next": "mark_checked_and_next",
    "mark_rejected_and_next": "mark_rejected_and_next",
    "confirm_classification": "confirm_classification",
    "keep_prev_mode": "keep_prev_mode",
    "auto_use_last_label_mode": "auto_use_last_label_mode",
    "auto_use_last_gid_mode": "auto_use_last_gid_mode",
    "use_system_clipboard": "use_system_clipboard",
    "visibility_shapes_mode": "visibility_shapes_mode",
    "run_all_images": "run_all_images",
    "union_selection": "union_selection",
    "delete": "delete",
    "edit": "edit",
    "duplicate": "duplicate",
    "copy": "copy",
    "copy_coordinates": "copy_coordinates",
    "paste": "paste",
    "toggle_shape_lock": "toggle_shape_lock",
    "overview": "overview",
    "save_visualization_image": "save_visualization_image",
    "undo_last_point": "undo_last_point",
    "undo": "undo",
    "redo": "redo",
    "remove_point": "remove_point",
    "create_mode": "create_mode",
    "create_brush_polygon_mode": "create_brush_polygon_mode",
    "edit_mode": "edit_mode",
    "edit_brush_mode": "edit_brush_mode",
    "create_rectangle_mode": "create_rectangle_mode",
    "create_point_mode": "create_point_mode",
    "create_cuboid_mode": "create_cuboid_mode",
    "create_rotation_mode": "create_rotation_mode",
    "create_quadrilateral_mode": "create_quadrilateral_mode",
    "create_circle_mode": "create_circle_mode",
    "create_line_mode": "create_line_mode",
    "create_linestrip_mode": "create_linestrip_mode",
    "digit_shortcut_0": "digit_shortcut_0",
    "digit_shortcut_1": "digit_shortcut_1",
    "digit_shortcut_2": "digit_shortcut_2",
    "digit_shortcut_3": "digit_shortcut_3",
    "digit_shortcut_4": "digit_shortcut_4",
    "digit_shortcut_5": "digit_shortcut_5",
    "digit_shortcut_6": "digit_shortcut_6",
    "digit_shortcut_7": "digit_shortcut_7",
    "digit_shortcut_8": "digit_shortcut_8",
    "digit_shortcut_9": "digit_shortcut_9",
    "upload_image_flags_file": "upload_image_flags_file",
    "upload_label_flags_file": "upload_label_flags_file",
    "upload_label_classes_file": "upload_label_classes_file",
    "upload_yolo_hbb_annotation": "upload_yolo_hbb_annotation",
    "upload_yolo_seg_annotation": "upload_yolo_seg_annotation",
    "upload_yolo_pose_annotation": "upload_yolo_pose_annotation",
    "upload_yolo_obb_annotation": "upload_yolo_obb_annotation",
    "export_yolo_hbb_annotation": "export_yolo_hbb_annotation",
    "export_yolo_seg_annotation": "export_yolo_seg_annotation",
    "export_yolo_pose_annotation": "export_yolo_pose_annotation",
    "export_yolo_obb_annotation": "export_yolo_obb_annotation",
    "zoom": "zoom",
    "zoom_in": "zoom_in",
    "zoom_out": "zoom_out",
    "zoom_org": "zoom_org",
    "keep_prev_scale": "keep_prev_scale",
    "keep_prev_brightness": "keep_prev_brightness",
    "keep_prev_contrast": "keep_prev_contrast",
    "fit_window": "fit_window",
    "fit_width": "fit_width",
    "brightness_contrast": "brightness_contrast",
    "set_cross_line": "set_cross_line",
    "show_groups": "show_groups",
    "show_masks": "show_masks",
    "show_texts": "show_texts",
    "show_labels": "show_labels",
    "show_attributes": "show_attributes",
    "show_scores": "show_scores",
    "show_degrees": "show_degrees",
    "show_navigator": "show_navigator",
    "zoom_actions": "zoom_actions",
    "open_next_image": "open_next_image",
    "open_prev_image": "open_prev_image",
    "open_next_unchecked_image": "open_next_unchecked_image",
    "open_prev_unchecked_image": "open_prev_unchecked_image",
    "toggle_auto_labeling_widget": "toggle_auto_labeling_widget",
    "digit_shortcut_manager": "digit_shortcut_manager",
    "label_manager": "label_manager",
    "gid_manager": "gid_manager",
    "shape_manager": "shape_manager",
    "loop_thru_labels": "loop_thru_labels",
    "loop_select_labels": "loop_select_labels",
    "select_toggle_shapes": "select_toggle_shapes",
    "select_all": "select_all",
    "hide_selected_polygons": "hide_selected_polygons",
    "show_hidden_polygons": "show_hidden_polygons",
    "group_selected_shapes": "group_selected_shapes",
    "ungroup_selected_shapes": "ungroup_selected_shapes",
}


def _grouped_actions(ns):
    """Rebuild the tuple fields from the flat namespace."""
    return {
        "digit_shortcut_actions": (
            ns["digit_shortcut_0"],
            ns["digit_shortcut_1"],
            ns["digit_shortcut_2"],
            ns["digit_shortcut_3"],
            ns["digit_shortcut_4"],
            ns["digit_shortcut_5"],
            ns["digit_shortcut_6"],
            ns["digit_shortcut_7"],
            ns["digit_shortcut_8"],
            ns["digit_shortcut_9"],
        ),
        "file_menu_actions": (
            ns["open"],
            ns["open_dir"],
            ns["save"],
            ns["save_as"],
            ns["close"],
        ),
        "tool": (),
        "editMenu": (
            ns["edit"],
            ns["select_all"],
            ns["duplicate"],
            ns["delete"],
            ns["copy"],
            ns["paste"],
            None,
            ns["undo"],
            ns["undo_last_point"],
            ns["redo"],
            None,
            ns["copy_coordinates"],
            ns["remove_point"],
            ns["union_selection"],
            None,
            ns["keep_prev_mode"],
            ns["auto_use_last_label_mode"],
            ns["auto_use_last_gid_mode"],
            ns["use_system_clipboard"],
            ns["visibility_shapes_mode"],
        ),
        "menu": (
            ns["create_mode"],
            ns["create_brush_polygon_mode"],
            ns["create_rectangle_mode"],
            ns["create_point_mode"],
            ns["create_rotation_mode"],
            ns["create_quadrilateral_mode"],
            ns["create_circle_mode"],
            ns["create_line_mode"],
            ns["create_linestrip_mode"],
            ns["create_cuboid_mode"],
            None,
            ns["edit_mode"],
            ns["edit_brush_mode"],
            ns["edit"],
            ns["toggle_shape_lock"],
            None,
            ns["copy_coordinates"],
            ns["union_selection"],
            ns["duplicate"],
            ns["copy"],
            ns["paste"],
            None,
            ns["delete"],
            ns["undo"],
            ns["undo_last_point"],
            ns["redo"],
            ns["remove_point"],
        ),
        "on_load_active": (
            ns["close"],
            ns["create_mode"],
            ns["create_brush_polygon_mode"],
            ns["create_rectangle_mode"],
            ns["create_point_mode"],
            ns["create_cuboid_mode"],
            ns["create_rotation_mode"],
            ns["create_quadrilateral_mode"],
            ns["create_circle_mode"],
            ns["create_line_mode"],
            ns["create_linestrip_mode"],
            ns["digit_shortcut_0"],
            ns["digit_shortcut_1"],
            ns["digit_shortcut_2"],
            ns["digit_shortcut_3"],
            ns["digit_shortcut_4"],
            ns["digit_shortcut_5"],
            ns["digit_shortcut_6"],
            ns["digit_shortcut_7"],
            ns["digit_shortcut_8"],
            ns["digit_shortcut_9"],
            ns["edit_mode"],
            ns["brightness_contrast"],
            ns["toggle_annotation_checked"],
            ns["mark_checked_and_next"],
            ns["mark_rejected_and_next"],
            ns["shape_manager"],
            ns["loop_thru_labels"],
            ns["loop_select_labels"],
            ns["select_toggle_shapes"],
        ),
        "on_shapes_present": (ns["save_as"], ns["delete"]),
    }


def build_actions(widget):
    """Create every QAction, then the menus and the tool list."""
    action = functools.partial(utils.new_action, widget)

    created = {}
    created.update(file_actions.build(widget))
    created.update(draw_actions.build(widget))
    created.update(edit_actions.build(widget))
    created.update(view_actions.build(widget))

    namespace = {field: created[var] for field, var in _FIELD_TO_VAR.items()}
    namespace.update(_grouped_actions(namespace))
    widget.actions = utils.Struct(**namespace)
    #: Not an action handle: the theme menu consumes the list of the three
    #: appearance actions as one unit, so the builder hands it back by name.
    theme_mode_actions = created["theme_mode_actions"]

    for index in range(10):
        widget.addAction(getattr(widget.actions, f"digit_shortcut_{index}"))
    widget.addAction(widget.actions.toggle_annotation_checked)
    widget.addAction(widget.actions.mark_checked_and_next)
    widget.addAction(widget.actions.mark_rejected_and_next)
    # The quality/review actions live in a menu, which only owns its shortcuts
    # while the menu bar is in play; adding them to the widget keeps the keys
    # working while the canvas has focus.
    widget.addAction(widget.actions.data_audit)
    widget.addAction(widget.actions.smart_review)
    widget.addAction(widget.actions.smart_propagate)
    widget.addAction(widget.actions.smart_stale_audit)
    widget.addAction(widget.actions.smart_calibrate)
    widget.addAction(widget.actions.smart_analysis)
    widget.addAction(widget.actions.smart_missing_scan)
    widget.addAction(widget.actions.smart_iteration)
    widget.addAction(widget.actions.smart_archive)
    widget.addAction(widget.actions.smart_advice)
    widget.addAction(widget.actions.smart_template)
    widget.addAction(widget.actions.smart_restore_backup)
    widget.addAction(widget.actions.brightness_contrast)
    widget.addAction(widget.actions.fill_drawing)
    widget.addAction(widget.actions.keep_prev_scale)
    widget.addAction(widget.actions.keep_prev_brightness)
    widget.addAction(widget.actions.keep_prev_contrast)
    widget.addAction(widget.actions.select_toggle_shapes)
    widget.addAction(widget.actions.select_all)
    widget.addAction(widget.actions.shape_converter)
    widget.addAction(widget.actions.show_groups)
    widget.addAction(widget.actions.show_scores)
    widget.addAction(widget.actions.show_degrees)

    widget.canvas.vertex_selected.connect(
        widget.actions.remove_point.setEnabled
    )

    widget.menus = utils.Struct(
        file=widget.menu(QCoreApplication.translate("LabelingWidget", "File")),
        edit=widget.menu(QCoreApplication.translate("LabelingWidget", "Edit")),
        view=widget.menu(QCoreApplication.translate("LabelingWidget", "View")),
        theme=widget.menu(
            QCoreApplication.translate("LabelingWidget", "Theme")
        ),
        upload=widget.menu(
            QCoreApplication.translate("LabelingWidget", "Upload")
        ),
        export=widget.menu(
            QCoreApplication.translate("LabelingWidget", "Export")
        ),
        tool=widget.menu(QCoreApplication.translate("LabelingWidget", "Tool")),
        train=widget.menu(
            QCoreApplication.translate("LabelingWidget", "Train")
        ),
        smart_tools=widget.menu(
            QCoreApplication.translate("LabelingWidget", "智能工具")
        ),
        help=widget.menu(QCoreApplication.translate("LabelingWidget", "帮助")),
        recent_files=QtWidgets.QMenu(
            QCoreApplication.translate("LabelingWidget", "Open Recent")
        ),
    )
    widget.menus.recent_files.aboutToShow.connect(widget.update_file_menu)
    widget.canvas_label_filter_menu_0 = None
    widget.canvas_gid_filter_menu_0 = None
    widget.canvas_label_filter_menu_1 = None
    widget.canvas_gid_filter_menu_1 = None

    utils.add_actions(
        widget.menus.file,
        (
            widget.actions.open,
            widget.actions.open_next_image,
            widget.actions.open_prev_image,
            widget.actions.open_next_unchecked_image,
            widget.actions.open_prev_unchecked_image,
            widget.actions.open_dir,
            widget.menus.recent_files,
            widget.actions.save,
            widget.actions.save_as,
            widget.actions.save_auto,
            widget.actions.change_output_dir,
            widget.actions.save_with_image_data,
            widget.actions.close,
            widget.actions.delete_file,
            widget.actions.delete_image_file,
            None,
            widget.actions.mark_checked_and_next,
            widget.actions.mark_rejected_and_next,
            widget.actions.confirm_classification,
            None,
        ),
    )
    smart_tools_menu.populate_smart_tools_menu(
        widget.menus.smart_tools, widget.actions
    )
    device_menu.populate_device_menu(widget)
    help_menu.populate_help_menu(
        widget, widget.menus.help, widget.actions.shortcuts_help
    )
    utils.add_actions(
        widget.menus.train,
        (widget.actions.ultralytics_train, widget.actions.run_history),
    )
    utils.add_actions(
        widget.menus.tool,
        (
            widget.actions.overview,
            None,
            widget.actions.save_crop,
            widget.actions.save_visualization_image,
            None,
            widget.actions.digit_shortcut_manager,
            widget.actions.label_manager,
            widget.actions.gid_manager,
            widget.actions.shape_manager,
            None,
            widget.actions.shape_converter,
        ),
    )
    utils.add_actions(widget.menus.theme, theme_mode_actions)
    utils.add_actions(
        widget.menus.upload,
        (
            widget.actions.upload_image_flags_file,
            widget.actions.upload_label_flags_file,
            widget.actions.upload_label_classes_file,
            None,
            widget.actions.upload_yolo_hbb_annotation,
            widget.actions.upload_yolo_seg_annotation,
            widget.actions.upload_yolo_obb_annotation,
            widget.actions.upload_yolo_pose_annotation,
        ),
    )
    utils.add_actions(
        widget.menus.export,
        (
            widget.actions.export_yolo_hbb_annotation,
            widget.actions.export_yolo_seg_annotation,
            widget.actions.export_yolo_obb_annotation,
            widget.actions.export_yolo_pose_annotation,
        ),
    )
    utils.add_actions(
        widget.menus.view,
        (
            widget.actions.show_navigator,
            widget.actions.fill_drawing,
            widget.actions.loop_thru_labels,
            widget.actions.loop_select_labels,
            None,
            widget.actions.zoom_in,
            widget.actions.zoom_out,
            widget.actions.zoom_org,
            None,
            widget.actions.keep_prev_scale,
            widget.actions.keep_prev_brightness,
            widget.actions.keep_prev_contrast,
            None,
            widget.actions.fit_window,
            widget.actions.fit_width,
            None,
            widget.actions.brightness_contrast,
            widget.actions.set_cross_line,
            None,
            widget.actions.show_masks,
            widget.actions.show_texts,
            widget.actions.show_labels,
            widget.actions.show_attributes,
            widget.actions.show_scores,
            widget.actions.show_degrees,
            widget.actions.show_groups,
            widget.actions.hide_selected_polygons,
            widget.actions.show_hidden_polygons,
            widget.actions.group_selected_shapes,
            widget.actions.ungroup_selected_shapes,
        ),
    )

    widget._view_menu_filter = utils.StayOpenMenuFilter(widget.menus.view)
    widget.menus.view.installEventFilter(widget._view_menu_filter)

    widget.menus.file.aboutToShow.connect(widget.update_file_menu)

    # 「项目」子菜单插在 File 菜单最前面：项目化改造的第一步是让"项目"
    # 出现在用户第一眼看到的位置，项目管理本身（新建/重命名/删除）留
    # 给后续批次，这里只做呈现。
    widget.menus.project = project_view.build_project_menu(widget)

    # Custom context menu for the canvas widget:
    utils.add_actions(widget.canvas.menus[0], widget.actions.menu)
    utils.add_actions(
        widget.canvas.menus[1],
        (
            action("&Copy here", widget.copy_shape),
            action("&Move here", widget.move_shape),
        ),
    )
    (
        widget.canvas_label_filter_menu_0,
        widget.canvas_gid_filter_menu_0,
    ) = widget._append_filter_submenus(
        widget.canvas.menus[0],
        prepend=True,
        after_filter_actions=(widget.actions.toggle_annotation_checked,),
    )
    widget.canvas.menus[0].aboutToShow.connect(widget.refresh_filter_menus)
    widget.canvas.menus[0].aboutToShow.connect(
        widget.refresh_shape_lock_action
    )

    widget.tools = widget.toolbar("Tools")
    # Menu buttons on Left
    widget.actions.tool = (
        widget.actions.open_dir,
        widget.actions.open_prev_image,
        widget.actions.open_next_image,
        widget.actions.save,
        widget.actions.delete_file,
        None,
        widget.actions.create_mode,
        widget.actions.create_rectangle_mode,
        widget.actions.create_point_mode,
        widget.actions.create_brush_polygon_mode,
        None,
        widget.actions.edit_mode,
        widget.actions.edit_brush_mode,
        widget.actions.delete,
        widget.actions.undo,
        widget.actions.redo,
        None,
        widget.actions.loop_thru_labels,
        widget.actions.loop_select_labels,
        widget.actions.select_toggle_shapes,
        None,
        widget.actions.run_all_images,
        widget.actions.toggle_auto_labeling_widget,
        None,
        widget.actions.fit_width,
        widget.actions.zoom,
    )
