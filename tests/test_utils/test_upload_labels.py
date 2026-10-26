"""An imported class file becomes the project's list, not a session illusion."""

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from anylabeling.views.labeling.utils import upload as upload_module
from anylabeling.views.labeling.utils.upload import (
    apply_uploaded_labels,
    persist_label_flags,
    persist_shape_attributes,
    sanitize_label_list,
    validate_label_flags,
)


def test_validate_label_flags_normalizes_names():
    assert validate_label_flags(
        {"cat": ["occluded", " cut "], "dog": None}
    ) == {"cat": ["occluded", "cut"], "dog": []}


@pytest.mark.parametrize(
    "data",
    [None, ["cat"], {"": ["x"]}, {"cat": "x"}, {"cat": [1]}],
)
def test_validate_label_flags_rejects_bad_shapes(data):
    with pytest.raises(ValueError):
        validate_label_flags(data)


def test_persist_helpers_write_the_config(monkeypatch):
    saved = []
    widget = SimpleNamespace(
        _config={"canvas": {"attributes": None}, "label_flags": None}
    )
    monkeypatch.setattr(
        upload_module, "save_config", lambda cfg: saved.append(cfg) or True
    )

    persist_shape_attributes(widget, {"cat": []})
    persist_label_flags(widget, {"cat": ["hidden"]})

    assert widget._config["canvas"]["attributes"] == {"cat": []}
    assert widget._config["label_flags"] == {"cat": ["hidden"]}
    assert len(saved) == 2


def test_persist_shape_attributes_repairs_a_broken_canvas(monkeypatch):
    widget = SimpleNamespace(_config={"canvas": None})
    monkeypatch.setattr(upload_module, "save_config", lambda cfg: True)

    persist_shape_attributes(widget, {"cat": []})

    assert widget._config["canvas"] == {"attributes": {"cat": []}}


def test_sanitize_drops_blanks_and_duplicates():
    assert sanitize_label_list(
        ["cat\n", " dog \n", "\n", "cat\n", "", "dog\n"]
    ) == ["cat", "dog"]
    assert sanitize_label_list(["\n", "   \n"]) == []


class _Items:
    def __init__(self):
        self.items = []

    def clear(self):
        self.items.clear()

    def addItems(self, labels):
        self.items.extend(labels)

    def sort_labels(self):
        pass


class _LabelDialog:
    def __init__(self):
        self.label_list = _Items()
        self._sort_labels = False


def _widget(calls):
    return SimpleNamespace(
        _config={"labels": ["old"]},
        load_labels=lambda labels: calls.setdefault("loaded", list(labels)),
        label_dialog=_LabelDialog(),
        digit_shortcut_controller=SimpleNamespace(
            assign_label_digits=lambda labels: calls.setdefault(
                "digits", list(labels)
            )
        ),
    )


def test_apply_persists_config_ui_and_project(monkeypatch, tmp_path):
    calls = {}
    widget = _widget(calls)
    monkeypatch.setattr(
        upload_module,
        "save_config",
        lambda cfg: calls.setdefault("saved", list(cfg["labels"])) or True,
    )
    monkeypatch.setattr(
        upload_module.project_context,
        "current_dataset_dir",
        lambda _widget: str(tmp_path),
    )
    monkeypatch.setattr(
        upload_module.project_settings,
        "save_current_labels",
        lambda w, d: calls.setdefault("project", (w, d)) or True,
    )

    apply_uploaded_labels(widget, ["a", "b"])

    assert widget._config["labels"] == ["a", "b"]
    assert calls["saved"] == ["a", "b"]
    assert calls["loaded"] == ["a", "b"]
    assert calls["digits"] == ["a", "b"]
    assert widget.label_dialog.label_list.items == ["a", "b"]
    assert calls["project"][1] == str(tmp_path)


def test_outside_a_project_only_the_config_is_saved(monkeypatch):
    calls = {}
    widget = _widget(calls)
    monkeypatch.setattr(
        upload_module,
        "save_config",
        lambda cfg: calls.setdefault("saved", list(cfg["labels"])) or True,
    )
    monkeypatch.setattr(
        upload_module.project_context,
        "current_dataset_dir",
        lambda _widget: None,
    )

    apply_uploaded_labels(widget, ["x"])

    assert calls["saved"] == ["x"]
    assert "project" not in calls
