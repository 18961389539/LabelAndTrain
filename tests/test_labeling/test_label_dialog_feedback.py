"""An empty label says so instead of silently doing nothing."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


_APP = None


def _dialog():
    global _APP
    from PyQt6 import QtWidgets

    _APP = QtWidgets.QApplication.instance()
    if _APP is None:
        _APP = QtWidgets.QApplication([])
    from jllabeling.views.labeling.widgets.label_dialog import LabelDialog

    return LabelDialog(labels=["cat"])


def test_empty_label_shows_an_inline_error_and_stays_open():
    dialog = _dialog()
    dialog.validate()

    assert dialog.result() == 0
    assert not dialog._edit_error.isHidden()
    assert dialog._edit_error.text() == "标签不能为空"


def test_typing_a_label_clears_the_error_and_accepts():
    dialog = _dialog()
    dialog.validate()
    dialog.edit.setText("dog")

    assert dialog._edit_error.isHidden()
    dialog.validate()
    assert dialog.result() == 1
