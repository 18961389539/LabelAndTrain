import os
import copy
import re
import time
import yaml
import importlib.resources as pkg_resources
from threading import Lock, Event

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

import anylabeling.configs as auto_labeling_configs
from anylabeling.services.auto_labeling.worker import GenericWorker
from anylabeling.views.labeling.logger import logger
from anylabeling.config import get_config, save_config
from anylabeling.services.auto_labeling.types import (
    AutoLabelingResult,
    DownloadCancelledError,
)
from anylabeling.services.auto_labeling.utils import TimeoutContext
from anylabeling.services.auto_labeling import (
    _CUSTOM_MODELS,
    _CACHED_AUTO_LABELING_MODELS,
    _AUTO_LABELING_MARKS_MODELS,
    _AUTO_LABELING_CONF_MODELS,
    _AUTO_LABELING_IOU_MODELS,
    _AUTO_LABELING_MASK_FINENESS_MODELS,
    _AUTO_LABELING_CROPPING_MODE_MODELS,
    _AUTO_LABELING_PRESERVE_EXISTING_ANNOTATIONS_STATE_MODELS,
    _ON_NEXT_FILES_CHANGED_MODELS,
)


class ModelManager(QObject):
    """Model manager"""

    MAX_NUM_CUSTOM_MODELS = 5
    CUSTOM_MODEL_NAME_PATTERN = re.compile(r"[A-Za-z0-9._-]+")
    model_configs_changed = pyqtSignal(list)
    new_model_status = pyqtSignal(str)
    model_loaded = pyqtSignal(dict)
    new_auto_labeling_result = pyqtSignal(AutoLabelingResult)
    auto_segmentation_model_selected = pyqtSignal()
    auto_segmentation_model_unselected = pyqtSignal()
    prediction_started = pyqtSignal()
    prediction_finished = pyqtSignal()
    request_next_files_requested = pyqtSignal()
    output_modes_changed = pyqtSignal(dict, str)
    download_progress = pyqtSignal(int, int)
    download_finished = pyqtSignal()
    # Separate channel for download *phases* ("Verifying...", "Connecting
    # to <host>...", "Downloading: 42%"). Unlike ``new_model_status``, the
    # view must keep showing these even after byte progress starts, so they
    # are not subject to the ``_downloading`` freeze applied to the status
    # label.
    download_stage = pyqtSignal(str)
    # Dedicated failure channel.  Model load/download errors must reach the
    # user even while the UI freezes the status label during byte progress
    # (``_downloading``), otherwise a failed load looks like a silent reset.
    model_load_failed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.model_configs = []

        self.loaded_model_config = None
        self.loaded_model_config_lock = Lock()

        self.model_download_worker = None
        self.model_download_thread = None
        self.model_execution_thread = None
        self.model_execution_thread_lock = Lock()
        self.model_execution_worker = None
        self._cancel_event = Event()
        # Interactive prediction cancellation: set when the user asks to stop
        # a running inference.  Cooperating models (e.g. SAM2 AMG) poll it to
        # abort long loops; the manager also discards any result produced
        # after a cancel so a stale prediction never lands on the canvas.
        self._cancel_prediction_event = Event()

        self.load_model_configs()

    def load_model_configs(self):
        """Load model configs"""
        # Load list of default models
        with pkg_resources.open_text(
            auto_labeling_configs, "models.yaml"
        ) as f:
            model_list = yaml.safe_load(f)

        # Load list of custom models
        custom_models = get_config().get("custom_models", [])
        for custom_model in custom_models:
            custom_model["is_custom_model"] = True

        # Remove invalid/not found custom models
        custom_models = [
            custom_model
            for custom_model in custom_models
            if os.path.isfile(custom_model.get("config_file", ""))
        ]
        config = get_config()
        config["custom_models"] = custom_models
        save_config(config)

        model_list += custom_models

        # Load model configs
        model_configs = []
        for model in model_list:
            model_config = {}
            config_file = model["config_file"]
            if config_file.startswith(":/"):  # Config file is in resources
                config_file_name = config_file[2:]
                resource_path = pkg_resources.files(
                    auto_labeling_configs
                ).joinpath("auto_labeling", config_file_name)
                config_content = resource_path.read_text(encoding="utf-8")
                model_config = yaml.safe_load(config_content)
                model_config["config_file"] = str(config_file)
            else:  # Config file is in local file system
                with open(config_file, "r", encoding="utf-8") as f:
                    model_config = yaml.safe_load(f)
                    model_config["config_file"] = os.path.normpath(
                        os.path.abspath(config_file)
                    )
            is_custom = model.get("is_custom_model", False)
            model_config["is_custom_model"] = is_custom
            if is_custom and not self.is_valid_custom_model_name(
                model_config.get("name")
            ):
                logger.error(
                    "Skipping custom model with an invalid 'name' field."
                )
                continue
            if is_custom and not model_config["name"].startswith("_custom_"):
                model_config["name"] = f"_custom_{model_config['name']}"

            model_configs.append(model_config)

        # Sort by last used
        for i, model_config in enumerate(model_configs):
            # Keep order for integrated models
            if not model_config.get("is_custom_model", False):
                model_config["last_used"] = -i
            else:
                model_config["last_used"] = model_config.get(
                    "last_used", time.time()
                )
        model_configs.sort(key=lambda x: x.get("last_used", 0), reverse=True)

        self.model_configs = model_configs
        self.model_configs_changed.emit(model_configs)

    @classmethod
    def is_valid_custom_model_name(cls, name):
        return (
            isinstance(name, str)
            and name not in (".", "..")
            and cls.CUSTOM_MODEL_NAME_PATTERN.fullmatch(name) is not None
        )

    def update_model_config(self, config_file, key, value):
        """Update a specific key in a model's configuration."""
        for config in self.model_configs:
            if config.get("config_file") == config_file:
                config[key] = value
                if (
                    self.loaded_model_config
                    and self.loaded_model_config.get("config_file")
                    == config_file
                ):
                    self.loaded_model_config[key] = value
                break

        if config_file and config_file.startswith(":/"):
            user_config = get_config()
            save_config(user_config)

    def get_model_configs(self):
        """Return model infos"""
        return self.model_configs

    def set_output_mode(self, mode):
        """Set output mode"""
        if self.loaded_model_config and self.loaded_model_config["model"]:
            self.loaded_model_config["model"].set_output_mode(mode)

    def cancel_download(self):
        """Cancel the current model download."""
        self._cancel_event.set()

    def cancel_prediction(self):
        """Request cancellation of the currently running inference.

        UI calls this from the cancel button; models that poll
        ``is_prediction_cancelled`` abort their loops promptly and the
        manager drops any result emitted after this point.
        """
        self._cancel_prediction_event.set()

    def is_prediction_cancelled(self):
        """Whether the current interactive inference was cancelled."""
        return self._cancel_prediction_event.is_set()

    def reset_prediction_cancel(self):
        """Clear the cancellation flag before starting a new inference."""
        self._cancel_prediction_event.clear()

    @pyqtSlot()
    def on_model_download_finished(self):
        """Handle model download thread finished"""
        logger.info("on_model_download_finished entered")
        self.download_finished.emit()
        if self._cancel_event.is_set():
            self._cancel_event.clear()
            self.new_model_status.emit(self.tr("Download cancelled."))
            self.model_loaded.emit({})
            return
        if self.loaded_model_config and self.loaded_model_config["model"]:
            logger.info(
                "Model object present; emitting model_loaded "
                f"({self.loaded_model_config.get('type')})"
            )
            self.new_model_status.emit(
                self.tr("Model loaded. Ready for labeling.")
            )
            self.model_loaded.emit(self.loaded_model_config)
            logger.info("output_modes_changed emitting")
            self.output_modes_changed.emit(
                self.loaded_model_config["model"].Meta.output_modes,
                self.loaded_model_config["model"].Meta.default_output_mode,
            )
            logger.info("on_model_download_finished completed OK")
        else:
            self.model_loaded.emit({})
            logger.warning(
                "on_model_download_finished: no loaded model object"
            )

    def remove_custom_model(self, config_file):
        """Remove a previously registered custom model.

        Deletes the entry from the persisted ``custom_models`` config and
        reloads the registry.  The model weights/config file on disk are
        intentionally left untouched so nothing is lost irreversibly.

        Returns:
            True when an entry was actually removed.
        """
        config_file = os.path.normpath(os.path.abspath(config_file))
        config = get_config()
        custom_models = config.get("custom_models", [])
        kept = []
        removed = False
        for model in custom_models:
            if os.path.normpath(
                os.path.abspath(model.get("config_file", ""))
            ) == config_file:
                removed = True
                continue
            kept.append(model)
        if removed:
            config["custom_models"] = kept
            save_config(config)
            self.load_model_configs()
            logger.info(f"Removed custom model config: {config_file}")
        return removed

    def load_custom_model(self, config_file):
        """Run custom model loading in a thread"""
        config_file = os.path.normpath(os.path.abspath(config_file))
        if (
            self.model_download_thread is not None
            and self.is_model_download_running()
        ):
            logger.info(
                "Another model is being loaded. Please wait for it to finish."
            )
            return False

        # Check config file path
        if not config_file or not os.path.isfile(config_file):
            logger.error(
                "An error occurred while loading the custom model: "
                "The model path is invalid."
            )
            self.new_model_status.emit(
                self.tr("Error in loading custom model: Invalid path.")
            )
            return False

        # Check config file content
        model_config = {}
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                model_config = yaml.safe_load(f)
                model_config["config_file"] = os.path.abspath(config_file)
        except Exception as e:
            logger.error(
                "An error occurred while loading the custom model: "
                "The config file is invalid."
            )
            self.new_model_status.emit(
                self.tr("Error in loading custom model: Invalid config file.")
            )
            return False

        if (
            "type" not in model_config
            or "display_name" not in model_config
            or "name" not in model_config
            or model_config["type"] not in _CUSTOM_MODELS
        ):
            if "type" not in model_config:
                logger.error(
                    "An error occurred while loading the custom model: "
                    "The 'type' field is missing in the model configuration file."
                )
            elif "display_name" not in model_config:
                logger.error(
                    "An error occurred while loading the custom model: "
                    "The 'display_name' field is missing in the model configuration file."
                )
            elif "name" not in model_config:
                logger.error(
                    "An error occurred while loading the custom model: "
                    "The 'name' field is missing in the model configuration file."
                )
            else:
                logger.error(
                    "An error occurred while loading the custom model: "
                    "The model type {model_config['type']} is not supported."
                )
            self.new_model_status.emit(
                self.tr(
                    "Error in loading custom model: Invalid config file format."
                )
            )
            self.model_loaded.emit({})
            return False

        if not self.is_valid_custom_model_name(model_config["name"]):
            logger.error(
                "An error occurred while loading the custom model: "
                "The 'name' field must be a single path segment containing "
                "only letters, numbers, dots, underscores, and hyphens."
            )
            self.new_model_status.emit(
                self.tr("Error in loading custom model: Invalid model name.")
            )
            self.model_loaded.emit({})
            return False

        # Add or replace custom model
        custom_models = get_config().get("custom_models", [])
        matched_index = None
        for i, model in enumerate(custom_models):
            if os.path.normpath(model["config_file"]) == os.path.normpath(
                config_file
            ):
                matched_index = i
                break
        if matched_index is not None:
            model_config["last_used"] = time.time()
            custom_models[matched_index] = model_config
        else:
            if len(custom_models) >= self.MAX_NUM_CUSTOM_MODELS:
                custom_models.sort(
                    key=lambda x: x.get("last_used", 0), reverse=True
                )
                evicted = custom_models.pop()
                evicted_name = evicted.get("display_name", evicted.get("name", ""))
                logger.warning(
                    f"Custom model limit reached "
                    f"({self.MAX_NUM_CUSTOM_MODELS}); evicting "
                    f"{evicted_name}"
                )
                self.new_model_status.emit(
                    self.tr(
                        "Custom model limit reached (%d). "
                        "Removed the least recently used model: %s. "
                        "Use the trash icon in the model list to manage "
                        "custom models."
                    )
                    % (self.MAX_NUM_CUSTOM_MODELS, evicted_name)
                )
            custom_models = [model_config] + custom_models

        # Save config
        config = get_config()
        config["custom_models"] = custom_models
        save_config(config)

        # Reload model configs
        self.load_model_configs()

        # Load model
        self.load_model(model_config["config_file"])

        return True

    def load_model(self, config_file):
        """Run model loading in a thread"""
        if self.is_model_download_running():
            logger.info(
                "Another model is being loaded. Please wait for it to finish."
            )
            return
        if not config_file:
            if self.model_download_worker is not None:
                try:
                    self.model_download_worker.finished.disconnect(
                        self.on_model_download_finished
                    )
                except TypeError:
                    pass
            self.unload_model()
            self.new_model_status.emit(self.tr("No model selected."))
            return

        # Check and get model id
        model_id = None
        for i, model_config in enumerate(self.model_configs):
            if model_config["config_file"] == config_file:
                model_id = i
                break
        if model_id is None:
            logger.error(
                "An error occurred while loading the model: "
                "The model name is invalid."
            )
            self.new_model_status.emit(
                self.tr("Error in loading model: Invalid model name.")
            )
            return

        self._cancel_event.clear()
        self.model_download_thread = QThread()
        template = "Loading model: {model_name}. Please wait..."
        translated_template = self.tr(template)
        message = translated_template.format(
            model_name=self.model_configs[model_id]["display_name"]
        )
        self.new_model_status.emit(message)

        self.model_download_worker = GenericWorker(self._load_model, model_id)
        self.model_download_worker.finished.connect(
            self.on_model_download_finished
        )
        self.model_download_worker.finished.connect(
            self.model_download_thread.quit
        )
        self.model_download_thread.finished.connect(
            self.on_model_download_thread_finished
        )
        self.model_download_thread.finished.connect(
            self.model_download_thread.deleteLater
        )
        self.model_download_worker.moveToThread(self.model_download_thread)
        self.model_download_thread.started.connect(
            self.model_download_worker.run
        )
        self.model_download_thread.start()

    def is_model_download_running(self):
        """Return whether the model download thread is still running."""
        try:
            return (
                self.model_download_thread is not None
                and self.model_download_thread.isRunning()
            )
        except RuntimeError:
            self.model_download_thread = None
            self.model_download_worker = None
            return False

    @pyqtSlot()
    def on_model_download_thread_finished(self):
        """Clear finished model download thread references."""
        self.model_download_thread = None
        self.model_download_worker = None

    def _load_model(self, model_id):  # noqa: C901
        """Load and return model info"""
        with self.loaded_model_config_lock:
            old_config = self.loaded_model_config
            if old_config is not None:
                self.loaded_model_config = None
        if old_config is not None:
            old_config["model"].unload()
            self.auto_segmentation_model_unselected.emit()

        model_config = copy.deepcopy(self.model_configs[model_id])
        model_config["_cancel_event"] = self._cancel_event
        model_config["_cancel_prediction_event"] = self._cancel_prediction_event
        model_config["_on_progress"] = (
            lambda downloaded, total: self.download_progress.emit(
                downloaded, total
            )
        )
        model_config["_on_stage"] = self.download_stage.emit
        if model_config["type"] == "yolov8":
            from .yolov8 import YOLOv8

            try:
                model_config["model"] = YOLOv8(
                    model_config, on_message=self.new_model_status.emit
                )
                with self.loaded_model_config_lock:
                    self.loaded_model_config = model_config
                self.auto_segmentation_model_unselected.emit()
                logger.info(
                    f"✅ Model loaded successfully: {model_config['type']}"
                )
            except Exception as e:  # noqa
                template = "Error in loading model: {error_message}"
                translated_template = self.tr(template)
                error_text = translated_template.format(error_message=str(e))
                self.new_model_status.emit(error_text)
                self.model_load_failed.emit(error_text)
                logger.error(
                    f"❌ Error in loading model: {model_config['type']} with error: {str(e)}"
                )
                return
        elif model_config["type"] == "yolov8_seg":
            from .yolov8_seg import YOLOv8_Seg

            try:
                model_config["model"] = YOLOv8_Seg(
                    model_config, on_message=self.new_model_status.emit
                )
                with self.loaded_model_config_lock:
                    self.loaded_model_config = model_config
                self.auto_segmentation_model_unselected.emit()
                logger.info(
                    f"✅ Model loaded successfully: {model_config['type']}"
                )
            except Exception as e:  # noqa
                template = "Error in loading model: {error_message}"
                translated_template = self.tr(template)
                error_text = translated_template.format(error_message=str(e))
                self.new_model_status.emit(error_text)
                self.model_load_failed.emit(error_text)
                logger.error(
                    f"❌ Error in loading model: {model_config['type']} with error: {str(e)}"
                )
                return
        elif model_config["type"] == "yolov8_sam2":
            from .yolov8_sam2 import YOLOv8SegmentAnything2

            try:
                model_config["model"] = YOLOv8SegmentAnything2(
                    model_config, on_message=self.new_model_status.emit
                )
                with self.loaded_model_config_lock:
                    self.loaded_model_config = model_config
                self.auto_segmentation_model_selected.emit()
                logger.info(
                    f"✅ Model loaded successfully: {model_config['type']}"
                )
            except Exception as e:  # noqa
                logger.error(
                    f"❌ Error in loading model: {model_config['type']} with error: {str(e)}"
                )
                template = "Error in loading model: {error_message}"
                translated_template = self.tr(template)
                error_text = translated_template.format(error_message=str(e))
                self.new_model_status.emit(error_text)
                self.model_load_failed.emit(error_text)
                return
            # Request next files for prediction
            self.request_next_files_requested.emit()
        elif model_config["type"] == "segment_anything_2":
            from .segment_anything_2 import SegmentAnything2

            try:
                logger.info(
                    "Loading SegmentAnything2 engine "
                    f"({model_config['name']})..."
                )
                model_config["model"] = SegmentAnything2(
                    model_config, on_message=self.new_model_status.emit
                )
                with self.loaded_model_config_lock:
                    self.loaded_model_config = model_config
                logger.info(
                    "SegmentAnything2 engine initialized successfully"
                )
                self.auto_segmentation_model_selected.emit()
                logger.info("auto_segmentation_model_selected emitted")
                logger.info(
                    f"✅ Model loaded successfully: {model_config['type']}"
                )
            except Exception as e:  # noqa
                logger.exception(
                    f"❌ Error in loading model: {model_config['type']} "
                    f"with error: {str(e)}"
                )
                template = "Error in loading model: {error_message}"
                translated_template = self.tr(template)
                error_text = translated_template.format(error_message=str(e))
                self.new_model_status.emit(error_text)
                self.model_load_failed.emit(error_text)
                return
            # Request next files for prediction
            self.request_next_files_requested.emit()
            logger.info("request_next_files_requested emitted (SAM2)")
        elif model_config["type"] == "yolo26":
            from .yolo26 import YOLO26

            try:
                model_config["model"] = YOLO26(
                    model_config, on_message=self.new_model_status.emit
                )
                with self.loaded_model_config_lock:
                    self.loaded_model_config = model_config
                self.auto_segmentation_model_unselected.emit()
                logger.info(
                    f"✅ Model loaded successfully: {model_config['type']}"
                )
            except Exception as e:  # noqa
                template = "Error in loading model: {error_message}"
                translated_template = self.tr(template)
                error_text = translated_template.format(error_message=str(e))
                self.new_model_status.emit(error_text)
                self.model_load_failed.emit(error_text)
                logger.error(
                    f"❌ Error in loading model: {model_config['type']} with error: {str(e)}"
                )
                return
        elif model_config["type"] == "yolo26_seg":
            from .yolo26_seg import YOLO26_Seg

            try:
                model_config["model"] = YOLO26_Seg(
                    model_config, on_message=self.new_model_status.emit
                )
                with self.loaded_model_config_lock:
                    self.loaded_model_config = model_config
                self.auto_segmentation_model_unselected.emit()
                logger.info(
                    f"✅ Model loaded successfully: {model_config['type']}"
                )
            except Exception as e:  # noqa
                template = "Error in loading model: {error_message}"
                translated_template = self.tr(template)
                error_text = translated_template.format(error_message=str(e))
                self.new_model_status.emit(error_text)
                self.model_load_failed.emit(error_text)
                logger.error(
                    f"❌ Error in loading model: {model_config['type']} with error: {str(e)}"
                )
                return
        elif model_config["type"] == "yolo26_pose":
            from .yolo26_pose import YOLO26_Pose

            try:
                model_config["model"] = YOLO26_Pose(
                    model_config, on_message=self.new_model_status.emit
                )
                with self.loaded_model_config_lock:
                    self.loaded_model_config = model_config
                self.auto_segmentation_model_unselected.emit()
                logger.info(
                    f"✅ Model loaded successfully: {model_config['type']}"
                )
            except Exception as e:  # noqa
                template = "Error in loading model: {error_message}"
                translated_template = self.tr(template)
                error_text = translated_template.format(error_message=str(e))
                self.new_model_status.emit(error_text)
                self.model_load_failed.emit(error_text)
                logger.error(
                    f"❌ Error in loading model: {model_config['type']} with error: {str(e)}"
                )
                return
    def set_cache_auto_label(self, text, gid):
        """Set cache auto label"""
        if (
            self.loaded_model_config is not None
            and self.loaded_model_config["type"]
            in _CACHED_AUTO_LABELING_MODELS
        ):
            self.loaded_model_config["model"].set_cache_auto_label(text, gid)

    def set_auto_labeling_marks(self, marks):
        """Set auto labeling marks
        (For example, for segment_anything model, it is the marks for)
        """
        if (
            self.loaded_model_config is None
            or self.loaded_model_config["type"]
            not in _AUTO_LABELING_MARKS_MODELS
        ):
            return
        self.loaded_model_config["model"].set_auto_labeling_marks(marks)

    def set_auto_labeling_conf(self, value):
        """Set auto labeling confidences"""
        if (
            self.loaded_model_config is None
            or self.loaded_model_config["type"]
            not in _AUTO_LABELING_CONF_MODELS
        ):
            return
        self.loaded_model_config["model"].set_auto_labeling_conf(value)

    def set_auto_labeling_iou(self, value):
        """Set auto labeling iou"""
        if (
            self.loaded_model_config is None
            or self.loaded_model_config["type"]
            not in _AUTO_LABELING_IOU_MODELS
        ):
            return
        self.loaded_model_config["model"].set_auto_labeling_iou(value)

    def set_auto_labeling_preserve_existing_annotations_state(self, state):
        if (
            self.loaded_model_config is not None
            and self.loaded_model_config["type"]
            in _AUTO_LABELING_PRESERVE_EXISTING_ANNOTATIONS_STATE_MODELS
        ):
            self.loaded_model_config[
                "model"
            ].set_auto_labeling_preserve_existing_annotations_state(state)

    def set_auto_labeling_filter_classes(self, class_names):
        """Set the active class filter by name on the loaded model."""
        if self.loaded_model_config is None:
            return
        model = self.loaded_model_config.get("model")
        if model and hasattr(model, "set_auto_labeling_filter_classes"):
            model.set_auto_labeling_filter_classes(class_names)

    def unload_model(self):
        """Unload model"""
        if self.loaded_model_config is not None:
            self.loaded_model_config["model"].unload()
            self.loaded_model_config = None

    def predict_shapes(
        self,
        image,
        filename=None,
        text_prompt=None,
        batch=False,
        existing_shapes=None,
    ):
        """Predict shapes.
        NOTE: This function is blocking. The model can take a long time to
        predict. So it is recommended to use predict_shapes_threading instead.
        """
        with self.loaded_model_config_lock:
            model_config = self.loaded_model_config
        if model_config is None:
            self.new_model_status.emit(
                self.tr("Model is not loaded. Choose a mode to continue.")
            )
            self.prediction_finished.emit()
            return

        try:
            if text_prompt is not None:
                auto_labeling_result = model_config["model"].predict_shapes(
                    image, filename, text_prompt=text_prompt
                )
            elif existing_shapes is not None:
                auto_labeling_result = model_config["model"].predict_shapes(
                    image, filename, existing_shapes=existing_shapes
                )
            else:
                auto_labeling_result = model_config["model"].predict_shapes(
                    image, filename
                )

            if isinstance(auto_labeling_result, AutoLabelingResult):
                auto_labeling_result.image_path = filename

            # A stale prediction must never land on the canvas after the
            # user asked to cancel (e.g. AMG takes minutes on big images).
            if not batch and self.is_prediction_cancelled():
                self.new_model_status.emit(
                    self.tr("Inference cancelled. Result discarded.")
                )
                self.prediction_finished.emit()
                return

            if batch:
                return auto_labeling_result
            else:
                self.new_auto_labeling_result.emit(auto_labeling_result)
                self.new_model_status.emit(
                    self.tr("Finished inferencing AI model. Check the result.")
                )

        except Exception as e:  # noqa
            logger.error(f"Error in predict_shapes: {e}")
            template = "Error in model prediction: {error_message}"
            translated_template = self.tr(template)
            error_text = translated_template.format(error_message=str(e))
            self.new_model_status.emit(error_text)

        self.prediction_finished.emit()

    @pyqtSlot()
    def predict_shapes_threading(
        self,
        image,
        filename=None,
        text_prompt=None,
        existing_shapes=None,
    ):
        """Predict shapes.
        This function starts a thread to run the prediction.
        """
        with self.loaded_model_config_lock:
            _config_snapshot = self.loaded_model_config
        if _config_snapshot is None:
            self.new_model_status.emit(
                self.tr("Model is not loaded. Choose a mode to continue.")
            )
            return
        self.new_model_status.emit(
            self.tr("Inferencing AI model. Please wait...")
        )
        self.reset_prediction_cancel()
        self.prediction_started.emit()

        with self.model_execution_thread_lock:
            try:
                execution_running = (
                    self.model_execution_thread is not None
                    and self.model_execution_thread.isRunning()
                )
            except RuntimeError:
                self.model_execution_thread = None
                self.model_execution_worker = None
                execution_running = False

            if execution_running:
                self.new_model_status.emit(
                    self.tr(
                        "Another model is being executed."
                        " Please wait for it to finish."
                    )
                )
                self.prediction_finished.emit()
                return

            self.model_execution_thread = QThread()
            if text_prompt is not None:
                self.model_execution_worker = GenericWorker(
                    self.predict_shapes,
                    image,
                    filename,
                    text_prompt=text_prompt,
                )
            elif existing_shapes is not None:
                self.model_execution_worker = GenericWorker(
                    self.predict_shapes,
                    image,
                    filename,
                    existing_shapes=existing_shapes,
                )
            else:
                self.model_execution_worker = GenericWorker(
                    self.predict_shapes, image, filename
                )
            self.model_execution_worker.finished.connect(
                self.model_execution_thread.quit
            )
            self.model_execution_thread.finished.connect(
                self.on_model_execution_finished
            )
            self.model_execution_thread.finished.connect(
                self.model_execution_thread.deleteLater
            )
            self.model_execution_worker.moveToThread(
                self.model_execution_thread
            )
            self.model_execution_thread.started.connect(
                self.model_execution_worker.run
            )
            self.model_execution_thread.start()

    @pyqtSlot()
    def on_model_execution_finished(self):
        """Clear finished model execution thread references."""
        with self.model_execution_thread_lock:
            self.model_execution_thread = None
            self.model_execution_worker = None

    def on_next_files_changed(self, next_files):
        """Run prediction on next files in advance to save inference time later"""
        if self.loaded_model_config is None:
            return

        # Currently only segment_anything-like model supports this feature
        if (
            self.loaded_model_config["type"]
            not in _ON_NEXT_FILES_CHANGED_MODELS
        ):
            return

        self.loaded_model_config["model"].on_next_files_changed(next_files)

    # Specific model setters
    def set_task(self, task_id):
        """Set task ID for the current model"""
        if self.loaded_model_config is None:
            return

    def set_mask_fineness(self, epsilon):
        """Set mask fineness (epsilon value for Douglas-Peucker algorithm)"""
        if (
            self.loaded_model_config is None
            or self.loaded_model_config["type"]
            not in _AUTO_LABELING_MASK_FINENESS_MODELS
        ):
            return
        self.loaded_model_config["model"].set_mask_fineness(epsilon)

    def set_cropping_mode(self, enabled: bool):
        """Set cropping mode for small object detection"""
        if (
            self.loaded_model_config is None
            or self.loaded_model_config["type"]
            not in _AUTO_LABELING_CROPPING_MODE_MODELS
        ):
            return
        self.loaded_model_config["model"].set_cropping_mode(enabled)
