"""File, project, audit and annotation-state actions.

Split out of ``action_builder.build_actions`` (the function was 1757
lines); the body is moved verbatim and returns its locals so the
caller can publish them under the historical action names.
"""

import functools

from PyQt6.QtCore import QCoreApplication

from jllabeling.views.labeling import utils

from .data_audit import run_data_audit
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


def build(widget):
    """Create the file actions and return them by name."""
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
    return locals()
