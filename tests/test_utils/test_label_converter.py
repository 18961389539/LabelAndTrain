import json
import os
import tempfile
import unittest
from unittest import mock

import yaml

from anylabeling.views.labeling.label_converter import LabelConverter


class TestLabelConverterPoseConfig(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _write_pose_cfg(self, data):
        cfg_path = os.path.join(self.temp_dir, "pose.yaml")
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)
        return cfg_path

    def test_missing_has_visible_defaults_to_true(self):
        cfg_path = self._write_pose_cfg(
            {"classes": {"person": ["nose", "left_eye"]}}
        )

        converter = LabelConverter(pose_cfg_file=cfg_path)

        self.assertTrue(converter.has_visible)
        self.assertEqual(converter.classes, ["person"])

    def test_explicit_has_visible_false_is_respected(self):
        cfg_path = self._write_pose_cfg(
            {
                "has_visible": False,
                "classes": {"person": ["nose", "left_eye"]},
            }
        )

        converter = LabelConverter(pose_cfg_file=cfg_path)

        self.assertFalse(converter.has_visible)

    def test_missing_classes_raises_value_error(self):
        cfg_path = self._write_pose_cfg({"has_visible": True})

        with self.assertRaises(ValueError):
            LabelConverter(pose_cfg_file=cfg_path)


class TestLabelConverterObbBounds(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.classes_file = os.path.join(self.temp_dir, "classes.txt")
        with open(self.classes_file, "w", encoding="utf-8") as f:
            f.write("plane\n")
        self.converter = LabelConverter(classes_file=self.classes_file)

    def tearDown(self):
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _write_label_file(self, points):
        label_file = os.path.join(self.temp_dir, "label.json")
        data = {
            "imagePath": "image.jpg",
            "imageWidth": 100,
            "imageHeight": 50,
            "shapes": [
                {
                    "label": "plane",
                    "shape_type": "rotation",
                    "points": points,
                }
            ],
        }
        with open(label_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return label_file

    def test_yolo_obb_skips_rotation_shape_with_any_out_of_bounds_point(self):
        label_file = self._write_label_file(
            [[-1, 10], [20, 10], [20, 20], [10, 20]]
        )
        output_file = os.path.join(self.temp_dir, "label.txt")

        self.converter.custom_to_yolo(label_file, output_file, "obb")

        with open(output_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "")


class TestLabelConverterYoloExportStats(unittest.TestCase):
    """A skipped shape used to vanish without a trace.

    ``stats`` is the out-parameter the export dialog reads to tell the
    annotator what was dropped, so the counters have to be exact.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.classes_file = os.path.join(self.temp_dir, "classes.txt")
        with open(self.classes_file, "w", encoding="utf-8") as f:
            f.write("plane\nship\n")
        self.converter = LabelConverter(classes_file=self.classes_file)

    def tearDown(self):
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def _write_label_file(self, shapes):
        label_file = os.path.join(self.temp_dir, "label.json")
        data = {
            "imagePath": "image.jpg",
            "imageWidth": 100,
            "imageHeight": 50,
            "shapes": shapes,
        }
        with open(label_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return label_file

    @staticmethod
    def _rectangle(label, points=None):
        return {
            "label": label,
            "shape_type": "rectangle",
            "points": points or [[0, 0], [10, 0], [10, 10], [0, 10]],
        }

    def test_explicit_classes_list_is_used_instead_of_a_file(self):
        converter = LabelConverter(classes=["a", "b"])

        self.assertEqual(converter.classes, ["a", "b"])

    def test_counters_name_every_reason_a_shape_was_dropped(self):
        label_file = self._write_label_file(
            [
                self._rectangle("plane"),
                self._rectangle("dog"),
                {
                    "label": "plane",
                    "shape_type": "polygon",
                    "points": [[0, 0], [10, 0], [10, 10]],
                },
            ]
        )
        stats = {}

        self.converter.custom_to_yolo(
            label_file,
            os.path.join(self.temp_dir, "label.txt"),
            "hbb",
            stats=stats,
        )

        self.assertEqual(stats["exported"], 1)
        self.assertEqual(
            stats["skipped"],
            {
                "label not in classes: dog": 1,
                "polygon is not part of a hbb export": 1,
            },
        )

    def test_a_clean_export_reports_no_skips(self):
        label_file = self._write_label_file(
            [self._rectangle("plane"), self._rectangle("ship")]
        )
        stats = {}

        self.converter.custom_to_yolo(
            label_file,
            os.path.join(self.temp_dir, "label.txt"),
            "hbb",
            stats=stats,
        )

        self.assertEqual(stats.get("exported"), 2)
        self.assertNotIn("skipped", stats)

    def test_missing_label_file_is_counted(self):
        stats = {}

        self.converter.custom_to_yolo(
            os.path.join(self.temp_dir, "nope.json"),
            os.path.join(self.temp_dir, "nope.txt"),
            "hbb",
            stats=stats,
        )

        self.assertEqual(stats["missing_label_file"], 1)

    def test_obb_counts_the_shapes_it_leaves_out_of_bounds(self):
        label_file = self._write_label_file(
            [
                {
                    "label": "plane",
                    "shape_type": "rotation",
                    "points": [[0, 0], [10, 0], [10, 10], [0, 10]],
                },
                {
                    "label": "plane",
                    "shape_type": "rotation",
                    "points": [[-5, 0], [10, 0], [10, 10], [0, 10]],
                },
            ]
        )
        stats = {}

        self.converter.custom_to_yolo(
            label_file,
            os.path.join(self.temp_dir, "label.txt"),
            "obb",
            stats=stats,
        )

        self.assertEqual(stats["exported"], 1)
        self.assertEqual(
            stats["skipped"], {"rotation reaching outside the image": 1}
        )

    def test_without_a_stats_sink_nothing_changes(self):
        # The CLI calls this the old way; the return value must stay a bool.
        label_file = self._write_label_file([self._rectangle("plane")])

        is_empty = self.converter.custom_to_yolo(
            label_file, os.path.join(self.temp_dir, "label.txt"), "hbb"
        )

        self.assertFalse(is_empty)


class TestLabelConverterVocValidation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.converter = LabelConverter()
        self.input_file = os.path.join(self.temp_dir.name, "input.xml")
        self.output_file = os.path.join(self.temp_dir.name, "output.json")

    def _convert(self, objects, mode="rectangle"):
        xml = (
            "<annotation><filename>image.jpg</filename>"
            "<size><width>100</width><height>50</height></size>"
            f"{objects}</annotation>"
        )
        with open(self.input_file, "w", encoding="utf-8") as f:
            f.write(xml)
        self.converter.voc_to_custom(
            self.input_file, self.output_file, "image.jpg", mode
        )
        with open(self.output_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_missing_geometry_is_skipped(self):
        objects = (
            "<object><name>missing</name></object>"
            "<object><name>valid</name><bndbox>"
            "<xmin>1</xmin><ymin>2</ymin><xmax>3</xmax><ymax>4</ymax>"
            "</bndbox></object>"
        )

        with mock.patch(
            "anylabeling.views.labeling.label_converter.logger.warning"
        ) as warning:
            data = self._convert(objects)

        self.assertEqual(
            [shape["label"] for shape in data["shapes"]], ["valid"]
        )
        warning.assert_called_once()
        self.assertIn("VOC object 1", warning.call_args.args[0])
        self.assertIn(self.input_file, warning.call_args.args[0])

    def test_incomplete_geometry_is_skipped(self):
        objects = (
            "<object><name>incomplete</name><bndbox>"
            "<xmin>1</xmin><ymin>2</ymin><xmax>3</xmax>"
            "</bndbox></object>"
        )

        with mock.patch(
            "anylabeling.views.labeling.label_converter.logger.warning"
        ) as warning:
            data = self._convert(objects)

        self.assertEqual(data["shapes"], [])
        warning.assert_called_once()
        self.assertIn("bndbox/ymax", warning.call_args.args[0])
