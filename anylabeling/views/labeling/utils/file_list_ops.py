"""File-list item operations and thumbnails. Moved out of LabelingWidget by scripts/extract_method.py; the class keeps stubs so wiring and tests stay."""

from .. import utils
from ..provenance import (
    SOURCE_HUMAN,
    SOURCE_MODEL,
    get_source,
    is_deletable_stale_shape,
    model_display_name,
    model_of,
    model_version_of,
    resolve_model_path,
    stamp_model_shapes,
    weight_digest,
)
from anylabeling.services.auto_labeling import _THUMBNAIL_RENDER_MODELS
from ..logger import logger
from ..filelist import items as filelist_items
from PyQt6.QtCore import QCoreApplication, Qt, pyqtSlot
from ..utils.async_label_check import (
    _label_file_review_state,
    label_file_review_info,
)
from ..schema import (
    REVIEW_CONFIRMED,
    REVIEW_REJECTED,
    REVIEW_STATES,
    REVIEW_UNCHECKED,
)
from ..label_file import LabelFile, LabelFileError
from ..filelist.roles import (
    CHECKED_FIELD,
    FILE_ANNOTATION_ROLE,
    FILE_LOW_CONF_ROLE,
    FILE_NEGATIVE_ROLE,
    FILE_REVIEW_ROLE,
    FILE_REVIEWED_AT_ROLE,
    REVIEW_STATE_FIELD,
    REVIEWED_AT_FIELD,
)
from PyQt6 import QtCore, QtGui, QtWidgets
import os
import os.path as osp


def pop_file_list_menu(widget, point):
    item = widget.file_list_widget.itemAt(point)
    if item is None:
        return

    menu = QtWidgets.QMenu(widget.file_list_widget)
    copy_name_action = menu.addAction(
        utils.new_icon("copy", "svg"),
        QCoreApplication.translate("LabelingWidget", "Copy File Name"),
    )
    copy_path_action = menu.addAction(
        utils.new_icon("copy", "svg"),
        QCoreApplication.translate("LabelingWidget", "Copy File Path"),
    )
    menu.addSeparator()
    check_and_next_action = menu.addAction(
        QCoreApplication.translate("LabelingWidget", "标记已检查并下一张")
    )
    del_label_action = menu.addAction(
        utils.new_icon("trash", "svg"),
        QCoreApplication.translate("LabelingWidget", "删除标注文件"),
    )
    del_image_action = menu.addAction(
        utils.new_icon("trash", "svg"),
        QCoreApplication.translate("LabelingWidget", "删除图片文件"),
    )
    menu.addSeparator()
    sort_menu = menu.addMenu(
        QCoreApplication.translate("LabelingWidget", "排序方式")
    )
    sort_name = sort_menu.addAction(
        QCoreApplication.translate("LabelingWidget", "按文件名")
    )
    sort_time = sort_menu.addAction(
        QCoreApplication.translate("LabelingWidget", "按修改时间")
    )
    sort_annotation = sort_menu.addAction(
        QCoreApplication.translate("LabelingWidget", "按标注状态")
    )
    current_sort = getattr(widget, "_file_sort_mode", "name")
    sort_name.setCheckable(True)
    sort_time.setCheckable(True)
    sort_annotation.setCheckable(True)
    sort_name.setChecked(current_sort == "name")
    sort_time.setChecked(current_sort == "time")
    sort_annotation.setChecked(current_sort == "annotation")
    action = menu.exec(widget.file_list_widget.mapToGlobal(point))
    if action == copy_name_action:
        widget.copy_file_path(osp.basename(item.text()))
    elif action == copy_path_action:
        widget.copy_file_path(item.text())
    elif action == check_and_next_action:
        widget.file_list_widget.setCurrentItem(item)
        widget.load_file(item.text())
        widget.mark_checked_and_next()
    elif action == del_label_action:
        widget._delete_via_context(item, include_image=False)
    elif action == del_image_action:
        widget._delete_via_context(item, include_image=True)
    elif action in (sort_name, sort_time, sort_annotation):
        mode = {
            sort_name: "name",
            sort_time: "time",
            sort_annotation: "annotation",
        }[action]
        widget._file_sort_mode = mode
        widget._apply_file_sort()


def _create_file_list_item(widget, file, label_file, read_checked=True):
    item = QtWidgets.QListWidgetItem(file)
    flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
    if widget._config.get("file_list_checkbox_editable", False):
        flags |= Qt.ItemFlag.ItemIsUserCheckable
    item.setFlags(flags)
    has_annotation = QtCore.QFile.exists(
        label_file
    ) and LabelFile.is_label_file(label_file)
    item.setData(FILE_ANNOTATION_ROLE, bool(has_annotation))
    if widget._config.get("file_list_checkbox_editable", False):
        if has_annotation:
            item.setCheckState(Qt.CheckState.Checked)
        else:
            item.setCheckState(Qt.CheckState.Unchecked)
    # Reading the JSON is slow on large folders; batch callers pass
    # read_checked=False and let the background checker fill the dot.
    if read_checked:
        state, reviewed_at = label_file_review_info(label_file)
    else:
        state, reviewed_at = REVIEW_UNCHECKED, None
    item.setData(Qt.ItemDataRole.UserRole, state == REVIEW_CONFIRMED)
    item.setData(FILE_REVIEW_ROLE, state)
    item.setData(FILE_REVIEWED_AT_ROLE, reviewed_at)
    widget._refresh_file_item_status_icon(item)
    item.setToolTip(
        widget._file_item_tooltip(file, label_file, state, reviewed_at)
    )
    return item


def _on_file_item_changed(widget, item):
    """Keep annotation flag in sync when the checkbox is toggled.

    Note: QListWidgetItem.setData()/setIcon() emit itemChanged()
    unconditionally (even when the value is unchanged), so this slot
    MUST NOT mutate the item without a re-entrancy guard, otherwise a
    programmatic data/icon update during folder load recurses into
    itself until RecursionError crashes the app. Items that are not
    user-checkable have no checkbox to toggle, so we skip them too
    (their FILE_ANNOTATION_ROLE is owned by the loader).
    """
    if getattr(widget, "_syncing_file_item", False):
        return
    if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
        return
    widget._syncing_file_item = True
    try:
        item.setData(
            FILE_ANNOTATION_ROLE,
            item.checkState() == Qt.CheckState.Checked,
        )
        widget._refresh_file_item_status_icon(item)
        widget._refresh_file_progress()
    finally:
        widget._syncing_file_item = False


def get_label_file_list(widget):
    label_file_list = []
    if not widget.image_list and widget.filename:
        dir_path, filename = osp.split(widget.filename)
        label_file = osp.join(dir_path, osp.splitext(filename)[0] + ".json")
        if osp.exists(label_file):
            label_file_list = [label_file]
    elif widget.image_list and not widget.output_dir and widget.filename:
        file_list = os.listdir(osp.dirname(widget.filename))
        for file_name in file_list:
            if not file_name.endswith(".json"):
                continue
            label_file_list.append(
                osp.join(osp.dirname(widget.filename), file_name)
            )
    if widget.output_dir:
        for file_name in os.listdir(widget.output_dir):
            if not file_name.endswith(".json"):
                continue
            label_file_list.append(osp.join(widget.output_dir, file_name))
    return label_file_list


def _file_item_tooltip(
    widget,
    file,
    label_file,
    state,
    reviewed_at=None,
    counts=None,
    negative=False,
    low_conf=False,
):
    """Delegates to filelist.items."""
    return filelist_items.file_item_tooltip(
        widget,
        file,
        label_file,
        state,
        reviewed_at=reviewed_at,
        counts=counts,
        negative=negative,
        low_conf=low_conf,
    )


def update_thumbnail_pixmap(widget):
    if widget.thumbnail_pixmap and not widget.thumbnail_pixmap.isNull():
        width = widget.thumbnail_image_label.width()
        if width > 0:
            widget.thumbnail_image_label.setPixmap(
                widget.thumbnail_pixmap.scaledToWidth(
                    width,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                )
            )


def mark_file_item_negative_state(widget, image_file, negative):
    """Delegates to filelist.quality (batch auto-label flags negatives)."""
    widget.file_quality_controller.mark_file_item_negative_state(
        image_file, negative
    )


def _set_file_item_review_state(widget, item, state, reviewed_at=None):
    """Delegates to filelist.items (async checker & tests call this)."""
    return filelist_items.set_file_item_review_state(
        widget, item, state, reviewed_at
    )


def _current_file_item(widget):
    if str(widget.filename) not in widget.fn_to_index:
        return None
    return widget.file_list_widget.item(
        widget.fn_to_index[str(widget.filename)]
    )


def update_thumbnail_display(widget):
    widget.thumbnail_pixmap = None
    widget.thumbnail_image_label.clear()
    widget.thumbnail_container.hide()

    model_config = (
        widget.auto_labeling_widget.model_manager.loaded_model_config
    )
    supported_model_list = list(_THUMBNAIL_RENDER_MODELS.keys())
    if not (
        model_config
        and model_config.get("type") in supported_model_list
        and widget.image_list
    ):
        return

    try:
        image_dir = osp.dirname(widget.filename)
        parent_dir = osp.dirname(image_dir)
        base_name = osp.splitext(osp.basename(widget.filename))[0]
        save_dir, _thumbnail_file_ext = _THUMBNAIL_RENDER_MODELS[
            model_config["type"]
        ]
        thumbnail_dir = osp.join(parent_dir, save_dir)
        thumbnail_path = osp.join(
            thumbnail_dir, base_name + _thumbnail_file_ext
        )
        if not osp.exists(thumbnail_path):
            return

        widget.thumbnail_pixmap = QtGui.QPixmap(thumbnail_path)
        if not widget.thumbnail_pixmap.isNull():
            widget.thumbnail_container.show()
            widget.update_thumbnail_pixmap()

    except Exception as e:
        logger.error(f"Failed to load thumbnail image: {str(e)}")


def _set_file_item_checked(widget, item, checked):
    state = REVIEW_CONFIRMED if checked else REVIEW_UNCHECKED
    return widget._set_file_item_review_state(item, state)


def _update_current_file_tooltip(widget):
    """Give the open row the counts that only the canvas knows."""
    item = widget._current_file_item()
    if item is None or not widget.filename:
        return
    shapes = widget.canvas.shapes or []
    counts = {
        "total": len(shapes),
        "model": 0,
        "human": 0,
        "unknown": 0,
    }
    for shape in shapes:
        source = get_source(shape)
        if source == SOURCE_MODEL:
            counts["model"] += 1
        elif source == SOURCE_HUMAN:
            counts["human"] += 1
        else:
            counts["unknown"] += 1
    state = widget._current_review_state()
    item.setToolTip(
        widget._file_item_tooltip(
            widget.filename,
            widget._label_path_for_image(widget.filename),
            state,
            widget.other_data.get("reviewed_at"),
            counts=counts,
        )
    )


def _note_save_quality(widget, shapes, file_item=None):
    """Delegates to filelist.quality (save path + attribute panel call)."""
    return widget.file_quality_controller.note_save_quality(shapes, file_item)
