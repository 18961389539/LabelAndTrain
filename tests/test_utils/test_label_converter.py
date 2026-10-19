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

    def test_yolo_obb_clamp_pulls_vertices_to_the_image_edge(self):
        label_file = self._write_label_file(
            [[-10, 10], [20, 10], [20, 20], [10, -5]]
        )
        output_file = os.path.join(self.temp_dir, "label.txt")

        self.converter.custom_to_yolo(
            label_file, output_file, "obb", obb_boundary_policy="clamp"
        )

        with open(output_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "0 0.0 0.2 0.2 0.2 0.2 0.4 0.1 0.0\n")

    def test_yolo_obb_clamp_skips_a_box_that_collapses_to_nothing(self):
        # Every vertex is outside the same corner, so clamping makes them
        # coincide; a zero-area rotation is not a training sample.
        label_file = self._write_label_file(
            [[-9, -9], [-3, -9], [-3, -3], [-9, -3]]
        )
        output_file = os.path.join(self.temp_dir, "label.txt")
        stats = {}

        self.converter.custom_to_yolo(
            label_file,
            output_file,
            "obb",
            obb_boundary_policy="clamp",
            stats=stats,
        )

        with open(output_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "")
        self.assertEqual(
            stats["skipped"],
            {"rotation collapsed after clamping": 1},
        )

    def test_an_unknown_obb_policy_behaves_like_skip(self):
        # A typo must not silently export coordinates outside [0, 1].
        label_file = self._write_label_file(
            [[-1, 10], [20, 10], [20, 20], [10, 20]]
        )
        output_file = os.path.join(self.temp_dir, "label.txt")

        self.converter.custom_to_yolo(
            label_file, output_file, "obb", obb_boundary_policy="clmap"
        )

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


class TestYoloExportLines(unittest.TestCase):
    """Pin the bytes of the exported .txt, not just the skip counters.

    Ultralytics trains on exactly this file, so a class index taken from the
    wrong order, a swapped centre/width pair or a changed decimal format is a
    silent dataset corruption. The stats tests above count shapes; these read
    the file back and compare whole lines.
    """

    def setUp(self):
        import shutil

        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def _convert(self, classes, shapes, mode, pose_cfg=None):
        label_file = os.path.join(self.dir, "label.json")
        with open(label_file, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "imagePath": "image.jpg",
                    "imageWidth": 100,
                    "imageHeight": 50,
                    "shapes": shapes,
                },
                handle,
            )
        output_file = os.path.join(self.dir, "label.txt")
        converter = (
            LabelConverter(pose_cfg_file=pose_cfg)
            if pose_cfg
            else LabelConverter(classes=classes)
        )
        converter.custom_to_yolo(label_file, output_file, mode)
        with open(output_file, encoding="utf-8") as handle:
            return handle.read()

    @staticmethod
    def _rectangle(label, points):
        return {
            "label": label,
            "shape_type": "rectangle",
            "points": points,
        }

    def test_hbb_lines_carry_the_class_index_in_classes_order(self):
        text = self._convert(
            ["ship", "plane"],
            [
                self._rectangle(
                    "plane", [[10, 20], [30, 20], [30, 40], [10, 40]]
                ),
                self._rectangle("ship", [[0, 0], [10, 0], [10, 10], [0, 10]]),
            ],
            "hbb",
        )

        self.assertEqual(
            text,
            "1 0.200000 0.600000 0.200000 0.400000\n"
            "0 0.050000 0.100000 0.100000 0.200000\n",
        )

    def test_a_two_point_diagonal_still_exports_a_four_corner_box(self):
        text = self._convert(
            ["plane"],
            [self._rectangle("plane", [[10, 20], [30, 40]])],
            "hbb",
        )

        self.assertEqual(text, "0 0.200000 0.600000 0.200000 0.400000\n")

    def test_a_skipped_shape_leaves_no_partial_line(self):
        text = self._convert(
            ["plane"],
            [
                self._rectangle(
                    "plane", [[10, 20], [30, 20], [30, 40], [10, 40]]
                ),
                self._rectangle("dog", [[0, 0], [10, 0], [10, 10], [0, 10]]),
            ],
            "hbb",
        )

        self.assertEqual(text, "0 0.200000 0.600000 0.200000 0.400000\n")

    def test_seg_lines_are_normalised_vertex_pairs(self):
        text = self._convert(
            ["plane"],
            [
                {
                    "label": "plane",
                    "shape_type": "polygon",
                    "points": [[0, 0], [50, 0], [50, 25]],
                }
            ],
            "seg",
        )

        self.assertEqual(text, "0 0.0 0.0 0.5 0.0 0.5 0.5\n")

    def test_obb_lines_keep_vertex_order(self):
        text = self._convert(
            ["plane"],
            [
                {
                    "label": "plane",
                    "shape_type": "rotation",
                    "points": [[10, 5], [20, 5], [20, 15], [10, 15]],
                }
            ],
            "obb",
        )

        self.assertEqual(text, "0 0.1 0.1 0.2 0.1 0.2 0.3 0.1 0.3\n")

    def test_pose_lines_pad_missing_keypoints_in_declared_order(self):
        pose_cfg = os.path.join(self.dir, "pose.yaml")
        with open(pose_cfg, "w", encoding="utf-8") as handle:
            yaml.safe_dump(
                {
                    "classes": {
                        "person": ["nose", "left_eye"],
                        "dog": ["tail"],
                    }
                },
                handle,
                sort_keys=False,
            )

        text = self._convert(
            None,
            [
                {
                    "label": "person",
                    "shape_type": "rectangle",
                    "group_id": 1,
                    "points": [[10, 10], [30, 10], [30, 30], [10, 30]],
                },
                {
                    "label": "nose",
                    "shape_type": "point",
                    "group_id": 1,
                    "points": [[25, 10]],
                },
            ],
            "pose",
            pose_cfg=pose_cfg,
        )

        # Box, then nose (visible), then left_eye padded as absent.
        self.assertEqual(text, "0 0.2 0.4 0.2 0.4 0.25 0.2 2 0 0 0\n")


class TestCocoExportContent(unittest.TestCase):
    """The COCO json is consumed by training and review tools; pin its facts.

    Shape ids, category ids, pixel bboxes and instance grouping were covered
    only by "the aggregate file exists" -- a wrong id mapping or a swapped
    width/height passes that.
    """

    def setUp(self):
        self.holder = tempfile.TemporaryDirectory()
        self.dir = self.holder.name
        self.addCleanup(self.holder.cleanup)
        self.images = os.path.join(self.dir, "images")
        self.out = os.path.join(self.dir, "out")
        os.makedirs(self.images)
        os.makedirs(self.out)

    def _image(self, shapes, width=100, height=50):
        from PIL import Image

        Image.new("RGB", (width, height), "gray").save(
            os.path.join(self.images, "a.png")
        )
        with open(
            os.path.join(self.images, "a.json"), "w", encoding="utf-8"
        ) as handle:
            json.dump(
                {
                    "version": "2.4.0",
                    "flags": {},
                    "shapes": shapes,
                    "imagePath": "a.png",
                    "imageData": None,
                    "imageHeight": height,
                    "imageWidth": width,
                },
                handle,
            )
        return os.path.join(self.images, "a.png")

    def _export(self, converter, image, mode, name):
        converter.custom_to_coco([image], self.images, self.out, mode)
        with open(os.path.join(self.out, name), encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _rectangle(label, points, difficult=False, group_id=None):
        return {
            "label": label,
            "shape_type": "rectangle",
            "points": points,
            "group_id": group_id,
            "difficult": difficult,
            "flags": {},
        }

    def test_rectangle_annotations_carry_category_ids_pixels_and_order(self):
        image = self._image(
            [
                self._rectangle(
                    "dog", [[10, 20], [30, 20], [30, 40], [10, 40]]
                ),
                self._rectangle("zebra", [[0, 0], [1, 0], [1, 1], [0, 1]]),
                self._rectangle("cat", [[0, 0], [10, 0], [10, 10], [0, 10]]),
            ]
        )

        data = self._export(
            LabelConverter(classes=["cat", "dog"]),
            image,
            "rectangle",
            "coco_detection.json",
        )

        self.assertEqual(
            [c["name"] for c in data["categories"]], ["cat", "dog"]
        )
        self.assertEqual(
            [
                (i["file_name"], i["width"], i["height"], i["id"])
                for i in data["images"]
            ],
            [("a.png", 100, 50, 0)],
        )
        self.assertEqual(
            [
                (
                    a["id"],
                    a["image_id"],
                    a["category_id"],
                    a["bbox"],
                    a["area"],
                )
                for a in data["annotations"]
            ],
            [
                (0, 0, 2, [10, 20, 20, 20], 400),
                (1, 0, 1, [0, 0, 10, 10], 100),
            ],
        )

    def test_polygon_instances_group_and_keep_their_vertices(self):
        cat_a = {
            "label": "cat",
            "shape_type": "polygon",
            "group_id": 1,
            "points": [[10, 10], [30, 10], [30, 30]],
            "flags": {},
        }
        cat_b = dict(cat_a, points=[[10, 10], [10, 30], [30, 30]])
        dog = {
            "label": "dog",
            "shape_type": "polygon",
            "group_id": 2,
            "points": [[50, 10], [60, 10], [60, 20]],
            "flags": {},
        }
        lone = dict(
            cat_a, group_id=None, points=[[70, 10], [80, 10], [80, 20]]
        )
        image = self._image([cat_a, cat_b, dog, lone])

        data = self._export(
            LabelConverter(classes=["cat", "dog"]),
            image,
            "polygon",
            "coco_instance_segmentation.json",
        )

        self.assertEqual(
            [(c["id"], c["name"]) for c in data["categories"]],
            [(0, "_background_"), (1, "cat"), (2, "dog")],
        )
        self.assertEqual(
            [a["category_id"] for a in data["annotations"]], [1, 2, 1]
        )
        grouped = data["annotations"][0]
        self.assertEqual(
            grouped["segmentation"],
            [
                [10, 10, 30, 10, 30, 30],
                [10, 10, 10, 30, 30, 30],
            ],
        )
        # pycocotools' inclusive pixel grid: x_max - x_min + 1, as floats.
        self.assertEqual(grouped["bbox"], [10.0, 10.0, 21.0, 21.0])
        self.assertGreater(grouped["area"], 0)

    def test_pose_ignore_belongs_to_its_own_box(self):
        """It used to be whatever the last shape in the file carried."""
        cfg = os.path.join(self.dir, "pose.yaml")
        with open(cfg, "w", encoding="utf-8") as handle:
            yaml.safe_dump(
                {"classes": {"person": ["nose"]}},
                handle,
                sort_keys=False,
            )
        image = self._image(
            [
                self._rectangle(
                    "person",
                    [[10, 10], [30, 10], [30, 30], [10, 30]],
                    difficult=True,
                    group_id=1,
                ),
                {
                    "label": "nose",
                    "shape_type": "point",
                    "group_id": 1,
                    "points": [[20, 20]],
                    "difficult": False,
                    "flags": {},
                },
                self._rectangle(
                    "person",
                    [[40, 10], [60, 10], [60, 30], [40, 30]],
                    group_id=2,
                ),
                {
                    "label": "nose",
                    "shape_type": "point",
                    "group_id": 2,
                    "points": [[50, 20]],
                    "difficult": False,
                    "flags": {},
                },
            ]
        )

        data = self._export(
            LabelConverter(pose_cfg_file=cfg),
            image,
            "pose",
            "coco_keypoints.json",
        )

        annotations = data["annotations"]
        self.assertEqual([a["ignore"] for a in annotations], [1, 0])
        self.assertEqual(
            [a["bbox"] for a in annotations],
            [[10, 10, 20, 20], [40, 10, 20, 20]],
        )
        self.assertEqual(
            [a["keypoints"] for a in annotations],
            [[20, 20, 2], [50, 20, 2]],
        )
        self.assertEqual([a["num_keypoints"] for a in annotations], [1, 1])
