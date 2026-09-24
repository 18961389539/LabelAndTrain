"""Keyboard-shortcut reference for the shortcuts-help dialog.

Kept free of Qt so the grouping/filtering logic can be unit-tested. The
dialog itself lives in :mod:`label_widget` and only renders the rows.
"""

from __future__ import annotations

#: (group title, [(config shortcut key, Chinese description), ...])
SHORTCUT_GROUPS = [
    (
        "文件与切图",
        [
            ("open", "打开图片"),
            ("open_dir", "打开文件夹"),
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
            ("delete_polygon", "删除选中标注"),
            ("duplicate_polygon", "复制标注"),
            ("copy_polygon", "复制到剪贴板"),
            ("paste_polygon", "粘贴标注"),
            ("undo", "撤销"),
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

#: config keys that may appear but are intentionally hidden (no user value).
_HIDDEN_KEYS = {"undo_last_point"}


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
    no bound shortcut (empty/None) or hidden keys are skipped.
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
    return rows


def filter_shortcut_rows(rows, query):
    """Keep rows whose group/key/description contains ``query`` (case-insensitive)."""
    query = (query or "").strip().lower()
    if not query:
        return rows
    return [
        row
        for row in rows
        if any(query in str(part).lower() for part in row)
    ]
