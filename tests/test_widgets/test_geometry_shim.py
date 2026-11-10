"""The view-layer geometry names must be the core implementations.

``views/labeling/utils/shape.py`` re-exports the four array helpers from
``jllabeling.core.labels.geometry`` and keeps only the Qt-bound conversion
code plus the deprecated ``polygons_to_mask`` wrapper.  This test is what
stops a second copy from quietly growing back: importing the view module
pulls Qt, so it cannot live in ``tests/test_utils`` beside the behaviour
tests.
"""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from jllabeling.core.labels import geometry  # noqa: E402
from jllabeling.views.labeling.utils import shape as view_shape  # noqa: E402

HELPERS = (
    "shape_to_mask",
    "shapes_to_label",
    "masks_to_bboxes",
    "rectangle_from_diagonal",
)


class GeometryReExportTest(unittest.TestCase):
    def test_every_helper_is_the_core_object(self):
        for name in HELPERS:
            with self.subTest(helper=name):
                self.assertIs(
                    getattr(view_shape, name),
                    getattr(geometry, name),
                    f"{name} is defined in the view layer again",
                )

    def test_deprecated_wrapper_forwards_to_the_core_mask(self):
        points = [[1, 1], [4, 4]]
        mask = view_shape.polygons_to_mask((6, 6), points, "rectangle")
        expected = geometry.shape_to_mask((6, 6), points, "rectangle")
        self.assertTrue((mask == expected).all())


if __name__ == "__main__":
    unittest.main()
