"""项目内搜索对话框：条件收集、结果回填、跳转的闸门顺序。

匹配逻辑归 ``test_project_search.py``；这里钉的是呈现层 —— 后台线程
在测试里一律关掉，回填与跳转直接调方法，结果必须确定。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PyQt6 import QtWidgets

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


class _StubWidget(QtWidgets.QWidget):
    """文件列表、输出目录、跳转录波——对话框要什么就给什么。

    必须是真 QWidget：QDialog 的构造参数不接受普通 Python 对象。
    """

    def __init__(self, files=(), output_dir=None):
        super().__init__()
        self.file_list_widget = QtWidgets.QListWidget()
        for name in files:
            self.file_list_widget.addItem(name)
        self.output_dir = output_dir
        self._project_dataset_dir = "G:/data/plates"
        self.loaded = []
        self.may_continue = lambda: True
        self._paging_blocked_by_drawing = lambda: False

    def load_file(self, file):
        self.loaded.append(file)


@pytest.fixture()
def dialog(qapp, monkeypatch):
    from anylabeling.views.labeling.widgets.project_search_dialog import (
        ProjectSearchDialog,
    )

    monkeypatch.setattr(
        ProjectSearchDialog, "_start_search", lambda self: None
    )
    widget = _StubWidget(
        files=["G:/data/plates/a.png", "G:/data/plates/b.png"]
    )
    dialog = ProjectSearchDialog(widget)
    yield dialog
    dialog.deleteLater()


def test_criteria_come_from_the_session(dialog):
    root, output_dir, files, label_query, state_query = dialog._criteria()
    assert root == "G:/data/plates"
    assert files == ["G:/data/plates/a.png", "G:/data/plates/b.png"]
    assert label_query == ""
    assert state_query == ""  # 默认「全部」


def test_apply_results_fills_rows_and_count(dialog):
    dialog._apply_results(
        dialog._generation,
        [
            {
                "file": "G:/data/plates/a.png",
                "state": "未复检",
                "labels": ["划痕"],
            },
            {"file": "G:/data/plates/b.png", "state": "未标注", "labels": []},
        ],
    )
    assert dialog.result_list.count() == 2
    assert "a.png" in dialog.result_list.item(0).text()
    assert "未复检" in dialog.result_list.item(0).text()
    assert "共 2 张" in dialog.count_label.text()


def test_apply_results_of_a_stale_generation_is_dropped(dialog):
    dialog._generation = 5
    dialog._apply_results(
        4,  # 旧代：条件又变过一次，这份结果已经没人要了
        [{"file": "G:/data/plates/a.png", "state": "未复检", "labels": []}],
    )
    assert dialog.result_list.count() == 0


def test_apply_results_of_no_match_says_so(dialog):
    dialog._apply_results(dialog._generation, [])
    assert "没有匹配" in dialog.count_label.text()


def test_double_click_jumps_and_closes(dialog):
    dialog._apply_results(
        dialog._generation,
        [{"file": "G:/data/plates/b.png", "state": "未复检", "labels": []}],
    )
    dialog.result_list.setCurrentRow(0)
    dialog._open_selected()
    assert dialog.widget.loaded == ["G:/data/plates/b.png"]
    assert dialog.result() == int(
        QtWidgets.QDialog.DialogCode.Accepted
    )  # 跳转完顺手关掉自己


def test_jump_is_refused_when_unsaved_work_is_pending(dialog, monkeypatch):
    dialog._apply_results(
        dialog._generation,
        [{"file": "G:/data/plates/b.png", "state": "未复检", "labels": []}],
    )
    dialog.result_list.setCurrentRow(0)
    dialog.widget.may_continue = lambda: False
    dialog._open_selected()
    assert dialog.widget.loaded == []


def test_empty_session_says_no_images(qapp):
    from anylabeling.views.labeling.widgets.project_search_dialog import (
        ProjectSearchDialog,
    )

    # 空列表时 _start_search 在起线程之前就返回，真方法可以直接跑。
    dialog = ProjectSearchDialog(_StubWidget(files=[]))
    dialog._start_search()
    assert "没有打开的图片" in dialog.count_label.text()
    dialog.deleteLater()
