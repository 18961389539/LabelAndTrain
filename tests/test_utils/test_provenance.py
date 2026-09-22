import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from anylabeling.views.labeling.provenance import (  # noqa: E402
    SOURCE_HUMAN,
    SOURCE_MODEL,
    SOURCE_UNKNOWN,
    collect_other_model_shapes,
    describe_shape,
    get_source,
    is_from_other_model,
    model_of,
    model_display_name,
    stamp_model_shapes,
)


class TestStamping(unittest.TestCase):
    def test_stamps_every_fresh_prediction(self):
        # Callers only ever pass shapes a model just produced, so the
        # constructor's `human` default must not shield them from the stamp.
        shapes = [{"label": "cat"}, {"label": "dog", "source": "human"}]
        self.assertEqual(stamp_model_shapes(shapes, "run_07"), 2)
        for shape in shapes:
            self.assertEqual(shape["source"], SOURCE_MODEL)
            self.assertEqual(shape["model"], "run_07")

    def test_stamps_shape_objects(self):
        from anylabeling.views.labeling.shape import Shape

        shape = Shape(label="cat")
        stamp_model_shapes([shape], "run_07")
        self.assertEqual(get_source(shape), SOURCE_MODEL)
        self.assertEqual(model_of(shape), "run_07")

    def test_none_and_empty_input(self):
        self.assertEqual(stamp_model_shapes(None, "m"), 0)
        self.assertEqual(stamp_model_shapes([], "m"), 0)


class TestStaleness(unittest.TestCase):
    def test_only_other_model_boxes_are_stale(self):
        shapes = [
            {"label": "a", "source": SOURCE_MODEL, "model": "run_01"},
            {"label": "b", "source": SOURCE_MODEL, "model": "run_07"},
            {"label": "c", "source": SOURCE_HUMAN, "model": "run_01"},
            {"label": "d"},
        ]
        stale = collect_other_model_shapes({"shapes": shapes}, "run_07")
        self.assertEqual([index for index, _ in stale], [0])

    def test_missing_provenance_is_never_a_cleanup_candidate(self):
        # Legacy files predate the field: treating "absent" as "model" would
        # let a cleanup pass delete work nobody ever attributed.
        self.assertFalse(is_from_other_model({"label": "a"}, "run_07"))
        self.assertEqual(get_source({"label": "a"}), SOURCE_UNKNOWN)

    def test_unattributed_model_box_counts_as_other_model(self):
        shape = {"label": "a", "source": SOURCE_MODEL}
        self.assertTrue(is_from_other_model(shape, "run_07"))

    def test_describe_shape(self):
        _label, detail = describe_shape(
            {
                "label": "cat",
                "points": [[0, 0], [10, 0], [10, 20], [0, 20]],
                "score": 0.87,
            }
        )
        self.assertIn("10x20", detail)
        self.assertIn("0.87", detail)

    def test_model_identity_falls_back(self):
        self.assertEqual(
            model_display_name({"display_name": "A", "name": "B"}), "A"
        )
        self.assertEqual(model_display_name({"name": "B"}), "B")
        self.assertIsNone(model_display_name(None))


class TestShapeRoundTrip(unittest.TestCase):
    def test_source_and_model_survive_to_dict_load(self):
        from anylabeling.views.labeling.shape import Shape

        shape = Shape(label="cat", shape_type="rectangle")
        stamp_model_shapes([shape], "run_07")
        payload = shape.to_dict()
        self.assertEqual(payload["source"], SOURCE_MODEL)
        self.assertEqual(payload["model"], "run_07")

        restored = Shape().load_from_dict(payload)
        self.assertEqual(get_source(restored), SOURCE_MODEL)
        self.assertEqual(model_of(restored), "run_07")

    def test_human_shape_does_not_write_an_empty_model_key(self):
        from anylabeling.views.labeling.shape import Shape

        shape = Shape(label="cat", shape_type="rectangle")
        payload = shape.to_dict()
        self.assertEqual(payload["source"], SOURCE_HUMAN)
        self.assertNotIn("model", payload)

    def test_legacy_payload_loads_as_unknown_not_human(self):
        from anylabeling.views.labeling.shape import Shape

        restored = Shape().load_from_dict(
            {"label": "cat", "points": [[0, 0], [1, 1]], "shape_type": "rectangle"}
        )
        self.assertEqual(get_source(restored), SOURCE_UNKNOWN)
        self.assertNotEqual(get_source(restored), SOURCE_HUMAN)


if __name__ == "__main__":
    unittest.main()
