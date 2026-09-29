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
from anylabeling.views.labeling.schema import (
    REVIEW_UNCHECKED,
    is_review_confirmed,
)
from anylabeling.views.labeling.utils.async_label_check import (
    label_file_review_info,
)
from anylabeling.views.labeling.widgets import Popup
from anylabeling.views.labeling.utils.qt import new_icon_path
from anylabeling.views.labeling.utils.output_dir import (
    CANCEL,
    resolve_existing_output_dir,
)
from anylabeling.views.labeling.utils.export_check import (
    MANIFEST_NAME,
    build_manifest,
    check_export_readiness,
    format_readiness,
    is_blocking,
    write_manifest,
)
from anylabeling.app_info import __version__
from anylabeling.views.labeling.utils.style import *
from anylabeling.views.labeling.utils.style import get_msg_box_style
from anylabeling.views.labeling.utils.theme import get_theme


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


def resolve_classes_for_yolo(widget, mode):
    """Pick the class list for a YOLO export/import.

    The open project's own labels are offered first — they are what the
    annotator just drew with — and picking a ``classes.txt`` stays available
    for when the target order differs from the annotated one.

    Returns ``(classes, source_label, converter)``, or ``None`` when the
    annotator cancelled.
    """
    labels = [
        str(name) for name in (widget._config.get("labels") or []) if name
    ]
    if labels:
        box = QtWidgets.QMessageBox(widget)
        box.setIcon(QtWidgets.QMessageBox.Icon.Question)
        box.setWindowTitle(widget.tr("Select the class list"))
        box.setText(
            widget.tr("用当前标签列表（%d 个类别）还是选择一个 classes.txt？")
            % len(labels)
        )
        preview = ", ".join(labels[:8])
        if len(labels) > 8:
            preview += ", ..."
        box.setInformativeText(
            preview
            + "\n\n"
            + widget.tr(
                "类别顺序决定 YOLO 的类别编号，导出前请确认与训练一致。"
            )
        )
        current_button = box.addButton(
            widget.tr("用当前标签列表"),
            QtWidgets.QMessageBox.ButtonRole.AcceptRole,
        )
        file_button = box.addButton(
            widget.tr("选择 classes.txt..."),
            QtWidgets.QMessageBox.ButtonRole.ActionRole,
        )
        box.addButton(
            widget.tr("Cancel"), QtWidgets.QMessageBox.ButtonRole.RejectRole
        )
        box.setDefaultButton(current_button)
        box.setStyleSheet(get_msg_box_style())
        box.exec()
        clicked = box.clickedButton()
        if clicked is current_button:
            logger.info(f"{mode}: using the open project's label list")
            return (
                labels,
                widget.tr("当前标签列表"),
                LabelConverter(classes=labels),
            )
        if clicked is not file_button:
            return None

    classes_file, _ = QtWidgets.QFileDialog.getOpenFileName(
        widget,
        widget.tr("Select a specific classes file"),
        "",
        "Classes Files (*.txt);;All Files (*)",
    )
    if not classes_file:
        return None
    widget.classes_file = classes_file
    logger.info(f"{mode}: classes from {classes_file}")
    converter = LabelConverter(classes_file=classes_file)
    return list(converter.classes), osp.basename(classes_file), converter


def split_images_by_review(image_list, label_path_for, only_confirmed):
    """Split an export's image list by review state.

    ``label_path_for`` maps an image path to its label file. With
    ``only_confirmed`` the kept list holds the images whose label file is in
    the confirmed state, and everything else — unchecked, rejected, or with no
    label file at all — lands in the returned count. The training side already
    has this filter (`only_checked_files` in the ultralytics general module);
    the export used to ignore the review state entirely, so an image marked
    需返工 was excluded from training and written into the export at once.
    """
    if not only_confirmed:
        return list(image_list), 0
    kept = []
    skipped = 0
    for image_file in image_list:
        try:
            state = label_file_review_info(label_path_for(image_file))[0]
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"Could not read the review state of {image_file}: {e}"
            )
            state = REVIEW_UNCHECKED
        if is_review_confirmed(state):
            kept.append(image_file)
        else:
            skipped += 1
    return kept, skipped


def _write_classes_file(save_path, classes):
    """Drop the class list next to the exported labels."""
    target = osp.join(save_path, "classes.txt")
    with open(target, "w", encoding="utf-8") as handle:
        for name in classes:
            handle.write(f"{name}\n")
    return target


def _write_data_yaml(save_path, classes):
    """Drop a minimal data.yaml next to the exported labels.

    ``nc``/``names`` are all the export can know; a data.yaml that
    guesses ``train``/``val`` would point at directories that may not
    exist, so those are left as comments for the training side to fill
    in.  This still saves the hand-typing of the class list on every
    run -- the part that is easy to get subtly wrong (order, spelling),
    and the exact mistake that makes an export silently drop a class.
    """
    target = osp.join(save_path, "data.yaml")
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(
            "# Written by JLLabelingAndTrain export. Fill in path/train/val\n"
            "# to match your dataset layout before training, e.g.:\n"
            "#   path: <this directory>\n"
            "#   train: images/train\n"
            "#   val: images/val\n"
        )
        handle.write(f"nc: {len(classes)}\n")
        handle.write("names:\n")
        for name in classes:
            handle.write(f"- {name}\n")
    return target


def _format_yolo_export_summary(
    widget,
    counted_files,
    total_files,
    stats,
    copied_images,
    classes_target,
    skipped_unchecked=0,
    data_yaml_target=None,
    manifest_target=None,
):
    """Human-readable recap of a YOLO export, skips included.

    "Exporting annotations successfully!" with nothing else is how a batch
    that silently dropped half its polygons passes for a good run.
    """
    lines = [
        widget.tr("导出完成：%d/%d 张图，%d 个标注")
        % (counted_files, total_files, stats.get("exported", 0)),
    ]
    if skipped_unchecked:
        lines.append(
            widget.tr("按「仅导出已确认图片」跳过 %d 张（未检查或需返工）")
            % skipped_unchecked
        )
    if copied_images:
        lines.append(widget.tr("已复制 %d 张图片") % copied_images)
    if classes_target:
        lines.append(widget.tr("已写入 %s") % osp.basename(classes_target))
    if data_yaml_target:
        lines.append(
            widget.tr("已写入 %s（train/val 需按布局补填）") % "data.yaml"
        )
    if manifest_target:
        lines.append(
            widget.tr("已写入 %s（本次的类别来源、筛选条件与跳过明细）")
            % MANIFEST_NAME
        )
    missing = stats.get("missing_label_file", 0)
    if missing:
        lines.append(
            widget.tr("没有标签文件（按空标注处理）：%d 张") % missing
        )
    skipped = stats.get("skipped") or {}
    if skipped:
        total_skipped = sum(skipped.values())
        lines.append(widget.tr("跳过 %d 个无法转换的标注：") % total_skipped)
        for reason, count in sorted(
            skipped.items(), key=lambda item: (-item[1], item[0])
        ):
            lines.append(f"    - {count} × {reason}")
        lines.append(
            widget.tr(
                "若不应跳过，请检查类别列表与形状类型（例如 hbb 只导出矩形框）。"
            )
        )
    return "\n".join(lines)


def export_yolo_annotation(self, mode):
    if not _check_filename_exist(self):
        return

    # Handle config/classes file selection based on mode
    classes = []
    classes_source = ""
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
        classes = list(converter.classes)
        classes_source = osp.basename(self.yaml_file)

    else:
        resolved = resolve_classes_for_yolo(self, mode)
        if resolved is None:
            return
        classes, classes_source, converter = resolved
        if not classes:
            popup = Popup(
                self.tr("The class list is empty - nothing can be exported."),
                self,
                icon=new_icon_path("warning", "svg"),
            )
            popup.show_popup(self, position="center")
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
        self.tr(
            "Skip empty labels / 跳过空标注\n"
            "\n"
            "默认关闭：空标注（确认无目标的负样本图）会导出为空文件，"
            "作为背景样本参与 YOLO 训练。\n"
            "\n"
            "勾选后：空标注的图片不会导出对应标签文件，这些负样本将从"
            "训练数据中排除（通常不建议，除非你确实不要背景样本）。"
        )
    )
    layout.addWidget(skip_empty_files_checkbox)

    only_checked_checkbox = QtWidgets.QCheckBox(
        self.tr("仅导出「已确认」的图片")
    )
    only_checked_checkbox.setChecked(False)
    only_checked_checkbox.setToolTip(
        self.tr(
            "Only export confirmed images / 仅导出已确认的图片\n"
            "\n"
            "默认关闭：导出当前文件夹里的全部图片，含未检查与「需返工」的。\n"
            "\n"
            "勾选后：只导出在文件列表里标记为「已确认」的图片，"
            "未检查与需返工的一律跳过（数量会在导出结果里报出来）。\n"
            "训练侧本来就有同样的过滤（只用已检查的图片），"
            "勾上它可以让导出与训练集合保持一致。"
        )
    )
    layout.addWidget(only_checked_checkbox)

    write_classes_checkbox = None
    if classes:
        write_classes_checkbox = QtWidgets.QCheckBox(
            self.tr("在导出目录写入 classes.txt（%d 个类别）") % len(classes)
        )
        write_classes_checkbox.setChecked(True)
        write_classes_checkbox.setToolTip(
            self.tr(
                "勾选后会在导出目录生成 classes.txt，类别顺序与本次导出"
                "所用的列表一致；训练前不必再手工摆一份。\n"
                "类别来源：%s"
            )
            % (classes_source or self.tr("项目标签列表"))
        )
        layout.addWidget(write_classes_checkbox)

    manifest_checkbox = QtWidgets.QCheckBox(
        self.tr("写入导出记录（%s）") % MANIFEST_NAME
    )
    manifest_checkbox.setChecked(True)
    manifest_checkbox.setToolTip(
        self.tr(
            "写入导出记录 export_manifest.json / export record\n"
            "\n"
            "勾选后会在导出目录生成一份 JSON，记下本次导出的类别列表及其来源、"
            "筛选条件（仅已确认 / 跳过空标注 / 复制图片）、导出与跳过的数量，"
            "以及源数据的检查结果（无标注 / 空标注 / 读不出的文件 / "
            "不在类别表里的标签）。\n"
            "\n"
            "训练不读这个文件，删掉也不影响；它是为了几个月后还能回答"
            "「这批标签是怎么导出来的」。"
        )
    )
    layout.addWidget(manifest_checkbox)

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
    only_checked = only_checked_checkbox.isChecked()
    write_manifest_record = manifest_checkbox.isChecked()
    save_path = path_edit.text()
    image_list = self.image_list if self.image_list else [self.filename]

    def get_label_file(image_file):
        label_file_name = osp.splitext(osp.basename(image_file))[0] + ".json"
        label_dir = self.output_dir or osp.dirname(image_file)
        return osp.join(label_dir, label_file_name)

    skipped_unchecked = 0
    if only_checked:
        image_list, skipped_unchecked = split_images_by_review(
            image_list, get_label_file, True
        )
        logger.info(
            f"YOLO ({mode}) export filtered by review state: "
            f"{len(image_list)} confirmed, {skipped_unchecked} skipped"
        )
        if not image_list:
            popup = Popup(
                self.tr(
                    "没有「已确认」的图片可导出（共 %d 张未确认）。\n"
                    "先在文件列表里把要看过的图标成「已检查」，"
                    "或取消勾选「仅导出已确认的图片」。"
                )
                % skipped_unchecked,
                self,
                icon=new_icon_path("warning", "svg"),
            )
            popup.show_popup(self, position="center")
            return

    # The run reports its skips afterwards, which is too late for the two
    # findings that cannot be undone once the first file is written: shapes
    # whose label is outside the exported class list, and label files that
    # cannot be read. Check the files the run will read, before it reads them.
    readiness = check_export_readiness(image_list, get_label_file, classes)
    if is_blocking(readiness):
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        box.setWindowTitle(self.tr("导出前检查"))
        box.setText(self.tr("这批数据无法完整导出。"))
        box.setInformativeText(
            "\n".join(format_readiness(readiness))
            + "\n\n"
            + self.tr(
                "继续导出：类别不在表里的形状不会出现在结果里；"
                "读不出来的标注文件会让本轮导出中断，留下不完整的目录。"
            )
        )
        proceed_button = box.addButton(
            self.tr("仍然导出"),
            QtWidgets.QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = box.addButton(
            self.tr("Cancel"), QtWidgets.QMessageBox.ButtonRole.RejectRole
        )
        box.setDefaultButton(cancel_button)
        box.setStyleSheet(get_msg_box_style())
        box.exec()
        if box.clickedButton() is not proceed_button:
            return

    protected_dirs = {
        osp.dirname(path)
        for path in (self.image_list if self.image_list else [self.filename])
    }
    if (
        resolve_existing_output_dir(
            self, save_path, protected_paths=protected_dirs
        )
        == CANCEL
    ):
        return

    classes_target = None
    data_yaml_target = None
    if (
        write_classes_checkbox is not None
        and write_classes_checkbox.isChecked()
    ):
        classes_target = _write_classes_file(save_path, classes)
        data_yaml_target = _write_data_yaml(save_path, classes)

    progress_dialog = QProgressDialog(
        self.tr("Exporting..."), self.tr("Cancel"), 0, len(image_list), self
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Progress"))
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setStyleSheet(
        get_progress_dialog_style(color=get_theme()["text"], height=20)
    )

    try:
        stats = {}
        exported_files = 0
        copied_images = 0
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
                stats=stats,
            )
            exported_files += 1

            if save_images and not (skip_empty_files and is_empty_file):
                image_dst = osp.join(save_path, image_file_name)
                shutil.copy(image_file, image_dst)
                copied_images += 1

            if skip_empty_files and is_empty_file and osp.exists(dst_file):
                os.remove(dst_file)

            progress_dialog.setValue(i)
            if progress_dialog.wasCanceled():
                break

        progress_dialog.close()
        manifest_target = None
        if write_manifest_record:
            manifest_target = write_manifest(
                save_path,
                build_manifest(
                    mode=mode,
                    version=__version__,
                    image_dir=(
                        osp.dirname(self.filename) if self.filename else ""
                    ),
                    label_dir=self.output_dir
                    or osp.dirname(self.filename or ""),
                    classes=classes,
                    classes_source=classes_source,
                    filters={
                        "only_confirmed": only_checked,
                        "skip_empty_labels": skip_empty_files,
                        "save_with_images": save_images,
                        "write_classes_txt": classes_target is not None,
                    },
                    result={
                        "images_exported": exported_files,
                        "shapes_exported": stats.get("exported", 0),
                        "images_copied": copied_images,
                        "skipped_unconfirmed": skipped_unchecked,
                        "missing_label_files": stats.get(
                            "missing_label_file", 0
                        ),
                        "skipped_shapes": dict(stats.get("skipped") or {}),
                    },
                    readiness=readiness,
                ),
            )
        summary = _format_yolo_export_summary(
            self,
            exported_files,
            len(image_list),
            stats,
            copied_images,
            classes_target,
            skipped_unchecked=skipped_unchecked,
            data_yaml_target=data_yaml_target,
            manifest_target=manifest_target,
        )
        message_text = (
            self.tr(
                "Exporting annotations successfully!\n"
                "Results have been saved to:\n"
                "%s"
            )
            % save_path
        )
        message_text += "\n\n" + summary
        skipped_total = sum((stats.get("skipped") or {}).values())
        if skipped_total or stats.get("missing_label_file"):
            logger.warning(
                f"YOLO ({mode}) export finished with skips: "
                f"exported={stats.get('exported', 0)} "
                f"skipped={stats.get('skipped') or {}} "
                f"missing_label_file={stats.get('missing_label_file', 0)}"
            )
        popup = Popup(
            message_text,
            self,
            icon=new_icon_path(
                "warning" if skipped_total else "copy-green", "svg"
            ),
        )
        popup.show_popup(
            self,
            popup_height=95 + 18 * summary.count("\n"),
            position="center",
        )

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
        self.tr(
            "Skip empty labels / 跳过空标注\n"
            "\n"
            "默认关闭：空标注（确认无目标的负样本图）会导出为空文件，"
            "作为背景样本参与 YOLO 训练。\n"
            "\n"
            "勾选后：空标注的图片不会导出对应标签文件，这些负样本将从"
            "训练数据中排除（通常不建议，除非你确实不要背景样本）。"
        )
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

    protected_dirs = {
        osp.dirname(path)
        for path in (self.image_list if self.image_list else [self.filename])
    }
    if (
        resolve_existing_output_dir(
            self, save_path, protected_paths=protected_dirs
        )
        == CANCEL
    ):
        return

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
        get_progress_dialog_style(color=get_theme()["text"], height=20)
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
    protected_dirs = {
        osp.dirname(path)
        for path in (self.image_list if self.image_list else [self.filename])
    }
    if (
        resolve_existing_output_dir(
            self, save_path, protected_paths=protected_dirs
        )
        == CANCEL
    ):
        return

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
