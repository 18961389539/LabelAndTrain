import unittest

from anylabeling.views.labeling.utils.training_advisor import (
    MIN_SAMPLES_PER_CLASS,
    history_summary,
    preflight_checks,
    recommend_training_config,
)


HEALTHY = {
    "total_images": 500,
    "labeled_images": 480,
    "missing_json": 20,
    "class_counts": {"cat": 1200, "dog": 1100},
    "objects_per_image": {"avg": 4.8, "max": 20},
}


class TestPreflightChecks(unittest.TestCase):

    def test_healthy_dataset_passes(self):
        levels = [c["level"] for c in preflight_checks(HEALTHY)]
        self.assertIn("ok", levels)
        self.assertNotIn("err", levels)

    def test_empty_dataset_is_error(self):
        checks = preflight_checks({"total_images": 0})
        self.assertEqual(checks[0]["level"], "err")

    def test_more_than_half_unlabeled_warns(self):
        checks = preflight_checks(
            {"total_images": 100, "labeled_images": 30, "missing_json": 70,
             "class_counts": {"cat": 50}}
        )
        self.assertTrue(any("超过一半" in c["message"] for c in checks))

    def test_tiny_class_warns(self):
        stats = dict(HEALTHY)
        stats["class_counts"] = {"cat": 1200, "mouse": 3}
        checks = preflight_checks(stats)
        self.assertTrue(
            any(
                "mouse" in c["message"] and "只有" in c["message"]
                for c in checks
            )
        )

    def test_imbalance_warns(self):
        stats = dict(HEALTHY)
        stats["class_counts"] = {"cat": 5000, "dog": 10}
        checks = preflight_checks(stats)
        self.assertTrue(any("类别不平衡" in c["message"] for c in checks))


class TestHistorySummary(unittest.TestCase):

    def test_no_history_returns_none(self):
        self.assertIsNone(history_summary(None))
        self.assertIsNone(history_summary({}))
        self.assertIsNone(history_summary({"rounds": []}))

    def test_rounds_summary(self):
        summary = history_summary(
            {"rounds": [{"round": 1, "map50": 0.5}, {"round": 2, "map50": 0.62}]}
        )
        self.assertEqual(summary["iterations"], 2)
        self.assertEqual(summary["last_map50"], 0.62)

    def test_rounds_without_map50_returns_none(self):
        summary = history_summary({"rounds": [{"round": 1}]})
        self.assertEqual(summary["iterations"], 1)
        self.assertIsNone(summary["last_map50"])

    def test_map50_falls_back_to_lookup(self):
        summary = history_summary(
            {"rounds": [{"round": 1, "metrics/mAP50(B)": 0.71}]}
        )
        self.assertEqual(summary["last_map50"], 0.71)

    def test_invalid_map50_is_ignored(self):
        summary = history_summary({"rounds": [{"round": 1, "map50": "oops"}]})
        self.assertIsNone(summary["last_map50"])

    def test_feeds_recommend_config_history_mentions_iteration(self):
        advice = recommend_training_config(
            HEALTHY, history=history_summary({"rounds": [{"round": 1}, {"round": 2}]})
        )
        self.assertIn("第 2 轮", advice["text"])


class TestRecommendTrainingConfig(unittest.TestCase):

    def test_error_stats_short_circuits(self):
        advice = recommend_training_config({"total_images": 0})
        self.assertIn("数据集为空", advice["text"])

    def test_no_counts_still_returns_config(self):
        advice = recommend_training_config(
            {"total_images": 100, "labeled_images": 100, "class_counts": {}}
        )
        self.assertEqual(advice["epochs"], 100)
        self.assertEqual(advice["imgsz"], 640)

    def test_small_dataset_gets_more_epochs_and_tiny_batch(self):
        stats = dict(HEALTHY)
        stats["labeled_images"] = 30
        stats["total_images"] = 30
        advice = recommend_training_config(stats)
        self.assertEqual(advice["epochs"], 150)
        self.assertEqual(advice["batch"], 8)

    def test_large_dataset_gets_fewer_epochs(self):
        stats = dict(HEALTHY)
        stats["labeled_images"] = 8000
        advice = recommend_training_config(stats)
        self.assertEqual(advice["epochs"], 60)
        self.assertEqual(advice["batch"], 32)

    def test_imgsz_rounds_to_multiple_of_32(self):
        advice = recommend_training_config(HEALTHY, max_image_dim=850)
        self.assertEqual(advice["imgsz"], 832)

    def test_imgsz_caps_at_1280(self):
        advice = recommend_training_config(HEALTHY, max_image_dim=2000)
        self.assertEqual(advice["imgsz"], 1280)

    def test_imgsz_defaults_to_640(self):
        advice = recommend_training_config(HEALTHY)
        self.assertEqual(advice["imgsz"], 640)

    def test_history_mentions_iteration(self):
        advice = recommend_training_config(
            HEALTHY, history={"iterations": 3, "last_map50": 0.55}
        )
        self.assertIn("第 3 轮", advice["text"])

    def test_history_low_map50_mentions_quality(self):
        advice = recommend_training_config(
            HEALTHY, history={"iterations": 1, "last_map50": 0.2}
        )
        self.assertIn("mAP50", advice["text"])


if __name__ == "__main__":
    unittest.main()