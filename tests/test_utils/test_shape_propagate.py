import json
import os
import os.path as osp
import tempfile
import unittest

from anylabeling.views.labeling.utils.shape_propagate import (
    bbox_signature,
    load_shapes_from_file,
    plan_template_propagation,
    propagate_labels,
    scale_shape,
    template_candidates,
)


class TestLoadShapesFromFile(unittest.TestCase):

    def test_missing_file_degrades_gracefully(self):
        self.assertEqual(load_shapes_from_file(None), (0, 0, []))
        self.assertEqual(load_shapes_from_file("/no/such/file.json"), (0, 0, []))

    def test_corrupt_file_degrades_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = osp.join(tmp, "bad.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write("not json")
            self.assertEqual(load_shapes_from_file(path), (0, 0, []))

    def test_reads_shapes_and_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = osp.join(tmp, "a.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "imageWidth": 200,
                        "imageHeight": 100,
                        "shapes": [{"label": "cat", "points": [[0, 0], [10, 10]]}],
                    },
                    f,
                )
            w, h, shapes = load_shapes_from_file(path)
            self.assertEqual(w, 200)
            self.assertEqual(h, 100)
            self.assertEqual(shapes[0]["label"], "cat")


class TestScaleShape(unittest.TestCase):

    def test_scales_and_clamps_coordinates(self):
        shape = {"label": "cat", "shape_type": "rectangle",
                 "points": [[0, 0], [100, 50]]}
        scaled = scale_shape(shape, 200, 100, 50, 100)
        self.assertEqual(scaled["points"], [[0.0, 0.0], [25.0, 50.0]])
        self.assertEqual(scaled["shape_type"], "rectangle")

    def test_clamps_out_of_bounds(self):
        shape = {"label": "cat", "points": [[-5, -5], [250, 120]]}
        scaled = scale_shape(shape, 200, 100, 100, 100)
        self.assertEqual(scaled["points"], [[0.0, 0.0], [100.0, 100.0]])

    def test_invalid_points_are_dropped(self):
        shape = {"label": "cat", "points": [[0, 0], ["x", 5]]}
        scaled = scale_shape(shape, 100, 100, 200, 200)
        self.assertEqual(scaled["points"], [[0.0, 0.0]])

    def test_zero_target_falls_back_to_identity(self):
        shape = {"label": "cat", "points": [[10, 20]]}
        scaled = scale_shape(shape, 0, 0, 100, 100)
        self.assertEqual(scaled["points"], [[10.0, 20.0]])


class TestPropagateLabels(unittest.TestCase):

    def _write(self, tmp, name, w, h, shapes):
        path = osp.join(tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"imageWidth": w, "imageHeight": h, "shapes": shapes}, f)
        return path

    def test_copies_and_scales_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            prev = self._write(
                tmp,
                "prev.json",
                200,
                100,
                [{"label": "cat", "points": [[0, 0], [100, 50]]}],
            )
            planned = propagate_labels(prev, None, 100, 100, [])
            self.assertEqual(len(planned), 1)
            self.assertEqual(planned[0]["label"], "cat")
            self.assertEqual(planned[0]["points"], [[0.0, 0.0], [50.0, 50.0]])

    def test_prev_size_overrides_stored_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            prev = self._write(
                tmp, "prev.json", 100, 100,
                [{"label": "cat", "points": [[0, 0], [10, 10]]}],
            )
            planned = propagate_labels(prev, (50, 50), 100, 100, [])
            # source is 50x50, so 10 -> scaled by 100/50 = 2 -> 20
            self.assertEqual(planned[0]["points"], [[0.0, 0.0], [20.0, 20.0]])

    def test_skips_existing_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            prev = self._write(
                tmp,
                "prev.json",
                100,
                100,
                [{"label": "cat", "points": [[0, 0], [10, 10]]}],
            )
            existing = [{"label": "cat", "points": [[0, 0], [10, 10]]}]
            planned = propagate_labels(prev, None, 100, 100, existing)
            self.assertEqual(planned, [])

    def test_keeps_distinct_labels_at_same_spot(self):
        with tempfile.TemporaryDirectory() as tmp:
            prev = self._write(
                tmp,
                "prev.json",
                100,
                100,
                [{"label": "cat", "points": [[0, 0], [10, 10]]}],
            )
            existing = [{"label": "dog", "points": [[0, 0], [10, 10]]}]
            planned = propagate_labels(prev, None, 100, 100, existing)
            self.assertEqual(len(planned), 1)
            self.assertEqual(planned[0]["label"], "cat")

    def test_empty_target_returns_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            prev = self._write(
                tmp, "prev.json", 100, 100,
                [{"label": "cat", "points": [[0, 0], [10, 10]]}],
            )
            self.assertEqual(propagate_labels(prev, None, 0, 100, []), [])


class TestBboxSignature(unittest.TestCase):

    def test_normalized_rounded_signature(self):
        shape = {"label": "cat", "points": [[0, 0], [50, 50]]}
        self.assertEqual(bbox_signature(shape, 100, 100), ("cat", (0.0, 0.0, 0.5, 0.5)))


def _scene(path, offset):
    """Structured synthetic image (like the dhash tests, actually hashes)."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (64, 64), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for index in range(-64, 128, 6):
        draw.line([(index, 0), (index + offset, 64)], fill=(0, 0, 0), width=2)
    image.save(path)
    return path


def _solid(path, rgb=(200, 10, 10)):
    from PIL import Image

    Image.new("RGB", (64, 64), rgb).save(path)
    return path


def _label(tmp, name, shapes):
    with open(osp.join(tmp, name), "w", encoding="utf-8") as f:
        json.dump({"imageWidth": 64, "imageHeight": 64, "shapes": shapes}, f)


class TestTemplateCandidates(unittest.TestCase):

    def test_similar_image_is_selected_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = _scene(osp.join(tmp, "t.png"), 0)
            target = _scene(osp.join(tmp, "g.png"), 0)  # identical render
            far = _scene(osp.join(tmp, "f.png"), 48)
            matches = template_candidates(target, [far, template])
            self.assertTrue(matches)
            best, distance = matches[0]
            self.assertEqual(best, template)
            self.assertEqual(distance, 0)

    def test_dissimilar_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = _scene(osp.join(tmp, "t.png"), 0)
            target = _solid(osp.join(tmp, "g.png"))
            self.assertEqual(template_candidates(target, [template]), [])


class TestPlanTemplatePropagation(unittest.TestCase):

    def test_matching_template_produces_scaled_prelabels(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = _scene(osp.join(tmp, "template.png"), 0)
            _label(tmp, "template.json", [{"label": "cat", "points": [[0, 0], [16, 16]]}])
            target = _scene(osp.join(tmp, "shot.png"), 0)
            plan = plan_template_propagation(tmp, [target], [template])
            self.assertEqual(len(plan), 1)
            self.assertEqual(plan[0]["template"], template)
            self.assertEqual(plan[0]["distance"], 0)
            self.assertEqual(plan[0]["shapes"][0]["points"], [[0.0, 0.0], [16.0, 16.0]])

    def test_no_match_skips_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = _scene(osp.join(tmp, "template.png"), 0)
            _label(tmp, "template.json", [{"label": "cat", "points": [[0, 0], [16, 16]]}])
            target = _solid(osp.join(tmp, "shot.png"))
            self.assertEqual(plan_template_propagation(tmp, [target], [template]), [])

    def test_existing_duplicate_shapes_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            template = _scene(osp.join(tmp, "template.png"), 0)
            _label(tmp, "template.json", [{"label": "cat", "points": [[0, 0], [16, 16]]}])
            target = _scene(osp.join(tmp, "shot.png"), 0)
            _label(tmp, "shot.json", [{"label": "cat", "points": [[0, 0], [16, 16]]}])
            plan = plan_template_propagation(tmp, [target], [template])
            self.assertEqual(plan, [])


if __name__ == "__main__":
    unittest.main()