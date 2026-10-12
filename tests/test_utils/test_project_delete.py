"""删除项目数据：回收站通道 + 双重确认 + 当前项目先安全关闭。

回收站是本应用删除数据的唯一通道（``shutil.rmtree`` 没有资格）；
这里钉住通道的契约（False=什么都没删）与切换器流程的闸门顺序。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from anylabeling.views.labeling import project_model, project_registry
from anylabeling.views.labeling.utils import recycle_bin

# --- 回收站通道 -------------------------------------------------------------


def test_send_passes_the_absolute_path_to_the_operation(tmp_path):
    target = tmp_path / "plates"
    target.mkdir()
    seen = []
    assert recycle_bin.send_to_recycle_bin(
        str(target), _operation=lambda p: seen.append(p) or True
    )
    assert seen == [str(target)]


def test_send_of_a_missing_path_never_calls_the_operation(tmp_path):
    seen = []
    assert not recycle_bin.send_to_recycle_bin(
        str(tmp_path / "gone"), _operation=lambda p: seen.append(p) or True
    )
    assert seen == []
    assert (
        recycle_bin.send_to_recycle_bin(
            "", _operation=lambda p: seen.append(p) or True
        )
        is False
    )


def test_a_refusing_operation_reads_as_refusal(tmp_path):
    target = tmp_path / "plates"
    target.mkdir()
    assert not recycle_bin.send_to_recycle_bin(
        str(target), _operation=lambda _p: False
    )


def test_windows_channel_exists_only_on_windows():
    operation = recycle_bin._windows_recycle_operation()
    if os.name != "nt":
        assert operation is None
    else:
        assert callable(operation)


# --- 切换器里的删除流程 -----------------------------------------------------


_QAPP = None  # QApplication 必须留引用：被 GC 后下一个控件创建是原生崩溃


@pytest.fixture()
def qapp():
    pytest.importorskip("PyQt6")
    from PyQt6 import QtWidgets

    global _QAPP
    if QtWidgets.QApplication.instance() is None:
        _QAPP = QtWidgets.QApplication([])
    return QtWidgets.QApplication.instance()


@pytest.fixture()
def one_project(tmp_path, monkeypatch):
    root = tmp_path / "plates"
    root.mkdir()
    (root / "a.png").write_bytes(b"x")
    assert project_model.create(str(root), task="Segment", labels=["划痕"])
    path = tmp_path / "projects.json"
    monkeypatch.setattr(project_registry, "registry_path", lambda: str(path))
    project_registry.record_project(str(root))
    return root, path


@pytest.fixture(autouse=True)
def no_modal_boxes(monkeypatch):
    """offscreen 下任何漏桩的模态框都会永远阻塞——一律自动应答。"""
    from PyQt6 import QtWidgets

    OK = QtWidgets.QMessageBox.StandardButton.Ok
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning", lambda *a, **k: OK)
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda *a, **k: OK)


def _open_switcher(widget):
    from anylabeling.views.labeling.widgets.project_switcher import (
        ProjectSwitcherDialog,
    )

    return ProjectSwitcherDialog(widget)


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


def test_first_confirm_declines_and_nothing_happens(
    qapp, tmp_path, one_project, monkeypatch
):
    from PyQt6 import QtWidgets

    root, _path = one_project
    dialog = _open_switcher(_stub_widget())
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *a, **k: QtWidgets.QMessageBox.StandardButton.No,
    )
    dialog._delete_selected()
    assert root.exists()
    assert any(
        e["root"] == str(root)
        for e in project_registry.load_registry()["projects"]
    )


def test_double_confirmed_delete_forgets_and_reloads(
    qapp, tmp_path, one_project, monkeypatch
):
    from PyQt6 import QtWidgets

    root, _path = one_project
    dialog = _open_switcher(_stub_widget())
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        "anylabeling.views.labeling.utils.recycle_bin." "send_to_recycle_bin",
        lambda _p, **k: True,
    )
    dialog._delete_selected()
    # 假回收站不动真文件（真通道由 Windows shell 负责）；列表必须忘掉它。
    assert root.exists()
    assert project_registry.load_registry()["projects"] == []


def test_failed_recycle_keeps_the_registry_entry(
    qapp, tmp_path, one_project, monkeypatch
):
    from PyQt6 import QtWidgets

    root, _path = one_project
    dialog = _open_switcher(_stub_widget())
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        "anylabeling.views.labeling.utils.recycle_bin." "send_to_recycle_bin",
        lambda _p, **k: False,
    )
    dialog._delete_selected()
    assert root.exists()
    assert any(
        e["root"] == str(root)
        for e in project_registry.load_registry()["projects"]
    )


def test_deleting_the_open_project_closes_it_first(
    qapp, tmp_path, one_project, monkeypatch
):
    from PyQt6 import QtWidgets

    root, _path = one_project
    widget = _stub_widget(dataset_dir=str(root))
    dialog = _open_switcher(widget)
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        "anylabeling.views.labeling.utils.recycle_bin." "send_to_recycle_bin",
        lambda _p, **k: True,
    )
    dialog._delete_selected()
    assert widget._project_dataset_dir is None
    assert project_registry.load_registry()["projects"] == []


# --- 卷类型闸门 -------------------------------------------------------------
# FOF_ALLOWUNDO 在没有回收站的卷（网络盘/RAM盘）上会直接永久删除——
# 这类卷必须被拒绝，False 永远意味着"什么都没删"。


def test_a_volume_without_a_recycle_bin_is_refused():
    if os.name != "nt":
        pytest.skip("the drive-type gate is Windows-only")
    operation = recycle_bin._windows_recycle_operation()
    if operation is None:
        pytest.skip("not windows")
    # DRIVE_REMOTE(4)：网络共享没有回收站
    assert operation("X:/plates", _drive_type_of=lambda _p: 4) is False
    # DRIVE_CDROM(5)：光驱同理
    assert operation("X:/plates", _drive_type_of=lambda _p: 5) is False
    # DRIVE_UNKNOWN(0)：认不出的卷也不赌
    assert operation("X:/plates", _drive_type_of=lambda _p: 0) is False


def test_drive_type_reads_the_volume_root():
    if os.name != "nt":
        pytest.skip("the drive-type gate is Windows-only")
    operation = recycle_bin._windows_recycle_operation()
    if operation is None:
        pytest.skip("not windows")
    seen = []
    # drive_type_of 是 operation 的默认参数，通过注入观察它收到的卷根
    operation("C:/plates", _drive_type_of=lambda p: seen.append(p) or 3)
    assert seen and seen[0].upper().startswith("C:")
