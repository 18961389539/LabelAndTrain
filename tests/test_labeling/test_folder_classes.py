import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from anylabeling.views.labeling.label_widget import (  # noqa: E402
    LabelingWidget as LabelWidget,
)
from anylabeling.views.labeling.widgets.unique_label_qlist_widget import (  # noqa: E402
    UniqueLabelQListWidget,
)


class _Item:
    def __init__(self, label):
        self.label = label

    def data(self, _role):
        return self.label


class _UniqueLabelList:
    """Minimal stand-in for the label panel list widget."""

    def __init__(self, labels=()):
        self.labels = list(labels)

    def count(self):
        return len(self.labels)

    def item(self, row):
        return _Item(self.labels[row])

    def clear(self):
        self.labels = []


class TestLoadClassesFromFolder(unittest.TestCase):
    """classes.txt of the opened folder is authoritative for the panel."""

    def _widget(self, existing_labels=(), output_dir=None):
        widget = type("W", (), {})()
        widget.unique_label_list = _UniqueLabelList(existing_labels)
        widget.output_dir = output_dir
        widget.loaded = []

        def _load_labels(labels, clear_existing=False):
            widget.loaded.extend(labels)
            if clear_existing:
                widget.unique_label_list.clear()
            widget.unique_label_list.labels.extend(labels)

        widget.load_labels = _load_labels
        widget.label_dialog = None
        for name in (
            "_load_classes_from_folder",
            "_panel_label_names",
            "_reset_label_dialog_labels",
        ):
            setattr(
                widget, name, getattr(LabelWidget, name).__get__(widget)
            )
        return widget

    def _write_classes(self, directory, names):
        path = os.path.join(directory, "classes.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("".join(f"{name}\n" for name in names))
        return path

    def test_loads_classes_txt_from_opened_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_classes(tmp, ["bag"])
            widget = self._widget()
            names = widget._load_classes_from_folder(tmp)
            self.assertEqual(names, ["bag"])
            self.assertEqual(widget.unique_label_list.labels, ["bag"])

    def test_previous_folder_labels_are_replaced(self):
        """The reported bug: stale labels from another folder must go away."""
        with tempfile.TemporaryDirectory() as tmp:
            self._write_classes(tmp, ["bag"])
            widget = self._widget(existing_labels=["cat", "dog", "person"])
            widget._load_classes_from_folder(tmp)
            self.assertEqual(widget.unique_label_list.labels, ["bag"])

    def test_same_labels_are_not_reloaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_classes(tmp, ["bag"])
            widget = self._widget(existing_labels=["bag"])
            widget._load_classes_from_folder(tmp)
            self.assertEqual(widget.loaded, [])

    def test_folder_without_classes_txt_leaves_panel_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            widget = self._widget(existing_labels=["configured"])
            self.assertEqual(widget._load_classes_from_folder(tmp), [])
            self.assertEqual(widget.unique_label_list.labels, ["configured"])

    def test_blank_lines_and_duplicates_are_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(
                os.path.join(tmp, "classes.txt"), "w", encoding="utf-8"
            ) as handle:
                handle.write("bag\n\n  box  \nbag\n")
            widget = self._widget()
            self.assertEqual(widget._load_classes_from_folder(tmp), ["bag", "box"])

    def test_output_dir_takes_priority(self):
        with tempfile.TemporaryDirectory() as images, tempfile.TemporaryDirectory() as labels:
            self._write_classes(images, ["from_images"])
            self._write_classes(labels, ["from_output"])
            widget = self._widget(output_dir=labels)
            self.assertEqual(
                widget._load_classes_from_folder(images), ["from_output"]
            )

    def test_falls_back_to_image_dir_when_output_dir_has_none(self):
        with tempfile.TemporaryDirectory() as images, tempfile.TemporaryDirectory() as labels:
            self._write_classes(images, ["from_images"])
            widget = self._widget(output_dir=labels)
            self.assertEqual(
                widget._load_classes_from_folder(images), ["from_images"]
            )

    def test_empty_dir_argument(self):
        widget = self._widget(existing_labels=["keep"])
        self.assertEqual(widget._load_classes_from_folder(""), [])
        self.assertEqual(widget.unique_label_list.labels, ["keep"])

    def test_label_dialog_is_reset(self):
        class _LabelList:
            def __init__(self):
                self.items = ["old_label"]

            def clear(self):
                self.items = []

            def addItems(self, values):
                self.items.extend(values)

        class _Dialog:
            def __init__(self):
                self.label_list = _LabelList()
                self._sort_labels = False

        with tempfile.TemporaryDirectory() as tmp:
            self._write_classes(tmp, ["bag"])
            widget = self._widget()
            widget.label_dialog = _Dialog()
            widget._load_classes_from_folder(tmp)
            self.assertEqual(widget.label_dialog.label_list.items, ["bag"])


class TestLoadLabelsRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_load_labels_does_not_crash_on_first_auto_color_label(self):
        widget = type("W", (), {})()
        widget.unique_label_list = UniqueLabelQListWidget()
        widget._config = {
            "shape_color": "auto",
            "label_colors": None,
            "default_shape_color": [0, 255, 0],
        }
        widget.label_info = {}
        widget._runtime_shape_color_shift = 0
        widget._get_rgb_by_label = LabelWidget._get_rgb_by_label.__get__(widget)
        widget.load_labels = LabelWidget.load_labels.__get__(widget)

        widget.load_labels(["bag"], clear_existing=False)

        self.assertEqual(widget.unique_label_list.count(), 1)
        self.assertEqual(
            widget.unique_label_list.item(0).data(Qt.ItemDataRole.UserRole),
            "bag",
        )


if __name__ == "__main__":
    unittest.main()
