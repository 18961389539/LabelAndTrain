"""Label editing: the label dialog flows and their list-item formatting.

Methods moved out of LabelingWidget by scripts/extract_method.py; the
class keeps thin stubs so wiring and tests stay. The module-level
helpers below were moved first because the moved methods reach them by
plain name -- the extraction script treats them as module locals here.
"""

import html
from anylabeling.services.auto_labeling.types import AutoLabelingMode
import os.path as osp
from ..utils.yolo_detect import (
    CLASSES_FILENAME,
    load_class_names,
    merge_class_names,
    rename_label_across_folder,
    write_yolo_detect_sidecar,
)
from ....config import get_config, save_config
from PyQt6.QtCore import QCoreApplication, Qt, pyqtSlot
from ..utils.qt import measure_text_width as _measure_text_width
from PyQt6 import QtCore, QtGui, QtWidgets
from ..widgets import (
    AutoLabelingWidget,
    BrightnessContrastDialog,
    Canvas,
    CanvasAdjustmentWidget,
    CanvasEmptyStateWidget,
    CrosshairSettingsDialog,
    FileDialogPreview,
    FloatingToolPanel,
    ShapeModifyDialog,
    GroupIDFilterComboBox,
    LabelDialog,
    LabelFilterComboBox,
    LabelListWidget,
    LabelListWidgetItem,
    LabelModifyDialog,
    GroupIDModifyDialog,
    OverviewDialog,
    Popup,
    copy_text_to_system_clipboard,
    SearchBar,
    ToolBar,
    UniqueLabelQListWidget,
    ZoomWidget,
    NavigatorDialog,
)

# Whole-image class suggestions from a classification model. Deliberately not
# shapes: a suggestion becomes an annotation only when a human confirms it.
LABEL_OPACITY = 128


def _format_label_list_text(label, group_id):
    text = html.escape("" if label is None else str(label))
    if group_id is None:
        return text
    return f"{text} ({group_id})"


def _shape_editable_state(shape):
    """Fields edited by the label dialog, as one comparable tuple.

    Used to decide whether a label edit actually changed anything. Qt emits
    change signals even when the value is identical, and an unchanged edit
    must not consume an undo slot or invalidate the redo branch.
    """
    return (
        shape.label,
        shape.flags,
        shape.group_id,
        shape.description,
        shape.difficult,
        shape.kie_linking,
    )


def _find_next_label_loop_shape(shapes, start_index, canvas_shapes):
    canvas_shape_ids = {id(shape) for shape in canvas_shapes}
    for index in range(start_index, len(shapes)):
        shape = shapes[index]
        if id(shape) in canvas_shape_ids:
            return index, shape
    return len(shapes), None


def edit_label(widget, item=None):
    if item and not isinstance(item, LabelListWidgetItem):
        raise TypeError("item must be LabelListWidgetItem type")

    if not widget.canvas.editing():
        return

    selected_shapes = widget.canvas.selected_shapes
    if not selected_shapes:
        return

    if len(selected_shapes) > 1:
        return widget.batch_edit_labels(selected_shapes)

    if not item:
        item = widget.current_item()
    if item is None:
        return
    shape = item.shape()
    if shape is None:
        return
    (
        text,
        flags,
        group_id,
        description,
        difficult,
        kie_linking,
    ) = widget.label_dialog.pop_up(
        text=shape.label,
        flags=shape.flags,
        group_id=shape.group_id,
        description=shape.description,
        difficult=shape.difficult,
        kie_linking=shape.kie_linking,
        move_mode=widget._config.get("move_mode", "auto"),
    )
    if text is None:
        return
    if not widget.validate_label(text):
        widget.error_message(
            QCoreApplication.translate("LabelingWidget", "Invalid label"),
            QCoreApplication.translate(
                "LabelingWidget",
                "Invalid label '{}' with validation type '{}'",
            ).format(text, widget._config["validate_label"]),
        )
        return
    if widget.attributes and text and text != shape.label:
        text = widget.reset_attribute(text, shape)
    state_before = _shape_editable_state(shape)
    shape.label = text
    shape.flags = flags
    shape.group_id = group_id
    shape.description = description
    shape.difficult = difficult
    shape.kie_linking = kie_linking

    # Add to label history
    widget.label_dialog.add_label_history(shape.label)

    # Update last group_id
    if group_id is not None:
        widget.label_dialog._last_gid = group_id

    # Update unique label list
    if not widget.unique_label_list.find_items_by_label(shape.label):
        unique_label_item = widget.unique_label_list.create_item_from_label(
            shape.label
        )
        widget.unique_label_list.addItem(unique_label_item)
        rgb = widget._get_rgb_by_label(shape.label)
        widget.unique_label_list.set_item_label(
            unique_label_item, shape.label, rgb, LABEL_OPACITY
        )

    widget._update_shape_color(shape)
    if shape.group_id is None:
        color = shape.fill_color.getRgb()[:3]
        item.setText(_format_label_list_text(shape.label, shape.group_id))
        item.setBackground(QtGui.QColor(*color, LABEL_OPACITY))
    else:
        item.setText(_format_label_list_text(shape.label, shape.group_id))
    # The canvas saves the state AFTER each edit (see
    # Canvas.is_shape_restorable), so the snapshot has to happen here --
    # after the new values are in place. Without it a mistaken label was
    # permanent: edit_label only marked the file dirty.
    if state_before != _shape_editable_state(shape):
        widget.canvas.store_shapes()
    widget.set_dirty()
    widget._refresh_shape_filters()

    # update top-right attributes panel
    selected_idx = widget.canvas.shapes.index(selected_shapes[0])
    widget.update_attributes(selected_idx)


def batch_edit_labels(widget, shapes):
    if not widget._batch_edit_warning_shown:
        reply = QtWidgets.QMessageBox.question(
            widget,
            QCoreApplication.translate("LabelingWidget", "Batch Edit"),
            QCoreApplication.translate(
                "LabelingWidget",
                "You are about to edit multiple shapes in batch mode. "
                "You can undo this with Ctrl+Z.\n\n"
                "This warning will only be shown once. Do you want to continue?",
            ),
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )

        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        widget._batch_edit_warning_shown = True

    first_shape = shapes[0]
    result = widget.label_dialog.pop_up(
        text=first_shape.label,
        flags=first_shape.flags,
        group_id=first_shape.group_id,
        description=first_shape.description,
        difficult=first_shape.difficult,
        kie_linking=first_shape.kie_linking,
        move_mode="center",
    )

    if result[0] is None:
        return

    text, flags, group_id, description, difficult, kie_linking = result

    if not widget.validate_label(text):
        widget.error_message(
            QCoreApplication.translate("LabelingWidget", "Invalid label"),
            QCoreApplication.translate(
                "LabelingWidget",
                "Invalid label '{}' with validation type '{}'",
            ).format(text, widget._config["validate_label"]),
        )
        return

    states_before = [_shape_editable_state(shape) for shape in shapes]
    for shape in shapes:
        if widget.attributes and text and text != shape.label:
            text = widget.reset_attribute(text, shape)

        shape.label = text
        shape.flags = flags
        shape.group_id = group_id
        shape.description = description
        shape.difficult = difficult
        shape.kie_linking = kie_linking

        widget._update_shape_color(shape)

        item = widget.label_list.find_item_by_shape(shape)
        if item is not None:
            if shape.group_id is None:
                color = shape.fill_color.getRgb()[:3]
                item.setText(
                    _format_label_list_text(shape.label, shape.group_id)
                )
                item.setBackground(QtGui.QColor(*color, LABEL_OPACITY))
            else:
                item.setText(
                    _format_label_list_text(shape.label, shape.group_id)
                )

    widget.label_dialog.add_label_history(text)

    if not widget.unique_label_list.find_items_by_label(text):
        unique_label_item = widget.unique_label_list.create_item_from_label(
            text
        )
        widget.unique_label_list.addItem(unique_label_item)
        rgb = widget._get_rgb_by_label(text)
        widget.unique_label_list.set_item_label(
            unique_label_item, text, rgb, LABEL_OPACITY
        )

    # The confirmation dialog promises "You can undo this with Ctrl+Z";
    # keep that promise by snapshotting the new state (see
    # Canvas.is_shape_restorable for why this happens after the edit).
    if any(
        before != _shape_editable_state(shape)
        for before, shape in zip(states_before, shapes)
    ):
        widget.canvas.store_shapes()
    widget.set_dirty()
    widget._refresh_shape_filters()


def loop_thru_labels(widget):
    is_new_loop = widget.label_loop_shapes is None
    if is_new_loop:
        widget.label_loop_shapes = list(widget.canvas.shapes)

    widget.label_loop_count, shape = _find_next_label_loop_shape(
        widget.label_loop_shapes,
        widget.label_loop_count + 1,
        widget.canvas.shapes,
    )
    if shape is None:
        message = (
            QCoreApplication.translate(
                "LabelingWidget", "No objects to review"
            )
            if is_new_loop
            else QCoreApplication.translate(
                "LabelingWidget", "Review complete"
            )
        )
        widget._reset_label_loop()
        if not is_new_loop:
            widget.canvas.deselect_shape()
            widget.set_zoom(int(100 * widget.scale_fit_window()))
        widget._show_label_loop_popup(message)
        return

    width = widget.central_widget().width() - 2.0
    height = widget.central_widget().height() - 2.0

    im_width = widget.canvas.pixmap.width()
    im_height = widget.canvas.pixmap.height()

    zoom_scale = 4

    xs = []
    ys = []
    # loop through all points on this label
    for point in shape.points:
        xs.append(point.x())
        ys.append(point.y())

    # Set minimum label width to 30px this should handle point
    # labels and very tiny labels gracefully
    label_width = max(int(max(xs) - min(xs)), 30)
    x = (max(xs) + min(xs)) / 2
    y = (max(ys) + min(ys)) / 2

    zoom = int(100 * width / (zoom_scale * label_width))
    # Don't go past the max zoom which is 1000
    zoom = min(1000, zoom)

    widget.set_zoom(zoom)

    x_range = widget.scroll_bars[Qt.Orientation.Horizontal].maximum()
    x_step = widget.scroll_bars[Qt.Orientation.Horizontal].pageStep()

    y_range = widget.scroll_bars[Qt.Orientation.Vertical].maximum()
    # QT docs says Document length = maximum() - minimum() + pageStep().
    # so there's a weird pageStep thing we gotta add
    y_step = widget.scroll_bars[Qt.Orientation.Vertical].pageStep()
    screen_width = width / (zoom / 100)
    # add half a screen to this
    x_scroll = int((x - screen_width / 2) / im_width * (x_range + x_step))
    x_scroll = min(max(0, x_scroll), x_range)

    screen_height = height / (zoom / 100)

    y_scroll = int((y - screen_height / 2) / (im_height) * (y_range + y_step))
    y_scroll = min(max(0, y_scroll), y_range)

    widget.set_scroll(Qt.Orientation.Horizontal, x_scroll)
    widget.set_scroll(Qt.Orientation.Vertical, y_scroll)
    widget.canvas.prev_h_shape = widget.canvas.h_shape = shape
    widget.canvas.select_shapes([shape])

    progress = QCoreApplication.translate(
        "LabelingWidget", "Reviewing {current} / {total}"
    ).format(
        current=widget.label_loop_count + 1,
        total=len(widget.label_loop_shapes),
    )
    font_metrics = widget.fontMetrics()
    label_width = min(
        240,
        max(
            0,
            widget.central_widget().viewport().width()
            - _measure_text_width(font_metrics, progress)
            - 56,
        ),
    )
    label = font_metrics.elidedText(
        str(shape.label or ""), Qt.TextElideMode.ElideRight, label_width
    )
    if label:
        progress = f"{progress} - {label}"
    widget._show_label_loop_popup(progress)


def _apply_unique_label_rename(  # noqa: C901
    widget, old_label, new_label
):  # noqa: C901 -- moved as-is
    if widget.canvas.shapes:
        widget.canvas.store_shapes()

    old_items = widget.unique_label_list.find_items_by_label(old_label)
    new_items = widget.unique_label_list.find_items_by_label(new_label)
    if new_items:
        for old_item in old_items:
            row = widget.unique_label_list.row(old_item)
            if row >= 0:
                widget.unique_label_list.takeItem(row)
    else:
        for old_item in old_items:
            old_item.setData(Qt.ItemDataRole.UserRole, new_label)
            rgb = widget._get_rgb_by_label(new_label)
            widget.unique_label_list.set_item_label(
                old_item, new_label, rgb, LABEL_OPACITY
            )

    if old_label in widget.label_info:
        info = widget.label_info.pop(old_label)
        if new_label not in widget.label_info:
            info["value"] = None
            widget.label_info[new_label] = info

    renamed = 0
    for shape in widget.canvas.shapes:
        if shape.label != old_label:
            continue
        shape.label = new_label
        widget._update_shape_color(shape)
        renamed += 1
        list_item = widget.label_list.find_item_by_shape(shape)
        if list_item is not None:
            list_item.setText(
                _format_label_list_text(shape.label, shape.group_id)
            )
            color = shape.fill_color.getRgb()[:3]
            list_item.setBackground(QtGui.QColor(*color, LABEL_OPACITY))

    widget.label_dialog.remove_label_history(old_label)
    widget.label_dialog.add_label_history(new_label)

    labels = list(widget._config.get("labels") or [])
    if old_label in labels:
        labels = [new_label if name == old_label else name for name in labels]
    elif new_label not in labels:
        labels.append(new_label)
    seen = set()
    unique_labels = []
    for name in labels:
        if name in seen:
            continue
        seen.add(name)
        unique_labels.append(name)
    widget._config["labels"] = unique_labels
    save_config(widget._config)

    folder_changed = 0
    label_dir = widget.output_dir
    if not label_dir and widget.filename:
        label_dir = osp.dirname(widget.filename)
    if label_dir:
        paths = list(widget.image_list or [])
        if widget.filename and widget.filename not in paths:
            paths = [widget.filename, *paths]
        folder_changed = rename_label_across_folder(
            paths,
            label_dir,
            old_label,
            new_label,
            extra_class_names=widget._yolo_class_names(),
        )

    widget.canvas.update()
    widget._refresh_shape_filters()
    widget._refresh_label_panel()
    widget.set_dirty()
    status = (
        QCoreApplication.translate("LabelingWidget", "已将 %1 改为 %2")
        .replace("%1", old_label)
        .replace("%2", new_label)
    )
    if renamed:
        status += f" ({renamed})"
    if folder_changed:
        status += QCoreApplication.translate(
            "LabelingWidget", " · 文件夹 %1 个文件"
        ).replace("%1", str(folder_changed))
    widget.status(status)


def finish_auto_labeling_object(widget):
    """Finish auto labeling object."""
    has_object, cache_label = False, None
    for shape in widget.canvas.shapes:
        if shape.label == AutoLabelingMode.OBJECT:
            cache_label = shape.cache_label
            cache_description = shape.cache_description
            has_object = True
            break

    # If there is no object, do nothing
    if not has_object:
        return

    # Ask a label for the object
    text, flags, group_id, description, difficult, kie_linking = (
        "",
        {},
        None,
        None,
        False,
        [],
    )
    last_label = widget.find_last_label()
    last_gid = (
        widget.find_last_gid() if widget._config["auto_use_last_gid"] else None
    )
    if widget._config["auto_use_last_label"] and last_label:
        text = last_label
        if last_gid is not None:
            group_id = last_gid
    elif cache_label is not None:
        text = cache_label
        description = cache_description
    else:
        previous_text = widget.label_dialog.edit.text()
        (
            text,
            flags,
            group_id,
            description,
            difficult,
            kie_linking,
        ) = widget.label_dialog.pop_up(
            text=widget.find_last_label(),
            flags={},
            group_id=last_gid,
            description=None,
            difficult=False,
            kie_linking=[],
            move_mode=widget._config.get("move_mode", "auto"),
        )
        if not text:
            widget.label_dialog.edit.setText(previous_text)
            return

    widget.cache_auto_label = text
    widget.cache_auto_label_group_id = group_id
    if not widget.validate_label(text):
        widget.error_message(
            QCoreApplication.translate("LabelingWidget", "Invalid label"),
            QCoreApplication.translate(
                "LabelingWidget",
                "Invalid label '{}' with validation type '{}'",
            ).format(text, widget._config["validate_label"]),
        )
        return

    if widget.attributes and text:
        text = widget.reset_attribute(text, shape)

    # Add to label history
    widget.label_dialog.add_label_history(text)

    # Update label for the object
    updated_shapes = False
    for shape in widget.canvas.shapes:
        if shape.label == AutoLabelingMode.OBJECT:
            updated_shapes = True
            shape.label = text
            shape.flags = flags
            shape.group_id = group_id
            shape.description = description
            shape.difficult = difficult
            shape.kie_linking = kie_linking
            # Update unique label list
            if not widget.unique_label_list.find_items_by_label(shape.label):
                unique_label_item = (
                    widget.unique_label_list.create_item_from_label(
                        shape.label
                    )
                )
                widget.unique_label_list.addItem(unique_label_item)
                rgb = widget._get_rgb_by_label(shape.label)
                widget.unique_label_list.set_item_label(
                    unique_label_item, shape.label, rgb, LABEL_OPACITY
                )

            # Update label list
            widget._update_shape_color(shape)
            item = widget.label_list.find_item_by_shape(shape)
            if shape.group_id is None:
                color = shape.fill_color.getRgb()[:3]
                item.setText(
                    '{} <font color="#{:02x}{:02x}{:02x}">●</font>'.format(
                        html.escape(shape.label), *color
                    )
                )
            else:
                item.setText(
                    _format_label_list_text(shape.label, shape.group_id)
                )

    # Clean up auto labeling objects
    widget.clear_auto_labeling_marks()

    # Update shape colors
    for shape in widget.canvas.shapes:
        widget._update_shape_color(shape)
        color = shape.fill_color.getRgb()[:3]
        item = widget.label_list.find_item_by_shape(shape)
        item.setText(_format_label_list_text(shape.label, shape.group_id))
        item.setBackground(QtGui.QColor(*color, LABEL_OPACITY))
        widget.unique_label_list.update_item_color(
            shape.label, color, LABEL_OPACITY
        )

    if updated_shapes:
        widget.set_dirty()


def new_shape(widget):
    """Pop-up and give focus to the label editor.

    position MUST be in global coordinates.
    """
    items = widget.unique_label_list.selectedItems()
    text = None
    if items:
        text = items[0].data(Qt.ItemDataRole.UserRole)
    flags = {}
    group_id = None
    description = ""
    difficult = False
    kie_linking = []

    if widget.canvas.shapes[-1].label in [
        AutoLabelingMode.ADD,
        AutoLabelingMode.REMOVE,
    ]:
        text = widget.canvas.shapes[-1].label
    elif (
        widget._config["display_label_popup"]
        or not text
        or widget.canvas.shapes[-1].label == AutoLabelingMode.OBJECT
    ):
        last_label = widget.find_last_label()
        last_gid = (
            widget.find_last_gid()
            if widget._config["auto_use_last_gid"]
            else None
        )
        if widget.digit_to_label is not None:
            text = widget.digit_to_label
            widget.digit_to_label = None
            if last_gid is not None:
                group_id = last_gid
        elif widget._config["auto_use_last_label"] and last_label:
            text = last_label
            if last_gid is not None:
                group_id = last_gid
        else:
            previous_text = widget.label_dialog.edit.text()
            (
                text,
                flags,
                group_id,
                description,
                difficult,
                kie_linking,
            ) = widget.label_dialog.pop_up(
                text,
                group_id=last_gid,
                move_mode=widget._config.get("move_mode", "auto"),
            )
            if not text:
                widget.label_dialog.edit.setText(previous_text)

    if text and not widget.validate_label(text):
        widget.error_message(
            QCoreApplication.translate("LabelingWidget", "Invalid label"),
            QCoreApplication.translate(
                "LabelingWidget",
                "Invalid label '{}' with validation type '{}'",
            ).format(text, widget._config["validate_label"]),
        )
        text = ""
        return

    if widget.attributes and text:
        text = widget.reset_attribute(text, widget.canvas.shapes[-1])

    if text:
        widget.label_list.clearSelection()
        shape = widget.canvas.set_last_label(text, flags, group_id)
        shape.group_id = group_id
        shape.description = description
        if text not in [AutoLabelingMode.ADD, AutoLabelingMode.REMOVE]:
            shape.label = text
        shape.difficult = difficult
        shape.kie_linking = kie_linking
        widget.add_label(shape)
        widget.actions.edit_mode.setEnabled(True)
        widget.actions.undo_last_point.setEnabled(False)
        widget.actions.undo.setEnabled(True)
        widget.set_dirty()
        if (
            widget.canvas.drawing()
            and widget.canvas.create_mode == "polygon"
            and not widget.actions.create_brush_polygon_mode.isEnabled()
        ):
            widget.canvas._brush_drawing = True

        if widget.attributes and text in widget.attributes:
            shape.selected = True
            widget.shape_attributes.show()
            widget.scroll_area.show()
            for i, canvas_shape in enumerate(widget.canvas.shapes):
                if canvas_shape is shape:
                    widget.update_attributes(i)
                    break
    else:
        widget.canvas.undo_last_line()
        widget.canvas.shapes_backups.pop()
