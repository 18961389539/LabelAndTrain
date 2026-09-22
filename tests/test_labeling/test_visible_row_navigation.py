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


class _FakeItem:
    def __init__(self, row, checked_rows=()):
        self.row = row
        self.checked = row in checked_rows

    def isHidden(self):
        return False

    def text(self):
        return f"img_{self.row:04d}.png"

    def data(self, _role):
        return self.checked


class _FakeList:
    def __init__(self, n):
        self.items = [_FakeItem(r) for r in range(n)]

    def set_checked(self, rows):
        for item in self.items:
            item.checked = item.row in rows

    def count(self):
        return len(self.items)

    def item(self, row):
        return self.items[row]


@unittest.skipUnless(
    os.environ.get("QT_QPA_PLATFORM") == "offscreen", "requires offscreen Qt"
)
class TestUncheckedImageNavigation(unittest.TestCase):
    """`image_list` rebuilds the whole list on every access, so the review
    short keys must scan rows through `file_list_widget` alone."""

    N = 2000

    def _make_widget(self, checked_rows=()):
        from anylabeling.views.labeling.label_widget import (
            LabelingWidget as LabelWidget,
        )

        accesses = []
        n = self.N
        list_widget = _FakeList(n)
        list_widget.set_checked(checked_rows)

        class _Widget:
            loaded = []

            def __init__(self):
                self.file_list_widget = list_widget
                self.filename = None
                self.fn_to_index = {f"img_{r:04d}.png": r for r in range(n)}
                self.loaded = []

            @property
            def image_list(self):
                accesses.append(1)
                return [
                    self.file_list_widget.item(i).text()
                    for i in range(self.file_list_widget.count())
                ]

            def may_continue(self, silent=False):
                return True

            def _paging_blocked_by_drawing(self):
                return False

            def load_file(self, filename):
                self.loaded.append(filename)

        widget = _Widget()
        for name in (
            "_file_item_annotation_checked",
            "open_next_unchecked_image",
            "open_prev_unchecked_image",
        ):
            bound = getattr(LabelWidget, name).__get__(widget)
            setattr(widget, name, bound)
        return widget, accesses

    def test_item_text_is_what_image_list_would_return(self):
        widget, accesses = self._make_widget()
        # This equivalence is what lets the scan use `item.text()`.
        for row in (0, 7, self.N - 1):
            self.assertEqual(
                widget.image_list[row],
                widget.file_list_widget.item(row).text(),
            )
        del accesses[:]

    def test_full_forward_scan_touches_image_list_once_at_most(self):
        # Nothing ahead is unchecked: the scan runs to the end of the list.
        widget, accesses = self._make_widget(checked_rows=range(self.N))
        widget.filename = "img_0000.png"
        widget.open_next_unchecked_image()
        self.assertEqual(accesses, [])
        self.assertEqual(widget.loaded, [])

    def test_lands_on_the_next_unchecked_row(self):
        widget, accesses = self._make_widget(checked_rows=range(self.N - 1))
        widget.filename = "img_0000.png"
        widget.open_next_unchecked_image()
        self.assertEqual(widget.loaded, [f"img_{self.N - 1:04d}.png"])
        self.assertEqual(accesses, [])

    def test_lands_on_the_previous_unchecked_row(self):
        widget, accesses = self._make_widget(checked_rows=range(1, self.N))
        widget.filename = f"img_{self.N - 1:04d}.png"
        widget.open_prev_unchecked_image()
        self.assertEqual(widget.loaded, ["img_0000.png"])
        self.assertEqual(accesses, [])


@unittest.skipUnless(
    os.environ.get("QT_QPA_PLATFORM") == "offscreen", "requires offscreen Qt"
)
class TestFileSortKeepsIndexMap(unittest.TestCase):
    """Sorting moves rows, so `fn_to_index` must move with them.

    Every consumer that resolves a path to a row -- the checked dot, the
    status icon, navigation -- reads that map.
    """

    N = 2000

    def _make_widget(self, paths):
        from anylabeling.views.labeling.label_widget import (
            LabelingWidget as LabelWidget,
        )

        class _Item:
            def __init__(self, path):
                self.path = path

            def text(self):
                return self.path

            def isHidden(self):
                return False

        class _List:
            def __init__(self, paths):
                self.items = [_Item(p) for p in paths]

            def count(self):
                return len(self.items)

            def item(self, row):
                if 0 <= row < len(self.items):
                    return self.items[row]
                return None

            def addItem(self, item):
                self.items.append(item)

            def takeItem(self, row):
                return self.items.pop(row)

            def currentItem(self):
                return self.items[0] if self.items else None

            def setCurrentRow(self, _row):
                pass

            def scrollToItem(self, _item):
                pass

        widget = type(
            "W",
            (),
            {
                "_file_sort_mode": "name",
                "fn_to_index": {},
            },
        )()
        widget.file_list_widget = _List(paths)
        widget.fn_to_index = {path: row for row, path in enumerate(paths)}
        for name in ("_file_sort_key", "_apply_file_sort"):
            setattr(widget, name, getattr(LabelWidget, name).__get__(widget))
        return widget

    def test_sort_reindexes_every_path(self):
        paths = ["/d/img_9.png", "/d/img_1.png", "/d/img_5.png"]
        widget = self._make_widget(paths)
        widget._apply_file_sort()

        rows = [
            widget.file_list_widget.item(r).text()
            for r in range(widget.file_list_widget.count())
        ]
        self.assertEqual(
            rows, ["/d/img_1.png", "/d/img_5.png", "/d/img_9.png"]
        )
        for row, path in enumerate(rows):
            self.assertEqual(widget.fn_to_index[path], row)

    def test_map_stays_consistent_for_a_longer_list(self):
        paths = [f"/d/img_{(i * 7) % 50:03d}.png" for i in range(50)]
        widget = self._make_widget(paths)
        widget._apply_file_sort()
        for row in range(widget.file_list_widget.count()):
            path = widget.file_list_widget.item(row).text()
            self.assertEqual(widget.fn_to_index[path], row)


if __name__ == "__main__":
    unittest.main()
