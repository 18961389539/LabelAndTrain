"""This module defines Canvas widget - the core component for drawing image labels"""

import math

import cv2
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QTimer

from anylabeling.services.auto_labeling.types import AutoLabelingMode
from anylabeling.views.labeling.utils.theme import get_theme

from .. import utils
from ..shape import Shape
from . import canvas_geometry
from .canvas_brush import BrushCanvasMixin
from .canvas_cuboid import (  # noqa: F401
    CUBOID_BACK_EDGE_CENTER_INDICES,
    CUBOID_FACE_BACK,
    CUBOID_FACE_BOTTOM,
    CUBOID_FACE_LEFT,
    CUBOID_FACE_FRONT,
    CUBOID_FACE_RIGHT,
    CUBOID_FACE_TOP,
    CUBOID_FRONT_EDGE_CENTER_INDICES,
    CuboidCanvasMixin,
)
from .canvas_interaction import CanvasInteractionMixin, CanvasInteractionState
from .canvas_render import CanvasRenderMixin, CanvasRenderState
from .canvas_rotation import (  # noqa: F401
    CURSOR_DEFAULT,
    CURSOR_DRAW,
    CURSOR_GRAB,
    CURSOR_MOVE,
    CURSOR_POINT,
    ROTATION_HANDLE_DISTANCE,
    ROTATION_HANDLE_HIT_RADIUS,
    ROTATION_HANDLE_SNAP_DEGREES,
    CanvasRotationMixin,
)
from .shape_history import ShapeHistoryMixin, ShapeHistoryStore

LARGE_ROTATION_INCREMENT = math.radians(1.0)
SMALL_ROTATION_INCREMENT = math.radians(0.1)


class Canvas(
    ShapeHistoryMixin,
    BrushCanvasMixin,
    CanvasRotationMixin,
    CuboidCanvasMixin,
    CanvasInteractionMixin,
    CanvasRenderMixin,
    QtWidgets.QWidget,
):  # pylint: disable=too-many-public-methods, too-many-instance-attributes
    """Canvas widget to handle label drawing"""

    zoom_request = QtCore.pyqtSignal(int, QtCore.QPoint)
    scroll_request = QtCore.pyqtSignal(float, object, int)
    # [Feature] support for automatically switching to editing mode
    # when the cursor moves over an object
    mode_changed = QtCore.pyqtSignal()
    new_shape = QtCore.pyqtSignal()
    show_shape = QtCore.pyqtSignal(int, int, QtCore.QPointF)
    selection_changed = QtCore.pyqtSignal(list)
    shape_moved = QtCore.pyqtSignal()
    shape_rotated = QtCore.pyqtSignal()
    shapes_deleted = QtCore.pyqtSignal(list)
    drawing_polygon = QtCore.pyqtSignal(bool)
    vertex_selected = QtCore.pyqtSignal(bool)
    auto_labeling_marks_updated = QtCore.pyqtSignal(list)
    auto_decode_requested = QtCore.pyqtSignal(list)
    auto_decode_finish_requested = QtCore.pyqtSignal()
    shape_hover_changed = QtCore.pyqtSignal()
    split_position_changed = QtCore.pyqtSignal(float)
    edit_label_requested = QtCore.pyqtSignal()
    # Emitted when brush-edit mode is toggled on/off (keeps the UI in sync).
    brush_mode_changed = QtCore.pyqtSignal(bool)
    brush_history_changed = QtCore.pyqtSignal(bool)

    CREATE, EDIT = 0, 1

    # polygon, rectangle, rotation, line, or point
    _create_mode = "polygon"

    _fill_drawing = False

    def __init__(self, *args, **kwargs):
        self.epsilon = kwargs.pop("epsilon", 10.0)
        self.double_click = kwargs.pop("double_click", "close")
        if self.double_click not in [None, "close"]:
            raise ValueError(
                f"Unexpected value for double_click event: {self.double_click}"
            )
        self.double_click_edit_label = kwargs.pop(
            "double_click_edit_label", True
        )
        self.num_backups = kwargs.pop("num_backups", 100)
        self.wheel_rectangle_editing = kwargs.pop(
            "wheel_rectangle_editing", {}
        )
        self.enable_wheel_rectangle_editing = self.wheel_rectangle_editing.get(
            "enable", False
        )
        self.rect_adjust_step = self.wheel_rectangle_editing.get(
            "adjust_step", 2.0
        )
        self.rect_scale_step = self.wheel_rectangle_editing.get(
            "scale_step", 0.05
        )
        self.auto_highlight_shape = kwargs.pop("auto_highlight_shape", False)
        self.attributes_config = kwargs.pop("attributes", {})
        self.rotation_config = kwargs.pop("rotation", {})
        self.mask_config = kwargs.pop("mask", {})
        self.brush_config = kwargs.pop("brush", {})
        self.cuboid_config = kwargs.pop("cuboid", {})
        self.parent = kwargs.pop("parent")
        super().__init__(*args, **kwargs)
        self.interaction_state = CanvasInteractionState(edit_mode=self.EDIT)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(
            QtGui.QPalette.ColorRole.Window,
            QtGui.QColor(get_theme()["background"]),
        )
        self.setPalette(palette)
        # Initialise local state.
        self.is_auto_labeling = False
        self.auto_labeling_mode: AutoLabelingMode = None
        self.shapes = []
        # Undo/redo, keyed by the image on screen: a detour through
        # another file no longer throws them away.
        self.shape_history = ShapeHistoryStore()
        self.scale = 1.0
        self.pixmap = QtGui.QPixmap()
        self.visible = {}
        self.allowed_oop_shape_types = ["rotation", "quadrilateral", "cuboid"]
        default_cuboid_depth_vector = self.cuboid_config.get(
            "default_depth_vector", [24.0, -24.0]
        )
        if (
            not isinstance(default_cuboid_depth_vector, (list, tuple))
            or len(default_cuboid_depth_vector) != 2
        ):
            default_cuboid_depth_vector = [24.0, -24.0]
        self.cuboid_default_depth_vector = [
            float(default_cuboid_depth_vector[0]),
            float(default_cuboid_depth_vector[1]),
        ]
        self.cuboid_min_depth = float(self.cuboid_config.get("min_depth", 5.0))
        self._painter = QtGui.QPainter()
        self._cursor = CURSOR_DEFAULT
        # Menus:
        # 0: right-click without selection and dragging of shapes
        # 1: right-click with selection and dragging of shapes
        self.menus = (QtWidgets.QMenu(), QtWidgets.QMenu())
        # Set widget options.
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.WheelFocus)
        # Render flags, colors and loading/compare state live in
        # CanvasRenderState; the descriptors on CanvasRenderMixin keep the
        # historical attribute names for actions, settings and tests.
        self.render_state = CanvasRenderState(
            attributes_config=self.attributes_config,
            mask_config=self.mask_config,
            loading_text=self.tr("Loading..."),
        )

        # Set rotation increment options.
        self.large_rotation_increment = math.radians(
            self.rotation_config.get("large_increment", 1.0)
        )
        self.small_rotation_increment = math.radians(
            self.rotation_config.get("small_increment", 0.1)
        )

        # Auto mask decode mode
        self.auto_decode_mode = False
        self.auto_decode_timer = QTimer()
        self.auto_decode_timer.timeout.connect(self.on_auto_decode_timeout)
        self.auto_decode_timer.setSingleShot(True)
        self.auto_decode_tracklet = []

        # Brush drawing mode for polygon
        self._brush_drawing = False
        self.brush_point_distance = self.brush_config.get(
            "point_distance", 25.0
        )

        # Brush edit mode (refine a selected shape by painting/erasing).
        self.is_brush_mode = False
        self.brush_radius = 12  # in image pixels
        self.eraser_mode = False  # True while Ctrl is held
        self._brush_target_shape = None
        self._brush_original_shape = None
        self._prev_brush_pos = None
        # shape -> (mask_version, outline_path)
        self._brush_overlay_cache = {}
        self._brush_modified = False
        # Mask -> polygon simplification tolerance, in image pixels.
        self.brush_simplify_epsilon_px = float(
            self.brush_config.get("simplify_epsilon", 2.0)
        )
        # Per-stroke mask snapshots powering brush undo/redo.
        self._brush_undo_stack = []
        self._brush_redo_stack = []
        self._brush_baseline_mask = None
        self._brush_stroke_dirty = False
        self._brush_max_undo_steps = max(
            1, int(self.brush_config.get("max_undo_steps", 30))
        )
        self._brush_max_undo_bytes = (
            max(1, int(self.brush_config.get("max_undo_memory_mb", 128)))
            * 1024
            * 1024
        )

    def set_loading(self, is_loading: bool, loading_text: str = None):
        """Set loading state"""
        self.is_loading = is_loading
        if loading_text:
            self.loading_text = loading_text
        self.update()

    def set_auto_labeling_mode(self, mode: AutoLabelingMode):
        """Set auto labeling mode"""
        if mode == AutoLabelingMode.NONE:
            self.is_auto_labeling = False
            self.auto_labeling_mode = mode
        else:
            self.is_auto_labeling = True
            self.auto_labeling_mode = mode
            self.create_mode = mode.shape_type
            self.parent.toggle_draw_mode(
                False, mode.shape_type, disable_auto_labeling=False
            )

    def set_auto_decode_mode(self, enabled: bool):
        """Set auto decode mode"""
        if self.auto_decode_mode and not enabled:
            self.reset_auto_decode_state()
        self.auto_decode_mode = enabled

    def reset_auto_decode_state(self):
        """Reset auto decode state"""
        if self.auto_decode_timer.isActive():
            self.auto_decode_timer.stop()
        self.auto_decode_tracklet.clear()
        self.last_mouse_pos = None

    def fill_drawing(self):
        """Get option to fill shapes by color"""
        return self._fill_drawing

    def set_fill_drawing(self, value):
        """Set shape filling option"""
        self._fill_drawing = value
        self.update()

    @property
    def create_mode(self):
        """Create mode for canvas - Modes: polygon, rectangle, rotation, circle,..."""
        return self._create_mode

    @create_mode.setter
    def create_mode(self, value):
        """Set create mode for canvas"""
        if value not in Shape.get_supported_shape():
            raise ValueError(f"Unsupported create_mode: {value}")
        self._create_mode = value

    def store_shapes(self):
        """Store shapes for restoring later (Undo feature)"""
        self.shape_history.push(
            [shape.copy() for shape in self.shapes], self.num_backups
        )

    def clip_rectangle_to_pixmap(self, shape):
        """Clip rectangle shape to pixmap boundaries"""
        if self.pixmap is None:
            return True
        return canvas_geometry.clip_rectangle_to_pixmap(
            shape, self.pixmap.width(), self.pixmap.height()
        )

    @property
    def is_shape_restorable(self):
        """Check if shape can be restored from backup"""
        return self.shape_history.can_undo()

    @property
    def is_shape_redoable(self):
        """Check if a previously undone state can be re-applied"""
        return self.shape_history.can_redo()

    def restore_shape(self):
        """Restore/Undo a shape"""
        # This does _part_ of the job of restoring shapes. The rest is
        # done by the caller (label_widget
        # _reload_shapes_after_history_change), and Canvas.load_shapes
        # pushes the restored state right back onto the stack.
        shapes_backup = self.shape_history.undo()
        if shapes_backup is None:
            return
        self.shapes = [shape.copy() for shape in shapes_backup]
        self.selected_shapes = []
        self._selected_group_id = None
        self._hovered_group_id = None
        self.h_shape = None
        self.prev_h_shape = None
        self.h_vertex = None
        self.h_edge = None
        for shape in self.shapes:
            shape.selected = False
        self.update()

    def redo_shape(self):
        """Re-apply the most recently undone state (Redo).

        Mirrors restore_shape(): the re-applied state is pushed onto the
        undo stack by the caller via Canvas.load_shapes, exactly like the
        normal edit flow.
        """
        shapes_backup = self.shape_history.redo()
        if shapes_backup is None:
            return
        self.shapes = [shape.copy() for shape in shapes_backup]
        self.selected_shapes = []
        self._selected_group_id = None
        self._hovered_group_id = None
        self.h_shape = None
        self.prev_h_shape = None
        self.h_vertex = None
        self.h_edge = None
        for shape in self.shapes:
            shape.selected = False
        self.update()

    def is_visible(self, shape):
        """Check if a shape is visible"""
        return self.visible.get(shape, True)

    # ------------------------------------------------------------------ #
    # Brush edit mode
    #
    # Refine a single selected shape by painting (add) or Ctrl+painting
    # (erase) onto a rasterized mask, resize the brush with the mouse
    # wheel, then convert the mask back into a simplified polygon on exit.
    # ------------------------------------------------------------------ #

    def set_auto_labeling(self, value=True):
        """Set auto labeling mode"""
        self.is_auto_labeling = value
        if self.auto_labeling_mode is None:
            self.auto_labeling_mode = AutoLabelingMode.NONE
            self.parent.toggle_draw_mode(
                True, "rectangle", disable_auto_labeling=True
            )

    # QT Overload

    # QT Overload

    # QT Overload

    def end_move(self, copy):
        """End of move"""
        assert self.selected_shapes and self.selected_shapes_copy
        assert len(self.selected_shapes_copy) == len(self.selected_shapes)
        if copy:
            for i, shape in enumerate(self.selected_shapes_copy):
                self.shapes.append(shape)
                self.selected_shapes[i].selected = False
                self.selected_shapes[i] = shape
        else:
            for i, shape in enumerate(self.selected_shapes_copy):
                self.selected_shapes[i].points = shape.points
        self.selected_shapes_copy = []
        self.update()
        self.store_shapes()
        return True

    def can_close_shape(self):
        """Check if a shape can be closed (number of points > 2)"""
        return self.drawing() and self.current and len(self.current) > 2

    # QT Overload

    def delete_selected(self):
        """Remove selected shapes"""
        deleted_shapes = []
        if self.selected_shapes:
            for shape in self.selected_shapes:
                if not shape.locked and shape in self.shapes:
                    self.shapes.remove(shape)
                    deleted_shapes.append(shape)
            if deleted_shapes:
                self.store_shapes()
            self.selected_shapes = [
                shape for shape in self.selected_shapes if shape.locked
            ]
            self.update()
        return deleted_shapes

    def delete_shape(self, shape):
        """Remove a specific shape"""
        if shape.locked:
            return
        if shape in self.selected_shapes:
            self.selected_shapes.remove(shape)
        if shape in self.shapes:
            self.shapes.remove(shape)
        self.store_shapes()
        self.update()

    def duplicate_selected_shapes(self):
        """Duplicate selected shapes"""
        if self.selected_shapes:
            self.selected_shapes_copy = [
                s.copy() for s in self.selected_shapes
            ]
            for shape in self.selected_shapes_copy:
                shape.locked = False
            self.bounded_shift_shapes(self.selected_shapes_copy)
            self.end_move(copy=True)
        return self.selected_shapes

    def bounded_shift_shapes(self, shapes):
        """
        Shift shapes by an offset. Adjust positions to be bounded
        by pixmap borders
        """
        # Try to move in one direction, and if it fails in another.
        # Give up if both fail.
        point = shapes[0][0]
        offset = QtCore.QPointF(2.0, 2.0)
        self.offsets = QtCore.QPointF(), QtCore.QPointF()
        self.prev_point = point
        if not self.bounded_move_shapes(shapes, point - offset):
            self.bounded_move_shapes(shapes, point + offset)

    def prepare_pasted_shapes(self, shapes, copied_group_id=None):
        pasted_shapes = [shape.copy() for shape in shapes]
        if not pasted_shapes:
            return pasted_shapes
        for shape in pasted_shapes:
            shape.locked = False
        if copied_group_id is not None and all(
            shape.group_id == copied_group_id for shape in pasted_shapes
        ):
            group_id = self.gen_new_group_id()
            for shape in pasted_shapes:
                shape.group_id = group_id
        return pasted_shapes

    def transform_pos(self, point):
        """Convert from widget-logical coordinates to painter-logical ones."""
        return point / self.scale - self.offset_to_center()

    def offset_to_center(self):
        """Calculate offset to the center"""
        if self.pixmap is None:
            return QtCore.QPointF()
        s = self.scale
        area = super().size()
        w, h = self.pixmap.width() * s, self.pixmap.height() * s
        area_width, area_height = area.width(), area.height()
        x = (area_width - w) / (2 * s) if area_width > w else 0
        y = (area_height - h) / (2 * s) if area_height > h else 0
        return QtCore.QPointF(x, y)

    def out_off_pixmap(self, p):
        """Check if a position is out of pixmap"""
        if self.pixmap is None:
            return True
        w, h = self.pixmap.width(), self.pixmap.height()
        return not (0 <= p.x() <= w - 1 and 0 <= p.y() <= h - 1)

    def finalise(self):
        """Finish drawing for a shape"""
        assert self.current
        self._brush_drawing = False
        if (
            self.is_auto_labeling
            and self.auto_labeling_mode != AutoLabelingMode.NONE
        ):
            self.current.label = self.auto_labeling_mode.edit_mode
        if self.current.label is None:
            self.current.label = ""
        self.current.close()
        if self.current.shape_type == "rectangle":
            if not self.clip_rectangle_to_pixmap(self.current):
                self.current = None
                self.drawing_polygon.emit(False)
                self.update()
                return
        elif self.current.shape_type == "rotation":
            if not self.clip_rotation_to_pixmap(self.current):
                self.current = None
                self.drawing_polygon.emit(False)
                self.update()
                return
        elif self.current.shape_type == "cuboid":
            self.current.sync_cuboid_depth_vector()

        self.shapes.append(self.current)
        self.store_shapes()
        self.current = None
        self.new_shape.emit()
        self.update()
        if self.is_auto_labeling:
            self.update_auto_labeling_marks()

    def update_auto_labeling_marks(self):
        """Update the auto labeling marks"""
        marks = []
        for shape in self.shapes:
            if shape.label == AutoLabelingMode.ADD:
                if shape.shape_type == AutoLabelingMode.POINT:
                    marks.append(
                        {
                            "type": "point",
                            "data": [
                                int(shape.points[0].x()),
                                int(shape.points[0].y()),
                            ],
                            "label": 1,
                        }
                    )
                elif shape.shape_type == AutoLabelingMode.RECTANGLE:
                    marks.append(
                        {
                            "type": "rectangle",
                            "data": [
                                int(shape.points[0].x()),
                                int(shape.points[0].y()),
                                int(shape.points[2].x()),
                                int(shape.points[2].y()),
                            ],
                            "label": 1,
                        }
                    )
            elif shape.label == AutoLabelingMode.REMOVE:
                if shape.shape_type == AutoLabelingMode.POINT:
                    marks.append(
                        {
                            "type": "point",
                            "data": [
                                int(shape.points[0].x()),
                                int(shape.points[0].y()),
                            ],
                            "label": 0,
                        }
                    )
                elif shape.shape_type == AutoLabelingMode.RECTANGLE:
                    marks.append(
                        {
                            "type": "rectangle",
                            "data": [
                                int(shape.points[0].x()),
                                int(shape.points[0].y()),
                                int(shape.points[2].x()),
                                int(shape.points[2].y()),
                            ],
                            "label": 0,
                        }
                    )

        self.auto_labeling_marks_updated.emit(marks)

    def close_enough(self, p1, p2):
        """Check if 2 points are close enough (by an threshold epsilon)"""
        # d = distance(p1 - p2)
        # m = (p1-p2).manhattanLength()
        # print "d %.2f, m %d, %.2f" % (d, m, d - m)
        # divide by scale to allow more precision when zoomed in
        return utils.distance(p1 - p2) < (self.epsilon / self.scale)

    def intersection_point(self, p1, p2):
        """Cycle through each image edge in clockwise fashion,
        and find the one intersecting the current line segment.
        """
        size = self.pixmap.size()
        return canvas_geometry.line_image_intersection(
            p1, p2, size.width(), size.height()
        )

    # These two, along with a call to adjustSize are required for the
    # scroll area.
    # QT Overload
    def sizeHint(self):
        """Get size hint"""
        return self.minimumSizeHint()

    # QT Overload
    def minimumSizeHint(self):
        """Get minimum size hint"""
        if self.pixmap:
            return self.scale * self.pixmap.size()
        return super().minimumSizeHint()

    # QT Overload

    # QT Overload

    # QT Overload

    def set_last_label(self, text, flags, group_id):
        """Set label and flags for last shape"""
        assert text
        if self.is_auto_labeling:
            self.shapes[-1].label = self.auto_labeling_mode.edit_mode
        else:
            self.shapes[-1].label = text
        self.shapes[-1].flags = flags
        self.shapes[-1].group_id = group_id
        self.shapes_backups.pop()
        self.store_shapes()
        return self.shapes[-1]

    def undo_last_line(self):
        """Undo last line"""
        assert self.shapes
        self.current = self.shapes.pop()
        self.current.set_open()
        if self.create_mode in ["polygon", "linestrip", "quadrilateral"]:
            self.line.points = [self.current[-1], self.current[0]]
        elif self.create_mode in [
            "rectangle",
            "line",
            "circle",
            "rotation",
            "cuboid",
        ]:
            self.current.points = self.current.points[0:1]
        elif self.create_mode == "point":
            self.current = None
        self.drawing_polygon.emit(True)

    def undo_last_point(self):
        """Undo last point"""
        if not self.current or self.current.is_closed():
            return
        self.current.pop_point()
        if len(self.current) > 0:
            self.line[0] = self.current[-1]
        else:
            self.current = None
            self._brush_drawing = False
            self.drawing_polygon.emit(False)
        self.update()

    def load_pixmap(self, pixmap, clear_shapes=True):
        """Load pixmap"""
        self.cancel_brush_mode()
        self.pixmap = pixmap
        if clear_shapes:
            self.shapes = []
        self.update()

    def load_shapes(self, shapes, replace=True):
        """Load shapes"""
        self.cancel_brush_mode()
        if replace:
            self.shapes = list(shapes)
        else:
            self.shapes.extend(shapes)
        self.store_shapes()
        self.current = None
        self._brush_drawing = False
        self.h_shape = None
        self.h_vertex = None
        self.h_edge = None
        self.h_cuboid_face = None
        self._selected_group_id = None
        self._hovered_group_id = None
        self.update()

    def set_shape_visible(self, shape, value):
        """Set visibility for a shape"""
        self.visible[shape] = value
        self.update()

    def current_cursor(self):
        """Current cursor"""
        cursor = QtWidgets.QApplication.overrideCursor()
        cursor = cursor.shape() if cursor else None

        return cursor

    def override_cursor(self, cursor):
        """Override cursor"""
        current_cursor = self.current_cursor()
        cursor_shape = (
            cursor.shape() if isinstance(cursor, QtGui.QCursor) else cursor
        )
        if current_cursor != cursor_shape:
            self._cursor = cursor
            if current_cursor is None:
                QtWidgets.QApplication.setOverrideCursor(cursor)
            else:
                QtWidgets.QApplication.changeOverrideCursor(cursor)

    def restore_cursor(self):
        """Restore override cursor"""
        QtWidgets.QApplication.restoreOverrideCursor()

    def reset_state(self):
        """Clear shapes and pixmap"""
        self._clear_space_pan_state()
        self.restore_cursor()
        self.pixmap = None
        # Bank this image's history rather than dropping it: leaving a
        # file is not a decision to forget what was done in it.
        self.shape_history.leave()
        self.is_move_editing = False
        self.compare_pixmap = None
        self._selected_group_id = None
        self._hovered_group_id = None
        self.update()

    def set_cross_line(self, show, width, color, opacity):
        """Set cross line options"""
        self.cross_line_show = show
        self.cross_line_width = width
        self.cross_line_color = color
        self.cross_line_opacity = opacity
        self.update()

    def gen_new_group_id(self):
        """Generate new shape's group_id based on current shapes"""
        max_group_id = 0
        for shape in self.shapes:
            if shape.group_id is not None:
                max_group_id = max(max_group_id, shape.group_id)
        return max_group_id + 1

    def merge_group_ids(self, group_ids, new_group_id):
        """Merge multiple shapes' group_id into a new one"""
        for shape in self.shapes:
            if shape.group_id in group_ids:
                shape.group_id = new_group_id

    def group_selected_shapes(self):
        """Group selected shapes"""
        if len(self.selected_shapes) == 0:
            return

        # List all group ids for selected shapes
        group_ids = set()
        has_non_group_shape = False
        for shape in self.selected_shapes:
            if shape.group_id is not None:
                group_ids.add(shape.group_id)
            else:
                has_non_group_shape = True

        # If there is at least 1 shape having a group id,
        # use that id as the new group id. Otherwise, generate a new group_id
        new_group_id = None
        if len(group_ids) > 0:
            new_group_id = min(group_ids)
        else:
            new_group_id = self.gen_new_group_id()

        # Merge group ids
        if len(group_ids) > 1:
            self.merge_group_ids(
                group_ids=group_ids, new_group_id=new_group_id
            )
        # Assign new_group_id to non-group shapes
        if has_non_group_shape:
            for shape in self.selected_shapes:
                if shape.group_id is None:
                    shape.group_id = new_group_id

        self.update()

    def ungroup_selected_shapes(self):
        """Ungroup selected shapes"""
        if len(self.selected_shapes) == 0:
            return

        # List all group ids for selected shapes
        group_ids = set()
        for shape in self.selected_shapes:
            if shape.group_id is not None:
                group_ids.add(shape.group_id)

        for group_id in group_ids:
            for shape in self.shapes:
                if shape.group_id == group_id:
                    shape.group_id = None

        self.update()
