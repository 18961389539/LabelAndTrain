"""Rotation-handle behaviour for the Canvas widget.

Split out of canvas.py (batch 5-1) as a mixin so the methods stay on the
Canvas class: the paint / mouse-event entry points and the tests keep
calling ``canvas._rotation_handle_*`` unchanged. The drag state
(``_rotation_drag_shape`` / ``_rotation_drag_prev_angle``) still lives in
``Canvas.__init__``.
"""

import math

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt

from .. import utils
from ..shape import Shape

CURSOR_DEFAULT = QtCore.Qt.CursorShape.ArrowCursor
CURSOR_POINT = QtCore.Qt.CursorShape.PointingHandCursor
CURSOR_DRAW = QtCore.Qt.CursorShape.CrossCursor
CURSOR_MOVE = QtCore.Qt.CursorShape.ClosedHandCursor
CURSOR_GRAB = QtCore.Qt.CursorShape.OpenHandCursor

ROTATION_HANDLE_DISTANCE = 32.0
ROTATION_HANDLE_HIT_RADIUS = 10.0
ROTATION_HANDLE_SNAP_DEGREES = 15.0


class CanvasRotationMixin:
    """Rotation-handle rendering, hit-testing and dragging."""

    def clip_rotation_to_pixmap(self, shape):
        """Clip an axis-aligned rotation shape's bounding box to pixmap boundaries.

        Only clamps shapes whose direction is zero, i.e. freshly drawn in
        manual mode before any rotation has been applied.

        Args:
            shape (Shape): The rotation shape to clip.

        Returns:
            bool: True if the resulting shape is valid, False if it degenerates
                to zero area and should be discarded.
        """
        if self.pixmap is None or shape.shape_type != "rotation":
            return True
        if shape.direction != 0:
            return True
        if len(shape.points) != 4:
            return True

        w, h = self.pixmap.width(), self.pixmap.height()
        x_coords = [p.x() for p in shape.points]
        y_coords = [p.y() for p in shape.points]
        min_x, max_x = min(x_coords), max(x_coords)
        min_y, max_y = min(y_coords), max(y_coords)

        clipped_min_x = max(0, min_x)
        clipped_min_y = max(0, min_y)
        clipped_max_x = min(w - 1, max_x)
        clipped_max_y = min(h - 1, max_y)

        if clipped_max_x <= clipped_min_x or clipped_max_y <= clipped_min_y:
            return False

        shape.points = [
            QtCore.QPointF(clipped_min_x, clipped_min_y),
            QtCore.QPointF(clipped_max_x, clipped_min_y),
            QtCore.QPointF(clipped_max_x, clipped_max_y),
            QtCore.QPointF(clipped_min_x, clipped_max_y),
        ]
        shape.center = QtCore.QPointF(
            (clipped_min_x + clipped_max_x) / 2,
            (clipped_min_y + clipped_max_y) / 2,
        )
        return True

    def _paint_rotation_handles(self, p):
        for shape in self._rotation_handle_shapes():
            self._paint_rotation_handle(p, shape)

    def _paint_rotation_handle(self, p, shape):
        geometry = self._rotation_handle_geometry(shape)
        if geometry is None:
            return
        _, handle, _ = geometry
        scale = max(self.scale, 1e-6)
        vertex_radius = Shape.point_size / (2.0 * scale)
        vertex_pen_width = max(1.0 / scale, float(shape.line_width) / scale)
        radius = vertex_radius + vertex_pen_width / 2.0
        hovered = shape in (self.h_rotation_shape, self._rotation_drag_shape)
        ring_width = (vertex_pen_width / 2.0) * (2.2 if hovered else 1.0)
        inner_radius = max(0.5 / scale, radius - ring_width)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QColor(0, 0, 0, 255))
        p.drawEllipse(handle, radius, radius)
        p.setBrush(QtGui.QColor(255, 255, 255, 255))
        p.drawEllipse(handle, inner_radius, inner_radius)

    @staticmethod
    def _rotation_shape_center(shape):
        return QtCore.QPointF(
            (shape.points[0].x() + shape.points[2].x()) / 2.0,
            (shape.points[0].y() + shape.points[2].y()) / 2.0,
        )

    def _rotation_handle_geometry(self, shape):
        if (
            shape is None
            or shape.shape_type != "rotation"
            or len(shape.points) != 4
        ):
            return None
        p0, p1 = shape.points[0], shape.points[1]
        dx = p1.x() - p0.x()
        dy = p1.y() - p0.y()
        edge_length = math.hypot(dx, dy)
        if edge_length < 1e-6:
            return None
        edge_mid = QtCore.QPointF(
            (p0.x() + p1.x()) / 2.0,
            (p0.y() + p1.y()) / 2.0,
        )
        normal_x = dy / edge_length
        normal_y = -dx / edge_length
        distance = ROTATION_HANDLE_DISTANCE / max(self.scale, 1e-6)
        handle = QtCore.QPointF(
            edge_mid.x() + normal_x * distance,
            edge_mid.y() + normal_y * distance,
        )
        return edge_mid, handle, self._rotation_shape_center(shape)

    def _rotation_handle_shapes(self):
        candidates = []
        for shape in self.selected_shapes:
            if shape not in candidates:
                candidates.append(shape)
        for shape in (self.h_shape, self.h_rotation_shape):
            if shape is not None and shape not in candidates:
                candidates.append(shape)
        return sorted(
            [
                shape
                for shape in candidates
                if shape in self.shapes
                and not shape.locked
                and shape.visible
                and self.is_visible(shape)
                and shape.shape_type == "rotation"
                and len(shape.points) == 4
            ],
            key=lambda shape: self.shapes.index(shape),
            reverse=True,
        )

    def _rotation_handle_shape_at(self, pos):
        hit_radius = ROTATION_HANDLE_HIT_RADIUS / max(self.scale, 1e-6)
        for shape in self._rotation_handle_shapes():
            geometry = self._rotation_handle_geometry(shape)
            if geometry is None:
                continue
            edge_mid, handle, _ = geometry
            if utils.distance(handle - pos) <= hit_radius:
                return shape
            if utils.distance_to_line(pos, [edge_mid, handle]) <= hit_radius:
                return shape
        return None

    def _set_rotation_handle_hover(self, shape):
        if self.h_shape is not None:
            self.h_shape.highlight_clear()
        self.prev_h_vertex = self.h_vertex
        self.h_vertex = None
        self.prev_h_shape = self.h_shape = shape
        self.prev_h_edge = self.h_edge
        self.h_edge = None
        self.prev_h_cuboid_face = self.h_cuboid_face
        self.h_cuboid_face = None
        self.prev_h_rotation_shape = self.h_rotation_shape
        self.h_rotation_shape = shape
        self.override_cursor(CURSOR_POINT)
        self.setToolTip(
            self.tr("Click & drag to rotate shape '%s'") % shape.label
        )
        self.setStatusTip(self.toolTip())
        self.update()

    def _rotation_mouse_angle(self, shape, pos):
        if shape is None or len(shape.points) != 4:
            return None
        center = self._rotation_shape_center(shape)
        return math.atan2(pos.y() - center.y(), pos.x() - center.x())

    @staticmethod
    def _snap_rotation_angle(angle):
        step = math.radians(ROTATION_HANDLE_SNAP_DEGREES)
        return round(angle / step) * step

    def _start_rotation_handle_drag(
        self, shape, pos, multiple_selection_mode, modifiers
    ):
        self.set_hiding()
        if shape not in self.selected_shapes:
            if multiple_selection_mode:
                self.selection_changed.emit(self.selected_shapes + [shape])
            else:
                self.selection_changed.emit([shape])
            self.h_shape_is_selected = False
        else:
            self.h_shape_is_selected = True
        self.h_shape = shape
        self.h_rotation_shape = shape
        self.h_vertex = None
        self.h_edge = None
        self.h_cuboid_face = None
        angle = self._rotation_mouse_angle(shape, pos)
        if angle is None:
            return
        if modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier:
            angle = self._snap_rotation_angle(angle)
        self._rotation_drag_shape = shape
        self._rotation_drag_prev_angle = angle
        self.prev_point = pos
        self.calculate_offsets(pos)
        self.override_cursor(CURSOR_MOVE)

    def _update_rotation_handle_drag(self, pos, modifiers):
        shape = self._rotation_drag_shape
        if shape is None or shape.locked:
            return
        angle = self._rotation_mouse_angle(shape, pos)
        if angle is None or self._rotation_drag_prev_angle is None:
            return
        if modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier:
            angle = self._snap_rotation_angle(angle)
        theta = self._rotation_drag_prev_angle - angle
        if abs(theta) < 1e-9:
            return
        if self.bounded_rotate_shapes(0, shape, theta):
            self._rotation_drag_prev_angle = angle
            self.rotating_shape = True
            self.h_shape = shape
            self.h_rotation_shape = shape
            self.repaint()

    def _store_rotated_shape(self, shape):
        if shape is None or shape not in self.shapes:
            return
        index = self.shapes.index(shape)
        if (
            self.shapes_backups
            and index < len(self.shapes_backups[-1])
            and self.shapes_backups[-1][index].points
            != self.shapes[index].points
        ):
            self.store_shapes()
            self.shape_rotated.emit()

    def _finish_rotation_handle_drag(self):
        shape = self._rotation_drag_shape
        self._rotation_drag_shape = None
        self._rotation_drag_prev_angle = None
        if self.rotating_shape:
            self._store_rotated_shape(shape)
            self.rotating_shape = False
        self.override_cursor(CURSOR_POINT)
        self.update()
