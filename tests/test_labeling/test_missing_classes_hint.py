"""The 还没有类别 hint: advice once per project, never on every folder open.

The 2026-10-10 machine check counted eleven of these dialogs in nine steps,
because ``load_dir`` ended with the prompt unconditionally: reopening the
project that was just closed, or switching projects, stacked another modal.
These tests pin the two rules that replaced it: one prompt per project per
session, and 不再提示 recorded in the project so a restart stays quiet.
"""

import os
from types import SimpleNamespace

import pytest

from anylabeling.views.labeling import project_settings
from anylabeling.views.labeling.utils import missing_classes_hint


class _Labels:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count


class _Widget:
    def __init__(self, labels=0, visible=True, dataset_dir=None):
        self.unique_label_list = _Labels(labels)
        self._visible = visible
        self._project_dataset_dir = dataset_dir
        self.manager_opens = 0

    def isVisible(self):
        return self._visible

    def label_manager(self):
        self.manager_opens += 1


class _Box:
    """Stands in for QMessageBox: no modal, and the click is decided up front.

    ``clickedButton()`` is only meaningful after ``exec()``, so a test that
    wants a button to have been pressed names it before the hint runs.
    """

    Icon = SimpleNamespace(Information="information")
    ButtonRole = SimpleNamespace(
        AcceptRole="accept",
        ActionRole="action",
        DestructiveRole="destructive",
        RejectRole="reject",
    )
    shown = []
    next_click = "reject"

    def __init__(self, parent=None):
        self.parent = parent
        self.buttons = {}
        self.title = None
        self.text = None
        self.icon = None
        type(self).shown.append(self)

    def setWindowTitle(self, title):
        self.title = title

    def setIcon(self, icon):
        self.icon = icon

    def setText(self, text):
        self.text = text

    def addButton(self, text, role):
        button = SimpleNamespace(text=text, role=role)
        self.buttons[role] = button
        return button

    def exec(self):
        return 0

    def clickedButton(self):
        return self.buttons.get(self.next_click)


@pytest.fixture(autouse=True)
def _fresh_box(monkeypatch):
    """Route the hint through the fake box; no modal ever opens.

    ``translate`` is stubbed to the source text: this build's source strings
    are already Chinese, and the point here is which buttons exist and what
    they do, not the catalog. The asked table is process state, so each test
    starts from an empty one.
    """
    _Box.shown = []
    _Box.next_click = "reject"
    missing_classes_hint.asked_roots().clear()
    monkeypatch.setattr(
        missing_classes_hint,
        "QtWidgets",
        SimpleNamespace(QMessageBox=_Box),
    )
    monkeypatch.setattr(
        missing_classes_hint,
        "QtCore",
        SimpleNamespace(
            QCoreApplication=SimpleNamespace(
                translate=lambda context, text, *rest: text
            )
        ),
    )
    yield _Box


def _click(role):
    _Box.next_click = role


def _one_shown():
    assert len(_Box.shown) == 1, [b.text for b in _Box.shown]
    return _Box.shown[0]


# --- the repeat the machine check counted ---------------------------------


def test_classes_present_leaves_the_widget_alone():
    missing_classes_hint.maybe_prompt(_Widget(labels=3), "C:/proj")
    assert _Box.shown == []


def test_same_project_is_asked_once_per_session(tmp_path):
    widget = _Widget()
    root = str(tmp_path)
    missing_classes_hint.maybe_prompt(widget, root)
    missing_classes_hint.maybe_prompt(widget, root)
    assert len(_Box.shown) == 1


def test_each_project_is_asked_once(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    widget = _Widget()
    missing_classes_hint.maybe_prompt(widget, str(first))
    missing_classes_hint.maybe_prompt(widget, str(second))
    assert len(_Box.shown) == 2
    missing_classes_hint.maybe_prompt(widget, str(first))
    assert len(_Box.shown) == 2


def test_reopening_after_a_project_switch_is_silent(tmp_path):
    """The check's eleven: 关闭项目后重开 must not start a new modal.

    A fresh widget object is the point: the table of asked projects is
    process state on purpose, so whatever rebuilds the labeling view cannot
    restart the counting.
    """
    root = str(tmp_path)
    missing_classes_hint.maybe_prompt(_Widget(), root)
    missing_classes_hint.maybe_prompt(_Widget(), root)
    assert len(_Box.shown) == 1


def test_two_spellings_of_one_folder_are_one_project(tmp_path):
    """Case and separator noise must not buy the annotator a second dialog."""
    root = str(tmp_path)
    missing_classes_hint.maybe_prompt(_Widget(), root)
    missing_classes_hint.maybe_prompt(_Widget(), root + os.sep)
    missing_classes_hint.maybe_prompt(_Widget(), root.upper())
    assert len(_Box.shown) == 1


# --- 不再提示 is a recorded choice, not a one-off dismissal ---------------


def test_never_ask_mutes_the_project_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(
        project_settings,
        "report_write_failure",
        lambda *args, **kwargs: pytest.fail("the write should succeed"),
    )
    _click("destructive")
    missing_classes_hint.maybe_prompt(_Widget(), str(tmp_path))
    assert (
        project_settings.get_value(str(tmp_path), project_settings.HINT_KEY)
        == missing_classes_hint.MUTED
    )
    # A later session, same project: quiet without remembering anything.
    _Box.shown = []
    missing_classes_hint.asked_roots().clear()
    missing_classes_hint.maybe_prompt(_Widget(), str(tmp_path))
    assert _Box.shown == []


def test_later_does_not_mute_the_project(tmp_path):
    missing_classes_hint.maybe_prompt(_Widget(), str(tmp_path))
    assert not missing_classes_hint.is_muted(str(tmp_path))
    # A later session -- the process restarted, so the asked table is empty
    # -- is entitled to ask again. 「稍后再说」 is not 「不再提示」.
    missing_classes_hint.asked_roots().clear()
    missing_classes_hint.maybe_prompt(_Widget(), str(tmp_path))
    assert len(_Box.shown) == 2


def test_the_reset_entry_re_arms_the_next_session(tmp_path):
    """不再提示 must be reversible from the UI, not only by editing files."""
    assert project_settings.HINT_KEY in project_settings.UI_KEYS
    root = str(tmp_path)
    _click("destructive")
    missing_classes_hint.maybe_prompt(_Widget(), root)
    assert missing_classes_hint.is_muted(root)

    # A new session, same mute: the record is what keeps it quiet, because a
    # muted project never enters the asked table in the first place.
    _Box.shown = []
    missing_classes_hint.asked_roots().clear()
    missing_classes_hint.maybe_prompt(_Widget(), root)
    assert _Box.shown == []

    assert project_settings.reset_ui_settings(root) is True
    assert not missing_classes_hint.is_muted(root)
    missing_classes_hint.maybe_prompt(_Widget(), root)
    assert len(_Box.shown) == 1


def test_a_failed_mute_is_reported_rather_than_silently_lost(
    tmp_path, monkeypatch
):
    reported = []
    monkeypatch.setattr(
        project_settings,
        "report_write_failure",
        lambda widget, root, action="": reported.append((root, action)),
    )
    monkeypatch.setattr(
        project_settings, "update_values", lambda *a, **k: False
    )
    _click("destructive")
    missing_classes_hint.maybe_prompt(_Widget(), str(tmp_path))
    assert reported == [(str(tmp_path), "missing-classes hint")]


# --- the doors the hint offers -------------------------------------------


def test_import_button_reaches_the_classes_file_import(tmp_path, monkeypatch):
    from anylabeling.views.labeling.utils import upload

    calls = []
    monkeypatch.setattr(
        upload,
        "upload_label_classes_file",
        lambda widget: calls.append(widget),
    )
    widget = _Widget()
    _click("accept")
    missing_classes_hint.maybe_prompt(widget, str(tmp_path))
    assert calls == [widget]


def test_manager_button_opens_the_label_manager(tmp_path):
    widget = _Widget()
    _click("action")
    missing_classes_hint.maybe_prompt(widget, str(tmp_path))
    assert widget.manager_opens == 1


def test_the_hint_names_both_ways_out(tmp_path):
    """Advice that only states the problem is the nagging the check saw."""
    missing_classes_hint.maybe_prompt(_Widget(), str(tmp_path))
    box = _one_shown()
    assert box.title == "还没有类别"
    assert box.icon == "information"
    assert "classes.txt" in box.text
    assert {b.text for b in box.buttons.values()} == {
        "导入 classes.txt",
        "打开标签管理器",
        "不再提示",
        "稍后再说",
    }


# --- nothing to advise about ---------------------------------------------


def test_no_folder_open_is_silent():
    missing_classes_hint.maybe_prompt(_Widget(dataset_dir=None), None)
    assert _Box.shown == []


def test_a_vanished_folder_is_not_a_project(tmp_path):
    missing_classes_hint.maybe_prompt(_Widget(), str(tmp_path / "gone"))
    assert _Box.shown == []


def test_invisible_widget_retries_once_and_does_not_stack(
    tmp_path, monkeypatch
):
    """A folder can open before the window is shown; the hint waits, once."""
    scheduled = []
    monkeypatch.setattr(
        missing_classes_hint,
        "_schedule",
        lambda widget, dataset_dir: scheduled.append((widget, dataset_dir)),
    )
    widget = _Widget(visible=False)
    missing_classes_hint.maybe_prompt(widget, str(tmp_path))
    missing_classes_hint.maybe_prompt(widget, str(tmp_path))
    assert [call[1] for call in scheduled] == [str(tmp_path)]
    assert widget._missing_classes_hint_pending is True
    assert _Box.shown == []
