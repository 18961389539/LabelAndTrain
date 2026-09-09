import json
import os
import tempfile
import unittest

from anylabeling.views.labeling.utils.quality import (
    file_needs_re_autolabel,
    format_save_quality_status,
    inspect_shape_quality,
    json_txt_mismatch,
    shapes_have_low_confidence,
)
from anylabeling.views.labeling.utils.yolo_detect import write_yolo_detect_sidecar


def _box(label, points, score=None):
    shape = {
        "label": label,
        "shape_type": "rectangle",
        "points": points,
    }
    if score is not None:
        shape["score"] = score
    return shape


class TestQualityChecks(unittest.TestCase):
    def test_tiny_and_edge_boxes(self):
        stats = inspect_shape_quality(
            [
                _box("a", [[0, 0], [1, 0], [1, 1], [0, 1]]),
                _box("b", [[20, 20], [40, 20], [40, 40], [20, 40]]),
            ],
            100,
            100,
        )
        self.assertEqual(stats["tiny"], 1)
        self.assertEqual(stats["edge"], 1)
        self.assertEqual(
            format_save_quality_status(stats),
            "注意：1 个极小框，1 个贴边框",
        )

    def test_low_confidence_range(self):
        self.assertTrue(
            shapes_have_low_confidence([_box("a", [[0, 0], [10, 10]], 0.3)])
        )
        self.assertFalse(
            shapes_have_low_confidence([_box("a", [[0, 0], [10, 10]], 0.9)])
        )
        self.assertFalse(
            shapes_have_low_confidence([_box("a", [[0, 0], [10, 10]])])
        )

    def test_json_txt_mismatch_and_re_autolabel(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = os.path.join(tmp, "a.jpg")
            json_path = os.path.join(tmp, "a.json")
            open(image, "wb").close()
            shapes = [
                _box("产品", [[0, 0], [50, 0], [50, 40], [0, 40]], 0.32)
            ]
            with open(json_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "imageWidth": 100,
                        "imageHeight": 80,
                        "shapes": shapes,
                    },
                    handle,
                )
            self.assertTrue(json_txt_mismatch(json_path))
            write_yolo_detect_sidecar(
                json_path, shapes, 100, 80, extra_class_names=["产品"]
            )
            self.assertFalse(json_txt_mismatch(json_path))
            self.assertTrue(file_needs_re_autolabel(image))

            empty_image = os.path.join(tmp, "b.jpg")
            open(empty_image, "wb").close()
            with open(
                os.path.join(tmp, "b.json"), "w", encoding="utf-8"
            ) as handle:
                json.dump({"shapes": []}, handle)
            self.assertFalse(file_needs_re_autolabel(empty_image))

            missing = os.path.join(tmp, "c.jpg")
            open(missing, "wb").close()
            self.assertTrue(file_needs_re_autolabel(missing))


try:
    from anylabeling.views.labeling.utils.data_audit import audit_dataset

    _AUDIT_AVAILABLE = True
except Exception:
    _AUDIT_AVAILABLE = False


@unittest.skipUnless(_AUDIT_AVAILABLE, "PyQt6 is required")
class TestDatasetAuditQuality(unittest.TestCase):
    def test_tiny_edge_and_json_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = os.path.join(tmp, "a.jpg")
            open(image, "wb").close()
            with open(
                os.path.join(tmp, "a.json"), "w", encoding="utf-8"
            ) as handle:
                json.dump(
                    {
                        "imageWidth": 100,
                        "imageHeight": 100,
                        "shapes": [
                            _box("a", [[0, 0], [1, 0], [1, 1], [0, 1]])
                        ],
                    },
                    handle,
                )
            results = audit_dataset([image], tmp)
            self.assertEqual(results["tiny"], [image])
            self.assertEqual(results["edge"], [image])
            self.assertEqual(results["json_txt"], [image])
