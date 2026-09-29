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


class TestLineImageIntersection(unittest.TestCase):
    def test_crossing_the_right_edge(self):
        hit = canvas_geometry.line_image_intersection(
            QPointF(50, 40), QPointF(150, 40), IMG_W, IMG_H
        )
        self.assertEqual((hit.x(), hit.y()), (99, 40))

    def test_crossing_the_bottom_edge(self):
        hit = canvas_geometry.line_image_intersection(
            QPointF(50, 40), QPointF(50, 120), IMG_W, IMG_H
        )
        self.assertEqual((hit.x(), hit.y()), (50, 79))

    def test_diagonal_segment_hits_a_corner_region(self):
        hit = canvas_geometry.line_image_intersection(
            QPointF(90, 70), QPointF(120, 100), IMG_W, IMG_H
        )
        # the closest crossing edge clamps the point inside the image
        self.assertTrue(0 <= hit.x() < IMG_W and 0 <= hit.y() < IMG_H)


class TestSelectionOffsetsAndDrag(unittest.TestCase):
    def test_offsets_reach_the_image_borders(self):
        shapes = [rectangle(10, 10, 50, 40)]
        o1, o2 = canvas_geometry.selection_offsets(
            shapes, QPointF(30, 25), IMG_W, IMG_H
        )
        self.assertEqual((o1.x(), o1.y()), (-20, -15))
        self.assertEqual((o2.x(), o2.y()), (20, 15))

    def test_drag_inside_image_moves_and_reports_position(self):
        shape = rectangle(10, 10, 50, 40)
        offsets = canvas_geometry.selection_offsets(
            [shape], QPointF(30, 25), IMG_W, IMG_H
        )
        moved, new_pos = canvas_geometry.drag_shapes_bounded(
            [shape],
            QPointF(40, 35),
            QPointF(30, 25),
            offsets,
            IMG_W,
            IMG_H,
            frozenset(),
        )
        self.assertTrue(moved)
        self.assertEqual((new_pos.x(), new_pos.y()), (40, 35))
        self.assertEqual(points_of(shape)[0], (20, 20))  # moved +10,+10

    def test_drag_beyond_the_border_is_clamped(self):
        # cursor stays inside the image, but the shape's right edge would
        # cross it -- the drag is clamped so the shape lands on the border
        shape = rectangle(60, 10, 90, 40)  # right edge at x=90
        offsets = canvas_geometry.selection_offsets(
            [shape], QPointF(75, 25), IMG_W, IMG_H
        )
        moved, new_pos = canvas_geometry.drag_shapes_bounded(
            [shape],
            QPointF(98, 25),  # would push the right edge to 113
            QPointF(75, 25),
            offsets,
            IMG_W,
            IMG_H,
            frozenset(),
        )
        self.assertTrue(moved)
        # 85, not 84: the clamp uses pixmap.width() (not width - 1), the
        # same off-by-one the original XXX "shaky" comment in upstream
        # describes -- the shape may end 1px over the border. Pinned as-is.
        self.assertAlmostEqual(new_pos.x(), 85)
        self.assertAlmostEqual(max(p.x() for p in shape.points), 100)

    def test_drag_with_the_cursor_outside_the_image_is_refused(self):
        # upstream behaviour: once the cursor itself leaves the image the
        # drag simply stops (the clamp above only handles in-image cursors)
        shape = rectangle(10, 10, 50, 40)
        offsets = canvas_geometry.selection_offsets(
            [shape], QPointF(30, 25), IMG_W, IMG_H
        )
        moved, _ = canvas_geometry.drag_shapes_bounded(
            [shape],
            QPointF(140, 25),
            QPointF(30, 25),
            offsets,
            IMG_W,
            IMG_H,
            frozenset(),
        )
        self.assertFalse(moved)

    def test_drag_with_locked_shape_only_is_ignored(self):
        shape = rectangle(10, 10, 50, 40)
        shape.locked = True
        moved, _ = canvas_geometry.drag_shapes_bounded(
            [shape],
            QPointF(40, 35),
            QPointF(30, 25),
            ((QPointF(0, 0), QPointF(0, 0))),
            IMG_W,
            IMG_H,
            frozenset(),
        )
        self.assertFalse(moved)

    def test_oop_type_may_leave_the_image(self):
        shape = rectangle(10, 10, 50, 40)
        shape.shape_type = "point"
        moved, _ = canvas_geometry.drag_shapes_bounded(
            [shape],
            QPointF(150, 150),  # far outside
            QPointF(30, 25),
            ((QPointF(0, 0), QPointF(0, 0))),
            IMG_W,
            IMG_H,
            frozenset({"point"}),
        )
        self.assertTrue(moved)  # allowed out of pixmap


class TestMoveVertexBounded(unittest.TestCase):
    def test_rectangle_vertex_keeps_the_opposite_edge_axis(self):
        shape = rectangle(10, 10, 50, 40)
        # vertex 0 (top-left) moves diagonally
        canvas_geometry.move_vertex_bounded(
            shape, 0, QPointF(20, 5), IMG_W, IMG_H, frozenset()
        )
        pts = points_of(shape)
        self.assertEqual(pts[0], (20, 5))
        # top-right follows the x shift, bottom-left the y shift
        self.assertEqual(pts[1], (50, 5))
        self.assertEqual(pts[3], (20, 40))
        self.assertEqual(pts[2], (50, 40))

    def test_vertex_out_of_image_is_clamped_to_the_border(self):
        shape = rectangle(10, 10, 50, 40)
        canvas_geometry.move_vertex_bounded(
            shape, 0, QPointF(-30, 5), IMG_W, IMG_H, frozenset()
        )
        # the vertex lands on the left border, not beyond it
        self.assertGreaterEqual(min(p.x() for p in shape.points), 0)

    def test_generic_shape_moves_one_vertex(self):
        shape = polygon([(10, 10), (50, 10), (50, 40), (10, 40)])
        canvas_geometry.move_vertex_bounded(
            shape, 1, QPointF(60, 10), IMG_W, IMG_H, frozenset()
        )
        self.assertEqual(points_of(shape)[1], (60, 10))
        self.assertEqual(points_of(shape)[0], (10, 10))  # others untouched

    def test_rotation_shape_moves_its_adjacent_corners(self):
        shape = polygon([(10, 10), (50, 10), (50, 40), (10, 40)])
        shape.shape_type = "rotation"
        shape.direction = 0.0
        canvas_geometry.move_vertex_bounded(
            shape, 0, QPointF(5, 5), IMG_W, IMG_H, frozenset()
        )
        pts = points_of(shape)
        # the moved corner and its two adjoints form the rotated rect
        self.assertEqual(pts[0], (5, 5))
        self.assertEqual(pts[1][1], 5)  # p2 shares the moved vertex's y
        self.assertEqual(pts[3][0], 5)  # p4 shares the moved vertex's x


if __name__ == "__main__":
    unittest.main()
