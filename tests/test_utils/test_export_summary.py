"""The YOLO export has to say what it did, and what it could not do.

"Exporting annotations successfully!" on its own let a batch that dropped
half its polygons pass for a good run. These tests pin the recap that
replaced it, the classes.txt the dialog can drop next to the labels, and the
review-state filter that keeps 需返工 images out of an export.
"""

import json
import os
import tempfile
import unittest
from types import SimpleNamespace

from anylabeling.views.labeling.utils.export import (
    _format_yolo_export_summary,
    _write_classes_file,
    _write_data_yaml,
    split_images_by_review,
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


class TestWriteDataYaml(unittest.TestCase):
    def test_nc_and_names_match_the_class_list(self):
        import yaml

        with tempfile.TemporaryDirectory() as tmp:
            target = _write_data_yaml(tmp, ["plane", "ship"])

            self.assertEqual(os.path.basename(target), "data.yaml")
            with open(target, "r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle)

            self.assertEqual(data["nc"], 2)
            self.assertEqual(data["names"], ["plane", "ship"])

    def test_train_and_val_are_left_for_the_training_side(self):
        # A guessed path would point at directories that may not exist;
        # only a comment tells the reader what belongs there.
        with tempfile.TemporaryDirectory() as tmp:
            target = _write_data_yaml(tmp, ["plane"])

            with open(target, "r", encoding="utf-8") as handle:
                text = handle.read()

            self.assertNotIn("train:", text.split("#")[0].replace("\n", " "))
            self.assertIn("train: images/train", text)

    def test_summary_names_data_yaml_when_written(self):
        summary = _format_yolo_export_summary(
            fake_widget(),
            counted_files=1,
            total_files=1,
            stats={"exported": 1},
            copied_images=0,
            classes_target="C:/out/classes.txt",
            data_yaml_target="C:/out/data.yaml",
        )

        self.assertIn("classes.txt", summary)
        self.assertIn("data.yaml", summary)


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

    def test_the_record_is_named_only_when_it_was_written(self):
        # The export record is optional; a summary that names a file which is
        # not there would send the reader looking for it.
        written = _format_yolo_export_summary(
            fake_widget(),
            counted_files=1,
            total_files=1,
            stats={"exported": 1},
            copied_images=0,
            classes_target=None,
            manifest_target="C:/out/export_manifest.json",
        )
        skipped = _format_yolo_export_summary(
            fake_widget(),
            counted_files=1,
            total_files=1,
            stats={"exported": 1},
            copied_images=0,
            classes_target=None,
        )

        self.assertIn("export_manifest.json", written)
        self.assertNotIn("export_manifest.json", skipped)

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

    def test_the_review_filter_count_reaches_the_summary(self):
        summary = _format_yolo_export_summary(
            fake_widget(),
            counted_files=2,
            total_files=2,
            stats={"exported": 3},
            copied_images=0,
            classes_target=None,
            skipped_unchecked=7,
        )

        self.assertIn("7", summary)
        self.assertIn("仅导出已确认图片", summary)


class TestReviewStateFilter(unittest.TestCase):
    """需返工 images used to be excluded from training and exported anyway."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _write_label(self, name, review_state=None, checked=None):
        path = os.path.join(self.tmp.name, name)
        data = {"imagePath": name.replace(".json", ".png"), "shapes": []}
        if review_state is not None:
            data["review_state"] = review_state
        if checked is not None:
            data["checked"] = checked
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        return path

    @staticmethod
    def _label_path_for(image_file):
        return image_file.replace(".png", ".json")

    def test_only_confirmed_images_are_kept(self):
        images = [
            os.path.join(self.tmp.name, name)
            for name in ("confirmed.png", "unchecked.png", "rejected.png")
        ]
        self._write_label("confirmed.json", review_state="confirmed")
        self._write_label("unchecked.json", review_state="unchecked")
        self._write_label("rejected.json", review_state="rejected")

        kept, skipped = split_images_by_review(
            images, self._label_path_for, True
        )

        self.assertEqual(
            [os.path.basename(path) for path in kept], ["confirmed.png"]
        )
        self.assertEqual(skipped, 2)

    def test_a_missing_label_file_counts_as_unconfirmed(self):
        images = [os.path.join(self.tmp.name, "nothing.png")]

        kept, skipped = split_images_by_review(
            images, self._label_path_for, True
        )

        self.assertEqual(kept, [])
        self.assertEqual(skipped, 1)

    def test_the_legacy_checked_flag_still_qualifies(self):
        images = [os.path.join(self.tmp.name, "legacy.png")]
        self._write_label("legacy.json", checked=True)

        kept, skipped = split_images_by_review(
            images, self._label_path_for, True
        )

        self.assertEqual(len(kept), 1)
        self.assertEqual(skipped, 0)

    def test_the_filter_is_off_by_default(self):
        images = [os.path.join(self.tmp.name, "anything.png")]

        kept, skipped = split_images_by_review(
            images, self._label_path_for, False
        )

        self.assertEqual(kept, images)
        self.assertEqual(skipped, 0)
