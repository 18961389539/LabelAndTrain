"""项目管理增强：概览里的标签列表与上次导出，以及「打开项目文件夹」。

两个 format 函数是纯函数，单独驱动；dashboard 聚合用真记录；
打开文件夹把 QDesktopServices 桩掉，只验证"给了哪个目录"。
"""

import os
import os.path as osp

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from anylabeling.views.labeling import project_dashboard, project_model
from anylabeling.views.labeling.widgets import project_dialog


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "plates"
    root.mkdir()
    assert project_model.create(
        str(root), name="划痕", task="Segment", labels=["划痕", "凹坑", "气泡"]
    )
    return str(root)


# --- 标签行 -----------------------------------------------------------------


def test_labels_line_lists_names():
    line = project_dialog.format_labels_line(["划痕", "凹坑", "气泡"])
    assert line == "标签 3 个：划痕、凹坑、气泡"


def test_labels_line_truncates_a_long_list():
    labels = [f"类{i}" for i in range(9)]
    line = project_dialog.format_labels_line(labels, limit=6)
    assert line.startswith("标签 9 个：类0、类1、类2、类3、类4、类5、")
    assert "共 9 个" in line


def test_labels_line_is_silent_when_there_are_none():
    assert project_dialog.format_labels_line([]) == ""
    assert project_dialog.format_labels_line(["", "  "]) == ""


# --- 上次导出行 -------------------------------------------------------------


def test_last_export_line_shows_path_mode_and_time():
    line = project_dialog.format_last_export_line(
        {
            "save_path": "G:/out/labels",
            "mode": "yolo",
            "at": "2026-10-14 09:20:11",
        }
    )
    assert line == "上次导出：G:/out/labels（yolo，2026-10-14 09:20:11）"


def test_last_export_line_survives_a_bare_snapshot():
    """老快照（没有 at）也要能显示，不能显示一个空的括号。"""
    line = project_dialog.format_last_export_line({"save_path": "G:/out"})
    assert line == "上次导出：G:/out"


def test_last_export_line_is_silent_without_a_path():
    assert project_dialog.format_last_export_line({}) == ""
    assert project_dialog.format_last_export_line(None) == ""


# --- dashboard 聚合 ---------------------------------------------------------


def test_collect_carries_labels_and_last_export(project):
    assert project_model.remember_export(
        project,
        {
            "save_path": "G:/out",
            "mode": "yolo",
            "at": "2026-10-14 09:20:11",
        },
    )
    data = project_dashboard.collect(project)
    assert data["labels"] == ["划痕", "凹坑", "气泡"]
    assert data["last_export"]["save_path"] == "G:/out"
    assert data["last_export"]["at"] == "2026-10-14 09:20:11"


def test_collect_is_forgiving_without_a_record(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    data = project_dashboard.collect(str(plain))
    assert data["labels"] == []
    assert data["last_export"] == {}


def test_the_snapshot_keeps_its_timestamp(project):
    """at 是白名单键：写进去要能读回来，不然概览显示不了时间。"""
    assert project_model.remember_export(
        project, {"save_path": "G:/x", "at": "2026-10-14 10:00:00"}
    )
    assert project_model.last_export(project)["at"] == "2026-10-14 10:00:00"


# --- 打开项目文件夹 ---------------------------------------------------------


def _widget_for(root):
    class _Actions:
        pass

    class _Widget:
        actions = _Actions()

        def __init__(self):
            self.messages = []

        def status(self, message, delay=5000):
            self.messages.append(message)

    class _FileList:
        def count(self):
            return 0

    widget = _Widget()
    widget.file_list_widget = _FileList()
    widget.filename = osp.join(root, "a.png")
    widget.output_dir = root
    widget.image_list = [widget.filename]
    return widget


def test_open_project_folder_opens_the_root(project, monkeypatch):
    from anylabeling.views.labeling.utils import project_view

    opened = []
    monkeypatch.setattr(
        project_view, "current_root", lambda widget: project, raising=False
    )
    monkeypatch.setattr(
        "anylabeling.views.labeling.widgets.project_switcher._open_in_file_manager",
        lambda path: opened.append(path),
    )
    project_view.open_project_folder(_widget_for(project))
    assert opened == [project]


def test_open_project_folder_without_a_project_says_so(monkeypatch):
    from anylabeling.views.labeling.utils import project_view

    seen = {}

    class _Box:
        @staticmethod
        def information(parent, title, text):
            seen["title"] = title
            seen["text"] = text

    monkeypatch.setattr(project_view, "current_root", lambda widget: None)
    monkeypatch.setattr(project_view.QtWidgets, "QMessageBox", _Box)
    project_view.open_project_folder(object())
    assert seen["title"] == "没有打开的项目"
