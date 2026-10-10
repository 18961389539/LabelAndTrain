"""项目概览聚合：进度与训练轮次都从盘上现数，不另存一份。

``project_dashboard`` 的价值在于"两边的数字在同一处对得上"：进度用与
文件列表相同的 review 扫描，训练归属用与项目列表相同的最近祖先规则。
这里重点钉住：计数口径、output_dir 覆盖、runs 归属边界，以及"读不了
就当没有"的容错。
"""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from anylabeling.views.labeling import project_dashboard
from anylabeling.views.labeling.utils.async_label_check import (
    label_file_review_info,
)


def _write_label(path, *, state=None, checked=None):
    """与文件列表同源的标注 JSON：review 头在 shapes 之前。"""
    header = {}
    if state is not None:
        header["review_state"] = state
    if checked is not None:
        header["checked"] = checked
    header["shapes"] = []
    path.write_text(json.dumps(header), encoding="utf-8")


def _write_run_meta(runs_root, task, name, label_dir, finished, map50=None):
    run_dir = runs_root / task / name
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "name": name,
        "task": task,
        "status": "completed",
        "finished_at": finished,
        "metrics": {"map50": map50, "epochs": 50},
        "dataset": {"label_dir": label_dir},
    }
    (run_dir / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")


# --- 标签路径规则 -----------------------------------------------------------


def test_label_path_sits_beside_the_image():
    assert project_dashboard.label_path_for_image("/d/a.png") == "/d/a.json"


def test_label_path_honours_the_output_dir_override():
    assert project_dashboard.label_path_for_image(
        "/d/sub/a.png", output_dir="/out"
    ) == os.path.join("/out", "a.json")


# --- 进度计数 ---------------------------------------------------------------


def test_progress_counts_each_review_state(tmp_path):
    (tmp_path / "ok.png").write_bytes(b"x")
    (tmp_path / "bad.png").write_bytes(b"x")
    (tmp_path / "plain.png").write_bytes(b"x")
    (tmp_path / "unreviewed.png").write_bytes(b"x")
    _write_label(tmp_path / "ok.json", state="confirmed")
    _write_label(tmp_path / "bad.json", state="rejected")
    _write_label(tmp_path / "unreviewed.json", checked=False)
    # plain.png 有标注但未复核 —— 走 legacy checked 字段。

    progress = project_dashboard.collect_progress(str(tmp_path))
    assert progress == {
        "images": 4,
        "annotated": 3,
        "confirmed": 1,
        "rework": 1,
    }


def test_progress_uses_the_output_dir(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    out = tmp_path / "labels"
    out.mkdir()
    (images / "a.png").write_bytes(b"x")
    _write_label(out / "a.json", state="confirmed")

    progress = project_dashboard.collect_progress(
        str(images), output_dir=str(out)
    )
    assert progress["annotated"] == 1
    assert progress["confirmed"] == 1


def test_progress_of_an_empty_folder_is_all_zero(tmp_path):
    assert project_dashboard.collect_progress(str(tmp_path)) == {
        "images": 0,
        "annotated": 0,
        "confirmed": 0,
        "rework": 0,
    }


def test_progress_of_a_missing_folder_is_all_zero(tmp_path):
    progress = project_dashboard.collect_progress(str(tmp_path / "gone"))
    assert progress["images"] == 0


# --- 训练归属 ---------------------------------------------------------------


def test_training_rows_follow_the_closest_anchor(tmp_path):
    runs = tmp_path / "runs"
    _write_run_meta(
        runs,
        "detect",
        "exp1",
        str(tmp_path / "labels"),
        "2026-10-01 10:00:00",
        map50=0.5,
    )
    _write_run_meta(
        runs,
        "detect",
        "exp2",
        str(tmp_path / "labels"),
        "2026-10-02 11:00:00",
        map50=0.75,
    )
    _write_run_meta(
        runs,
        "detect",
        "elsewhere",
        "/data/other",
        "2026-10-03 09:00:00",
        map50=0.9,
    )

    stats = project_dashboard.collect_training(
        str(tmp_path),
        output_dir=str(tmp_path / "labels"),
        runs_root=str(runs),
    )
    assert stats["runs"] == 2
    assert stats["best_map50"] == 0.75
    assert stats["best_name"] == "exp2"
    # newest finished first：最后一轮是 exp2。
    assert stats["last_run"] == "exp2"
    assert stats["last_finished"] == "2026-10-02 11:00:00"


def test_training_attribution_respects_prefix_boundaries(tmp_path):
    runs = tmp_path / "runs"
    _write_run_meta(
        runs,
        "detect",
        "sneaky",
        str(tmp_path) + "_extra",
        "2026-10-01 10:00:00",
        map50=0.5,
    )
    stats = project_dashboard.collect_training(
        str(tmp_path), runs_root=str(runs)
    )
    assert stats["runs"] == 0


def test_training_without_runs_reads_as_never_trained(tmp_path):
    stats = project_dashboard.collect_training(
        str(tmp_path), runs_root=str(tmp_path / "nope")
    )
    assert stats == {
        "runs": 0,
        "best_map50": None,
        "best_name": "",
        "last_run": "",
        "last_finished": "",
    }


# --- 汇总与渲染 -------------------------------------------------------------


def test_collect_joins_both_halves(tmp_path):
    (tmp_path / "a.png").write_bytes(b"x")
    _write_label(tmp_path / "a.json", state="confirmed")

    overview = project_dashboard.collect(str(tmp_path), runs_root="")
    assert overview["progress"]["images"] == 1
    assert overview["training"]["runs"] == 0


@pytest.mark.parametrize(
    "overview, expected",
    [
        (
            {
                "progress": {
                    "images": 3,
                    "annotated": 2,
                    "confirmed": 1,
                    "rework": 0,
                },
                "training": {"runs": 0},
            },
            ["已标 2/3 · 已确认 1 · 需返工 0", "尚未训练"],
        ),
        (
            {
                "progress": {
                    "images": 0,
                    "annotated": 0,
                    "confirmed": 0,
                    "rework": 0,
                },
                "training": {"runs": 0},
            },
            [],
        ),
    ],
)
def test_overview_group_lines(overview, expected):
    pytest.importorskip("PyQt6")
    from PyQt6 import QtWidgets

    from anylabeling.views.labeling.widgets.project_dialog import (
        build_overview_group,
    )

    # QApplication 必须留引用：临时对象被 GC 后，下一个控件创建是
    # 原生崩溃（Qt 运行时被连根拆掉）。
    global _QAPP
    if QtWidgets.QApplication.instance() is None:
        _QAPP = QtWidgets.QApplication([])

    group = build_overview_group(overview)
    if not expected:
        assert group is None
        return
    texts = [label.text() for label in group.findChildren(QtWidgets.QLabel)]
    group.deleteLater()
    assert texts == expected


_QAPP = None


def test_fmt_map50():
    from anylabeling.views.labeling.widgets.project_dialog import _fmt_map50

    assert _fmt_map50(0.734) == "73.4%"
    assert _fmt_map50(None) is None
    assert _fmt_map50("junk") is None
