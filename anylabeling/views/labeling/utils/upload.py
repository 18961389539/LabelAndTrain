import json
import jsonlines
import os
import os.path as osp
import time
import yaml

from PyQt6 import QtWidgets
from PyQt6.QtCore import QCoreApplication, Qt, QThread, pyqtSignal
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
from anylabeling.config import save_config
from anylabeling.views.labeling import project_context, project_settings
from anylabeling.views.labeling.utils.export import (
    _check_filename_exist,
    resolve_classes_for_yolo,
)
from anylabeling.views.labeling.utils.theme import get_theme


class UploadCocoThread(QThread):
    # Deliberately not ``finished``: that name collides with QThread's own
    # zero-argument signal, which Qt emits when run() returns.
    upload_finished = pyqtSignal(bool, str, dict)

    def __init__(self, converter, input_file, output_dir_path, mode):
        super().__init__()
        self.converter = converter
        self.input_file = input_file
        self.output_dir_path = output_dir_path
        self.mode = mode

    def run(self):
        try:
            time.sleep(1)

            report = self.converter.coco_to_custom(
                input_file=self.input_file,
                output_dir_path=self.output_dir_path,
                mode=self.mode,
                cancel=self.isInterruptionRequested,
            )

            self.upload_finished.emit(True, "", report or {})

        except Exception as e:
            self.upload_finished.emit(False, str(e), {})


def upload_coco_annotation(self, mode):
    if not _check_filename_exist(self):
        return

    filter = "Attribute Files (*.json);;All Files (*)"
    input_file, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        QCoreApplication.translate(
            "LabelingWidget", "Select a custom coco annotation file"
        ),
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
    response.setWindowTitle(
        QCoreApplication.translate("LabelingWidget", "Warning")
    )
    response.setText(
        QCoreApplication.translate(
            "LabelingWidget", "Current annotation will be lost"
        )
    )
    response.setInformativeText(
        QCoreApplication.translate(
            "LabelingWidget",
            "You are going to upload new annotations to this task. Continue?",
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
        QCoreApplication.translate("LabelingWidget", "Uploading..."),
        QCoreApplication.translate("LabelingWidget", "Cancel"),
        0,
        0,
        self,
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(
        QCoreApplication.translate("LabelingWidget", "Progress")
    )
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setRange(0, 0)
    progress_dialog.setStyleSheet(get_progress_dialog_style())

    self.upload_thread = UploadCocoThread(
        LabelConverter(), input_file, output_dir_path, mode
    )

    def on_upload_finished(success, error_msg, report):
        progress_dialog.close()
        if success:
            # update and refresh the current canvas
            self.load_file(self.filename)

            skipped = report.get("skipped") or []
            failed = report.get("failed") or []
            if skipped or failed:
                _report_coco_import_problems(self, report)
            elif not report.get("cancelled"):
                popup = Popup(
                    QCoreApplication.translate(
                        "LabelingWidget",
                        "Uploading annotations successfully!",
                    ),
                    self,
                    icon=new_icon_path("copy-green", "svg"),
                )
                popup.show_popup(self, popup_height=65, position="center")
        else:
            message = QCoreApplication.translate(
                "LabelingWidget", "上传标注时出错：%s"
            ) % str(error_msg)
            logger.error(message)
            popup = Popup(
                message,
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, position="center")

    self.upload_thread.upload_finished.connect(on_upload_finished)

    progress_dialog.show()
    self.upload_thread.start()

    progress_dialog.canceled.connect(self.upload_thread.requestInterruption)


def upload_voc_annotation(self, mode):
    if not _check_filename_exist(self):
        return

    dialog = QtWidgets.QDialog(self)
    dialog.setWindowTitle(
        QCoreApplication.translate("LabelingWidget", "Upload Options")
    )
    dialog.setMinimumWidth(500)
    dialog.setStyleSheet(get_export_option_style())

    layout = QVBoxLayout()
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    path_layout = QVBoxLayout()
    path_label = QtWidgets.QLabel(
        QCoreApplication.translate("LabelingWidget", "Select Upload Folder")
    )
    path_layout.addWidget(path_label)

    path_input_layout = QHBoxLayout()
    path_input_layout.setSpacing(8)

    path_edit = QtWidgets.QLineEdit()
    path_edit.setText(osp.dirname(osp.dirname(self.filename)))

    def browse_upload_folder():
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            QCoreApplication.translate(
                "LabelingWidget", "Select Upload Folder"
            ),
            path_edit.text(),
            QtWidgets.QFileDialog.Option.ShowDirsOnly
            | QtWidgets.QFileDialog.Option.DontResolveSymlinks
            | QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            path_edit.setText(path)

    path_button = QtWidgets.QPushButton(
        QCoreApplication.translate("LabelingWidget", "Browse")
    )
    path_button.clicked.connect(browse_upload_folder)
    path_button.setStyleSheet(get_cancel_btn_style())

    path_input_layout.addWidget(path_edit)
    path_input_layout.addWidget(path_button)
    path_layout.addLayout(path_input_layout)
    layout.addLayout(path_layout)

    button_layout = QHBoxLayout()
    button_layout.setContentsMargins(0, 16, 0, 0)
    button_layout.setSpacing(8)

    cancel_button = QtWidgets.QPushButton(
        QCoreApplication.translate("LabelingWidget", "Cancel")
    )
    cancel_button.clicked.connect(dialog.reject)
    cancel_button.setStyleSheet(get_cancel_btn_style())

    ok_button = QtWidgets.QPushButton(
        QCoreApplication.translate("LabelingWidget", "OK")
    )
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
    response.setWindowTitle(
        QCoreApplication.translate("LabelingWidget", "Warning")
    )
    response.setText(
        QCoreApplication.translate(
            "LabelingWidget", "Current annotation will be lost"
        )
    )
    response.setInformativeText(
        QCoreApplication.translate(
            "LabelingWidget",
            "You are going to upload new annotations to this task. Continue?",
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
        QCoreApplication.translate("LabelingWidget", "Uploading..."),
        QCoreApplication.translate("LabelingWidget", "Cancel"),
        0,
        len(image_list),
        self,
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(
        QCoreApplication.translate("LabelingWidget", "Progress")
    )
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setStyleSheet(
        get_progress_dialog_style(color=get_theme()["text"], height=20)
    )

    def _progress(index, total):
        progress_dialog.setValue(index + 1)
        QtWidgets.QApplication.processEvents()

    try:
        result = import_voc_labels(
            converter,
            image_list,
            label_file_list,
            label_dir_path,
            output_dir_path,
            mode,
            progress=_progress,
            is_cancelled=progress_dialog.wasCanceled,
        )
        progress_dialog.close()
        # update and refresh the current canvas
        self.load_file(self.filename)

        if result["failed"]:
            _report_import_failures(self, result)
        elif not result["cancelled"]:
            template = QCoreApplication.translate(
                "LabelingWidget",
                "Uploading annotations successfully!\n"
                "Results have been saved to:\n"
                "%s",
            )
            popup = Popup(
                template % output_dir_path,
                self,
                icon=new_icon_path("copy-green", "svg"),
            )
            popup.show_popup(self, popup_height=65, position="center")

    except Exception as e:
        progress_dialog.close()
        message = QCoreApplication.translate(
            "LabelingWidget", "上传标注时出错：%s"
        ) % str(e)
        logger.error(message)
        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def _report_coco_import_problems(parent, report):
    skipped = report.get("skipped") or []
    failed = report.get("failed") or []
    box = QtWidgets.QMessageBox(parent)
    box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    box.setWindowTitle(
        QCoreApplication.translate(
            "LabelingWidget", "Error occurred while processing images!"
        )
    )
    box.setText(
        QCoreApplication.translate(
            "LabelingWidget",
            "已写入 %d 张图片；%d 条标注无法读取，%d 张图片写入失败。",
        )
        % (report.get("written", 0), len(skipped), len(failed))
    )
    details = []
    for image_id, reason in skipped[:20]:
        details.append(reason if image_id is None else f"{image_id}: {reason}")
    for path, error in failed[:20]:
        details.append(f"{path}: {error}")
    if details:
        box.setDetailedText("\n".join(details))
    box.exec()


def import_yolo_labels(
    converter,
    image_file_list,
    label_file_list,
    label_dir_path,
    image_dir_path,
    output_dir_path,
    mode,
    preserve_existing,
    progress=None,
    is_cancelled=None,
):
    """Import one YOLO folder, one file at a time.

    A malformed line, a missing image or an unreadable existing JSON must
    not abandon the rest of the folder: the pair goes into ``failed`` with
    its reason and the loop continues. Returns
    ``{"imported", "attempted", "failed", "cancelled"}`` so the caller can
    report what actually happened.
    """
    result = {"imported": 0, "attempted": 0, "failed": [], "cancelled": False}
    for index, image_filename in enumerate(image_file_list):
        if is_cancelled is not None and is_cancelled():
            result["cancelled"] = True
            break
        if image_filename.endswith(".json"):
            continue
        label_filename = osp.splitext(image_filename)[0] + ".txt"
        if label_filename not in label_file_list:
            continue
        data_filename = osp.splitext(image_filename)[0] + ".json"
        input_file = osp.join(label_dir_path, label_filename)
        output_file = osp.join(output_dir_path, data_filename)
        image_file = osp.join(image_dir_path, image_filename)
        result["attempted"] += 1
        try:
            existing_shapes = []
            if preserve_existing and osp.exists(output_file):
                with open(output_file, "r", encoding="utf-8") as handle:
                    existing_data = json.load(handle)
                existing_shapes = existing_data.get("shapes", [])

            if mode in ("hbb", "seg"):
                converter.yolo_to_custom(
                    input_file, output_file, image_file, mode
                )
            elif mode == "obb":
                converter.yolo_obb_to_custom(
                    input_file, output_file, image_file
                )
            elif mode == "pose":
                converter.yolo_pose_to_custom(
                    input_file, output_file, image_file
                )
            else:
                raise ValueError(f"Unsupported YOLO mode: {mode}")

            if preserve_existing and existing_shapes:
                with open(output_file, "r", encoding="utf-8") as handle:
                    new_data = json.load(handle)
                new_data["shapes"] = existing_shapes + new_data.get(
                    "shapes", []
                )
                converter.save_label_json(new_data, output_file)
        except Exception as exc:  # noqa: BLE001 - one bad file, not a batch
            logger.warning(f"YOLO import failed for {output_file}: {exc}")
            result["failed"].append((output_file, str(exc)))
        else:
            result["imported"] += 1
        if progress is not None:
            progress(index, len(image_file_list))
    return result


def import_voc_labels(
    converter,
    image_list,
    label_file_list,
    label_dir_path,
    output_dir_path,
    mode,
    progress=None,
    is_cancelled=None,
):
    """Import VOC XMLs one image at a time; one bad XML is not a batch."""
    result = {"imported": 0, "attempted": 0, "failed": [], "cancelled": False}
    for index, image_path in enumerate(image_list):
        if is_cancelled is not None and is_cancelled():
            result["cancelled"] = True
            break
        image_filename = osp.basename(image_path)
        label_filename = osp.splitext(image_filename)[0] + ".xml"
        if label_filename not in label_file_list:
            continue
        input_file = osp.join(label_dir_path, label_filename)
        output_file = osp.join(
            output_dir_path, osp.splitext(image_filename)[0] + ".json"
        )
        result["attempted"] += 1
        try:
            converter.voc_to_custom(
                input_file=input_file,
                output_file=output_file,
                image_filename=image_filename,
                mode=mode,
            )
        except Exception as exc:  # noqa: BLE001 - one bad file, not a batch
            logger.warning(f"VOC import failed for {output_file}: {exc}")
            result["failed"].append((output_file, str(exc)))
        else:
            result["imported"] += 1
        if progress is not None:
            progress(index, len(image_list))
    return result


def _report_import_failures(parent, result):
    box = QtWidgets.QMessageBox(parent)
    box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    box.setWindowTitle(
        QCoreApplication.translate(
            "LabelingWidget", "Error occurred while processing images!"
        )
    )
    box.setText(
        QCoreApplication.translate(
            "LabelingWidget",
            "Processing finished: %d succeeded, %d failed " "(of %d total).",
        )
        % (result["imported"], len(result["failed"]), result["attempted"])
    )
    box.setDetailedText(
        "\n".join(f"{path}: {error}" for path, error in result["failed"][:20])
    )
    box.exec()


def upload_yolo_annotation(self, mode, LABEL_OPACITY):
    if not _check_filename_exist(self):
        return

    if mode == "pose":
        filter = "Classes Files (*.yaml);;All Files (*)"
        self.yaml_file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            QCoreApplication.translate(
                "LabelingWidget", "Select a specific yolo-pose config file"
            ),
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
                QCoreApplication.translate(
                    "LabelingWidget", "Invalid pose config file:\n%s"
                )
                % str(e),
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, popup_height=65, position="center")
            return

        labels = []
        for class_name, keypoint_name in converter.pose_classes.items():
            labels.append(class_name)
            labels.extend(keypoint_name)

    elif mode in ["hbb", "seg", "obb"]:
        resolved = resolve_classes_for_yolo(self, mode)
        if resolved is None:
            return
        labels, _, converter = resolved
        if not labels:
            popup = Popup(
                QCoreApplication.translate(
                    "LabelingWidget",
                    "The class list is empty - nothing can be imported.",
                ),
                self,
                icon=new_icon_path("warning", "svg"),
            )
            popup.show_popup(self, position="center")
            return

    dialog = QtWidgets.QDialog(self)
    dialog.setWindowTitle(
        QCoreApplication.translate("LabelingWidget", "Upload Options")
    )
    dialog.setMinimumWidth(500)
    dialog.setStyleSheet(get_export_option_style())

    layout = QVBoxLayout()
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    path_layout = QVBoxLayout()
    path_label = QtWidgets.QLabel(
        QCoreApplication.translate("LabelingWidget", "Select Upload Folder")
    )
    path_layout.addWidget(path_label)

    path_input_layout = QHBoxLayout()
    path_input_layout.setSpacing(8)

    path_edit = QtWidgets.QLineEdit()
    path_edit.setText(osp.dirname(osp.dirname(self.filename)))

    def browse_upload_folder():
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            QCoreApplication.translate(
                "LabelingWidget", "Select Upload Folder"
            ),
            path_edit.text(),
            QtWidgets.QFileDialog.Option.ShowDirsOnly
            | QtWidgets.QFileDialog.Option.DontResolveSymlinks
            | QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            path_edit.setText(path)

    path_button = QtWidgets.QPushButton(
        QCoreApplication.translate("LabelingWidget", "Browse")
    )
    path_button.clicked.connect(browse_upload_folder)
    path_button.setStyleSheet(get_cancel_btn_style())

    path_input_layout.addWidget(path_edit)
    path_input_layout.addWidget(path_button)
    path_layout.addLayout(path_input_layout)
    layout.addLayout(path_layout)

    preserve_checkbox = QtWidgets.QCheckBox(
        QCoreApplication.translate(
            "LabelingWidget", "Preserve existing annotations"
        )
    )
    preserve_checkbox.setChecked(False)
    layout.addWidget(preserve_checkbox)

    button_layout = QHBoxLayout()
    button_layout.setContentsMargins(0, 16, 0, 0)
    button_layout.setSpacing(8)

    cancel_button = QtWidgets.QPushButton(
        QCoreApplication.translate("LabelingWidget", "Cancel")
    )
    cancel_button.clicked.connect(dialog.reject)
    cancel_button.setStyleSheet(get_cancel_btn_style())

    ok_button = QtWidgets.QPushButton(
        QCoreApplication.translate("LabelingWidget", "OK")
    )
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
    response.setWindowTitle(
        QCoreApplication.translate("LabelingWidget", "Warning")
    )
    if preserve_existing:
        response.setText(
            QCoreApplication.translate(
                "LabelingWidget",
                "New annotations will be merged with existing ones",
            )
        )
        response.setInformativeText(
            QCoreApplication.translate(
                "LabelingWidget",
                "You are going to add new annotations to this task. Existing annotations will be preserved. Continue?",
            )
        )
    else:
        response.setText(
            QCoreApplication.translate(
                "LabelingWidget", "Current annotation will be lost"
            )
        )
        response.setInformativeText(
            QCoreApplication.translate(
                "LabelingWidget",
                "You are going to upload new annotations to this task. Continue?",
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
        QCoreApplication.translate("LabelingWidget", "Uploading..."),
        QCoreApplication.translate("LabelingWidget", "Cancel"),
        0,
        len(image_file_list),
        self,
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(
        QCoreApplication.translate("LabelingWidget", "Progress")
    )
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setStyleSheet(
        get_progress_dialog_style(color=get_theme()["text"], height=20)
    )

    def _progress(index, total):
        progress_dialog.setValue(index + 1)
        QtWidgets.QApplication.processEvents()

    try:
        result = import_yolo_labels(
            converter,
            image_file_list,
            label_file_list,
            label_dir_path,
            image_dir_path,
            output_dir_path,
            mode,
            preserve_existing,
            progress=_progress,
            is_cancelled=progress_dialog.wasCanceled,
        )
        progress_dialog.close()
        self.load_file(self.filename)

        # Initialize unique labels
        for label in labels:
            if not self.unique_label_list.find_items_by_label(label):
                item = self.unique_label_list.create_item_from_label(label)
                self.unique_label_list.addItem(item)
                rgb = self._get_rgb_by_label(label)
                self.unique_label_list.set_item_label(
                    item, label, rgb, LABEL_OPACITY
                )

        if result["failed"]:
            _report_import_failures(self, result)
        elif not result["cancelled"]:
            popup = Popup(
                QCoreApplication.translate(
                    "LabelingWidget", "Upload completed successfully!"
                ),
                self,
                icon=new_icon_path("copy-green", "svg"),
            )
            popup.show_popup(self, position="center")

    except Exception as e:
        progress_dialog.close()
        message = QCoreApplication.translate(
            "LabelingWidget", "上传标注时出错：%s"
        ) % str(e)
        logger.error(message)
        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def sanitize_label_list(lines):
    """One class per line: strip, drop blanks, keep the first occurrence."""
    labels = []
    seen = set()
    for line in lines:
        name = line.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        labels.append(name)
    return labels


def apply_uploaded_labels(widget, labels):
    """Make an imported class list the open project's list, and persist it.

    The action used to update only the two in-memory widgets: the config and
    the project record kept the old names, so the import vanished at restart
    and training/export still used the previous classes. Digit shortcuts are
    re-assigned so the imported list is usable immediately.
    """
    widget._config["labels"] = list(labels)
    save_config(widget._config)
    widget.load_labels(labels)
    widget.label_dialog.label_list.clear()
    widget.label_dialog.label_list.addItems(labels)
    if widget.label_dialog._sort_labels:
        widget.label_dialog.sort_labels()
    widget.digit_shortcut_controller.assign_label_digits(labels)
    dataset_dir = project_context.current_dataset_dir(widget)
    if dataset_dir:
        project_settings.save_current_labels(widget, dataset_dir)


def upload_label_classes_file(self):
    filter = "Label Files (*.txt);;All Files (*)"
    file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        QCoreApplication.translate(
            "LabelingWidget", "Select a specific label classes file"
        ),
        "",
        filter,
    )
    if not file_path:
        return

    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            labels = sanitize_label_list(f.readlines())

        if not labels:
            popup = Popup(
                QCoreApplication.translate(
                    "LabelingWidget", "No labels found in the file!"
                ),
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, position="center")
            return

        response = QtWidgets.QMessageBox()
        response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        response.setWindowTitle(
            QCoreApplication.translate("LabelingWidget", "Warning")
        )
        response.setText(
            QCoreApplication.translate(
                "LabelingWidget", "Current labels will be lost"
            )
        )
        response.setInformativeText(
            QCoreApplication.translate(
                "LabelingWidget",
                "You are going to upload new labels to this task. Continue?",
            )
        )
        response.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Cancel
            | QtWidgets.QMessageBox.StandardButton.Ok
        )
        response.setStyleSheet(get_msg_box_style())

        if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
            return

        apply_uploaded_labels(self, labels)

        popup = Popup(
            QCoreApplication.translate(
                "LabelingWidget", "已加载 %1 个类别。"
            ).replace("%1", str(len(labels))),
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, position="center")

    except Exception as e:
        message = QCoreApplication.translate(
            "LabelingWidget", "上传类别文件时出错：%s"
        ) % str(e)
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


def validate_label_flags(data):
    """Normalize a label -> flag-names mapping from a flags file."""
    if not isinstance(data, dict):
        raise ValueError("flags file must contain a label-to-flags mapping")
    result = {}
    for label, names in data.items():
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"invalid label in flags file: {label!r}")
        if names is None:
            names = []
        if not isinstance(names, list) or not all(
            isinstance(name, str) and name.strip() for name in names
        ):
            raise ValueError(f"flags for {label!r} must be a list of names")
        result[label.strip()] = [name.strip() for name in names]
    return result


def persist_shape_attributes(widget, attributes):
    """Make an imported attributes schema survive the session."""
    canvas = widget._config.get("canvas")
    if not isinstance(canvas, dict):
        canvas = {}
        widget._config["canvas"] = canvas
    canvas["attributes"] = attributes
    save_config(widget._config)


def persist_label_flags(widget, flags):
    """Make an imported label-flags schema survive the session."""
    widget._config["label_flags"] = flags
    save_config(widget._config)


def persist_image_flags(widget, flags):
    """Make an imported image-flag name list survive the session."""
    widget._config["flags"] = list(flags)
    save_config(widget._config)


def upload_shape_attrs_file(self, LABEL_OPACITY):
    filter = "Shape Attributes Files (*.json);;All Files (*)"
    file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        QCoreApplication.translate(
            "LabelingWidget", "Select a specific shape attributes file"
        ),
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
        persist_shape_attributes(self, attributes)
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
            QCoreApplication.translate(
                "LabelingWidget", "形状属性文件导入成功。"
            ),
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=65, position="center")

    except Exception as e:
        message = QCoreApplication.translate(
            "LabelingWidget", "上传形状属性文件时出错：%s"
        ) % str(e)
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
        QCoreApplication.translate(
            "LabelingWidget", "Select a specific flags file"
        ),
        "",
        filter,
    )
    if not file_path:
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            # Each line in the file is an flag-level flag
            self.label_flags = validate_label_flags(yaml.safe_load(f))
            persist_label_flags(self, self.label_flags)
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
            QCoreApplication.translate(
                "LabelingWidget", "标签标志文件导入成功。"
            ),
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=65, position="center")

    except Exception as e:
        message = QCoreApplication.translate(
            "LabelingWidget", "上传标签标志文件时出错：%s"
        ) % str(e)
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
        QCoreApplication.translate(
            "LabelingWidget", "Select a specific flags file"
        ),
        "",
        filter,
    )
    if not file_path:
        return

    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            # Each line in the file is an image-level flag
            flags = sanitize_label_list(f.read().splitlines())
        if not flags:
            popup = Popup(
                QCoreApplication.translate(
                    "LabelingWidget", "文件中没有标志。"
                ),
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, position="center")
            return

        self.image_flags = flags
        persist_image_flags(self, flags)
        self.load_flags({name: False for name in flags})
        self.flag_dock.show()
        # No reload here: loading the file again read the old flags back from
        # disk, because nothing had saved the imported list yet.
        self.set_dirty()

        popup = Popup(
            QCoreApplication.translate(
                "LabelingWidget", "图像标志文件导入成功。"
            ),
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=65, position="center")

    except Exception as e:
        message = QCoreApplication.translate(
            "LabelingWidget", "上传图像标志文件时出错：%s"
        ) % str(e)
        logger.error(message)
        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")
