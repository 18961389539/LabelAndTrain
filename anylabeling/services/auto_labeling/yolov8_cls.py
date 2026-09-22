import os

import cv2
import numpy as np
from datetime import datetime

from PyQt6.QtCore import QCoreApplication

from .engines import OnnxBaseModel
from .model import Model
from .types import AutoLabelingResult
from anylabeling.views.common.device_manager import get_preferred_device


def softmax(scores):
    exp = np.exp(scores - np.max(scores))
    return exp / exp.sum()


class YOLOv8Cls(Model):
    """Whole-image classifier.

    Unlike the detection adapters this one produces no shapes: a class
    suggestion is not an annotation until a human confirms it, and the label
    JSON has nowhere to carry a score or a model name inside ``flags``. The
    suggestion is therefore returned as ``result.predictions`` and stored under
    the file's own ``predictions`` key; confirming copies the chosen class into
    ``flags``, which is what the Classify training path reads.
    """

    class Meta:
        required_config_names = [
            "type",
            "name",
            "display_name",
            "model_path",
        ]
        widgets = ["button_run", "input_conf", "edit_conf"]
        output_modes = {}
        default_output_mode = "rectangle"

    def __init__(self, model_config, on_message) -> None:
        super().__init__(model_config, on_message)

        model_abs_path = self.get_model_abs_path(self.config, "model_path")
        if not model_abs_path or not os.path.isfile(model_abs_path):
            raise FileNotFoundError(
                QCoreApplication.translate(
                    "Model",
                    f"Could not initialize {self.config['type']} model.",
                )
            )

        self.net = OnnxBaseModel(model_abs_path, get_preferred_device())
        input_shape = self.net.get_input_shape() or []
        # Ultralytics exports a fixed 4D input; fall back to its default
        # classification size when the graph is dynamic.
        self.input_height = int(
            self.config.get("input_height")
            or (input_shape[2] if _is_int(input_shape, 2) else 224)
        )
        self.input_width = int(
            self.config.get("input_width")
            or (input_shape[3] if _is_int(input_shape, 3) else 224)
        )
        self.classes = list(self.config.get("classes", []) or [])
        self.topk = max(1, int(self.config.get("topk", 3)))
        self.conf_thres = float(self.config.get("conf_threshold", 0.0) or 0.0)
        # Ultralytics bakes its /255 into the exported graph. Keep it opt-in so
        # a model exported without the in-place scale can still be used.
        self.rescale = bool(self.config.get("rescale", False))

    def set_auto_labeling_conf(self, value):
        if value > 0:
            self.conf_thres = value

    def preprocess(self, image):
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(
            rgb,
            (self.input_width, self.input_height),
            interpolation=cv2.INTER_LINEAR,
        )
        blob = resized.astype(np.float32)
        if self.rescale:
            blob /= 255.0
        blob = np.transpose(blob, (2, 0, 1))[np.newaxis, ...]
        return np.ascontiguousarray(blob)

    def postprocess(self, output):
        scores = np.asarray(output, dtype=np.float32).reshape(-1)
        if scores.size == 0:
            return []
        probs = softmax(scores)
        order = np.argsort(probs)[::-1][: self.topk]
        predictions = []
        for index in order:
            score = float(probs[index])
            if score < self.conf_thres:
                continue
            name = self._class_name(int(index))
            if name is None:
                continue
            predictions.append(
                {
                    "label": name,
                    "score": round(score, 6),
                    "model": self.config.get("name"),
                    "created_at": datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                }
            )
        return predictions

    def _class_name(self, index):
        if self.classes:
            if 0 <= index < len(self.classes):
                return self.classes[index]
            return None
        # Without a class list the index is all there is; keeping it lets the
        # user see raw output rather than silently dropping the prediction.
        return str(index)

    def predict_shapes(self, image, image_path=None):
        if image is None:
            return AutoLabelingResult([], replace=False)
        blob = self.preprocess(image)
        output = self.net.get_ort_inference(blob)
        predictions = self.postprocess(output)
        return AutoLabelingResult(
            [],
            replace=False,
            image_path=image_path,
            predictions=predictions,
        )

    def unload(self):
        del self.net


def _is_int(shape, index):
    return len(shape) > index and isinstance(shape[index], int)
