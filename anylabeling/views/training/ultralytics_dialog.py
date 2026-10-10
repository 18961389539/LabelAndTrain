import csv
import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import threading
import time

from PyQt6 import QtWidgets
from PyQt6.QtCore import (
    QCoreApplication,
    QRegularExpression,
    QTimer,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QIcon, QPixmap, QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QPushButton,
    QLabel,
    QMessageBox,
    QScrollArea,
    QGroupBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QProgressBar,
    QTextEdit,
    QApplication,
    QSizePolicy,
)

from anylabeling.config import get_config, save_config as save_labeling_config
from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils.qt import new_icon
from anylabeling.views.labeling.utils.theme import get_theme
from anylabeling.views.training.image_preview_dialog import (
    TrainingImagePreviewDialog,
)
from anylabeling.views.training.platform_open import open_path
from anylabeling.views.training.widgets.ultralytics_widgets import (
    CustomCheckBox,
    CustomComboBox,
    CustomDoubleSpinBox,
    CustomLineEdit,
    CustomQPushButton,
    CustomSlider,
    CustomSpinBox,
    CustomTable,
    ExportFormatDialog,
    PrimaryButton,
    SecondaryButton,
    TrainingStepBar,
)
from anylabeling.services.auto_training.ultralytics._io import (
    load_config,
    load_config_from_file,
    load_yaml_config,
    save_config,
    save_yaml_config,
)
from anylabeling.services.auto_training.ultralytics.config import (
    DEFAULT_TRAINING_CONFIG,
    DEFAULT_WINDOW_SIZE,
    DEFAULT_WINDOW_TITLE,
    DEVICE_OPTIONS,
    ICON_SIZE_NORMAL,
    MIN_LABELED_IMAGES_THRESHOLD,
    NUM_WORKERS,
    OPTIMIZER_OPTIONS,
    PRETRAINED_MODEL_PRESETS,
    TASK_TYPES,
    TRAINING_STATUS_COLORS,
    TRAINING_STATUS_TEXTS,
    get_dataset_path,
    get_default_project_dir,
    get_preset_models,
    get_settings_config_path,
    get_trainer_root_dir,
)
from anylabeling.services.auto_training.ultralytics.exporter import (
    ExportEventRedirector,
    ExportLogRedirector,
    get_export_manager,
    get_export_validator,
)
from anylabeling.services.auto_training.ultralytics.general import (
    collect_dataset_runs,
    create_yolo_dataset,
    directory_size,
    file_sha1,
    format_classes_display,
    load_dataset_manifest,
    parse_string_to_digit_list,
    plan_dataset_prune,
    prune_datasets,
)
from anylabeling.services.auto_training.ultralytics.style import (
    get_advanced_toggle_btn_style,
    get_image_label_style,
    get_log_display_style,
    get_progress_bar_style,
    get_status_label_style,
    get_ultralytics_dialog_style,
)
from anylabeling.services.auto_training.ultralytics.trainer import (
    TrainingEventRedirector,
    TrainingLogRedirector,
    get_training_manager,
)
from anylabeling.services.auto_training.ultralytics.utils import (
    TASK_SHAPE_MAPPINGS,
    autolabel_type_for_task,
    collect_class_names,
    dataset_overview_stats,
    estimate_remaining_seconds,
    get_label_infos,
    get_statistics_table_data,
    get_task_valid_images,
    parse_training_metrics,
    sanitize_custom_model_name,
    write_autolabel_model_yaml,
)
from anylabeling.services.auto_training.ultralytics.validators import (
    is_inside_directory,
    validate_basic_config,
    validate_classes,
    validate_data_file,
    validate_task_requirements,
)

#: Files/directories that mark a directory as a training run's output. The
#: overwrite confirmation deletes recursively, so a directory that has none of
#: them is not offered the option at all - the way ``utils/output_dir.py``
#: refuses to clear a folder that holds the images being annotated.
RUN_MARKERS = ("weights", "args.yaml", "results.csv")


def looks_like_training_run(path: str) -> bool:
    """True when ``path`` holds something one of our runs would have written."""
    if not path or not os.path.isdir(path):
        return False
    try:
        entries = os.listdir(path)
    except OSError:
        return False
    return any(marker in entries for marker in RUN_MARKERS)


#: How many offending paths a confirmation spells out. Enough to act on (the
#: first few are usually one bad script or one interrupted session), short
#: enough that the box stays readable; the full list is on disk either way.
MAX_LISTED_SKIPS = 5


def dataset_skips(report) -> list:
    """``[(kind, count, details)]`` for what a dataset build could not use.

    ``kind`` is ``"unreadable"`` (the label file is there but cannot be
    parsed), ``"failed"`` (the converter raised on it) or ``"dropped_shapes"``
    (shapes the task's mode cannot express). Pure data, so the dialog owns the
    wording: a ``tr()`` inside a module-level function never reaches the
    catalog, and the strings would ship untranslated.
    """
    report = report or {}
    skips = []
    unreadable = list(report.get("unreadable_labels") or [])
    if unreadable:
        skips.append(("unreadable", len(unreadable), unreadable))
    failed = [
        str(entry.get("label") or "")
        for entry in (report.get("conversion_errors") or [])
    ]
    if failed:
        skips.append(("failed", len(failed), failed))
    dropped = report.get("dropped_shapes") or {}
    if dropped:
        details = [
            f"{count} × {reason}"
            for reason, count in sorted(
                dropped.items(), key=lambda item: (-item[1], item[0])
            )
        ]
        skips.append(("dropped_shapes", sum(dropped.values()), details))
    return skips


def is_blocking_dataset_skip(kind: str) -> bool:
    """True for the skips that must be confirmed before a run starts.

    Same split as ``utils/export_check.is_blocking``: a file that cannot be
    used is irreversible in the sense that its annotations never reach the
    model, while a shape the mode cannot express is a known limitation and
    only gets counted.
    """
    return kind in ("unreadable", "failed")


def is_fresh_export(exported_path: str, weights_path: str) -> bool:
    """True when an already-exported artifact is not older than its weights.

    "用于自动标注" reuses ``weights/best.onnx`` when it exists, without
    comparing dates, so resuming a run and then reloading the model handed
    back the ONNX from before the resume — a run that looks finished with a
    model that is not the one on screen. An unreadable timestamp counts as
    stale, so the artifact is rebuilt rather than trusted.
    """
    if not exported_path or not weights_path:
        return False
    try:
        if not os.path.exists(exported_path):
            return False
        return os.path.getmtime(exported_path) >= os.path.getmtime(
            weights_path
        )
    except OSError:
        return False


#: What ``train_prefs`` may mirror into the dataset's ``.jllabel/project.json``.
#: Deliberately excluded: ``basic.project`` (global runs root), ``basic.name``
#: (run name), ``basic.data`` (temp dataset yaml rebuilt per run),
#: ``basic.device`` and ``train.workers`` (machine-specific) and
#: ``basic.dataset_ratio`` (data-tab split choice, not tuning). Everything
#: else is the tuning a user actually iterates on per dataset.
TRAIN_PREFS_BASIC_KEYS = ("model", "pose_config")
#: Untouched epochs/batch/imgsz are filled from this preset while the selected
#: device is CPU: with the GPU-oriented defaults (100 epochs at 640) a first
#: CPU pass can run for hours before it shows anything useful.
CPU_PARAM_PRESET = {"epochs": 50, "batch": 8, "imgsz": 416}
#: One-click tuning tiers. Unlike CPU_PARAM_PRESET these replace the fields
#: they name whatever the user had there — that is what a tier button is for —
#: and they answer one question: how hard should this run try? ``standard``
#: matches DEFAULT_TRAINING_CONFIG, so it doubles as "reset the pace".
TRAIN_PARAM_PRESETS = {
    "quick": {
        "epochs": 30,
        "imgsz": 416,
        "patience": 10,
        "close_mosaic": 5,
        "cos_lr": False,
    },
    "standard": {
        "epochs": 100,
        "imgsz": 640,
        "patience": 100,
        "close_mosaic": 10,
        "cos_lr": False,
    },
    "high": {
        "epochs": 300,
        "imgsz": 640,
        "patience": 100,
        "close_mosaic": 20,
        "cos_lr": True,
    },
}
#: Phrases that mean "raise less memory pressure" in a training traceback.
OOM_ERROR_MARKERS = ("out of memory", "allocate memory", "not enough memory")
#: Log view line cap: enough for a long run's tail, bounded so a chatty
#: worker cannot grow the widget without limit.
LOG_DISPLAY_MAX_LINES = 10000
TRAIN_PREFS_SECTIONS = (
    "train",
    "strategy",
    "learning_rate",
    "warmup",
    "augment",
    "regularization",
    "loss_weights",
    "checkpoint",
)


def _dataset_dir_for(dialog):
    """The open dataset's folder — the project's identity — or ``""``.

    Module-level and taking the dialog, not a method: the tests drive
    ``_project_train_prefs`` / ``_save_project_train_prefs`` with a
    ``SimpleNamespace`` stand-in, and a new ``self._helper()`` call would
    break every one of them (the stand-in has no such attribute).

    The widget's own project context wins over "where the first image
    lives". Opening a folder that contains annotated sub-folders scans
    them all (``scan_all_images`` recurses), so ``image_list[0]`` can sit
    inside a *different* folder than the one that was opened — and the
    tuning, and now the task kind, would be read from and written to the
    wrong project.
    """
    from anylabeling.views.labeling import project_settings

    # ``getattr`` twice: the tests drive the prefs helpers with a
    # SimpleNamespace stand-in, which has neither a ``parent`` nor the
    # attribute behind it.
    parent_fn = getattr(dialog, "parent", None)
    opened = (
        getattr(parent_fn(), "_project_dataset_dir", None)
        if callable(parent_fn)
        else None
    )
    if opened and os.path.isdir(str(opened)):
        return str(opened)
    return (
        project_settings.dataset_dir_for(
            image_list=getattr(dialog, "image_list", None)
        )
        or ""
    )


class UltralyticsDialog(QDialog):
    # Emitted from the background dataset-preparation thread when the YOLO
    # dataset build finishes (temp_dir_or_empty, error_message).
    dataset_preparation_finished = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(DEFAULT_WINDOW_TITLE)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(*DEFAULT_WINDOW_SIZE)
        self.setMinimumSize(*DEFAULT_WINDOW_SIZE)

        self.image_list = parent.image_list
        self.output_dir = parent.output_dir
        self.supported_shape = parent.supported_shape
        self.selected_task_type = None
        self.config_widgets = {}
        self._classification_cache = None
        self._detection_cache = None
        self._valid_image_count_cache = {}
        self._summary_view_mode = None
        self._config_tab_initialized = False
        self._train_tab_initialized = False
        self.task_type_buttons = {}
        self.names = []

        # Training related attributes
        self.log_redirector = TrainingLogRedirector()
        self.log_redirector.log_signal.connect(
            self.append_training_log, Qt.ConnectionType.QueuedConnection
        )
        self.event_redirector = TrainingEventRedirector()
        self.event_redirector.training_event_signal.connect(
            self.on_training_event, Qt.ConnectionType.QueuedConnection
        )
        self.training_manager = get_training_manager()
        self.training_manager.callbacks = [
            self.event_redirector.emit_training_event
        ]

        # Export related attributes
        # The export worker redirects sys.stdout/stderr to the manager's
        # log_redirector; connect its signal here so ultralytics export
        # progress actually shows up in the log view.
        self.export_event_redirector = ExportEventRedirector()
        self.export_event_redirector.export_event_signal.connect(
            self.on_export_event, Qt.ConnectionType.QueuedConnection
        )
        self.export_manager = get_export_manager()
        self.export_manager.log_redirector.log_signal.connect(
            self.append_training_log, Qt.ConnectionType.QueuedConnection
        )
        self.export_manager.callbacks = [
            self.export_event_redirector.emit_export_event
        ]

        self.progress_timer = QTimer()
        self.progress_timer.timeout.connect(self.update_training_progress)
        self.image_timer = QTimer()
        self.image_timer.timeout.connect(self.update_training_images)
        self.current_project_path = None
        self.training_status = "idle"  # idle, training, completed, error
        self.current_epochs = 0
        self._pending_autolabel_after_export = False
        # Set when the user picks "resume": the run continues from its own
        # last.pt, so the dataset is rebuilt but the tuning comes from the
        # checkpoint instead of the config form.
        self._resume_from = None
        self._resume_info = None
        # AMP is forced off while the device is CPU; this remembers whether it
        # was on, so switching back to a GPU device does not silently lose it.
        self._amp_before_cpu = False
        self._loading_config = False
        # What the last log-file write contained, so a terminal state and the
        # window close do not write the same text twice.
        self._last_saved_log_text = None

        # Background dataset preparation (kept off the UI thread so large
        # image sets do not freeze the dialog while YOLO files are written).
        self._dataset_thread = None
        self._dataset_pending_config = None
        self.dataset_preparation_finished.connect(
            self._on_dataset_preparation_finished
        )

        app_config = get_config()
        self.project_readonly = (
            app_config.get("training", {})
            .get("ultralytics", {})
            .get("project_readonly", True)
        )

        self.init_ui()
        self.setStyleSheet(get_ultralytics_dialog_style())
        self.refresh_dataset_summary()
        self.update_labeled_images_hint()
        self.refresh_wizard_state()

    def init_ui(self):
        self.data_tab = QWidget()
        self.config_tab = QWidget()
        self.train_tab = QWidget()

        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.data_tab, self.tr("Data"))
        self.tab_widget.addTab(self.config_tab, self.tr("Config"))
        self.tab_widget.addTab(self.train_tab, self.tr("Train"))
        self.tab_widget.tabBar().setEnabled(False)
        self.step_bar = TrainingStepBar()
        self.step_bar.step_clicked.connect(self.on_step_bar_clicked)
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.step_bar)
        main_layout.addWidget(self.tab_widget)

        self.init_data_tab()

    def ensure_config_tab_initialized(self):
        if self._config_tab_initialized:
            return
        self.init_config_tab()
        self._config_tab_initialized = True

    def ensure_train_tab_initialized(self):
        if self._train_tab_initialized:
            return
        self.init_train_tab()
        self._train_tab_initialized = True

    def save_training_logs_to_file(self, force=False):
        """Write the log view beside the run, returning the path written.

        Called whenever a run reaches a terminal state — not only when the
        window closes — so a crash, a force-quit or a machine that dies
        mid-session cannot take the only copy of the log with it. Identical
        content is never written twice; ``force`` overrides that.
        """
        if not hasattr(self, "log_display"):
            return None
        text = self.log_display.toPlainText()
        if not text.strip():
            return None
        if not self.current_project_path or not os.path.exists(
            self.current_project_path
        ):
            return None
        if not force and text == self._last_saved_log_text:
            return None

        try:
            log_dir_path = os.path.join(self.current_project_path, "logs")
            os.makedirs(log_dir_path, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            stem = f"training_log_{self.training_status}_{timestamp}"
            log_file_path = os.path.join(log_dir_path, f"{stem}.txt")
            # Second-granularity names collide when two terminal states land
            # together; the earlier snapshot is worth keeping.
            suffix = 2
            while os.path.exists(log_file_path):
                log_file_path = os.path.join(
                    log_dir_path, f"{stem}_{suffix}.txt"
                )
                suffix += 1

            with open(log_file_path, "w", encoding="utf-8") as f:
                f.write(text)
            self._last_saved_log_text = text
            logger.info(f"Training logs saved to: {log_file_path}")
            return log_file_path

        except Exception as e:
            logger.error(f"Failed to save training logs: {str(e)}")
            return None

    def closeEvent(self, event):
        """Handle window close event"""
        if (
            self._dataset_thread is not None
            and self._dataset_thread.is_alive()
        ):
            QMessageBox.warning(
                self,
                self.tr("Dataset Preparation in Progress"),
                self.tr(
                    "Cannot close window while the dataset is being prepared. "
                    "Please wait for it to finish."
                ),
            )
            event.ignore()
            return

        if self.training_status == "training":
            QMessageBox.warning(
                self,
                self.tr("Training in Progress"),
                self.tr(
                    "Cannot close window while training is in progress. Please stop training first."
                ),
            )
            event.ignore()
            return

        if self.training_status in ["completed", "error", "stop"]:
            self.save_training_logs_to_file()

        # Detach callbacks held by the module-level singletons so they do not
        # reference this (about-to-be-destroyed) dialog after close.
        self.training_manager.callbacks = []
        self.export_manager.callbacks = []

        self.clear_cache()
        super().closeEvent(event)

    def go_to_specific_tab(self, index):
        """Go to specific tab by index"""
        if index >= 1:
            self.ensure_config_tab_initialized()
        if index >= 2:
            self.ensure_train_tab_initialized()
        self.tab_widget.setCurrentIndex(index)
        self.refresh_wizard_state()

    # Data Tab
    def show_pose_config(self):
        """Show the pose config field"""
        if hasattr(self, "pose_config_label"):
            self.pose_config_label.setVisible(True)
            self.config_widgets["pose_config"].setVisible(True)

            for i in range(self.pose_config_layout.count()):
                widget = self.pose_config_layout.itemAt(i).widget()
                if widget:
                    widget.setVisible(True)

    def hide_pose_config(self):
        """Hide the pose config field"""
        if hasattr(self, "pose_config_label"):
            self.pose_config_label.setVisible(False)
            self.config_widgets["pose_config"].setVisible(False)

            for i in range(self.pose_config_layout.count()):
                widget = self.pose_config_layout.itemAt(i).widget()
                if widget:
                    widget.setVisible(False)

    def on_task_type_selected(self, task_type):
        normalized_task_type = None
        for task in TASK_TYPES:
            if task.lower() == task_type.lower():
                normalized_task_type = task
                break

        if normalized_task_type is None:
            logger.warning(f"Unknown task type: {task_type}")
            return

        task_type = normalized_task_type

        if task_type not in self.task_type_buttons:
            logger.warning(f"Task type button not found: {task_type}")
            return

        if self.selected_task_type == task_type:
            self.selected_task_type = None
            self.task_type_buttons[task_type].set_selected(False)
            self.hide_pose_config()
        else:
            if self.selected_task_type:
                self.task_type_buttons[self.selected_task_type].set_selected(
                    False
                )
            self.selected_task_type = task_type
            self.task_type_buttons[task_type].set_selected(True)

            if task_type.lower() == "pose":
                self.show_pose_config()
            else:
                self.hide_pose_config()

        self.refresh_dataset_summary()
        self.update_labeled_images_hint()
        self.refresh_wizard_state()

    def create_task_handler(self, task_type):
        def handler():
            self.on_task_type_selected(task_type)

        return handler

    def init_task_configuration(self, parent_layout):
        config_widget = QWidget()
        config_layout = QVBoxLayout(config_widget)

        task_type_layout = QHBoxLayout()
        task_type_layout.addWidget(QLabel(self.tr("Task Type:")))
        for task_type in TASK_TYPES:
            button = CustomQPushButton(task_type)
            button.clicked.connect(self.create_task_handler(task_type))
            task_type_layout.addWidget(button)
            self.task_type_buttons[task_type] = button

        task_type_layout.addStretch()
        self.labeled_images_hint = QLabel()
        self.labeled_images_hint.setVisible(False)
        self.labeled_images_hint.setStyleSheet(
            f"color: {get_theme()['text_secondary']}; font-size: 10px;"
        )
        task_type_layout.addWidget(self.labeled_images_hint)
        config_layout.addLayout(task_type_layout)
        parent_layout.addWidget(config_widget)

    def update_labeled_images_hint(self):
        if not self.selected_task_type:
            self.labeled_images_hint.setVisible(False)
            return

        if self.selected_task_type not in self._valid_image_count_cache:
            self._valid_image_count_cache[self.selected_task_type] = (
                get_task_valid_images(
                    self.image_list,
                    self.selected_task_type,
                    self.output_dir,
                )
            )

        valid_images = self._valid_image_count_cache[self.selected_task_type]
        theme = get_theme()
        color = (
            theme["success"]
            if valid_images >= MIN_LABELED_IMAGES_THRESHOLD
            else theme["error"]
        )
        self.labeled_images_hint.setText(
            f'{self.tr("Valid Images:")} {valid_images} | '
            f'{self.tr("Required:")} <span style="color: {color};">'
            f"{MIN_LABELED_IMAGES_THRESHOLD}</span>"
        )
        self.labeled_images_hint.setVisible(True)

    def refresh_dataset_summary(self):
        if not self.image_list:
            self.summary_table.clear()
            self._summary_view_mode = None
            self._update_dataset_headline()
            return

        summary_view_mode = (
            "classify" if self.selected_task_type == "Classify" else "detect"
        )
        if self._summary_view_mode != summary_view_mode:
            if summary_view_mode == "classify":
                table_data = self._get_classification_table_data()
            else:
                table_data = self._get_detection_table_data()
            self.summary_table.load_data(table_data)
            self._summary_view_mode = summary_view_mode
        self._update_dataset_headline()

    def _update_dataset_headline(self):
        if not hasattr(self, "dataset_headline"):
            return
        total, labeled, empty, class_count = dataset_overview_stats(
            self.image_list, self.output_dir
        )
        if total <= 0:
            self.dataset_headline.setText(
                self.tr(
                    "No images yet. Open a folder in the main window first."
                )
            )
            return
        self.dataset_headline.setText(
            self.tr("%1 images · %2 classes · %3 labeled · %4 empty")
            .replace("%1", str(total))
            .replace("%2", str(class_count))
            .replace("%3", str(labeled))
            .replace("%4", str(empty))
        )

    def refresh_wizard_state(self):
        if not hasattr(self, "step_bar"):
            return
        current = self.tab_widget.currentIndex()
        valid_images = 0
        if self.selected_task_type:
            if self.selected_task_type not in self._valid_image_count_cache:
                self.update_labeled_images_hint()
            valid_images = self._valid_image_count_cache.get(
                self.selected_task_type, 0
            )
        if not self.selected_task_type:
            data_hint = self.tr("Select a task type")
        elif valid_images < MIN_LABELED_IMAGES_THRESHOLD:
            remain = MIN_LABELED_IMAGES_THRESHOLD - valid_images
            data_hint = self.tr("%1 more labeled image(s) needed").replace(
                "%1", str(remain)
            )
        else:
            data_hint = self.tr("Data is ready")
        config_hint = self.tr("Set model and hyperparameters")
        train_hint = {
            "preparing": self.tr("Preparing dataset"),
            "training": self.tr("Training in Progress"),
            "completed": self.tr("Training completed"),
            "error": self.tr("Training Failed"),
        }.get(
            self.training_status, self.tr("Start training and watch the log")
        )
        self.step_bar.set_state(current, [data_hint, config_hint, train_hint])

    def on_step_bar_clicked(self, index):
        if index <= self.tab_widget.currentIndex():
            self.go_to_specific_tab(index)
            return
        if index == 1:
            self.proceed_to_config()
            return
        if index == 2:
            if self.tab_widget.currentIndex() < 1:
                self.proceed_to_config()
                return
            self.go_to_specific_tab(2)

    def _get_classification_table_data(self):
        if self._classification_cache is None:
            self._classification_cache = self._compute_classification_data()
        return self._classification_cache

    def _get_detection_table_data(self):
        if self._detection_cache is None:
            self._detection_cache = self._compute_detection_data()
        return self._detection_cache

    def _compute_classification_data(self):
        headers = ["Label"] + self.supported_shape + ["Total"]

        # Get classification statistics
        classify_shapes = TASK_SHAPE_MAPPINGS.get("Classify", ["flags"])
        label_infos = get_label_infos(
            self.image_list, classify_shapes, self.output_dir
        )
        if not label_infos:
            return [headers]

        table_data = [headers]
        total_counts = [0] * len(self.supported_shape)
        total_images = 0

        for label, infos in sorted(label_infos.items()):
            # All shape columns are 0 for classification
            shape_counts = [0] * len(self.supported_shape)
            image_count = infos.get("_total", 0)
            total_images += image_count

            row = [label] + [str(c) for c in shape_counts] + [str(image_count)]
            table_data.append(row)

        total_row = (
            ["Total"] + [str(c) for c in total_counts] + [str(total_images)]
        )
        table_data.append(total_row)

        return table_data

    def _compute_detection_data(self):
        return get_statistics_table_data(
            self.image_list, self.supported_shape, self.output_dir
        )

    def clear_cache(self):
        self._classification_cache = None
        self._detection_cache = None
        self._valid_image_count_cache.clear()
        self._summary_view_mode = None

    def load_images(self):
        self.parent().open_folder_dialog()
        self.image_list = self.parent().image_list
        self.clear_cache()
        self.refresh_dataset_summary()
        self.update_labeled_images_hint()
        self.refresh_wizard_state()

    def init_dataset_summary(self, parent_layout):
        summary_widget = QWidget()
        summary_layout = QVBoxLayout(summary_widget)
        self.dataset_headline = QLabel("")
        self.dataset_headline.setWordWrap(True)
        self.dataset_headline.setStyleSheet(
            "font-size: 18px; font-weight: 700; padding: 4px 0 8px 0;"
        )
        summary_layout.addWidget(self.dataset_headline)
        summary_layout.addWidget(QLabel(self.tr("Dataset Summary:")))

        self.summary_table = CustomTable()
        summary_layout.addWidget(self.summary_table)
        parent_layout.addWidget(summary_widget, 1)

    def proceed_to_config(self):
        is_valid, error_message = validate_task_requirements(
            self.selected_task_type, self.image_list, self.output_dir
        )
        if not is_valid:
            QMessageBox.warning(
                self, self.tr("Validation Error"), error_message
            )
            return

        self.ensure_config_tab_initialized()
        project = os.path.join(
            get_default_project_dir(), self.selected_task_type.lower()
        )
        self.config_widgets["project"].setText(project)
        self.config_widgets["project"].setReadOnly(self.project_readonly)
        self._refresh_task_config_fields()

        self.go_to_specific_tab(1)

    def _refresh_task_config_fields(self):
        """Re-align task-dependent fields after the task type may have changed."""
        self._reload_model_presets()
        is_classify = (self.selected_task_type or "").lower() == "classify"
        if hasattr(self, "data_autofill_btn"):
            # Classification has no class-list yaml to regenerate.
            self.data_autofill_btn.setVisible(not is_classify)
        if is_classify:
            # Classification runs without a Data path (flags, or a directory
            # the user picks); a stale path from another task would only
            # block validation, so drop the ones that no longer resolve.
            widget = self.config_widgets.get("data")
            if widget is not None:
                current = widget.text().strip().strip('"')
                if current and not os.path.exists(current):
                    widget.clear()
            return
        self._ensure_data_file()

    def on_model_preset_activated(self, index):
        """Fill the Model field from the preset dropdown."""
        combo = self.model_preset_combo
        if index <= 0:
            return
        self.config_widgets["model"].setText(combo.itemText(index))
        combo.setCurrentIndex(0)

    def _reload_model_presets(self):
        """Refresh the Model preset list for the selected task type.

        Also swaps a preset left over from another task (e.g. ``-seg`` after
        switching to Detect), which ultralytics would reject at train time.
        """
        combo = getattr(self, "model_preset_combo", None)
        widget = self.config_widgets.get("model")
        if combo is None or widget is None:
            return

        presets = get_preset_models(self.selected_task_type or "Detect")
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(self.tr("Preset weights..."))
        combo.addItems(presets)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

        current = widget.text().strip().strip('"')
        known_names = {
            name
            for names in PRETRAINED_MODEL_PRESETS.values()
            for name in names
        }
        if current in known_names and current not in presets:
            widget.setText(presets[0] if presets else "")
        elif not current and presets:
            widget.setText(presets[0])

    def _generated_data_path(self):
        """Stable class-list yaml path for the open folder + current task."""
        label_dir = self.output_dir
        if not label_dir and self.image_list:
            label_dir = os.path.dirname(self.image_list[0])
        if not label_dir:
            return None
        stem = sanitize_custom_model_name(
            os.path.basename(os.path.normpath(label_dir)) or "dataset"
        )
        digest = hashlib.md5(
            os.path.abspath(label_dir).encode("utf-8")
        ).hexdigest()[:8]
        task = (self.selected_task_type or "detect").lower()
        return os.path.join(
            get_trainer_root_dir(),
            "data",
            f"{stem}_{digest}_{task}.yaml",
        )

    def _ensure_data_file(self, force=False):
        """Generate/refresh the Data field's class list for the open folder.

        The Data field only supplies class names for det/seg/pose runs; the
        dataset itself is rebuilt on every training. Files under the trainer's
        generated-data directory are rewritten freely, while a yaml the user
        picked is never touched. Returns True when the field holds a valid
        generated file.
        """
        if (self.selected_task_type or "").lower() == "classify":
            # Classification derives its classes from flags or a directory.
            return False
        widget = self.config_widgets.get("data")
        target = self._generated_data_path()
        if widget is None or not target:
            return False

        current = widget.text().strip().strip('"')
        generated_dir = os.path.normpath(os.path.dirname(target))
        if (
            current
            and os.path.normpath(os.path.dirname(os.path.normpath(current)))
            != generated_dir
        ):
            return False

        classes = collect_class_names(self.image_list, self.output_dir)
        if not classes:
            if force:
                QMessageBox.warning(
                    self,
                    self.tr("No Classes Found"),
                    self.tr(
                        "This folder's labels do not contain any class names "
                        "yet. Label at least one image first."
                    ),
                )
            return False

        os.makedirs(generated_dir, exist_ok=True)
        payload = {"names": dict(enumerate(classes))}
        if not save_yaml_config(payload, target):
            if force:
                QMessageBox.warning(
                    self,
                    self.tr("Write Failed"),
                    self.tr("Could not write the data file:\n%1").replace(
                        "%1", target
                    ),
                )
            return False

        widget.setText(target)
        if force:
            self.append_training_log(
                self.tr("Regenerated the data file from labels: %1").replace(
                    "%1", target
                )
            )
        return True

    def init_actions(self, parent_layout):
        actions_layout = QHBoxLayout()

        self.load_images_button = SecondaryButton(self.tr("Load Images"))
        self.load_images_button.clicked.connect(self.load_images)
        actions_layout.addWidget(self.load_images_button)
        actions_layout.addStretch()

        self.next_button = PrimaryButton(self.tr("Next"))
        self.next_button.clicked.connect(self.proceed_to_config)
        actions_layout.addWidget(self.next_button)
        parent_layout.addLayout(actions_layout)

    def init_data_tab(self):
        layout = QVBoxLayout(self.data_tab)

        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        self.init_task_configuration(scroll_layout)
        self.init_dataset_summary(scroll_layout)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        self.init_actions(layout)
        # Last, once every widget the handler touches exists: the project's
        # declared task is preselected so the Data tab opens knowing what
        # this dataset is for.
        self._apply_project_task()

    # Config Tab
    def browse_model_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Select Model File"),
            "",
            "Model Files (*.pt);;All Files (*)",
        )
        if file_path:
            self.config_widgets["model"].setText(file_path)

    def browse_data_file(self):
        if self.selected_task_type == "Classify":
            dir_path = QFileDialog.getExistingDirectory(
                self, self.tr("Select Classification Dataset Directory"), ""
            )
            if dir_path:
                self.config_widgets["data"].setText(dir_path)
        else:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                self.tr("Select Data File"),
                "",
                "Text Files (*.yaml);;All Files (*)",
            )
            if file_path:
                is_valid, result = validate_data_file(file_path)
                if is_valid:
                    self.config_widgets["data"].setText(file_path)
                    self.names = result
                    logger.info(f"Data file loaded successfully: {file_path}")
                else:
                    QMessageBox.warning(
                        self, self.tr("Invalid Data File"), result
                    )
                    self.config_widgets["data"].clear()
                    self.names = []

    def browse_pose_config_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Select Pose Config File"),
            "",
            "YAML Files (*.yaml *.yml);;All Files (*)",
        )
        if file_path:
            self.config_widgets["pose_config"].setText(file_path)

    def setup_cuda_checkboxes(self, device_count):
        if not hasattr(self, "_cuda_layout") or not self._cuda_layout:
            if self.device_checkboxes.layout() is None:
                self._cuda_layout = QHBoxLayout(self.device_checkboxes)
            else:
                self._cuda_layout = self.device_checkboxes.layout()
            self._cuda_layout.setContentsMargins(0, 0, 0, 0)
            self._cuda_layout.setSpacing(5)
        else:
            while self._cuda_layout.count():
                child = self._cuda_layout.takeAt(0)
                if child.widget():
                    child.widget().setParent(None)

        for i in range(device_count):
            checkbox = CustomCheckBox(f"GPU {i}")
            checkbox.setMaximumHeight(20)
            checkbox.setChecked(True)  # Default check all GPUs
            self._cuda_layout.addWidget(checkbox)

    def on_device_changed(self, device_text):
        if device_text == "cuda":
            try:
                import torch

                if os.environ.get("CUDA_VISIBLE_DEVICES") == "-1":
                    cuda_visible_devices_backup = os.environ.get(
                        "CUDA_VISIBLE_DEVICES"
                    )
                    del os.environ["CUDA_VISIBLE_DEVICES"]
                    torch.cuda.empty_cache()
                    device_count = torch.cuda.device_count()
                    if cuda_visible_devices_backup != "-1":
                        os.environ["CUDA_VISIBLE_DEVICES"] = (
                            cuda_visible_devices_backup
                        )
                else:
                    device_count = torch.cuda.device_count()

                self.setup_cuda_checkboxes(device_count)
                self.device_checkboxes.setVisible(True)
            except ImportError:
                self.device_checkboxes.setVisible(False)
        else:
            self.device_checkboxes.setVisible(False)
        self._sync_cpu_device_options()

    def _sync_cpu_device_options(self):
        """Keep AMP and the parameter defaults honest for the chosen device.

        CPU ignores AMP (ultralytics switches it off itself) and the
        GPU-oriented defaults make a first CPU pass needlessly slow, so AMP is
        unchecked/disabled and untouched epochs/batch/imgsz get a CPU preset.
        """
        if getattr(self, "_loading_config", False):
            # The config load applies device and amp in separate passes;
            # load_config_to_ui calls this again once both are in.
            return
        device_widget = self.config_widgets.get("device")
        if device_widget is None:
            return
        is_cpu = device_widget.currentText() == "cpu"
        self._apply_amp_for_device(is_cpu)
        filled = self._apply_cpu_preset() if is_cpu else []
        self._update_device_hint(is_cpu, filled)

    def _apply_amp_for_device(self, is_cpu):
        """Force AMP off while the device is CPU; restore the choice after."""
        amp_widget = self.config_widgets.get("amp")
        if amp_widget is None:
            return
        if is_cpu:
            if amp_widget.isChecked():
                self._amp_before_cpu = True
                amp_widget.setChecked(False)
            amp_widget.setEnabled(False)
            amp_widget.setToolTip(
                self.tr(
                    "AMP has no effect on CPU, so it stays off while the "
                    "device is CPU."
                )
            )
            return
        amp_widget.setEnabled(True)
        amp_widget.setToolTip(
            self.tr("Mixed precision: faster on CUDA, no effect on CPU.")
        )
        if (
            getattr(self, "_amp_before_cpu", False)
            and not amp_widget.isChecked()
        ):
            amp_widget.setChecked(True)
        self._amp_before_cpu = False

    def _apply_cpu_preset(self):
        """Fill CPU-friendly values into the fields still at their defaults."""
        filled = []
        for key, value in CPU_PARAM_PRESET.items():
            widget = self.config_widgets.get(key)
            if (
                widget is None
                or widget.value() != DEFAULT_TRAINING_CONFIG[key]
            ):
                continue
            widget.setValue(value)
            filled.append(f"{key}={value}")
        return filled

    def _update_device_hint(self, is_cpu, filled):
        """One line under Device explaining what CPU changed and why."""
        if not hasattr(self, "device_hint"):
            return
        if not is_cpu:
            self.device_hint.setVisible(False)
            return
        text = self.tr("CPU training is much slower than GPU.")
        if filled:
            text += " " + self.tr(
                "Default values were replaced with a CPU-friendly preset "
                "(%1); adjust them in Train Settings if needed."
            ).replace("%1", " / ".join(filled))
        self.device_hint.setText(text)
        self.device_hint.setVisible(True)

    def init_basic_settings(self, parent_layout):
        group = QGroupBox(self.tr("Basic Settings"))
        layout = QFormLayout(group)
        layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)

        self.config_widgets["project"] = CustomLineEdit()
        selected_task_type = (
            self.selected_task_type.lower()
            if self.selected_task_type
            else "detect"
        )
        text_project = os.path.join(
            get_default_project_dir(), selected_task_type
        )
        self.config_widgets["project"].setText(text_project)
        layout.addRow(self.tr("Project:"), self.config_widgets["project"])

        self.config_widgets["name"] = CustomLineEdit()
        self.config_widgets["name"].setText("exp")
        # A run name is one directory, never a path. Project and Name are
        # joined into the directory the overwrite confirmation deletes
        # recursively, so a pasted path (or "..") in this field used to point
        # that delete at a folder the user never named - ``os.path.join``
        # drops the Project part entirely when the second one is absolute.
        # The leading-dot block also rules out "." and "..".
        self.config_widgets["name"].setValidator(
            QRegularExpressionValidator(
                QRegularExpression(r'[^/\\:*?"<>|.][^/\\:*?"<>|]*'),
                self,
            )
        )
        self.config_widgets["name"].setToolTip(
            self.tr(
                "Folder name for this run, inside the Project folder. One folder name only - no path separators."
            )
        )
        layout.addRow(self.tr("Name:"), self.config_widgets["name"])

        model_layout = QHBoxLayout()
        self.config_widgets["model"] = CustomLineEdit()
        self.config_widgets["model"].setPlaceholderText(
            self.tr("e.g. yolov8n.pt (downloaded when training starts)")
        )
        model_browse_btn = SecondaryButton(self.tr("Browse"))
        model_browse_btn.clicked.connect(self.browse_model_file)
        self.model_preset_combo = CustomComboBox()
        self.model_preset_combo.setToolTip(
            self.tr("Pick a common pretrained checkpoint")
        )
        self.model_preset_combo.activated.connect(
            self.on_model_preset_activated
        )
        model_layout.addWidget(self.config_widgets["model"])
        model_layout.addWidget(self.model_preset_combo)
        model_layout.addWidget(model_browse_btn)
        layout.addRow(self.tr("Model:"), model_layout)

        data_layout = QHBoxLayout()
        self.config_widgets["data"] = CustomLineEdit()
        self.config_widgets["data"].setToolTip(
            self.tr(
                "Only the class list matters here; the dataset itself is "
                "rebuilt on every run."
            )
        )
        data_browse_btn = SecondaryButton(self.tr("Browse"))
        data_browse_btn.clicked.connect(self.browse_data_file)
        self.data_autofill_btn = SecondaryButton(self.tr("From Labels"))
        self.data_autofill_btn.setToolTip(
            self.tr(
                "Regenerate the class-list yaml from the open folder's labels"
            )
        )
        self.data_autofill_btn.clicked.connect(
            lambda: self._ensure_data_file(force=True)
        )
        data_layout.addWidget(self.config_widgets["data"])
        data_layout.addWidget(self.data_autofill_btn)
        data_layout.addWidget(data_browse_btn)
        layout.addRow(self.tr("Data:"), data_layout)

        pose_config_layout = QHBoxLayout()
        self.config_widgets["pose_config"] = CustomLineEdit()
        pose_config_browse_btn = SecondaryButton(self.tr("Browse"))
        pose_config_browse_btn.clicked.connect(self.browse_pose_config_file)
        pose_config_layout.addWidget(self.config_widgets["pose_config"])
        pose_config_layout.addWidget(pose_config_browse_btn)

        self.pose_config_label = QLabel(self.tr("Pose Config:"))
        layout.addRow(self.pose_config_label, pose_config_layout)
        self.pose_config_layout = pose_config_layout

        self.pose_config_label.setVisible(False)
        self.config_widgets["pose_config"].setVisible(False)
        pose_config_browse_btn.setVisible(False)

        device_layout = QHBoxLayout()
        self.config_widgets["device"] = CustomComboBox()
        self.config_widgets["device"].addItems(DEVICE_OPTIONS)
        self.device_checkboxes = QWidget()
        self.device_checkboxes.setVisible(False)
        self.config_widgets["device"].currentTextChanged.connect(
            self.on_device_changed
        )
        device_layout.addWidget(self.config_widgets["device"])
        device_layout.addWidget(self.device_checkboxes)
        layout.addRow(self.tr("Device:"), device_layout)
        self.on_device_changed(self.config_widgets["device"].currentText())

        self.device_hint = QLabel()
        self.device_hint.setWordWrap(True)
        self.device_hint.setVisible(False)
        self.device_hint.setStyleSheet(
            f"color: {get_theme()['text_secondary']}; font-size: 10px;"
        )
        layout.addRow(self.device_hint)

        dataset_layout = QHBoxLayout()
        self.config_widgets["dataset_ratio"] = CustomSlider(
            Qt.Orientation.Horizontal
        )
        self.config_widgets["dataset_ratio"].setRange(5, 95)
        self.config_widgets["dataset_ratio"].setValue(80)
        self.dataset_ratio_label = QLabel("0.8")
        self.config_widgets["dataset_ratio"].valueChanged.connect(
            lambda v: self.dataset_ratio_label.setText(str(v / 100.0))
        )
        dataset_layout.addWidget(self.config_widgets["dataset_ratio"])
        dataset_layout.addWidget(self.dataset_ratio_label)
        layout.addRow(self.tr("Dataset Ratio:"), dataset_layout)

        parent_layout.addWidget(group)

    def toggle_advanced_settings(self):
        """Toggle the visibility of advanced settings"""
        if self.advanced_content_widget.isVisible():
            self.advanced_content_widget.setVisible(False)
            self.advanced_toggle_btn.setIcon(
                QIcon(new_icon("caret-down", "svg"))
            )
        else:
            self.advanced_content_widget.setVisible(True)
            self.advanced_toggle_btn.setIcon(
                QIcon(new_icon("caret-up", "svg"))
            )

    def _compute_training_advice(self):
        """Recommended config based on the labeling folder behind this dialog.

        Returns the advice dict from :mod:`training_advisor`, or ``None``
        (after telling the user) when there is no folder to analyse yet.
        """
        import json as _json

        from anylabeling.views.labeling.utils.active_learning import (
            load_history,
        )
        from anylabeling.views.labeling.utils.data_intel import (
            analyze_distribution,
        )
        from anylabeling.views.labeling.utils.training_advisor import (
            history_summary,
            recommend_training_config,
        )

        parent = self.parent
        image_list = getattr(parent, "image_list", None) or []
        label_dir = getattr(parent, "output_dir", None)
        if not label_dir and getattr(parent, "filename", None):
            label_dir = os.path.dirname(parent.filename)
        if not image_list or not label_dir:
            QMessageBox.information(
                self,
                self.tr("Smart Recommend"),
                self.tr(
                    "Open an image folder in the labeling view first, then click Smart Recommend."
                ),
            )
            return None

        entries = []
        for image_path in image_list:
            label_file = os.path.join(
                label_dir,
                os.path.splitext(os.path.basename(image_path))[0] + ".json",
            )
            data = None
            if os.path.isfile(label_file):
                try:
                    with open(label_file, "r", encoding="utf-8") as handle:
                        data = _json.load(handle)
                except (OSError, ValueError):
                    data = None
            entries.append((image_path, data))

        stats = analyze_distribution(entries)
        hist_info = history_summary(load_history(label_dir))
        max_dim = None
        image = getattr(parent, "image", None)
        if image is not None and not image.isNull():
            max_dim = max(image.width(), image.height())
        return recommend_training_config(
            stats, history=hist_info, max_image_dim=max_dim
        )

    def apply_recommended_config(self, advice):
        """Write advice values into the config widgets; returns applied keys."""
        applied = []
        if not isinstance(advice, dict):
            return applied
        for key in ("epochs", "batch", "imgsz"):
            widget = self.config_widgets.get(key)
            value = advice.get(key)
            if widget is None or not isinstance(value, int):
                continue
            try:
                widget.setValue(value)
            except Exception:  # noqa: BLE001
                continue
            applied.append(f"{key}={value}")
        return applied

    def run_smart_recommendation(self):
        """Compute advice from the current labeling folder and apply it."""
        advice = self._compute_training_advice()
        if advice is None:
            return
        applied = self.apply_recommended_config(advice)
        if not applied:
            return
        text = advice.get("text") or ""
        QMessageBox.information(
            self,
            self.tr("Smart recommendation applied"),
            self.tr("Filled in: %1\n\n%2")
            .replace("%1", " · ".join(applied))
            .replace("%2", text),
        )

    def apply_param_preset(self, key):
        """Apply one tuning tier to the fields it names.

        These are explicit one-click choices, so (unlike the CPU preset) they
        overwrite whatever is in the fields; the log line records what.
        """
        values = TRAIN_PARAM_PRESETS.get(key)
        if not values:
            return
        applied = []
        for field, value in values.items():
            widget = self.config_widgets.get(field)
            if widget is None:
                continue
            if isinstance(widget, CustomCheckBox):
                widget.setChecked(bool(value))
            else:
                widget.setValue(value)
            applied.append(f"{field}={value}")
        self.append_training_log(
            self.tr("Applied the %1 preset: %2")
            .replace("%1", key)
            .replace("%2", ", ".join(applied))
        )
        # The CPU note described values this click just replaced.
        device_widget = self.config_widgets.get("device")
        is_cpu = (
            device_widget is not None and device_widget.currentText() == "cpu"
        )
        self._update_device_hint(is_cpu, [])

    def init_train_settings(self, parent_layout):
        group = QGroupBox(self.tr("Train Settings"))
        layout = QVBoxLayout(group)

        # Tuning tiers: one click answers "how hard should this run try?"
        # (the smart-recommend button below is the data-driven variant).
        preset_row = QHBoxLayout()
        preset_label = QLabel(self.tr("Presets:"))
        preset_row.addWidget(preset_label)
        for key, label in (
            ("quick", self.tr("Quick check")),
            ("standard", self.tr("Standard")),
            ("high", self.tr("High quality")),
        ):
            button = SecondaryButton(label)
            button.setToolTip(
                self.tr(
                    "Sets epochs, image size, patience, close-mosaic and "
                    "cosine LR for this tier"
                )
            )
            button.clicked.connect(
                lambda _checked=False, name=key: self.apply_param_preset(name)
            )
            preset_row.addWidget(button)
        preset_row.addStretch()
        layout.addLayout(preset_row)

        # Basic settings
        basic_group = QGroupBox(self.tr("Basic"))
        basic_layout = QHBoxLayout(basic_group)
        basic_layout.addWidget(QLabel(self.tr("Epochs:")))
        self.config_widgets["epochs"] = CustomSpinBox()
        self.config_widgets["epochs"].setRange(1, 10000)
        self.config_widgets["epochs"].setValue(
            DEFAULT_TRAINING_CONFIG["epochs"]
        )
        self.config_widgets["epochs"].setToolTip(
            self.tr(
                "Number of training epochs. On CPU, start small to check the "
                "pipeline before a long run."
            )
        )
        basic_layout.addWidget(self.config_widgets["epochs"])

        basic_layout.addWidget(QLabel(self.tr("Batch:")))
        self.config_widgets["batch"] = CustomSpinBox()
        self.config_widgets["batch"].setRange(-1, 8192)
        self.config_widgets["batch"].setValue(DEFAULT_TRAINING_CONFIG["batch"])
        self.config_widgets["batch"].setToolTip(
            self.tr(
                "Images per batch. -1 picks the batch automatically (GPU "
                "only; on CPU it falls back to 16). Lower it if training runs "
                "out of memory."
            )
        )
        basic_layout.addWidget(self.config_widgets["batch"])

        basic_layout.addWidget(QLabel(self.tr("Image Size:")))
        self.config_widgets["imgsz"] = CustomSpinBox()
        self.config_widgets["imgsz"].setRange(32, 8192)
        self.config_widgets["imgsz"].setValue(DEFAULT_TRAINING_CONFIG["imgsz"])
        self.config_widgets["imgsz"].setToolTip(
            self.tr(
                "Training image size. Smaller trains faster: 640 is the "
                "default, 416 a common CPU choice."
            )
        )
        basic_layout.addWidget(self.config_widgets["imgsz"])

        basic_layout.addWidget(QLabel(self.tr("Workers:")))
        self.config_widgets["workers"] = CustomSpinBox()
        self.config_widgets["workers"].setRange(0, NUM_WORKERS)
        self.config_widgets["workers"].setValue(
            DEFAULT_TRAINING_CONFIG["workers"]
        )
        self.config_widgets["workers"].setToolTip(
            self.tr(
                "Data-loader worker processes. Ultralytics forces 0 on CPU; "
                "0-2 is the safest range on Windows."
            )
        )
        basic_layout.addWidget(self.config_widgets["workers"])

        basic_layout.addWidget(QLabel(self.tr("Classes:")))
        self.config_widgets["classes"] = CustomLineEdit()
        self.config_widgets["classes"].setText(
            DEFAULT_TRAINING_CONFIG["classes"]
        )
        self.config_widgets["classes"].setPlaceholderText(
            self.tr("Class indices (e.g., 0,1,2) or leave empty for all")
        )
        basic_layout.addWidget(self.config_widgets["classes"])

        self.config_widgets["single_cls"] = CustomCheckBox(
            self.tr("Single Class")
        )
        self.config_widgets["single_cls"].setChecked(
            DEFAULT_TRAINING_CONFIG["single_cls"]
        )
        basic_layout.addWidget(self.config_widgets["single_cls"])

        basic_layout.addStretch()
        layout.addWidget(basic_group)

        # Advanced settings
        advanced_container = QWidget()
        advanced_container_layout = QVBoxLayout(advanced_container)
        advanced_container_layout.setContentsMargins(0, 0, 0, 0)

        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)

        advanced_label = QLabel(self.tr("Advanced Settings"))
        advanced_label.setStyleSheet("font-weight: bold;")
        header_layout.addWidget(advanced_label)

        # Collapse/Expand button
        self.advanced_toggle_btn = QPushButton()
        self.advanced_toggle_btn.setFixedSize(*ICON_SIZE_NORMAL)
        self.advanced_toggle_btn.setStyleSheet(get_advanced_toggle_btn_style())
        self.advanced_toggle_btn.setIcon(QIcon(new_icon("caret-down", "svg")))
        self.advanced_toggle_btn.clicked.connect(self.toggle_advanced_settings)
        header_layout.addWidget(self.advanced_toggle_btn)
        header_layout.addStretch()
        advanced_container_layout.addWidget(header_widget)

        self.advanced_content_widget = QWidget()
        self.advanced_content_widget.setVisible(False)
        advanced_layout = QVBoxLayout(self.advanced_content_widget)

        # 1. Training Strategy
        strategy_group = QGroupBox(self.tr("Training Strategy"))
        strat_layout = QHBoxLayout(strategy_group)
        strat_layout.addWidget(QLabel(self.tr("Time (h):")))
        self.config_widgets["time"] = CustomDoubleSpinBox()
        self.config_widgets["time"].setValue(DEFAULT_TRAINING_CONFIG["time"])
        self.config_widgets["time"].setSpecialValueText("None")
        self.config_widgets["time"].setToolTip(
            self.tr(
                "Wall-clock limit in hours; training stops when it is reached "
                "(None = no limit)."
            )
        )
        strat_layout.addWidget(self.config_widgets["time"])

        strat_layout.addWidget(QLabel(self.tr("Patience:")))
        self.config_widgets["patience"] = CustomSpinBox()
        self.config_widgets["patience"].setRange(1, 10000)
        self.config_widgets["patience"].setValue(
            DEFAULT_TRAINING_CONFIG["patience"]
        )
        self.config_widgets["patience"].setToolTip(
            self.tr(
                "Stop early after this many epochs without an improvement. "
                "Lower it to fail fast while experimenting."
            )
        )
        strat_layout.addWidget(self.config_widgets["patience"])

        strat_layout.addWidget(QLabel(self.tr("Close Mosaic:")))
        self.config_widgets["close_mosaic"] = CustomSpinBox()
        self.config_widgets["close_mosaic"].setRange(0, 1000)
        self.config_widgets["close_mosaic"].setValue(
            DEFAULT_TRAINING_CONFIG["close_mosaic"]
        )
        self.config_widgets["close_mosaic"].setToolTip(
            self.tr(
                "Disable mosaic augmentation for the last N epochs so the "
                "model finishes on clean images (0 keeps it on)."
            )
        )
        strat_layout.addWidget(self.config_widgets["close_mosaic"])

        strat_layout.addWidget(QLabel(self.tr("Optimizer:")))
        self.config_widgets["optimizer"] = CustomComboBox()
        self.config_widgets["optimizer"].addItems(OPTIMIZER_OPTIONS)
        self.config_widgets["optimizer"].setToolTip(
            self.tr(
                "Weight-update algorithm. 'auto' picks one from the model and "
                "dataset size; SGD and AdamW are the usual manual choices."
            )
        )
        strat_layout.addWidget(self.config_widgets["optimizer"])

        self.config_widgets["cos_lr"] = CustomCheckBox(self.tr("Cosine LR"))
        self.config_widgets["cos_lr"].setChecked(
            DEFAULT_TRAINING_CONFIG["cos_lr"]
        )
        self.config_widgets["cos_lr"].setToolTip(
            self.tr(
                "Cosine learning-rate schedule: the rate decays smoothly to "
                "its final value instead of dropping linearly."
            )
        )
        strat_layout.addWidget(self.config_widgets["cos_lr"])
        self.config_widgets["amp"] = CustomCheckBox(self.tr("AMP"))
        self.config_widgets["amp"].setChecked(DEFAULT_TRAINING_CONFIG["amp"])
        strat_layout.addWidget(self.config_widgets["amp"])
        self.config_widgets["multi_scale"] = CustomCheckBox(
            self.tr("Multi Scale")
        )
        self.config_widgets["multi_scale"].setChecked(
            DEFAULT_TRAINING_CONFIG["multi_scale"]
        )
        self.config_widgets["multi_scale"].setToolTip(
            self.tr(
                "Randomly rescales inputs during training. Costs CPU time "
                "with little benefit there."
            )
        )
        strat_layout.addWidget(self.config_widgets["multi_scale"])
        strat_layout.addStretch()
        advanced_layout.addWidget(strategy_group)

        # 2. Learning Rate
        lr_group = QGroupBox(self.tr("Learning Rate"))
        lr_layout = QHBoxLayout(lr_group)
        lr_layout.addWidget(QLabel(self.tr("LR0:")))
        self.config_widgets["lr0"] = CustomDoubleSpinBox()
        self.config_widgets["lr0"].setDecimals(6)
        self.config_widgets["lr0"].setValue(DEFAULT_TRAINING_CONFIG["lr0"])
        self.config_widgets["lr0"].setToolTip(
            self.tr(
                "Initial learning rate. Lower it if the loss explodes; raise "
                "it if learning stalls."
            )
        )
        lr_layout.addWidget(self.config_widgets["lr0"])

        lr_layout.addWidget(QLabel(self.tr("LRF:")))
        self.config_widgets["lrf"] = CustomDoubleSpinBox()
        self.config_widgets["lrf"].setDecimals(6)
        self.config_widgets["lrf"].setValue(DEFAULT_TRAINING_CONFIG["lrf"])
        self.config_widgets["lrf"].setToolTip(
            self.tr(
                "Final learning rate as a fraction of LR0 (0.01 = 1%): the "
                "rate travels from LR0 down to this."
            )
        )
        lr_layout.addWidget(self.config_widgets["lrf"])

        lr_layout.addWidget(QLabel(self.tr("Momentum:")))
        self.config_widgets["momentum"] = CustomDoubleSpinBox()
        self.config_widgets["momentum"].setDecimals(3)
        self.config_widgets["momentum"].setValue(
            DEFAULT_TRAINING_CONFIG["momentum"]
        )
        self.config_widgets["momentum"].setToolTip(
            self.tr(
                "Momentum for SGD (beta1 for the Adam family); it smooths how "
                "much the previous step steers the next one."
            )
        )
        lr_layout.addWidget(self.config_widgets["momentum"])

        lr_layout.addWidget(QLabel(self.tr("Weight Decay:")))
        self.config_widgets["weight_decay"] = CustomDoubleSpinBox()
        self.config_widgets["weight_decay"].setDecimals(6)
        self.config_widgets["weight_decay"].setValue(
            DEFAULT_TRAINING_CONFIG["weight_decay"]
        )
        self.config_widgets["weight_decay"].setToolTip(
            self.tr(
                "Penalty on large weights: higher fights overfitting, too high "
                "underfits."
            )
        )
        lr_layout.addWidget(self.config_widgets["weight_decay"])
        lr_layout.addStretch()
        advanced_layout.addWidget(lr_group)

        # 3. Warmup Parameters
        warmup_group = QGroupBox(self.tr("Warmup Parameters"))
        warmup_layout = QHBoxLayout(warmup_group)
        warmup_layout.addWidget(QLabel(self.tr("Warmup Epochs:")))
        self.config_widgets["warmup_epochs"] = CustomDoubleSpinBox()
        self.config_widgets["warmup_epochs"].setDecimals(1)
        self.config_widgets["warmup_epochs"].setValue(
            DEFAULT_TRAINING_CONFIG["warmup_epochs"]
        )
        self.config_widgets["warmup_epochs"].setToolTip(
            self.tr(
                "Epochs spent ramping the learning rate up from zero: a "
                "stabiliser at the start, but they count toward the total."
            )
        )
        warmup_layout.addWidget(self.config_widgets["warmup_epochs"])

        warmup_layout.addWidget(QLabel(self.tr("Warmup Momentum:")))
        self.config_widgets["warmup_momentum"] = CustomDoubleSpinBox()
        self.config_widgets["warmup_momentum"].setDecimals(3)
        self.config_widgets["warmup_momentum"].setValue(
            DEFAULT_TRAINING_CONFIG["warmup_momentum"]
        )
        self.config_widgets["warmup_momentum"].setToolTip(
            self.tr(
                "Momentum at the start of warmup; it ramps up to the main "
                "value."
            )
        )
        warmup_layout.addWidget(self.config_widgets["warmup_momentum"])

        warmup_layout.addWidget(QLabel(self.tr("Warmup Bias LR:")))
        self.config_widgets["warmup_bias_lr"] = CustomDoubleSpinBox()
        self.config_widgets["warmup_bias_lr"].setDecimals(3)
        self.config_widgets["warmup_bias_lr"].setValue(
            DEFAULT_TRAINING_CONFIG["warmup_bias_lr"]
        )
        self.config_widgets["warmup_bias_lr"].setToolTip(
            self.tr(
                "Learning rate for bias terms during warmup, usually higher "
                "than LR0 so they can move early."
            )
        )
        warmup_layout.addWidget(self.config_widgets["warmup_bias_lr"])
        warmup_layout.addStretch()
        advanced_layout.addWidget(warmup_group)

        # 4. Augmentation Settings
        augment_group = QGroupBox(self.tr("Augmentation Settings"))
        augment_layout = QVBoxLayout(augment_group)
        augment_params = [
            (
                "hsv_h",
                self.tr("HSV Hue:"),
                DEFAULT_TRAINING_CONFIG["hsv_h"],
                0.0,
                1.0,
                3,
                self.tr(
                    "Random hue shift as a fraction of the colour wheel. Keep "
                    "small; 0 disables."
                ),
            ),
            (
                "hsv_s",
                self.tr("HSV Saturation:"),
                DEFAULT_TRAINING_CONFIG["hsv_s"],
                0.0,
                1.0,
                3,
                self.tr(
                    "Random saturation shift; useful when lighting varies "
                    "across the images."
                ),
            ),
            (
                "hsv_v",
                self.tr("HSV Value:"),
                DEFAULT_TRAINING_CONFIG["hsv_v"],
                0.0,
                1.0,
                3,
                self.tr(
                    "Random brightness shift; useful when exposure varies "
                    "across the images."
                ),
            ),
            (
                "degrees",
                self.tr("Rotation Degrees:"),
                DEFAULT_TRAINING_CONFIG["degrees"],
                -180.0,
                180.0,
                1,
                self.tr(
                    "Random rotation range in degrees. Use it only if the "
                    "objects really appear rotated."
                ),
            ),
            (
                "translate",
                self.tr("Translate:"),
                DEFAULT_TRAINING_CONFIG["translate"],
                0.0,
                1.0,
                3,
                self.tr("Random translation as a fraction of the image size."),
            ),
            (
                "scale",
                self.tr("Scale:"),
                DEFAULT_TRAINING_CONFIG["scale"],
                0.0,
                2.0,
                3,
                self.tr(
                    "Random zoom range (0.5 means +/-50%): teaches size "
                    "robustness."
                ),
            ),
            (
                "shear",
                self.tr("Shear:"),
                DEFAULT_TRAINING_CONFIG["shear"],
                -45.0,
                45.0,
                1,
                self.tr("Random shear in degrees; rarely needed."),
            ),
            (
                "perspective",
                self.tr("Perspective:"),
                DEFAULT_TRAINING_CONFIG["perspective"],
                0.0,
                0.001,
                6,
                self.tr(
                    "Random perspective warp as a fraction (very small "
                    "values); helps with tilted viewpoints."
                ),
            ),
        ]

        grid_layout = QGridLayout()
        grid_layout.setHorizontalSpacing(10)
        grid_layout.setVerticalSpacing(5)
        for i, (
            param,
            label,
            default,
            min_val,
            max_val,
            decimals,
            tooltip,
        ) in enumerate(augment_params):
            row = i // 4
            col = (i % 4) * 2

            label_widget = QLabel(label)
            label_widget.setMinimumWidth(80)
            grid_layout.addWidget(label_widget, row, col)

            widget = CustomDoubleSpinBox()
            widget.setRange(min_val, max_val)
            widget.setDecimals(decimals)
            widget.setValue(default)
            widget.setMinimumWidth(80)
            widget.setToolTip(tooltip)
            self.config_widgets[param] = widget
            grid_layout.addWidget(widget, row, col + 1)

        for col in range(8, 10):
            grid_layout.setColumnStretch(col, 1)
        augment_layout.addLayout(grid_layout)
        advanced_layout.addWidget(augment_group)

        # 5. Regularization
        reg_group = QGroupBox(self.tr("Regularization"))
        reg_layout = QHBoxLayout(reg_group)
        reg_layout.addWidget(QLabel(self.tr("Dropout:")))
        self.config_widgets["dropout"] = CustomDoubleSpinBox()
        self.config_widgets["dropout"].setDecimals(3)
        self.config_widgets["dropout"].setValue(
            DEFAULT_TRAINING_CONFIG["dropout"]
        )
        self.config_widgets["dropout"].setToolTip(
            self.tr(
                "Dropout for classification heads only; it does nothing for "
                "detect/segment/pose."
            )
        )
        reg_layout.addWidget(self.config_widgets["dropout"])

        reg_layout.addWidget(QLabel(self.tr("Fraction:")))
        self.config_widgets["fraction"] = CustomDoubleSpinBox()
        self.config_widgets["fraction"].setDecimals(3)
        self.config_widgets["fraction"].setValue(
            DEFAULT_TRAINING_CONFIG["fraction"]
        )
        self.config_widgets["fraction"].setToolTip(
            self.tr(
                "Fraction of the training set used per run (1.0 = all). "
                "Lower it for quick experiments."
            )
        )
        reg_layout.addWidget(self.config_widgets["fraction"])

        self.config_widgets["rect"] = CustomCheckBox(self.tr("Rectangular"))
        self.config_widgets["rect"].setChecked(DEFAULT_TRAINING_CONFIG["rect"])
        self.config_widgets["rect"].setToolTip(
            self.tr(
                "Rectangular training batches: less padding and faster, but "
                "validation loses the batch-shape consistency."
            )
        )
        reg_layout.addWidget(self.config_widgets["rect"])
        reg_layout.addStretch()
        advanced_layout.addWidget(reg_group)

        # 6. Loss Weights
        loss_group = QGroupBox(self.tr("Loss Weights"))
        loss_layout = QHBoxLayout(loss_group)
        loss_layout.addWidget(QLabel(self.tr("Box:")))
        self.config_widgets["box"] = CustomDoubleSpinBox()
        self.config_widgets["box"].setDecimals(2)
        self.config_widgets["box"].setValue(DEFAULT_TRAINING_CONFIG["box"])
        self.config_widgets["box"].setToolTip(
            self.tr(
                "Weight of the box-position loss: raise it when the boxes are "
                "loose around the objects."
            )
        )
        loss_layout.addWidget(self.config_widgets["box"])

        loss_layout.addWidget(QLabel(self.tr("Cls:")))
        self.config_widgets["cls"] = CustomDoubleSpinBox()
        self.config_widgets["cls"].setDecimals(2)
        self.config_widgets["cls"].setValue(DEFAULT_TRAINING_CONFIG["cls"])
        self.config_widgets["cls"].setToolTip(
            self.tr(
                "Weight of the classification loss: raise it when classes are "
                "being confused."
            )
        )
        loss_layout.addWidget(self.config_widgets["cls"])

        loss_layout.addWidget(QLabel(self.tr("DFL:")))
        self.config_widgets["dfl"] = CustomDoubleSpinBox()
        self.config_widgets["dfl"].setDecimals(2)
        self.config_widgets["dfl"].setValue(DEFAULT_TRAINING_CONFIG["dfl"])
        self.config_widgets["dfl"].setToolTip(
            self.tr(
                "Weight of the distribution-focal loss: how sharply box edges "
                "are localised."
            )
        )
        loss_layout.addWidget(self.config_widgets["dfl"])

        loss_layout.addWidget(QLabel(self.tr("Pose:")))
        self.config_widgets["pose"] = CustomDoubleSpinBox()
        self.config_widgets["pose"].setDecimals(2)
        self.config_widgets["pose"].setValue(DEFAULT_TRAINING_CONFIG["pose"])
        self.config_widgets["pose"].setToolTip(
            self.tr("Weight of the keypoint loss; pose tasks only.")
        )
        loss_layout.addWidget(self.config_widgets["pose"])

        loss_layout.addWidget(QLabel(self.tr("Kobj:")))
        self.config_widgets["kobj"] = CustomDoubleSpinBox()
        self.config_widgets["kobj"].setDecimals(2)
        self.config_widgets["kobj"].setValue(DEFAULT_TRAINING_CONFIG["kobj"])
        self.config_widgets["kobj"].setToolTip(
            self.tr("Weight of the keypoint-objectness loss; pose tasks only.")
        )
        loss_layout.addWidget(self.config_widgets["kobj"])
        loss_layout.addStretch()
        advanced_layout.addWidget(loss_group)

        # 7. Checkpoint and Validation
        ckpt_group = QGroupBox(self.tr("Checkpoint and Validation"))
        ckpt_layout = QHBoxLayout(ckpt_group)
        ckpt_layout.addWidget(QLabel(self.tr("Save Period:")))
        self.config_widgets["save_period"] = CustomSpinBox()
        self.config_widgets["save_period"].setRange(-1, 1000)
        self.config_widgets["save_period"].setValue(
            DEFAULT_TRAINING_CONFIG["save_period"]
        )
        self.config_widgets["save_period"].setSpecialValueText("Disabled")
        self.config_widgets["save_period"].setToolTip(
            self.tr(
                "Save a checkpoint every N epochs (Disabled = only the final "
                "one)."
            )
        )
        ckpt_layout.addWidget(self.config_widgets["save_period"])

        self.config_widgets["val"] = CustomCheckBox(self.tr("Validation"))
        self.config_widgets["val"].setChecked(DEFAULT_TRAINING_CONFIG["val"])
        self.config_widgets["val"].setToolTip(
            self.tr(
                "Validate after every epoch. Turning it off is faster but "
                "leaves no mAP curve and no best.pt to export."
            )
        )
        ckpt_layout.addWidget(self.config_widgets["val"])
        self.config_widgets["plots"] = CustomCheckBox(self.tr("Plots"))
        self.config_widgets["plots"].setChecked(
            DEFAULT_TRAINING_CONFIG["plots"]
        )
        self.config_widgets["plots"].setToolTip(
            self.tr(
                "Write the training plots (curves, confusion matrix) into the "
                "run directory."
            )
        )
        ckpt_layout.addWidget(self.config_widgets["plots"])
        self.config_widgets["save"] = CustomCheckBox(self.tr("Save"))
        self.config_widgets["save"].setChecked(DEFAULT_TRAINING_CONFIG["save"])
        self.config_widgets["save"].setToolTip(
            self.tr("Save checkpoints while training runs.")
        )
        ckpt_layout.addWidget(self.config_widgets["save"])
        self.config_widgets["resume"] = CustomCheckBox(self.tr("Resume"))
        self.config_widgets["resume"].setChecked(
            DEFAULT_TRAINING_CONFIG["resume"]
        )
        self.config_widgets["resume"].setToolTip(
            self.tr(
                "Continue an interrupted run from its last checkpoint; a "
                "stopped run also offers this in the directory dialog."
            )
        )
        ckpt_layout.addWidget(self.config_widgets["resume"])
        self.config_widgets["cache"] = CustomCheckBox(self.tr("Cache"))
        self.config_widgets["cache"].setChecked(
            DEFAULT_TRAINING_CONFIG["cache"]
        )
        self.config_widgets["cache"].setToolTip(
            self.tr(
                "Keep the dataset in RAM: faster epochs when the images fit in "
                "memory."
            )
        )
        ckpt_layout.addWidget(self.config_widgets["cache"])
        self.config_widgets["skip_empty_files"] = CustomCheckBox(
            self.tr("Skip Empty Files")
        )
        self.config_widgets["skip_empty_files"].setChecked(False)
        self.config_widgets["skip_empty_files"].setToolTip(
            self.tr(
                "Leave images with no shapes out of training; otherwise they "
                "act as background (negative) samples."
            )
        )
        ckpt_layout.addWidget(self.config_widgets["skip_empty_files"])
        self.config_widgets["only_checked_files"] = CustomCheckBox(
            self.tr("Only Checked Files")
        )
        self.config_widgets["only_checked_files"].setChecked(False)
        self.config_widgets["only_checked_files"].setToolTip(
            self.tr(
                "Train only on images marked as confirmed in the label list."
            )
        )
        ckpt_layout.addWidget(self.config_widgets["only_checked_files"])
        ckpt_layout.addStretch()
        advanced_layout.addWidget(ckpt_group)

        advanced_container_layout.addWidget(self.advanced_content_widget)
        layout.addWidget(advanced_container)

        # Smart recommendation button on its own row (the Basic row above is
        # already dense; squeezing it there broke narrow windows).
        from anylabeling.views.labeling.utils.style import (
            get_highlight_button_style,
        )

        recommend_row = QHBoxLayout()
        recommend_row.addStretch()
        recommend_btn = QPushButton(self.tr("Smart Recommend"))
        recommend_btn.setToolTip(
            self.tr(
                "Auto-fill epochs/batch/imgsz from the current labeled folder and past iterations"
            )
        )
        recommend_btn.setStyleSheet(get_highlight_button_style(compact=True))
        recommend_btn.clicked.connect(self.run_smart_recommendation)
        recommend_row.addWidget(recommend_btn)
        layout.addLayout(recommend_row)

        parent_layout.addWidget(group)

    def load_config_to_ui(self, config):
        """Write a config dict into the widgets, then re-apply device rules.

        The device rules run once at the end instead of mid-load: ``device``
        and ``amp`` are applied in separate passes, and adapting AMP to the
        device in between would let the later pass re-enable it.
        """
        self._loading_config = True
        try:
            self._write_config_into_widgets(config)
        finally:
            self._loading_config = False
        self._sync_cpu_device_options()

    def _write_config_into_widgets(self, config):
        def set_widget_value(key, value):
            if key not in self.config_widgets:
                return

            widget = self.config_widgets[key]
            widget_type = type(widget).__name__

            try:
                if widget_type == "CustomLineEdit":
                    if key == "classes":
                        widget.setText(format_classes_display(value))
                    else:
                        widget.setText(str(value) if value is not None else "")
                elif widget_type in ["CustomSpinBox", "CustomDoubleSpinBox"]:
                    widget.setValue(value)
                elif widget_type == "CustomComboBox":
                    if isinstance(value, str):
                        index = widget.findText(value)
                        if index >= 0:
                            widget.setCurrentIndex(index)
                    else:
                        widget.setCurrentIndex(value)
                elif widget_type == "CustomCheckBox":
                    widget.setChecked(bool(value))
                elif widget_type == "CustomSlider":
                    widget.setValue(value)
            except Exception as e:
                logger.warning(f"Failed to set value for widget {key}: {e}")

        sections_to_process = [
            "basic",
            "train",
            "augment",
            "strategy",
            "learning_rate",
            "warmup",
            "regularization",
            "loss_weights",
            "checkpoint",
        ]
        for section in sections_to_process:
            if section in config:
                for key, value in config[section].items():
                    if key == "dataset_ratio":
                        if 0 <= value <= 1:
                            self.config_widgets[key].setValue(int(value * 100))
                            self.dataset_ratio_label.setText(str(value))
                        else:
                            self.config_widgets[key].setValue(int(value))
                            self.dataset_ratio_label.setText(
                                str(value / 100.0)
                            )
                    elif key == "device":
                        index = self.config_widgets[key].findText(str(value))
                        if index >= 0:
                            self.config_widgets[key].setCurrentIndex(index)
                            self.on_device_changed(str(value))
                    elif key == "optimizer":
                        index = self.config_widgets[key].findText(str(value))
                        if index >= 0:
                            self.config_widgets[key].setCurrentIndex(index)
                    elif key == "pose_config":
                        if value:
                            self.config_widgets[key].setText(value)
                    elif key in (
                        "skip_empty_files",
                        "only_checked_files",
                    ):
                        set_widget_value(key, value)
                    else:
                        set_widget_value(key, value)

        for key, value in config.items():
            if key not in sections_to_process and key in self.config_widgets:
                set_widget_value(key, value)

    def import_config(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Import Config"),
            "",
            "JSON Files (*.json);;All Files (*)",
        )
        if file_path:
            config = load_config_from_file(file_path)
            if config:
                self.load_config_to_ui(config)
                QMessageBox.information(
                    self,
                    self.tr("Success"),
                    self.tr("Config imported successfully"),
                )
            else:
                QMessageBox.warning(
                    self, self.tr("Error"), self.tr("Failed to import config")
                )

    def get_current_config(self):
        def get_widget_value(key):
            if key not in self.config_widgets:
                return None
            widget = self.config_widgets[key]
            widget_type = type(widget).__name__
            try:
                if widget_type == "CustomLineEdit":
                    return widget.text()
                elif widget_type in ["CustomSpinBox", "CustomDoubleSpinBox"]:
                    return widget.value()
                elif widget_type == "CustomComboBox":
                    return widget.currentText()
                elif widget_type == "CustomCheckBox":
                    return widget.isChecked()
                elif widget_type == "CustomSlider":
                    return widget.value()
            except Exception:
                return None
            return None

        config = {
            "basic": {
                "project": get_widget_value("project"),
                "name": get_widget_value("name"),
                "model": get_widget_value("model").strip('"'),
                "data": get_widget_value("data").strip('"'),
                "device": get_widget_value("device"),
                "dataset_ratio": (
                    get_widget_value("dataset_ratio") / 100.0
                    if get_widget_value("dataset_ratio") is not None
                    else 0.8
                ),
                "pose_config": get_widget_value("pose_config"),
            },
            "train": {
                "epochs": get_widget_value("epochs"),
                "batch": get_widget_value("batch"),
                "imgsz": get_widget_value("imgsz"),
                "workers": get_widget_value("workers"),
                "single_cls": get_widget_value("single_cls"),
                "classes": parse_string_to_digit_list(
                    get_widget_value("classes")
                ),
            },
            "strategy": {
                "time": get_widget_value("time"),
                "patience": get_widget_value("patience"),
                "close_mosaic": get_widget_value("close_mosaic"),
                "optimizer": get_widget_value("optimizer"),
                "cos_lr": get_widget_value("cos_lr"),
                "amp": get_widget_value("amp"),
                "multi_scale": get_widget_value("multi_scale"),
            },
            "learning_rate": {
                "lr0": get_widget_value("lr0"),
                "lrf": get_widget_value("lrf"),
                "momentum": get_widget_value("momentum"),
                "weight_decay": get_widget_value("weight_decay"),
            },
            "warmup": {
                "warmup_epochs": get_widget_value("warmup_epochs"),
                "warmup_momentum": get_widget_value("warmup_momentum"),
                "warmup_bias_lr": get_widget_value("warmup_bias_lr"),
            },
            "augment": {
                "hsv_h": get_widget_value("hsv_h"),
                "hsv_s": get_widget_value("hsv_s"),
                "hsv_v": get_widget_value("hsv_v"),
                "degrees": get_widget_value("degrees"),
                "translate": get_widget_value("translate"),
                "scale": get_widget_value("scale"),
                "shear": get_widget_value("shear"),
                "perspective": get_widget_value("perspective"),
            },
            "regularization": {
                "dropout": get_widget_value("dropout"),
                "fraction": get_widget_value("fraction"),
                "rect": get_widget_value("rect"),
            },
            "loss_weights": {
                "box": get_widget_value("box"),
                "cls": get_widget_value("cls"),
                "dfl": get_widget_value("dfl"),
                "pose": get_widget_value("pose"),
                "kobj": get_widget_value("kobj"),
            },
            "checkpoint": {
                "save_period": get_widget_value("save_period"),
                "val": get_widget_value("val"),
                "plots": get_widget_value("plots"),
                "save": get_widget_value("save"),
                "resume": get_widget_value("resume"),
                "cache": get_widget_value("cache"),
                "skip_empty_files": get_widget_value("skip_empty_files"),
                "only_checked_files": get_widget_value("only_checked_files"),
            },
        }

        return config

    def save_current_config(self):
        try:
            # save_config() never raises — it returns False when the write
            # fails, so "Success" here used to be shown on a failed save.
            if not save_config(self.get_current_config()):
                raise RuntimeError(get_settings_config_path())
            template = self.tr("Configuration saved successfully to %s")
            msg_test = template % get_settings_config_path()
            QMessageBox.information(self, self.tr("Success"), msg_test)
        except Exception as e:
            QMessageBox.warning(
                self, self.tr("Error"), f"Failed to save config: {str(e)}"
            )

    def _describe_dir_contents(self, project_dir):
        """Summarize what an overwrite would destroy, for the confirm text."""
        try:
            entries = os.listdir(project_dir)
        except OSError:
            return self.tr("(cannot read directory contents)")
        weights = os.path.join(project_dir, "weights")
        has_weights = os.path.isdir(weights) and bool(os.listdir(weights))
        args_path = os.path.join(project_dir, "args.yaml")
        parts = []
        if has_weights:
            parts.append(self.tr("Contains trained weights weights/"))
        elif os.path.isdir(weights):
            parts.append(self.tr("Only an empty weights/ directory"))
        if os.path.isfile(args_path):
            parts.append(self.tr("Contains previous training args args.yaml"))
        others = [
            name for name in entries if name not in ("weights", "args.yaml")
        ]
        if others:
            parts.append(
                self.tr("and %d other files/subdirectories") % len(others)
            )
        if not parts:
            return self.tr(
                "The directory is empty; deleting it loses nothing."
            )
        return "、".join(parts) + self.tr(" Deletion cannot be undone.")

    def _read_resume_checkpoint(self, last_pt):
        """``last.pt`` info when the run can continue, else ``None``.

        Ultralytics can only resume a checkpoint that carries epoch and
        optimizer state, and only while the run still has epochs left;
        anything else would silently start a fresh run instead.
        """
        if not os.path.isfile(last_pt):
            return None
        try:
            import torch

            try:
                ckpt = torch.load(
                    last_pt, map_location="cpu", weights_only=False
                )
            except TypeError:  # torch < 1.13 has no weights_only
                ckpt = torch.load(last_pt, map_location="cpu")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to read checkpoint {last_pt}: {e}")
            return None
        if not isinstance(ckpt, dict) or ckpt.get("optimizer") is None:
            return None
        try:
            last_epoch = int(ckpt.get("epoch", -1))
        except (TypeError, ValueError):
            return None
        if last_epoch < 0:
            return None
        try:
            epochs = int((ckpt.get("train_args") or {}).get("epochs") or 0)
        except (TypeError, ValueError):
            epochs = 0
        if epochs and last_epoch + 1 >= epochs:
            return None  # already trained its configured epochs
        return {"epochs": epochs or None, "last_epoch": last_epoch}

    def _ask_existing_run_action(self, project_dir, resume_info, has_best):
        """One dialog for the existing-directory branch: resume/export/retrain."""
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Icon.Question)
        box.setWindowTitle(self.tr("Training Directory Exists"))
        lines = [
            self.tr("A training run already lives in this directory:"),
            project_dir,
            "",
        ]
        if resume_info:
            if resume_info.get("epochs"):
                lines.append(
                    self.tr("Checkpoint: epoch %1 of %2 completed.")
                    .replace("%1", str(resume_info["last_epoch"] + 1))
                    .replace("%2", str(resume_info["epochs"]))
                )
            else:
                lines.append(self.tr("A resumable checkpoint was found."))
        if has_best:
            lines.append(
                self.tr("A trained model (weights/best.pt) exists here.")
            )
        lines.append("")
        lines.append(self.tr("Choose an action:"))
        box.setText("\n".join(lines))

        resume_btn = None
        if resume_info:
            resume_btn = box.addButton(
                self.tr("Resume Training"),
                QtWidgets.QMessageBox.ButtonRole.AcceptRole,
            )
        export_btn = None
        if has_best:
            export_btn = box.addButton(
                self.tr("Use Existing Model"),
                QtWidgets.QMessageBox.ButtonRole.ActionRole,
            )
        retrain_btn = box.addButton(
            self.tr("Retrain (overwrite)"),
            QtWidgets.QMessageBox.ButtonRole.DestructiveRole,
        )
        box.addButton(
            self.tr("Cancel"), QtWidgets.QMessageBox.ButtonRole.RejectRole
        )
        # Default to the first non-destructive option: pressing Enter must not
        # land on "Retrain (overwrite)".
        box.setDefaultButton(resume_btn or export_btn or retrain_btn)
        box.exec()

        clicked = box.clickedButton()
        if clicked is resume_btn and resume_btn is not None:
            return "resume"
        if clicked is export_btn and export_btn is not None:
            return "export"
        if clicked is retrain_btn and retrain_btn is not None:
            return "retrain"
        return None

    def _adopt_existing_model(self, project_dir, best_pt, config):
        """Show the finished run's weights on the Train tab for export."""
        self.current_project_path = project_dir
        self.training_status = "completed"
        save_config(config)
        self.go_to_specific_tab(2)
        self.update_training_status_display()
        self.start_training_button.setVisible(False)
        self.export_button.setVisible(True)
        self.previous_button.setVisible(True)
        if hasattr(self, "use_autolabel_button"):
            self.use_autolabel_button.setVisible(True)
        self.update_training_images()
        self._update_metrics_label()
        self.refresh_wizard_state()
        self.append_training_log(f"Loaded existing model from: {best_pt}")

    def _confirm_overwrite(self, project_dir, project_root=None):
        """Destructive guard: deleting the existing run directory.

        Two refusals come before the question, because the question itself is
        not a sufficient guard when the path is not what the user thinks it
        is: the directory has to live inside the project that was typed
        (``Name`` cannot walk out of it) *and* has to look like a run this
        tool wrote. Anything else cancels with an explanation instead of
        offering a click that cannot be undone.
        """
        if project_root and not is_inside_directory(project_dir, project_root):
            self._refuse_overwrite(
                project_dir,
                self.tr(
                    "This directory is not inside the Project folder, so overwriting it is not offered."
                ),
            )
            return False
        if not looks_like_training_run(project_dir):
            self._refuse_overwrite(
                project_dir,
                self.tr(
                    "This directory holds no training output (no weights/, args.yaml or results.csv), so it is probably not a result folder. Nothing was deleted - change the Name field or pick another Project."
                ),
            )
            return False

        reply = QMessageBox.question(
            self,
            self.tr("Directory Exists"),
            self.tr(
                "This will delete the existing project directory and restart training:\n{path}\n\n{detail}\nOverwrite it? To keep it, choose No and change the Name field."
            ).format(
                path=os.path.abspath(project_dir),
                detail=self._describe_dir_contents(project_dir),
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False
        try:
            shutil.rmtree(project_dir)
            self.append_training_log(
                f"Removed existing directory: {project_dir}"
            )
        except Exception as e:
            error_msg = f"Failed to remove directory: {str(e)}"
            logger.error(error_msg)
            QMessageBox.critical(
                self,
                self.tr("Directory Exists"),
                self.tr(
                    "Could not delete the directory; training was cancelled.\n{path}\nReason: {error}\n\nIf the directory is held by Explorer or another program, close it and retry."
                ).format(path=project_dir, error=str(e)),
            )
            return False
        return True

    def _refuse_overwrite(self, project_dir, reason):
        """Report a refused overwrite and remember it in the log."""
        QMessageBox.warning(
            self,
            self.tr("Directory Exists"),
            self.tr("%1\n\nDirectory:\n%2")
            .replace("%1", reason)
            .replace("%2", os.path.abspath(project_dir)),
        )
        self.append_training_log(
            f"Refused to overwrite: {os.path.abspath(project_dir)} ({reason})"
        )

    def on_start_training_clicked(self):
        """Config tab: commit the form and start right away (one step)."""
        if self.start_training():
            self.start_training_from_train_tab()

    def start_training(self):
        """Commit the config; returns True when the run should start now.

        The Config tab used to only turn to the Train tab and wait for a
        second click there; the caller now starts the run when this returns
        True. False means a dialog said to stop (cancel, export-only,
        validation failure).
        """
        if self.training_status in ("training", "preparing"):
            QMessageBox.warning(
                self,
                self.tr("Training in Progress"),
                self.tr(
                    "Training is currently in progress. Please stop the training first if you need to reconfigure."
                ),
            )
            return False

        self._resume_from = None
        self._resume_info = None

        config = self.get_current_config()
        is_valid, error_message = validate_basic_config(
            config, self.selected_task_type
        )
        if is_valid == "directory_exists":
            project_dir = error_message
            last_pt = os.path.join(project_dir, "weights", "last.pt")
            best_pt = os.path.join(project_dir, "weights", "best.pt")
            resume_info = self._read_resume_checkpoint(last_pt)
            has_best = os.path.exists(best_pt)

            action = "retrain"
            if resume_info or has_best:
                action = self._ask_existing_run_action(
                    project_dir, resume_info, has_best
                )
                if action is None:
                    return False
            if action == "export":
                self._adopt_existing_model(project_dir, best_pt, config)
                return False
            if action == "resume":
                # Continuing the run: the dataset is rebuilt below, but the
                # tuning comes from the checkpoint, not the form.
                self._resume_from = last_pt
                self._resume_info = resume_info
            elif not self._confirm_overwrite(
                project_dir, config["basic"]["project"]
            ):
                return False
        elif not is_valid:
            QMessageBox.warning(
                self, self.tr("Validation Error"), error_message
            )
            self.append_training_log(f"Validation Error: {error_message}")
            return False

        if not self.selected_task_type:
            QMessageBox.warning(
                self,
                self.tr("Error"),
                self.tr("Please select a task type first"),
            )
            return False

        if self.selected_task_type.lower() == "pose":
            pose_config = config["basic"].get("pose_config", "")
            if not pose_config or not os.path.exists(pose_config):
                QMessageBox.warning(
                    self,
                    self.tr("Error"),
                    self.tr(
                        "Please select a valid pose configuration file for pose detection tasks"
                    ),
                )
                return False

        if self.training_status in ["completed", "error"]:
            reply = QMessageBox.question(
                self,
                self.tr("Reset Training"),
                self.tr(
                    "Training traces detected. Do you want to reset the training tab?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.reset_train_tab()
        elif self.training_status == "stop":
            self.start_training_button.setVisible(True)
            self.training_status = "idle"

        if self._resume_from:
            self.append_training_log(
                self.tr("Continuing from checkpoint: %1").replace(
                    "%1", self._resume_from
                )
            )
            self.append_training_log(
                self.tr(
                    "Resume keeps the checkpoint's own epochs/batch/imgsz; the other Config values are ignored."
                )
            )

        save_config(config)
        # The run is committed: remember its tuning for this dataset so the
        # next session on the same images restores it instead of inheriting
        # whatever the previous dataset used.
        self._save_project_train_prefs(config)
        self.go_to_specific_tab(2)
        return True

    def _on_resume_training_clicked(self):
        """Train tab: continue a stopped run straight from its last.pt."""
        if not self.current_project_path:
            return
        last_pt = os.path.join(self.current_project_path, "weights", "last.pt")
        info = self._read_resume_checkpoint(last_pt)
        if info is None:
            QMessageBox.information(
                self,
                self.tr("Cannot Resume"),
                self.tr(
                    "No resumable checkpoint (weights/last.pt) was found for this run."
                ),
            )
            return
        self._resume_from = last_pt
        self._resume_info = info
        self.training_status = "idle"
        if hasattr(self, "resume_training_button"):
            self.resume_training_button.setVisible(False)
        self.start_training_button.setVisible(True)
        self.start_training_from_train_tab()

    def init_config_buttons(self, parent_layout):
        button_layout = QHBoxLayout()

        import_btn = SecondaryButton(self.tr("Import Config"))
        import_btn.clicked.connect(self.import_config)
        button_layout.addWidget(import_btn)

        save_btn = SecondaryButton(self.tr("Save Config"))
        save_btn.clicked.connect(self.save_current_config)
        button_layout.addWidget(save_btn)
        button_layout.addStretch()

        previous_btn = SecondaryButton(self.tr("Previous"))
        previous_btn.clicked.connect(lambda: self.go_to_specific_tab(0))
        button_layout.addWidget(previous_btn)

        # One step: the config tab starts the run itself instead of turning
        # the page and waiting for a second click on the Train tab.
        train_btn = PrimaryButton(self.tr("Start Training"))
        train_btn.clicked.connect(self.on_start_training_clicked)
        button_layout.addWidget(train_btn)

        parent_layout.addLayout(button_layout)

    def load_default_config(self):
        config = load_config()
        self.load_config_to_ui(config)
        # Per-project tuning on top of the global defaults: reopening a
        # dataset restores the hyperparameters it was last trained with
        # (missing sections/keys simply keep the global value).
        prefs = self._project_train_prefs()
        if prefs:
            self.load_config_to_ui(prefs)

    def _project_train_prefs(self):
        """``train_prefs`` recorded for the open dataset, ``{}`` when none."""
        from anylabeling.views.labeling import project_settings

        dataset_dir = _dataset_dir_for(self)
        if not dataset_dir:
            return {}
        prefs = project_settings.get_value(dataset_dir, "train_prefs")
        return prefs if isinstance(prefs, dict) else {}

    def _apply_project_task(self):
        """Preselect the task kind the open *project* declares.

        Only for a folder that really carries a project record: one that
        was merely opened keeps the old "nothing selected yet" start on
        purpose, because picking a task here is picking wrong on a full
        run, and the project is the only thing that has actually been
        told what it is for.
        """
        from anylabeling.views.labeling import project_model

        dataset_dir = _dataset_dir_for(self)
        if not dataset_dir:
            return False
        described = project_model.describe(dataset_dir)
        if not described["has_record"]:
            return False
        task = described["task"]
        if task not in self.task_type_buttons:
            return False
        if self.selected_task_type == task:
            return False
        # Through the real handler: it is what refreshes the summary, the
        # labeled-image hint and the wizard state.
        self.on_task_type_selected(task)
        return True

    def _save_project_train_prefs(self, config):
        """Mirror the whitelisted tuning onto the open dataset's record.

        The task kind rides along: whichever kind the run was committed
        with becomes the project's declared kind, so a project whose task
        was never set — or was set differently — ends up agreeing with
        what was actually trained.
        """
        from anylabeling.views.labeling import project_model, project_settings

        dataset_dir = _dataset_dir_for(self)
        if not dataset_dir:
            return False
        basic = config.get("basic") or {}
        prefs = {
            "basic": {key: basic.get(key) for key in TRAIN_PREFS_BASIC_KEYS}
        }
        for section in TRAIN_PREFS_SECTIONS:
            if section in config:
                prefs[section] = dict(config[section])
        ok = project_settings.update_values(dataset_dir, train_prefs=prefs)
        # ``getattr`` because the tests drive this with a SimpleNamespace
        # stand-in that carries only ``image_list``.
        task = getattr(self, "selected_task_type", None)
        if task:
            # Written straight to the record rather than through
            # ``project_model.set_task``: that one requires a project to
            # already exist, and a folder reaching training has just had
            # its record created by the line above.
            project_settings.update_values(
                dataset_dir, task=project_model.normalize_task(task)
            )
        return ok

    def init_config_tab(self):
        layout = QVBoxLayout(self.config_tab)

        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        self.init_basic_settings(scroll_layout)
        self.init_train_settings(scroll_layout)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)

        self.init_config_buttons(layout)
        self.load_default_config()

    # Train tab
    def update_training_status_display(self):
        color = TRAINING_STATUS_COLORS.get(self.training_status, "#6c757d")
        text = self.tr(
            TRAINING_STATUS_TEXTS.get(self.training_status, "Unknown status")
        )
        self.status_label.setText(text)
        self.status_label.setStyleSheet(get_status_label_style(color))

    def update_training_progress(self):
        if not self.current_project_path:
            return

        results_file = os.path.join(self.current_project_path, "results.csv")
        # Read the ``epoch`` column, not the row count: a resumed run repeats
        # one row, and this number has to agree with run_meta.json and with the
        # metrics label sitting right beside the progress bar.
        metrics = parse_training_metrics(results_file)
        epoch_rows = metrics[2] if metrics else 0

        if epoch_rows > 0:
            self.current_epochs = epoch_rows
            progress = min(
                100,
                int((self.current_epochs / self.total_epochs) * 100),
            )
            self.progress_bar.setValue(progress)
            self.progress_bar.setFormat(
                f"{self.current_epochs}/{self.total_epochs}"
            )
        else:
            # Before the first epoch row is written, ultralytics is still
            # warming up (model load / cache build / first epoch, which is
            # often the longest). Surface elapsed time so the user can tell
            # the worker is alive instead of staring at a frozen 0/N.
            self.progress_bar.setValue(0)
            elapsed = 0
            start = getattr(self, "_training_started_at", None)
            if start is not None:
                elapsed = int(time.time() - start)
            mm, ss = divmod(max(0, elapsed), 60)
            self.progress_bar.setFormat(
                self.tr("Starting (elapsed %d:%02d)...") % (mm, ss)
            )
        self._update_metrics_label()

    def _update_metrics_label(self):
        if not hasattr(self, "metrics_label"):
            return
        if not self.current_project_path:
            self.metrics_label.setText("")
            return
        results_file = os.path.join(self.current_project_path, "results.csv")
        parsed = parse_training_metrics(results_file)
        if not parsed:
            if self.training_status == "training":
                self.metrics_label.setText(
                    self.tr("Training; waiting for the first epoch metrics…")
                )
            else:
                self.metrics_label.setText("")
            return
        loss, map50, epochs = parsed
        parts = []
        if loss:
            parts.append(self.tr("loss %1").replace("%1", str(loss)))
        if map50:
            parts.append(self.tr("mAP50 %1").replace("%1", str(map50)))
        if epochs:
            parts.append(self.tr("%1 epoch").replace("%1", str(epochs)))
        eta_text = self._format_eta(results_file)
        if eta_text:
            parts.append(eta_text)
        self.metrics_label.setText(" · ".join(parts))

    def _format_eta(self, results_file):
        """``About 12 min left`` for a running job, else an empty string.

        Deliberately silent once the run is over (nothing is left) and before
        two epochs are known (nothing to average yet).
        """
        if self.training_status != "training":
            return ""
        remaining = estimate_remaining_seconds(results_file, self.total_epochs)
        if remaining is None:
            return ""
        if remaining < 60:
            return self.tr("Less than a minute left")
        return self.tr("About %1 min left").replace(
            "%1", str(int(round(remaining / 60)))
        )

    def update_training_images(self):
        if not self.current_project_path:
            return

        def find_images_by_pattern(patterns, max_count=3):
            found_files = []
            for pattern in patterns:
                matches = glob.glob(
                    os.path.join(self.current_project_path, pattern)
                )
                matches.sort()
                found_files.extend(matches)
                if len(found_files) >= max_count:
                    break
            return found_files[:max_count]

        if self.selected_task_type == "Classify":
            image_configs = [
                {"patterns": ["train_batch*.jpg"], "max_count": 3},
                {
                    "patterns": [
                        "val_batch0_labels.jpg",
                        "val_batch0_pred.jpg",
                        "results.png",
                    ],
                    "max_count": 3,
                },
            ]
        else:
            image_configs = [
                {"patterns": ["train_batch*.jpg"], "max_count": 3},
                {
                    "patterns": [
                        "*PR_curve.png",
                        "*F1_curve.png",
                        "results.png",
                    ],
                    "max_count": 3,
                },
            ]

        all_images = []
        for config in image_configs:
            all_images.extend(
                find_images_by_pattern(config["patterns"], config["max_count"])
            )

        for i, image_label in enumerate(self.image_labels):
            if i < len(all_images):
                image_path = all_images[i]
                try:
                    pixmap = QPixmap(image_path)
                    if not pixmap.isNull():
                        scaled_pixmap = pixmap.scaled(
                            150,
                            150,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        image_label.setPixmap(scaled_pixmap)
                        image_label.setText("")
                        image_label.setToolTip(
                            os.path.basename(image_path)
                            + "\n"
                            + self.tr("Click to page through the images")
                        )
                        self.image_paths[i] = image_path
                    else:
                        image_label.clear()
                        image_label.setText(self.tr("No image"))
                        image_label.setToolTip("")
                        self.image_paths[i] = None
                except Exception as e:
                    logger.warning(f"Failed to load image {image_path}: {e}")
                    image_label.clear()
                    image_label.setText(self.tr("No image"))
                    image_label.setToolTip("")
                    self.image_paths[i] = None
            else:
                image_label.clear()
                image_label.setText(self.tr("No image"))
                image_label.setToolTip("")
                self.image_paths[i] = None

    KEEP_DATASET_BUILDS = 5
    MIN_CLEANUP_OFFER_BYTES = 100 * 1024 * 1024

    def _offer_dataset_cleanup(self):
        """Ask before dropping old dataset builds the loop left behind.

        Every training copies the images on Windows and never reclaims them, so
        without this the folder only grows. The build the finished run used is
        excluded regardless of age.
        """
        task_root = os.path.join(
            get_dataset_path(), (self.selected_task_type or "").lower()
        )
        manifest = getattr(self, "_last_dataset_manifest", None) or {}
        current = None
        if manifest.get("data_yaml"):
            current = os.path.dirname(manifest["data_yaml"])
        candidates = plan_dataset_prune(
            collect_dataset_runs(task_root), self.KEEP_DATASET_BUILDS, current
        )
        if not candidates:
            return
        size = sum(directory_size(path) for path in candidates)
        if size < self.MIN_CLEANUP_OFFER_BYTES:
            return

        # Name the directories: "5 old builds" is not something anyone can
        # check before agreeing to delete them.
        listed = list(candidates[:MAX_LISTED_SKIPS])
        extra = len(candidates) - len(listed)
        body = [
            self.tr(
                "Training left dataset copies taking %1 across %2 old directories."
            )
            .replace("%1", f"{size / (1024 * 1024):.1f} MB")
            .replace("%2", str(len(candidates))),
            "",
        ]
        body.extend(f"  {os.path.basename(path)}" for path in listed)
        if extra > 0:
            body.append(
                "  " + self.tr("... and %1 more").replace("%1", str(extra))
            )
        body.extend(
            [
                "",
                self.tr(
                    "Delete the old copies beyond this run? The most recent %1 are kept."
                ).replace("%1", str(self.KEEP_DATASET_BUILDS)),
            ]
        )

        answer = QMessageBox.question(
            self,
            self.tr("Clean up old dataset copies"),
            "\n".join(body),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        deleted, freed, failed = prune_datasets(
            task_root, self.KEEP_DATASET_BUILDS, current
        )
        self.append_training_log(
            self.tr("Cleaned %1 dataset copies, freeing %2 MB.")
            .replace("%1", str(len(deleted)))
            .replace("%2", f"{freed / (1024 * 1024):.1f}")
        )
        if failed:
            self.append_training_log(
                self.tr(
                    "%1 directories could not be deleted (possibly in use)."
                ).replace("%1", str(len(failed)))
            )

    def write_run_metadata(self, status="completed"):
        """Record what this run trained on, beside its weights.

        The dataset is a mutable set of label JSONs that keeps being edited
        after training, so without this snapshot a completed run cannot be
        tied back to the annotations and arguments that produced it.

        ``status`` distinguishes a finished run from one the user stopped.
        A stopped run writes this too: it has a ``results.csv``, a resumable
        ``last.pt``, and it is the very run someone wants to compare against
        the full one — leaving it out of the history made "round 2, interrupted
        vs round 3, finished" unanswerable.
        """
        project_path = self.current_project_path
        if not project_path or not os.path.isdir(project_path):
            return None

        manifest = getattr(self, "_last_dataset_manifest", None) or {}
        dataset_dir = os.path.dirname(manifest.get("data_yaml") or "") or None
        from anylabeling.views.labeling.project import label_dir_for_dataset

        label_dir = label_dir_for_dataset(
            getattr(self, "output_dir", None),
            getattr(self, "image_list", None),
        )
        manifest_path = (
            os.path.join(dataset_dir, "manifest.json") if dataset_dir else None
        )
        weights = os.path.join(project_path, "weights", "best.pt")
        metrics = parse_training_metrics(
            os.path.join(project_path, "results.csv")
        )
        started_at = getattr(self, "_training_started_at", None)
        meta = {
            "schema": 1,
            "task": self.selected_task_type,
            "status": status,
            "project": os.path.dirname(project_path),
            "name": os.path.basename(project_path),
            "started_at": (
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_at))
                if started_at
                else None
            ),
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "weights": {
                "path": weights if os.path.isfile(weights) else None,
                "sha1": file_sha1(weights),
            },
            "train_args": dict(getattr(self, "_last_train_args", None) or {}),
            "dataset": {
                "dir": dataset_dir,
                "label_dir": label_dir,
                "manifest": manifest_path,
                "manifest_sha1": (
                    file_sha1(manifest_path) if manifest_path else None
                ),
                "seed": manifest.get("seed"),
                "classes": manifest.get("classes"),
                "counts": manifest.get("counts"),
            },
            "metrics": (
                None
                if metrics is None
                else {
                    "loss": metrics[0],
                    "map50": metrics[1],
                    "epochs": metrics[2],
                }
            ),
        }

        meta_path = os.path.join(project_path, "run_meta.json")
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except OSError as e:  # noqa: BLE001
            logger.warning(f"Failed to write run metadata: {e}")
            return None
        return meta_path

    def on_training_event(self, event_type, data):
        if event_type == "training_started":
            self.training_status = "training"
            self.total_epochs = data["total_epochs"]
            self.current_epochs = 0
            self._training_started_at = time.time()
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat(f"0/{self.total_epochs}")
            self.update_training_status_display()
            self.start_training_button.setVisible(False)
            self.stop_training_button.setVisible(True)
            self.export_button.setVisible(False)
            self.previous_button.setVisible(False)
            if hasattr(self, "use_autolabel_button"):
                self.use_autolabel_button.setVisible(False)
            if hasattr(self, "resume_training_button"):
                self.resume_training_button.setVisible(False)
            self.refresh_wizard_state()
            self.progress_timer.start(1000)
            self.image_timer.start(5000)
            self.append_training_log(self.tr("Training is about to start..."))
        elif event_type == "training_completed":
            self.training_status = "completed"
            self.write_run_metadata()
            self._offer_dataset_cleanup()
            self.update_training_status_display()
            self.stop_training_button.setVisible(False)
            self.start_training_button.setVisible(False)
            self.previous_button.setVisible(True)
            self.export_button.setVisible(True)
            if hasattr(self, "use_autolabel_button"):
                self.use_autolabel_button.setVisible(True)
            if hasattr(self, "resume_training_button"):
                self.resume_training_button.setVisible(False)
            self.progress_timer.stop()
            self.image_timer.stop()
            self.update_training_progress()
            self.update_training_images()
            self.refresh_wizard_state()
            self.append_training_log(
                self.tr("Training completed successfully!")
            )
            self.save_training_logs_to_file()
        elif event_type == "training_error":
            self._handle_training_error(data)
        elif event_type == "training_stopped":
            self.training_status = "stop"
            # A stopped run is a real run: it has a results.csv, a resumable
            # last.pt and arguments worth keeping. Writing the record here is
            # what lets the history tell it apart from a finished one instead
            # of counting it as "unrecorded".
            self.write_run_metadata(status="stopped")
            self.update_training_status_display()
            self.start_training_button.setVisible(False)
            self.previous_button.setVisible(True)
            self.stop_training_button.setVisible(False)
            self.export_button.setVisible(False)
            if hasattr(self, "use_autolabel_button"):
                self.use_autolabel_button.setVisible(False)
            # A stopped run can usually continue from its last.pt: surface the
            # resume entry point right here instead of routing through Config.
            # (The click validates the checkpoint; a plain stat keeps this
            # event handler free of a torch checkpoint load.)
            last_pt = os.path.join(
                self.current_project_path or "", "weights", "last.pt"
            )
            if hasattr(self, "resume_training_button"):
                self.resume_training_button.setVisible(os.path.isfile(last_pt))
            self.refresh_wizard_state()
            self.progress_timer.stop()
            self.image_timer.stop()
            self.append_training_log(self.tr("Training stopped by user"))
            self.save_training_logs_to_file()
        elif event_type == "training_log":
            log_message = data.get("message", "")
            if log_message:
                self.append_training_log(log_message)

    def _handle_training_error(self, data):
        """Report a failed run, offering a remedy when one can be named.

        Kept out of ``on_training_event`` so that dispatcher stays a readable
        switch over the event types.
        """
        self.training_status = "error"
        self.update_training_status_display()
        self.start_training_button.setVisible(False)
        self.previous_button.setVisible(True)
        self.stop_training_button.setVisible(False)
        self.export_button.setVisible(False)
        if hasattr(self, "use_autolabel_button"):
            self.use_autolabel_button.setVisible(False)
        if hasattr(self, "resume_training_button"):
            self.resume_training_button.setVisible(False)
        self.refresh_wizard_state()
        self.progress_timer.stop()
        self.image_timer.stop()

        error_msg = data.get("error", "Unknown error occurred")
        trace = data.get("traceback", "")
        self.append_training_log(f"ERROR: {error_msg}")
        if trace:
            # Keep the full traceback in the log view so advanced users can
            # diagnose crashes, while the dialog shows a readable summary.
            self.append_training_log(self.tr("--- Traceback ---"))
            self.append_training_log(trace.strip())
        # Persist before the modal box: the log view can be cleared (or the
        # app closed) while the box is up, and this is the only copy.
        self.save_training_logs_to_file()

        # Explain cryptic codes (e.g. Windows -1073741819 == access
        # violation) and offer an explicit retry path.
        readable = self._readable_training_error(error_msg)
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Icon.Critical)
        box.setWindowTitle(self.tr("Training Failed"))
        box.setText(self.tr("Training failed:\n%s") % readable)
        if trace:
            box.setInformativeText(
                self.tr("Full traceback was written to the training log.")
            )
        # One-click remedies for the failure modes we can name: pressing plain
        # retry after an OOM reproduces the OOM.
        fix_buttons = []
        for label, changes in self._error_quick_fixes(error_msg):
            fix_buttons.append(
                (
                    box.addButton(
                        label,
                        QtWidgets.QMessageBox.ButtonRole.AcceptRole,
                    ),
                    changes,
                )
            )
        retry_btn = box.addButton(
            self.tr("Retry Training"),
            QtWidgets.QMessageBox.ButtonRole.AcceptRole,
        )
        box.addButton(
            self.tr("Back to Config"),
            QtWidgets.QMessageBox.ButtonRole.RejectRole,
        )
        box.setDefaultButton(fix_buttons[0][0] if fix_buttons else retry_btn)
        box.exec()

        clicked = box.clickedButton()
        fix = next(
            (changes for button, changes in fix_buttons if clicked is button),
            None,
        )
        if fix is not None:
            applied = self._apply_error_fix(fix)
            self.reset_train_tab()
            if applied:
                self.append_training_log(
                    self.tr("Applied a quick fix before retrying: %1").replace(
                        "%1", applied
                    )
                )
            self.start_training_from_train_tab()
        elif clicked is retry_btn:
            self.reset_train_tab()
            self.start_training_from_train_tab()
        else:
            self.go_to_specific_tab(1)

    def _error_quick_fixes(self, error_msg):
        """One-click remedies for the failure modes we can name.

        Each entry is ``(label, {widget key: new value})``. Values are decided
        now, from the current form, so a fix always halves what the user
        actually has rather than a default.
        """
        text = str(error_msg).lower()
        config_widgets = getattr(self, "config_widgets", {})
        if any(marker in text for marker in OOM_ERROR_MARKERS):
            batch = config_widgets.get("batch")
            current = batch.value() if batch is not None else 0
            new_batch = (
                max(1, int(current) // 2)
                if current and current > 0
                else DEFAULT_TRAINING_CONFIG["batch"] // 2
            )
            return [(self.tr("Halve Batch & Retry"), {"batch": new_batch})]
        if "-1073741819" in text or "-1073740940" in text:
            # Access violation / heap corruption: the data-loader workers are
            # the usual suspects on Windows, hence the smallest real change.
            return [(self.tr("Set Workers to 0 & Retry"), {"workers": 0})]
        if "no cuda-capable device" in text or "cuda error" in text:
            return [(self.tr("Switch to CPU & Retry"), {"device": "cpu"})]
        return []

    def _apply_error_fix(self, changes):
        """Write a quick fix into the form; returns what it changed."""
        applied = []
        for key, value in changes.items():
            widget = self.config_widgets.get(key)
            if widget is None:
                continue
            if key == "device":
                # Through the combo, so the CPU adaptations run as well.
                index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)
            elif isinstance(widget, CustomCheckBox):
                widget.setChecked(bool(value))
            else:
                widget.setValue(value)
            applied.append(f"{key}={value}")
        return ", ".join(applied)

    def append_training_log(self, text):
        def clean_ansi_codes(text: str) -> str:
            ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
            return ansi_escape.sub("", text)

        if hasattr(self, "log_display"):
            text = clean_ansi_codes(text)
            self.log_display.append(text.strip())

    def _readable_training_error(self, error_msg):
        """Map cryptic process codes to a human-readable explanation."""
        text = str(error_msg)
        if "exited with code -1073741819" in text:
            return self.tr(
                "The training worker crashed (access violation). "
                "This is usually caused by CUDA / driver / memory issues. "
                "Please check the training log above for the traceback."
            )
        if "exited with code -1073740940" in text:
            return self.tr(
                "The training worker crashed (heap corruption). "
                "This is usually caused by CUDA / driver issues. "
                "Please check the training log above."
            )
        if "No CUDA-capable device" in text or "CUDA out of memory" in text:
            return self.tr(
                "CUDA error: the GPU is unavailable or out of memory. "
                "Select CPU or a different device in the config, "
                "or free GPU memory and retry."
            )
        if "exited with code" in text:
            return (
                self.tr(
                    "%s — the training subprocess terminated unexpectedly. "
                    "Please check the training log above for details."
                )
                % text
            )
        return text

    def init_training_status(self, parent_layout):
        status_group = QGroupBox(self.tr("Training Status"))
        status_layout = QVBoxLayout(status_group)

        self.status_label = QLabel(self.tr("Ready to train"))
        self.status_label.setStyleSheet(get_status_label_style())
        status_layout.addWidget(self.status_label)

        progress_layout = QHBoxLayout()
        progress_layout.addWidget(QLabel(self.tr("Progress:")))
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0/0")
        self.progress_bar.setStyleSheet(get_progress_bar_style())
        progress_layout.addWidget(self.progress_bar)
        status_layout.addLayout(progress_layout)
        self.metrics_label = QLabel("")
        self.metrics_label.setWordWrap(True)
        status_layout.addWidget(self.metrics_label)
        parent_layout.addWidget(status_group)

    def clear_training_logs(self):
        if hasattr(self, "log_display"):
            reply = QMessageBox.question(
                self,
                self.tr("Clear Logs"),
                self.tr("Are you sure you want to clear all training logs?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.log_display.clear()

    def copy_training_logs(self):
        if hasattr(self, "log_display"):
            text = self.log_display.toPlainText()
            if text:
                clipboard = QApplication.clipboard()
                clipboard.setText(text)

    def init_training_logs(self, parent_layout):
        logs_group = QGroupBox(self.tr("Training Logs"))
        logs_layout = QVBoxLayout(logs_group)

        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setMinimumHeight(250)
        self.log_display.setStyleSheet(get_log_display_style())
        # A long run's stdout would otherwise grow without bound; the file the
        # terminal-state save writes keeps the tail that fits here.
        self.log_display.document().setMaximumBlockCount(LOG_DISPLAY_MAX_LINES)
        logs_layout.addWidget(self.log_display)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.clear_logs_button = SecondaryButton(self.tr("Clear"))
        self.clear_logs_button.clicked.connect(self.clear_training_logs)
        button_layout.addWidget(self.clear_logs_button)

        self.copy_logs_button = SecondaryButton(self.tr("Copy"))
        self.copy_logs_button.clicked.connect(self.copy_training_logs)
        button_layout.addWidget(self.copy_logs_button)

        logs_layout.addLayout(button_layout)
        parent_layout.addWidget(logs_group)

    def init_training_images(self, parent_layout):
        images_group = QGroupBox(self.tr("Training Images"))
        images_layout = QVBoxLayout(images_group)
        images_layout.setContentsMargins(5, 5, 5, 5)

        self.image_labels = []
        self.image_paths = [None] * 6
        self.images_widget = QWidget()
        images_row_layout = QHBoxLayout(self.images_widget)
        images_row_layout.setSpacing(10)
        images_row_layout.setContentsMargins(0, 0, 0, 0)

        for i in range(6):
            image_label = QLabel()
            image_label.setMinimumSize(150, 150)
            image_label.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            image_label.setStyleSheet(get_image_label_style())
            image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image_label.setText(self.tr("No image"))
            image_label.setScaledContents(False)
            image_label.mousePressEvent = (
                lambda event, idx=i: self.on_image_clicked(idx)
            )
            self.image_labels.append(image_label)
            images_row_layout.addWidget(image_label, 1)

        images_layout.addWidget(self.images_widget, 1)
        parent_layout.addWidget(images_group, 1)

    def on_image_clicked(self, index):
        """Open the built-in pager at the clicked thumbnail.

        The six slots show a subset; the pager carries every image the run
        wrote so the rest are reachable without leaving the dialog.
        """
        clicked_path = self.image_paths[index]
        if not clicked_path:
            return
        paths = self._collect_preview_images() or [
            path for path in self.image_paths if path
        ]
        try:
            start = paths.index(clicked_path)
        except ValueError:
            start = 0
        preview = TrainingImagePreviewDialog(paths, start, self)
        preview.exec()

    def _collect_preview_images(self):
        """Every training image this run has written, in reading order."""
        if not self.current_project_path:
            return []
        patterns = [
            "train_batch*.jpg",
            "val_batch*_labels.jpg",
            "val_batch*_pred.jpg",
            "results.png",
            "*PR_curve.png",
            "*F1_curve.png",
            "confusion_matrix*.png",
        ]
        found = []
        for pattern in patterns:
            matches = glob.glob(
                os.path.join(self.current_project_path, pattern)
            )
            found.extend(sorted(matches))
        return found

    def open_image_file(self, image_path):
        open_path(image_path)

    def open_training_directory(self):
        if self.current_project_path and os.path.exists(
            self.current_project_path
        ):
            if open_path(self.current_project_path):
                return
            QMessageBox.information(
                self,
                self.tr("Info"),
                self.tr("Could not open this directory:\n%1").replace(
                    "%1", self.current_project_path
                ),
            )
        else:
            QMessageBox.information(
                self,
                self.tr("Info"),
                self.tr("No training directory available"),
            )

    def stop_training(self):
        reply = QMessageBox.question(
            self,
            self.tr("Confirm Stop"),
            self.tr("Are you sure you want to stop the training?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            success = self.training_manager.stop_training()
            if success:
                self.append_training_log(self.tr("Stopping training..."))
            else:
                self.append_training_log(self.tr("Cancel to stop training"))

    def _project_split_seed(self):
        """``(seed, source)`` pinned for the dataset currently being trained.

        The same seed across rounds is what makes two mAP numbers comparable;
        a freshly random split every round turns val-set churn into an
        apparent model improvement.
        """
        from anylabeling.views.labeling.project import (
            get_or_create_split_seed,
            label_dir_for_dataset,
        )

        label_dir = label_dir_for_dataset(
            self.output_dir, getattr(self, "image_list", None)
        )
        if not label_dir:
            return None, "generated"
        seed, created = get_or_create_split_seed(label_dir)
        return seed, "project" if created else "pinned"

    def get_training_args(self, config, data_path=None):
        try:
            if data_path is None:
                if self.selected_task_type == "Classify" and os.path.isdir(
                    config["basic"]["data"]
                ):
                    data_path = config["basic"]["data"]
                    self.append_training_log(
                        f"Using existing dataset: {data_path}"
                    )
                else:
                    # Synchronous fallback (the train-tab entry point runs
                    # this step on a background thread and passes data_path).
                    seed, seed_source = self._project_split_seed()
                    report = {}
                    temp_dir = create_yolo_dataset(
                        self.image_list,
                        self.selected_task_type,
                        config["basic"]["dataset_ratio"],
                        config["basic"]["data"],
                        self.output_dir,
                        config["basic"].get("pose_config"),
                        config["checkpoint"].get("skip_empty_files", False),
                        config["checkpoint"].get("only_checked_files", False),
                        seed=seed,
                        seed_source=seed_source,
                        report=report,
                    )
                    self._dataset_report = report
                    logger.info(
                        f"Successfully created YOLO dataset at {temp_dir}"
                    )
                    self.append_training_log(f"Created dataset: {temp_dir}")
                    if self.selected_task_type == "Classify":
                        data_path = temp_dir
                    else:
                        data_path = os.path.join(temp_dir, "data.yaml")

            device_value = config["basic"]["device"]
            if device_value == "cuda" and hasattr(self, "device_checkboxes"):
                selected_gpus = []
                if hasattr(self, "_cuda_layout") and self._cuda_layout:
                    for i in range(self._cuda_layout.count()):
                        widget = self._cuda_layout.itemAt(i).widget()
                        if (
                            widget
                            and hasattr(widget, "isChecked")
                            and widget.isChecked()
                        ):
                            gpu_text = widget.text()
                            gpu_id = gpu_text.split()[-1]
                            selected_gpus.append(int(gpu_id))
                device_value = selected_gpus if selected_gpus else "cpu"

            # The split was already drawn with this seed while building the
            # dataset; handing it to Ultralytics keeps the whole run tied to
            # the manifest instead of re-randomising on every other axis.
            manifest = load_dataset_manifest(data_path)

            if self._resume_from:
                # Resume: ultralytics restores project/name/epochs and every
                # hyperparameter from the checkpoint, then allows only a few
                # overrides through (device, imgsz, batch, ...). Passing just
                # those keeps the log free of "Resume ignores [...]" warnings.
                train_args = {
                    "model": self._resume_from,
                    "resume": True,
                    "data": data_path,
                    "device": device_value,
                }
                info = self._resume_info or {}
                if info.get("epochs"):
                    # Same value the checkpoint records, so it is not reported
                    # as an ignored override; it also keeps the progress bar
                    # honest about the total.
                    train_args["epochs"] = info["epochs"]
                self.total_epochs = train_args.get("epochs", 100)
                self._last_train_args = dict(train_args)
                self._last_dataset_manifest = manifest
                cmd_parts = ["yolo", self.selected_task_type.lower(), "train"]
                for key, value in train_args.items():
                    cmd_parts.append(f"{key}={value}")
                self.append_training_log(
                    f"Training command: {' '.join(cmd_parts)}"
                )
                return train_args

            train_args = {
                "data": data_path,
                "model": config["basic"]["model"],
                "project": config["basic"]["project"],
                "name": config["basic"]["name"],
                "device": device_value,
            }

            # Add advanced parameters
            advanced_params = {}
            for section in [
                "train",
                "strategy",
                "learning_rate",
                "warmup",
                "augment",
                "regularization",
                "loss_weights",
                "checkpoint",
            ]:
                advanced_params.update(config.get(section, {}))
            # Exclude X-AnyLabeling specific parameters not recognized by ultralytics
            xany_params_to_exclude = {"skip_empty_files", "only_checked_files"}
            for key, value in advanced_params.items():
                if key not in xany_params_to_exclude:
                    train_args[key] = value
            if manifest and manifest.get("seed") is not None:
                train_args.setdefault("seed", manifest["seed"])
            self.total_epochs = train_args.get("epochs", 100)
            # Kept for run_meta.json: the payload file the worker reads is
            # deleted when the process ends, so this is the only record of the
            # arguments this run was launched with.
            self._last_train_args = dict(train_args)
            self._last_dataset_manifest = manifest

            # Log the training command
            cmd_parts = ["yolo", self.selected_task_type.lower(), "train"]
            for key, value in train_args.items():
                cmd_parts.append(f"{key}={value}")
            self.append_training_log(
                f"Training command: {' '.join(cmd_parts)}"
            )

            return train_args

        except Exception as e:
            self.append_training_log(
                f"Error preparing training args: {str(e)}"
            )
            raise

    def _resolve_filter_names(self, config):
        """Class names the ``classes`` filter is checked against.

        Cheap on purpose: the data config when there is one, else whatever the
        label panel already knows. Reading every label file here would put a
        full folder scan in front of the Start button.
        """
        data_path = (config.get("basic") or {}).get("data") or ""
        if data_path and os.path.isfile(data_path):
            is_valid, result = validate_data_file(data_path)
            if is_valid and isinstance(result, list):
                return result
        return list(getattr(self, "names", None) or [])

    def _check_classes_filter(self, config):
        """Refuse a ``classes`` filter whose indices are not in the dataset.

        Every index out of range means ultralytics trains on nothing, and the
        resulting mAP describes the filter rather than the data — the failure
        reads as "my dataset is bad". ``validate_classes`` existed for this and
        had no caller until now.
        """
        is_valid, message = validate_classes(
            (config.get("train") or {}).get("classes"),
            self._resolve_filter_names(config),
        )
        if is_valid:
            return True
        QMessageBox.warning(self, self.tr("Validation Error"), message)
        self.append_training_log(f"Validation Error: {message}")
        return False

    def start_training_from_train_tab(self):
        config = self.get_current_config()
        project_path = config["basic"]["project"]
        name = config["basic"]["name"]
        self.current_project_path = os.path.join(project_path, name)

        # Both entry points land here (the Config tab commits first and calls
        # this, the Train tab calls it directly), so the filter check sits
        # here rather than in either caller.
        if not self._check_classes_filter(config):
            return

        # Re-entrancy guard: dataset preparation runs on a background thread.
        if (
            self._dataset_thread is not None
            and self._dataset_thread.is_alive()
        ):
            self.append_training_log(
                self.tr("Dataset is still being prepared...")
            )
            return

        # The run is committed: remember its tuning for this dataset.
        self._save_project_train_prefs(config)

        # If the dataset already exists (classification on a folder),
        # take the fast path without any background preparation.
        if self.selected_task_type == "Classify" and os.path.isdir(
            config["basic"]["data"]
        ):
            try:
                self.append_training_log(self.tr("Preparing training..."))
                train_args = self.get_training_args(config)
                self._start_training_after_args(train_args)
            except Exception as e:
                error_msg = f"Failed to start training: {str(e)}"
                self.append_training_log(f"ERROR: {error_msg}")
                QMessageBox.critical(
                    self, self.tr("Training Error"), error_msg
                )
            return

        # Build the dataset off the UI thread so large image sets do not
        # freeze the dialog for tens of seconds / minutes.
        self._dataset_pending_config = config
        self.start_training_button.setEnabled(False)
        self.start_training_button.setText(self.tr("Preparing dataset..."))
        # Name the phase in the status area too: the button is on the config
        # tab, and "Ready to train" would otherwise sit there for the whole
        # build (the training_started event takes over from here).
        self.training_status = "preparing"
        self.update_training_status_display()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(self.tr("Preparing dataset..."))
        if hasattr(self, "metrics_label"):
            self.metrics_label.setText(self.tr("Preparing dataset..."))
        self.refresh_wizard_state()
        self.append_training_log(
            self.tr("Preparing dataset in the background...")
        )
        self._dataset_thread = threading.Thread(
            target=self._prepare_dataset_worker,
            args=(config,),
            daemon=True,
        )
        self._dataset_thread.start()

    def _prepare_dataset_worker(self, config):
        """Run create_yolo_dataset off the UI thread (pure file IO)."""
        temp_dir = None
        error_msg = ""
        report = {}
        try:
            # Runs on a worker thread: no widget calls here. The seed reaches
            # the log through the training command line on the UI thread.
            seed, seed_source = self._project_split_seed()
            temp_dir = create_yolo_dataset(
                self.image_list,
                self.selected_task_type,
                config["basic"]["dataset_ratio"],
                config["basic"]["data"],
                self.output_dir,
                config["basic"].get("pose_config"),
                config["checkpoint"].get("skip_empty_files", False),
                config["checkpoint"].get("only_checked_files", False),
                seed=seed,
                seed_source=seed_source,
                report=report,
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"Dataset preparation failed: {e}")
            error_msg = str(e)
        # Read by the UI thread once the queued signal lands; the assignment
        # happens before the emit so the dict is always there.
        self._dataset_report = report
        # PyQt signals are thread-safe; delivery is queued to the UI thread.
        self.dataset_preparation_finished.emit(temp_dir or "", error_msg)

    def _report_dataset_skips(self, report):
        """Put what a build left out into the log; returns the skip list."""
        skips = dataset_skips(report)
        for kind, count, _details in skips:
            if kind == "unreadable":
                self.append_training_log(
                    self.tr(
                        "%1 label file(s) could not be read; they are NOT in the dataset."
                    ).replace("%1", str(count))
                )
            elif kind == "failed":
                self.append_training_log(
                    self.tr(
                        "%1 label file(s) failed to convert; they are NOT in the dataset."
                    ).replace("%1", str(count))
                )
            else:
                self.append_training_log(
                    self.tr(
                        "%1 shape(s) were dropped by the converter (not representable in this task)."
                    ).replace("%1", str(count))
                )
        return skips

    def _confirm_dataset_skips(self, report):
        """Ask before training on a dataset that had to leave files out.

        Returns True to continue. An unreadable or unconvertible label file
        means the image is not in the dataset at all, and that must not happen
        quietly: the model then never sees annotation the person training it
        believes went in. The default button is the one that does not train.
        """
        blocking = [
            entry
            for entry in dataset_skips(report)
            if is_blocking_dataset_skip(entry[0])
        ]
        if not blocking:
            return True

        lines = []
        for kind, count, details in blocking:
            if kind == "unreadable":
                lines.append(
                    self.tr(
                        "%1 label file(s) exist but could not be read, so they were left out of the dataset:"
                    ).replace("%1", str(count))
                )
            else:
                lines.append(
                    self.tr(
                        "%1 label file(s) could not be converted, so they were left out of the dataset:"
                    ).replace("%1", str(count))
                )
            for item in details[:MAX_LISTED_SKIPS]:
                lines.append(f"  {item}")
            if len(details) > MAX_LISTED_SKIPS:
                lines.append(
                    "  "
                    + self.tr("... and %1 more").replace(
                        "%1", str(len(details) - MAX_LISTED_SKIPS)
                    )
                )
        lines.append("")
        lines.append(
            self.tr(
                "They are not negative samples: nothing in them reaches the model. The full list is in the dataset's manifest.json and dataset_info.txt."
            )
        )

        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        box.setWindowTitle(self.tr("Dataset Incomplete"))
        box.setText("\n".join(lines))
        train_btn = box.addButton(
            self.tr("Train Anyway"),
            QtWidgets.QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_btn = box.addButton(
            self.tr("Back to Config"),
            QtWidgets.QMessageBox.ButtonRole.RejectRole,
        )
        box.setDefaultButton(cancel_btn)
        box.exec()
        return box.clickedButton() is train_btn

    def _leave_preparing_status(self):
        """Drop the dataset-build phase when the build did not lead to a run."""
        self.training_status = "idle"
        self.update_training_status_display()
        self.progress_bar.setFormat("0/0")
        if hasattr(self, "metrics_label"):
            self.metrics_label.setText("")
        self.refresh_wizard_state()

    def _on_dataset_preparation_finished(self, temp_dir, error_msg):
        """Continue the training flow once the background dataset is ready."""
        self._dataset_thread = None
        self.start_training_button.setEnabled(True)
        self.start_training_button.setText(self.tr("Start Training"))

        if error_msg:
            self._leave_preparing_status()
            self.append_training_log(f"Failed to prepare dataset: {error_msg}")
            QMessageBox.critical(
                self,
                self.tr("Dataset Error"),
                self.tr("Failed to prepare dataset:\n%s") % error_msg,
            )
            return
        if not temp_dir:
            self._leave_preparing_status()
            self.append_training_log(
                self.tr("Dataset preparation returned no output directory.")
            )
            return

        logger.info(f"Successfully created YOLO dataset at {temp_dir}")
        self.append_training_log(f"Created dataset: {temp_dir}")

        # A build that had to leave label files out says so here, before the
        # run starts: those images are absent from the dataset, not trained as
        # empty ones, and the difference is invisible in the metrics.
        report = getattr(self, "_dataset_report", None) or {}
        self._report_dataset_skips(report)
        if not self._confirm_dataset_skips(report):
            self._leave_preparing_status()
            self.append_training_log(
                self.tr(
                    "Training cancelled: fix the listed label files first."
                )
            )
            return

        config = self._dataset_pending_config
        try:
            if self.selected_task_type == "Classify":
                data_path = temp_dir
            else:
                data_path = os.path.join(temp_dir, "data.yaml")
            train_args = self.get_training_args(config, data_path=data_path)
            self._start_training_after_args(train_args)
        except Exception as e:
            error_msg = f"Failed to start training: {str(e)}"
            self.append_training_log(f"ERROR: {error_msg}")
            QMessageBox.critical(self, self.tr("Training Error"), error_msg)

    def _start_training_after_args(self, train_args):
        success, message = self.training_manager.start_training(train_args)
        if not success:
            self.append_training_log(f"Failed to start training: {message}")
            QMessageBox.critical(self, self.tr("Training Error"), message)

    def init_training_actions(self, parent_layout):
        actions_layout = QHBoxLayout()

        self.open_dir_button = SecondaryButton(self.tr("Open Directory"))
        self.open_dir_button.clicked.connect(self.open_training_directory)
        actions_layout.addWidget(self.open_dir_button)
        actions_layout.addStretch()

        self.stop_training_button = SecondaryButton(self.tr("Stop Training"))
        self.stop_training_button.clicked.connect(self.stop_training)
        self.stop_training_button.setVisible(False)
        actions_layout.addWidget(self.stop_training_button)

        self.previous_button = SecondaryButton(self.tr("Previous"))
        self.previous_button.clicked.connect(
            lambda: self.go_to_specific_tab(1)
        )
        self.previous_button.setVisible(True)
        actions_layout.addWidget(self.previous_button)

        # Shown after a stop: one click continues the run from its last.pt
        # instead of forcing a trip back through the Config tab.
        self.resume_training_button = PrimaryButton(self.tr("Resume Training"))
        self.resume_training_button.setToolTip(
            self.tr("Continue this run from weights/last.pt")
        )
        self.resume_training_button.clicked.connect(
            self._on_resume_training_clicked
        )
        self.resume_training_button.setVisible(False)
        actions_layout.addWidget(self.resume_training_button)

        self.start_training_button = PrimaryButton(self.tr("Start Training"))
        self.start_training_button.clicked.connect(
            self.start_training_from_train_tab
        )
        actions_layout.addWidget(self.start_training_button)

        self.export_button = PrimaryButton(self.tr("Export"))
        self.export_button.clicked.connect(self.start_export)
        self.export_button.setVisible(False)
        actions_layout.addWidget(self.export_button)

        self.use_autolabel_button = PrimaryButton(
            self.tr("Use for Auto-labeling")
        )
        self.use_autolabel_button.setToolTip(
            self.tr("Export ONNX and load it into the auto-labeling panel")
        )
        self.use_autolabel_button.clicked.connect(
            self.use_weights_for_autolabel
        )
        self.use_autolabel_button.setVisible(False)
        actions_layout.addWidget(self.use_autolabel_button)

        parent_layout.addLayout(actions_layout)

    def init_train_tab(self):
        layout = QVBoxLayout(self.train_tab)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        self.init_training_status(scroll_layout)
        self.init_training_logs(scroll_layout)
        self.init_training_images(scroll_layout)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        self.init_training_actions(layout)

    def on_export_event(self, event_type, data):
        if event_type == "export_started":
            self.append_training_log(self.tr("Export started..."))
            self.export_button.setEnabled(False)
            if hasattr(self, "use_autolabel_button"):
                self.use_autolabel_button.setEnabled(False)
        elif event_type == "export_completed":
            exported_path = data.get("exported_path", "")
            export_format = data.get("format", "onnx")
            self.append_training_log(
                self.tr(
                    f"Export completed successfully! File saved to: {exported_path}"
                )
            )
            self.export_button.setEnabled(True)
            if hasattr(self, "use_autolabel_button"):
                self.use_autolabel_button.setEnabled(True)
            if self._pending_autolabel_after_export:
                self._pending_autolabel_after_export = False
                if exported_path:
                    self._load_exported_weights_for_autolabel(exported_path)
                return
            QMessageBox.information(
                self,
                self.tr("Export Successful"),
                self.tr(
                    f"Model successfully exported to {export_format.upper()} format:\n{exported_path}"
                ),
            )
        elif event_type == "export_error":
            error_msg = data.get("error", "Unknown error occurred")
            self.append_training_log(f"ERROR: {error_msg}")
            self.export_button.setEnabled(True)
            if hasattr(self, "use_autolabel_button"):
                self.use_autolabel_button.setEnabled(True)
            if self._pending_autolabel_after_export:
                self._pending_autolabel_after_export = False
                QMessageBox.warning(
                    self,
                    self.tr("Export Error"),
                    self.tr(
                        "Failed to export ONNX; not loaded into auto-labeling.\n%1"
                    ).replace("%1", error_msg),
                )
                return
            QMessageBox.warning(self, self.tr("Export Error"), error_msg)
        elif event_type == "export_log":
            log_message = data.get("message", "")
            if log_message:
                self.append_training_log(log_message)

    def start_export(self):
        if not self.current_project_path:
            QMessageBox.warning(
                self,
                self.tr("Error"),
                self.tr("No training project available for export"),
            )
            return

        weights_path = os.path.join(
            self.current_project_path, "weights", "best.pt"
        )
        if not os.path.exists(weights_path):
            QMessageBox.warning(
                self,
                self.tr("Model Not Found"),
                self.tr(f"Model weights not found at: {weights_path}"),
            )
            return

        export_dialog = ExportFormatDialog(self)
        if export_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        export_format = export_dialog.get_selected_format()
        if not self._confirm_export_dependencies(export_format):
            return
        success, message = self.export_manager.start_export(
            self.current_project_path, export_format, allow_install=True
        )
        if not success:
            QMessageBox.critical(self, self.tr("Export Error"), message)
            self.append_training_log(f"Failed to start export: {message}")

    def _resolve_class_names(self):
        if self.names:
            return list(self.names)
        if getattr(self, "_config_tab_initialized", False):
            widget = self.config_widgets.get("data")
            if widget is not None:
                path = widget.text().strip().strip('"')
                if path and os.path.isfile(path):
                    is_valid, result = validate_data_file(path)
                    if is_valid and isinstance(result, list):
                        return result
        return collect_class_names(self.image_list, self.output_dir)

    def use_weights_for_autolabel(self):
        model_type = autolabel_type_for_task(self.selected_task_type)
        if not model_type:
            QMessageBox.information(
                self,
                self.tr("Not supported yet"),
                self.tr(
                    "No auto-labeling type for this task yet; export the weights and load the model manually. Supported: detect / segment / pose / classify (ONNX)."
                ),
            )
            return
        if not self.current_project_path:
            QMessageBox.warning(
                self,
                self.tr("Error"),
                self.tr("No training project available for export"),
            )
            return
        weights_path = os.path.join(
            self.current_project_path, "weights", "best.pt"
        )
        if not os.path.exists(weights_path):
            QMessageBox.warning(
                self,
                self.tr("Model Not Found"),
                self.tr("Model weights not found at: %1").replace(
                    "%1", weights_path
                ),
            )
            return
        onnx_path = os.path.join(
            self.current_project_path, "weights", "best.onnx"
        )
        if os.path.exists(onnx_path) and not is_fresh_export(
            onnx_path, weights_path
        ):
            # Reusing a stale artifact silently pairs the run on screen with
            # the model from before the last resume, so it is rebuilt instead.
            self.append_training_log(
                self.tr(
                    "The existing ONNX export is older than best.pt; exporting again."
                )
            )
        elif os.path.exists(onnx_path):
            self._load_exported_weights_for_autolabel(onnx_path)
            return
        if not self._confirm_export_dependencies("onnx"):
            self.append_training_log(
                self.tr(
                    "Auto-labeling export cancelled: dependencies missing."
                )
            )
            return
        self._pending_autolabel_after_export = True
        self.use_autolabel_button.setEnabled(False)
        self.append_training_log(
            self.tr("Exporting ONNX for auto-labeling...")
        )
        success, message = self.export_manager.start_export(
            self.current_project_path, "onnx", allow_install=True
        )
        if not success:
            self._pending_autolabel_after_export = False
            self.use_autolabel_button.setEnabled(True)
            QMessageBox.critical(self, self.tr("Export Error"), message)
            self.append_training_log(f"Failed to start export: {message}")

    def _confirm_export_dependencies(self, export_format):
        """Ask before pip touches the environment; True means "carry on".

        The worker used to install missing packages by itself, unprompted, with
        a 30s timeout that no real wheel download fits in — so the automatic
        path could only fail slowly. Consent is asked here, on the UI thread
        (a worker thread cannot show a modal dialog), and the prompt carries
        the exact command, which is the only route a packaged build has.
        """
        missing = get_export_validator(export_format)()
        if not missing:
            return True

        missing_text = ", ".join(missing)
        manual = f"pip install {missing_text}"
        reply = QMessageBox.question(
            self,
            self.tr("Missing Export Dependencies"),
            self.tr(
                "Exporting to %1 needs these packages:\n%2\n\n"
                "Install them now with pip?\n%3\n\n"
                "Choosing No cancels the export. Nothing is installed without asking."
            )
            .replace("%1", export_format)
            .replace("%2", missing_text)
            .replace("%3", manual),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.append_training_log(
                f"Installing export dependencies: {missing_text}"
            )
            return True
        self.append_training_log(
            f"Export cancelled; install manually: {manual}"
        )
        return False

    def _record_active_learning_round(self, parent):
        """Log one train -> relabel round for the marginal-gain dashboard."""
        try:
            from anylabeling.views.labeling.utils.active_learning import (
                read_last_map50,
            )
            from anylabeling.views.labeling.utils.smart_tools import (
                record_training_round,
            )

            map50 = None
            if self.current_project_path:
                map50 = read_last_map50(
                    os.path.join(self.current_project_path, "results.csv")
                )
            record_training_round(
                parent,
                self.current_project_path,
                model_name=os.path.basename(
                    os.path.normpath(self.current_project_path or "")
                ),
                map50=map50,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to record active learning round: {exc}")

    def _resolve_pose_classes(self):
        """``({class: [keypoint names]}, has_visible)`` from the pose config.

        The pose adapter reads ``classes`` as a mapping and derives
        ``kpt_shape`` from it when the exported ONNX carries no metadata, so
        the names must come from the same pose config training used.
        """
        path = ""
        widget = self.config_widgets.get("pose_config")
        if widget is not None:
            path = widget.text().strip().strip('"')
        if not path or not os.path.isfile(path):
            return None, True
        try:
            data = load_yaml_config(path)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to read pose config {path}: {exc}")
            return None, True
        classes = (data or {}).get("classes")
        if not isinstance(classes, dict) or not classes:
            return None, True
        mapping = {}
        for class_name, key_points in classes.items():
            if not isinstance(key_points, (list, tuple)) or not key_points:
                return None, True
            mapping[str(class_name)] = [str(name) for name in key_points]
        return mapping, bool((data or {}).get("has_visible", True))

    def _load_exported_weights_for_autolabel(self, onnx_path):
        has_visible = True
        if self.selected_task_type == "Pose":
            classes, has_visible = self._resolve_pose_classes()
            if not classes:
                QMessageBox.warning(
                    self,
                    self.tr("Missing pose config"),
                    self.tr(
                        "Pose feedback needs the same pose config used for training (classes: class name -> keypoint name list). Fill in Pose Config on the Data tab and retry."
                    ),
                )
                return
        else:
            classes = self._resolve_class_names()
        if not classes:
            QMessageBox.warning(
                self,
                self.tr("Missing classes"),
                self.tr(
                    "Could not read class names from the labels; check the data config and retry."
                ),
            )
            return
        model_type = autolabel_type_for_task(self.selected_task_type)
        if not model_type:
            return
        project_name = os.path.basename(
            os.path.normpath(self.current_project_path)
        )
        name = sanitize_custom_model_name(f"{project_name}_best")
        display_name = self.tr("Training weights · %1").replace(
            "%1", project_name
        )
        yaml_path = os.path.join(
            self.current_project_path, "weights", f"{name}.yaml"
        )
        write_autolabel_model_yaml(
            yaml_path,
            model_type=model_type,
            name=name,
            display_name=display_name,
            model_path=onnx_path,
            classes=classes,
            has_visible=has_visible,
            # A classifier ranks its top-k; a 0.25 floor would silently drop
            # every suggestion once the classes are many.
            conf_threshold=(
                0.0 if self.selected_task_type == "Classify" else 0.25
            ),
        )
        parent = self.parent()
        self.accept()
        widget = (
            getattr(parent, "auto_labeling_widget", None) if parent else None
        )
        if widget is None:
            return
        widget._last_model_selection = ("Custom", name, yaml_path)
        widget.show()
        self._sync_training_classes_to_label_dock(parent, classes)

        def _on_exported_model_loaded(model_config):
            try:
                widget.model_manager.model_loaded.disconnect(
                    _on_exported_model_loaded
                )
            except TypeError:
                pass
            if not model_config or not model_config.get("model"):
                return
            if parent is None:
                return
            from anylabeling.views.labeling.utils.active_learning import (
                load_history,
                suggest_next_step,
            )
            from anylabeling.views.labeling.utils.smart_tools import (
                label_dir_for,
            )

            label_dir = label_dir_for(parent)
            suggestion = suggest_next_step(load_history(label_dir))
            suggestion_text = self.tr(
                "Current iteration suggestion: %1"
            ).replace("%1", suggestion["reason"])
            reply = QMessageBox.question(
                parent,
                QCoreApplication.translate("LabelingWidget", "Feed Back Now"),
                QCoreApplication.translate(
                    "LabelingWidget",
                    "Training weights loaded. Re-run auto-labeling on unlabeled and pending-review images; the Iteration Gains Board updates automatically when done.\nConfirmed empty labels (negatives) are skipped.\n\n%1\n\nStart now?",
                ).replace("%1", suggestion_text),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                if hasattr(parent, "status"):
                    parent.status(
                        QCoreApplication.translate(
                            "LabelingWidget",
                            "Check the next-step suggestions in the Iteration Gains Board later.",
                        ),
                        4000,
                    )
                return
            from anylabeling.views.labeling.utils.active_learning import (
                count_annotations,
            )
            from anylabeling.views.labeling.utils.batch import run_all_images
            from anylabeling.views.labeling.utils.quality import (
                file_needs_re_autolabel,
            )
            from anylabeling.views.labeling.utils.smart_tools import (
                watch_relabel_result,
            )

            output_dir = getattr(parent, "output_dir", None)
            baseline = count_annotations(
                list(getattr(parent, "image_list", None) or []), label_dir
            )
            self._record_active_learning_round(parent)
            run_all_images(
                parent,
                prompt=False,
                from_start=True,
                skip_existing=False,
                skip_if=lambda image_file, directory=output_dir: (
                    not file_needs_re_autolabel(image_file, directory)
                ),
            )
            watch_relabel_result(parent, label_dir, baseline)

        widget.model_manager.model_loaded.connect(_on_exported_model_loaded)
        # Pin it: the iteration history now references this model, so the
        # custom-model cap must never evict it behind the user's back.
        widget.model_manager.load_custom_model(yaml_path, pin=True)

    def _sync_training_classes_to_label_dock(self, parent, classes):
        if parent is None or not classes:
            return
        from anylabeling.views.labeling.utils.yolo_detect import (
            merge_class_names,
        )

        dock_names = []
        unique_list = getattr(parent, "unique_label_list", None)
        if unique_list is not None:
            for row in range(unique_list.count()):
                item = unique_list.item(row)
                if item is None:
                    continue
                dock_names.append(item.data(Qt.ItemDataRole.UserRole))
        merged = merge_class_names(classes, dock_names)
        load_labels = getattr(parent, "load_labels", None)
        if callable(load_labels):
            load_labels(merged, clear_existing=True)
        config = getattr(parent, "_config", None)
        if isinstance(config, dict):
            config["labels"] = merged
            save_labeling_config(config)

    def reset_train_tab(self):
        self.training_status = "idle"
        self.current_project_path = None
        self.current_epochs = 0
        self._training_started_at = None
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0/0")
        self.update_training_status_display()
        if hasattr(self, "metrics_label"):
            self.metrics_label.setText("")

        if hasattr(self, "log_display"):
            self.log_display.clear()
        self._last_saved_log_text = None

        for i, image_label in enumerate(self.image_labels):
            image_label.clear()
            image_label.setText(self.tr("No image"))
            image_label.setToolTip("")
            self.image_paths[i] = None

        self.previous_button.setVisible(True)
        self.start_training_button.setVisible(True)
        self.export_button.setVisible(False)
        self.stop_training_button.setVisible(False)
        if hasattr(self, "resume_training_button"):
            self.resume_training_button.setVisible(False)
        if hasattr(self, "use_autolabel_button"):
            self.use_autolabel_button.setVisible(False)
            self.use_autolabel_button.setEnabled(True)
        self.refresh_wizard_state()
