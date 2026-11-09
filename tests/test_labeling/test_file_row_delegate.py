"""File rows paint the name first; navigation still reads the full path."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import QtCore, QtWidgets

from jllabeling.views.labeling.filelist.items import FileRowDisplayDelegate


def test_display_text_is_name_then_folder():
    delegate = FileRowDisplayDelegate()
    shown = delegate.displayText(
        os.path.join(os.sep, "datasets", "plates", "photo.png"),
        QtCore.QLocale(),
    )
    assert shown == "photo.png  ·  plates"


def test_item_text_stays_the_full_path_for_navigation():
    app = QtWidgets.QApplication.instance()
    if app is None:
        QtWidgets.QApplication([])

    path = os.path.join(os.sep, "datasets", "plates", "photo.png")
    item = QtWidgets.QListWidgetItem(path)
    delegate = FileRowDisplayDelegate()
    delegate.displayText(item.text(), QtCore.QLocale())

    assert item.text() == path
