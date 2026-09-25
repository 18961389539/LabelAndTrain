"""Per-project settings layer and the project registry."""

import json
import os
import os.path as osp
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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
    assert data["rows"][0]["dataset_label_dir"] == "/data/plates_dataset"

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
    assert data["rows"][0]["dataset_label_dir"] == ""


# --- per-project training stats -------------------------------------------


def _write_run_meta(runs_root, task, name, label_dir, finished_at):
    run_dir = runs_root / task / name
    run_dir.mkdir(parents=True)
    meta = {
        "task": task,
        "name": name,
        "finished_at": finished_at,
        "dataset": {"label_dir": label_dir},
    }
    (run_dir / "run_meta.json").write_text(
        json.dumps(meta), encoding="utf-8"
    )


def test_project_training_stats_match_by_closest_anchor(tmp_path):
    from anylabeling.views.training import run_history

    runs = tmp_path / "runs"
    _write_run_meta(
        runs, "detect", "exp1", "/data/plates/labels", "2026-09-25 10:00:00"
    )
    _write_run_meta(
        runs, "detect", "exp2", "/data/plates", "2026-09-25 11:00:00"
    )
    _write_run_meta(
        runs, "detect", "exp3", "/elsewhere", "2026-09-25 12:00:00"
    )

    projects = [
        {"root": "/data/plates", "label_dir": "/data/plates/labels"},
        {"root": "/data/other", "label_dir": None},
    ]
    stats = run_history.project_training_stats(projects, str(runs))

    # exp1 lands on the inner label_dir anchor, exp2 on the root itself,
    # exp3 belongs to nobody.
    assert stats["/data/plates"] == {
        "runs": 2,
        "last": "2026-09-25 11:00:00",
    }
    assert stats["/data/other"] == {"runs": 0, "last": ""}


def test_project_training_stats_respect_prefix_boundaries(tmp_path):
    from anylabeling.views.training import run_history

    runs = tmp_path / "runs"
    _write_run_meta(
        runs,
        "detect",
        "exp1",
        "/data/plates_extra/ds",
        "2026-09-25 10:00:00",
    )

    projects = [
        {"root": "/data/plates", "label_dir": None},
        {"root": "/data/plates_extra", "label_dir": None},
    ]
    stats = run_history.project_training_stats(projects, str(runs))

    # "plates_extra" is a sibling of "plates": a bare startswith would
    # credit the run to the wrong project.
    assert stats["/data/plates"] == {"runs": 0, "last": ""}
    assert stats["/data/plates_extra"] == {
        "runs": 1,
        "last": "2026-09-25 10:00:00",
    }


def test_project_training_stats_without_runs_root_is_all_zero(tmp_path):
    from anylabeling.views.training import run_history

    projects = [{"root": str(tmp_path / "ds"), "label_dir": None}]
    stats = run_history.project_training_stats(projects, "")
    assert stats == {str(tmp_path / "ds"): {"runs": 0, "last": ""}}


# --- startup flow ---------------------------------------------------------


def test_startup_action_matrix():
    decide = project_registry.decide_startup_action
    # The always-show switch wins over everything.
    assert (
        decide(True, True, True) == "manager"
        and decide(False, True, False) == "manager"
    )
    # A recorded session is restored directly, without asking.
    assert decide(True, False, True) == "restore"
    assert decide(True, False, False) == "restore"
    # No session but the registry has entries: let the user pick.
    assert decide(False, False, True) == "manager"
    # First run: the empty-canvas CTA stays unobstructed.
    assert decide(False, False, False) == "none"


def test_startup_show_project_manager_defaults_off():
    import importlib.resources as pkg_resources

    import yaml

    import anylabeling.configs as anylabeling_configs

    with pkg_resources.open_text(
        anylabeling_configs, "jllabeling_config.yaml"
    ) as handle:
        template = yaml.safe_load(handle)
    assert template["startup_show_project_manager"] is False


# --- training prefs whitelist ---------------------------------------------


def _train_dialog_stub(dataset_dir):
    from anylabeling.views.training.ultralytics_dialog import UltralyticsDialog

    stub = SimpleNamespace(image_list=[osp.join(dataset_dir, "a.jpg")])
    stub.save_prefs = UltralyticsDialog._save_project_train_prefs.__get__(stub)
    stub.load_prefs = UltralyticsDialog._project_train_prefs.__get__(stub)
    return stub


def test_train_prefs_whitelist_round_trip(tmp_path):
    stub = _train_dialog_stub(str(tmp_path))
    config = {
        "basic": {
            "project": "/runs",
            "name": "exp",
            "model": "yolo11n.pt",
            "data": "C:/temp/dataset.yaml",
            "device": "0",
            "dataset_ratio": 0.8,
            "pose_config": "",
        },
        "train": {
            "epochs": 100,
            "batch": 16,
            "imgsz": 640,
            "workers": 8,
            "single_cls": False,
            "classes": [],
        },
        "learning_rate": {"lr0": 0.01, "lrf": 0.01},
        "regularization": {"dropout": 0.0},
    }

    assert stub.save_prefs(config) is True

    data = project.load_project(str(tmp_path))
    prefs = data["train_prefs"]
    # Global/run-specific/machine-specific keys never travel with the dataset.
    assert prefs["basic"] == {"model": "yolo11n.pt", "pose_config": ""}
    assert "project" not in prefs["basic"]
    assert "data" not in prefs["basic"]
    assert "device" not in prefs["basic"]
    assert "dataset_ratio" not in prefs["basic"]
    assert prefs["train"]["workers"] == 8
    assert prefs["learning_rate"] == {"lr0": 0.01, "lrf": 0.01}
    assert stub.load_prefs()["train"]["epochs"] == 100

    # Re-saving with changed values overwrites, not merges stale keys.
    config["train"]["epochs"] = 200
    config.pop("learning_rate")
    assert stub.save_prefs(config) is True
    prefs = stub.load_prefs()
    assert prefs["train"]["epochs"] == 200
    assert "learning_rate" not in prefs


def test_train_prefs_without_a_dataset_dir_is_a_no_op():
    from anylabeling.views.training.ultralytics_dialog import UltralyticsDialog

    stub = SimpleNamespace(image_list=[])
    assert UltralyticsDialog._project_train_prefs.__get__(stub)() == {}
    config = {"basic": {"model": "x.pt"}}
    assert UltralyticsDialog._save_project_train_prefs.__get__(stub)(
        config
    ) is False


def test_train_prefs_damaged_record_falls_back_to_empty(tmp_path):
    project.save_project(str(tmp_path), {"train_prefs": "not a dict"})
    stub = _train_dialog_stub(str(tmp_path))
    assert stub.load_prefs() == {}
