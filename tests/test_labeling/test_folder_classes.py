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
            setattr(widget, name, getattr(LabelWidget, name).__get__(widget))
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

    def test_folder_without_classes_txt_falls_back_to_the_config(self):
        """Stale labels go, the configured ones keep working."""
        with tempfile.TemporaryDirectory() as tmp:
            widget = self._widget(existing_labels=["stale", "configured"])
            widget._config = {"labels": ["configured"]}
            self.assertEqual(widget._load_classes_from_folder(tmp), [])
            self.assertEqual(widget.unique_label_list.labels, ["configured"])

    def test_folder_without_classes_txt_clears_when_nothing_is_configured(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            widget = self._widget(existing_labels=["stale"])
            widget._config = {"labels": []}
            self.assertEqual(widget._load_classes_from_folder(tmp), [])
            self.assertEqual(widget.unique_label_list.labels, [])

    def test_blank_lines_and_duplicates_are_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(
                os.path.join(tmp, "classes.txt"), "w", encoding="utf-8"
            ) as handle:
                handle.write("bag\n\n  box  \nbag\n")
            widget = self._widget()
            self.assertEqual(
                widget._load_classes_from_folder(tmp), ["bag", "box"]
            )

    def test_output_dir_takes_priority(self):
        with (
            tempfile.TemporaryDirectory() as images,
            tempfile.TemporaryDirectory() as labels,
        ):
            self._write_classes(images, ["from_images"])
            self._write_classes(labels, ["from_output"])
            widget = self._widget(output_dir=labels)
            self.assertEqual(
                widget._load_classes_from_folder(images), ["from_output"]
            )

    def test_falls_back_to_image_dir_when_output_dir_has_none(self):
        with (
            tempfile.TemporaryDirectory() as images,
            tempfile.TemporaryDirectory() as labels,
        ):
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

    def test_the_project_record_wins_over_classes_txt(self):
        """单源化：记录里有标签后，classes.txt 退化为不再被读的种子。"""
        from anylabeling.views.labeling import project_model

        with tempfile.TemporaryDirectory() as tmp:
            self._write_classes(tmp, ["from_classes_txt"])
            assert project_model.create(
                tmp, task="Detect", labels=["from_record", "added"]
            )
            widget = self._widget()
            self.assertEqual(
                widget._load_classes_from_folder(tmp),
                ["from_record", "added"],
            )
            self.assertEqual(
                widget.unique_label_list.labels,
                ["from_record", "added"],
            )

    def test_a_record_classes_txt_mismatch_says_so(self):
        from anylabeling.views.labeling import project_model

        with tempfile.TemporaryDirectory() as tmp:
            self._write_classes(tmp, ["stale", "classes"])
            assert project_model.create(
                tmp, task="Detect", labels=["live", "labels"]
            )
            widget = self._widget()
            widget.messages = []
            widget.tr = lambda text: text
            widget.status = lambda text, _ms=0: widget.messages.append(text)
            self.assertEqual(
                widget._load_classes_from_folder(tmp), ["live", "labels"]
            )
            # 记录仍然赢，但"classes.txt 没生效"不再是沉默的。
            self.assertTrue(
                any("不一致" in message for message in widget.messages)
            )

    def test_a_matching_classes_txt_says_nothing(self):
        from anylabeling.views.labeling import project_model

        with tempfile.TemporaryDirectory() as tmp:
            self._write_classes(tmp, ["bag"])
            assert project_model.create(tmp, task="Detect", labels=["bag"])
            widget = self._widget()
            widget.messages = []
            widget.status = lambda text, _ms=0: widget.messages.append(text)
            self.assertEqual(widget._load_classes_from_folder(tmp), ["bag"])
            self.assertEqual(widget.messages, [])


class TestResolveOpenLabels:
    """解析本身只读：打开一个数据集不写盘（离开时的 flush 才写）。"""

    def test_seeding_from_classes_txt_writes_nothing(self, tmp_path):
        from anylabeling.views.labeling import (
            project_model,
            project_settings,
        )

        (tmp_path / "classes.txt").write_text("bag\n", encoding="utf-8")
        resolution = project_settings.resolve_open_labels(
            str(tmp_path), (str(tmp_path),)
        )
        assert resolution == {
            "names": ["bag"],
            "source": "classes.txt",
            "conflict": False,
        }
        assert not project_model.has_record(str(tmp_path))

    def test_the_record_beats_the_seed(self, tmp_path):
        from anylabeling.views.labeling import (
            project_model,
            project_settings,
        )

        (tmp_path / "classes.txt").write_text("stale\n", encoding="utf-8")
        assert project_model.create(str(tmp_path), labels=["live"])
        resolution = project_settings.resolve_open_labels(
            str(tmp_path), (str(tmp_path),)
        )
        assert resolution["source"] == "record"
        assert resolution["conflict"] is True
        assert resolution["names"] == ["live"]

    def test_nothing_to_read(self, tmp_path):
        from anylabeling.views.labeling import project_settings

        resolution = project_settings.resolve_open_labels(
            str(tmp_path), (None, str(tmp_path))
        )
        assert resolution == {
            "names": [],
            "source": "none",
            "conflict": False,
        }


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
        widget._get_rgb_by_label = LabelWidget._get_rgb_by_label.__get__(
            widget
        )
        widget.load_labels = LabelWidget.load_labels.__get__(widget)

        widget.load_labels(["bag"], clear_existing=False)

        self.assertEqual(widget.unique_label_list.count(), 1)
        self.assertEqual(
            widget.unique_label_list.item(0).data(Qt.ItemDataRole.UserRole),
            "bag",
        )


if __name__ == "__main__":
    unittest.main()
