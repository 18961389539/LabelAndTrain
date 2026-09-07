import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@unittest.skipUnless(
    os.environ.get("QT_QPA_PLATFORM") == "offscreen", "requires offscreen Qt"
)
class TestVisibleRowNavigation(unittest.TestCase):
    """Navigation must only ever land on rows the filter did not hide."""

    def _make_widget(self, hidden_rows):
        """Bare label-widget stand-in exposing just the navigation math."""
        class _Item:
            def __init__(self, row):
                self.row = row
                self.hidden = row in hidden_rows

            def isHidden(self):
                return self.hidden

            def text(self):
                return f"img_{self.row:04d}.png"

        class _List:
            def __init__(self, n):
                self.items = [_Item(r) for r in range(n)]

            def count(self):
                return len(self.items)

            def item(self, row):
                return self.items[row]

        list_widget = _List(10)
        widget = type("W", (), {"file_list_widget": list_widget})()
        from anylabeling.views.labeling.label_widget import LabelingWidget as LabelWidget

        # Reuse the real helpers without constructing the whole widget.
        widget._visible_rows = LabelWidget._visible_rows.__get__(widget)
        widget._first_visible_row = LabelWidget._first_visible_row.__get__(
            widget
        )
        widget._next_visible_row = LabelWidget._next_visible_row.__get__(
            widget
        )
        return widget, list_widget

    def test_next_visible_skips_hidden(self):
        w, _ = self._make_widget(hidden_rows={3, 4})
        # row 1 visible -> next visible after it is 2
        self.assertEqual(w._next_visible_row(1, 1), 2)
        # row 2 visible -> next is 5 (3 and 4 are hidden)
        self.assertEqual(w._next_visible_row(2, 1), 5)

    def test_prev_visible_skips_hidden(self):
        w, _ = self._make_widget(hidden_rows={3, 4})
        self.assertEqual(w._next_visible_row(5, -1), 2)

    def test_no_other_visible_returns_minus_one(self):
        w, _ = self._make_widget(hidden_rows={0, 2, 3, 4, 5, 6, 7, 8, 9})
        # Only row 1 visible; asking for the next returns -1 (stop).
        self.assertEqual(w._next_visible_row(1, 1), -1)
        self.assertEqual(w._next_visible_row(1, -1), -1)

    def test_hidden_current_moves_to_nearest_visible(self):
        w, _ = self._make_widget(hidden_rows={3})
        # Current row is hidden; next-direction scan finds row 4 first.
        self.assertEqual(w._next_visible_row(3, 1), 4)
        # Prev-direction scan wraps and finds row 2.
        self.assertEqual(w._next_visible_row(3, -1), 2)

    def test_first_visible_row(self):
        w, _ = self._make_widget(hidden_rows={0, 1, 2})
        self.assertEqual(w._first_visible_row(), 3)

    def test_empty_list(self):
        class _List:
            def count(self):
                return 0

            def item(self, row):
                return None

        widget = type(
            "W", (), {"file_list_widget": _List()}
        )()
        from anylabeling.views.labeling.label_widget import LabelingWidget as LabelWidget

        widget._visible_rows = LabelWidget._visible_rows.__get__(widget)
        widget._first_visible_row = LabelWidget._first_visible_row.__get__(
            widget
        )
        widget._next_visible_row = LabelWidget._next_visible_row.__get__(
            widget
        )
        self.assertEqual(widget._next_visible_row(0, 1), -1)
        self.assertEqual(widget._first_visible_row(), -1)


@unittest.skipUnless(
    os.environ.get("QT_QPA_PLATFORM") == "offscreen", "requires offscreen Qt"
)
class TestAsyncLabelCheck(unittest.TestCase):
    def test_label_file_checked_detection(self):
        import tempfile

        from anylabeling.views.labeling.utils.async_label_check import (
            _label_file_checked,
        )

        with tempfile.TemporaryDirectory() as d:
            checked = os.path.join(d, "a.json")
            unchecked = os.path.join(d, "b.json")
            missing = os.path.join(d, "c.json")
            with open(checked, "w", encoding="utf-8") as f:
                f.write('{"shapes":[],"checked":true}')
            with open(unchecked, "w", encoding="utf-8") as f:
                f.write('{"shapes":[],"checked":false}')
            self.assertTrue(_label_file_checked(checked))
            self.assertFalse(_label_file_checked(unchecked))
            self.assertFalse(_label_file_checked(missing))


if __name__ == "__main__":
    unittest.main()
