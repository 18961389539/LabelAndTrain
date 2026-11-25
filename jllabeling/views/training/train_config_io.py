"""Read and write the Train tab config through the widget map.

The Train tab is a two-way bridge: ``read_config_from_widgets`` walks
``config_widgets`` into the nested dict the trainer consumes, and
``write_config_into_widgets`` pushes a saved dict back into the same
widgets. Both used to be methods on ``UltralyticsDialog``, but they only
touch the widget map plus two collaborators (the ratio caption and the
device-changed hook), so they live here and are testable without
constructing the dialog.
"""

from jllabeling.views.labeling.logger import logger
from jllabeling.services.auto_training.ultralytics.general import (
    format_classes_display,
    parse_string_to_digit_list,
)


def write_config_into_widgets(config, widgets, ratio_label, on_device_changed):
    """Push a saved config dict back into the Train tab widgets."""

    def set_widget_value(key, value):
        if key not in widgets:
            return

        widget = widgets[key]
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
                        widgets[key].setValue(int(value * 100))
                        ratio_label.setText(str(value))
                    else:
                        widgets[key].setValue(int(value))
                        ratio_label.setText(str(value / 100.0))
                elif key == "device":
                    index = widgets[key].findText(str(value))
                    if index >= 0:
                        widgets[key].setCurrentIndex(index)
                        on_device_changed(str(value))
                elif key == "optimizer":
                    index = widgets[key].findText(str(value))
                    if index >= 0:
                        widgets[key].setCurrentIndex(index)
                elif key == "pose_config":
                    if value:
                        widgets[key].setText(value)
                elif key in (
                    "skip_empty_files",
                    "only_checked_files",
                ):
                    set_widget_value(key, value)
                else:
                    set_widget_value(key, value)

    for key, value in config.items():
        if key not in sections_to_process and key in widgets:
            set_widget_value(key, value)


def read_config_from_widgets(widgets):
    """Collect every Train tab widget into the nested config dict."""

    def get_widget_value(key):
        if key not in widgets:
            return None
        widget = widgets[key]
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
            # ``or ""``: a dialog built without these two fields (a test
            # double, or a future tab that drops them) used to raise on the
            # None before Ultralytics ever saw the config.  An empty string
            # still fails later, but with the trainer's own message.
            "model": (get_widget_value("model") or "").strip('"'),
            "data": (get_widget_value("data") or "").strip('"'),
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
            "classes": parse_string_to_digit_list(get_widget_value("classes")),
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
