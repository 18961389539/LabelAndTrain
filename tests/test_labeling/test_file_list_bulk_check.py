"""Bulk checking the file list: 全部勾选 / 全部取消勾选 / 反选.

The menu entries only touch rows the filter is showing, and only edit
item data -- the same edit a click makes, nothing written to disk -- so
a wrong one is undone by reopening the folder.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtCore, QtWidgets

    from anylabeling.views.labeling.filelist.roles import (
        FILE_ANNOTATION_ROLE,
    )
    from anylabeling.views.labeling.utils import file_list_ops

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


def _make_item(text, checkable=True, checked=False):
    item = QtWidgets.QListWidgetItem(text)
    flags = QtCore.Qt.ItemFlag.ItemIsEnabled
    if checkable:
        flags |= QtCore.Qt.ItemFlag.ItemIsUserCheckable
    item.setFlags(flags)
    item.setCheckState(
        QtCore.Qt.CheckState.Checked
        if checked
        else QtCore.Qt.CheckState.Unchecked
    )
    return item


class _StubWidget:
    """Just enough widget for the bulk helpers."""

    def __init__(self, items):
        self.file_list_widget = QtWidgets.QListWidget()
        for item in items:
            self.file_list_widget.addItem(item)
        self._syncing_file_item = False
        self.refreshed = 0

    def _refresh_file_item_status_icon(self, item):
        pass

    def _refresh_file_progress(self):
        self.refreshed += 1


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestBulkCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])

    def _widget(self, *states):
        items = [
            _make_item(f"img{index}.jpg", checked=state)
            for index, state in enumerate(states)
        ]
        return _StubWidget(items), items

    def test_all_checks_every_visible_row(self):
        widget, items = self._widget(False, True, False)
        file_list_ops.set_all_items_checked(widget, "all")
        self.assertEqual(
            [item.data(FILE_ANNOTATION_ROLE) for item in items],
            [True, True, True],
        )
        self.assertEqual(widget.refreshed, 1)

    def test_none_clears_every_visible_row(self):
        widget, items = self._widget(True, True, False)
        file_list_ops.set_all_items_checked(widget, "none")
        self.assertEqual(
            [item.checkState() for item in items],
            [QtCore.Qt.CheckState.Unchecked] * 3,
        )

    def test_invert_flips_each_row(self):
        widget, items = self._widget(True, False, True)
        file_list_ops.set_all_items_checked(widget, "invert")
        self.assertEqual(
            [item.data(FILE_ANNOTATION_ROLE) for item in items],
            [False, True, False],
        )

    def test_filtered_out_rows_are_left_alone(self):
        widget, items = self._widget(True, False, True)
        items[1].setHidden(True)
        file_list_ops.set_all_items_checked(widget, "none")
        self.assertFalse(items[0].data(FILE_ANNOTATION_ROLE))
        self.assertIsNone(items[1].data(FILE_ANNOTATION_ROLE))

    def test_rows_without_a_checkbox_are_left_alone(self):
        widget, items = self._widget(True, False, True)
        items[0].setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
        file_list_ops.set_all_items_checked(widget, "invert")
        self.assertIsNone(items[0].data(FILE_ANNOTATION_ROLE))
        self.assertTrue(items[1].data(FILE_ANNOTATION_ROLE))
        self.assertFalse(items[2].data(FILE_ANNOTATION_ROLE))

    def test_the_targets_ignore_hidden_and_uncheckable_rows(self):
        widget, items = self._widget(True, False, True)
        items[1].setHidden(True)
        self.assertEqual(
            file_list_ops._checked_targets(widget), [items[0], items[2]]
        )


if __name__ == "__main__":
    unittest.main()
