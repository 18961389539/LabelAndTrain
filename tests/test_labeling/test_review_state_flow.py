import json
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtCore, QtGui, QtWidgets

    from anylabeling.views.labeling.label_widget import LabelingWidget
    from anylabeling.views.labeling.utils.async_label_check import (
        _label_file_review_state,
    )

    QT_AVAILABLE = True
except Exception:
    QT_AVAILABLE = False

REVIEW_ROLE = QtCore.Qt.ItemDataRole.UserRole
ANNOTATED_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1
NEGATIVE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 2
LOW_CONF_ROLE = QtCore.Qt.ItemDataRole.UserRole + 3
FILE_REVIEW_ROLE = QtCore.Qt.ItemDataRole.UserRole + 4


def _bind(widget, *names):
    from anylabeling.views.labeling.label_widget import LabelingWidget as LW

    for name in names:
        raw = LW.__dict__.get(name)
        if isinstance(raw, staticmethod):
            setattr(widget, name, raw.__func__)
        else:
            setattr(widget, name, getattr(LW, name).__get__(widget))


def _write_png(path):
    QtGui.QImage(2, 3, QtGui.QImage.Format.Format_RGB32).save(path, "PNG")


class _Item:
    def __init__(self, text):
        self.text_value = text
        self.data_values = {}
        self.hidden = False
        self.icon = None
        self.tooltip = ""

    def text(self):
        return self.text_value

    def data(self, role):
        return self.data_values.get(role)

    def setData(self, role, value):
        self.data_values[role] = value

    def isHidden(self):
        return self.hidden

    def setHidden(self, value):
        self.hidden = bool(value)

    def setIcon(self, icon):
        self.icon = icon

    def setToolTip(self, tip):
        self.tooltip = tip


class _List:
    def __init__(self, items):
        self.items = items

    def count(self):
        return len(self.items)

    def item(self, row):
        return self.items[row]


class _Combo:
    def __init__(self, mode):
        self.mode = mode

    def currentData(self):
        return self.mode


def make_widget(modes=("img_1.png", "img_2.png"), filter_mode="all"):
    items = [_Item(name) for name in modes]

    class Widget:
        def __init__(self):
            self.file_list_widget = _List(items)
            self.file_filter_combo = _Combo(filter_mode)
            self.file_status_icons = {
                "checked": "checked-icon",
                "annotated": "annotated-icon",
                "negative": "negative-icon",
                "rejected": "rejected-icon",
                "unannotated": "unannotated-icon",
            }
            self.progress_calls = 0
            self.output_dir = None
            self.tr = lambda text: text

        def _refresh_file_progress(self):
            self.progress_calls += 1

        def _file_item_has_low_conf(self, item):
            return bool(item.data(LOW_CONF_ROLE))

    widget = Widget()
    _bind(
        widget,
        "_is_confirmed",
        "_set_file_item_review_state",
        "_set_file_item_checked",
        "_refresh_file_item_status_icon",
        "_refresh_file_item_tooltip",
        "_file_item_tooltip",
        "_label_path_for_image",
        "_review_state_name",
        "_file_item_annotation_checked",
        "_apply_file_filter",
    )
    widget._file_sort_key = None
    return widget, items


@unittest.skipUnless(QT_AVAILABLE, "PyQt6 is required")
class TestReviewStateRows(unittest.TestCase):
    def test_rejected_row_is_not_checked_but_has_its_own_icon(self):
        widget, items = make_widget()
        self.assertTrue(
            widget._set_file_item_review_state(items[0], "rejected")
        )
        self.assertEqual(items[0].data(FILE_REVIEW_ROLE), "rejected")
        self.assertIs(items[0].data(REVIEW_ROLE), False)
        self.assertIsNone(items[0].data(NEGATIVE_ROLE))
        self.assertEqual(items[0].icon, "rejected-icon")
        # The row tooltip subsumes what used to be the icon's one-liner: state,
        # meaning of the dot, and the file itself. Asserted on content so the
        # wording can change without breaking a guard that is about coverage.
        self.assertIn("img_1.png", items[0].tooltip)
        self.assertIn("需返工", items[0].tooltip)
        self.assertIn("图标含义", items[0].tooltip)
        self.assertFalse(widget._file_item_annotation_checked(items[0]))

    def test_confirmed_row_keeps_legacy_checked_semantics(self):
        widget, items = make_widget()
        items[1].data_values[ANNOTATED_ROLE] = True
        widget._set_file_item_checked(items[1], True)
        self.assertIs(items[1].data(REVIEW_ROLE), True)
        self.assertEqual(items[1].data(FILE_REVIEW_ROLE), "confirmed")
        self.assertEqual(items[1].icon, "checked-icon")
        self.assertTrue(widget._file_item_annotation_checked(items[1]))

    def test_rework_filter_shows_only_rejected_rows(self):
        widget, items = make_widget(filter_mode="rework")
        widget._set_file_item_review_state(items[0], "rejected")
        widget._set_file_item_review_state(items[1], "confirmed")
        widget._apply_file_filter()
        self.assertFalse(items[0].hidden)
        self.assertTrue(items[1].hidden)
        self.assertEqual(widget.progress_calls, 1)

    def test_checked_filter_still_hides_rejected_rows(self):
        widget, items = make_widget(filter_mode="checked")
        widget._set_file_item_review_state(items[0], "rejected")
        widget._set_file_item_review_state(items[1], "confirmed")
        widget._apply_file_filter()
        self.assertTrue(items[0].hidden)
        self.assertFalse(items[1].hidden)


@unittest.skipUnless(QT_AVAILABLE, "PyQt6 is required")
class TestReviewStatePersistence(unittest.TestCase):
    """The verdict the action records must land on disk in the same shape."""

    def _widget(self, directory, filename):
        from anylabeling.views.labeling.label_file import LabelFile

        class Widget:
            def __init__(self):
                self.filename = filename
                self.image = QtGui.QImage(
                    2, 2, QtGui.QImage.Format.Format_RGB32
                )
                self.other_data = {}
                self.sync_calls = 0
                self.saved_to = None
                self.tr = lambda text: text

            def _sync_annotation_checked_state(self):
                self.sync_calls += 1

            def get_label_file(self):
                return LabelFile()

            def save_labels(self, label_file):
                label_file.save(
                    filename=filename,
                    shapes=[],
                    image_path="img_1.png",
                    image_height=3,
                    image_width=2,
                    image_data=None,
                    other_data=dict(self.other_data),
                )
                self.saved_to = filename
                return True

            def set_clean(self):
                pass

            def _show_save_feedback(self, ok):
                pass

        widget = Widget()
        _bind(widget, "_apply_review_state", "_current_review_state")
        return widget

    def test_reject_writes_state_clears_checked_and_stamps_time(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_png(os.path.join(directory, "img_1.png"))
            filename = os.path.join(directory, "img_1.json")
            widget = self._widget(directory, filename)
            widget._apply_review_state("rejected")

            with open(filename, "r", encoding="utf-8") as stream:
                data = json.load(stream)
            self.assertEqual(data["review_state"], "rejected")
            self.assertIs(data["checked"], False)
            self.assertTrue(data["reviewed_at"])
            self.assertEqual(
                _label_file_review_state(filename), "rejected"
            )
            self.assertEqual(widget._current_review_state(), "rejected")

    def test_confirm_then_uncheck_drops_the_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            _write_png(os.path.join(directory, "img_1.png"))
            filename = os.path.join(directory, "img_1.json")
            widget = self._widget(directory, filename)
            widget._apply_review_state("confirmed")
            with open(filename, "r", encoding="utf-8") as stream:
                data = json.load(stream)
            self.assertIs(data["checked"], True)
            self.assertTrue(data["reviewed_at"])

            widget._apply_review_state("unchecked")
            with open(filename, "r", encoding="utf-8") as stream:
                data = json.load(stream)
            self.assertIsNone(data["reviewed_at"])
            self.assertEqual(data["review_state"], "unchecked")
            self.assertIs(data["checked"], False)


if __name__ == "__main__":
    unittest.main()
