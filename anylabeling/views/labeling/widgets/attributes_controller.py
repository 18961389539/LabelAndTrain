"""Attribute-panel behaviour, carved out of label_widget.

Owns building the per-shape attribute editor grid (combo boxes, radio rows
with width-aware wrapping, line edits), persisting attributes through the
standard label-file serialization, and syncing the edit actions with the
canvas selection. The widget keeps thin delegates so the menu wiring and
the unbound-call test style (``LabelingWidget.update_attributes(stub, 0)``)
stay untouched.

Functions take the widget as their first argument, per the house
convention for migrated behaviour: light test stubs can call them without
constructing a real widget.
"""

import os
import os.path as osp

from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from anylabeling.services.auto_labeling.types import AutoLabelingMode

from ..filelist.roles import CHECKED_FIELD
from ..label_file import LabelFile, LabelFileError
from ..utils.qt import measure_text_width as _measure_text_width


def measure_text_width(font_metrics, text):
    if hasattr(font_metrics, "horizontalAdvance"):
        return font_metrics.horizontalAdvance(text)
    return font_metrics.width(text)


def update_attributes(widget, shape_index):
    if shape_index >= len(widget.canvas.shapes) or shape_index < 0:
        widget.hide_attributes_panel()
        return

    update_shape = widget.canvas.shapes[shape_index]
    update_category = update_shape.label
    if update_category not in widget.attributes:
        widget.hide_attributes_panel()
        return

    current_attibute = widget.attributes[update_category]
    if not update_shape.attributes:
        update_shape.attributes = {}
    attributes_changed = False

    widget.grid_layout = QGridLayout()
    row_counter = 0

    def unknown_value_tooltip(value):
        return widget.tr(
            "Value '{}' is not defined in the current attribute "
            "configuration."
        ).format(value)

    def set_current_combo_value(combo, value):
        value = str(value)
        index = combo.findText(value)
        if index < 0:
            combo.addItem(value)
            index = combo.count() - 1
            tooltip = unknown_value_tooltip(value)
            combo.setItemData(index, tooltip, Qt.ItemDataRole.ToolTipRole)
            combo.setToolTip(tooltip)
        combo.setCurrentIndex(index)

    for property, options in current_attibute.items():
        widget_type = widget.attribute_widget_types.get(
            update_category, {}
        ).get(property, "combobox")
        has_current_value = property in update_shape.attributes
        current_value = update_shape.attributes.get(property)
        current_value_text = (
            str(current_value) if has_current_value else None
        )
        if hasattr(widget, "grid_layout_container"):
            font_metrics = QFontMetrics(widget.grid_layout_container.font())
        else:
            font_metrics = QFontMetrics(QLabel().font())
        available_width = widget.scroll_area.width() - 30
        property_display = property
        if _measure_text_width(font_metrics, property) > available_width:
            while (
                _measure_text_width(font_metrics, property_display + "...")
                > available_width
                and len(property_display) > 1
            ):
                property_display = property_display[:-1]
            property_display += "..."

        property_label = QLabel(property_display)
        if property_display != property:
            property_label.setToolTip(property)

        widget.grid_layout.addWidget(property_label, row_counter, 0, 1, 2)
        row_counter += 1

        if widget_type == "radiobutton":
            radio_options = list(options)
            unknown_radio_value = None
            if (
                has_current_value
                and current_value_text not in radio_options
            ):
                unknown_radio_value = current_value_text
                radio_options.append(unknown_radio_value)
            radio_container = QWidget()
            radio_group = QButtonGroup(radio_container)
            main_layout = QVBoxLayout()
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(2)

            def get_truncated_text(text, max_width):
                if _measure_text_width(font_metrics, text) <= max_width:
                    return text, text
                truncated = text
                while (
                    _measure_text_width(font_metrics, truncated + "...")
                    > max_width
                    and len(truncated) > 1
                ):
                    truncated = truncated[:-1]
                return truncated + "...", text

            def get_button_width(text):
                return _measure_text_width(font_metrics, text) + 30

            def create_radio_button_with_handler(
                display_text, original_text, prop, shape_idx
            ):
                radio_button = QRadioButton(display_text)
                if original_text == unknown_radio_value:
                    radio_button.setToolTip(
                        unknown_value_tooltip(original_text)
                    )
                elif display_text != original_text:
                    radio_button.setToolTip(original_text)
                radio_group.addButton(radio_button)

                def handler(checked):
                    if checked:
                        widget.attribute_radio_changed(
                            shape_idx, prop, original_text, checked
                        )

                radio_button.toggled.connect(handler)
                return radio_button

            buttons_data = []
            for option in radio_options:
                display_text, original_text = get_truncated_text(
                    option, available_width
                )
                button_width = get_button_width(display_text)
                buttons_data.append(
                    (display_text, original_text, button_width)
                )

            current_row_buttons = []
            current_row_width = 0

            idx = 0
            while idx < len(buttons_data):
                display_text, original_text, button_width = buttons_data[
                    idx
                ]

                if not current_row_buttons:
                    current_row_buttons.append(
                        (display_text, original_text)
                    )
                    current_row_width = button_width
                    idx += 1
                    continue

                if current_row_width + button_width <= available_width:
                    current_row_buttons.append(
                        (display_text, original_text)
                    )
                    current_row_width += button_width
                    idx += 1
                else:
                    if len(current_row_buttons) == 1:
                        (
                            first_display,
                            first_original,
                        ) = current_row_buttons[0]
                        first_truncated, _ = get_truncated_text(
                            first_original, available_width - button_width
                        )
                        first_truncated_width = get_button_width(
                            first_truncated
                        )

                        if (
                            first_truncated_width + button_width
                            <= available_width
                        ):
                            current_row_buttons = [
                                (first_truncated, first_original),
                                (display_text, original_text),
                            ]
                            current_row_width = (
                                first_truncated_width + button_width
                            )
                            idx += 1
                        else:
                            row_layout = QHBoxLayout()
                            row_layout.setContentsMargins(0, 0, 0, 0)
                            row_layout.setSpacing(4)

                            for (
                                btn_display,
                                btn_original,
                            ) in current_row_buttons:
                                radio_button = (
                                    create_radio_button_with_handler(
                                        btn_display,
                                        btn_original,
                                        property,
                                        shape_index,
                                    )
                                )
                                row_layout.addWidget(radio_button)
                                if current_value_text == btn_original or (
                                    not has_current_value
                                    and btn_original == options[0]
                                ):
                                    blocker = QtCore.QSignalBlocker(
                                        radio_button
                                    )
                                    radio_button.setChecked(True)
                                    del blocker
                                    if not has_current_value:
                                        update_shape.attributes[
                                            property
                                        ] = btn_original
                                        attributes_changed = True

                            row_layout.addStretch()
                            row_widget = QWidget()
                            row_widget.setLayout(row_layout)
                            main_layout.addWidget(row_widget)

                            current_row_buttons = []
                            current_row_width = 0
                            continue
                    else:
                        row_layout = QHBoxLayout()
                        row_layout.setContentsMargins(0, 0, 0, 0)
                        row_layout.setSpacing(4)
                        for (
                            btn_display,
                            btn_original,
                        ) in current_row_buttons:
                            radio_button = (
                                create_radio_button_with_handler(
                                    btn_display,
                                    btn_original,
                                    property,
                                    shape_index,
                                )
                            )
                            row_layout.addWidget(radio_button)
                            if current_value_text == btn_original or (
                                not has_current_value
                                and btn_original == options[0]
                            ):
                                blocker = QtCore.QSignalBlocker(
                                    radio_button
                                )
                                radio_button.setChecked(True)
                                del blocker
                                if not has_current_value:
                                    update_shape.attributes[property] = (
                                        btn_original
                                    )
                                    attributes_changed = True

                        row_layout.addStretch()
                        row_widget = QWidget()
                        row_widget.setLayout(row_layout)
                        main_layout.addWidget(row_widget)

                        current_row_buttons = []
                        current_row_width = 0
                        continue

            if current_row_buttons:
                row_layout = QHBoxLayout()
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(4)
                for btn_display, btn_original in current_row_buttons:
                    radio_button = create_radio_button_with_handler(
                        btn_display, btn_original, property, shape_index
                    )
                    row_layout.addWidget(radio_button)
                    if current_value_text == btn_original or (
                        not has_current_value
                        and btn_original == options[0]
                    ):
                        blocker = QtCore.QSignalBlocker(radio_button)
                        radio_button.setChecked(True)
                        del blocker
                        if not has_current_value:
                            update_shape.attributes[property] = (
                                btn_original
                            )
                            attributes_changed = True
                row_layout.addStretch()
                row_widget = QWidget()
                row_widget.setLayout(row_layout)
                main_layout.addWidget(row_widget)

            radio_container.setLayout(main_layout)
            widget.grid_layout.addWidget(
                radio_container, row_counter, 0, 1, 2
            )
            row_counter += 1
        elif widget_type == "group_id":
            property_combo = QComboBox()
            options = [""] + sorted(
                {
                    str(obj.group_id)
                    for obj in widget.canvas.shapes
                    if obj.group_id is not None
                }
            )
            property_combo.addItems(options)
            if has_current_value:
                set_current_combo_value(property_combo, current_value)
            property_combo.currentIndexChanged.connect(
                lambda _, prop=property, combo=property_combo, shape_idx=shape_index: widget.attribute_selection_changed(
                    shape_idx, prop, combo
                )
            )
            widget.grid_layout.addWidget(
                property_combo, row_counter, 0, 1, 2
            )
            row_counter += 1
        elif widget_type == "lineedit":
            property_line = QLineEdit()
            if has_current_value:
                property_line.setText(current_value_text)
            property_line.textChanged.connect(
                lambda _, prop=property, line=property_line, shape_idx=shape_index: widget.attribute_line_changed(
                    shape_idx, prop, line
                )
            )
            widget.grid_layout.addWidget(property_line, row_counter, 0, 1, 2)
            row_counter += 1
        else:
            property_combo = QComboBox()
            property_combo.addItems(options)
            if has_current_value:
                set_current_combo_value(property_combo, current_value)
            else:
                update_shape.attributes[property] = options[0]
                attributes_changed = True
            property_combo.currentIndexChanged.connect(
                lambda _, prop=property, combo=property_combo, shape_idx=shape_index: widget.attribute_selection_changed(
                    shape_idx, prop, combo
                )
            )
            widget.grid_layout.addWidget(
                property_combo, row_counter, 0, 1, 2
            )
            row_counter += 1

    widget.grid_layout_container = QWidget()
    widget.grid_layout_container.setLayout(widget.grid_layout)
    widget.scroll_area.setWidget(widget.grid_layout_container)
    widget.scroll_area.setWidgetResizable(True)
    if shape_index < len(widget.canvas.shapes):
        widget.canvas.shapes[shape_index] = update_shape
        if attributes_changed:
            widget.save_attributes(widget.canvas.shapes)
    widget.show_attributes_panel()


def save_attributes(widget, _shapes):
    filename = osp.splitext(widget.image_path)[0] + ".json"
    if widget.output_dir:
        label_file_without_path = osp.basename(filename)
        filename = osp.join(widget.output_dir, label_file_without_path)
    label_file = LabelFile()

    # Get current shapes
    # Excluding auto labeling special shapes
    shapes = [
        shape.to_dict()
        for shape in _shapes
        if shape.label
        not in [
            AutoLabelingMode.OBJECT,
            AutoLabelingMode.ADD,
            AutoLabelingMode.REMOVE,
        ]
    ]
    flags = {}
    for i in range(widget.flag_widget.count()):
        item = widget.flag_widget.item(i)
        key = item.text()
        flag = item.checkState() == Qt.CheckState.Checked
        flags[key] = flag
    widget.other_data[CHECKED_FIELD] = widget._annotation_checked()
    try:
        image_path = osp.relpath(widget.image_path, osp.dirname(filename))
        image_data = (
            widget.image_data if widget._config["store_data"] else None
        )
        if osp.dirname(filename) and not osp.exists(osp.dirname(filename)):
            os.makedirs(osp.dirname(filename))
        label_file.save(
            filename=filename,
            shapes=shapes,
            image_path=image_path,
            image_data=image_data,
            image_height=widget.image.height(),
            image_width=widget.image.width(),
            other_data=widget.other_data,
            flags=flags,
        )
        write_sidecar = getattr(widget, "_write_yolo_sidecar", None)
        if write_sidecar is not None:
            write_sidecar(filename, shapes)
        widget.label_file = label_file
        items = widget.file_list_widget.findItems(
            widget.image_path, Qt.MatchFlag.MatchExactly
        )
        if len(items) > 0:
            if len(items) != 1:
                raise RuntimeError("There are duplicate files.")
            widget._set_file_item_annotated(
                items[0], True, negative=not shapes
            )
            widget._set_file_item_checked(
                items[0], widget._annotation_checked()
            )
            note_quality = getattr(widget, "_note_save_quality", None)
            if note_quality is not None:
                note_quality(shapes, items[0])
        else:
            note_quality = getattr(widget, "_note_save_quality", None)
            if note_quality is not None:
                note_quality(shapes)
        # Defensive refresh: tests may use a lightweight mock widget.
        refresh_progress = getattr(widget, "_refresh_file_progress", None)
        if refresh_progress is not None:
            refresh_progress()
        refresh_labels = getattr(widget, "_refresh_label_panel", None)
        if refresh_labels is not None:
            refresh_labels()
        # disable allows next and previous image to proceed
        # widget.filename = filename
        return True
    except LabelFileError as e:
        widget.error_message(
            widget.tr("Error saving label data"), widget.tr("<b>%s</b>") % e
        )
        return False


def shape_selection_changed(widget, selected_shapes):
    if widget.canvas.is_brush_mode:
        target = widget.canvas._brush_target_shape
        if selected_shapes != [target]:
            widget._no_selection_slot = True
            widget.label_list.clearSelection()
            item = widget.label_list.find_item_by_shape(target)
            if item is not None:
                widget.label_list.select_item(item)
                widget.label_list.scroll_to_item(item)
            widget._no_selection_slot = False
            return
    widget._no_selection_slot = True
    for shape in widget.canvas.selected_shapes:
        shape.selected = False
    widget.label_list.clearSelection()
    widget.canvas.selected_shapes = selected_shapes
    allow_merge_shape_type = {"rectangle": 0, "polygon": 0}
    for shape in widget.canvas.selected_shapes:
        shape.selected = True
        if shape.shape_type in ["rectangle", "polygon"]:
            allow_merge_shape_type[shape.shape_type] += 1
        item = widget.label_list.find_item_by_shape(shape)
        # NOTE: Handle the case when the shape is not found
        if item is not None:
            widget.label_list.select_item(item)
            widget.label_list.scroll_to_item(item)
    widget._no_selection_slot = False
    n_selected = len(selected_shapes)
    same_type = (
        len(set(shape.shape_type for shape in selected_shapes)) <= 1
    )
    has_locked = any(shape.locked for shape in selected_shapes)
    has_unlocked = any(not shape.locked for shape in selected_shapes)
    group_shapes = widget.canvas._active_group_shapes()
    widget.actions.delete.setEnabled(
        has_unlocked and not (group_shapes and has_locked)
    )
    widget.actions.duplicate.setEnabled(n_selected)
    widget.actions.copy.setEnabled(n_selected)
    widget.actions.edit.setEnabled(n_selected >= 1 and same_type)
    widget.actions.copy_coordinates.setEnabled(n_selected == 1)
    can_brush_edit = (
        n_selected == 1
        and selected_shapes[0].shape_type == "polygon"
        and not selected_shapes[0].locked
    )
    widget.actions.edit_brush_mode.setEnabled(can_brush_edit)
    widget.actions.union_selection.setEnabled(
        not has_locked
        and not all(value > 0 for value in allow_merge_shape_type.values())
        and (
            allow_merge_shape_type["rectangle"] > 1
            or allow_merge_shape_type["polygon"] > 1
        )
    )
    widget.refresh_shape_lock_action()

    selected_count = len(widget.canvas.selected_shapes)
    is_drawing_mode = (
        hasattr(widget.canvas, "current") and widget.canvas.current is not None
    )
    if widget.attributes and selected_count == 1 and not is_drawing_mode:
        for i in range(len(widget.canvas.shapes)):
            if widget.canvas.shapes[i].selected:
                widget.update_attributes(i)
                break
    else:
        widget.hide_attributes_panel()
