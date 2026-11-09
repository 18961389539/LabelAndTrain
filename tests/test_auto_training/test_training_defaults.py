"""Shared training defaults: one source of truth, no drifting literals.

Covers the config.py defaults / CPU overrides, the lowered small-sample gate,
the install-timeout wiring, the shared export format and the auto-labeling
thresholds written into the custom-model YAML.
"""

import inspect
import os
import tempfile
from unittest import mock

import yaml

from jllabeling import net_defaults
from jllabeling.services.auto_labeling.thresholds import (
    DEFAULT_CONF_THRESHOLD,
    DEFAULT_IOU_THRESHOLD,
)
from jllabeling.services.auto_training.ultralytics import (
    config,
    exporter,
    validators,
)
from jllabeling.services.auto_training.ultralytics.exporter import (
    DEFAULT_EXPORT_FORMAT,
)
from jllabeling.services.auto_training.ultralytics.utils import (
    write_autolabel_model_yaml,
)


def test_gpu_defaults_keep_the_full_pace():
    cfg = config.get_default_training_config("cuda")
    assert cfg["epochs"] == 100
    assert cfg["batch"] == 16
    assert cfg["imgsz"] == 640
    assert cfg["workers"] == 8
    # 100 effectively disabled early stopping, which was wrong on GPU too.
    assert cfg["patience"] == 20


def test_none_and_cpu_apply_the_shared_overrides():
    for device in (None, "cpu", "CPU"):
        cfg = config.get_default_training_config(device)
        for key, value in config.CPU_TRAINING_OVERRIDES.items():
            assert cfg[key] == value, (device, key)
    # Windows spawns dataloader workers; 0 on CPU is deliberate.
    assert config.CPU_TRAINING_OVERRIDES["workers"] == 0


def test_default_config_is_a_fresh_deep_copy():
    first = config.get_default_training_config()
    first["epochs"] = 999
    assert config.DEFAULT_TRAINING_CONFIG["epochs"] == 100
    assert config.get_default_training_config("cuda")["epochs"] == 100


def test_min_labeled_threshold_allows_small_sample_trials():
    assert config.MIN_LABELED_IMAGES_THRESHOLD == 4
    with mock.patch.object(
        validators, "get_task_valid_images", return_value=4
    ):
        ok, msg = validators.validate_task_requirements("Detect", ["x"], None)
        assert ok is True
        assert msg == ""
    with mock.patch.object(
        validators, "get_task_valid_images", return_value=3
    ):
        ok, msg = validators.validate_task_requirements("Detect", ["x"], None)
        assert ok is False
        assert "4" in msg


def test_install_timeout_comes_from_net_defaults():
    assert validators.DEFAULT_INSTALL_TIMEOUT == net_defaults.install_timeout()


def test_autolabel_yaml_uses_shared_thresholds():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "model.yaml")
        write_autolabel_model_yaml(
            path,
            model_type="yolov8",
            name="n",
            display_name="d",
            model_path=os.path.join(tmp, "best.onnx"),
            classes=["cat"],
        )
        with open(path, "r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
    assert payload["conf_threshold"] == DEFAULT_CONF_THRESHOLD
    assert payload["iou_threshold"] == DEFAULT_IOU_THRESHOLD


def test_export_format_is_shared_between_service_and_view():
    from jllabeling.views.training import export_autolabel

    assert DEFAULT_EXPORT_FORMAT == "onnx"
    assert (
        inspect.signature(exporter.ExportManager.start_export)
        .parameters["export_format"]
        .default
        == DEFAULT_EXPORT_FORMAT
    )
    assert (
        inspect.signature(exporter.export_model)
        .parameters["export_format"]
        .default
        == DEFAULT_EXPORT_FORMAT
    )
    assert export_autolabel.DEFAULT_EXPORT_FORMAT == DEFAULT_EXPORT_FORMAT
