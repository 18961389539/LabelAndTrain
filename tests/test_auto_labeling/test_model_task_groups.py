import unittest

from anylabeling.services.auto_labeling import _CUSTOM_MODELS
from anylabeling.views.labeling.utils.model_task_groups import (
    TASK_FILTER_ORDER,
    TASK_GROUP_LABELS,
    TASK_TYPE_GROUPS,
    classify_model_load_error,
    group_for_model_type,
    mark_recommended_models,
)


class TestModelTaskGroups(unittest.TestCase):
    def test_group_for_known_types(self):
        self.assertEqual(group_for_model_type("yolov8"), "detect")
        self.assertEqual(group_for_model_type("yolov8_seg"), "segment")
        self.assertEqual(group_for_model_type("yolo26_pose"), "pose")
        self.assertEqual(group_for_model_type("yolov8_sam2"), "segment")
        self.assertEqual(group_for_model_type(""), "other")
        self.assertEqual(group_for_model_type("unknown_model"), "other")

    def test_every_loadable_model_type_gets_a_group(self):
        # A type landing in "other" means the dropdown filter buries it; this
        # is what silently regressed when upstream-only task types were pruned.
        ungrouped = sorted(
            model_type
            for model_type in _CUSTOM_MODELS
            if group_for_model_type(model_type) == "other"
        )
        self.assertEqual(ungrouped, [])

    def test_groups_and_filter_labels_stay_in_sync(self):
        for group in TASK_TYPE_GROUPS:
            self.assertIn(group, TASK_GROUP_LABELS)
            self.assertIn(group, TASK_FILTER_ORDER)
        self.assertEqual(TASK_FILTER_ORDER[0], "all")
        self.assertIn("all", TASK_GROUP_LABELS)

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
