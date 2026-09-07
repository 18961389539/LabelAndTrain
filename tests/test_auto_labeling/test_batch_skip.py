import json
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from anylabeling.views.labeling.utils.batch import image_has_annotations

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestImageHasAnnotations(unittest.TestCase):
    def test_true_when_shapes_exist(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            image = os.path.join(tmp, "a.jpg")
            label = os.path.join(tmp, "a.json")
            open(image, "wb").close()
            with open(label, "w", encoding="utf-8") as handle:
                json.dump({"shapes": [{"label": "cat"}]}, handle)
            self.assertTrue(image_has_annotations(image))

    def test_false_when_json_missing_or_empty(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            image = os.path.join(tmp, "a.jpg")
            open(image, "wb").close()
            self.assertFalse(image_has_annotations(image))
            with open(
                os.path.join(tmp, "a.json"), "w", encoding="utf-8"
            ) as handle:
                json.dump({"shapes": []}, handle)
            self.assertFalse(image_has_annotations(image))
