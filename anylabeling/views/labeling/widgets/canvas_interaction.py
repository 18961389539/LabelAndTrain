"""Interaction state and event handlers for the labeling canvas."""

import math

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QWheelEvent

from anylabeling.services.auto_labeling.types import AutoLabelingMode
from anylabeling.views.labeling.utils.qt import new_icon_path

from .. import utils
from ..shape import Shape
from . import canvas_geometry
from .canvas_cuboid import (
    CUBOID_BACK_EDGE_CENTER_INDICES,
    CUBOID_FACE_FRONT,
)
from .canvas_rotation import (
    CURSOR_DEFAULT,
    CURSOR_DRAW,
    CURSOR_GRAB,
    CURSOR_MOVE,
    CURSOR_POINT,
)

AUTO_DECODE_DELAY_MS = 100
MAX_AUTO_DECODE_MARKS = 42
AUTO_DECODE_MOVE_THRESHOLD = 5.0
MOVE_SPEED = 5.0


class _InteractionField:
    """Delegate one historical Canvas attribute to its interaction state."""

    def __init__(self, name):
        self.name = name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        return getattr(obj.interaction_state, self.name)

    def __set__(self, obj, value):
        setattr(obj.interaction_state, self.name, value)


class CanvasInteractionState:
    """Transient drawing, selection, hover, drag and keyboard state."""

    def __init__(self, edit_mode):
        self.mode = edit_mode
        self.is_move_editing = False
        self.current = None
        self.selected_shapes = []
        self.selected_shapes_copy = []
        self.line = Shape()
        self.prev_point = QtCore.QPointF()
        self.prev_pan_point = QtCore.QPointF()
        self.prev_move_point = QtCore.QPointF()
        self._space_pressed = False
        self._space_panning = False
        self._space_pan_prev_point = None
        self._space_pan_suppress_until_release = False
        self._vertex_erasing = False
        self._vertex_eraser_cursor_cache = None
        self.offsets = QtCore.QPointF(), QtCore.QPointF()
        self.h_shape = None
        self.prev_h_shape = None
        self.h_vertex = None
        self.prev_h_vertex = None
        self.h_edge = None
        self.prev_h_edge = None
        self.h_cuboid_face = None
        self.prev_h_cuboid_face = None
        self.h_rotation_shape = None
        self.prev_h_rotation_shape = None
        self.moving_shape = False
        self._pending_edge_point = None
        self.rotating_shape = False
        self._rotation_drag_shape = None
        self._rotation_drag_prev_angle = None
        self.snapping = True
        self.h_shape_is_selected = False
        self.h_shape_is_hovered = None
        self._selected_group_id = None
        self._hovered_group_id = None
        self.last_mouse_pos = None


class CanvasInteractionMixin:
    """Interaction handlers for Canvas; state lives in CanvasInteractionState."""

    mode = _InteractionField("mode")
    is_move_editing = _InteractionField("is_move_editing")
    current = _InteractionField("current")
    selected_shapes = _InteractionField("selected_shapes")
    selected_shapes_copy = _InteractionField("selected_shapes_copy")
    line = _InteractionField("line")
    prev_point = _InteractionField("prev_point")
    prev_pan_point = _InteractionField("prev_pan_point")
    prev_move_point = _InteractionField("prev_move_point")
    _space_pressed = _InteractionField("_space_pressed")
    _space_panning = _InteractionField("_space_panning")
    _space_pan_prev_point = _InteractionField("_space_pan_prev_point")
    _space_pan_suppress_until_release = _InteractionField(
        "_space_pan_suppress_until_release"
    )
    _vertex_erasing = _InteractionField("_vertex_erasing")
    _vertex_eraser_cursor_cache = _InteractionField(
        "_vertex_eraser_cursor_cache"
    )
    offsets = _InteractionField("offsets")
    h_shape = _InteractionField("h_shape")
    prev_h_shape = _InteractionField("prev_h_shape")
    h_vertex = _InteractionField("h_vertex")
    prev_h_vertex = _InteractionField("prev_h_vertex")
    h_edge = _InteractionField("h_edge")
    prev_h_edge = _InteractionField("prev_h_edge")
    h_cuboid_face = _InteractionField("h_cuboid_face")
    prev_h_cuboid_face = _InteractionField("prev_h_cuboid_face")
    h_rotation_shape = _InteractionField("h_rotation_shape")
    prev_h_rotation_shape = _InteractionField("prev_h_rotation_shape")
    moving_shape = _InteractionField("moving_shape")
    _pending_edge_point = _InteractionField("_pending_edge_point")
    rotating_shape = _InteractionField("rotating_shape")
    _rotation_drag_shape = _InteractionField("_rotation_drag_shape")
    _rotation_drag_prev_angle = _InteractionField("_rotation_drag_prev_angle")
    snapping = _InteractionField("snapping")
    h_shape_is_selected = _InteractionField("h_shape_is_selected")
    h_shape_is_hovered = _InteractionField("h_shape_is_hovered")
    _selected_group_id = _InteractionField("_selected_group_id")
    _hovered_group_id = _InteractionField("_hovered_group_id")
    last_mouse_pos = _InteractionField("last_mouse_pos")

    def store_moving_shape(self):
        """Store a moving shape"""
        if self.moving_shape:
            moving_shapes = (
                [self.h_shape] + self.selected_shapes
                if self.h_shape and self.h_shape not in self.selected_shapes
                else self.selected_shapes.copy()
            )
            for shape in moving_shapes:
                if shape in self.shapes:
                    index = self.shapes.index(shape)
                    if (
                        len(self.shapes_backups) > 0
                        and index < len(self.shapes_backups[-1])
                        and self.shapes_backups[-1][index].points
                        != self.shapes[index].points
                    ):
                        self.store_shapes()
                        self.shape_moved.emit()
                        break

            self.moving_shape = False

    def enterEvent(self, _):
        """Mouse enter event"""
        self.override_cursor(self._cursor)

    def leaveEvent(self, _):
        """Mouse leave event"""
        self._clear_space_pan_state()
        self.store_moving_shape()
        self.un_highlight()
        self._hovered_group_id = None
        self.restore_cursor()
        self.shape_hover_changed.emit()

    def focusOutEvent(self, _):
        """Window out of focus event"""
        self._clear_space_pan_state()
        self.restore_cursor()

    def _shape_hit_candidates(self, point):
        """Return shapes under a point in interaction priority order."""
        epsilon = self.epsilon / self.scale

        def cuboid_vertex_lookup(shape, pt, eps):
            if shape.shape_type == "cuboid" and len(shape.points) == 8:
                index = self.nearest_cuboid_control(shape, pt, eps)
                vertex = (
                    self.cuboid_control_point(shape, index)
                    if index is not None
                    else None
                )
                return index, vertex
            index = shape.nearest_vertex(pt, eps)
            vertex = shape.points[index] if index is not None else None
            return index, vertex

        def cuboid_face_hit(shape, pt):
            front_path = self.cuboid_face_path(shape, CUBOID_FACE_FRONT)
            return (
                front_path is not None and front_path.contains(pt)
            ) or self.cuboid_face_hit_test(shape, pt) is not None

        return canvas_geometry.hit_candidates(
            self.shapes,
            point,
            epsilon,
            self.is_visible,
            cuboid_vertex_lookup,
            cuboid_face_hit,
        )

    def drawing(self):
        """Check if user is drawing (mode==CREATE)"""
        return self.mode == self.CREATE

    def editing(self):
        """Check if user is editing (mode==EDIT)"""
        return self.mode == self.EDIT

    def get_mode(self):
        """Get current mode"""
        if (
            self.is_auto_labeling
            and self.auto_labeling_mode != AutoLabelingMode.NONE
        ):
            return QCoreApplication.translate("Canvas", "Auto Labeling")
        if self.mode == self.CREATE:
            return QCoreApplication.translate("Canvas", "Drawing")
        elif self.mode == self.EDIT:
            return QCoreApplication.translate("Canvas", "Editing")
        else:
            return QCoreApplication.translate("Canvas", "Unknown")

    def set_editing(self, value=True):
        """Set editing mode. Editing is set to False, user is drawing"""
        self.mode = self.EDIT if value else self.CREATE
        if not value:  # Create
            self.un_highlight()
            self.deselect_shape()
            self.is_move_editing = False
            self.shape_hover_changed.emit()

    def un_highlight(self):
        """Unhighlight shape/vertex/edge"""
        if self.h_shape:
            self.h_shape.highlight_clear()
            self.update()
        self.prev_h_shape = self.h_shape
        self.prev_h_vertex = self.h_vertex
        self.prev_h_edge = self.h_edge
        self.prev_h_cuboid_face = self.h_cuboid_face
        self.prev_h_rotation_shape = self.h_rotation_shape
        self.h_shape = self.h_vertex = self.h_edge = self.h_cuboid_face = None
        self.h_rotation_shape = None

    def selected_vertex(self):
        """Check if selected a vertex"""
        return self.h_vertex is not None

    def selected_edge(self):
        """Check if selected an edge"""
        return self.h_edge is not None

    def selected_cuboid_face(self):
        return self.h_cuboid_face is not None

    def can_erase_selected_vertices(self):
        if not self.editing() or len(self.selected_shapes) != 1:
            return False
        shape = self.selected_shapes[0]
        return not shape.locked and shape.shape_type in [
            "polygon",
            "linestrip",
        ]

    def _vertex_eraser_cursor(self):
        if self._vertex_eraser_cursor_cache is None:
            pixmap = QtGui.QPixmap(new_icon_path("eraser", "svg"))
            if pixmap.isNull():
                return CURSOR_POINT
            self._vertex_eraser_cursor_cache = QtGui.QCursor(
                pixmap.scaled(
                    24,
                    24,
                    QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                    QtCore.Qt.TransformationMode.SmoothTransformation,
                ),
                3,
                20,
            )
        return self._vertex_eraser_cursor_cache

    def _set_vertex_eraser_tooltip(self):
        if not self.can_erase_selected_vertices():
            return
        tooltip = QCoreApplication.translate(
            "Canvas", "Click & drag to erase points of shape '%s'"
        ) % (self.selected_shapes[0].label)
        self.setToolTip(tooltip)
        self.setStatusTip(tooltip)

    @staticmethod
    def _minimum_points_for_shape(shape):
        if shape.shape_type == "polygon":
            return 3
        if shape.shape_type == "linestrip":
            return 2
        return 0

    def erase_selected_vertex_at(self, pos):
        if not self.can_erase_selected_vertices():
            return False
        shape = self.selected_shapes[0]
        index = shape.nearest_vertex(pos, self.epsilon / self.scale)
        if index is None:
            return False

        shape.remove_point(index)
        shape.highlight_clear()
        self.h_shape = shape
        self.h_vertex = None
        self.prev_h_vertex = None
        if len(shape.points) < self._minimum_points_for_shape(shape):
            if shape in self.shapes:
                self.shapes.remove(shape)
            self.selected_shapes = []
            self.h_shape = None
            self.h_edge = None
            self.moving_shape = False
            self.store_shapes()
            self.shapes_deleted.emit([shape])
        else:
            self.moving_shape = True
        self.update()
        return True

    @staticmethod
    def _snap_line_pos(anchor, pos):
        """Snap line endpoint to horizontal or vertical direction."""
        dx = abs(pos.x() - anchor.x())
        dy = abs(pos.y() - anchor.y())
        if dx >= dy:
            return QtCore.QPointF(pos.x(), anchor.y())
        return QtCore.QPointF(anchor.x(), pos.y())

    def _should_trigger_auto_decode(self, pos):
        """Check if mouse movement exceeds threshold to trigger auto decode"""
        if not self.auto_decode_tracklet:
            return True

        last_point = self.auto_decode_tracklet[-1]["data"]
        distance = (
            (pos.x() - last_point[0]) ** 2 + (pos.y() - last_point[1]) ** 2
        ) ** 0.5
        return distance >= AUTO_DECODE_MOVE_THRESHOLD

    def _has_valid_pixmap(self):
        return (
            self.pixmap
            and not self.pixmap.isNull()
            and self.pixmap.width()
            and self.pixmap.height()
        )

    def _clear_space_pan_state(self):
        self._space_pressed = False
        self._space_panning = False
        self._space_pan_prev_point = None
        self._space_pan_suppress_until_release = False

    def _restore_space_pan_cursor(self):
        if self._space_pressed:
            self.override_cursor(CURSOR_GRAB)
        elif self.drawing():
            self.override_cursor(CURSOR_DRAW)
        else:
            self.override_cursor(CURSOR_DEFAULT)

    def _start_space_pan(self, point):
        if not self._has_valid_pixmap():
            return False
        self._space_panning = True
        self._space_pan_suppress_until_release = True
        self._space_pan_prev_point = point
        self._clear_space_pan_hover_state()
        self.override_cursor(CURSOR_MOVE)
        return True

    def _left_button_pressed(self, ev):
        return bool(QtCore.Qt.MouseButton.LeftButton & ev.buttons())

    def _clear_space_pan_hover_state(self):
        had_hover = any(
            item is not None
            for item in (
                self.h_shape,
                self.h_vertex,
                self.h_edge,
                self.h_cuboid_face,
                self.h_rotation_shape,
            )
        )
        self.un_highlight()
        self.h_shape_is_selected = False
        self.vertex_selected.emit(False)
        if had_hover:
            self.shape_hover_changed.emit()

    def _sync_drawing_line(self, pos, modifiers):
        if not self.drawing() or not self.current:
            return
        if self.out_off_pixmap(pos) and self.create_mode not in [
            "rectangle",
            "rotation",
            "quadrilateral",
            "cuboid",
        ]:
            pos = self.intersection_point(self.current[-1], pos)
        elif (
            self.snapping
            and len(self.current) > 1
            and self.create_mode == "polygon"
            and self.close_enough(pos, self.current[0])
        ):
            pos = self.current[0]
        elif (
            self.create_mode == "rotation"
            and len(self.current) > 0
            and self.close_enough(pos, self.current[0])
        ):
            pos = self.current[0]
        elif (
            self.create_mode == "quadrilateral"
            and len(self.current) >= 3
            and self.close_enough(pos, self.current[0])
        ):
            pos = self.current[0]
        if (
            self.create_mode in ["line", "linestrip"]
            and modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier
        ):
            pos = self._snap_line_pos(self.current[-1], pos)
        if self.create_mode in ["polygon", "linestrip", "quadrilateral"]:
            self.line[0] = self.current[-1]
            self.line[1] = pos
        elif self.create_mode == "rectangle":
            self.line.points = [self.current[0], pos]
            self.line.close()
        elif self.create_mode == "rotation":
            self.line[1] = pos
        elif self.create_mode == "circle":
            self.line.points = [self.current[0], pos]
            self.line.shape_type = "circle"
        elif self.create_mode == "line":
            self.line.points = [self.current[0], pos]
            self.line.close()
        elif self.create_mode == "cuboid":
            self.line.points = [self.current[0], pos]
            self.line.close()

    def _update_space_pan(self, point):
        if not self._space_panning:
            return False
        if not self._has_valid_pixmap():
            self._space_panning = False
            self._space_pan_prev_point = None
            self._space_pan_suppress_until_release = False
            return False
        if self._space_pan_prev_point is None:
            self._space_pan_prev_point = point
            return True

        delta = point - self._space_pan_prev_point
        self._space_pan_prev_point = point
        self.override_cursor(CURSOR_MOVE)
        self.scroll_request.emit(
            delta.x() / (self.pixmap.width() * self.scale),
            Qt.Orientation.Horizontal,
            1,
        )
        self.scroll_request.emit(
            delta.y() / (self.pixmap.height() * self.scale),
            Qt.Orientation.Vertical,
            1,
        )
        self.update()
        return True

    def mouseMoveEvent(self, ev):  # noqa: C901
        """Update line with last point and current coordinates"""
        if self.is_loading:
            return
        try:
            pos = self.transform_pos(ev.position())
        except AttributeError:
            return

        if self._space_panning:
            if self._left_button_pressed(ev):
                self._update_space_pan(ev.position())
                ev.accept()
                return
            self._space_panning = False
            self._space_pan_prev_point = None
            self._space_pan_suppress_until_release = False
        if self._space_pan_suppress_until_release:
            if self._left_button_pressed(ev):
                ev.accept()
                return
            self._space_pan_suppress_until_release = False
        if self._space_pressed:
            self.override_cursor(CURSOR_GRAB)
            ev.accept()
            return

        if self.is_brush_mode and self.editing():
            self._brush_mouse_move(ev, pos)
            return

        if (
            self.editing()
            and ev.modifiers() == QtCore.Qt.KeyboardModifier.AltModifier
            and self.can_erase_selected_vertices()
        ):
            self.override_cursor(self._vertex_eraser_cursor())
            self._set_vertex_eraser_tooltip()
            if QtCore.Qt.MouseButton.LeftButton & ev.buttons():
                self._vertex_erasing = True
                self.erase_selected_vertex_at(pos)
                self.update()
            ev.accept()
            return

        prev_hover_shape = self.h_shape
        self.prev_move_point = pos
        self.update()

        # Handle auto decode mode
        if (
            self.auto_decode_mode
            and self.is_auto_labeling
            and self.auto_decode_tracklet
        ):
            if self._should_trigger_auto_decode(pos):
                self.last_mouse_pos = pos
                if not self.auto_decode_timer.isActive():
                    self.auto_decode_timer.start(AUTO_DECODE_DELAY_MS)

        # Polygon drawing.
        if self.drawing():
            line_color = utils.hex_to_rgb(self.cross_line_color)
            self.line.line_color = QtGui.QColor(*line_color)
            self.line.shape_type = self.create_mode
            if self.create_mode == "cuboid":
                self.line.shape_type = "rectangle"

            if not self.current:
                self.override_cursor(CURSOR_DRAW)
                return

            if self.create_mode in ["rectangle", "cuboid"]:
                shape_width = int(abs(self.current[0].x() - pos.x()))
                shape_height = int(abs(self.current[0].y() - pos.y()))
                self.show_shape.emit(shape_height, shape_width, pos)

            color = QtGui.QColor(0, 0, 255)
            if self.out_off_pixmap(pos) and self.create_mode not in [
                "rectangle",
                "rotation",
                "quadrilateral",
                "cuboid",
            ]:
                pos = self.intersection_point(self.current[-1], pos)
            elif (
                self.snapping
                and len(self.current) > 1
                and self.create_mode == "polygon"
                and self.close_enough(pos, self.current[0])
            ):
                # Attract line to starting point and
                # colorise to alert the user.
                pos = self.current[0]
                self.override_cursor(CURSOR_POINT)
                self.current.highlight_vertex(0, Shape.NEAR_VERTEX)
            elif (
                self.create_mode == "rotation"
                and len(self.current) > 0
                and self.close_enough(pos, self.current[0])
            ):
                pos = self.current[0]
                color = self.current.line_color
                self.override_cursor(CURSOR_POINT)
                self.current.highlight_vertex(0, Shape.NEAR_VERTEX)
            elif (
                self.create_mode == "quadrilateral"
                and len(self.current) >= 3
                and self.close_enough(pos, self.current[0])
            ):
                pos = self.current[0]
                self.override_cursor(CURSOR_POINT)
                self.current.highlight_vertex(0, Shape.NEAR_VERTEX)
            else:
                self.override_cursor(CURSOR_DRAW)
            if (
                self.create_mode in ["line", "linestrip"]
                and ev.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier
            ):
                pos = self._snap_line_pos(self.current[-1], pos)
            if self.create_mode in ["polygon", "linestrip", "quadrilateral"]:
                self.line[0] = self.current[-1]
                self.line[1] = pos
            elif self.create_mode == "rectangle":
                self.line.points = [self.current[0], pos]
                self.line.close()
            elif self.create_mode == "rotation":
                self.line[1] = pos
                self.line.line_color = color
            elif self.create_mode == "circle":
                self.line.points = [self.current[0], pos]
                self.line.shape_type = "circle"
            elif self.create_mode == "line":
                self.line.points = [self.current[0], pos]
                self.line.close()
            elif self.create_mode == "point":
                self.line.points = [self.current[0]]
                self.line.close()
            elif self.create_mode == "cuboid":
                self.line.points = [self.current[0], pos]
                self.line.close()
            if self._brush_drawing and self.create_mode == "polygon":
                if self.snapping and self._brush_drawing_can_close(pos):
                    self.current.highlight_clear()
                    self.finalise()
                    return
                point_dist = utils.distance(pos - self.current[-1])
                if point_dist * self.scale >= self.brush_point_distance:
                    self.current.add_point(pos)
                    self.line[0] = self.current[-1]
            self.update()
            self.current.highlight_clear()
            return

        # Polygon copy moving.
        if QtCore.Qt.MouseButton.RightButton & ev.buttons():
            if self.selected_shapes_copy and self.prev_point:
                self.override_cursor(CURSOR_MOVE)
                self.bounded_move_shapes(self.selected_shapes_copy, pos)
                self.update()
            elif self.selected_shapes:
                self.selected_shapes_copy = [
                    s.copy() for s in self.selected_shapes
                ]
                self.update()
            return

        if self._rotation_drag_shape is not None:
            if QtCore.Qt.MouseButton.LeftButton & ev.buttons():
                self.is_move_editing = False
                self._update_rotation_handle_drag(pos, ev.modifiers())
            else:
                self._finish_rotation_handle_drag()
            return

        # Polygon/Vertex moving.
        if QtCore.Qt.MouseButton.LeftButton & ev.buttons():
            if self.selected_vertex():
                self.h_cuboid_face = None
                self.is_move_editing = False
                try:
                    self.bounded_move_vertex(pos)
                    self.update()
                    self.moving_shape = True
                except IndexError:
                    return
                if self.h_shape.shape_type == "rectangle":
                    p1 = self.h_shape[0]
                    p2 = self.h_shape[2]
                    shape_width = int(abs(p2.x() - p1.x()))
                    shape_height = int(abs(p2.y() - p1.y()))
                    self.show_shape.emit(shape_height, shape_width, pos)
                elif (
                    self.h_shape.shape_type == "cuboid"
                    and len(self.h_shape) >= 4
                ):
                    p1 = self.h_shape[0]
                    p2 = self.h_shape[2]
                    shape_width = int(abs(p2.x() - p1.x()))
                    shape_height = int(abs(p2.y() - p1.y()))
                    self.show_shape.emit(shape_height, shape_width, pos)
            elif (
                self.selected_cuboid_face()
                and self.h_shape is not None
                and self.h_shape.shape_type == "cuboid"
                and self.prev_point is not None
            ):
                self.is_move_editing = False
                offset = pos - self.prev_point
                self.move_cuboid_face_by(
                    self.h_shape, self.h_cuboid_face, offset
                )
                self.prev_point = pos
                self.update()
                self.moving_shape = True
                p1 = self.h_shape[0]
                p2 = self.h_shape[2]
                shape_width = int(abs(p2.x() - p1.x()))
                shape_height = int(abs(p2.y() - p1.y()))
                self.show_shape.emit(shape_height, shape_width, pos)
            elif self.selected_shapes and self.prev_point:
                self.h_cuboid_face = None
                group_shapes = self._active_group_shapes()
                if group_shapes and any(
                    shape.locked for shape in group_shapes
                ):
                    return
                self.override_cursor(CURSOR_MOVE)
                self.bounded_move_shapes(self.selected_shapes, pos)
                self.update()
                self.moving_shape = True
                if self.selected_shapes[-1].shape_type == "rectangle":
                    p1 = self.selected_shapes[-1][0]
                    p2 = self.selected_shapes[-1][2]
                    shape_width = int(abs(p2.x() - p1.x()))
                    shape_height = int(abs(p2.y() - p1.y()))
                    self.show_shape.emit(shape_height, shape_width, pos)
                elif (
                    self.selected_shapes[-1].shape_type == "cuboid"
                    and len(self.selected_shapes[-1]) >= 4
                ):
                    p1 = self.selected_shapes[-1][0]
                    p2 = self.selected_shapes[-1][2]
                    shape_width = int(abs(p2.x() - p1.x()))
                    shape_height = int(abs(p2.y() - p1.y()))
                    self.show_shape.emit(shape_height, shape_width, pos)
            else:
                if (
                    self.pixmap
                    and self.pixmap.width()
                    and self.pixmap.height()
                ):
                    self.override_cursor(CURSOR_MOVE)
                    delta = ev.position() - self.prev_pan_point
                    self.scroll_request.emit(
                        delta.x() / (self.pixmap.width() * self.scale),
                        Qt.Orientation.Horizontal,
                        1,
                    )
                    self.scroll_request.emit(
                        delta.y() / (self.pixmap.height() * self.scale),
                        Qt.Orientation.Vertical,
                        1,
                    )
                    self.update()
            return

        if self.editing() and self.is_move_editing:
            self.override_cursor(CURSOR_MOVE)
            if self.selected_vertex():
                self.h_cuboid_face = None
                try:
                    self.bounded_move_vertex(pos)
                    self.update()
                    self.moving_shape = True
                except IndexError:
                    return
                if self.h_shape.shape_type == "rectangle":
                    p1 = self.h_shape[0]
                    p2 = self.h_shape[2]
                    shape_width = int(abs(p2.x() - p1.x()))
                    shape_height = int(abs(p2.y() - p1.y()))
                    self.show_shape.emit(shape_height, shape_width, pos)
                elif (
                    self.h_shape.shape_type == "cuboid"
                    and len(self.h_shape) >= 4
                ):
                    p1 = self.h_shape[0]
                    p2 = self.h_shape[2]
                    shape_width = int(abs(p2.x() - p1.x()))
                    shape_height = int(abs(p2.y() - p1.y()))
                    self.show_shape.emit(shape_height, shape_width, pos)
            elif (
                self.selected_cuboid_face()
                and self.h_shape is not None
                and self.h_shape.shape_type == "cuboid"
                and self.prev_point is not None
            ):
                offset = pos - self.prev_point
                self.move_cuboid_face_by(
                    self.h_shape, self.h_cuboid_face, offset
                )
                self.prev_point = pos
                self.update()
                self.moving_shape = True
                p1 = self.h_shape[0]
                p2 = self.h_shape[2]
                shape_width = int(abs(p2.x() - p1.x()))
                shape_height = int(abs(p2.y() - p1.y()))
                self.show_shape.emit(shape_height, shape_width, pos)
            else:
                self.is_move_editing = False

            return

        self.show_shape.emit(-1, -1, pos)

        self._hovered_group_id = None

        rotation_handle_shape = self._rotation_handle_shape_at(pos)
        if rotation_handle_shape is not None:
            self._set_rotation_handle_hover(rotation_handle_shape)
            self.vertex_selected.emit(False)
            if prev_hover_shape != self.h_shape:
                self.shape_hover_changed.emit()
            return
        if self.h_rotation_shape is not None:
            self.prev_h_rotation_shape = self.h_rotation_shape
            self.h_rotation_shape = None

        # Just hovering over the canvas, 2 possibilities:
        # - Highlight shapes
        # - Highlight vertex
        # Update shape/vertex fill and tooltip value accordingly.
        # self.setToolTip(QCoreApplication.translate("Canvas", "Image"))
        for shape in self._shape_hit_candidates(pos):
            if (
                not shape.locked
                and shape.shape_type == "cuboid"
                and len(shape.points) == 8
            ):
                index = self.nearest_cuboid_control(
                    shape, pos, self.epsilon / self.scale
                )
                if index is not None:
                    if self.selected_vertex():
                        self.h_shape.highlight_clear()
                    self.prev_h_vertex = self.h_vertex
                    self.h_vertex = index
                    self.prev_h_shape = self.h_shape = shape
                    self.prev_h_edge = self.h_edge
                    self.h_edge = None
                    self.prev_h_cuboid_face = self.h_cuboid_face
                    self.h_cuboid_face = None
                    shape.highlight_vertex(index, shape.MOVE_VERTEX)
                    self.override_cursor(CURSOR_POINT)
                    if index in CUBOID_BACK_EDGE_CENTER_INDICES:
                        self.setToolTip(
                            QCoreApplication.translate(
                                "Canvas",
                                "Click & drag to adjust cuboid depth of shape '%s'",
                            )
                            % shape.label
                        )
                    elif index in [4, 5, 6, 7]:
                        self.setToolTip(
                            QCoreApplication.translate(
                                "Canvas",
                                "Click & drag to adjust rear edge of cuboid shape '%s'",
                            )
                            % shape.label
                        )
                    else:
                        self.setToolTip(
                            QCoreApplication.translate(
                                "Canvas",
                                "Click & drag to move point of shape '%s'",
                            )
                            % shape.label
                        )
                    self.setStatusTip(self.toolTip())
                    self.update()
                    break
                front_path = self.cuboid_face_path(shape, CUBOID_FACE_FRONT)
                if front_path is not None and front_path.contains(pos):
                    if self.selected_vertex():
                        self.h_shape.highlight_clear()
                    self.prev_h_vertex = self.h_vertex
                    self.h_vertex = None
                    self.prev_h_shape = self.h_shape = shape
                    self.prev_h_edge = self.h_edge
                    self.h_edge = None
                    self.prev_h_cuboid_face = self.h_cuboid_face
                    self.h_cuboid_face = None
                    self.setToolTip(
                        QCoreApplication.translate(
                            "Canvas", "Click & drag to move shape '%s'"
                        )
                        % shape.label
                    )
                    self.setStatusTip(self.toolTip())
                    self.override_cursor(CURSOR_GRAB)
                    self.update()
                    break
                face_name = self.cuboid_face_hit_test(shape, pos)
                if face_name and face_name != CUBOID_FACE_FRONT:
                    if self.selected_vertex():
                        self.h_shape.highlight_clear()
                    self.prev_h_vertex = self.h_vertex
                    self.h_vertex = None
                    self.prev_h_shape = self.h_shape = shape
                    self.prev_h_edge = self.h_edge
                    self.h_edge = None
                    self.prev_h_cuboid_face = self.h_cuboid_face
                    self.h_cuboid_face = face_name
                    self.override_cursor(CURSOR_POINT)
                    self.setToolTip(
                        QCoreApplication.translate(
                            "Canvas",
                            "Click & drag to adjust cuboid %s face of shape '%s'",
                        )
                        % (face_name, shape.label)
                    )
                    self.setStatusTip(self.toolTip())
                    self.update()
                    break
            # Look for a nearby vertex to highlight. If that fails,
            # check if we happen to be inside a shape.
            index = (
                None
                if shape.locked
                else shape.nearest_vertex(pos, self.epsilon / self.scale)
            )
            index_edge = (
                None
                if shape.locked
                else shape.nearest_edge(pos, self.epsilon / self.scale)
            )
            if index is not None:
                if self.selected_vertex():
                    self.h_shape.highlight_clear()
                self.prev_h_vertex = self.h_vertex = index
                self.prev_h_shape = self.h_shape = shape
                self.prev_h_edge = self.h_edge
                self.h_edge = None
                self.prev_h_cuboid_face = self.h_cuboid_face
                self.h_cuboid_face = None
                shape.highlight_vertex(index, shape.MOVE_VERTEX)
                self.override_cursor(CURSOR_POINT)
                self.setToolTip(
                    QCoreApplication.translate(
                        "Canvas", "Click & drag to move point of shape '%s'"
                    )
                    % shape.label
                )
                self.setStatusTip(self.toolTip())
                self.update()
                break
            if (
                index_edge is not None
                and shape.can_add_point()
                and shape.shape_type != "quadrilateral"
            ):
                if self.selected_vertex():
                    self.h_shape.highlight_clear()
                self.prev_h_vertex = self.h_vertex
                self.h_vertex = None
                self.prev_h_shape = self.h_shape = shape
                self.prev_h_edge = self.h_edge = index_edge
                self.prev_h_cuboid_face = self.h_cuboid_face
                self.h_cuboid_face = None
                self.override_cursor(CURSOR_POINT)
                self.setToolTip(
                    QCoreApplication.translate(
                        "Canvas", "Click to create point of shape '%s'"
                    )
                    % shape.label
                )
                self.setStatusTip(self.toolTip())
                self.update()
                break
            shape_hit = False
            if shape.shape_type in ["point", "line", "linestrip"]:
                nearest_index = shape.nearest_vertex(
                    pos, self.epsilon * 3 / self.scale
                )
                if nearest_index is not None:
                    shape_hit = True
            elif shape.shape_type == "cuboid" and len(shape.points) == 8:
                front_path = self.cuboid_face_path(shape, CUBOID_FACE_FRONT)
                shape_hit = front_path is not None and front_path.contains(pos)
            elif len(shape.points) > 1 and shape.contains_point(pos):
                shape_hit = True

            if shape_hit:
                if self.selected_vertex():
                    self.h_shape.highlight_clear()
                self.prev_h_vertex = self.h_vertex
                self.h_vertex = None
                self.prev_h_shape = self.h_shape = shape
                self.prev_h_edge = self.h_edge
                self.h_edge = None
                self.prev_h_cuboid_face = self.h_cuboid_face
                self.h_cuboid_face = None
                if shape.locked:
                    self.setToolTip(
                        QCoreApplication.translate(
                            "Canvas", "Locked shape '%s'"
                        )
                        % shape.label
                    )
                elif shape.group_id and shape.shape_type == "rectangle":
                    tooltip_text = "Click & drag to move shape '{label} {group_id}'".format(
                        label=shape.label, group_id=shape.group_id
                    )
                    self.setToolTip(
                        QCoreApplication.translate("Canvas", tooltip_text)
                    )
                else:
                    self.setToolTip(
                        QCoreApplication.translate(
                            "Canvas", "Click & drag to move shape '%s'"
                        )
                        % shape.label
                    )
                self.setStatusTip(self.toolTip())
                self.override_cursor(
                    CURSOR_DEFAULT if shape.locked else CURSOR_GRAB
                )
                # [Feature] Automatically highlight shape when the mouse is moved inside it
                if self.h_shape_is_hovered:
                    group_mode = (
                        ev.modifiers()
                        == QtCore.Qt.KeyboardModifier.ControlModifier
                    )
                    self.select_shape_point(
                        pos, multiple_selection_mode=group_mode
                    )
                self.update()

                if shape.shape_type == "rectangle":
                    p1 = self.h_shape[0]
                    p2 = self.h_shape[2]
                    shape_width = int(abs(p2.x() - p1.x()))
                    shape_height = int(abs(p2.y() - p1.y()))
                    self.show_shape.emit(shape_height, shape_width, pos)
                elif shape.shape_type == "cuboid" and len(self.h_shape) >= 4:
                    p1 = self.h_shape[0]
                    p2 = self.h_shape[2]
                    shape_width = int(abs(p2.x() - p1.x()))
                    shape_height = int(abs(p2.y() - p1.y()))
                    self.show_shape.emit(shape_height, shape_width, pos)
                break
        else:  # Nothing found, clear highlights, reset state.
            group_id = self._group_at_point(pos)
            if group_id is not None:
                self.un_highlight()
                self._hover_group(group_id)
                return
            self.un_highlight()
            self.override_cursor(CURSOR_DEFAULT)
            self.setToolTip("")
            self.setStatusTip("")
        self.vertex_selected.emit(self.h_vertex is not None)

        if prev_hover_shape != self.h_shape:
            self.shape_hover_changed.emit()

    def add_point_to_edge(self):
        """Add a point to current shape"""
        shape = self.prev_h_shape
        index = self.prev_h_edge
        point = self.prev_move_point
        if shape is None or shape.locked or index is None or point is None:
            return
        shape.insert_point(index, point)
        shape.highlight_vertex(index, shape.MOVE_VERTEX)
        self.h_shape = shape
        self.h_vertex = index
        self.h_edge = None
        self.moving_shape = True
        self._pending_edge_point = (shape, index)

    def _undo_pending_edge_point(self):
        """Undo the edge point inserted by the preceding mousePressEvent"""
        if self._pending_edge_point is None:
            return
        shape, index = self._pending_edge_point
        self._pending_edge_point = None
        shape.remove_point(index)
        shape.highlight_clear()
        if len(self.shapes_backups) >= 2 and shape in self.shapes:
            self.shapes_backups.pop()
            # Dropping the backup of a cancelled edit invalidates any
            # pending redo branch as well.
            self.shapes_redo_backups.clear()

    def remove_selected_point(self):
        """Remove a point from current shape"""
        shape = self.prev_h_shape
        index = self.prev_h_vertex
        if shape is None or shape.locked or index is None:
            return
        shape.remove_point(index)
        shape.highlight_clear()
        self.h_shape = shape
        self.prev_h_vertex = None
        self.moving_shape = True  # Save changes

    def on_auto_decode_timeout(self):
        """Handle auto decode timeout"""
        if (
            not self.auto_decode_mode
            or self.auto_labeling_mode.shape_type != AutoLabelingMode.POINT
        ):
            return

        flag = -1
        if self.auto_labeling_mode.edit_mode == AutoLabelingMode.ADD:
            flag = 1
        elif self.auto_labeling_mode.edit_mode == AutoLabelingMode.REMOVE:
            flag = 0
        if flag == -1:
            return

        if self.auto_decode_mode and self.last_mouse_pos:
            if len(self.auto_decode_tracklet) >= MAX_AUTO_DECODE_MARKS:
                self.auto_decode_tracklet.pop(0)

            marks = {
                "type": "point",
                "data": [
                    int(self.last_mouse_pos.x()),
                    int(self.last_mouse_pos.y()),
                ],
                "label": flag,
            }
            self.auto_decode_tracklet.append(marks)
            self.auto_decode_requested.emit(self.auto_decode_tracklet)

    def mousePressEvent(self, ev):  # noqa: C901
        """Mouse press event"""
        if self.is_loading:
            return
        self._pending_edge_point = None
        pos = self.transform_pos(ev.position())

        if self.is_brush_mode and self._brush_mouse_press(ev, pos):
            return

        if ev.button() == QtCore.Qt.MouseButton.LeftButton:
            if (
                self._space_pan_suppress_until_release
                and not self._space_pressed
            ):
                self._space_pan_suppress_until_release = False
            if self._space_pressed and self._start_space_pan(ev.position()):
                ev.accept()
                return
            if self.drawing():
                if self.current:
                    self._sync_drawing_line(pos, ev.modifiers())
                    # Add point to existing shape.
                    if self.create_mode == "polygon":
                        self.current.add_point(self.line[1])
                        self.line[0] = self.current[-1]
                        if self.current.is_closed():
                            self.finalise()
                    elif self.create_mode in ["circle", "line"]:
                        assert len(self.current.points) == 1
                        self.current.points = self.line.points
                        self.finalise()
                    elif self.create_mode == "rectangle":
                        if self.current.reach_max_points() is False:
                            init_pos = self.current[0]
                            min_x = init_pos.x()
                            min_y = init_pos.y()
                            target_pos = self.line[1]
                            max_x = target_pos.x()
                            max_y = target_pos.y()
                            self.current.add_point(
                                QtCore.QPointF(max_x, min_y)
                            )
                            self.current.add_point(target_pos)
                            self.current.add_point(
                                QtCore.QPointF(min_x, max_y)
                            )
                            self.finalise()
                    elif self.create_mode == "cuboid":
                        if len(self.current.points) == 1:
                            init_pos = self.current[0]
                            target_pos = self.line[1]
                            front_points = self.make_rectangle_points(
                                init_pos, target_pos
                            )
                            if (
                                abs(front_points[2].x() - front_points[0].x())
                                < 1
                                or abs(
                                    front_points[2].y() - front_points[0].y()
                                )
                                < 1
                            ):
                                return
                            depth_vector = QtCore.QPointF(
                                self.cuboid_default_depth_vector[0],
                                self.cuboid_default_depth_vector[1],
                            )
                            self.set_cuboid_points(
                                self.current, front_points, depth_vector
                            )
                            self.finalise()
                    elif self.create_mode == "rotation":
                        initPos = self.current[0]
                        minX = initPos.x()
                        minY = initPos.y()
                        targetPos = self.line[1]
                        maxX = targetPos.x()
                        maxY = targetPos.y()
                        self.current.add_point(QtCore.QPointF(maxX, minY))
                        self.current.add_point(targetPos)
                        self.current.add_point(QtCore.QPointF(minX, maxY))
                        self.current.add_point(initPos)
                        self.line[0] = self.current[-1]
                        if self.current.is_closed():
                            self.finalise()
                    elif self.create_mode == "quadrilateral":
                        self.current.add_point(self.line[1])
                        self.line[0] = self.current[-1]
                        if self.current.is_closed():
                            self.finalise()
                    elif self.create_mode == "linestrip":
                        self.current.add_point(self.line[1])
                        self.line[0] = self.current[-1]
                        if (
                            ev.modifiers()
                            == QtCore.Qt.KeyboardModifier.ControlModifier
                        ):
                            self.finalise()
                    # [Feature] support for automatically switching to editing mode
                    # when the cursor moves over an object
                    if (
                        self.create_mode
                        in [
                            "rectangle",
                            "rotation",
                            "quadrilateral",
                            "cuboid",
                            "circle",
                            "line",
                            "point",
                        ]
                        and not self.is_auto_labeling
                        and not self.current
                    ):
                        self.prev_pan_point = ev.position()
                        self.mode_changed.emit()
                elif not self.out_off_pixmap(pos):
                    # Handle auto decode mode first click
                    if self.auto_decode_mode and self.is_auto_labeling:
                        if (
                            self.auto_labeling_mode.shape_type
                            == AutoLabelingMode.POINT
                        ):
                            self.last_mouse_pos = pos
                            self.on_auto_decode_timeout()
                            return

                    # Create new shape.
                    self.current = Shape(shape_type=self.create_mode)
                    self.current.add_point(pos)
                    if self.create_mode == "point":
                        self.finalise()
                    else:
                        if self.create_mode == "circle":
                            self.current.shape_type = "circle"
                        self.line.points = [pos, pos]
                        self.drawing_polygon.emit(True)
                        self.update()
                elif self.out_off_pixmap(pos) and self.create_mode in [
                    "polygon",
                    "linestrip",
                ]:
                    w = self.pixmap.width()
                    h = self.pixmap.height()
                    if w > 0 and h > 0:
                        pos = QtCore.QPointF(
                            min(max(pos.x(), 0), w - 1),
                            min(max(pos.y(), 0), h - 1),
                        )
                        self.current = Shape(shape_type=self.create_mode)
                        self.current.add_point(pos)
                        self.line.points = [pos, pos]
                        self.drawing_polygon.emit(True)
                        self.update()
                elif self.out_off_pixmap(pos) and self.create_mode in [
                    "rectangle",
                    "rotation",
                    "quadrilateral",
                    "cuboid",
                ]:
                    # Create new shape.
                    self.current = Shape(shape_type=self.create_mode)
                    self.current.add_point(pos)
                    self.line.points = [pos, pos]
                    self.drawing_polygon.emit(True)
                    self.update()
            elif self.editing():
                if (
                    ev.modifiers() == QtCore.Qt.KeyboardModifier.AltModifier
                    and self.can_erase_selected_vertices()
                ):
                    self._vertex_erasing = True
                    self.override_cursor(self._vertex_eraser_cursor())
                    self._set_vertex_eraser_tooltip()
                    self.erase_selected_vertex_at(pos)
                    self.prev_point = pos
                    self.prev_pan_point = ev.position()
                    self.update()
                    ev.accept()
                    return
                rotation_handle_shape = self._rotation_handle_shape_at(pos)
                if rotation_handle_shape is not None:
                    group_mode = (
                        ev.modifiers()
                        == QtCore.Qt.KeyboardModifier.ControlModifier
                    )
                    self._start_rotation_handle_drag(
                        rotation_handle_shape,
                        pos,
                        group_mode,
                        ev.modifiers(),
                    )
                    self.prev_point = pos
                    self.prev_pan_point = ev.position()
                    self.update()
                    ev.accept()
                    return
                if self.selected_edge():
                    self.add_point_to_edge()
                elif (
                    self.selected_vertex()
                    and ev.modifiers()
                    == QtCore.Qt.KeyboardModifier.ShiftModifier
                    and self.h_shape.shape_type
                    not in [
                        "rectangle",
                        "rotation",
                        "quadrilateral",
                        "line",
                        "cuboid",
                    ]
                ):
                    # Delete point if: left-click + SHIFT on a point
                    # (quadrilateral must keep exactly 4 points)
                    self.remove_selected_point()

                if (
                    self.selected_vertex()
                    and ev.modifiers()
                    != QtCore.Qt.KeyboardModifier.ShiftModifier
                ):
                    self.is_move_editing = not self.is_move_editing
                    if self.is_move_editing:
                        self.override_cursor(CURSOR_MOVE)
                    else:
                        self.override_cursor(CURSOR_POINT)

                group_mode = (
                    ev.modifiers()
                    == QtCore.Qt.KeyboardModifier.ControlModifier
                )
                self.select_shape_point(
                    pos, multiple_selection_mode=group_mode
                )
                self.prev_point = pos
                self.prev_pan_point = ev.position()
                self.update()
        elif (
            ev.button() == QtCore.Qt.MouseButton.RightButton and self.editing()
        ):
            group_mode = (
                ev.modifiers() == QtCore.Qt.KeyboardModifier.ControlModifier
            )
            if not self.selected_shapes or (
                self.h_shape is not None
                and self.h_shape not in self.selected_shapes
            ):
                self.select_shape_point(
                    pos, multiple_selection_mode=group_mode
                )
                self.update()
            self.prev_point = pos

    def mouseReleaseEvent(self, ev):
        """Mouse release event"""
        if self.is_loading:
            return

        if ev.button() == QtCore.Qt.MouseButton.LeftButton and (
            self._space_panning or self._space_pan_suppress_until_release
        ):
            self._space_panning = False
            self._space_pan_prev_point = None
            self._space_pan_suppress_until_release = False
            self._restore_space_pan_cursor()
            ev.accept()
            return

        if self.is_brush_mode and self._brush_mouse_release(ev):
            return

        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            menu = self.menus[len(self.selected_shapes_copy) > 0]
            self.restore_cursor()
            if (
                not menu.exec(self.mapToGlobal(ev.position().toPoint()))
                and self.selected_shapes_copy
            ):
                # Cancel the move by deleting the shadow copy.
                self.selected_shapes_copy = []
                self.update()
        elif ev.button() == QtCore.Qt.MouseButton.LeftButton:
            if self._rotation_drag_shape is not None:
                self._finish_rotation_handle_drag()
                ev.accept()
                return
            if self._vertex_erasing:
                self._vertex_erasing = False
                self.store_moving_shape()
                ev.accept()
                return
            if self.editing():
                if (
                    self.h_shape is not None
                    and self.h_shape_is_selected
                    and not self.moving_shape
                ):
                    self.selection_changed.emit(
                        [x for x in self.selected_shapes if x != self.h_shape]
                    )

        self.store_moving_shape()

    def mouseDoubleClickEvent(self, ev):
        """Mouse double click event"""
        if self.is_loading:
            return
        if (
            self._space_pressed
            or self._space_panning
            or self._space_pan_suppress_until_release
        ):
            ev.accept()
            return

        # Handle auto decode mode double click to finish
        if (
            self.auto_decode_mode
            and self.is_auto_labeling
            and self.auto_decode_tracklet
        ):
            self.auto_decode_finish_requested.emit()
            return

        if self.editing() and self.double_click_edit_label:
            pos = self.transform_pos(ev.position())
            for shape in self._shape_hit_candidates(pos):
                self._undo_pending_edge_point()
                if shape not in self.selected_shapes:
                    self.selection_changed.emit([shape])
                self.h_shape_is_selected = False
                self.edit_label_requested.emit()
                return

        # For polygon/quadrilateral the mousePress handler adds a spurious
        # duplicate point before this handler fires, so we pop it first.
        # For linestrip the press-added point IS the intended final point,
        # so we keep it and finalize directly.
        if self.double_click == "close" and self.can_close_shape():
            if self.create_mode == "linestrip":
                self.finalise()
            elif len(self.current) > 3:
                self.current.pop_point()
                self.finalise()

    def select_shapes(self, shapes):
        """Select some shapes"""
        self._selected_group_id = None
        self.selection_changed.emit(shapes)
        self.update()

    def select_shape_point(self, point, multiple_selection_mode):  # noqa: C901
        """Select the first shape created which contains this point."""
        self._selected_group_id = None
        if self.selected_vertex():  # A vertex is marked for selection.
            index, shape = self.h_vertex, self.h_shape
            if shape.shape_type == "cuboid":
                if shape not in self.selected_shapes:
                    if multiple_selection_mode:
                        self.selection_changed.emit(
                            self.selected_shapes + [shape]
                        )
                    else:
                        self.selection_changed.emit([shape])
                    self.h_shape_is_selected = False
                else:
                    self.h_shape_is_selected = True
                self.calculate_offsets(point)
                return
            shape.highlight_vertex(index, shape.MOVE_VERTEX)
            if shape.shape_type == "rotation":
                if shape not in self.selected_shapes:
                    if multiple_selection_mode:
                        self.selection_changed.emit(
                            self.selected_shapes + [shape]
                        )
                    else:
                        self.selection_changed.emit([shape])
                    self.h_shape_is_selected = False
                else:
                    self.h_shape_is_selected = True
                self.calculate_offsets(point)
                return
            if shape not in self.selected_shapes:
                if multiple_selection_mode:
                    self.selection_changed.emit(self.selected_shapes + [shape])
                else:
                    self.selection_changed.emit([shape])
            self.h_shape_is_selected = False
            self.calculate_offsets(point)
            return
        elif (
            self.selected_cuboid_face()
            and self.h_shape is not None
            and self.h_shape.shape_type == "cuboid"
        ):
            shape = self.h_shape
            if shape not in self.selected_shapes:
                if multiple_selection_mode:
                    self.selection_changed.emit(self.selected_shapes + [shape])
                else:
                    self.selection_changed.emit([shape])
                self.h_shape_is_selected = False
            else:
                self.h_shape_is_selected = True
            self.calculate_offsets(point)
            return

        else:
            for shape in self._shape_hit_candidates(point):
                self._selected_group_id = None
                if shape not in self.selected_shapes:
                    if multiple_selection_mode:
                        self.selection_changed.emit(
                            self.selected_shapes + [shape]
                        )
                    else:
                        self.selection_changed.emit([shape])
                    self.h_shape_is_selected = False
                else:
                    self.h_shape_is_selected = True
                self.calculate_offsets(point)
                return
            self._select_group_at_point_or_deselect(point)

    def _select_group_at_point_or_deselect(self, point):
        group_id = self._group_at_point(point)
        if group_id is None:
            self.deselect_shape()
            return
        self._select_group(group_id, point)

    def _grouped_shapes(self):
        grouped_shapes = {}
        if not self.show_groups:
            return grouped_shapes
        for shape in self.shapes:
            if shape.group_id is None:
                continue
            grouped_shapes.setdefault(shape.group_id, []).append(shape)
        return grouped_shapes

    def _group_rect(self, shapes):
        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")
        for shape in shapes:
            rect = shape.bounding_rect()
            if shape.shape_type == "point":
                point = shape.points[0]
                min_x = min(min_x, point.x())
                min_y = min(min_y, point.y())
                max_x = max(max_x, point.x())
                max_y = max(max_y, point.y())
            else:
                min_x = min(min_x, rect.left())
                min_y = min(min_y, rect.top())
                max_x = max(max_x, rect.right())
                max_y = max(max_y, rect.bottom())
        return QtCore.QRectF(min_x, min_y, max_x - min_x, max_y - min_y)

    def _group_label(self, group_id, shape_count):
        return f"G{group_id} · S{shape_count}"

    def _group_label_font(self):
        font = QtGui.QFont("Arial")
        font.setPointSizeF(8.0 / self.scale)
        return font

    def _group_label_rect(self, group_id, shape_count, group_rect):
        font = self._group_label_font()
        metrics = QtGui.QFontMetricsF(font)
        padding_x = 5.0 / self.scale
        padding_y = 2.0 / self.scale
        text = self._group_label(group_id, shape_count)
        width = metrics.horizontalAdvance(text) + 2 * padding_x
        height = metrics.height() + 2 * padding_y
        top = group_rect.top() - height
        return QtCore.QRectF(group_rect.left(), top, width, height)

    def _group_at_point(self, point):
        candidates = []
        tolerance = max(0.5, 6.0 / self.scale)
        for group_id, group_shapes in self._grouped_shapes().items():
            visible_shapes = [shape for shape in group_shapes if shape.visible]
            if not visible_shapes:
                continue
            rect = self._group_rect(visible_shapes)
            shape_count = len(group_shapes)
            label_rect = self._group_label_rect(
                group_id, shape_count, rect
            ).adjusted(-tolerance, -tolerance, tolerance, tolerance)
            outer = rect.adjusted(-tolerance, -tolerance, tolerance, tolerance)
            inner = rect.adjusted(tolerance, tolerance, -tolerance, -tolerance)
            on_boundary = outer.contains(point) and not inner.contains(point)
            if label_rect.contains(point) or on_boundary:
                candidates.append((rect.width() * rect.height(), group_id))
            elif rect.contains(point):
                candidates.append((rect.width() * rect.height(), group_id))
        if not candidates:
            return None
        return min(candidates, key=lambda item: item[0])[1]

    def _group_shapes(self, group_id):
        return [shape for shape in self.shapes if shape.group_id == group_id]

    def _active_group_shapes(self):
        if not self.show_groups or self._selected_group_id is None:
            return []
        shapes = self._group_shapes(self._selected_group_id)
        if len(shapes) != len(self.selected_shapes):
            return []
        if any(shape not in self.selected_shapes for shape in shapes):
            return []
        return shapes

    def _select_group(self, group_id, point):
        shapes = self._group_shapes(group_id)
        if not shapes:
            return
        self._selected_group_id = group_id
        self._hovered_group_id = group_id
        self.h_shape = None
        self.h_vertex = None
        self.h_edge = None
        self.h_cuboid_face = None
        self.h_shape_is_selected = False
        self.selection_changed.emit(shapes)
        self.calculate_offsets(point)
        self.prev_point = point
        self.override_cursor(
            CURSOR_DEFAULT
            if any(shape.locked for shape in shapes)
            else CURSOR_GRAB
        )
        self.update()

    def _hover_group(self, group_id):
        shapes = self._group_shapes(group_id)
        self._hovered_group_id = group_id
        locked = any(shape.locked for shape in shapes)
        tooltip = QCoreApplication.translate(
            "Canvas", "Group %s · %d shapes"
        ) % (group_id, len(shapes))
        if locked:
            tooltip = (
                QCoreApplication.translate("Canvas", "Locked %s") % tooltip
            )
        else:
            tooltip = (
                QCoreApplication.translate("Canvas", "Click & drag to move %s")
                % tooltip
            )
        self.setToolTip(tooltip)
        self.setStatusTip(tooltip)
        self.override_cursor(CURSOR_DEFAULT if locked else CURSOR_GRAB)
        self.update()

    def calculate_offsets(self, point):
        """Calculate offsets of a point to pixmap borders"""
        self.offsets = canvas_geometry.selection_offsets(
            self.selected_shapes,
            point,
            self.pixmap.width(),
            self.pixmap.height(),
        )

    def bounded_move_vertex(self, pos):
        """Move a vertex. Adjust position to be bounded by pixmap border"""
        index, shape = self.h_vertex, self.h_shape
        if shape.locked:
            return
        if shape.shape_type == "cuboid":
            self.move_cuboid_control(shape, index, pos)
            return
        if self.pixmap is None:
            return
        canvas_geometry.move_vertex_bounded(
            shape,
            index,
            pos,
            self.pixmap.width(),
            self.pixmap.height(),
            self.allowed_oop_shape_types,
        )

    def bounded_move_shapes(self, shapes, pos):
        """Move shapes. Adjust position to be bounded by pixmap border"""
        if self.pixmap is None:
            return False
        moved, new_pos = canvas_geometry.drag_shapes_bounded(
            shapes,
            pos,
            self.prev_point,
            self.offsets,
            self.pixmap.width(),
            self.pixmap.height(),
            self.allowed_oop_shape_types,
        )
        if moved:
            self.prev_point = new_pos
        return moved

    def rotate_point(self, p, center, theta):
        return canvas_geometry.rotate_point(p, center, theta)

    def bounded_rotate_shapes(self, i, shape, theta):
        """Rotate shapes. Adjust position to be bounded by pixmap border"""
        if shape.locked:
            return False
        if len(shape.points) == 2:
            p0 = shape.points[0]
            p1 = shape.points[1]
            shape.points = [
                p0,
                QtCore.QPointF(
                    (p0.x() + p1.x()) / 2,
                    p0.y(),
                ),
                p1,
                QtCore.QPointF(p1.x(), (p0.y() + p1.y()) / 2),
            ]
        center = QtCore.QPointF(
            (shape.points[0].x() + shape.points[2].x()) / 2,
            (shape.points[0].y() + shape.points[2].y()) / 2,
        )
        for j, p in enumerate(shape.points):
            pos = self.rotate_point(p, center, theta)
            # TODO: Reserved for now
            # if self.out_off_pixmap(pos):
            #     return False  # No need to rotate
            shape.points[j] = pos
        shape.direction = (shape.direction - theta) % (2 * math.pi)
        return True

    def deselect_shape(self):
        """Deselect all shapes"""
        self._selected_group_id = None
        if self.selected_shapes:
            self.selection_changed.emit([])
            self.h_shape_is_selected = False
            self.h_cuboid_face = None
            self.update()

    def wheelEvent(self, ev: QWheelEvent):
        """Mouse wheel event"""
        mods = ev.modifiers()
        delta = ev.angleDelta()

        if self.is_brush_mode:
            # Resize the brush instead of zooming/scrolling.
            if delta.y() == 0:
                ev.accept()
                return
            step = 1 if delta.y() > 0 else -1
            self.brush_radius = int(max(1, min(200, self.brush_radius + step)))
            self.update()
            ev.accept()
            return

        # Rectangle wheel-editing only when the user explicitly holds Alt,
        # so a plain wheel always scrolls the viewport and never silently
        # resizes a selected box (common accidental damage during browsing).
        if (
            self.editing()
            and self.enable_wheel_rectangle_editing
            and not self.auto_highlight_shape
            and len(self.selected_shapes) == 1
            and self.selected_shapes[0].shape_type == "rectangle"
            and not self.selected_shapes[0].locked
            and (mods & QtCore.Qt.KeyboardModifier.AltModifier)
            and not (mods & QtCore.Qt.KeyboardModifier.ControlModifier)
        ):
            try:
                pos = self.transform_pos(ev.position())
            except AttributeError:
                pos = self.transform_pos(ev.position())

            shape = self.selected_shapes[0]
            wheel_up = delta.y() > 0

            if shape.contains_point(pos):
                self._scale_rectangle(shape, wheel_up)
            else:
                self._adjust_rectangle_edge(shape, pos, wheel_up)

            self.store_shapes()
            self.shape_moved.emit()
            self.update()
            ev.accept()
            return

        # Shift+wheel: adjust compare view split position
        if (
            mods == QtCore.Qt.KeyboardModifier.ShiftModifier
            and self.compare_pixmap is not None
            and not self.compare_pixmap.isNull()
        ):
            step = 0.02 if delta.y() > 0 else -0.02
            self.split_position = max(
                0.0, min(1.0, self.split_position + step)
            )
            self.split_position_changed.emit(self.split_position)
            self.update()
            ev.accept()
            return

        if mods & QtCore.Qt.KeyboardModifier.ControlModifier:
            # with Ctrl/Command key
            # zoom
            self.zoom_request.emit(delta.y(), ev.position().toPoint())
        else:
            # scroll
            self.scroll_request.emit(
                delta.x(), QtCore.Qt.Orientation.Horizontal, 0
            )
            self.scroll_request.emit(
                delta.y(), QtCore.Qt.Orientation.Vertical, 0
            )
        ev.accept()

    def _scale_rectangle(self, shape, scale_up):
        """Scale rectangle from center, keeping within image bounds."""
        if self.pixmap is None:
            return
        canvas_geometry.scale_from_center(
            shape,
            scale_up,
            self.rect_scale_step,
            self.pixmap.width(),
            self.pixmap.height(),
        )

    def _adjust_rectangle_edge(self, shape, cursor_pos, move_outward):
        """Adjust the rectangle edge closest to the cursor."""
        if self.pixmap is None:
            return
        canvas_geometry.adjust_edge(
            shape,
            cursor_pos,
            move_outward,
            self.rect_adjust_step,
            self.pixmap.width(),
            self.pixmap.height(),
        )

    def move_by_keyboard(self, offset):
        """Move selected shapes by an offset (using keyboard)"""
        if self.selected_shapes:
            group_shapes = self._active_group_shapes()
            if group_shapes and any(shape.locked for shape in group_shapes):
                return
            self.bounded_move_shapes(
                self.selected_shapes, self.prev_point + offset
            )
            self.update()
            self.moving_shape = True

    def rotate_by_keyboard(self, theta):
        """Rotate selected shapes by an theta (using keyboard)"""
        if self.selected_shapes:
            rotating_shape = False
            for i, shape in enumerate(self.selected_shapes):
                if shape._shape_type == "rotation":
                    self.bounded_rotate_shapes(i, shape, theta)
                    rotating_shape = True
            if rotating_shape:
                self.update()
                self.rotating_shape = True

    def keyPressEvent(self, ev):  # noqa: C901
        """Key press event"""
        modifiers = ev.modifiers()
        key = ev.key()
        if key == QtCore.Qt.Key.Key_Space and not ev.isAutoRepeat():
            self._space_pressed = True
            self._clear_space_pan_hover_state()
            if self._space_panning:
                self.override_cursor(CURSOR_MOVE)
            else:
                self.override_cursor(CURSOR_GRAB)
            ev.accept()
            return
        if self.is_brush_mode and self.editing():
            if self._brush_key_press(ev):
                return
        if self.drawing():
            if key == QtCore.Qt.Key.Key_Escape and self.current:
                self.current = None
                self._brush_drawing = False
                self.drawing_polygon.emit(False)
                self.update()
            elif key == QtCore.Qt.Key.Key_Backspace and self.current:
                if self.create_mode in ["polygon", "linestrip"]:
                    if len(self.current.points) > 1:
                        self.current.points.pop()
                        self.line[0] = self.current[-1]
                        self.update()
                    elif len(self.current.points) == 1:
                        self.current = None
                        self._brush_drawing = False
                        self.drawing_polygon.emit(False)
                        self.update()
            elif key == QtCore.Qt.Key.Key_Return and self.can_close_shape():
                self.finalise()
            elif modifiers == QtCore.Qt.KeyboardModifier.AltModifier:
                self.snapping = False
        elif self.editing():
            if key == QtCore.Qt.Key.Key_Escape:
                self.deselect_shape()
                return
            if (
                key == QtCore.Qt.Key.Key_Alt
                and self.can_erase_selected_vertices()
            ):
                self.override_cursor(self._vertex_eraser_cursor())
                self._set_vertex_eraser_tooltip()
                ev.accept()
                return
            move_speed = MOVE_SPEED
            if self._active_group_shapes():
                move_speed = (
                    10.0
                    if modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier
                    else 1.0
                )
            if key == QtCore.Qt.Key.Key_Up:
                self.move_by_keyboard(QtCore.QPointF(0.0, -move_speed))
            elif key == QtCore.Qt.Key.Key_Down:
                self.move_by_keyboard(QtCore.QPointF(0.0, move_speed))
            elif key == QtCore.Qt.Key.Key_Left:
                self.move_by_keyboard(QtCore.QPointF(-move_speed, 0.0))
            elif key == QtCore.Qt.Key.Key_Right:
                self.move_by_keyboard(QtCore.QPointF(move_speed, 0.0))
            elif key in (
                QtCore.Qt.Key.Key_Z,
                QtCore.Qt.Key.Key_X,
                QtCore.Qt.Key.Key_C,
                QtCore.Qt.Key.Key_V,
            ):
                # Z/X/C/V rotate selected boxes. Ctrl+Z/X/C/V are undo /
                # cut / copy / paste and must not also rotate (that combo
                # used to crash on Ctrl+Z).
                if modifiers & (
                    QtCore.Qt.KeyboardModifier.ControlModifier
                    | QtCore.Qt.KeyboardModifier.MetaModifier
                    | QtCore.Qt.KeyboardModifier.AltModifier
                ):
                    return
                if key == QtCore.Qt.Key.Key_Z:
                    self.rotate_by_keyboard(self.large_rotation_increment)
                elif key == QtCore.Qt.Key.Key_X:
                    self.rotate_by_keyboard(self.small_rotation_increment)
                elif key == QtCore.Qt.Key.Key_C:
                    self.rotate_by_keyboard(-self.small_rotation_increment)
                else:
                    self.rotate_by_keyboard(-self.large_rotation_increment)

    def keyReleaseEvent(self, ev):
        """Key release event"""
        modifiers = ev.modifiers()
        key = ev.key()
        if key == QtCore.Qt.Key.Key_Space and not ev.isAutoRepeat():
            self._space_pressed = False
            self._space_panning = False
            self._space_pan_prev_point = None
            self._restore_space_pan_cursor()
            ev.accept()
            return
        if (
            key == QtCore.Qt.Key.Key_Alt
            and self.editing()
            and not ev.isAutoRepeat()
        ):
            self._vertex_erasing = False
            self.override_cursor(CURSOR_DEFAULT)
            ev.accept()
            return
        if self.drawing():
            if modifiers == QtCore.Qt.KeyboardModifier.NoModifier:
                self.snapping = True
        elif self.editing():
            # NOTE: Temporary fix to avoid ValueError
            # when the selected shape is not in the shapes list
            if (
                (self.moving_shape or self.rotating_shape)
                and self.selected_shapes
                and self.selected_shapes[0] in self.shapes
            ):
                index = self.shapes.index(self.selected_shapes[0])
                if (
                    self.shapes_backups
                    and index < len(self.shapes_backups[-1])
                    and self.shapes_backups[-1][index].points
                    != self.shapes[index].points
                ):
                    self.store_shapes()
                    if self.moving_shape:
                        self.shape_moved.emit()
                    if self.rotating_shape:
                        self.shape_rotated.emit()

                if self.moving_shape:
                    self.moving_shape = False
                if self.rotating_shape:
                    self.rotating_shape = False
