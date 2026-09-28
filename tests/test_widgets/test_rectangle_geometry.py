"""Rectangle geometry: the domain math, tested without a widget.

These functions used to live on ``Canvas`` and were only reachable
through a full offscreen widget with a loaded pixmap.  As plain
functions taking ``(shape, img_width, img_height, ...)`` they pin the
wheel-editing behaviour -- clip to image, scale from center, edge
adjust -- directly.
"""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from PyQt6.QtCore import QPointF  # noqa: E402

from anylabeling.views.labeling.shape import Shape  # noqa: E402
from anylabeling.views.labeling.widgets import rectangle_geometry  # noqa: E402

IMG_W, IMG_H = 100, 80


def rectangle(x0, y0, x1, y1):
    shape = Shape(label="box", shape_type="rectangle")
    shape.points = [
        QPointF(x0, y0),
        QPointF(x1, y0),
        QPointF(x1, y1),
        QPointF(x0, y1),
    ]
    return shape


def points_of(shape):
    return [(p.x(), p.y()) for p in shape.points]


class TestClipRectangleToPixmap(unittest.TestCase):
    def test_inside_image_is_untouched(self):
        shape = rectangle(10, 10, 50, 40)
        self.assertTrue(
            rectangle_geometry.clip_rectangle_to_pixmap(shape, IMG_W, IMG_H)
        )
        self.assertEqual(
            points_of(shape),
            [(10, 10), (50, 10), (50, 40), (10, 40)],
        )

    def test_overflowing_rectangle_is_clamped(self):
        shape = rectangle(-5, -5, 150, 90)
        self.assertTrue(
            rectangle_geometry.clip_rectangle_to_pixmap(shape, IMG_W, IMG_H)
        )
        self.assertEqual(
            points_of(shape),
            [(0, 0), (99, 0), (99, 79), (0, 79)],
        )

    def test_fully_outside_cannot_be_clipped(self):
        shape = rectangle(200, 200, 300, 300)
        original = points_of(shape)
        self.assertFalse(
            rectangle_geometry.clip_rectangle_to_pixmap(shape, IMG_W, IMG_H)
        )
        self.assertEqual(points_of(shape), original)


class TestScaleFromCenter(unittest.TestCase):
    def test_scale_down_keeps_center(self):
        shape = rectangle(10, 10, 50, 50)  # center (30, 30)
        self.assertTrue(
            rectangle_geometry.scale_from_center(
                shape, False, 0.5, IMG_W, IMG_H
            )
        )
        xs = [p.x() for p in shape.points]
        ys = [p.y() for p in shape.points]
        self.assertAlmostEqual(sum(xs) / 4, 30)
        self.assertAlmostEqual(sum(ys) / 4, 30)
        self.assertAlmostEqual(max(xs) - min(xs), 20)  # 40 * 0.5

    def test_scale_up_out_of_image_is_atomic(self):
        shape = rectangle(10, 10, 50, 50)  # scaling up leaves the image
        original = points_of(shape)
        self.assertFalse(
            rectangle_geometry.scale_from_center(
                shape, True, 2.0, IMG_W, IMG_H
            )
        )
        self.assertEqual(points_of(shape), original)

    def test_scale_factor_never_below_point_one(self):
        shape = rectangle(10, 10, 50, 50)
        self.assertTrue(
            rectangle_geometry.scale_from_center(
                shape, False, 5.0, IMG_W, IMG_H
            )
        )
        width = max(p.x() for p in shape.points) - min(
            p.x() for p in shape.points
        )
        self.assertAlmostEqual(width, 40 * 0.1)  # max(0.1, 1 - 5)


class TestAdjustEdge(unittest.TestCase):
    def test_cursor_inside_picks_nearest_edge_and_clamps(self):
        shape = rectangle(10, 10, 50, 40)
        rectangle_geometry.adjust_edge(
            shape,
            QPointF(12, 25),  # near the left edge, inside
            True,
            2.0,
            IMG_W,
            IMG_H,
        )
        # left edge moved outward by 2; right edge untouched
        self.assertAlmostEqual(min(p.x() for p in shape.points), 8)
        self.assertAlmostEqual(max(p.x() for p in shape.points), 50)
        self.assertEqual([p.y() for p in shape.points], [10, 10, 40, 40])

    def test_left_edge_clamps_at_zero(self):
        shape = rectangle(1, 10, 50, 40)
        rectangle_geometry.adjust_edge(
            shape, QPointF(11, 25), True, 5.0, IMG_W, IMG_H
        )
        self.assertAlmostEqual(min(p.x() for p in shape.points), 0)

    def test_right_edge_clamps_at_width_minus_one(self):
        shape = rectangle(10, 10, 98, 40)
        rectangle_geometry.adjust_edge(
            shape, QPointF(97, 25), True, 5.0, IMG_W, IMG_H
        )
        self.assertAlmostEqual(max(p.x() for p in shape.points), 99)

    def test_move_inward_shrinks(self):
        shape = rectangle(10, 10, 50, 40)
        rectangle_geometry.adjust_edge(
            shape, QPointF(12, 25), False, 2.0, IMG_W, IMG_H
        )
        self.assertAlmostEqual(min(p.x() for p in shape.points), 12)


if __name__ == "__main__":
    unittest.main()
