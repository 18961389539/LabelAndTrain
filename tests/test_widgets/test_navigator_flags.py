"""The navigator must be able to go behind the canvas."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import QtCore, QtWidgets

_APP = None


def test_navigator_is_not_always_on_top():
    global _APP
    _APP = QtWidgets.QApplication.instance()
    if _APP is None:
        _APP = QtWidgets.QApplication([])
    from jllabeling.views.labeling.widgets.navigator_widget import (
        NavigatorDialog,
    )

    dialog = NavigatorDialog()

    assert not (
        dialog.windowFlags() & QtCore.Qt.WindowType.WindowStaysOnTopHint
    )
    dialog.close()
