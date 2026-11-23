"""Action, menu and toolbar assembly for the labeling window.

Moved out of ``label_widget.py`` (split batch 24): the function had grown to
1757 lines and was the largest single block left in the widget.  It only
builds QActions and menus from ``widget`` and stores the result on
``widget.actions`` / ``widget.menus`` / ``widget.tools``, so the whole block
moves without changing a call site inside it.  The layout half stays in
``label_widget._build_layout``.
"""

import functools

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import QCoreApplication, Qt

from jllabeling.views.labeling import utils

from . import device_menu, help_menu, project_view, smart_tools_menu
from .data_audit import run_data_audit
from .label_editing import LABEL_OPACITY
from .smart_analysis import run_smart_analysis, run_threshold_calibration
from .smart_archive import run_duplicate_archive
from .smart_backup import run_backup_restore
from .smart_missing import run_missing_scan
from .smart_prelabel import run_template_propagation
from .smart_review import (
    run_review_jump,
    run_training_advice,
    show_iteration_dashboard,
)
from .smart_stale import run_stale_model_audit


def build_actions(widget):
    """Create every QAction, then the menus and the tool list.

    Moved out of LabelingWidget.__init__ (split batch 4): pure assembly,
    everything is reached through the widget argument. The menus live here
    rather than in their own function on purpose - they consume ~80 of the
    action handles created above, so splitting them would mean threading a
    namespace through the two halves for little gain. The layout half was
    carved off instead, see ``_build_layout``.
    """
    # Actions
    action = functools.partial(utils.new_action, widget)
    shortcuts = widget._config["shortcuts"]

    open_ = action(
        QCoreApplication.translate("LabelingWidget", "Open File"),
        widget.open_file,
        shortcuts["open"],
        "file",
        QCoreApplication.translate(
            "LabelingWidget", "Open image or label file"
        ),
    )
    opendir = action(
        QCoreApplication.translate("LabelingWidget", "Open Dir"),
        widget.open_folder_dialog,
        shortcuts["open_dir"],
        "open",
        QCoreApplication.translate("LabelingWidget", "Open Dir"),
    )
    open_project = action(
        QCoreApplication.translate("LabelingWidget", "Switch Project"),
        widget.open_project_switcher,
        shortcuts["open_project"],
        "open",
        QCoreApplication.translate(
            "LabelingWidget", "Switch between recently opened projects"
        ),
    )
    open_next_image = action(
        QCoreApplication.translate("LabelingWidget", "Next Image"),
        widget.open_next_image,
        shortcuts["open_next"],
        "next",
        QCoreApplication.translate("LabelingWidget", "Open next image"),
        enabled=False,
    )
    open_prev_image = action(
        QCoreApplication.translate("LabelingWidget", "Prev Image"),
        widget.open_prev_image,
        shortcuts["open_prev"],
        "prev",
        QCoreApplication.translate("LabelingWidget", "Open prev image"),
        enabled=False,
    )
    open_next_unchecked_image = action(
        QCoreApplication.translate("LabelingWidget", "Next Unchecked Image"),
        widget.open_next_unchecked_image,
        shortcuts["open_next_unchecked"],
        "next",
        QCoreApplication.translate(
            "LabelingWidget", "Open next unchecked image"
        ),
        enabled=False,
    )
    open_prev_unchecked_image = action(
        QCoreApplication.translate("LabelingWidget", "Prev Unchecked Image"),
        widget.open_prev_unchecked_image,
        shortcuts["open_prev_unchecked"],
        "prev",
        QCoreApplication.translate(
            "LabelingWidget", "Open previous unchecked image"
        ),
        enabled=False,
    )
    save = action(
        QCoreApplication.translate("LabelingWidget", "Save"),
        widget.save_file,
        shortcuts["save"],
        "save",
        QCoreApplication.translate("LabelingWidget", "Save labels to file"),
        enabled=False,
    )
    save_as = action(
        QCoreApplication.translate("LabelingWidget", "Save As"),
        widget.save_file_as,
        shortcuts["save_as"],
        "save-as",
        QCoreApplication.translate(
            "LabelingWidget", "Save labels to a different file"
        ),
        enabled=False,
    )
    run_all_images = action(
        QCoreApplication.translate("LabelingWidget", "Auto Run"),
        lambda: utils.run_all_images(widget),
        shortcuts["auto_run"],
        "auto-run",
        QCoreApplication.translate(
            "LabelingWidget", "Auto run all images at once"
        ),
        enabled=False,
    )
    delete_file = action(
        QCoreApplication.translate("LabelingWidget", "Delete File"),
        widget.delete_file,
        shortcuts["delete_file"],
        "delete",
        QCoreApplication.translate(
            "LabelingWidget", "Delete current label file"
        ),
        enabled=False,
    )
    delete_image_file = action(
        QCoreApplication.translate("LabelingWidget", "Delete Image File"),
        widget.delete_image_file,
        shortcuts["delete_image_file"],
        "delete",
        QCoreApplication.translate(
            "LabelingWidget", "Delete current image file"
        ),
        enabled=True,
    )
    data_audit = action(
        QCoreApplication.translate("LabelingWidget", "数据体检"),
        lambda: run_data_audit(widget),
        shortcuts["smart_data_audit"],
        "icon",
        QCoreApplication.translate(
            "LabelingWidget",
            "Scan the folder for unlabeled images, empty/corrupted "
            "labels and orphan label files",
        ),
        enabled=True,
    )
    smart_calibrate = action(
        QCoreApplication.translate("LabelingWidget", "1. 阈值校准"),
        lambda: run_threshold_calibration(widget),
        shortcuts["smart_calibrate"],
        "settings",
        QCoreApplication.translate(
            "LabelingWidget",
            "推荐先做：按各类置信度分布生成自动接受 / 建议复核阈值",
        ),
        enabled=True,
    )
    smart_analysis = action(
        QCoreApplication.translate("LabelingWidget", "2. 数据智能分析"),
        lambda: run_smart_analysis(widget),
        shortcuts["smart_analysis"],
        "overview",
        QCoreApplication.translate(
            "LabelingWidget",
            "阈值校准后再做：难例排序、重复图片检测与配平建议",
        ),
        enabled=True,
    )
    smart_missing_scan = action(
        QCoreApplication.translate("LabelingWidget", "3. 漏标扫描"),
        lambda: run_missing_scan(widget),
        shortcuts["smart_missing_scan"],
        "search",
        QCoreApplication.translate(
            "LabelingWidget",
            "智能分析后再做：用当前模型找出置信度高但没有标注的目标",
        ),
        enabled=True,
    )
    smart_iteration = action(
        QCoreApplication.translate("LabelingWidget", "4. 迭代收益看板"),
        lambda: show_iteration_dashboard(widget),
        shortcuts["smart_iteration"],
        "loop",
        QCoreApplication.translate(
            "LabelingWidget", "最后查看：每轮训练→回灌的边际收益与下一步建议"
        ),
        enabled=True,
    )
    smart_review = action(
        QCoreApplication.translate(
            "LabelingWidget", "5. 智能复核（下一张待复核）"
        ),
        lambda: run_review_jump(widget),
        shortcuts["smart_review"],
        "check",
        QCoreApplication.translate(
            "LabelingWidget",
            "按不确定性优先级跳到下一张待复核的图片（再次点击可继续跳）",
        ),
        enabled=True,
    )
    smart_propagate = action(
        QCoreApplication.translate(
            "LabelingWidget", "6. 标注传播（上一张→当前图）"
        ),
        widget._propagate_previous_labels,
        shortcuts["smart_propagate"],
        "copy",
        QCoreApplication.translate(
            "LabelingWidget",
            "把上一张已标注图片的框按比例复制到当前图片，自动跳过重复框",
        ),
        enabled=True,
    )
    smart_archive = action(
        QCoreApplication.translate("LabelingWidget", "7. 一键去重归档"),
        lambda: run_duplicate_archive(widget),
        shortcuts["smart_archive"],
        "trash",
        QCoreApplication.translate(
            "LabelingWidget",
            "把近重复图片及其标注移动到「._duplicates_archive」文件夹",
        ),
        enabled=True,
    )
    smart_advice = action(
        QCoreApplication.translate("LabelingWidget", "8. 训练建议"),
        lambda: run_training_advice(widget),
        shortcuts["smart_advice"],
        "brain",
        QCoreApplication.translate(
            "LabelingWidget",
            "训练前预检 + 基于当前数据与历史轮次推荐 epochs/batch/imgsz 初值",
        ),
        enabled=True,
    )
    smart_template = action(
        QCoreApplication.translate(
            "LabelingWidget", "9. 智能模板预标注（批量）"
        ),
        lambda: run_template_propagation(widget),
        shortcuts["smart_template"],
        "labels",
        QCoreApplication.translate(
            "LabelingWidget",
            "为未标注图片按相似度匹配已标注模板，批量生成预标注后再人工确认",
        ),
        enabled=True,
    )
    smart_stale_audit = action(
        QCoreApplication.translate("LabelingWidget", "10. 旧轮模型框盘点"),
        lambda: run_stale_model_audit(widget),
        shortcuts["smart_stale_audit"],
        "layers",
        QCoreApplication.translate(
            "LabelingWidget",
            "列出由其它模型留下、可考虑清理的框（只报告，不删除）",
        ),
        enabled=True,
    )
    smart_restore_backup = action(
        QCoreApplication.translate(
            "LabelingWidget", "11. 从备份恢复标注（撤销批量删除）"
        ),
        lambda: run_backup_restore(widget),
        shortcuts["smart_restore_backup"],
        "undo",
        QCoreApplication.translate(
            "LabelingWidget",
            "把 .label_backups 里的某一次快照写回标注目录；"
            "被覆盖的文件会先生成一个新快照",
        ),
        enabled=True,
    )
    toggle_annotation_checked = action(
        QCoreApplication.translate("LabelingWidget", "Mark as Checked"),
        widget.set_annotation_checked,
        shortcuts.get("toggle_annotation_checked"),
        None,
        QCoreApplication.translate(
            "LabelingWidget", "Mark current annotation as checked"
        ),
        checkable=True,
        enabled=False,
    )
    mark_checked_and_next = action(
        QCoreApplication.translate("LabelingWidget", "检查完成并下一张"),
        widget.mark_checked_and_next,
        shortcuts["mark_checked_and_next"],
        None,
        QCoreApplication.translate(
            "LabelingWidget", "将当前图片标为已检查，并跳到下一张未检查图片"
        ),
        enabled=False,
    )
    mark_rejected_and_next = action(
        QCoreApplication.translate("LabelingWidget", "打回并下一张"),
        widget.mark_rejected_and_next,
        shortcuts.get("mark_rejected_and_next"),
        None,
        QCoreApplication.translate(
            "LabelingWidget", "将当前图片标为需返工，并跳到下一张未检查图片"
        ),
        enabled=False,
    )
    # Menu-only on purpose: no shortcut key is invented here, so there is no
    # config entry that could drift from a real binding.
    confirm_classification = action(
        QCoreApplication.translate("LabelingWidget", "确认分类建议"),
        widget.confirm_classification,
        None,
        None,
        QCoreApplication.translate(
            "LabelingWidget", "把分类模型的整图建议写入图片类别（flags）"
        ),
        enabled=False,
    )

    change_output_dir = action(
        QCoreApplication.translate("LabelingWidget", "Change Output Dir"),
        slot=widget.change_output_dir_dialog,
        shortcut=shortcuts["save_to"],
        icon="open",
        tip=QCoreApplication.translate(
            "LabelingWidget", "Change where annotations are loaded/saved"
        ),
    )

    save_auto = action(
        text=QCoreApplication.translate(
            "LabelingWidget", "Save Automatically"
        ),
        slot=lambda x: widget._config.update({"auto_save": x}),
        icon=None,
        tip=QCoreApplication.translate("LabelingWidget", "Save automatically"),
        checkable=True,
        enabled=True,
        checked=widget._config["auto_save"],
    )

    save_with_image_data = action(
        text=QCoreApplication.translate(
            "LabelingWidget", "Save With Image Data"
        ),
        slot=lambda x: widget._config.update({"store_data": x}),
        icon=None,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Save image data in label file"
        ),
        checkable=True,
        checked=widget._config["store_data"],
    )

    close = action(
        QCoreApplication.translate("LabelingWidget", "Close"),
        widget.close_file,
        shortcuts["close"],
        "cancel",
        QCoreApplication.translate("LabelingWidget", "Close current file"),
    )

    keep_prev_mode = action(
        QCoreApplication.translate(
            "LabelingWidget", "Keep Previous Annotation"
        ),
        lambda x: widget._config.update({"keep_prev": x}),
        shortcuts["toggle_keep_prev_mode"],
        None,
        QCoreApplication.translate(
            "LabelingWidget", 'Toggle "Keep Previous Annotation" mode'
        ),
        checkable=True,
        checked=widget._config["keep_prev"],
    )

    auto_use_last_label_mode = action(
        QCoreApplication.translate("LabelingWidget", "Auto Use Last Label"),
        lambda x: widget._config.update({"auto_use_last_label": x}),
        shortcuts["toggle_auto_use_last_label"],
        None,
        QCoreApplication.translate(
            "LabelingWidget", 'Toggle "Auto Use Last Label" mode'
        ),
        checkable=True,
        checked=widget._config["auto_use_last_label"],
    )

    auto_use_last_gid_mode = action(
        QCoreApplication.translate("LabelingWidget", "Auto Use Last Group ID"),
        lambda x: widget._config.update({"auto_use_last_gid": x}),
        shortcuts["toggle_auto_use_last_gid"],
        None,
        QCoreApplication.translate(
            "LabelingWidget", 'Toggle "Auto Use Last Group ID" mode'
        ),
        checkable=True,
        checked=widget._config["auto_use_last_gid"],
    )

    use_system_clipboard = action(
        QCoreApplication.translate("LabelingWidget", "Use System Clipboard"),
        widget.toggle_system_clipboard,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Use system clipboard for copy and paste"
        ),
        checkable=True,
        checked=widget._config["system_clipboard"],
        enabled=True,
    )

    visibility_shapes_mode = action(
        QCoreApplication.translate("LabelingWidget", "Visibility Shapes"),
        widget.toggle_visibility_shapes,
        shortcuts["toggle_visibility_shapes"],
        None,
        QCoreApplication.translate(
            "LabelingWidget", 'Toggle "Visibility Shapes" mode'
        ),
        checkable=True,
        checked=widget._config["show_shapes"],
    )

    create_mode = action(
        QCoreApplication.translate("LabelingWidget", "Create Polygons"),
        lambda: widget.toggle_draw_mode(False, create_mode="polygon"),
        shortcuts["create_polygon"],
        "polygon",
        QCoreApplication.translate("LabelingWidget", "Start drawing polygons"),
        enabled=False,
    )
    create_brush_polygon_mode = action(
        QCoreApplication.translate("LabelingWidget", "Create Brush Polygons"),
        widget.toggle_brush_polygon_mode,
        shortcuts["create_brush_polygon"],
        "brush_polygon",
        QCoreApplication.translate(
            "LabelingWidget", "Toggle brush mode for drawing polygons"
        ),
        enabled=False,
    )
    create_rectangle_mode = action(
        QCoreApplication.translate("LabelingWidget", "Create Rectangle"),
        lambda: widget.toggle_draw_mode(False, create_mode="rectangle"),
        shortcuts["create_rectangle"],
        "rectangle",
        QCoreApplication.translate(
            "LabelingWidget", "Start drawing rectangles"
        ),
        enabled=False,
    )
    create_point_mode = action(
        QCoreApplication.translate("LabelingWidget", "Create Point"),
        lambda: widget.toggle_draw_mode(False, create_mode="point"),
        shortcuts["create_point"],
        "point",
        QCoreApplication.translate("LabelingWidget", "Start drawing points"),
        enabled=False,
    )
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

    zoom = QtWidgets.QWidgetAction(widget)
    zoom.setDefaultWidget(widget.zoom_widget)
    widget.zoom_widget.setWhatsThis(
        str(
            QCoreApplication.translate(
                "LabelingWidget",
                "Zoom in or out of the image. Also accessible with "
                "{} and {} from the canvas.",
            )
        ).format(
            utils.fmt_shortcut(
                f"{shortcuts['zoom_in']},{shortcuts['zoom_out']}"
            ),
            utils.fmt_shortcut(
                QCoreApplication.translate("LabelingWidget", "Ctrl+Wheel")
            ),
        )
    )
    widget.zoom_widget.setEnabled(False)

    zoom_in = action(
        QCoreApplication.translate("LabelingWidget", "Zoom In"),
        functools.partial(widget.add_zoom, 1.1),
        shortcuts["zoom_in"],
        "zoom-in",
        QCoreApplication.translate("LabelingWidget", "Increase zoom level"),
        enabled=False,
    )
    zoom_out = action(
        QCoreApplication.translate("LabelingWidget", "Zoom Out"),
        functools.partial(widget.add_zoom, 0.9),
        shortcuts["zoom_out"],
        "zoom-out",
        QCoreApplication.translate("LabelingWidget", "Decrease zoom level"),
        enabled=False,
    )
    zoom_org = action(
        QCoreApplication.translate("LabelingWidget", "Original Size"),
        functools.partial(widget.set_zoom, 100),
        shortcuts["zoom_to_original"],
        "zoom",
        QCoreApplication.translate("LabelingWidget", "Zoom to original size"),
        enabled=False,
    )
    keep_prev_scale = action(
        QCoreApplication.translate("LabelingWidget", "Keep Previous Scale"),
        lambda x: widget._config.update({"keep_prev_scale": x}),
        shortcut=shortcuts["keep_prev_scale"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Keep previous zoom scale"
        ),
        checkable=True,
        checked=widget._config["keep_prev_scale"],
        enabled=True,
    )
    keep_prev_brightness = action(
        QCoreApplication.translate(
            "LabelingWidget", "Keep Previous Brightness"
        ),
        lambda x: widget._config.update({"keep_prev_brightness": x}),
        shortcut=shortcuts["keep_prev_brightness"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Keep previous brightness"
        ),
        checkable=True,
        checked=widget._config["keep_prev_brightness"],
        enabled=True,
    )
    keep_prev_contrast = action(
        QCoreApplication.translate("LabelingWidget", "Keep Previous Contrast"),
        lambda x: widget._config.update({"keep_prev_contrast": x}),
        shortcut=shortcuts["keep_prev_contrast"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Keep previous contrast"
        ),
        checkable=True,
        checked=widget._config["keep_prev_contrast"],
        enabled=True,
    )
    fit_window = action(
        QCoreApplication.translate("LabelingWidget", "Fit Window"),
        widget.set_fit_window,
        shortcuts["fit_window"],
        "fit-window",
        QCoreApplication.translate(
            "LabelingWidget", "Zoom follows window size"
        ),
        checkable=True,
        enabled=False,
    )
    fit_width = action(
        QCoreApplication.translate("LabelingWidget", "Fit Width"),
        widget.set_fit_width,
        shortcuts["fit_width"],
        "fit-width",
        QCoreApplication.translate(
            "LabelingWidget", "Zoom follows window width"
        ),
        checkable=True,
        enabled=False,
    )
    brightness_contrast = action(
        QCoreApplication.translate(
            "LabelingWidget", "Set Brightness Contrast"
        ),
        widget.brightness_contrast,
        shortcuts["brightness_contrast"],
        "color",
        "Adjust brightness and contrast",
        enabled=False,
    )
    set_cross_line = action(
        QCoreApplication.translate("LabelingWidget", "Set Cross Line"),
        widget.set_cross_line,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Adjust cross line for mouse position"
        ),
        icon="cartesian",
    )
    show_groups = action(
        QCoreApplication.translate("LabelingWidget", "Show Groups"),
        lambda x: widget.set_canvas_params("show_groups", x),
        shortcut=shortcuts["show_groups"],
        tip=QCoreApplication.translate("LabelingWidget", "Show shape groups"),
        icon=None,
        checkable=True,
        checked=widget._config["show_groups"],
        enabled=True,
        auto_trigger=True,
    )
    show_masks = action(
        QCoreApplication.translate("LabelingWidget", "Show Masks"),
        lambda x: widget.set_canvas_params("show_masks", x),
        shortcut=shortcuts["show_masks"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Show semi-transparent masks for shapes"
        ),
        icon=None,
        checkable=True,
        checked=widget._config["show_masks"],
        enabled=True,
        auto_trigger=True,
    )
    # Fire the shortcut even when a child widget (e.g. the text-prompt
    # QLineEdit) has focus, so Ctrl+M reliably toggles the mask overlay.
    show_masks.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    show_texts = action(
        QCoreApplication.translate("LabelingWidget", "Show Texts"),
        lambda x: widget.set_canvas_params("show_texts", x),
        shortcut=shortcuts["show_texts"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Show text above shapes"
        ),
        icon=None,
        checkable=True,
        checked=widget._config["show_texts"],
        enabled=True,
        auto_trigger=True,
    )
    show_labels = action(
        QCoreApplication.translate("LabelingWidget", "Show Labels"),
        lambda x: widget.set_canvas_params("show_labels", x),
        shortcut=shortcuts["show_labels"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Show label inside shapes"
        ),
        icon=None,
        checkable=True,
        checked=widget._config["show_labels"],
        enabled=True,
        auto_trigger=True,
    )
    # Toggle the attribute text painted on the canvas. The canvas has
    # supported ``show_attributes`` all along, but it was never exposed as
    # an action, which left Ctrl+Shift+L advertised in the F1 cheat sheet
    # while doing nothing.
    show_attributes = action(
        QCoreApplication.translate("LabelingWidget", "Show Attributes"),
        lambda x: widget.set_canvas_params("show_attributes", x),
        shortcut=shortcuts["show_attributes"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Show attributes below shapes"
        ),
        icon=None,
        checkable=True,
        checked=widget._config["show_attributes"],
        enabled=True,
        auto_trigger=True,
    )
    # Same reasoning as show_masks: the shortcut must win over a focused
    # child widget (e.g. the text-prompt QLineEdit).
    show_attributes.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    show_scores = action(
        QCoreApplication.translate("LabelingWidget", "Show Scores"),
        lambda x: widget.set_canvas_params("show_scores", x),
        shortcut=shortcuts["show_scores"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Show score inside shapes"
        ),
        icon=None,
        checkable=True,
        checked=widget._config["show_scores"],
        enabled=True,
        auto_trigger=True,
    )
    show_degrees = action(
        QCoreApplication.translate("LabelingWidget", "Show Degrees"),
        lambda x: widget.set_canvas_params("show_degrees", x),
        shortcut=shortcuts["show_degrees"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Show degrees above rotated shapes"
        ),
        icon=None,
        checkable=True,
        checked=widget._config["show_degrees"],
        enabled=True,
        auto_trigger=True,
    )

    # Theme menu options (System / Light / Dark)
    theme_mode_actions = []
    theme_group = QtGui.QActionGroup(widget)
    theme_group.setExclusive(True)
    widget._theme_actions = {}
    current_appearance = widget._config.get("theme", "auto")
    for _mode, _label in (
        ("auto", QCoreApplication.translate("LabelingWidget", "System")),
        ("light", QCoreApplication.translate("LabelingWidget", "Light")),
        ("dark", QCoreApplication.translate("LabelingWidget", "Dark")),
    ):
        _act = QtGui.QAction(_label, theme_group)
        _act.setCheckable(True)
        _act.setChecked(current_appearance == _mode)
        _act.setData(_mode)
        _act.triggered.connect(
            functools.partial(widget._on_theme_changed, _mode)
        )
        theme_mode_actions.append(_act)
        widget._theme_actions[_mode] = _act

    # Upload
    upload_export_icon = "label"
    upload_image_flags_file = action(
        QCoreApplication.translate("LabelingWidget", "Image Flags"),
        lambda: utils.upload_image_flags_file(widget),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Upload Custom Image Flags File"
        ),
    )
    upload_label_flags_file = action(
        QCoreApplication.translate("LabelingWidget", "Label Flags"),
        lambda: utils.upload_label_flags_file(widget, LABEL_OPACITY),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Upload Custom Label Flags File"
        ),
    )
    upload_label_classes_file = action(
        QCoreApplication.translate("LabelingWidget", "Label Classes"),
        lambda: utils.upload_label_classes_file(widget),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Upload Custom Label Classes File"
        ),
    )
    upload_yolo_hbb_annotation = action(
        QCoreApplication.translate("LabelingWidget", "YOLO HBB"),
        lambda: utils.upload_yolo_annotation(widget, "hbb", LABEL_OPACITY),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget",
            "Upload Custom YOLO Horizontal Bounding Boxes Annotations",
        ),
    )
    upload_yolo_seg_annotation = action(
        QCoreApplication.translate("LabelingWidget", "YOLO Seg"),
        lambda: utils.upload_yolo_annotation(widget, "seg", LABEL_OPACITY),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Upload Custom YOLO Segmentation Annotations"
        ),
    )
    upload_yolo_obb_annotation = action(
        QCoreApplication.translate("LabelingWidget", "YOLO OBB"),
        lambda: utils.upload_yolo_annotation(widget, "obb", LABEL_OPACITY),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget",
            "Upload Custom YOLO Oriented Bounding Boxes Annotations",
        ),
    )
    upload_yolo_pose_annotation = action(
        QCoreApplication.translate("LabelingWidget", "YOLO Pose"),
        lambda: utils.upload_yolo_annotation(widget, "pose", LABEL_OPACITY),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Upload Custom YOLO Pose Annotations"
        ),
    )

    # Export
    export_yolo_hbb_annotation = action(
        QCoreApplication.translate("LabelingWidget", "YOLO HBB"),
        lambda: utils.export_yolo_annotation(widget, "hbb"),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget",
            "Export Custom YOLO Horizontal Bounding Boxes Annotations",
        ),
    )
    export_yolo_seg_annotation = action(
        QCoreApplication.translate("LabelingWidget", "YOLO Seg"),
        lambda: utils.export_yolo_annotation(widget, "seg"),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Export Custom YOLO Segmentation Annotations"
        ),
    )
    export_yolo_pose_annotation = action(
        QCoreApplication.translate("LabelingWidget", "YOLO Pose"),
        lambda: utils.export_yolo_annotation(widget, "pose"),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Export Custom YOLO Pose Annotations"
        ),
    )
    export_yolo_obb_annotation = action(
        QCoreApplication.translate("LabelingWidget", "YOLO OBB"),
        lambda: utils.export_yolo_annotation(widget, "obb"),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget",
            "Export Custom YOLO Oriented Bounding Boxes Annotations",
        ),
    )

    # Group zoom controls into a list for easier toggling.
    zoom_actions = (
        widget.zoom_widget,
        zoom_in,
        zoom_out,
        zoom_org,
        fit_window,
        fit_width,
    )
    widget.zoom_mode = widget.FIT_WINDOW
    fit_window.setChecked(True)
    widget.scalers = {
        widget.FIT_WINDOW: widget.scale_fit_window,
        widget.FIT_WIDTH: widget.scale_fit_width,
        # Set to one to scale to 100% when loading files.
        widget.MANUAL_ZOOM: lambda: 1,
    }

    edit = action(
        QCoreApplication.translate("LabelingWidget", "Edit Label"),
        widget.edit_label,
        shortcuts["edit_label"],
        "edit",
        QCoreApplication.translate(
            "LabelingWidget", "Modify the label of the selected polygon"
        ),
        enabled=False,
    )

    fill_drawing = action(
        QCoreApplication.translate("LabelingWidget", "Fill Drawing Polygon"),
        widget.canvas.set_fill_drawing,
        shortcuts["fill_drawing"],
        "color",
        QCoreApplication.translate(
            "LabelingWidget", "Fill polygon while drawing"
        ),
        checkable=True,
        enabled=True,
    )
    fill_drawing.trigger()

    show_navigator = action(
        QCoreApplication.translate("LabelingWidget", "Navigator"),
        widget.toggle_navigator,
        shortcuts["show_navigator"],
        "navigator",
        QCoreApplication.translate(
            "LabelingWidget", "Show/hide the navigator window"
        ),
        checkable=True,
        enabled=True,
    )

    # AI Actions
    toggle_auto_labeling_widget = action(
        QCoreApplication.translate("LabelingWidget", "Auto Labeling"),
        widget.toggle_auto_labeling_widget,
        shortcuts["auto_label"],
        "brain",
        QCoreApplication.translate("LabelingWidget", "Auto Labeling"),
    )

    widget.label_list.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    # Store actions for further handling.
    widget.actions = utils.Struct(
        # The quality/review tools live only in the 智能工具 menu, but they
        # carry rebindable shortcuts now, so the settings runtime needs to
        # reach them by name like every other action.
        data_audit=data_audit,
        smart_review=smart_review,
        smart_propagate=smart_propagate,
        smart_stale_audit=smart_stale_audit,
        smart_calibrate=smart_calibrate,
        smart_analysis=smart_analysis,
        smart_missing_scan=smart_missing_scan,
        smart_iteration=smart_iteration,
        smart_archive=smart_archive,
        smart_advice=smart_advice,
        smart_template=smart_template,
        smart_restore_backup=smart_restore_backup,
        fill_drawing=fill_drawing,
        shape_converter=shape_converter,
        run_history=run_history,
        shortcuts_help=shortcuts_help,
        save_crop=save_crop,
        ultralytics_train=ultralytics_train,
        save_auto=save_auto,
        save_with_image_data=save_with_image_data,
        change_output_dir=change_output_dir,
        save=save,
        save_as=save_as,
        open=open_,
        open_dir=opendir,
        open_project=open_project,
        close=close,
        delete_file=delete_file,
        delete_image_file=delete_image_file,
        toggle_annotation_checked=toggle_annotation_checked,
        mark_checked_and_next=mark_checked_and_next,
        mark_rejected_and_next=mark_rejected_and_next,
        confirm_classification=confirm_classification,
        keep_prev_mode=keep_prev_mode,
        auto_use_last_label_mode=auto_use_last_label_mode,
        auto_use_last_gid_mode=auto_use_last_gid_mode,
        use_system_clipboard=use_system_clipboard,
        visibility_shapes_mode=visibility_shapes_mode,
        run_all_images=run_all_images,
        union_selection=union_selection,
        delete=delete,
        edit=edit,
        duplicate=duplicate,
        copy=copy,
        copy_coordinates=copy_coordinates,
        paste=paste,
        toggle_shape_lock=toggle_shape_lock,
        overview=overview,
        save_visualization_image=save_visualization_image,
        undo_last_point=undo_last_point,
        undo=undo,
        redo=redo,
        remove_point=remove_point,
        create_mode=create_mode,
        create_brush_polygon_mode=create_brush_polygon_mode,
        edit_mode=edit_mode,
        edit_brush_mode=edit_brush_mode,
        create_rectangle_mode=create_rectangle_mode,
        create_point_mode=create_point_mode,
        create_cuboid_mode=create_cuboid_mode,
        create_rotation_mode=create_rotation_mode,
        create_quadrilateral_mode=create_quadrilateral_mode,
        create_circle_mode=create_circle_mode,
        create_line_mode=create_line_mode,
        create_linestrip_mode=create_linestrip_mode,
        digit_shortcut_0=digit_shortcut_0,
        digit_shortcut_1=digit_shortcut_1,
        digit_shortcut_2=digit_shortcut_2,
        digit_shortcut_3=digit_shortcut_3,
        digit_shortcut_4=digit_shortcut_4,
        digit_shortcut_5=digit_shortcut_5,
        digit_shortcut_6=digit_shortcut_6,
        digit_shortcut_7=digit_shortcut_7,
        digit_shortcut_8=digit_shortcut_8,
        digit_shortcut_9=digit_shortcut_9,
        digit_shortcut_actions=(
            digit_shortcut_0,
            digit_shortcut_1,
            digit_shortcut_2,
            digit_shortcut_3,
            digit_shortcut_4,
            digit_shortcut_5,
            digit_shortcut_6,
            digit_shortcut_7,
            digit_shortcut_8,
            digit_shortcut_9,
        ),
        upload_image_flags_file=upload_image_flags_file,
        upload_label_flags_file=upload_label_flags_file,
        upload_label_classes_file=upload_label_classes_file,
        upload_yolo_hbb_annotation=upload_yolo_hbb_annotation,
        upload_yolo_seg_annotation=upload_yolo_seg_annotation,
        upload_yolo_pose_annotation=upload_yolo_pose_annotation,
        upload_yolo_obb_annotation=upload_yolo_obb_annotation,
        export_yolo_hbb_annotation=export_yolo_hbb_annotation,
        export_yolo_seg_annotation=export_yolo_seg_annotation,
        export_yolo_pose_annotation=export_yolo_pose_annotation,
        export_yolo_obb_annotation=export_yolo_obb_annotation,
        zoom=zoom,
        zoom_in=zoom_in,
        zoom_out=zoom_out,
        zoom_org=zoom_org,
        keep_prev_scale=keep_prev_scale,
        keep_prev_brightness=keep_prev_brightness,
        keep_prev_contrast=keep_prev_contrast,
        fit_window=fit_window,
        fit_width=fit_width,
        brightness_contrast=brightness_contrast,
        set_cross_line=set_cross_line,
        show_groups=show_groups,
        show_masks=show_masks,
        show_texts=show_texts,
        show_labels=show_labels,
        show_attributes=show_attributes,
        show_scores=show_scores,
        show_degrees=show_degrees,
        show_navigator=show_navigator,
        zoom_actions=zoom_actions,
        open_next_image=open_next_image,
        open_prev_image=open_prev_image,
        open_next_unchecked_image=open_next_unchecked_image,
        open_prev_unchecked_image=open_prev_unchecked_image,
        toggle_auto_labeling_widget=toggle_auto_labeling_widget,
        digit_shortcut_manager=digit_shortcut_manager,
        label_manager=label_manager,
        gid_manager=gid_manager,
        shape_manager=shape_manager,
        loop_thru_labels=loop_thru_labels,
        loop_select_labels=loop_select_labels,
        select_toggle_shapes=select_toggle_shapes,
        select_all=select_all,
        file_menu_actions=(
            open_,
            opendir,
            save,
            save_as,
            close,
        ),
        tool=(),
        # 每个绑定的键都由窗口里已安装的 QAction 承载：验收第 15 步守住这点
        editMenu=(
            edit,
            select_all,
            duplicate,
            delete,
            copy,
            paste,
            None,
            undo,
            undo_last_point,
            redo,
            None,
            copy_coordinates,
            remove_point,
            union_selection,
            None,
            keep_prev_mode,
            auto_use_last_label_mode,
            auto_use_last_gid_mode,
            use_system_clipboard,
            visibility_shapes_mode,
        ),
        # menu shown at right click
        menu=(
            create_mode,
            create_brush_polygon_mode,
            create_rectangle_mode,
            create_point_mode,
            create_rotation_mode,
            create_quadrilateral_mode,
            create_circle_mode,
            create_line_mode,
            create_linestrip_mode,
            create_cuboid_mode,
            None,
            edit_mode,
            edit_brush_mode,
            edit,
            toggle_shape_lock,
            None,
            copy_coordinates,
            union_selection,
            duplicate,
            copy,
            paste,
            None,
            delete,
            undo,
            undo_last_point,
            redo,
            remove_point,
        ),
        on_load_active=(
            close,
            create_mode,
            create_brush_polygon_mode,
            create_rectangle_mode,
            create_point_mode,
            create_cuboid_mode,
            create_rotation_mode,
            create_quadrilateral_mode,
            create_circle_mode,
            create_line_mode,
            create_linestrip_mode,
            digit_shortcut_0,
            digit_shortcut_1,
            digit_shortcut_2,
            digit_shortcut_3,
            digit_shortcut_4,
            digit_shortcut_5,
            digit_shortcut_6,
            digit_shortcut_7,
            digit_shortcut_8,
            digit_shortcut_9,
            edit_mode,
            brightness_contrast,
            toggle_annotation_checked,
            mark_checked_and_next,
            mark_rejected_and_next,
            shape_manager,
            loop_thru_labels,
            loop_select_labels,
            select_toggle_shapes,
        ),
        on_shapes_present=(save_as, delete),
        hide_selected_polygons=hide_selected_polygons,
        show_hidden_polygons=show_hidden_polygons,
        group_selected_shapes=group_selected_shapes,
        ungroup_selected_shapes=ungroup_selected_shapes,
    )

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
            open_,
            open_next_image,
            open_prev_image,
            open_next_unchecked_image,
            open_prev_unchecked_image,
            opendir,
            widget.menus.recent_files,
            save,
            save_as,
            save_auto,
            change_output_dir,
            save_with_image_data,
            close,
            delete_file,
            delete_image_file,
            None,
            mark_checked_and_next,
            mark_rejected_and_next,
            confirm_classification,
            None,
        ),
    )
    smart_tools_menu.populate_smart_tools_menu(
        widget.menus.smart_tools, widget.actions
    )
    device_menu.populate_device_menu(widget)
    help_menu.populate_help_menu(widget, widget.menus.help, shortcuts_help)
    utils.add_actions(widget.menus.train, (ultralytics_train, run_history))
    utils.add_actions(
        widget.menus.tool,
        (
            overview,
            None,
            save_crop,
            save_visualization_image,
            None,
            digit_shortcut_manager,
            label_manager,
            gid_manager,
            shape_manager,
            None,
            shape_converter,
        ),
    )
    utils.add_actions(widget.menus.theme, theme_mode_actions)
    utils.add_actions(
        widget.menus.upload,
        (
            upload_image_flags_file,
            upload_label_flags_file,
            upload_label_classes_file,
            None,
            upload_yolo_hbb_annotation,
            upload_yolo_seg_annotation,
            upload_yolo_obb_annotation,
            upload_yolo_pose_annotation,
        ),
    )
    utils.add_actions(
        widget.menus.export,
        (
            export_yolo_hbb_annotation,
            export_yolo_seg_annotation,
            export_yolo_obb_annotation,
            export_yolo_pose_annotation,
        ),
    )
    utils.add_actions(
        widget.menus.view,
        (
            show_navigator,
            fill_drawing,
            loop_thru_labels,
            loop_select_labels,
            None,
            zoom_in,
            zoom_out,
            zoom_org,
            None,
            keep_prev_scale,
            keep_prev_brightness,
            keep_prev_contrast,
            None,
            fit_window,
            fit_width,
            None,
            brightness_contrast,
            set_cross_line,
            None,
            show_masks,
            show_texts,
            show_labels,
            show_attributes,
            show_scores,
            show_degrees,
            show_groups,
            hide_selected_polygons,
            show_hidden_polygons,
            group_selected_shapes,
            ungroup_selected_shapes,
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
        opendir,
        open_prev_image,
        open_next_image,
        save,
        delete_file,
        None,
        create_mode,
        widget.actions.create_rectangle_mode,
        widget.actions.create_point_mode,
        widget.actions.create_brush_polygon_mode,
        None,
        edit_mode,
        edit_brush_mode,
        delete,
        undo,
        redo,
        None,
        loop_thru_labels,
        loop_select_labels,
        select_toggle_shapes,
        None,
        run_all_images,
        toggle_auto_labeling_widget,
        None,
        fit_width,
        zoom,
    )
