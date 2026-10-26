"""Training settings JSON is written atomically."""

import json
from unittest import mock

from anylabeling.services.auto_training.ultralytics import _io


def _target(tmp_path, monkeypatch):
    target = tmp_path / "training_settings.json"
    monkeypatch.setattr(_io, "get_settings_config_path", lambda: str(target))
    return target


def test_save_config_writes_json(tmp_path, monkeypatch):
    target = _target(tmp_path, monkeypatch)

    assert _io.save_config({"a": 1}) is True

    with open(target, encoding="utf-8") as handle:
        assert json.load(handle) == {"a": 1}
    assert [
        n for n in target.parent.iterdir() if n.name.endswith(".tmp")
    ] == []


def test_a_failed_save_keeps_the_old_json(tmp_path, monkeypatch):
    target = _target(tmp_path, monkeypatch)
    target.write_text('{"old": 1}', encoding="utf-8")

    with mock.patch.object(_io.os, "fsync", side_effect=OSError("disk full")):
        assert _io.save_config({"new": 2}) is False

    assert target.read_text(encoding="utf-8") == '{"old": 1}'
    assert [p.name for p in target.parent.iterdir()] == [
        "training_settings.json"
    ]
