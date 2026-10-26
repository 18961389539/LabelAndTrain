"""The dataset YAML ultralytics reads must never be half-written."""

import json
from unittest import mock

import pytest
import yaml

from anylabeling.services.auto_training.ultralytics import _io


def test_save_json_atomic_writes_and_leaves_no_temp(tmp_path):
    target = tmp_path / "manifest.json"

    _io.save_json_atomic({"a": 1}, str(target))

    with open(target, encoding="utf-8") as handle:
        assert json.load(handle) == {"a": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["manifest.json"]


def test_a_failed_json_write_keeps_the_old_file(tmp_path):
    target = tmp_path / "run_meta.json"
    target.write_text('{"old": 1}', encoding="utf-8")

    with mock.patch.object(_io.os, "fsync", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            _io.save_json_atomic({"new": 2}, str(target))

    assert target.read_text(encoding="utf-8") == '{"old": 1}'
    assert [p.name for p in tmp_path.iterdir()] == ["run_meta.json"]


def test_save_yaml_config_writes_atomically(tmp_path):
    target = tmp_path / "data.yaml"

    assert _io.save_yaml_config({"names": ["cat"], "nc": 1}, str(target))

    with open(target, encoding="utf-8") as handle:
        assert yaml.safe_load(handle) == {"names": ["cat"], "nc": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["data.yaml"]


def test_a_failed_write_keeps_the_old_yaml(tmp_path):
    target = tmp_path / "data.yaml"
    target.write_text("names: [old]\n", encoding="utf-8")

    with mock.patch.object(_io.os, "fsync", side_effect=OSError("disk full")):
        assert _io.save_yaml_config({"names": ["new"]}, str(target)) is False

    assert target.read_text(encoding="utf-8") == "names: [old]\n"
    assert [p.name for p in tmp_path.iterdir()] == ["data.yaml"]
