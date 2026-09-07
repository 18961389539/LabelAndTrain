import json
import os
import os.path as osp
import pathlib
import shutil
import time

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


class ExportThread(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        converter,
        image_list,
        label_dir_path,
        save_path,
        mode,
        prefix=None,
    ):
        super().__init__()
        self.converter = converter
        self.image_list = image_list
        self.label_dir_path = label_dir_path
        self.save_path = save_path
        self.mode = mode
        self.prefix = prefix

    def run(self):
        try:
            time.sleep(1)

            if self.mode == "vlm_r1_ovd":
                self.converter.custom_to_vlm_r1_ovd(
                    self.image_list,
                    self.label_dir_path,
                    self.save_path,
                    self.prefix,
                )
            elif self.mode == "mot":
                self.converter.custom_to_mot(
                    self.label_dir_path, self.save_path
                )
            elif self.mode == "mots":
                self.converter.custom_to_mots(
                    self.label_dir_path, self.save_path
                )
            elif self.mode == "odvg":
                self.converter.custom_to_odvg(
                    self.image_list, self.label_dir_path, self.save_path
                )
            else:
                self.converter.custom_to_coco(
                    self.image_list,
                    self.label_dir_path,
                    self.save_path,
                    self.mode,
                )
            self.finished.emit(True, "")
        except Exception as e:
            self.finished.emit(False, str(e))


def _check_filename_exist(self):
    if not self.may_continue():
        return False

    if not self.filename:
        popup = Popup(
            self.tr("Please load an image folder before proceeding!"),
            self,
            icon=new_icon_path("warning", "svg"),
        )
        popup.show_popup(self, position="center")
        return False

    return True


def export_yolo_annotation(self, mode):
    if not _check_filename_exist(self):
        return

    # Handle config/classes file selection based on mode
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
        converter = LabelConverter(classes_file=self.classes_file)

    dialog = QtWidgets.QDialog(self)
    dialog.setWindowTitle(self.tr("Export options"))
    dialog.setMinimumWidth(500)
    dialog.setStyleSheet(get_export_option_style())

    layout = QVBoxLayout()
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    path_layout = QVBoxLayout()
    path_label = QtWidgets.QLabel(self.tr("Export path"))
    path_layout.addWidget(path_label)

    path_input_layout = QHBoxLayout()
    path_input_layout.setSpacing(8)

    path_edit = QtWidgets.QLineEdit()
    path_edit.setText(
        osp.realpath(osp.join(osp.dirname(self.filename), "..", "labels"))
    )
    path_edit.setPlaceholderText(self.tr("Select Export Directory"))

    def browse_export_path():
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("Select Export Directory"),
            path_edit.text(),
            QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            path_edit.setText(path)

    path_button = QtWidgets.QPushButton(self.tr("Browse"))
    path_button.clicked.connect(browse_export_path)
    path_button.setStyleSheet(get_cancel_btn_style())

    path_input_layout.addWidget(path_edit)
    path_input_layout.addWidget(path_button)
    path_layout.addLayout(path_input_layout)
    layout.addLayout(path_layout)

    options_label = QtWidgets.QLabel(self.tr("Export Options"))
    layout.addWidget(options_label)

    save_images_checkbox = QtWidgets.QCheckBox(self.tr("Save with images?"))
    save_images_checkbox.setChecked(False)
    layout.addWidget(save_images_checkbox)

    skip_empty_files_checkbox = QtWidgets.QCheckBox(
        self.tr("Skip empty labels?")
    )
    skip_empty_files_checkbox.setChecked(False)
    skip_empty_files_checkbox.setToolTip(
        "Skip empty labels / 跳过空标注\n"
        "\n"
        "默认关闭：空标注（确认无目标的负样本图）会导出为空文件，"
        "作为背景样本参与 YOLO 训练。\n"
        "\n"
        "勾选后：空标注的图片不会导出对应标签文件，这些负样本将从"
        "训练数据中排除（通常不建议，除非你确实不要背景样本）。"
    )
    layout.addWidget(skip_empty_files_checkbox)

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

    # Batch export reads the label files from disk. Save any unsaved
    # changes of the current image *before* exporting so the output does
    # not silently miss labels the user just drew. Abort if the user
    # cancels the save or the save fails (self.dirty stays set).
    if getattr(self, "dirty", False) and hasattr(self, "save_file"):
        self.save_file()
        if getattr(self, "dirty", False):
            logger.warning(
                "Export aborted: current labels were not saved on disk"
            )
            popup = Popup(
                self.tr(
                    "Export cancelled.\n"
                    "The current labels could not be saved first."
                ),
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, popup_height=65, position="center")
            return

    save_images = save_images_checkbox.isChecked()
    skip_empty_files = skip_empty_files_checkbox.isChecked()
    save_path = path_edit.text()
    image_list = self.image_list if self.image_list else [self.filename]

    def get_label_file(image_file):
        label_file_name = osp.splitext(osp.basename(image_file))[0] + ".json"
        label_dir = self.output_dir or osp.dirname(image_file)
        return osp.join(label_dir, label_file_name)

    if osp.exists(save_path):
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(self.tr("Output Directory Exists!"))
        msg_box.setText(self.tr("Directory already exists. Choose an action:"))
        msg_box.setInformativeText(
            self.tr(
                "• Yes    - Merge with existing files\n"
                "• No     - Delete existing directory\n"
                "• Cancel - Abort export"
            )
        )

        msg_box.addButton(
            self.tr("Yes"), QtWidgets.QMessageBox.ButtonRole.YesRole
        )
        no_button = msg_box.addButton(
            self.tr("No"), QtWidgets.QMessageBox.ButtonRole.NoRole
        )
        cancel_button = msg_box.addButton(
            self.tr("Cancel"), QtWidgets.QMessageBox.ButtonRole.RejectRole
        )
        msg_box.setStyleSheet(get_msg_box_style())
        msg_box.exec()

        clicked_button = msg_box.clickedButton()
        if clicked_button == no_button:
            shutil.rmtree(save_path)
            os.makedirs(save_path)
        elif clicked_button == cancel_button:
            return
    else:
        os.makedirs(save_path)

    progress_dialog = QProgressDialog(
        self.tr("Exporting..."), self.tr("Cancel"), 0, len(image_list), self
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Progress"))
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setStyleSheet(
        get_progress_dialog_style(color="#1d1d1f", height=20)
    )

    try:
        for i, image_file in enumerate(image_list):
            image_file_name = osp.basename(image_file)
            dst_file_name = osp.splitext(image_file_name)[0] + ".txt"

            src_file = get_label_file(image_file)
            dst_file = osp.join(save_path, dst_file_name)

            is_empty_file = converter.custom_to_yolo(
                src_file,
                dst_file,
                mode,
                skip_empty_files=skip_empty_files,
            )

            if save_images and not (skip_empty_files and is_empty_file):
                image_dst = osp.join(save_path, image_file_name)
                shutil.copy(image_file, image_dst)

            if skip_empty_files and is_empty_file and osp.exists(dst_file):
                os.remove(dst_file)

            progress_dialog.setValue(i)
            if progress_dialog.wasCanceled():
                break

        progress_dialog.close()
        template = self.tr(
            "Exporting annotations successfully!\n"
            "Results have been saved to:\n"
            "%s"
        )
        message_text = template % save_path
        popup = Popup(
            message_text,
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=65, position="center")

    except Exception as e:
        message = f"Error occurred while exporting annotations: {str(e)}"
        progress_dialog.close()
        logger.error(message)
        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def export_voc_annotation(self, mode):
    if not _check_filename_exist(self):
        return

    dialog = QtWidgets.QDialog(self)
    dialog.setWindowTitle(self.tr("Export options"))
    dialog.setMinimumWidth(500)
    dialog.setStyleSheet(get_export_option_style())

    layout = QVBoxLayout()
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    path_layout = QVBoxLayout()
    path_label = QtWidgets.QLabel(self.tr("Export path"))
    path_layout.addWidget(path_label)

    path_input_layout = QHBoxLayout()
    path_input_layout.setSpacing(8)

    path_edit = QtWidgets.QLineEdit()
    path_edit.setText(
        osp.realpath(osp.join(osp.dirname(self.filename), "..", "Annotations"))
    )
    path_edit.setPlaceholderText(self.tr("Select Export Directory"))

    def browse_export_path():
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("Select Export Directory"),
            path_edit.text(),
            QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            path_edit.setText(path)

    path_button = QtWidgets.QPushButton(self.tr("Browse"))
    path_button.clicked.connect(browse_export_path)
    path_button.setStyleSheet(get_cancel_btn_style())

    path_input_layout.addWidget(path_edit)
    path_input_layout.addWidget(path_button)
    path_layout.addLayout(path_input_layout)
    layout.addLayout(path_layout)

    options_label = QtWidgets.QLabel(self.tr("Export Options"))
    layout.addWidget(options_label)

    save_images_checkbox = QtWidgets.QCheckBox(self.tr("Save with images?"))
    save_images_checkbox.setChecked(False)
    layout.addWidget(save_images_checkbox)

    skip_empty_files_checkbox = QtWidgets.QCheckBox(
        self.tr("Skip empty labels?")
    )
    skip_empty_files_checkbox.setChecked(False)
    skip_empty_files_checkbox.setToolTip(
        "Skip empty labels / 跳过空标注\n"
        "\n"
        "默认关闭：空标注（确认无目标的负样本图）会导出为空文件，"
        "作为背景样本参与 YOLO 训练。\n"
        "\n"
        "勾选后：空标注的图片不会导出对应标签文件，这些负样本将从"
        "训练数据中排除（通常不建议，除非你确实不要背景样本）。"
    )
    layout.addWidget(skip_empty_files_checkbox)

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

    save_images = save_images_checkbox.isChecked()
    skip_empty_files = skip_empty_files_checkbox.isChecked()
    save_path = path_edit.text()

    if osp.exists(save_path):
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(self.tr("Output Directory Exists!"))
        msg_box.setText(self.tr("Directory already exists. Choose an action:"))
        msg_box.setInformativeText(
            self.tr(
                "• Yes    - Merge with existing files\n"
                "• No     - Delete existing directory\n"
                "• Cancel - Abort export"
            )
        )

        msg_box.addButton(
            self.tr("Yes"), QtWidgets.QMessageBox.ButtonRole.YesRole
        )
        no_button = msg_box.addButton(
            self.tr("No"), QtWidgets.QMessageBox.ButtonRole.NoRole
        )
        cancel_button = msg_box.addButton(
            self.tr("Cancel"), QtWidgets.QMessageBox.ButtonRole.RejectRole
        )
        msg_box.setStyleSheet(get_msg_box_style())
        msg_box.exec()

        clicked_button = msg_box.clickedButton()
        if clicked_button == no_button:
            shutil.rmtree(save_path)
            os.makedirs(save_path)
        elif clicked_button == cancel_button:
            return
    else:
        os.makedirs(save_path)

    converter = LabelConverter()

    image_list = self.image_list if self.image_list else [self.filename]

    progress_dialog = QProgressDialog(
        self.tr("Exporting..."), self.tr("Cancel"), 0, len(image_list), self
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Progress"))
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setStyleSheet(
        get_progress_dialog_style(color="#1d1d1f", height=20)
    )

    try:
        for i, image_file in enumerate(image_list):
            image_file_name = osp.basename(image_file)
            label_file_name = osp.splitext(image_file_name)[0] + ".json"
            dst_file_name = osp.splitext(image_file_name)[0] + ".xml"

            if self.output_dir:
                src_file = osp.join(self.output_dir, label_file_name)
            else:
                src_file = osp.join(osp.dirname(image_file), label_file_name)
            dst_file = osp.join(save_path, dst_file_name)

            is_empty_file = converter.custom_to_voc(
                image_file, src_file, dst_file, mode, skip_empty_files
            )

            if save_images and not (skip_empty_files and is_empty_file):
                image_dst = osp.join(save_path, image_file_name)
                shutil.copy(image_file, image_dst)

            if skip_empty_files and is_empty_file and osp.exists(dst_file):
                os.remove(dst_file)

            progress_dialog.setValue(i)
            if progress_dialog.wasCanceled():
                break

        progress_dialog.close()
        template = self.tr(
            "Exporting annotations successfully!\n"
            "Results have been saved to:\n"
            "%s"
        )
        message_text = template % save_path
        popup = Popup(
            message_text,
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=65, position="center")

    except Exception as e:
        message = f"Error occurred while exporting annotations: {str(e)}"
        progress_dialog.close()
        logger.error(message)
        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def export_coco_annotation(self, mode):
    if not _check_filename_exist(self):
        return

    if mode == "pose":
        filter = "Classes Files (*.yaml);;All Files (*)"
        self.yaml_file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("Select a specific coco-pose config file"),
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
    elif mode in ["rectangle", "polygon"]:
        filter = "Classes Files (*.txt);;All Files (*)"
        self.classes_file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("Select a specific classes file"),
            "",
            filter,
        )
        if not self.classes_file:
            return
        converter = LabelConverter(classes_file=self.classes_file)

    dialog = QtWidgets.QDialog(self)
    dialog.setWindowTitle(self.tr("Export options"))
    dialog.setMinimumWidth(500)
    dialog.setStyleSheet(get_export_option_style())

    layout = QVBoxLayout()
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    path_layout = QVBoxLayout()
    path_label = QtWidgets.QLabel(self.tr("Export path"))
    path_layout.addWidget(path_label)

    path_input_layout = QHBoxLayout()
    path_input_layout.setSpacing(8)

    label_dir_path = osp.dirname(self.filename)
    if self.output_dir:
        label_dir_path = self.output_dir

    path_edit = QtWidgets.QLineEdit()
    path_edit.setText(
        osp.realpath(osp.join(label_dir_path, "..", "annotations"))
    )
    path_edit.setPlaceholderText(self.tr("Select Export Directory"))

    def browse_export_path():
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("Select Export Directory"),
            path_edit.text(),
            QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            path_edit.setText(path)

    path_button = QtWidgets.QPushButton(self.tr("Browse"))
    path_button.clicked.connect(browse_export_path)
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

    save_path = path_edit.text()
    if osp.exists(save_path):
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        msg_box.setWindowTitle(self.tr("Output Directory Exists!"))
        msg_box.setText(self.tr("Directory already exists. Choose an action:"))
        msg_box.setInformativeText(
            self.tr(
                "• Overwrite - Overwrite existing directory\n"
                "• Cancel - Abort export"
            )
        )

        msg_box.addButton(
            self.tr("Overwrite"), QtWidgets.QMessageBox.ButtonRole.YesRole
        )
        cancel_button = msg_box.addButton(
            self.tr("Cancel"), QtWidgets.QMessageBox.ButtonRole.RejectRole
        )
        msg_box.setStyleSheet(get_msg_box_style())
        msg_box.exec()

        clicked_button = msg_box.clickedButton()
        if clicked_button == cancel_button:
            return
        else:
            shutil.rmtree(save_path)
            os.makedirs(save_path)
    else:
        os.makedirs(save_path)

    image_list = self.image_list if self.image_list else [self.filename]
    progress_dialog = QProgressDialog(
        self.tr("Exporting..."), self.tr("Cancel"), 0, 0, self
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Progress"))
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setRange(0, 0)
    progress_dialog.setStyleSheet(get_progress_dialog_style())

    self.export_thread = ExportThread(
        converter, image_list, label_dir_path, save_path, mode
    )

    def on_export_finished(success, error_msg):
        progress_dialog.close()
        if success:
            template = self.tr(
                "Exporting annotations successfully!\n"
                "Results have been saved to:\n"
                "%s"
            )
            message_text = template % save_path
            popup = Popup(
                message_text,
                self,
                icon=new_icon_path("copy-green", "svg"),
            )
            popup.show_popup(self, popup_height=65, position="center")
        else:
            message = (
                f"Error occurred while exporting annotations: {str(error_msg)}"
            )
            logger.error(message)
            popup = Popup(
                message,
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, position="center")

    self.export_thread.finished.connect(on_export_finished)

    progress_dialog.show()
    self.export_thread.start()

    progress_dialog.canceled.connect(self.export_thread.terminate)


