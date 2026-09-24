"""Pure row-item operations for the file list.

Each function takes the labeling widget as its first argument so tests
can drive them with a light stub, the same pattern as
``_shape_editable_state`` in label_widget.
"""

import os.path as osp

from PyQt6.QtCore import QFile, Qt

from ..schema import REVIEW_CONFIRMED, REVIEW_REJECTED, REVIEW_UNCHECKED
from .roles import (
    FILE_ANNOTATION_ROLE,
    FILE_LOW_CONF_ROLE,
    FILE_NEGATIVE_ROLE,
    FILE_REVIEW_ROLE,
    FILE_REVIEWED_AT_ROLE,
)


def is_confirmed(state):
    return state == REVIEW_CONFIRMED


def set_file_item_review_state(widget, item, state, reviewed_at=None):
    changed = (
        item.data(Qt.ItemDataRole.UserRole) is not is_confirmed(state)
        or item.data(FILE_REVIEW_ROLE) != state
    )
    if changed:
        item.setData(Qt.ItemDataRole.UserRole, is_confirmed(state))
        item.setData(FILE_REVIEW_ROLE, state)
    refresh_file_item_status_icon(widget, item)
    if reviewed_at is not None:
        item.setData(FILE_REVIEWED_AT_ROLE, reviewed_at)
    refresh_file_item_tooltip(widget, item)
    return changed


def refresh_file_item_tooltip(widget, item, counts=None):
    """Rebuild a row's hover text from what the row already knows."""
    if item is None:
        return
    file = item.text()
    item.setToolTip(
        widget._file_item_tooltip(
            file,
            widget._label_path_for_image(file),
            item.data(FILE_REVIEW_ROLE) or REVIEW_UNCHECKED,
            item.data(FILE_REVIEWED_AT_ROLE),
            counts=counts,
            negative=bool(item.data(FILE_NEGATIVE_ROLE)),
            low_conf=bool(item.data(FILE_LOW_CONF_ROLE)),
        )
    )


def set_file_item_annotated(widget, item, annotated, negative=False):
    item.setData(FILE_ANNOTATION_ROLE, bool(annotated))
    item.setData(FILE_NEGATIVE_ROLE, bool(annotated) and bool(negative))
    if not annotated:
        item.setData(FILE_LOW_CONF_ROLE, False)
    if widget._config.get("file_list_checkbox_editable", False):
        item.setCheckState(
            Qt.CheckState.Checked if annotated else Qt.CheckState.Unchecked
        )
    refresh_file_item_status_icon(widget, item)


def refresh_file_item_status_icon(widget, item):
    annotated = bool(item.data(FILE_ANNOTATION_ROLE))
    negative = bool(item.data(FILE_NEGATIVE_ROLE))
    state = item.data(FILE_REVIEW_ROLE) or (
        REVIEW_CONFIRMED
        if item.data(Qt.ItemDataRole.UserRole) is True
        else REVIEW_UNCHECKED
    )
    # Only the icon: what it means belongs to the row tooltip, which also
    # carries the path, the review timestamp and the shape counts.
    if state == REVIEW_REJECTED:
        # Sent back for rework: still untrained, but needs eyes on it.
        item.setIcon(widget.file_status_icons["rejected"])
    elif state == REVIEW_CONFIRMED:
        item.setIcon(widget.file_status_icons["checked"])
    elif annotated and negative:
        # Negative sample: confirmed empty (json with zero shapes).
        item.setIcon(widget.file_status_icons["negative"])
    elif annotated:
        item.setIcon(widget.file_status_icons["annotated"])
    else:
        item.setIcon(widget.file_status_icons["unannotated"])


def file_item_annotation_checked(item):
    return item.data(Qt.ItemDataRole.UserRole) is True


def set_file_item_low_conf(widget, item, has_low_conf):
    value = bool(has_low_conf)
    if item.data(FILE_LOW_CONF_ROLE) is value:
        return
    syncing = getattr(widget, "_syncing_file_item", False)
    widget._syncing_file_item = True
    try:
        item.setData(FILE_LOW_CONF_ROLE, value)
    finally:
        widget._syncing_file_item = syncing


def review_state_name(widget, state):
    return {
        REVIEW_UNCHECKED: widget.tr("未检查"),
        REVIEW_CONFIRMED: widget.tr("已检查"),
        REVIEW_REJECTED: widget.tr("需返工"),
    }.get(state, widget.tr("未知"))


def file_item_tooltip(
    widget, file, label_file, state, reviewed_at=None, counts=None,
    negative=False, low_conf=False,
):
    """Hover text for one file row: what it is, and where it stands.

    Only data the row already has goes in here. Counting shapes for every
    row would mean parsing every JSON, which is the exact cost the
    background checker was introduced to avoid -- the open row gets counts
    because the canvas already holds them.
    """
    annotated = QFile.exists(label_file)
    lines = [osp.basename(str(file)), str(file)]
    lines.append(
        widget.tr("标注文件：%1").replace("%1", osp.basename(label_file))
        if annotated
        else widget.tr("尚无标注文件（保存后创建）")
    )
    status = widget.tr("复核状态：%1").replace(
        "%1", review_state_name(widget, state)
    )
    if reviewed_at:
        status += widget.tr("（%1）").replace("%1", reviewed_at)
    lines.append(status)
    if counts:
        lines.append(
            widget.tr("对象 %1 个：模型 %2 / 人工 %3 / 未记录 %4")
            .replace("%1", str(counts["total"]))
            .replace("%2", str(counts["model"]))
            .replace("%3", str(counts["human"]))
            .replace("%4", str(counts["unknown"]))
        )
    if state == REVIEW_REJECTED:
        lines.append(widget.tr("图标含义：已打回，待人工返工"))
    elif negative:
        lines.append(widget.tr("图标含义：负样本（确认无目标，空标注）"))
    elif state == REVIEW_UNCHECKED and annotated:
        lines.append(widget.tr("图标含义：已标注，尚未复核"))
    if low_conf:
        lines.append(widget.tr("含低置信度对象（建议复核）"))
    return "\n".join(lines)
