"""Cuboid geometry and interaction for the Canvas widget.

Split out of canvas.py (batch 8) as a mixin, in the same style as
``BrushCanvasMixin`` / ``CanvasRotationMixin``: the methods are moved
verbatim at their original class indentation, so no transform was applied
and no string content changed.  All cuboid state (default depth vector,
minimum depth) still lives in ``Canvas.__init__``.

The ``CUBOID_*`` constants moved with them; ``canvas.py`` re-imports the
names, so ``tests/test_canvas/test_cuboid_interaction.py`` and the
mouse-event code that predates the split keep importing from ``canvas``.
"""

import math

from PyQt6 import QtCore, QtGui

from .. import utils
from ..shape import Shape


CUBOID_FRONT_EDGE_CENTER_INDICES = {
    Shape.CUBOID_FRONT_LEFT_EDGE_CENTER,
    Shape.CUBOID_FRONT_RIGHT_EDGE_CENTER,
    Shape.CUBOID_FRONT_TOP_EDGE_CENTER,
    Shape.CUBOID_FRONT_BOTTOM_EDGE_CENTER,
}
CUBOID_BACK_EDGE_CENTER_INDICES = {
    Shape.CUBOID_BACK_LEFT_EDGE_CENTER,
    Shape.CUBOID_BACK_RIGHT_EDGE_CENTER,
}
CUBOID_FACE_FRONT = "front"
CUBOID_FACE_RIGHT = "right"
CUBOID_FACE_LEFT = "left"
CUBOID_FACE_TOP = "top"
CUBOID_FACE_BOTTOM = "bottom"
CUBOID_FACE_BACK = "back"


class CuboidCanvasMixin:
    @staticmethod
    def make_rectangle_points(pt1, pt2):
        min_x = min(pt1.x(), pt2.x())
        min_y = min(pt1.y(), pt2.y())
        max_x = max(pt1.x(), pt2.x())
        max_y = max(pt1.y(), pt2.y())
        return [
            QtCore.QPointF(min_x, min_y),
            QtCore.QPointF(max_x, min_y),
            QtCore.QPointF(max_x, max_y),
            QtCore.QPointF(min_x, max_y),
        ]

    def get_cuboid_depth_vector(self, shape):
        depth_vector = shape.get_cuboid_depth_vector()
        return QtCore.QPointF(depth_vector[0], depth_vector[1])

    def cuboid_constraint_margin(self):
        return max(2.0, self.cuboid_min_depth * 0.2)

    def normalize_cuboid_depth(self, depth_vector):
        depth = math.hypot(depth_vector.x(), depth_vector.y())
        if depth >= self.cuboid_min_depth:
            return depth_vector
        if depth <= 1e-6:
            default_depth = QtCore.QPointF(
                self.cuboid_default_depth_vector[0],
                self.cuboid_default_depth_vector[1],
            )
            default_len = math.hypot(default_depth.x(), default_depth.y())
            if default_len <= 1e-6:
                return QtCore.QPointF(self.cuboid_min_depth, 0.0)
            scale = self.cuboid_min_depth / default_len
            return QtCore.QPointF(
                default_depth.x() * scale,
                default_depth.y() * scale,
            )
        scale = self.cuboid_min_depth / depth
        return QtCore.QPointF(
            depth_vector.x() * scale, depth_vector.y() * scale
        )

    def make_cuboid_points(self, front_points, depth_vector):
        depth_vector = self.normalize_cuboid_depth(depth_vector)
        back_points = [p + depth_vector for p in front_points]
        return list(front_points) + back_points

    def set_cuboid_points(
        self, shape, front_points, depth_vector, source="manual"
    ):
        shape.points = self.make_cuboid_points(front_points, depth_vector)
        shape.set_cuboid_depth_vector(
            [depth_vector.x(), depth_vector.y()],
            mode="from_rectangle",
            source=source,
        )

    def set_cuboid_raw_points(self, shape, points):
        shape.points = [QtCore.QPointF(p) for p in points]
        shape.sync_cuboid_depth_vector()

    @staticmethod
    def get_cuboid_back_offsets(shape):
        if shape.shape_type != "cuboid" or len(shape.points) != 8:
            return []
        return [shape.points[i + 4] - shape.points[i] for i in range(4)]

    def set_cuboid_front_with_offsets(self, shape, front_points, offsets):
        if len(front_points) != 4 or len(offsets) != 4:
            return
        points = [QtCore.QPointF(p) for p in front_points]
        points.extend([front_points[i] + offsets[i] for i in range(4)])
        self.set_cuboid_raw_points(shape, points)

    @staticmethod
    def _vector_dot(v1, v2):
        return v1.x() * v2.x() + v1.y() * v2.y()

    @staticmethod
    def _vector_length(v):
        return math.hypot(v.x(), v.y())

    @staticmethod
    def _vector_scale(v, s):
        return QtCore.QPointF(v.x() * s, v.y() * s)

    @staticmethod
    def _solve_vector_basis(target, basis_u, basis_v):
        det = basis_u.x() * basis_v.y() - basis_u.y() * basis_v.x()
        if abs(det) <= 1e-6:
            return None
        coeff_u = (target.x() * basis_v.y() - target.y() * basis_v.x()) / det
        coeff_v = (basis_u.x() * target.y() - basis_u.y() * target.x()) / det
        return coeff_u, coeff_v

    @staticmethod
    def get_mid_point(p1, p2):
        return QtCore.QPointF(
            (p1.x() + p2.x()) / 2.0,
            (p1.y() + p2.y()) / 2.0,
        )

    def cuboid_control_point(self, shape, index):
        if shape.shape_type != "cuboid" or len(shape.points) != 8:
            return None
        return shape.get_cuboid_control_point(index)

    def cuboid_visible_control_indices(self, shape):
        if shape.shape_type != "cuboid" or len(shape.points) != 8:
            return []
        return shape.get_cuboid_visible_control_indices()

    def nearest_cuboid_control(self, shape, pos, epsilon):
        min_distance = float("inf")
        nearest_index = None
        for index in self.cuboid_visible_control_indices(shape):
            control_point = self.cuboid_control_point(shape, index)
            if control_point is None:
                continue
            dist = utils.distance(control_point - pos)
            if dist <= epsilon and dist < min_distance:
                min_distance = dist
                nearest_index = index
        return nearest_index

    @staticmethod
    def cuboid_face_vertex_indices(face_name):
        mapping = {
            CUBOID_FACE_FRONT: [0, 1, 2, 3],
            CUBOID_FACE_RIGHT: [1, 2, 6, 5],
            CUBOID_FACE_LEFT: [0, 4, 7, 3],
            CUBOID_FACE_TOP: [0, 1, 5, 4],
            CUBOID_FACE_BOTTOM: [3, 2, 6, 7],
            CUBOID_FACE_BACK: [4, 5, 6, 7],
        }
        return mapping.get(face_name, [])

    def cuboid_face_path(self, shape, face_name):
        face_indices = self.cuboid_face_vertex_indices(face_name)
        if shape.shape_type != "cuboid" or len(shape.points) != 8:
            return None
        if len(face_indices) != 4:
            return None
        path = QtGui.QPainterPath()
        points = [shape.points[i] for i in face_indices]
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)
        path.closeSubpath()
        return path

    def cuboid_face_hit_test(self, shape, pos):
        if shape.shape_type != "cuboid" or len(shape.points) != 8:
            return None
        depth_vector = self.get_cuboid_depth_vector(shape)
        horizontal_faces = [CUBOID_FACE_RIGHT, CUBOID_FACE_LEFT]
        if depth_vector.x() < 0:
            horizontal_faces = [CUBOID_FACE_LEFT, CUBOID_FACE_RIGHT]
        face_order = horizontal_faces + [CUBOID_FACE_BACK]
        for face_name in face_order:
            face_path = self.cuboid_face_path(shape, face_name)
            if face_path is not None and face_path.contains(pos):
                return face_name
        return None

    def adjust_cuboid_visible_back_vertex(self, shape, index, pos):
        if shape.shape_type != "cuboid" or len(shape.points) != 8:
            return
        visible_rear = shape.get_cuboid_visible_rear_edge_indices()
        if len(visible_rear) != 2 or index not in visible_rear:
            return
        top_index, bottom_index = visible_rear
        points = [QtCore.QPointF(p) for p in shape.points]
        margin = self.cuboid_constraint_margin()
        top_indices = [0, 1, 4, 5]
        bottom_indices = [2, 3, 6, 7]
        if index == top_index:
            dy = pos.y() - points[top_index].y()
            max_dy = min(
                points[bottom_i].y() - margin - points[top_i].y()
                for top_i, bottom_i in zip(top_indices, bottom_indices)
            )
            dy = min(dy, max_dy)
            for top_i in top_indices:
                points[top_i].setY(points[top_i].y() + dy)
        else:
            dy = pos.y() - points[bottom_index].y()
            min_dy = max(
                points[top_i].y() + margin - points[bottom_i].y()
                for top_i, bottom_i in zip(top_indices, bottom_indices)
            )
            dy = max(dy, min_dy)
            for bottom_i in bottom_indices:
                points[bottom_i].setY(points[bottom_i].y() + dy)
        self.set_cuboid_raw_points(shape, points)

    def adjust_cuboid_front_vertex(self, shape, index, pos):
        if shape.shape_type != "cuboid" or len(shape.points) != 8:
            return
        if index not in [0, 1, 2, 3]:
            return
        front_points = [QtCore.QPointF(p) for p in shape.points[:4]]
        offsets = self.get_cuboid_back_offsets(shape)
        min_size = self.cuboid_constraint_margin()
        order = [index, (index + 1) % 4, (index + 2) % 4, (index + 3) % 4]
        p0 = QtCore.QPointF(front_points[order[0]])
        p1 = QtCore.QPointF(front_points[order[1]])
        p2 = QtCore.QPointF(front_points[order[2]])
        p3 = QtCore.QPointF(front_points[order[3]])
        basis_u = p1 - p0
        basis_v = p3 - p0
        len_u = self._vector_length(basis_u)
        len_v = self._vector_length(basis_v)
        if len_u <= 1e-6 or len_v <= 1e-6:
            return
        unit_u = self._vector_scale(basis_u, 1.0 / len_u)
        unit_v = self._vector_scale(basis_v, 1.0 / len_v)
        target = p2 - pos
        solved = self._solve_vector_basis(target, unit_u, unit_v)
        if solved is None:
            return
        coeff_u, coeff_v = solved
        coeff_u = max(coeff_u, min_size)
        coeff_v = max(coeff_v, min_size)
        new_p0 = (
            p2
            - self._vector_scale(unit_u, coeff_u)
            - self._vector_scale(unit_v, coeff_v)
        )
        new_p1 = p2 - self._vector_scale(unit_v, coeff_v)
        new_p3 = p2 - self._vector_scale(unit_u, coeff_u)
        front_points[order[0]] = new_p0
        front_points[order[1]] = new_p1
        front_points[order[3]] = new_p3
        front_points[order[2]] = p2
        self.set_cuboid_front_with_offsets(shape, front_points, offsets)

    def adjust_cuboid_front_edge(self, shape, index, pos):
        if shape.shape_type != "cuboid" or len(shape.points) != 8:
            return
        front_points = [QtCore.QPointF(p) for p in shape.points[:4]]
        offsets = self.get_cuboid_back_offsets(shape)
        min_size = self.cuboid_constraint_margin()
        edge_map = {
            Shape.CUBOID_FRONT_LEFT_EDGE_CENTER: (0, 3, 1, 2),
            Shape.CUBOID_FRONT_RIGHT_EDGE_CENTER: (1, 2, 0, 3),
            Shape.CUBOID_FRONT_TOP_EDGE_CENTER: (0, 1, 3, 2),
            Shape.CUBOID_FRONT_BOTTOM_EDGE_CENTER: (3, 2, 0, 1),
        }
        if index not in edge_map:
            return
        edge_a, edge_b, opposite_a, opposite_b = edge_map[index]
        dragged_center = self.get_mid_point(
            front_points[edge_a], front_points[edge_b]
        )
        edge_vector = front_points[edge_b] - front_points[edge_a]
        edge_length = self._vector_length(edge_vector)
        if edge_length <= 1e-6:
            return
        normal = QtCore.QPointF(
            -edge_vector.y() / edge_length,
            edge_vector.x() / edge_length,
        )
        edge_distance = self._vector_dot(
            front_points[opposite_a] - front_points[edge_a], normal
        )
        if edge_distance < 0:
            normal = self._vector_scale(normal, -1.0)
            edge_distance = -edge_distance
        shift = self._vector_dot(pos - dragged_center, normal)
        max_shift = edge_distance - min_size
        if shift > max_shift:
            shift = max_shift
        shift_vector = self._vector_scale(normal, shift)
        front_points[edge_a] = front_points[edge_a] + shift_vector
        front_points[edge_b] = front_points[edge_b] + shift_vector
        self.set_cuboid_front_with_offsets(shape, front_points, offsets)

    def adjust_cuboid_back_edge_center(self, shape, index, pos):
        if shape.shape_type != "cuboid" or len(shape.points) != 8:
            return
        visible_center_index = shape.get_cuboid_visible_rear_center_index()
        if index != visible_center_index:
            return
        points = [QtCore.QPointF(p) for p in shape.points]
        center = shape.get_cuboid_control_point(index)
        if center is None:
            return
        margin = self.cuboid_constraint_margin()
        front_right = max(points[1].x(), points[2].x())
        front_left = min(points[0].x(), points[3].x())
        target_x = pos.x()
        front_center_index = Shape.CUBOID_FRONT_RIGHT_EDGE_CENTER
        if index == Shape.CUBOID_BACK_RIGHT_EDGE_CENTER:
            target_x = max(target_x, front_right + margin)
        else:
            target_x = min(target_x, front_left - margin)
            front_center_index = Shape.CUBOID_FRONT_LEFT_EDGE_CENTER
        dx = target_x - center.x()
        front_center = shape.get_cuboid_control_point(front_center_index)
        dy = 0.0
        if front_center is not None:
            dir_x = center.x() - front_center.x()
            if abs(dir_x) > 1e-6:
                dir_y = center.y() - front_center.y()
                dy = dx * dir_y / dir_x
        for i in range(4, 8):
            points[i].setX(points[i].x() + dx)
            points[i].setY(points[i].y() + dy)
        self.set_cuboid_raw_points(shape, points)

    def move_cuboid_control(self, shape, index, pos):
        if (
            shape.locked
            or shape.shape_type != "cuboid"
            or len(shape.points) != 8
        ):
            return
        if index in [0, 1, 2, 3]:
            self.adjust_cuboid_front_vertex(shape, index, pos)
            return
        if index in [4, 5, 6, 7]:
            self.adjust_cuboid_visible_back_vertex(shape, index, pos)
            return
        if index in CUBOID_FRONT_EDGE_CENTER_INDICES:
            self.adjust_cuboid_front_edge(shape, index, pos)
            return
        if index in CUBOID_BACK_EDGE_CENTER_INDICES:
            self.adjust_cuboid_back_edge_center(shape, index, pos)

    def move_cuboid_face_by(self, shape, face_name, offset):
        if (
            shape.locked
            or shape.shape_type != "cuboid"
            or len(shape.points) != 8
        ):
            return
        min_size = self.cuboid_constraint_margin()
        if face_name == CUBOID_FACE_LEFT:
            points = [QtCore.QPointF(p) for p in shape.points]
            front_right_mid = (points[1].x() + points[2].x()) / 2.0
            back_right_mid = (points[5].x() + points[6].x()) / 2.0
            right_top, right_bottom = (1, 2)
            if back_right_mid > front_right_mid:
                right_top, right_bottom = (5, 6)
            right_candidates = [
                points[right_top].x(),
                (points[right_top].x() + points[right_bottom].x()) / 2.0,
                points[right_bottom].x(),
            ]
            right_limit_x = min(right_candidates) - min_size
            left_indices = [0, 3, 4, 7]
            left_max_x = max(points[i].x() for i in left_indices)
            dx = offset.x()
            if dx > 0:
                dx = min(dx, right_limit_x - left_max_x)
            dy = offset.y()
            for i in left_indices:
                points[i].setX(points[i].x() + dx)
                points[i].setY(points[i].y() + dy)
            self.set_cuboid_raw_points(shape, points)
        elif face_name == CUBOID_FACE_RIGHT:
            points = [QtCore.QPointF(p) for p in shape.points]
            front_left_mid = (points[0].x() + points[3].x()) / 2.0
            back_left_mid = (points[4].x() + points[7].x()) / 2.0
            left_top, left_bottom = (0, 3)
            if back_left_mid < front_left_mid:
                left_top, left_bottom = (4, 7)
            left_candidates = [
                points[left_top].x(),
                (points[left_top].x() + points[left_bottom].x()) / 2.0,
                points[left_bottom].x(),
            ]
            left_limit_x = max(left_candidates) + min_size
            right_indices = [1, 2, 5, 6]
            right_min_x = min(points[i].x() for i in right_indices)
            dx = offset.x()
            if dx < 0:
                dx = max(dx, left_limit_x - right_min_x)
            dy = offset.y()
            for i in right_indices:
                points[i].setX(points[i].x() + dx)
                points[i].setY(points[i].y() + dy)
            self.set_cuboid_raw_points(shape, points)
        elif face_name == CUBOID_FACE_BACK:
            points = [QtCore.QPointF(p) for p in shape.points]
            next_back_points = [QtCore.QPointF(points[i]) for i in range(4, 8)]
            for p in next_back_points:
                p.setX(p.x() + offset.x())
                p.setY(p.y() + offset.y())
            for i, p in enumerate(next_back_points, start=4):
                points[i] = p
            self.set_cuboid_raw_points(shape, points)
        else:
            return
