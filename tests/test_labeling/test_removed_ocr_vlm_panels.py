"""Guards for the removal of the OCR / document / VLM panels.

Upstream shipped PaddleOCR, PPOCR-KIE, VQA, chatbot and document-parsing
panels.  This fork removed the panels early on, but the KIE linking field they
left behind survived in the shape model, the label dialog, the canvas painter
and the overview table -- a hidden "linking" box in the label dialog was the
last visible piece.  These tests pin the removal so it cannot creep back, and
pin what happens to legacy files, which is the one thing a deletion like this
can get wrong.
"""

import os
import unittest

from jllabeling.views.labeling.shape import Shape
from jllabeling.views.labeling.widgets.label_dialog import LabelDialog

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

GONE_PAGES = (
    "docs/en/chatbot.md",
    "docs/en/paddle_ocr.md",
    "docs/en/vqa.md",
    "docs/zh_cn/chatbot.md",
    "docs/zh_cn/paddle_ocr.md",
    "docs/zh_cn/vqa.md",
)

GONE_EXAMPLES = (
    "examples/optical_character_recognition",
    "examples/vision_language",
    "examples/description",
)


class TestKieLinkingIsGone(unittest.TestCase):
    def test_new_shapes_do_not_carry_the_field(self):
        shape = Shape(label="text", shape_type="rectangle")
        self.assertFalse(hasattr(shape, "kie_linking"))
        self.assertNotIn("kie_linking", shape.to_dict())

    def test_legacy_files_still_load_and_keep_their_data(self):
        """Old labels must open, and must not lose the field on save.

        ``kie_linking`` is no longer a known key, so it lands in
        ``other_data`` and is written back untouched.  Dropping the feature
        must not silently rewrite someone's OCR labels.
        """
        data = {
            "label": "value",
            "points": [[1.0, 2.0], [3.0, 4.0]],
            "shape_type": "rectangle",
            "kie_linking": [[1, 2]],
        }
        shape = Shape()
        shape.load_from_dict(data)
        self.assertFalse(hasattr(shape, "kie_linking"))
        self.assertEqual(shape.other_data["kie_linking"], [[1, 2]])
        self.assertEqual(shape.to_dict()["kie_linking"], [[1, 2]])

    def test_dialog_no_longer_has_the_linking_widgets(self):
        for name in (
            "get_kie_linking",
            "add_linking_pair",
            "reset_linking",
            "remove_linking_item",
        ):
            self.assertFalse(
                hasattr(LabelDialog, name),
                f"LabelDialog.{name} came back with the KIE panel",
            )


class TestRemovedPagesStayRemoved(unittest.TestCase):
    def test_documentation_pages_are_gone(self):
        for relative in GONE_PAGES:
            self.assertFalse(
                os.path.exists(os.path.join(REPO_ROOT, relative)),
                f"{relative} documents a panel this build does not have",
            )

    def test_example_directories_are_gone(self):
        for relative in GONE_EXAMPLES:
            self.assertFalse(
                os.path.exists(os.path.join(REPO_ROOT, relative)),
                f"{relative} ships OCR/VLM examples for absent panels",
            )


if __name__ == "__main__":
    unittest.main()
