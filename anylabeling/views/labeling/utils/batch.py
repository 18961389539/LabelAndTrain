import base64
import json
import os.path as osp
from PIL import Image

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QProgressDialog,
    QDialog,
    QLabel,
    QLineEdit,
    QDialogButtonBox,
    QApplication,
    QCheckBox,
    QListWidget,
    QPushButton,
)

from anylabeling.app_info import __version__
from anylabeling.views.labeling.utils.theme import get_theme
from anylabeling.services.auto_labeling import (
    _BATCH_PROCESSING_AUTO_GRID_MODELS,
    _BATCH_PROCESSING_INVALID_MODELS,
    _BATCH_PROCESSING_TEXT_PROMPT_MODELS,
    _SKIP_DET_MODELS,
)
from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.shape import Shape
from anylabeling.views.labeling.utils._io import io_open
from anylabeling.views.labeling.utils.yolo_detect import (
    merge_class_names,
    write_yolo_detect_sidecar,
)
from anylabeling.views.labeling.utils.qt import new_icon_path
from anylabeling.views.labeling.utils.style import get_msg_box_style
from anylabeling.views.labeling.widgets.popup import Popup

__all__ = ["run_all_images"]


class TextInputDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(self.tr("Enter Text Prompt"))
        self.setFixedSize(400, 180)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.MSWindowsFixedSizeDialogHint
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        prompt_label = QLabel(self.tr("Please enter your text prompt:"))
        prompt_label.setStyleSheet(
            f"font-size: 13px; color: {get_theme()['text']}; font-weight: 500;"
        )
        layout.addWidget(prompt_label)

        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText(self.tr("Enter prompt here..."))
        layout.addWidget(self.text_input)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)
        t = get_theme()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {t["background"]};
                border-radius: 10px;
            }}

            QLineEdit {{
                border: 1px solid {t["border"]};
                border-radius: 8px;
                background-color: {t["background_secondary"]};
                font-size: 13px;
                height: 36px;
                padding: 0 12px;
                color: {t["text"]};
            }}

            QLineEdit:hover {{
                background-color: {t["background_hover"]};
            }}

            QLineEdit:focus {{
                border: 2px solid {t["highlight"]};
                background-color: {t["background_secondary"]};
            }}

            QPushButton {{
                min-width: 100px;
                height: 36px;
                border-radius: 8px;
                font-weight: 500;
                font-size: 13px;
            }}

            QPushButton[text="OK"] {{
                background-color: {t["primary"]};
                color: white;
                border: none;
            }}

            QPushButton[text="OK"]:hover {{
                background-color: {t["primary_hover"]};
            }}

            QPushButton[text="OK"]:pressed {{
                background-color: {t["primary"]};
            }}

            QPushButton[text="Cancel"] {{
                background-color: {t["surface"]};
                color: {t["text"]};
                border: 1px solid {t["border"]};
            }}

            QPushButton[text="Cancel"]:hover {{
                background-color: {t["background_hover"]};
            }}

            QPushButton[text="Cancel"]:pressed {{
                background-color: {t["surface"]};
            }}
        """)

    def get_input_text(self):
        if self.exec() == QDialog.DialogCode.Accepted:
            return self.text_input.text().strip()
        return ""


class BatchRunOptionsDialog(QDialog):
    def __init__(self, parent, current_position, total_count):
        super().__init__(parent)
        self.setWindowTitle(self.tr("批量自动标注"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        if current_position < total_count:
            summary = self.tr(
                "将从当前图（#%d）处理到最后（#%d）。\n"
                "当前图之前的图片不会处理。"
            ) % (current_position, total_count)
        else:
            summary = self.tr("将只处理当前这一张图。")
        layout.addWidget(QLabel(summary))
        self.skip_existing = QCheckBox(self.tr("跳过已有标注的图片"))
        self.skip_existing.setChecked(True)
        self.skip_existing.setToolTip(
            self.tr("已有 JSON 标注的图片直接跳过，避免覆盖人工结果")
        )
        layout.addWidget(self.skip_existing)
        hint = QLabel(self.tr("处理过程中可点「暂停」随时停下。失败的图片结束后可点回去检查。"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def should_skip_existing(self):
        return self.skip_existing.isChecked()


class FailedImagesDialog(QDialog):
    def __init__(self, parent, failed_files):
        super().__init__(parent)
        self.setWindowTitle(self.tr("失败图片"))
        self.resize(480, 360)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(self.tr("以下图片自动标注失败，双击或点打开可跳转："))
        )
        self.list_widget = QListWidget()
        for path in failed_files:
            self.list_widget.addItem(path)
        self.list_widget.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.list_widget)
        buttons = QHBoxLayout()
        open_btn = QPushButton(self.tr("打开选中图片"))
        open_btn.clicked.connect(self.accept)
        close_btn = QPushButton(self.tr("关闭"))
        close_btn.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(open_btn)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

    def selected_path(self):
        item = self.list_widget.currentItem()
        if item is None:
            return None
        return item.text()


def get_image_size(image_path):
    with Image.open(image_path) as img:
        return img.size


def load_existing_shapes(image_file):
    """
    Loads existing shapes from the JSON file for skip detection.

    Args:
        image_file (str): The path to the image file.

    Returns:
        list: A list of Shape objects loaded from the JSON file, or None if
              the file does not exist or contains no shapes.
    """
    label_file = osp.splitext(image_file)[0] + ".json"
    if not osp.exists(label_file):
        return None

    try:
        with io_open(label_file, "r") as f:
            data = json.load(f)

        shapes = data.get("shapes", [])
        if not shapes:
            return None

        existing_shapes = []
        for shape_data in shapes:
            shape = Shape()
            shape.load_from_dict(shape_data, close=False)
            if shape.shape_type in ["rectangle", "rotation", "polygon"]:
                shape.selected = True
                existing_shapes.append(shape)

        return existing_shapes if existing_shapes else None

    except Exception as e:
        logger.warning(f"Failed to load existing shapes: {e}")
        return None


def image_has_annotations(image_file, output_dir=None):
    label_file = osp.splitext(image_file)[0] + ".json"
    if output_dir:
        label_file = osp.join(output_dir, osp.basename(label_file))
    if not osp.exists(label_file):
        return False
    try:
        with io_open(label_file, "r") as f:
            data = json.load(f)
        return bool(data.get("shapes"))
    except Exception:
        return False


def finish_processing(
    self, progress_dialog, succeeded=0, failed=0, failed_files=None
):
    if not getattr(self, "_batch_processing_active", False):
        progress_dialog.close()
        return

    try:
        target_file = self.image_list[self.current_index]
        self.import_image_folder(osp.dirname(target_file), load=False)
        target_index = self.fn_to_index[str(target_file)]
        signals_blocked = self.file_list_widget.blockSignals(True)
        try:
            self.file_list_widget.setCurrentRow(target_index)
        finally:
            self.file_list_widget.blockSignals(signals_blocked)
        self.load_file(target_file)
        QApplication.processEvents()
    finally:
        self._batch_failed_files = list(failed_files or [])
        _reset_batch_processing_state(self)
        progress_dialog.close()

    if succeeded == 0 and failed == 0:
        # Legacy callers without stats: keep the historical message.
        message = self.tr("Processing completed successfully!")
    else:
        total = succeeded + failed
        if failed > 0:
            message = self.tr(
                "Processing finished: %d succeeded, %d failed "
                "(of %d total)."
            ) % (succeeded, failed, total)
        else:
            message = self.tr(
                "Processing completed successfully! "
                "(%d images processed)"
            ) % total

    popup = Popup(
        message,
        self,
        icon=(
            new_icon_path("error", "svg")
            if failed > 0
            else new_icon_path("copy-green", "svg")
        ),
    )
    popup.show_popup(self, position="center")
    failed_files = getattr(self, "_batch_failed_files", None) or []
    if failed_files:
        dialog = FailedImagesDialog(self, failed_files)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            path = dialog.selected_path()
            if path:
                _jump_to_batch_image(self, path)


def cancel_operation(self):
    self.cancel_processing = True


def _jump_to_batch_image(self, image_file):
    if image_file not in getattr(self, "fn_to_index", {}):
        return
    index = self.fn_to_index[str(image_file)]
    signals_blocked = self.file_list_widget.blockSignals(True)
    try:
        self.file_list_widget.setCurrentRow(index)
    finally:
        self.file_list_widget.blockSignals(signals_blocked)
    self.load_file(image_file)


def _start_batch_processing(self):
    self._batch_processing_active = True
    show_progress_dialog_and_process(self)


def _reset_batch_processing_state(self):
    self._batch_processing_active = False
    self._batch_skip_if = None
    for attribute in (
        "text_prompt",
        "image_index",
        "current_index",
    ):
        if hasattr(self, attribute):
            delattr(self, attribute)


def save_auto_labeling_result(self, image_file, auto_labeling_result):
    try:
        label_file = osp.splitext(image_file)[0] + ".json"
        if self.output_dir:
            label_file = osp.join(self.output_dir, osp.basename(label_file))

        if auto_labeling_result is None:
            new_shapes = []
            new_description = ""
            replace = True
        else:
            new_shapes = [
                shape.to_dict() for shape in auto_labeling_result.shapes
            ]
            new_description = auto_labeling_result.description
            replace = auto_labeling_result.replace
        if osp.exists(label_file):
            with io_open(label_file, "r") as f:
                data = json.load(f)

            if replace:
                if not new_shapes and (data.get("shapes") or []):
                    # YOLO-consistent guard (mirrors the single-image path):
                    # an empty prediction never erases existing ground truth.
                    logger.info(
                        f"Batch auto labeling found no objects on "
                        f"{image_file}; keeping existing annotations "
                        f"(empty results never erase ground truth)."
                    )
                else:
                    data["shapes"] = new_shapes
                    data["description"] = new_description
            else:
                data["shapes"].extend(new_shapes)
                if "description" in data:
                    data["description"] += new_description
                else:
                    data["description"] = new_description
        else:
            if self._config["store_data"]:
                with open(image_file, "rb") as f:
                    image_data = f.read()
                image_data = base64.b64encode(image_data).decode("utf-8")
            else:
                image_data = None

            image_path = osp.basename(image_file)
            image_width, image_height = get_image_size(image_file)

            data = {
                "version": __version__,
                "flags": {},
                "shapes": new_shapes,
                "imagePath": image_path,
                "imageData": image_data,
                "imageHeight": image_height,
                "imageWidth": image_width,
                "description": new_description,
            }

        with io_open(label_file, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        try:
            extra_names = []
            unique_list = getattr(self, "unique_label_list", None)
            if unique_list is not None:
                for row in range(unique_list.count()):
                    item = unique_list.item(row)
                    if item is None:
                        continue
                    extra_names.append(item.data(Qt.ItemDataRole.UserRole))
            config = getattr(self, "_config", None) or {}
            write_yolo_detect_sidecar(
                label_file,
                data.get("shapes") or [],
                data.get("imageWidth") or 0,
                data.get("imageHeight") or 0,
                extra_class_names=merge_class_names(
                    extra_names, config.get("labels") or []
                ),
            )
        except Exception as e:  # noqa: BLE001
            logger.error(
                f"Failed to write YOLO txt for '{label_file}': {e}"
            )

        # Keep the file-list badge in sync: a saved file whose final shapes
        # are empty is a negative sample (background image) for YOLO.
        marker = getattr(self.app, "mark_file_item_negative_state", None)
        if marker is not None:
            try:
                marker(image_file, not (data.get("shapes") or []))
            except Exception:  # noqa: BLE001
                pass

        return True

    except Exception as e:
        logger.error(
            f"Failed to save auto labeling result for image file '{image_file}': {str(e)}"
        )
        return False


class BatchProcessingThread(QThread):
    progress_updated = pyqtSignal(int, str)
    processing_finished = pyqtSignal(int, int, list)  # succeeded, failed, failed_files
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        app,
        image_list,
        image_index,
        model_type,
        text_prompt,
        skip_detection,
        skip_existing=False,
        skip_if=None,
    ):
        super().__init__()
        self.app = app
        self.image_list = image_list
        self.image_index = image_index
        self.model_type = model_type
        self.text_prompt = text_prompt
        self.skip_detection = skip_detection
        self.skip_existing = skip_existing
        self.skip_if = skip_if
        self._succeeded = 0
        self._failed = 0
        self._failed_files = []

    def run(self):
        total_images = len(self.image_list)
        try:
            while (
                self.image_index < total_images
                and not self.app.cancel_processing
            ):
                image_file = self.image_list[self.image_index]
                image_index = self.image_index

                should_skip = False
                if self.skip_if is not None:
                    try:
                        should_skip = bool(self.skip_if(image_file))
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            f"Batch skip_if failed for {image_file}: {exc}"
                        )
                if not should_skip and self.skip_existing:
                    should_skip = image_has_annotations(
                        image_file, getattr(self.app, "output_dir", None)
                    )
                if should_skip:
                    self.image_index += 1
                    self.progress_updated.emit(
                        self.image_index,
                        f"Progress: {self.image_index}/{total_images}",
                    )
                    continue

                if self.text_prompt:
                    result = self.app.auto_labeling_widget.model_manager.predict_shapes(
                        self.app.image,
                        image_file,
                        text_prompt=self.text_prompt,
                        batch=True,
                    )
                else:
                    existing_shapes = None
                    if (
                        self.model_type in _SKIP_DET_MODELS
                        and self.skip_detection
                    ):
                        existing_shapes = load_existing_shapes(image_file)
                    result = self.app.auto_labeling_widget.model_manager.predict_shapes(
                        self.app.image,
                        image_file,
                        batch=True,
                        existing_shapes=existing_shapes,
                    )

                try:
                    saved = save_auto_labeling_result(
                        self.app, image_file, result
                    )
                except Exception as e:  # noqa: BLE001
                    logger.error(
                        f"Failed to save result for {image_file}: {e}"
                    )
                    saved = False

                if saved:
                    self._succeeded += 1
                else:
                    self._failed += 1
                    self._failed_files.append(image_file)
                    logger.warning(
                        f"Batch: image {image_index + 1}/{total_images} "
                        f"produced no result or failed to save: {image_file}"
                    )

                self.image_index += 1
                self.progress_updated.emit(
                    self.image_index,
                    f"Progress: {self.image_index}/{total_images}",
                )

            self.app.image_index = self.image_index
            self.processing_finished.emit(
                self._succeeded, self._failed, self._failed_files
            )
        except Exception as e:
            self.app.image_index = self.image_index
            self.error_occurred.emit(str(e))


def process_next_image(self, progress_dialog, batch=True):
    """Process images in batch mode.

    Args:
        progress_dialog: Progress dialog widget for displaying progress.
        batch: If True, results are saved directly without updating canvas.
               If False, results trigger UI updates and canvas refresh.
               Defaults to True for batch processing mode.
    """
    model_type = self.auto_labeling_widget.model_manager.loaded_model_config[
        "type"
    ]
    model = self.auto_labeling_widget.model_manager.loaded_model_config[
        "model"
    ]
    total_images = len(self.image_list)
    self._progress_dialog = progress_dialog


    skip_detection = (
        self.auto_labeling_widget.button_skip_detection.isChecked()
    )
    self._batch_thread = BatchProcessingThread(
        self,
        self.image_list,
        self.image_index,
        model_type,
        self.text_prompt,
        skip_detection,
        skip_existing=getattr(self, "_batch_skip_existing", False),
        skip_if=getattr(self, "_batch_skip_if", None),
    )

    def _on_progress(value, label):
        progress_dialog.setValue(value)
        progress_dialog.setLabelText(label)

    def _on_error(msg):
        _reset_batch_processing_state(self)
        progress_dialog.close()
        logger.error(f"Error occurred while processing images: {msg}")
        popup = Popup(
            self.tr("Error occurred while processing images!"),
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")

    self._batch_thread.progress_updated.connect(_on_progress)
    self._batch_thread.processing_finished.connect(
        lambda succeeded, failed, failed_files: finish_processing(
            self, progress_dialog, succeeded, failed, failed_files
        )
    )
    self._batch_thread.error_occurred.connect(_on_error)
    self._batch_thread.start()
    return


def show_progress_dialog_and_process(self):
    self.cancel_processing = False

    progress_dialog = QProgressDialog(
        self.tr("Processing..."),
        self.tr("暂停"),
        0,
        len(self.image_list),
        self,
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Batch Processing"))
    progress_dialog.setMinimumWidth(400)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setAutoClose(False)
    progress_dialog.setAutoReset(False)

    initial_progress = min(self.image_index, len(self.image_list))
    progress_dialog.setValue(initial_progress)
    progress_dialog.setLabelText(
        f"Progress: {initial_progress}/{len(self.image_list)}"
    )
    progress_bar = progress_dialog.findChild(QtWidgets.QProgressBar)

    if progress_bar:
        model_type = (
            self.auto_labeling_widget.model_manager.loaded_model_config.get(
                "type", ""
            )
        )

        def update_progress(value):
            progress_dialog.setLabelText(f"{value}/{len(self.image_list)}")

        progress_bar.valueChanged.connect(update_progress)

    t = get_theme()
    progress_dialog.setStyleSheet(f"""
        QProgressDialog {{
            background-color: {t["background"]};
            border-radius: 12px;
            min-width: 280px;
            min-height: 120px;
            padding: 20px;
        }}
        QProgressBar {{
            border: none;
            border-radius: 4px;
            background-color: {t["surface"]};
            text-align: center;
            color: {t["text"]};
            font-size: 13px;
            min-height: 20px;
            max-height: 20px;
            margin: 16px 0;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 {t["primary"]},
                stop:0.5 {t["highlight"]},
                stop:1 {t["primary"]});
            border-radius: 3px;
        }}
        QLabel {{
            color: {t["text"]};
            font-size: 13px;
            font-weight: 500;
            margin-bottom: 8px;
        }}
        QPushButton {{
            background-color: {t["surface"]};
            border: 1px solid {t["border"]};
            border-radius: 6px;
            font-weight: 500;
            font-size: 13px;
            color: {t["primary"]};
            min-width: 82px;
            height: 36px;
            padding: 0 16px;
            margin-top: 16px;
        }}
        QPushButton:hover {{
            background-color: {t["background_hover"]};
        }}
        QPushButton:pressed {{
            background-color: {t["surface"]};
        }}
    """)
    progress_dialog.canceled.connect(lambda: cancel_operation(self))
    progress_dialog.show()

    QTimer.singleShot(200, lambda: process_next_image(self, progress_dialog))


def run_all_images(
    self, *, prompt=True, from_start=False, skip_existing=None, skip_if=None
):
    if getattr(self, "_batch_processing_active", False):
        logger.warning("Batch processing is already running.")
        return

    if len(self.image_list) < 1:
        return

    if self.auto_labeling_widget.model_manager.loaded_model_config is None:
        self.auto_labeling_widget.model_manager.new_model_status.emit(
            self.tr("Model is not loaded. Choose a mode to continue.")
        )
        return

    if (
        self.auto_labeling_widget.model_manager.loaded_model_config["type"]
        in _BATCH_PROCESSING_INVALID_MODELS
    ):
        logger.warning(
            f"The model `{self.auto_labeling_widget.model_manager.loaded_model_config['type']}`"
            f" is not supported for this action."
            f" Please choose a valid model to execute."
        )
        self.auto_labeling_widget.model_manager.new_model_status.emit(
            self.tr(
                "Invalid model type, please choose a valid model_type to run."
            )
        )
        return

    if prompt:
        # Start from the currently opened image to the end of the list.
        current_position = (
            self.fn_to_index[str(self.filename)] + 1
            if self.filename and str(self.filename) in self.fn_to_index
            else 1
        )
        total_count = len(self.image_list)
        options = BatchRunOptionsDialog(self, current_position, total_count)
        if options.exec() != QDialog.DialogCode.Accepted:
            return
        self._batch_skip_existing = options.should_skip_existing()
        self._batch_skip_if = None
    else:
        self._batch_skip_existing = (
            bool(skip_existing) if skip_existing is not None else False
        )
        self._batch_skip_if = skip_if

    logger.info("Start running all images...")

    if from_start or not (
        self.filename and str(self.filename) in self.fn_to_index
    ):
        self.current_index = 0
        self.image_index = 0
    else:
        self.current_index = self.fn_to_index[str(self.filename)]
        self.image_index = self.current_index
    self.text_prompt = ""

    model_type = self.auto_labeling_widget.model_manager.loaded_model_config[
        "type"
    ]

    if model_type in _BATCH_PROCESSING_AUTO_GRID_MODELS:
        self.auto_labeling_widget.model_manager.set_auto_labeling_marks(
            [{"type": "auto_grid"}]
        )
        _start_batch_processing(self)
    elif model_type in _BATCH_PROCESSING_TEXT_PROMPT_MODELS:
        text_input_dialog = TextInputDialog(parent=self)
        self.text_prompt = text_input_dialog.get_input_text()
        if self.text_prompt:
            _start_batch_processing(self)
    else:
        _start_batch_processing(self)
