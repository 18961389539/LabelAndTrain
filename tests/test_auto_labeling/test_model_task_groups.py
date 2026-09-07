import unittest

from anylabeling.views.labeling.utils.model_task_groups import (
    classify_model_load_error,
    group_for_model_type,
    mark_recommended_models,
)


class TestModelTaskGroups(unittest.TestCase):
    def test_group_for_known_types(self):
        self.assertEqual(group_for_model_type("yolov8"), "detect")
        self.assertEqual(group_for_model_type("yolov8_seg"), "segment")
        self.assertEqual(group_for_model_type("yolov8_pose"), "pose")
        self.assertEqual(group_for_model_type("ppocr"), "ocr")
        self.assertEqual(group_for_model_type(""), "other")
        self.assertEqual(group_for_model_type("unknown_model"), "other")

    def test_mark_recommended_picks_tiny_per_group(self):
        model_data = {
            "CVHub": {
                "yolov8s": {"type": "yolov8", "display_name": "YOLOv8s"},
                "yolov8n": {"type": "yolov8", "display_name": "YOLOv8n Nano"},
                "yolov8s_seg": {
                    "type": "yolov8_seg",
                    "display_name": "YOLOv8s-Seg",
                },
                "load_custom_model": {
                    "type": "yolov8",
                    "display_name": "...Load Custom Model",
                },
            }
        }
        mark_recommended_models(model_data)
        self.assertTrue(model_data["CVHub"]["yolov8n"]["recommended"])
        self.assertFalse(model_data["CVHub"]["yolov8s"]["recommended"])
        self.assertTrue(model_data["CVHub"]["yolov8s_seg"]["recommended"])
        self.assertFalse(
            model_data["CVHub"]["load_custom_model"].get("recommended", False)
        )

    def test_classify_cuda_error_offers_cpu(self):
        message, offer_cpu = classify_model_load_error(
            "CUDA execution provider is not available"
        )
        self.assertTrue(offer_cpu)
        self.assertIn("GPU", message)

    def test_classify_missing_weight_does_not_offer_cpu(self):
        message, offer_cpu = classify_model_load_error(
            "Could not download model: file not found"
        )
        self.assertFalse(offer_cpu)
        self.assertIn("\u6743\u91cd", message)
