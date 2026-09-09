import json
import os
import tempfile
import unittest

from anylabeling.views.labeling.utils.yolo_detect import (
    merge_class_names,
    rename_class_in_classes_txt,
    rename_label_across_folder,
    shapes_to_yolo_detect_text,
    write_yolo_detect_sidecar,
)


class TestYoloDetectSidecar(unittest.TestCase):
    def test_merge_keeps_existing_order_and_appends(self):
        self.assertEqual(
            merge_class_names(["产品", "缺陷"], ["缺陷", "其它"], ["产品"]),
            ["产品", "缺陷", "其它"],
        )

    def test_rectangle_writes_normalized_xywh(self):
        shapes = [
            {
                "label": "产品",
                "shape_type": "rectangle",
                "points": [[10, 10], [30, 10], [30, 30], [10, 30]],
            }
        ]
        text = shapes_to_yolo_detect_text(shapes, 100, 100, ["产品"])
        self.assertEqual(text, "0 0.200000 0.200000 0.200000 0.200000\n")

    def test_empty_shapes_write_empty_txt_and_classes(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "a.json")
            write_yolo_detect_sidecar(
                json_path,
                [],
                100,
                80,
                extra_class_names=["产品"],
            )
            txt_path = os.path.join(tmp, "a.txt")
            classes_path = os.path.join(tmp, "classes.txt")
            with open(txt_path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "")
            with open(classes_path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "产品\n")

    def test_existing_classes_txt_ids_stay_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "a.json")
            classes_path = os.path.join(tmp, "classes.txt")
            with open(classes_path, "w", encoding="utf-8") as handle:
                handle.write("背景\n产品\n")
            write_yolo_detect_sidecar(
                json_path,
                [
                    {
                        "label": "产品",
                        "shape_type": "rectangle",
                        "points": [[0, 0], [50, 0], [50, 40], [0, 40]],
                    }
                ],
                100,
                80,
                extra_class_names=["其它"],
            )
            with open(classes_path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "背景\n产品\n其它\n")
            with open(
                os.path.join(tmp, "a.txt"), "r", encoding="utf-8"
            ) as handle:
                self.assertTrue(handle.read().startswith("1 "))

    def test_skips_autolabel_placeholder_shapes(self):
        text = shapes_to_yolo_detect_text(
            [
                {
                    "label": "AUTOLABEL_OBJECT",
                    "shape_type": "rectangle",
                    "points": [[0, 0], [10, 0], [10, 10], [0, 10]],
                }
            ],
            100,
            100,
            ["产品"],
        )
        self.assertEqual(text, "")


class TestYoloDetectRename(unittest.TestCase):
    def test_rename_keeps_class_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            classes_path = os.path.join(tmp, "classes.txt")
            with open(classes_path, "w", encoding="utf-8") as handle:
                handle.write("背景\n产品\n其它\n")
            names = rename_class_in_classes_txt(classes_path, "产品", "零件")
            self.assertEqual(names, ["背景", "零件", "其它"])
            with open(classes_path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "背景\n零件\n其它\n")

    def test_rename_merge_drops_old_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            classes_path = os.path.join(tmp, "classes.txt")
            with open(classes_path, "w", encoding="utf-8") as handle:
                handle.write("背景\n产品\n其它\n")
            names = rename_class_in_classes_txt(classes_path, "产品", "其它")
            self.assertEqual(names, ["背景", "其它"])

    def test_rename_label_across_folder_rewrites_json_and_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = os.path.join(tmp, "a.json")
            image_path = os.path.join(tmp, "a.jpg")
            with open(json_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "imageWidth": 100,
                        "imageHeight": 80,
                        "shapes": [
                            {
                                "label": "产品",
                                "shape_type": "rectangle",
                                "points": [
                                    [0, 0],
                                    [50, 0],
                                    [50, 40],
                                    [0, 40],
                                ],
                            }
                        ],
                    },
                    handle,
                )
            write_yolo_detect_sidecar(
                json_path,
                [
                    {
                        "label": "产品",
                        "shape_type": "rectangle",
                        "points": [[0, 0], [50, 0], [50, 40], [0, 40]],
                    }
                ],
                100,
                80,
                extra_class_names=["背景", "产品"],
            )
            with open(os.path.join(tmp, "a.txt"), "r", encoding="utf-8") as handle:
                self.assertTrue(handle.read().startswith("1 "))

            changed = rename_label_across_folder(
                [image_path], tmp, "产品", "零件"
            )
            self.assertEqual(changed, 1)
            with open(json_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.assertEqual(data["shapes"][0]["label"], "零件")
            with open(os.path.join(tmp, "classes.txt"), "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "背景\n零件\n")
            with open(os.path.join(tmp, "a.txt"), "r", encoding="utf-8") as handle:
                self.assertTrue(handle.read().startswith("1 "))
