"""Custom-model registrations come from a user-editable rc; bad ones must
not take the auto-labeling panel down with them.

``custom_models`` can be ``null``, a mapping or a list of strings after a
hand edit, and a registered config file can be emptied by another tool.
Each of those used to raise inside ``ModelManager.__init__``. A skipped
entry is kept in the rc -- the file may only be transiently unreadable --
but never reaches the model list.
"""

import copy

import pytest
import yaml
from PyQt6 import QtWidgets

from anylabeling import config
from anylabeling.services.auto_labeling.model_manager import ModelManager


@pytest.fixture()
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    yield app


def _write_config(tmp_path, monkeypatch, custom_models):
    rc = tmp_path / ".xanylabelingrc"
    payload = copy.deepcopy(config._load_template_config())
    payload["custom_models"] = custom_models
    rc.write_text(
        yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8"
    )
    monkeypatch.setattr(config, "current_config_file", str(rc))
    return rc


def _write_model_config(path, payload):
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8"
    )
    return str(path)


def _builtin_names(manager):
    return {
        item["name"]
        for item in manager.model_configs
        if not item.get("is_custom_model")
    }


@pytest.mark.usefixtures("qapp")
class TestCustomModelRegistry:
    @pytest.mark.parametrize(
        "custom_models",
        [None, {"a": "b"}, ["oops"], [None, 5]],
    )
    def test_structurally_broken_custom_models_do_not_crash(
        self, tmp_path, monkeypatch, custom_models
    ):
        _write_config(tmp_path, monkeypatch, custom_models)

        manager = ModelManager()

        assert manager.model_configs
        assert config.get_config()["custom_models"] == []

    @pytest.mark.parametrize("content", ["", "- a\n- b\n"])
    def test_an_unreadable_registered_config_is_skipped_but_kept(
        self, tmp_path, monkeypatch, content
    ):
        bad = tmp_path / "bad.yaml"
        bad.write_text(content, encoding="utf-8")
        _write_config(
            tmp_path,
            monkeypatch,
            [{"config_file": str(bad), "name": "bad"}],
        )

        manager = ModelManager()

        assert "bad" not in {item["name"] for item in manager.model_configs}
        saved = config.get_config()["custom_models"]
        assert [
            (entry.get("config_file"), entry.get("name")) for entry in saved
        ] == [(str(bad), "bad")]

    def test_unsupported_type_and_display_name_are_skipped(
        self, tmp_path, monkeypatch
    ):
        bad_type = _write_model_config(
            tmp_path / "bad_type.yaml",
            {
                "type": "bogus",
                "display_name": "X",
                "name": "badtype",
                "model_path": "w.onnx",
            },
        )
        bad_display = _write_model_config(
            tmp_path / "bad_display.yaml",
            {
                "type": "yolov8",
                "display_name": 5,
                "name": "baddisplay",
                "model_path": "w.onnx",
            },
        )
        _write_config(
            tmp_path,
            monkeypatch,
            [
                {"config_file": bad_type, "name": "badtype"},
                {"config_file": bad_display, "name": "baddisplay"},
            ],
        )

        manager = ModelManager()

        names = {item["name"] for item in manager.model_configs}
        assert "_custom_badtype" not in names
        assert "_custom_baddisplay" not in names

    def test_a_valid_custom_model_is_registered(self, tmp_path, monkeypatch):
        good = _write_model_config(
            tmp_path / "good.yaml",
            {
                "type": "yolov8",
                "display_name": "My model",
                "name": "mine",
                "model_path": "w.onnx",
            },
        )
        _write_config(
            tmp_path,
            monkeypatch,
            [{"config_file": good, "name": "mine"}],
        )

        manager = ModelManager()

        custom = [
            item
            for item in manager.model_configs
            if item.get("is_custom_model")
        ]
        assert [item["name"] for item in custom] == ["_custom_mine"]
        assert custom[0]["display_name"] == "My model"

    def test_load_custom_model_rejects_non_mapping_yaml(
        self, tmp_path, monkeypatch
    ):
        _write_config(tmp_path, monkeypatch, [])
        manager = ModelManager()
        before = _builtin_names(manager)
        scalar = tmp_path / "scalar.yaml"
        scalar.write_text("just a scalar\n", encoding="utf-8")
        messages = []
        manager.new_model_status.connect(messages.append)

        assert manager.load_custom_model(str(scalar)) is False

        assert messages == [
            "Error in loading custom model: Invalid config file."
        ]
        assert _builtin_names(manager) == before
        assert config.get_config()["custom_models"] == []
