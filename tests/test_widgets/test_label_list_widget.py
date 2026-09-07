import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets

    PYQT_AVAILABLE = True
except Exception:  # pragma: no cover
    PYQT_AVAILABLE = False

from anylabeling.views.labeling.widgets.label_list_widget import (
    LabelListWidget,
    LabelListWidgetItem,
)


@unittest.skipUnless(
    PYQT_AVAILABLE, "PyQt6 is required for label list widget tests"
)
class TestLabelListWidget(unittest.TestCase):
    """Guards against duplicate-connection accumulation.

    Regression: connections used to be created inside paintEvent, so every
    repaint added another handler for selectionChanged/doubleClicked. After
    enough repaints a single selection change fired tens of thousands of
    handlers and the UI froze (loop select / loop through labels buttons).
    """

    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        self.widgets = []

    def tearDown(self):
        for widget in self.widgets:
            widget.close()
        self.app.processEvents()

    def _make_list(self, count=20):
        lst = LabelListWidget()
        lst.resize(200, 300)
        lst.show()
        self.widgets.append(lst)
        for i in range(count):
            lst.add_iem(LabelListWidgetItem(f"label-{i}", None))
        self.app.processEvents()
        return lst

    def test_handler_count_stays_flat_across_many_repaints(self):
        lst = self._make_list()

        events = []
        lst.item_selection_changed.connect(
            lambda selected, deselected: events.append(1)
        )

        def select_once():
            del events[:]
            lst.clearSelection()
            lst.select_item(lst[0])
            self.app.processEvents()
            return len(events)

        # paintEvent used to connect() once per paint -> unbounded growth.
        for _ in range(500):
            lst.viewport().repaint()
            self.app.processEvents()

        # Pre-select so both clearSelection and select_item emit changes.
        lst.select_item(lst[0])
        self.app.processEvents()

        first = select_once()
        second = select_once()
        self.assertEqual(first, 2)  # clearSelection + select_item
        self.assertEqual(second, 2)  # stable, no accumulation

    def test_selection_signal_payloads(self):
        lst = self._make_list(3)
        a, b, c = lst[0], lst[1], lst[2]

        seen = []
        lst.item_selection_changed.connect(
            lambda selected, deselected: seen.append(
                (selected, deselected)
            )
        )

        lst.clearSelection()
        lst.select_item(b)
        self.app.processEvents()

        self.assertTrue(any(len(sel) == 1 for sel, _ in seen))
        self.assertTrue(any(b in sel for sel, _ in seen))

    def test_placeholder_painting_keeps_working(self):
        # Empty list paint must not crash and must leave the list functional.
        lst = LabelListWidget()
        lst.resize(200, 300)
        lst.show()
        self.widgets.append(lst)
        self.app.processEvents()
        lst.add_iem(LabelListWidgetItem("x", None))
        self.app.processEvents()
        self.assertEqual(len(lst), 1)


if __name__ == "__main__":
    unittest.main()
