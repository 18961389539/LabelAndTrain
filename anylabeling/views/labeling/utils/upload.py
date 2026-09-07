import json
import jsonlines
import os
import os.path as osp
import time
import yaml

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QProgressDialog,
)

from anylabeling.views.labeling.label_converter import LabelConverter
from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.widgets import Popup
from anylabeling.views.labeling.utils.qt import new_icon_path
from anylabeling.views.labeling.utils.style import *
from anylabeling.views.labeling.utils.export import _check_filename_exist


class UploadCocoThread(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, converter, input_file, output_dir_path, mode):
        super().__init__()
        self.converter = converter
        self.input_file = input_file
        self.output_dir_path = output_dir_path
        self.mode = mode

    def run(self):
        try:
            time.sleep(1)

            self.converter.coco_to_custom(
                input_file=self.input_file,
                output_dir_path=self.output_dir_path,
                mode=self.mode,
            )

            self.finished.emit(True, "")

        except Exception as e:
            self.finished.emit(False, str(e))


def upload_coco_annotation(self, mode):
    if not _check_filename_exist(self):
        return

    filter = "Attribute Files (*.json);;All Files (*)"
    input_file, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        self.tr("Select a custom coco annotation file"),
        "",
        filter,
    )

    if not input_file:
        return

    output_dir_path = osp.dirname(self.filename)
    if self.output_dir:
        output_dir_path = self.output_dir

    response = QtWidgets.QMessageBox()
    response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    response.setWindowTitle(self.tr("Warning"))
    response.setText(self.tr("Current annotation will be lost"))
    response.setInformativeText(
        self.tr(
            "You are going to upload new annotations to this task. Continue?"
        )
    )
    response.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Cancel
        | QtWidgets.QMessageBox.StandardButton.Ok
    )
    response.setStyleSheet(get_msg_box_style())

    if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
        return

    progress_dialog = QProgressDialog(
        self.tr("Uploading..."), self.tr("Cancel"), 0, 0, self
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Progress"))
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setRange(0, 0)
    progress_dialog.setStyleSheet(get_progress_dialog_style())

    self.upload_thread = UploadCocoThread(
        LabelConverter(), input_file, output_dir_path, mode
    )

    def on_upload_finished(success, error_msg):
        progress_dialog.close()
        if success:
            # update and refresh the current canvas
            self.load_file(self.filename)

            popup = Popup(
                self.tr(f"Uploading annotations successfully!"),
                self,
                icon=new_icon_path("copy-green", "svg"),
            )
            popup.show_popup(self, popup_height=65, position="center")
        else:
            message = (
                f"Error occurred while uploading annotations: {str(error_msg)}"
            )
            logger.error(message)
            popup = Popup(
                message,
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, position="center")

    self.upload_thread.finished.connect(on_upload_finished)

    progress_dialog.show()
    self.upload_thread.start()

    progress_dialog.canceled.connect(self.upload_thread.terminate)


def upload_voc_annotation(self, mode):
    if not _check_filename_exist(self):
        return

    dialog = QtWidgets.QDialog(self)
    dialog.setWindowTitle(self.tr("Upload Options"))
    dialog.setMinimumWidth(500)
    dialog.setStyleSheet(get_export_option_style())

    layout = QVBoxLayout()
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    path_layout = QVBoxLayout()
    path_label = QtWidgets.QLabel(self.tr("Select Upload Folder"))
    path_layout.addWidget(path_label)

    path_input_layout = QHBoxLayout()
    path_input_layout.setSpacing(8)

    path_edit = QtWidgets.QLineEdit()
    path_edit.setText(osp.dirname(osp.dirname(self.filename)))

    def browse_upload_folder():
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("Select Upload Folder"),
            path_edit.text(),
            QtWidgets.QFileDialog.Option.ShowDirsOnly
            | QtWidgets.QFileDialog.Option.DontResolveSymlinks
            | QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            path_edit.setText(path)

    path_button = QtWidgets.QPushButton(self.tr("Browse"))
    path_button.clicked.connect(browse_upload_folder)
    path_button.setStyleSheet(get_cancel_btn_style())

    path_input_layout.addWidget(path_edit)
    path_input_layout.addWidget(path_button)
    path_layout.addLayout(path_input_layout)
    layout.addLayout(path_layout)

    button_layout = QHBoxLayout()
    button_layout.setContentsMargins(0, 16, 0, 0)
    button_layout.setSpacing(8)

    cancel_button = QtWidgets.QPushButton(self.tr("Cancel"))
    cancel_button.clicked.connect(dialog.reject)
    cancel_button.setStyleSheet(get_cancel_btn_style())

    ok_button = QtWidgets.QPushButton(self.tr("OK"))
    ok_button.clicked.connect(dialog.accept)
    ok_button.setStyleSheet(get_ok_btn_style())

    button_layout.addStretch()
    button_layout.addWidget(cancel_button)
    button_layout.addWidget(ok_button)
    layout.addLayout(button_layout)

    dialog.setLayout(layout)
    result = dialog.exec()

    if not result:
        return

    label_dir_path = path_edit.text()
    image_dir_path = osp.dirname(self.filename)
    label_file_list = os.listdir(label_dir_path)
    output_dir_path = self.output_dir if self.output_dir else image_dir_path
    converter = LabelConverter()

    response = QtWidgets.QMessageBox()
    response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    response.setWindowTitle(self.tr("Warning"))
    response.setText(self.tr("Current annotation will be lost"))
    response.setInformativeText(
        self.tr(
            "You are going to upload new annotations to this task. Continue?"
        )
    )
    response.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Cancel
        | QtWidgets.QMessageBox.StandardButton.Ok
    )
    response.setStyleSheet(get_msg_box_style())

    if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
        return

    image_list = self.image_list if self.image_list else [self.filename]
    progress_dialog = QProgressDialog(
        self.tr("Uploading..."), self.tr("Cancel"), 0, len(image_list), self
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Progress"))
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setStyleSheet(
        get_progress_dialog_style(color="#1d1d1f", height=20)
    )

    try:
        for i, image_path in enumerate(image_list):
            image_filename = osp.basename(image_path)
            label_filename = osp.splitext(image_filename)[0] + ".xml"
            if label_filename not in label_file_list:
                continue

            input_file = osp.join(label_dir_path, label_filename)
            output_file = osp.join(
                output_dir_path, osp.splitext(image_filename)[0] + ".json"
            )
            converter.voc_to_custom(
                input_file=input_file,
                output_file=output_file,
                image_filename=image_filename,
                mode=mode,
            )

            progress_dialog.setValue(i)
            if progress_dialog.wasCanceled():
                break

        progress_dialog.close()
        template = self.tr(
            "Uploading annotations successfully!\n"
            "Results have been saved to:\n"
            "%s"
        )
        message_text = template % output_dir_path
        popup = Popup(
            message_text,
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=65, position="center")

        # update and refresh the current canvas
        self.load_file(self.filename)

    except Exception as e:
        progress_dialog.close()
        message = f"Error occurred while uploading annotations: {str(e)}"
        logger.error(message)

        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def upload_yolo_annotation(self, mode, LABEL_OPACITY):
    if not _check_filename_exist(self):
        return

    if mode == "pose":
        filter = "Classes Files (*.yaml);;All Files (*)"
        self.yaml_file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("Select a specific yolo-pose config file"),
            "",
            filter,
        )
        if not self.yaml_file:
            return

        try:
            converter = LabelConverter(pose_cfg_file=self.yaml_file)
        except Exception as e:
            logger.error(f"Failed to load pose config: {self.yaml_file}: {e}")
            popup = Popup(
                self.tr("Invalid pose config file:\n%s") % str(e),
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, popup_height=65, position="center")
            return

        labels = []
        for class_name, keypoint_name in converter.pose_classes.items():
            labels.append(class_name)
            labels.extend(keypoint_name)

    elif mode in ["hbb", "seg"]:
        filter = "Classes Files (*.txt);;All Files (*)"
        self.classes_file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("Select a specific classes file"),
            "",
            filter,
        )
        if not self.classes_file:
            return

        with open(self.classes_file, "r", encoding="utf-8") as f:
            labels = f.read().splitlines()
        converter = LabelConverter(classes_file=self.classes_file)

    dialog = QtWidgets.QDialog(self)
    dialog.setWindowTitle(self.tr("Upload Options"))
    dialog.setMinimumWidth(500)
    dialog.setStyleSheet(get_export_option_style())

    layout = QVBoxLayout()
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    path_layout = QVBoxLayout()
    path_label = QtWidgets.QLabel(self.tr("Select Upload Folder"))
    path_layout.addWidget(path_label)

    path_input_layout = QHBoxLayout()
    path_input_layout.setSpacing(8)

    path_edit = QtWidgets.QLineEdit()
    path_edit.setText(osp.dirname(osp.dirname(self.filename)))

    def browse_upload_folder():
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("Select Upload Folder"),
            path_edit.text(),
            QtWidgets.QFileDialog.Option.ShowDirsOnly
            | QtWidgets.QFileDialog.Option.DontResolveSymlinks
            | QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            path_edit.setText(path)

    path_button = QtWidgets.QPushButton(self.tr("Browse"))
    path_button.clicked.connect(browse_upload_folder)
    path_button.setStyleSheet(get_cancel_btn_style())

    path_input_layout.addWidget(path_edit)
    path_input_layout.addWidget(path_button)
    path_layout.addLayout(path_input_layout)
    layout.addLayout(path_layout)

    preserve_checkbox = QtWidgets.QCheckBox(
        self.tr("Preserve existing annotations")
    )
    preserve_checkbox.setChecked(False)
    layout.addWidget(preserve_checkbox)

    button_layout = QHBoxLayout()
    button_layout.setContentsMargins(0, 16, 0, 0)
    button_layout.setSpacing(8)

    cancel_button = QtWidgets.QPushButton(self.tr("Cancel"))
    cancel_button.clicked.connect(dialog.reject)
    cancel_button.setStyleSheet(get_cancel_btn_style())

    ok_button = QtWidgets.QPushButton(self.tr("OK"))
    ok_button.clicked.connect(dialog.accept)
    ok_button.setStyleSheet(get_ok_btn_style())

    button_layout.addStretch()
    button_layout.addWidget(cancel_button)
    button_layout.addWidget(ok_button)
    layout.addLayout(button_layout)

    dialog.setLayout(layout)
    result = dialog.exec()

    if not result:
        return

    label_dir_path = path_edit.text()
    preserve_existing = preserve_checkbox.isChecked()
    image_dir_path = osp.dirname(self.filename)
    image_file_list = os.listdir(image_dir_path)
    label_file_list = os.listdir(label_dir_path)
    output_dir_path = self.output_dir if self.output_dir else image_dir_path

    response = QtWidgets.QMessageBox()
    response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    response.setWindowTitle(self.tr("Warning"))
    if preserve_existing:
        response.setText(
            self.tr("New annotations will be merged with existing ones")
        )
        response.setInformativeText(
            self.tr(
                "You are going to add new annotations to this task. Existing annotations will be preserved. Continue?"
            )
        )
    else:
        response.setText(self.tr("Current annotation will be lost"))
        response.setInformativeText(
            self.tr(
                "You are going to upload new annotations to this task. Continue?"
            )
        )
    response.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Cancel
        | QtWidgets.QMessageBox.StandardButton.Ok
    )
    response.setStyleSheet(get_msg_box_style())

    if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
        return

    progress_dialog = QProgressDialog(
        self.tr("Uploading..."),
        self.tr("Cancel"),
        0,
        len(image_file_list),
        self,
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Progress"))
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setStyleSheet(
        get_progress_dialog_style(color="#1d1d1f", height=20)
    )

    try:
        for i, image_filename in enumerate(image_file_list):
            if image_filename.endswith(".json"):
                continue
            label_filename = osp.splitext(image_filename)[0] + ".txt"
            data_filename = osp.splitext(image_filename)[0] + ".json"
            if label_filename not in label_file_list:
                continue
            input_file = osp.join(label_dir_path, label_filename)
            output_file = osp.join(output_dir_path, data_filename)
            image_file = osp.join(image_dir_path, image_filename)

            existing_shapes = []
            if preserve_existing and osp.exists(output_file):
                with open(output_file, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                    existing_shapes = existing_data.get("shapes", [])

            if mode in ["hbb", "seg"]:
                converter.yolo_to_custom(
                    input_file=input_file,
                    output_file=output_file,
                    image_file=image_file,
                    mode=mode,
                )
            elif mode == "pose":
                converter.yolo_pose_to_custom(
                    input_file=input_file,
                    output_file=output_file,
                    image_file=image_file,
                )

            # Merge with existing shapes if needed
            if preserve_existing and existing_shapes:
                with open(output_file, "r", encoding="utf-8") as f:
                    new_data = json.load(f)
                new_data["shapes"] = existing_shapes + new_data.get(
                    "shapes", []
                )
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(new_data, f, indent=2, ensure_ascii=False)

            progress_dialog.setValue(i)
            if progress_dialog.wasCanceled():
                break

        progress_dialog.close()
        self.load_file(self.filename)
        popup = Popup(
            self.tr("Upload completed successfully!"),
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, position="center")

        # Initialize unique labels
        for label in labels:
            if not self.unique_label_list.find_items_by_label(label):
                item = self.unique_label_list.create_item_from_label(label)
                self.unique_label_list.addItem(item)
                rgb = self._get_rgb_by_label(label)
                self.unique_label_list.set_item_label(
                    item, label, rgb, LABEL_OPACITY
                )

    except Exception as e:
        progress_dialog.close()
        message = f"Error occurred while uploading annotations: {str(e)}"
        logger.error(message)

        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def upload_label_classes_file(self):
    filter = "Label Files (*.txt);;All Files (*)"
    file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        self.tr("Select a specific label classes file"),
        "",
        filter,
    )
    if not file_path:
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            labels = [line.strip() for line in f.readlines()]

        if not labels:
            popup = Popup(
                self.tr("No labels found in the file!"),
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, position="center")
            return

        response = QtWidgets.QMessageBox()
        response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        response.setWindowTitle(self.tr("Warning"))
        response.setText(self.tr("Current labels will be lost"))
        response.setInformativeText(
            self.tr(
                "You are going to upload new labels to this task. Continue?"
            )
        )
        response.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Cancel
            | QtWidgets.QMessageBox.StandardButton.Ok
        )
        response.setStyleSheet(get_msg_box_style())

        if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
            return

        # Update unique_label_list
        self.unique_label_list.clear()
        self.load_labels(labels)

        # Update label_dialog.label_list
        self.label_dialog.label_list.clear()
        self.label_dialog.label_list.addItems(labels)
        if self.label_dialog._sort_labels:
            self.label_dialog.sort_labels()

        popup = Popup(
            self.tr(f"Successfully loaded {len(set(labels))} labels!"),
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, position="center")

    except Exception as e:
        message = (
            f"Error occurred while uploading label classes file: {str(e)}"
        )
        logger.error(message)

        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def validate_shape_attributes_config(attributes_data):
    """
    Validates and separates a shape attributes configuration.

    Args:
        attributes_data (dict): Parsed shape attributes configuration.

    Returns:
        tuple: Attribute definitions and widget type mappings.

    Raises:
        ValueError: If the configuration structure is invalid.
    """

    def invalid(label, property_name, widget_type, value, expected):
        raise ValueError(
            "Invalid shape attribute configuration: "
            f"label={label!r}, property={property_name!r}, "
            f"widget_type={widget_type!r}, "
            f"actual_type={type(value).__name__!r}, "
            f"expected={expected!r}"
        )

    if not isinstance(attributes_data, dict):
        invalid(
            "<root>",
            "<root>",
            "<none>",
            attributes_data,
            "a dictionary",
        )

    attributes = {
        label: properties
        for label, properties in attributes_data.items()
        if not label.startswith("__")
    }
    for label, properties in attributes.items():
        if not isinstance(properties, dict):
            invalid(
                label,
                "<all>",
                "<unknown>",
                properties,
                "a dictionary of attribute definitions",
            )

    widget_types = attributes_data.get("__widget_types__", {})
    if not isinstance(widget_types, dict):
        invalid(
            "__widget_types__",
            "<all>",
            "<mapping>",
            widget_types,
            "a dictionary of label widget mappings",
        )

    supported_widget_types = {
        "combobox",
        "radiobutton",
        "group_id",
        "lineedit",
    }
    for label, property_types in widget_types.items():
        if label not in attributes:
            invalid(
                label,
                "<all>",
                "<mapping>",
                None,
                "an existing attribute label",
            )
        if not isinstance(property_types, dict):
            invalid(
                label,
                "<all>",
                "<mapping>",
                property_types,
                "a dictionary of property widget types",
            )
        for property_name, widget_type in property_types.items():
            if property_name not in attributes[label]:
                invalid(
                    label,
                    property_name,
                    widget_type,
                    None,
                    "an existing attribute property",
                )
            if (
                not isinstance(widget_type, str)
                or widget_type not in supported_widget_types
            ):
                invalid(
                    label,
                    property_name,
                    widget_type,
                    widget_type,
                    "one of combobox, radiobutton, group_id, or lineedit",
                )

    for label, properties in attributes.items():
        property_types = widget_types.get(label, {})
        for property_name, value in properties.items():
            widget_type = property_types.get(property_name, "combobox")
            if widget_type in {"combobox", "radiobutton"}:
                if (
                    not isinstance(value, list)
                    or not value
                    or not all(isinstance(option, str) for option in value)
                ):
                    invalid(
                        label,
                        property_name,
                        widget_type,
                        value,
                        "a non-empty list of strings",
                    )
            elif widget_type == "lineedit" and not isinstance(value, str):
                invalid(
                    label,
                    property_name,
                    widget_type,
                    value,
                    "a string",
                )
            elif widget_type == "group_id" and value != []:
                invalid(
                    label,
                    property_name,
                    widget_type,
                    value,
                    "an empty list",
                )

    return attributes, widget_types


def upload_shape_attrs_file(self, LABEL_OPACITY):
    filter = "Shape Attributes Files (*.json);;All Files (*)"
    file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        self.tr("Select a specific shape attributes file"),
        "",
        filter,
    )
    if not file_path:
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            attributes_data = json.load(f)

        attributes, widget_types = validate_shape_attributes_config(
            attributes_data
        )
        self.attributes = attributes
        self.attribute_widget_types = widget_types
        for label in self.attributes:
            if not self.unique_label_list.find_items_by_label(label):
                item = self.unique_label_list.create_item_from_label(label)
                self.unique_label_list.addItem(item)
                rgb = self._get_rgb_by_label(label)
                self.unique_label_list.set_item_label(
                    item, label, rgb, LABEL_OPACITY
                )

        # update the shape attributes dialog
        self.shape_attributes.show()
        selected_shapes = self.canvas.selected_shapes
        is_drawing_mode = (
            hasattr(self.canvas, "current") and self.canvas.current is not None
        )
        if (
            len(selected_shapes) == 1
            and selected_shapes[0] in self.canvas.shapes
            and not is_drawing_mode
        ):
            self.update_attributes(
                self.canvas.shapes.index(selected_shapes[0])
            )
        else:
            self.hide_attributes_panel()
        self.canvas.h_shape_is_hovered = False
        self._settings_runtime_applier.set_auto_switch_to_edit_mode(False)

        popup = Popup(
            self.tr(f"Uploading shape attributes file successfully!"),
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=65, position="center")

    except Exception as e:
        message = (
            f"Error occurred while uploading shape attributes file: {str(e)}"
        )
        logger.error(message)

        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def upload_label_flags_file(self, LABEL_OPACITY):
    filter = "Label Flags Files (*.yaml);;All Files (*)"
    file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        self.tr("Select a specific flags file"),
        "",
        filter,
    )
    if not file_path:
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            # Each line in the file is an flag-level flag
            self.label_flags = yaml.safe_load(f)
            for label in list(self.label_flags.keys()):
                if not self.unique_label_list.find_items_by_label(label):
                    item = self.unique_label_list.create_item_from_label(label)
                    self.unique_label_list.addItem(item)
                    rgb = self._get_rgb_by_label(label)
                    self.unique_label_list.set_item_label(
                        item, label, rgb, LABEL_OPACITY
                    )

        # update the label dialog
        self.label_dialog.upload_flags(self.label_flags)

        popup = Popup(
            self.tr(f"Uploading flags file successfully!"),
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=65, position="center")

    except Exception as e:
        message = f"Error occurred while uploading flags file: {str(e)}"
        logger.error(message)

        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def upload_image_flags_file(self):
    filter = "Image Flags Files (*.txt);;All Files (*)"
    file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        self.tr("Select a specific flags file"),
        "",
        filter,
    )
    if not file_path:
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            # Each line in the file is an image-level flag
            self.image_flags = f.read().splitlines()
            self.load_flags({k: False for k in self.image_flags})
        self.flag_dock.show()

        # update and refresh the current canvas
        self.load_file(self.filename)

        popup = Popup(
            self.tr(f"Uploading flags file successfully!"),
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=65, position="center")

    except Exception as e:
        message = f"Error occurred while uploading flags file: {str(e)}"
        logger.error(message)
        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")
