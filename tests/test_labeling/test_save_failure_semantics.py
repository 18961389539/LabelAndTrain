"""Leaving an image must wait for a save the user asked for.

The Save/Discard/Cancel prompt used to return True after Save even when the
write had failed, and closing reused that answer -- so a full disk ended
with the edits gone. Cancelling the close also fell through to the rest of
the handler, silencing the background scanners and closing the settings
session while the window stayed open.
"""

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import QtWidgets

from anylabeling.views.labeling.label_widget import LabelingWidget

SAVE = QtWidgets.QMessageBox.StandardButton.Save
DISCARD = QtWidgets.QMessageBox.StandardButton.Discard
CANCEL = QtWidgets.QMessageBox.StandardButton.Cancel


def _widget(save_ok=False, **overrides):
    values = {
        "_auto_save_pending": False,
        "dirty": True,
        "filename": "a.png",
        "_pending_inherited_shapes": False,
        "output_file": None,
        "_config": {"auto_save": False},
        "save_file": lambda: save_ok,
        "tr": lambda text: text,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _answer(monkeypatch, button):
    monkeypatch.setattr(
        QtWidgets.QMessageBox, "question", lambda *args, **kwargs: button
    )


def test_a_failed_save_keeps_the_user_on_the_image(monkeypatch):
    _answer(monkeypatch, SAVE)

    assert LabelingWidget.may_continue(_widget(save_ok=False)) is False


def test_a_successful_save_allows_leaving(monkeypatch):
    _answer(monkeypatch, SAVE)

    assert LabelingWidget.may_continue(_widget(save_ok=True)) is True


def test_cancel_keeps_the_user_here(monkeypatch):
    _answer(monkeypatch, CANCEL)

    def must_not_save():
        raise AssertionError("cancel must not save")

    assert (
        LabelingWidget.may_continue(_widget(save_file=must_not_save)) is False
    )


def test_discard_allows_leaving_and_drops_the_inherited_flag(monkeypatch):
    _answer(monkeypatch, DISCARD)
    widget = _widget(_pending_inherited_shapes=True)

    assert LabelingWidget.may_continue(widget) is True
    assert widget._pending_inherited_shapes is False


def test_a_cancelled_close_does_not_touch_the_session():
    class _Settings:
        def setValue(self, *args):
            raise AssertionError("settings must not be persisted on cancel")

    class _Event:
        def __init__(self):
            self.ignored = False

        def ignore(self):
            self.ignored = True

    event = _Event()
    widget = SimpleNamespace(may_continue=lambda: False, settings=_Settings())

    LabelingWidget.closeEvent(widget, event)

    assert event.ignored is True


def test_a_failed_output_save_does_not_close_the_window():
    closed = []

    class _Image:
        def isNull(self):
            return False

    widget = SimpleNamespace(
        image=_Image(),
        label_file=None,
        output_file="out.json",
        _save_file=lambda filename: False,
        close=lambda: closed.append(True),
    )

    assert LabelingWidget.save_file(widget) is False
    assert closed == []


def test_save_file_reports_the_write_result():
    class _Image:
        def isNull(self):
            return False

    widget = SimpleNamespace(
        image=_Image(),
        label_file=None,
        output_file=None,
        save_file_dialog=lambda: "picked.json",
        _save_file=lambda filename: filename == "picked.json",
    )

    assert LabelingWidget.save_file(widget) is True

    widget._save_file = lambda filename: False
    assert LabelingWidget.save_file(widget) is False
