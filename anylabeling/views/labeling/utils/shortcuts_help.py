"""Keyboard-shortcut reference for the shortcuts-help dialog.

Kept free of Qt so the grouping/filtering logic can be unit-tested. The
dialog itself lives in :mod:`label_widget` and only renders the rows.
"""

from __future__ import annotations
from PyQt6.QtCore import QCoreApplication
from PyQt6 import QtCore, QtGui, QtWidgets

#: (group title, [(config shortcut key, Chinese description), ...])
SHORTCUT_GROUPS = [
    (
        "文件与切图",
        [
            ("open", "打开图片"),
            ("open_dir", "打开文件夹"),
            ("open_project", "切换项目"),
            ("open_next", "下一张图片"),
            ("open_prev", "上一张图片"),
            ("open_next_unchecked", "下一张未检查图片"),
            ("open_prev_unchecked", "上一张未检查图片"),
            ("toggle_annotation_checked", "标记当前图片已检查"),
            ("mark_checked_and_next", "标记已检查并跳到下一张未检查"),
            ("mark_rejected_and_next", "打回（需返工）并跳到下一张未检查"),
            ("save", "保存标注"),
            ("save_as", "另存为"),
            ("save_to", "另存到指定文件夹"),
            ("close", "关闭当前标注"),
            ("delete_file", "删除标注文件"),
            ("delete_image_file", "删除图片及其标注"),
            ("quit", "退出程序"),
        ],
    ),
    (
        "创建标注",
        [
            ("create_polygon", "画多边形"),
            ("create_rectangle", "画矩形框"),
            ("create_cuboid", "画立方体"),
            ("create_rotation", "画旋转框"),
            ("create_quadrilateral", "画四边形"),
            ("create_circle", "画圆"),
            ("create_line", "画线段"),
            ("create_point", "画点"),
            ("create_linestrip", "画折线"),
            ("create_brush_polygon", "画笔涂抹"),
        ],
    ),
    (
        "编辑标注",
        [
            ("edit_polygon", "编辑形状"),
            ("edit_brush_mode", "画笔编辑模式"),
            ("fill_drawing", "画多边形时填充"),
            ("shape_converter", "形状转换器"),
            ("delete_polygon", "删除选中标注"),
            ("duplicate_polygon", "复制标注"),
            ("copy_polygon", "复制到剪贴板"),
            ("paste_polygon", "粘贴标注"),
            ("undo", "撤销"),
            (
                "undo_last_point",
                "撤销上一个点（画多边形时 Ctrl+Z 的作用）",
            ),
            ("redo", "重做"),
            ("add_point_to_edge", "在边上加点"),
            ("remove_selected_point", "删除选中点"),
            ("edit_label", "编辑当前标签"),
            ("edit_group_id", "编辑分组号"),
            ("group_selected_shapes", "选中标注编组"),
            ("ungroup_selected_shapes", "取消编组"),
            ("union_selected_shapes", "合并选中标注"),
        ],
    ),
    (
        "视图与显示",
        [
            ("zoom_in", "放大"),
            ("zoom_out", "缩小"),
            ("zoom_to_original", "1:1 原始大小"),
            ("fit_window", "适应窗口"),
            ("fit_width", "适应宽度"),
            ("show_navigator", "显示导航器"),
            ("show_overview", "总览"),
            ("show_masks", "显示/隐藏掩膜"),
            ("show_texts", "显示/隐藏文本"),
            ("show_labels", "显示/隐藏标签"),
            ("show_attributes", "显示/隐藏属性"),
            ("toggle_visibility_shapes", "显示/隐藏标注"),
            ("hide_selected_polygons", "隐藏选中标注"),
            ("show_hidden_polygons", "显示已隐藏标注"),
            ("show_groups", "显示/隐藏分组号"),
            ("show_scores", "显示/隐藏置信度"),
            ("show_degrees", "显示/隐藏旋转角度"),
            ("select_toggle_shapes", "全部标注显隐"),
            ("toggle_sidebar", "收起/展开右侧面板"),
            ("brightness_contrast", "调整亮度与对比度"),
            ("keep_prev_scale", "记忆上一张的缩放"),
            ("keep_prev_brightness", "记忆上一张的亮度"),
            ("keep_prev_contrast", "记忆上一张的对比度"),
        ],
    ),
    (
        "自动标注与智能工具",
        [
            ("auto_label", "自动标注"),
            ("auto_run", "对所有图片自动标注"),
            ("loop_thru_labels", "循环遍历标签"),
            ("loop_select_labels", "循环选择标签"),
            ("auto_labeling_add_point", "自动标注：加提示点"),
            ("auto_labeling_remove_point", "自动标注：删提示点"),
            ("auto_labeling_run", "自动标注：执行"),
            ("auto_labeling_clear", "自动标注：清除"),
            ("auto_labeling_finish_object", "自动标注：完成当前对象"),
        ],
    ),
    (
        "质检与审核",
        [
            ("smart_data_audit", "数据体检"),
            ("smart_review", "智能复核：跳到下一张待复核"),
            ("smart_propagate", "标注传播：上一张→当前图"),
            ("smart_stale_audit", "陈旧框审计"),
            ("smart_calibrate", "阈值校准"),
            ("smart_analysis", "数据智能分析"),
            ("smart_missing_scan", "漏标扫描"),
            ("smart_iteration", "迭代收益看板"),
            ("smart_archive", "一键去重归档"),
            ("smart_advice", "训练建议"),
            ("smart_template", "智能模板预标注"),
            ("smart_restore_backup", "从备份恢复标注"),
        ],
    ),
    (
        "其它设置",
        [
            ("open_settings", "打开设置"),
            ("toggle_keep_prev_mode", "保留上一张状态"),
            ("toggle_auto_use_last_label", "自动沿用上一标签"),
            ("toggle_auto_use_last_gid", "自动沿用上一分组"),
            ("edit_digit_shortcut", "数字快捷键管理"),
            ("edit_labels", "批量编辑标签"),
            ("edit_shapes", "批量编辑标注"),
            ("show_shortcuts_help", "打开本速查表"),
        ],
    ),
]

#: Config keys that may appear but are intentionally hidden (no user value).
#: Empty on purpose: ``undo_last_point`` used to sit here, which left the
#: drawing-time meaning of ``Ctrl+Z`` — it removes the last vertex while a
#: polygon is being drawn — undocumented in the one place a user looks for it.
_HIDDEN_KEYS = frozenset()

#: Actions with no shipped default key, and why they are listed anyway: each
#: is a one-off menu item (a file dialog, a batch export, a training
#: launcher) that nobody needs a key for on day one, but a run of them turns
#: into a routine soon enough. They are rebindable in the settings dialog --
#: the field exists as soon as the key exists in the template -- so the F1
#: sheet names them instead of leaving the annotator to wonder whether the
#: feature has a keyboard entry at all. Kept to what a menu actually offers;
#: anything absent here is either bound or has no key on purpose.
UNBOUND_ACTIONS = [
    ("confirm_classification", "确认分类建议"),
    ("copy_coordinates", "复制选中标注的坐标"),
    ("export_yolo_hbb_annotation", "导出 YOLO 水平框"),
    ("export_yolo_obb_annotation", "导出 YOLO 旋转框"),
    ("export_yolo_pose_annotation", "导出 YOLO 姿态"),
    ("export_yolo_seg_annotation", "导出 YOLO 分割"),
    ("run_history", "训练历史"),
    ("save_auto", "保存到自动命名的标注文件"),
    ("save_crop", "保存裁剪图"),
    ("save_visualization_image", "保存可视化图"),
    ("save_with_image_data", "保存时内嵌图像数据"),
    ("set_cross_line", "设置十字线"),
    ("toggle_shape_lock", "锁定/解锁选中标注"),
    ("ultralytics_train", "启动 Ultralytics 训练"),
    ("upload_image_flags_file", "导入图像标志文件"),
    ("upload_label_classes_file", "导入类别文件"),
    ("upload_label_flags_file", "导入标签标志文件"),
    ("upload_yolo_hbb_annotation", "回导 YOLO 水平框"),
    ("upload_yolo_obb_annotation", "回导 YOLO 旋转框"),
    ("upload_yolo_pose_annotation", "回导 YOLO 姿态"),
    ("upload_yolo_seg_annotation", "回导 YOLO 分割"),
    ("use_system_clipboard", "使用系统剪贴板"),
]

#: Heading and key column used for those entries while they have no key.
UNBOUND_GROUP_TITLE = "未绑定动作（可在设置页绑键）"
NO_KEY_TEXT = "（未绑定）"


def _shortcut_to_text(value):
    """Normalize a shortcut config value (str/list/None) to display text."""
    if not value:
        return ""
    if isinstance(value, (list, tuple)):
        values = [str(item) for item in value if item]
        return " / ".join(values) if values else ""
    return str(value)


def build_shortcut_rows(shortcuts):
    """Map a shortcuts config dict to display rows.

    Returns a list of ``(group_title, key_text, description)``. Entries with
    no bound shortcut (empty/None) or hidden keys are skipped -- except the
    ones in :data:`UNBOUND_ACTIONS`, which get a trailing "no key yet"
    section instead. That section empties itself as keys are bound, so the
    sheet never claims a key exists that does not, and never hides a feature
    that does.
    """
    if not isinstance(shortcuts, dict):
        return []
    rows = []
    for group_title, entries in SHORTCUT_GROUPS:
        for config_key, description in entries:
            if config_key in _HIDDEN_KEYS:
                continue
            key_text = _shortcut_to_text(shortcuts.get(config_key))
            if not key_text:
                continue
            rows.append((group_title, key_text, description))
    rows.extend(
        (UNBOUND_GROUP_TITLE, NO_KEY_TEXT, description)
        for config_key, description in UNBOUND_ACTIONS
        if config_key not in _HIDDEN_KEYS
        and not _shortcut_to_text(shortcuts.get(config_key))
    )
    return rows


def filter_shortcut_rows(rows, query):
    """Keep rows whose group/key/description contains ``query`` (case-insensitive)."""
    query = (query or "").strip().lower()
    if not query:
        return rows
    return [
        row for row in rows if any(query in str(part).lower() for part in row)
    ]


def show_shortcuts_help(widget):
    """Dialog listing every configured shortcut with a search box."""
    shortcuts = widget._config.get("shortcuts", {})
    rows = build_shortcut_rows(shortcuts)
    dialog = QtWidgets.QDialog(widget)
    dialog.setWindowTitle(
        QCoreApplication.translate("LabelingWidget", "快捷键速查")
    )
    dialog.resize(460, 520)
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(8)

    search = QtWidgets.QLineEdit()
    search.setPlaceholderText(
        QCoreApplication.translate(
            "LabelingWidget", "搜索快捷键或功能（如 Ctrl+Z / 撤销）…"
        )
    )
    layout.addWidget(search)

    tree = QtWidgets.QTreeWidget()
    tree.setHeaderLabels(
        [
            QCoreApplication.translate("LabelingWidget", "快捷键"),
            QCoreApplication.translate("LabelingWidget", "功能"),
            QCoreApplication.translate("LabelingWidget", "分组"),
        ]
    )
    tree.setColumnWidth(0, 110)
    tree.setColumnWidth(1, 240)
    tree.setRootIsDecorated(False)
    tree.setAlternatingRowColors(True)
    layout.addWidget(tree, 1)

    def render():
        tree.clear()
        for group_title, key_text, description in filter_shortcut_rows(
            rows, search.text()
        ):
            item = QtWidgets.QTreeWidgetItem(
                [key_text, description, group_title]
            )
            tree.addTopLevelItem(item)

    def on_query(_text):
        render()
        if tree.topLevelItemCount():
            tree.scrollToTop()

    search.textChanged.connect(on_query)
    render()

    close_btn = QtWidgets.QPushButton(
        QCoreApplication.translate("LabelingWidget", "关闭")
    )
    close_btn.clicked.connect(dialog.accept)
    close_btn.setFixedWidth(80)
    button_row = QtWidgets.QHBoxLayout()
    button_row.addStretch()
    button_row.addWidget(close_btn)
    layout.addLayout(button_row)
    dialog.exec()
