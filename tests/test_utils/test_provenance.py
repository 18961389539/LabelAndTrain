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


class TestModelVersion(unittest.TestCase):
    """A name cannot tell a retrained model from the weights it replaced."""

    def _weights(self, tmp, name="best.onnx", body=b"v1"):
        path = os.path.join(tmp, name)
        with open(path, "wb") as handle:
            handle.write(body)
        return path

    def test_digest_tracks_content_and_survives_reopen(self):
        import tempfile

        from anylabeling.views.labeling.provenance import weight_digest

        with tempfile.TemporaryDirectory() as tmp:
            path = self._weights(tmp)
            first = weight_digest(path)
            self.assertEqual(first, weight_digest(path))
            self.assertEqual(len(first), 12)

            with open(path, "wb") as handle:
                handle.write(b"v2")
            self.assertNotEqual(first, weight_digest(path))

            self.assertIsNone(weight_digest(os.path.join(tmp, "gone.onnx")))

    def test_digest_covers_a_tail_only_rewrite(self):
        # Why the whole file is hashed: fine-tuning can rewrite just the head
        # layer at the end and leave both the leading bytes and the size equal.
        import tempfile

        from anylabeling.views.labeling.provenance import weight_digest

        with tempfile.TemporaryDirectory() as tmp:
            head = b"x" * (1024 * 1024)
            one = self._weights(tmp, "a.onnx", head + b"AAAA")
            two = self._weights(tmp, "b.onnx", head + b"BBBB")
            self.assertNotEqual(weight_digest(one), weight_digest(two))

    def test_resolve_model_path_handles_urls_and_yaml_relative_paths(self):
        import tempfile

        from anylabeling.views.labeling.provenance import resolve_model_path

        self.assertIsNone(resolve_model_path(None))
        self.assertIsNone(
            resolve_model_path({"model_path": "https://host/best.onnx"})
        )
        with tempfile.TemporaryDirectory() as tmp:
            weights_dir = os.path.join(tmp, "weights")
            os.makedirs(weights_dir)
            path = self._weights(weights_dir)
            config = {
                "model_path": "weights/best.onnx",
                "config_file": os.path.join(tmp, "m.yaml"),
            }
            cwd = os.getcwd()
            try:
                os.chdir(tmp)
                self.assertEqual(resolve_model_path(config), path)
            finally:
                os.chdir(cwd)

    def test_stamp_records_the_version_only_when_there_is_one(self):
        with_version = [{"label": "cat"}]
        stamp_model_shapes(with_version, "run_07", "a1b2c3d4e5f6")
        self.assertEqual(with_version[0]["model_version"], "a1b2c3d4e5f6")

        without = [{"label": "cat"}]
        stamp_model_shapes(without, "run_07")
        self.assertNotIn("model_version", without[0])

    def _shape(self, version=None, name="run_07"):
        payload = {"label": "cat", "source": SOURCE_MODEL, "model": name}
        if version:
            payload["model_version"] = version
        return payload

    def test_same_name_different_weights_counts_as_stale(self):
        shape = self._shape("a1b2c3d4e5f6")
        self.assertTrue(
            is_from_other_model(shape, "run_07", "ffeeccaa1122")
        )
        self.assertFalse(is_from_other_model(shape, "run_07", "a1b2c3d4e5f6"))

    def test_shape_without_a_version_is_not_made_stale_by_one(self):
        # Every box annotated before this field existed has no version. Treating
        # that as a mismatch would flood the cleanup report with false work.
        shape = self._shape()
        self.assertFalse(is_from_other_model(shape, "run_07", "a1b2c3d4e5f6"))
        self.assertFalse(is_from_other_model(shape, "run_07", None))
        self.assertTrue(is_from_other_model(shape, "run_06", None))

    def test_stale_collection_honours_the_version(self):
        data = {
            "shapes": [
                self._shape("old"),
                self._shape("new"),
                self._shape(),
                {"label": "human", "source": SOURCE_HUMAN},
            ]
        }
        found = collect_other_model_shapes(data, "run_07", "new")
        self.assertEqual([index for index, _ in found], [0])

    def test_round_trip_keeps_the_version(self):
        from anylabeling.views.labeling.shape import Shape

        shape = Shape(label="cat")
        stamp_model_shapes([shape], "run_07", "a1b2c3d4e5f6")
        payload = shape.to_dict()
        self.assertEqual(payload["model_version"], "a1b2c3d4e5f6")

        loaded = Shape()
        loaded.load_from_dict(payload)
        self.assertEqual(loaded.model_version, "a1b2c3d4e5f6")

        legacy = dict(payload)
        legacy.pop("model_version")
        reloaded = Shape()
        reloaded.load_from_dict(legacy)
        self.assertIsNone(reloaded.model_version)
        self.assertNotIn("model_version", reloaded.to_dict())
