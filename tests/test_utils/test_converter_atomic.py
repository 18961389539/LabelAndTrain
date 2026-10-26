"""Converter label writes must not truncate the file they replace."""

import json
from unittest import mock

import pytest

from anylabeling.views.labeling import label_converter


def test_save_json_keeps_the_old_file_on_failure(tmp_path):
    target = tmp_path / "a.json"
    target.write_text('{"old": 1}', encoding="utf-8")

    with mock.patch.object(
        label_converter.os, "fsync", side_effect=OSError("disk full")
    ):
        with pytest.raises(OSError):
            label_converter.LabelConverter.save_json({"new": 2}, str(target))

    assert target.read_text(encoding="utf-8") == '{"old": 1}'
    assert [
        n for n in target.parent.iterdir() if n.name.endswith(".tmp")
    ] == []


def test_save_json_replaces_the_file_on_success(tmp_path):
    target = tmp_path / "a.json"

    label_converter.LabelConverter.save_json({"a": 1}, str(target))

    with open(target, encoding="utf-8") as handle:
        assert json.load(handle) == {"a": 1}
    assert [p.name for p in target.parent.iterdir()] == ["a.json"]
