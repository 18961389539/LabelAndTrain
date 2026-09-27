"""The YOLO export has to say what it did, and what it could not do.

"Exporting annotations successfully!" on its own let a batch that dropped
half its polygons pass for a good run. These tests pin the recap that
replaced it, plus the classes.txt the dialog can drop next to the labels.
"""

import os
import tempfile
import unittest
from types import SimpleNamespace

from anylabeling.views.labeling.utils.export import (
    _format_yolo_export_summary,
    _write_classes_file,
)


def fake_widget():
    """A widget whose translations are the source strings themselves."""
    return SimpleNamespace(tr=lambda text: text)


class TestWriteClassesFile(unittest.TestCase):
    def test_writes_one_class_per_line_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = _write_classes_file(tmp, ["plane", "ship"])

            self.assertEqual(os.path.basename(target), "classes.txt")
            with open(target, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "plane\nship\n")


class TestExportSummary(unittest.TestCase):
    def test_a_clean_run_reports_counts_and_nothing_else(self):
        summary = _format_yolo_export_summary(
            fake_widget(),
            counted_files=3,
            total_files=3,
            stats={"exported": 7},
            copied_images=0,
            classes_target=None,
        )

        self.assertIn("3/3", summary)
        self.assertIn("7", summary)
        self.assertNotIn("跳过", summary)

    def test_skipped_shapes_are_listed_with_their_reason(self):
        summary = _format_yolo_export_summary(
            fake_widget(),
            counted_files=2,
            total_files=2,
            stats={
                "exported": 1,
                "skipped": {
                    "polygon is not part of a hbb export": 4,
                    "label not in classes: dog": 1,
                },
            },
            copied_images=0,
            classes_target=None,
        )

        self.assertIn("跳过 5 个", summary)
        self.assertIn("4 × polygon is not part of a hbb export", summary)
        self.assertIn("1 × label not in classes: dog", summary)

    def test_copied_images_and_classes_file_are_reported(self):
        summary = _format_yolo_export_summary(
            fake_widget(),
            counted_files=1,
            total_files=1,
            stats={"exported": 2},
            copied_images=1,
            classes_target="C:/out/classes.txt",
        )

        self.assertIn("已复制 1 张图片", summary)
        self.assertIn("classes.txt", summary)

    def test_images_without_a_label_file_are_named(self):
        summary = _format_yolo_export_summary(
            fake_widget(),
            counted_files=2,
            total_files=2,
            stats={"exported": 0, "missing_label_file": 2},
            copied_images=0,
            classes_target=None,
        )

        self.assertIn("2", summary)
        self.assertIn("没有标签文件", summary)
