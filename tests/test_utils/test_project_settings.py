"""Per-project settings layer and the project registry."""

import json
import os

import pytest

from anylabeling.views.labeling import project, project_registry
from anylabeling.views.labeling import project_settings

PROJECT_FILE = os.path.join(project.PROJECT_DIR_NAME, project.PROJECT_FILE_NAME)


# --- anchor ---------------------------------------------------------------


def test_dataset_dir_is_the_image_folder_not_the_output_dir():
    assert (
        project_settings.dataset_dir_for(
            output_dir="/out", image_list=["/imgs/a.jpg"]
        )
        == "/imgs"
    )
    assert project_settings.dataset_dir_for(filename="/other/x.jpg") == "/other"
    assert project_settings.dataset_dir_for() is None


# --- values ---------------------------------------------------------------


def test_update_values_merges_and_preserves_split_seed(tmp_path):
    project.get_or_create_split_seed(str(tmp_path))
    assert project_settings.update_values(
        str(tmp_path), labels=["cat", "dog"], output_dir=None
    )
    data = json.loads(
        open(os.path.join(str(tmp_path), PROJECT_FILE), encoding="utf-8").read()
    )
    assert data["labels"] == ["cat", "dog"]
    assert "output_dir" not in data
    assert data["split_seed"] > 0


def test_update_values_none_removes_a_key(tmp_path):
    project_settings.update_values(str(tmp_path), labels=["cat"])
    project_settings.update_values(str(tmp_path), labels=None)
    assert project_settings.get_value(str(tmp_path), "labels") is None


def test_get_value_falls_back_on_missing_dir(tmp_path):
    assert project_settings.get_value(str(tmp_path), "labels", ["x"]) == ["x"]
    assert project_settings.get_value(None, "labels", ["x"]) == ["x"]


def test_reset_ui_settings_keeps_split_seed(tmp_path):
    seed, _ = project.get_or_create_split_seed(str(tmp_path))
    project_settings.update_values(
        str(tmp_path), labels=["cat"], output_dir="/out"
    )
    assert project_settings.reset_ui_settings(str(tmp_path)) is True
    data = project.load_project(str(tmp_path))
    assert data["split_seed"] == seed
    assert "labels" not in data and "output_dir" not in data


def test_update_without_changes_skips_the_write(tmp_path):
    project_settings.update_values(str(tmp_path), labels=["cat"])
    before = os.path.getmtime(os.path.join(str(tmp_path), PROJECT_FILE))
    assert project_settings.update_values(str(tmp_path), labels=["cat"])
    after = os.path.getmtime(os.path.join(str(tmp_path), PROJECT_FILE))
    assert before == after


def test_unwritable_dataset_dir_reports_failure(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_text("i am a file, not a directory", encoding="utf-8")
    assert (
        project_settings.update_values(str(blocked), labels=["cat"]) is False
    )


# --- widget hooks (module-level functions, stub-friendly) -----------------


class _StubWidget:
    def __init__(self, panel_names=None, output_dir=None):
        self._panel = list(panel_names or [])
        self.output_dir = output_dir
        self.loaded = None
        self._project_dataset_dir = None

    def _panel_label_names(self):
        return list(self._panel)

    def load_labels(self, names, clear_existing=False):
        self.loaded = names
        self._panel = list(names)


def test_restore_output_dir_explicit_value_wins(tmp_path):
    project_settings.update_values(str(tmp_path), output_dir="/stored")
    widget = _StubWidget(output_dir="/explicit")
    project_settings._restore_output_dir(widget, str(tmp_path))
    assert widget.output_dir == "/explicit"


def test_restore_output_dir_missing_dir_is_ignored(tmp_path):
    project_settings.update_values(str(tmp_path), output_dir="/gone")
    widget = _StubWidget()
    project_settings._restore_output_dir(widget, str(tmp_path))
    assert widget.output_dir is None


def test_restore_output_dir_applies_existing_dir(tmp_path):
    stored = tmp_path / "labels_out"
    stored.mkdir()
    project_settings.update_values(str(tmp_path), output_dir=str(stored))
    widget = _StubWidget()
    project_settings._restore_output_dir(widget, str(tmp_path))
    assert widget.output_dir == str(stored)


def test_restore_labels_only_fills_an_empty_panel(tmp_path):
    project_settings.update_values(str(tmp_path), labels=["cat", "dog"])
    empty = _StubWidget()
    project_settings._restore_labels(empty, str(tmp_path))
    assert empty.loaded == ["cat", "dog"]

    occupied = _StubWidget(panel_names=["bird"])
    project_settings._restore_labels(occupied, str(tmp_path))
    assert occupied.loaded is None
    assert occupied._panel == ["bird"]


def test_save_current_labels_round_trips(tmp_path):
    widget = _StubWidget(panel_names=["cat", "dog"])
    assert project_settings.save_current_labels(widget, str(tmp_path))
    assert project_settings.get_value(str(tmp_path), "labels") == [
        "cat",
        "dog",
    ]


def test_switch_flushes_previous_and_tracks_the_current(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    widget = _StubWidget(panel_names=["cat"])
    project_settings.begin_project_switch(widget, str(first))
    assert widget._project_dataset_dir == str(first)
    widget._panel = ["dog"]  # edited after the switch
    project_settings.begin_project_switch(widget, str(second))
    # The edit was flushed to the previous project before switching.
    assert project_settings.get_value(str(first), "labels") == ["dog"]


# --- registry -------------------------------------------------------------


@pytest.fixture()
def registry_file(tmp_path, monkeypatch):
    path = tmp_path / "projects.json"
    monkeypatch.setattr(
        project_registry, "registry_path", lambda: str(path)
    )
    return path


def test_registry_records_and_orders_projects(registry_file, tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert project_registry.record_project(str(a), label_dir="/labels/a")
    assert project_registry.record_project(str(b))
    entries = project_registry.recent_projects()
    assert [entry["root"] for entry in entries] == [str(b), str(a)]
    assert entries[1]["label_dir"] == "/labels/a"

    project_registry.record_project(str(a))
    assert project_registry.recent_projects()[0]["root"] == str(a)


def test_registry_skips_vanished_folders(registry_file, tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    project_registry.record_project(str(a))
    project_registry.record_project(str(tmp_path / "ghost"))
    assert [
        entry["root"] for entry in project_registry.recent_projects()
    ] == [str(a)]


def test_registry_forget_keeps_the_dataset(registry_file, tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    project_registry.record_project(str(a))
    (a / "keep.jpg").write_text("data", encoding="utf-8")
    assert project_registry.forget_project(str(a)) is True
    assert project_registry.recent_projects() == []
    assert (a / "keep.jpg").exists()


def test_damaged_registry_reads_as_empty(registry_file):
    registry_file.write_text("{ not json", encoding="utf-8")
    assert project_registry.recent_projects() == []
    assert project_registry.load_registry() == {"projects": []}


# --- run history dataset column -------------------------------------------


def test_run_history_rows_carry_the_dataset_name(tmp_path):
    from anylabeling.views.training import run_history

    run_dir = tmp_path / "detect" / "exp1"
    (run_dir / "weights").mkdir(parents=True)
    meta = {
        "task": "detect",
        "name": "exp1",
        "finished_at": "2026-09-25 10:00:00",
        "dataset": {"label_dir": "/data/plates_dataset"},
    }
    with open(run_dir / "run_meta.json", "w", encoding="utf-8") as handle:
        json.dump(meta, handle)

    data = run_history.collect_run_history(str(tmp_path))
    assert data["rows"][0]["dataset"] == "plates_dataset"

    table = run_history.format_history_rows(data["rows"])
    assert table[0][-1] == "数据集"
    assert table[1][-1] == "plates_dataset"


def test_run_history_rows_without_label_dir_stay_blank(tmp_path):
    from anylabeling.views.training import run_history

    run_dir = tmp_path / "detect" / "exp1"
    run_dir.mkdir(parents=True)
    with open(run_dir / "run_meta.json", "w", encoding="utf-8") as handle:
        json.dump({"task": "detect", "name": "exp1"}, handle)

    data = run_history.collect_run_history(str(tmp_path))
    assert data["rows"][0]["dataset"] == ""
