import json
import os
import tempfile
import unittest

from anylabeling.views.labeling.utils.active_learning import (
    DEFAULT_ACCEPT,
    DEFAULT_REVIEW,
    append_iteration,
    calibrate_thresholds,
    collect_score_samples,
    format_iteration_summary,
    image_uncertainty,
    load_history,
    load_thresholds,
    needs_review,
    rank_by_uncertainty,
    read_last_map50,
    save_thresholds,
    shape_uncertainty,
    suggest_next_step,
    thresholds_for,
    update_last_iteration,
)


def _box(label, score=None, points=None):
    return {
        "label": label,
        "shape_type": "rectangle",
        "points": points or [[0, 0], [10, 10]],
        **({"score": score} if score is not None else {}),
    }


class TestUncertainty(unittest.TestCase):
    def test_score_bands(self):
        # below review -> fully uncertain
        self.assertEqual(shape_uncertainty(_box("a", 0.1)), 1.0)
        # inside the band -> interpolated
        self.assertAlmostEqual(shape_uncertainty(_box("a", 0.35)), 0.5)
        # above accept -> confident
        self.assertEqual(shape_uncertainty(_box("a", 0.9)), 0.0)

    def test_human_drawn_shape_is_certain(self):
        self.assertEqual(shape_uncertainty(_box("a")), 0.0)

    def test_custom_thresholds(self):
        # a high accept threshold leaves even 0.8 uncertain
        self.assertAlmostEqual(
            shape_uncertainty(_box("a", 0.8), accept=0.9, review=0.7), 0.5
        )
        self.assertEqual(shape_uncertainty(_box("a", 0.8), accept=0.7), 0.0)

    def test_image_uncertainty_worst_box_dominates(self):
        shapes = [_box("a", 0.9), _box("a", 0.9), _box("a", 0.1)]
        self.assertGreater(image_uncertainty(shapes), 0.6)
        self.assertLess(image_uncertainty([_box("a", 0.9)] * 3), 0.01)

    def test_empty_shape_list(self):
        self.assertEqual(image_uncertainty([]), 0.0)
        self.assertEqual(image_uncertainty(None), 0.0)

    def test_needs_review(self):
        self.assertTrue(needs_review([_box("a", 0.3)]))
        self.assertFalse(needs_review([_box("a", 0.9)]))
        # no score means a human drew or confirmed it
        self.assertFalse(needs_review([_box("a")]))
        self.assertFalse(needs_review([]))

    def test_rank_puts_unlabeled_first(self):
        ranked = rank_by_uncertainty(
            [
                ("b_labeled", [_box("a", 0.9)]),
                ("a_unlabeled", None),
                ("c_uncertain", [_box("a", 0.1)]),
            ]
        )
        self.assertEqual([path for path, _ in ranked][0], "a_unlabeled")
        # uncertain beats confident among labelled images
        self.assertEqual(ranked[1][0], "c_uncertain")
        self.assertEqual(ranked[-1][0], "b_labeled")


class TestCalibration(unittest.TestCase):
    def test_bimodal_distribution_splits_at_the_gap(self):
        # two clear clusters: noise around 0.25 and confident around 0.85
        scores = [0.2, 0.22, 0.25, 0.27, 0.3] + [0.8, 0.82, 0.85, 0.88, 0.9]
        result = calibrate_thresholds({"cat": scores})
        entry = result["cat"]
        self.assertGreater(entry["accept"], 0.5)
        self.assertLess(entry["review"], 0.5)
        self.assertGreater(entry["accept"], entry["review"])

    def test_small_class_falls_back_to_global_pool(self):
        result = calibrate_thresholds(
            {"rare": [0.9], "common": [0.2, 0.25, 0.3, 0.8, 0.85, 0.9, 0.95, 0.99]},
            min_samples=4,
        )
        self.assertIn("rare", result)

    def test_confirmed_scores_pull_accept_down(self):
        scores = [0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]
        plain = calibrate_thresholds({"dog": scores}, min_samples=4)
        confirmed = calibrate_thresholds(
            {"dog": scores}, {"dog": [0.5, 0.52, 0.55, 0.58, 0.6]}, min_samples=4
        )
        self.assertLess(
            confirmed["dog"]["accept"], plain["dog"]["accept"]
        )

    def test_thresholds_are_clamped_and_ordered(self):
        result = calibrate_thresholds(
            {"x": [0.01, 0.02, 0.03, 0.04, 0.99, 0.995, 0.999, 1.0]},
            min_samples=4,
        )
        entry = result["x"]
        self.assertGreaterEqual(entry["accept"], 0.10)
        self.assertLessEqual(entry["accept"], 0.95)
        self.assertGreater(entry["accept"], entry["review"])

    def test_roundtrip_persistence(self):
        thresholds = {"cat": {"accept": 0.7, "review": 0.3, "samples": 12}}
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_thresholds(tmp), {})
            save_thresholds(tmp, thresholds)
            loaded = load_thresholds(tmp)
            self.assertEqual(loaded["cat"]["accept"], 0.7)
            self.assertEqual(
                thresholds_for("cat", loaded), (0.7, 0.3)
            )

    def test_thresholds_for_unknown_label(self):
        self.assertEqual(
            thresholds_for("nope", {"cat": {"accept": 0.6, "review": 0.2}}),
            (DEFAULT_ACCEPT, DEFAULT_REVIEW),
        )

    def test_collect_score_samples_separates_confirmed(self):
        entries = [
            ({"shapes": [_box("cat", 0.4)]}, True),
            ({"shapes": [_box("cat", 0.3), _box("dog", 0.8)]}, False),
        ]
        class_scores, confirmed = collect_score_samples(entries)
        self.assertEqual(class_scores["cat"], [0.4, 0.3])
        self.assertEqual(confirmed["cat"], [0.4])
        # "dog" only appears in the unconfirmed image
        self.assertNotIn("dog", confirmed)
        self.assertEqual(class_scores["dog"], [0.8])


class TestIterationHistory(unittest.TestCase):
    def test_append_and_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            history = append_iteration(
                tmp, model="run1", labeled_images=100, total_shapes=500
            )
            self.assertEqual(len(history["rounds"]), 1)
            self.assertEqual(history["rounds"][0]["round"], 1)

            history = append_iteration(
                tmp, model="run2", labeled_images=200, total_shapes=700,
                new_shapes=200,
            )
            self.assertEqual(len(history["rounds"]), 2)

            history = update_last_iteration(tmp, reviewed_images=80)
            self.assertEqual(history["rounds"][-1]["reviewed_images"], 80)
            # reload from disk to prove it is persisted
            self.assertEqual(load_history(tmp)["rounds"][-1]["reviewed_images"], 80)

    def test_suggest_stop_when_gain_is_tiny(self):
        with tempfile.TemporaryDirectory() as tmp:
            append_iteration(
                tmp, labeled_images=100, total_shapes=1000, new_shapes=500
            )
            append_iteration(
                tmp, labeled_images=110, total_shapes=1005, new_shapes=5
            )
            suggestion = suggest_next_step(load_history(tmp))
            self.assertEqual(suggestion["action"], "stop")

    def test_suggest_continue_when_gain_is_real(self):
        history = {
            "rounds": [
                {"round": 1, "labeled_images": 100, "total_shapes": 500,
                 "new_shapes": 500, "reviewed_images": 100},
                {"round": 2, "labeled_images": 250, "total_shapes": 1100,
                 "new_shapes": 600, "reviewed_images": 150},
            ]
        }
        suggestion = suggest_next_step(history)
        self.assertEqual(suggestion["action"], "continue")
        self.assertIsNotNone(suggestion["suggested_images"])

    def test_suggest_stop_on_sharp_drop(self):
        history = {
            "rounds": [
                {"round": 1, "total_shapes": 500, "new_shapes": 400},
                {"round": 2, "total_shapes": 700, "new_shapes": 100},
            ]
        }
        suggestion = suggest_next_step(history)
        self.assertEqual(suggestion["action"], "stop")

    def test_single_round_is_not_enough_to_judge(self):
        history = {"rounds": [{"round": 1, "new_shapes": 0}]}
        self.assertEqual(suggest_next_step(history)["action"], "continue")

    def test_summary_text(self):
        history = {"rounds": [{"round": 1, "model": "run1", "map50": 0.8123,
                               "labeled_images": 10, "total_shapes": 40}]}
        lines = format_iteration_summary(history)
        self.assertIn("第 1 轮", lines[0])
        self.assertIn("0.812", lines[0])
        self.assertTrue(any("建议" in line for line in lines))

    def test_read_last_map50(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "results.csv")
            with open(csv_path, "w", encoding="utf-8") as handle:
                handle.write(
                    "epoch,metrics/mAP50(B),metrics/mAP50-95(B)\n"
                    "1,0.500,0.300\n"
                    "2,0.750,0.500\n"
                )
            self.assertAlmostEqual(read_last_map50(csv_path), 0.75)
            self.assertIsNone(read_last_map50(os.path.join(tmp, "nope.csv")))


class TestCalibrationIntegration(unittest.TestCase):
    """End-to-end: scores from json files -> calibration -> filtering."""

    def test_calibrated_thresholds_change_review_decision(self):
        entries = [
            (
                {
                    "shapes": [
                        _box("cat", 0.31),
                        _box("cat", 0.62),
                        _box("cat", 0.66),
                        _box("cat", 0.71),
                        _box("cat", 0.75),
                        _box("cat", 0.80),
                        _box("cat", 0.86),
                        _box("cat", 0.91),
                    ]
                },
                False,
            )
        ]
        class_scores, confirmed = collect_score_samples(entries)
        thresholds = calibrate_thresholds(class_scores, confirmed, min_samples=4)
        accept, _review = thresholds_for("cat", thresholds, DEFAULT_ACCEPT,
                                         DEFAULT_REVIEW)
        shapes = entries[0][0]["shapes"]
        # with a calibrated (low) accept threshold the 0.31 box is the only
        # one that still needs a human
        flagged = [
            shape["score"]
            for shape in shapes
            if shape_uncertainty(shape, accept, _review) > 0
        ]
        self.assertTrue(flagged)
        self.assertEqual(min(flagged), 0.31)

    def test_json_roundtrip_of_history_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            append_iteration(tmp, model="m", new_shapes=3)
            path = os.path.join(tmp, "active_learning_history.json")
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.assertEqual(data["rounds"][0]["new_shapes"], 3)


if __name__ == "__main__":
    unittest.main()
