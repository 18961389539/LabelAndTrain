"""项目管理器的标注进度列：格式化、回填、以及多余结果的丢弃。

进度计数本身住在 ``project_dashboard.collect_progress``（另有测试）；
这里钉住的是呈现层 —— 列格式、回填进正确的行、对话框关掉后迟到的
结果安静消失。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from anylabeling.views.labeling import project_dashboard

_QAPP = None  # QApplication 必须留引用：被 GC 后下一个控件创建是原生崩溃


@pytest.fixture()
def qapp():
    pytest.importorskip("PyQt6")
    from PyQt6 import QtWidgets

    global _QAPP
    if QtWidgets.QApplication.instance() is None:
        _QAPP = QtWidgets.QApplication([])
    return QtWidgets.QApplication.instance()


@pytest.fixture(autouse=True)
def no_modal_boxes(monkeypatch):
    """offscreen 下任何漏桩的模态框都会永远阻塞——一律自动应答。"""
    from PyQt6 import QtWidgets

    OK = QtWidgets.QMessageBox.StandardButton.Ok
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: OK)
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda *a, **k: OK)


# --- 纯格式化 ---------------------------------------------------------------


def test_format_progress_counts_annotated_over_images():
    stat = {"images": 40, "annotated": 12, "confirmed": 5, "rework": 1}
    assert project_dashboard.format_progress(stat) == {"short": "12/40"}


def test_format_progress_reads_no_images_as_a_dash():
    assert project_dashboard.format_progress({"images": 0}) == {"short": "—"}
    assert project_dashboard.format_progress({}) == {"short": "—"}


# --- 对话框呈现 ---------------------------------------------------------------


def _stub_widget(dataset_dir=None):
    """QDialog 的 parent 必须是真 QWidget，属性直接挂在它身上。"""
    from types import SimpleNamespace

    from PyQt6 import QtWidgets

    widget = QtWidgets.QWidget()
    widget._project_dataset_dir = dataset_dir
    widget.may_continue = lambda: True
    widget.file_list_widget = QtWidgets.QListWidget()
    widget.fn_to_index = {}
    widget.reset_state = lambda: None
    widget.set_clean = lambda: None
    widget.toggle_actions = lambda _on: None
    widget.canvas = SimpleNamespace(setEnabled=lambda _on: None)
    widget.actions = SimpleNamespace(
        save_as=SimpleNamespace(setEnabled=lambda _on: None)
    )
    widget.update_progress_title = lambda: None
    widget.status = lambda *_a: None
    return widget


@pytest.fixture()
def switcher(qapp, tmp_path, monkeypatch):
    """一个列出 tmp 下一个项目的切换器（不真正扫盘）。

    后台线程被关掉：呈现层测试必须确定，计数本身归
    ``collect_progress`` 的测试管。
    """
    from anylabeling.views.labeling import project_registry
    from anylabeling.views.labeling.widgets.project_switcher import (
        ProjectSwitcherDialog,
    )

    monkeypatch.setattr(
        ProjectSwitcherDialog,
        "_start_progress_workers",
        lambda self, entries: None,
    )
    root = tmp_path / "plates"
    root.mkdir()
    path = tmp_path / "projects.json"
    monkeypatch.setattr(project_registry, "registry_path", lambda: str(path))
    project_registry.record_project(str(root))
    dialog = ProjectSwitcherDialog(_stub_widget())
    yield dialog
    dialog.deleteLater()


def test_progress_column_exists_and_starts_as_a_placeholder(switcher):
    assert switcher.list.columnCount() == 6
    assert switcher.list.headerItem().text(3) == "标注进度"
    assert switcher.list.topLevelItem(0).text(3) == "计数中…"


def test_apply_progress_fills_its_row_and_tooltip(switcher):
    root = switcher._selected_root()
    stat = {"images": 40, "annotated": 12, "confirmed": 5, "rework": 1}

    switcher._apply_progress(root, stat)

    item = switcher.list.topLevelItem(0)
    assert item.text(3) == "12/40"
    assert "已标注: 12/40" in item.toolTip(0)
    assert "已确认 5" in item.toolTip(0)
    assert "待复检 1" in item.toolTip(0)


def test_apply_progress_for_an_unknown_root_is_dropped(switcher):
    switcher._apply_progress("G:/nowhere", {"images": 3, "annotated": 1})
    assert switcher.list.topLevelItem(0).text(3) == "计数中…"


def test_empty_registry_shows_no_progress_column_junk(
    qapp, tmp_path, monkeypatch
):
    """空列表（占位行）不该参与进度回填，也不该因此崩。"""
    from anylabeling.views.labeling import project_registry
    from anylabeling.views.labeling.widgets.project_switcher import (
        ProjectSwitcherDialog,
    )

    path = tmp_path / "empty.json"
    monkeypatch.setattr(project_registry, "registry_path", lambda: str(path))
    monkeypatch.setattr(
        ProjectSwitcherDialog,
        "_start_progress_workers",
        lambda self, entries: None,
    )
    dialog = ProjectSwitcherDialog(_stub_widget())
    dialog._apply_progress("G:/nowhere", {"images": 1, "annotated": 0})
    dialog.deleteLater()
