import os
import tempfile
import unittest

from anylabeling.views.labeling.utils.data_intel import (
    analyze_distribution,
    box_iou,
    find_duplicate_groups,
    find_missing_predictions,
    hamming_distance,
    mine_hard_examples,
    suggest_balancing,
)


def _drawn_image(path, offset):
    """A synthetic image with structure (plain colours hash identically)."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (64, 64), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for index in range(-64, 128, 6):
        draw.line([(index, 0), (index + offset, 64)], fill=(0, 0, 0), width=2)
    image.save(path)
    return path


def _box(label, points=None, score=None):
    shape = {
        "label": label,
        "shape_type": "rectangle",
        "points": points or [[0, 0], [10, 10]],
    }
    if score is not None:
        shape["score"] = score
    return shape


class TestBoxIoU(unittest.TestCase):
    def test_iou_values(self):
        self.assertEqual(box_iou((0, 0, 10, 10), (0, 0, 10, 10)), 1.0)
        self.assertEqual(box_iou((0, 0, 10, 10), (20, 20, 30, 30)), 0.0)
        # overlap 5x5 = 25, union = 100 + 100 - 25 = 175
        self.assertAlmostEqual(box_iou((0, 0, 10, 10), (5, 5, 15, 15)), 25 / 175)

    def test_degenerate_boxes(self):
        self.assertEqual(box_iou((0, 0, 0, 0), (0, 0, 10, 10)), 0.0)
        self.assertEqual(box_iou(None, (0, 0, 10, 10)), 0.0)


class TestMissingPredictions(unittest.TestCase):
    def test_unmatched_high_score_prediction_is_missing(self):
        annotations = [_box("cat", [[0, 0], [10, 10]])]
        predictions = [
            _box("cat", [[0, 0], [10, 10]], score=0.9),   # matched
            _box("cat", [[50, 50], [60, 60]], score=0.8),  # missed label
        ]
        missing = find_missing_predictions(predictions, annotations)
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["points"], [[50, 50], [60, 60]])

    def test_low_score_predictions_are_ignored(self):
        predictions = [_box("cat", [[50, 50], [60, 60]], score=0.2)]
        self.assertEqual(find_missing_predictions(predictions, []), [])

    def test_label_mismatch_counts_as_missing(self):
        annotations = [_box("cat", [[0, 0], [10, 10]])]
        predictions = [_box("dog", [[0, 0], [10, 10]], score=0.9)]
        self.assertEqual(
            len(find_missing_predictions(predictions, annotations)), 1
        )
        # ...unless label agreement is not required
        self.assertEqual(
            len(
                find_missing_predictions(
                    predictions, annotations, match_same_label=False
                )
            ),
            0,
        )

    def test_empty_inputs(self):
        self.assertEqual(find_missing_predictions([], []), [])
        self.assertEqual(find_missing_predictions(None, None), [])


class TestHashing(unittest.TestCase):
    def test_hamming_distance(self):
        self.assertEqual(hamming_distance(0b1010, 0b1010), 0)
        self.assertEqual(hamming_distance(0b1010, 0b0101), 4)

    def test_duplicate_grouping(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not available")

        with tempfile.TemporaryDirectory() as tmp:
            base = _drawn_image(os.path.join(tmp, "a.png"), 12)
            copy = _drawn_image(os.path.join(tmp, "b.png"), 12)
            other = _drawn_image(os.path.join(tmp, "c.png"), 48)

            groups = find_duplicate_groups([base, copy, other])
            self.assertEqual(len(groups), 1)
            self.assertEqual(set(groups[0]), {base, copy})
            self.assertNotIn(other, groups[0])

    def test_unique_images_produce_no_groups(self):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            self.skipTest("Pillow is not available")

        with tempfile.TemporaryDirectory() as tmp:
            paths = [
                _drawn_image(os.path.join(tmp, f"{index}.png"), index * 24)
                for index in range(3)
            ]
            self.assertEqual(find_duplicate_groups(paths), [])


class TestHardExampleMining(unittest.TestCase):
    def test_ranks_by_uncertainty(self):
        entries = [
            ("confident", [_box("a", score=0.95)]),
            ("uncertain", [_box("a", score=0.1)]),
            ("middle", [_box("a", score=0.35)]),
        ]
        mined = mine_hard_examples(entries, min_uncertainty=0.0)
        self.assertEqual(
            [path for path, _ in mined], ["uncertain", "middle", "confident"]
        )

    def test_unlabeled_images_win(self):
        mined = mine_hard_examples(
            [("labeled", [_box("a", score=0.3)]), ("empty", None)]
        )
        self.assertEqual(mined[0][0], "empty")

    def test_top_k_and_floor(self):
        entries = [(f"img{index}", [_box("a", score=0.99)]) for index in range(10)]
        self.assertEqual(len(mine_hard_examples(entries, top_k=5)), 0)
        uncertain = [
            (f"img{index}", [_box("a", score=0.2)]) for index in range(10)
        ]
        self.assertEqual(len(mine_hard_examples(uncertain, top_k=5)), 5)


class TestDistribution(unittest.TestCase):
    def _data(self, shapes):
        return {"imageWidth": 640, "imageHeight": 480, "shapes": shapes}

    def test_basic_stats(self):
        entries = [
            ("a.jpg", self._data([_box("cat", [[0, 0], [100, 100]])])),
            ("b.jpg", self._data([_box("cat", [[0, 0], [10, 10]])])),
            ("c.jpg", self._data([])),
            ("d.jpg", None),
        ]
        stats = analyze_distribution(entries)
        self.assertEqual(stats["total_images"], 4)
        self.assertEqual(stats["labeled_images"], 3)
        self.assertEqual(stats["negative_images"], 1)
        self.assertEqual(stats["missing_json"], 1)
        self.assertEqual(stats["total_shapes"], 2)
        self.assertEqual(stats["class_counts"], {"cat": 2})
        # 100x100 -> large, 10x10 -> small
        self.assertEqual(stats["area_buckets"]["large"], 1)
        self.assertEqual(stats["area_buckets"]["small"], 1)

    def test_extreme_aspect_ratio(self):
        entries = [
            ("a.jpg", self._data([_box("long", [[0, 0], [200, 10]])])),
        ]
        self.assertEqual(analyze_distribution(entries)["extreme_aspect"], 1)


class TestBalancingAdvice(unittest.TestCase):
    def test_imbalance_triggers_advice(self):
        stats = {
            "total_images": 100,
            "labeled_images": 100,
            "negative_images": 0,
            "missing_json": 0,
            "total_shapes": 210,
            "class_counts": {"cat": 200, "dog": 10},
            "area_buckets": {"small": 0, "medium": 10, "large": 200},
            "extreme_aspect": 0,
            "objects_per_image": {"avg": 2.1, "max": 5},
        }
        advice = suggest_balancing(stats)
        self.assertTrue(any("失衡" in line for line in advice))
        self.assertTrue(any("dog" in line for line in advice))

    def test_small_objects_trigger_advice(self):
        stats = {
            "total_images": 50,
            "labeled_images": 50,
            "negative_images": 0,
            "missing_json": 0,
            "total_shapes": 100,
            "class_counts": {"cat": 100},
            "area_buckets": {"small": 80, "medium": 10, "large": 10},
            "extreme_aspect": 0,
            "objects_per_image": {"avg": 2.0, "max": 4},
        }
        advice = suggest_balancing(stats)
        self.assertTrue(any("小目标" in line for line in advice))

    def test_clean_dataset_gets_positive_message(self):
        stats = {
            "total_images": 2000,
            "labeled_images": 2000,
            "negative_images": 20,
            "missing_json": 0,
            "total_shapes": 4000,
            "class_counts": {"cat": 2000, "dog": 2000},
            "area_buckets": {"small": 200, "medium": 1800, "large": 2000},
            "extreme_aspect": 10,
            "objects_per_image": {"avg": 2.0, "max": 6},
        }
        advice = suggest_balancing(stats)
        self.assertEqual(len(advice), 1)
        self.assertIn("未见明显问题", advice[0])

    def test_missing_labels_are_reported(self):
        stats = {
            "total_images": 10,
            "labeled_images": 8,
            "negative_images": 0,
            "missing_json": 2,
            "total_shapes": 20,
            "class_counts": {"cat": 20},
            "area_buckets": {"small": 0, "medium": 20, "large": 0},
            "extreme_aspect": 0,
            "objects_per_image": {"avg": 2.5, "max": 4},
        }
        self.assertTrue(
            any("没有标注" in line for line in suggest_balancing(stats))
        )

    def test_invalid_input(self):
        self.assertEqual(suggest_balancing(None), [])
        self.assertEqual(suggest_balancing({}), [])


if __name__ == "__main__":
    unittest.main()
