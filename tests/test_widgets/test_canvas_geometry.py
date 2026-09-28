"""Canvas geometry: the domain math, tested without a widget.

These functions used to live on ``Canvas`` and were only reachable
through a full offscreen widget with a loaded pixmap.  As plain
functions taking ``(shape, img_width, img_height, ...)`` (plus the
visibility predicate and the cuboid lookups for the hit test) they pin
the wheel-editing behaviour and the click hit-test directly.
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
from anylabeling.views.labeling.widgets import canvas_geometry  # noqa: E402

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
            canvas_geometry.clip_rectangle_to_pixmap(shape, IMG_W, IMG_H)
        )
        self.assertEqual(
            points_of(shape),
            [(10, 10), (50, 10), (50, 40), (10, 40)],
        )

    def test_overflowing_rectangle_is_clamped(self):
        shape = rectangle(-5, -5, 150, 90)
        self.assertTrue(
            canvas_geometry.clip_rectangle_to_pixmap(shape, IMG_W, IMG_H)
        )
        self.assertEqual(
            points_of(shape),
            [(0, 0), (99, 0), (99, 79), (0, 79)],
        )

    def test_fully_outside_cannot_be_clipped(self):
        shape = rectangle(200, 200, 300, 300)
        original = points_of(shape)
        self.assertFalse(
            canvas_geometry.clip_rectangle_to_pixmap(shape, IMG_W, IMG_H)
        )
        self.assertEqual(points_of(shape), original)


class TestScaleFromCenter(unittest.TestCase):
    def test_scale_down_keeps_center(self):
        shape = rectangle(10, 10, 50, 50)  # center (30, 30)
        self.assertTrue(
            canvas_geometry.scale_from_center(shape, False, 0.5, IMG_W, IMG_H)
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
            canvas_geometry.scale_from_center(shape, True, 2.0, IMG_W, IMG_H)
        )
        self.assertEqual(points_of(shape), original)

    def test_scale_factor_never_below_point_one(self):
        shape = rectangle(10, 10, 50, 50)
        self.assertTrue(
            canvas_geometry.scale_from_center(shape, False, 5.0, IMG_W, IMG_H)
        )
        width = max(p.x() for p in shape.points) - min(
            p.x() for p in shape.points
        )
        self.assertAlmostEqual(width, 40 * 0.1)  # max(0.1, 1 - 5)


class TestAdjustEdge(unittest.TestCase):
    def test_cursor_inside_picks_nearest_edge_and_clamps(self):
        shape = rectangle(10, 10, 50, 40)
        canvas_geometry.adjust_edge(
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
        canvas_geometry.adjust_edge(
            shape, QPointF(11, 25), True, 5.0, IMG_W, IMG_H
        )
        self.assertAlmostEqual(min(p.x() for p in shape.points), 0)

    def test_right_edge_clamps_at_width_minus_one(self):
        shape = rectangle(10, 10, 98, 40)
        canvas_geometry.adjust_edge(
            shape, QPointF(97, 25), True, 5.0, IMG_W, IMG_H
        )
        self.assertAlmostEqual(max(p.x() for p in shape.points), 99)

    def test_move_inward_shrinks(self):
        shape = rectangle(10, 10, 50, 40)
        canvas_geometry.adjust_edge(
            shape, QPointF(12, 25), False, 2.0, IMG_W, IMG_H
        )
        self.assertAlmostEqual(min(p.x() for p in shape.points), 12)


def polygon(points):
    shape = Shape(label="poly", shape_type="polygon")
    shape.points = [QPointF(x, y) for x, y in points]
    return shape


class TestHitCandidates(unittest.TestCase):
    def setUp(self):
        self.visible_all = lambda shape: True

    def test_vertex_hit_beats_body_hit(self):
        # big polygon first in stack; small one whose vertex sits on the
        # big one's body -- the vertex wins despite the smaller area.
        big = polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
        small = polygon([(40, 0), (60, 0), (60, 20), (40, 20)])
        hits = canvas_geometry.hit_candidates(
            [big, small], QPointF(50, 1), 6.0, self.visible_all
        )
        self.assertEqual(hits[0], small)

    def test_later_stack_position_wins_a_tie(self):
        a = polygon([(0, 0), (40, 0), (40, 40), (0, 40)])
        b = polygon([(0, 0), (40, 0), (40, 40), (0, 40)])
        hits = canvas_geometry.hit_candidates(
            [a, b], QPointF(20, 20), 6.0, self.visible_all
        )
        self.assertEqual(hits, [b, a])

    def test_hidden_shapes_are_skipped(self):
        a = polygon([(0, 0), (40, 0), (40, 40), (0, 40)])
        hits = canvas_geometry.hit_candidates(
            [a], QPointF(20, 20), 6.0, lambda shape: False
        )
        self.assertEqual(hits, [])

    def test_locked_shape_still_hits_by_body(self):
        a = polygon([(0, 0), (40, 0), (40, 40), (0, 40)])
        a.locked = True
        hits = canvas_geometry.hit_candidates(
            [a], QPointF(20, 20), 6.0, self.visible_all
        )
        self.assertEqual(hits, [a])

    def test_no_hit_outside_the_shape(self):
        a = polygon([(0, 0), (40, 0), (40, 40), (0, 40)])
        hits = canvas_geometry.hit_candidates(
            [a], QPointF(90, 90), 6.0, self.visible_all
        )
        self.assertEqual(hits, [])

    def test_cuboid_face_hit_goes_through_the_callback(self):
        a = polygon([(0, 0), (40, 0), (40, 40), (0, 40)])
        a.shape_type = "cuboid"
        a.points = [QPointF(x, y) for x, y in [(0, 0)] * 8]
        hits = canvas_geometry.hit_candidates(
            [a],
            QPointF(20, 20),
            6.0,
            self.visible_all,
            cuboid_face_hit=lambda shape, pt: True,
        )
        self.assertEqual(hits, [a])

    def test_cuboid_without_callback_never_body_hits(self):
        a = polygon([(0, 0), (40, 0), (40, 40), (0, 40)])
        a.shape_type = "cuboid"
        a.points = [QPointF(x, y) for x, y in [(0, 0)] * 8]
        hits = canvas_geometry.hit_candidates(
            [a], QPointF(20, 20), 6.0, self.visible_all
        )
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
