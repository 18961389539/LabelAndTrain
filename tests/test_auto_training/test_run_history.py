"""Run-history collection, iteration alignment and the dialog table."""

import json
import os

import pytest

from anylabeling.views.training import run_history as rh


def _make_run(root, task, name, meta=None, with_results=False):
    run_dir = os.path.join(root, task, name, "weights")
    os.makedirs(run_dir, exist_ok=True)
    if with_results:
        with open(
            os.path.join(root, task, name, "results.csv"),
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write("epoch\n1\n")
    if meta is not None:
        with open(
            os.path.join(root, task, name, "run_meta.json"),
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(meta, handle)
    return os.path.join(root, task, name)


def _meta(name, finished_at, map50, train=8, seed=42):
    return {
        "task": "Detect",
        "name": name,
        "project": "proj",
        "finished_at": finished_at,
        "metrics": {"loss": 0.4, "map50": map50, "epochs": 10},
        "train_args": {"model": "yolov8n.pt"},
        "dataset": {
            "seed": seed,
            "manifest_sha1": "abcdef1234567",
            "classes": ["cat", "dog"],
            "counts": {"train": train, "val": 2},
        },
        "weights": {"sha1": "1234567890abc"},
    }


def test_collects_only_runs_with_metadata(tmp_path):
    root = str(tmp_path / "runs")
    _make_run(root, "detect", "exp", with_results=True)  # legacy
    _make_run(
        root, "detect", "exp2", _meta("exp2", "2026-09-22 10:00:00", 0.72)
    )
    _make_run(
        root, "detect", "exp3", _meta("exp3", "2026-09-23 10:00:00", 0.81)
    )

    data = rh.collect_run_history(root)
    assert [row["name"] for row in data["rows"]] == ["exp3", "exp2"]
    assert data["unrecorded"] == 1


def test_metrics_are_coerced_from_csv_strings(tmp_path):
    root = str(tmp_path / "runs")
    _make_run(
        root, "detect", "exp", _meta("exp", "2026-09-22 10:00:00", "0.7250")
    )
    rows = rh.collect_run_history(root)["rows"]
    assert rows[0]["map50"] == pytest.approx(0.725)


def test_broken_metadata_is_skipped_not_fatal(tmp_path):
    root = str(tmp_path / "runs")
    run_dir = _make_run(root, "detect", "bad", with_results=True)
    with open(
        os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8"
    ) as handle:
        handle.write("{ truncated")
    data = rh.collect_run_history(root)
    assert data["rows"] == []
    assert data["unrecorded"] == 1


def test_missing_root_is_quiet():
    assert rh.collect_run_history("") == {"rows": [], "unrecorded": 0}
    assert rh.collect_run_history("/no/such/place") == {
        "rows": [],
        "unrecorded": 0,
    }


def test_task_filter(tmp_path):
    root = str(tmp_path / "runs")
    _make_run(root, "detect", "d1", _meta("d1", "2026-09-22 10:00:00", 0.5))
    _make_run(root, "segment", "s1", _meta("s1", "2026-09-22 11:00:00", 0.6))
    rows = rh.collect_run_history(root, task="segment")["rows"]
    assert [row["name"] for row in rows] == ["s1"]


def test_iterations_align_by_run_name():
    rows = [
        {"name": "exp3"},
        {"name": "manual_run"},
    ]
    history = {
        "rounds": [
            {"round": 1, "model": "exp2"},
            {"round": 2, "model": "exp3", "new_shapes": 40},
        ]
    }
    rh.align_with_iterations(rows, history)
    assert rows[0]["iteration"]["round"] == 2
    assert rows[0]["iteration"]["new_shapes"] == 40
    assert "iteration" not in rows[1]


def test_summary_reports_the_newest_trend(tmp_path):
    rows = [
        {"name": "b", "map50": 0.80},
        {"name": "a", "map50": 0.70},
    ]
    summary = rh.summarize_history(rows)
    assert summary["best_name"] == "b"
    assert summary["trend"] == pytest.approx(0.10)
    assert summary["trend_from"] == "a"


def test_summary_without_metrics(tmp_path):
    summary = rh.summarize_history([{"name": "x", "map50": None}])
    assert summary["best_map50"] is None
    assert summary["trend"] is None


def test_format_rows_has_a_header_and_one_line_per_run():
    lines = rh.format_history_rows([{"name": "exp", "map50": 0.5}])
    assert lines[0][0] == "任务"
    assert len(lines) == 2
    assert lines[1][1] == "exp"


class TestRunHistoryDialog:
    """Keeps the QApplication at module scope.

    A locally-created QApplication is collected when the helper returns, and
    taking the application down destroys every widget with it - which shows up
    as 'wrapped C/C++ object has been deleted' on a perfectly good table.
    """

    _app = None
    _parents = []

    def _dialog(self, tmp_path, rows_meta, with_label_dir=False):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        from anylabeling.views.training.run_history_dialog import (
            RunHistoryDialog,
        )

        if type(self)._app is None:
            type(
                self
            )._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
                []
            )

        root = str(tmp_path / "runs")
        for name, meta in rows_meta.items():
            _make_run(root, "detect", name, meta)

        label_dir = None
        if with_label_dir:
            label_dir = str(tmp_path / "labels")
            os.makedirs(label_dir, exist_ok=True)
            with open(
                os.path.join(label_dir, "active_learning_history.json"),
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(
                    {
                        "rounds": [
                            {
                                "round": 1,
                                "model": "exp1",
                                "labeled_images": 5,
                                "new_shapes": 12,
                            },
                            {
                                "round": 2,
                                "model": "exp2",
                                "labeled_images": 7,
                                "new_shapes": 40,
                            },
                        ]
                    },
                    handle,
                )

        import anylabeling.views.training.run_history_dialog as module

        original = module.get_default_project_dir
        module.get_default_project_dir = lambda: root
        try:
            parent = QtWidgets.QWidget()
            # The dialog is a Qt child of the parent, so both must outlive the
            # helper call.
            type(self)._parents.append(parent)
            return RunHistoryDialog(parent, label_dir=label_dir)
        finally:
            module.get_default_project_dir = original

    def test_table_width_matches_the_row_layout(self):
        # The table is built with a fixed column count while the header comes
        # from the row formatter, so a new field silently loses its column.
        from anylabeling.views.training.run_history_dialog import COLUMNS

        assert COLUMNS == len(rh.format_history_rows([])[0])

    def test_table_lists_runs_newest_first(self, tmp_path):
        dialog = self._dialog(
            tmp_path,
            {
                "exp2": _meta("exp2", "2026-09-22 10:00:00", 0.72),
                "exp3": _meta("exp3", "2026-09-23 10:00:00", 0.81),
            },
        )
        assert dialog.table.rowCount() == 2
        assert dialog.table.item(0, 1).text() == "exp3"
        assert dialog.table.item(0, 4).text() == "0.8100"
        text = dialog.summary_label.text()
        assert "0.8100" in text
        assert "exp2" in text  # the trend names both rounds

    def test_round_column_comes_from_the_iteration_history(self, tmp_path):
        # Reading the history file from disk is the whole point: the round
        # number lives beside the labels, not in run_meta.json.
        dialog = self._dialog(
            tmp_path,
            {
                "exp1": _meta("exp1", "2026-09-21 10:00:00", 0.60),
                "exp2": _meta("exp2", "2026-09-22 10:00:00", 0.72),
            },
            with_label_dir=True,
        )
        rows = {
            dialog.table.item(i, 1).text(): i
            for i in range(dialog.table.rowCount())
        }
        assert dialog.table.item(rows["exp2"], 2).text() == "2"
        assert dialog.table.item(rows["exp1"], 2).text() == "1"

    def test_empty_state_explains_what_is_missing(self, tmp_path):
        dialog = self._dialog(tmp_path, {})
        assert dialog.table.rowCount() == 0
        text = dialog.summary_label.text()
        assert "run_meta.json" in text
        # Naming the folder scanned is what tells a user whose runs live under a
        # custom Project that this table is not looking where they trained.
        assert str(tmp_path / "runs") in text

    def test_legacy_runs_are_reported_as_a_count(self, tmp_path):
        # Created before the dialog so the patched root already contains it.
        _make_run(str(tmp_path / "runs"), "detect", "old", with_results=True)
        dialog = self._dialog(tmp_path, {})
        assert "早于元数据功能" in dialog.summary_label.text()
        assert dialog.table.rowCount() == 0
