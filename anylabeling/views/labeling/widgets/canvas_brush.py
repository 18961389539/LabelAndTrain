"""Brush / bitmap-edit behaviour for the Canvas widget.

Split out of canvas.py (batch 5-2) as a mixin: the methods stay on
the Canvas class, so the paint / mouse-event entry points, the
label-widget call sites and the tests keep working unchanged. All
brush state (masks, undo stacks, mode flags) still lives in
``Canvas.__init__``.
"""

import copy
import math

import cv2
import numpy as np
from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt

from anylabeling.services.auto_labeling.types import AutoLabelingMode
from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils.qt import new_icon_path
from anylabeling.views.labeling.utils.theme import get_theme

from .. import utils
from ..shape import Shape
from .canvas_rotation import CURSOR_DEFAULT, CURSOR_MOVE, CURSOR_POINT


class BrushCanvasMixin:
    """Mask-based brush editing, undo and rendering."""

    """Mask-based brush editing, undo and rendering."""

    @staticmethod
    def _polygon_to_mask(points_xy: list, shape_hw: tuple) -> np.ndarray:
        """Rasterize polygon vertices into a binary ``uint8`` mask.

        Args:
            points_xy: Polygon vertices as ``(x, y)`` integer pairs.
            shape_hw: Target mask shape as ``(height, width)``.

        Returns:
            A ``(height, width)`` ``uint8`` array with filled pixels set
            to ``255`` and the background set to ``0``.
        """
        h, w = shape_hw
        mask = np.zeros((h, w), dtype=np.uint8)
        if not points_xy:
            return mask
        pts = np.array(points_xy, dtype=np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(mask, [pts], 255)
        return mask

    @staticmethod
    def _mask_to_polylines(mask: np.ndarray) -> list:
        """Extract a mask's external contours as polylines.

        Args:
            mask: A 2D ``uint8`` mask whose non-zero pixels are foreground.

        Returns:
            A list of polylines, each a list of ``(x, y)`` integer tuples.
            Contours with fewer than three points are dropped.
        """
        if mask is None:
            return []
        if mask.dtype != np.uint8:
            mask = (mask > 0).astype(np.uint8) * 255
        if mask.ndim != 2:
            mask = mask.squeeze()
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        polylines = []
        for cnt in contours:
            if cnt is None or len(cnt) < 3:
                continue
            pts = cnt.reshape(-1, 2)
            polylines.append([(int(x), int(y)) for x, y in pts])
        return polylines

    @staticmethod
    def _apply_brush_to_mask(
        mask: np.ndarray,
        x: float,
        y: float,
        radius: int,
        add: bool = True,
    ) -> np.ndarray:
        """Stamp a filled circle onto a mask in place.

        Args:
            mask: The 2D ``uint8`` mask to modify.
            x: Circle center x coordinate, in image pixels.
            y: Circle center y coordinate, in image pixels.
            radius: Brush radius in image pixels (clamped to ``>= 1``).
            add: If ``True`` paint foreground (``255``); otherwise erase
                to background (``0``).

        Returns:
            The same mask instance, modified in place.
        """
        if mask is None:
            return mask
        cv2.circle(
            mask,
            (int(round(x)), int(round(y))),
            max(1, int(round(radius))),
            255 if add else 0,
            thickness=-1,
            lineType=cv2.LINE_8,
        )
        return mask

    @staticmethod
    def _simplify_contour(cnt: np.ndarray, epsilon_px: float) -> list:
        """Simplify a contour with the Ramer-Douglas-Peucker algorithm.

        Args:
            cnt: An OpenCV contour of shape ``(N, 1, 2)``.
            epsilon_px: Approximation tolerance in image pixels. A value of
                zero preserves the extracted contour.

        Returns:
            A list of simplified ``(x, y)`` integer vertices, or an empty
            list when the result would have fewer than three points.
        """
        if cnt is None or len(cnt) < 3:
            return []
        eps = max(0.0, float(epsilon_px))
        if eps == 0:
            pts = cnt.reshape(-1, 2)
            return [(int(x), int(y)) for x, y in pts]
        approx = cv2.approxPolyDP(cnt, eps, True)
        if approx is None or len(approx) < 3:
            return []
        pts = approx.reshape(-1, 2)
        return [(int(x), int(y)) for x, y in pts]

    def _ensure_brush_mask(self, shape: Shape) -> None:
        """Ensure ``shape`` owns an editable mask buffer.

        If the shape has no mask yet, one is rasterized from its current
        polygon points at the image resolution. The ``_brush_using_mask``
        flag is always set so the canvas renders the mask in place of the
        vector polygon.

        Args:
            shape: The shape being brush-edited.
        """
        if shape is None or self.pixmap is None:
            return
        if getattr(shape, "mask", None) is None:
            h, w = int(self.pixmap.height()), int(self.pixmap.width())
            points = [
                (int(round(point.x())), int(round(point.y())))
                for point in shape.points
            ]
            shape.mask = self._polygon_to_mask(points, (h, w))
            shape._brush_mask_version = 0
        shape._brush_using_mask = True

    def _update_shape_points_from_mask(self, shape: Shape) -> bool:
        """Rewrite ``shape.points`` from its mask's largest component.

        The largest external contour is simplified and stored as the new
        polygon. Donut holes are not supported and are discarded.

        Args:
            shape: The brush-edited shape whose mask is converted back
                into polygon vertices.

        Returns:
            ``True`` when a valid polygon was produced.
        """
        if shape is None or getattr(shape, "mask", None) is None:
            return False
        polylines = self._mask_to_polylines(shape.mask)
        if not polylines:
            shape.points = []
            return False
        best = None
        best_area = -1.0
        for poly in polylines:
            if len(poly) < 3:
                continue
            area = float(cv2.contourArea(np.array(poly, dtype=np.int32)))
            if area > best_area:
                best_area = area
                best = poly
        if best is None or len(best) < 3:
            shape.points = []
            return False
        cnt = np.array(best, dtype=np.int32).reshape((-1, 1, 2))
        outer = self._simplify_contour(cnt, self.brush_simplify_epsilon_px)
        if len(outer) < 3:
            outer = best
        shape.mask.fill(0)
        cv2.fillPoly(shape.mask, [cnt], 255)
        self._bump_brush_version(shape)
        shape.shape_type = "polygon"
        shape.points = [QtCore.QPointF(float(x), float(y)) for x, y in outer]
        # Donut holes are not representable as a single polygon.
        shape.other_data.pop("holes", None)
        shape.close()
        return True

    def _invalidate_brush_cache(self, shape: Shape) -> None:
        """Drop the cached overlay image for ``shape``.

        Args:
            shape: The shape whose render cache is invalidated so the next
                paint regenerates it.
        """
        if shape is None:
            return
        self._brush_overlay_cache.pop(shape, None)

    def _bump_brush_version(self, shape: Shape) -> None:
        """Advance a shape's mask version and invalidate its cache.

        Args:
            shape: The shape whose rendered overlay must be refreshed.
        """
        shape._brush_mask_version = (
            int(getattr(shape, "_brush_mask_version", 0)) + 1
        )
        self._invalidate_brush_cache(shape)

    def _get_brush_render_data(
        self, shape: Shape
    ) -> QtGui.QPainterPath | None:
        """Build and cache the outline path for a mask.

        Args:
            shape: A shape currently rendered from its brush mask.

        Returns:
            A ``QPainterPath``, or ``None`` when the shape has no mask.
            Results are cached by mask version so repeated repaints between
            mask updates stay cheap.
        """
        if shape is None or getattr(shape, "mask", None) is None:
            return None
        version = int(getattr(shape, "_brush_mask_version", 0))
        cached = self._brush_overlay_cache.get(shape)
        if cached and cached[0] == version:
            return cached[1]

        mask = shape.mask
        if mask.dtype != np.uint8:
            mask = (mask > 0).astype(np.uint8) * 255
        if mask.ndim != 2:
            mask = mask.squeeze()

        outline_path = QtGui.QPainterPath()
        for poly in self._mask_to_polylines(mask):
            if len(poly) < 3:
                continue
            outline_path.moveTo(float(poly[0][0]), float(poly[0][1]))
            for x, y in poly[1:]:
                outline_path.lineTo(float(x), float(y))
            outline_path.closeSubpath()

        self._brush_overlay_cache[shape] = (version, outline_path)
        return outline_path

    def _restore_brush_original_geometry(self, shape: Shape) -> None:
        """Restore geometry captured when brush editing started."""
        original = self._brush_original_shape
        if shape is None or original is None:
            return
        shape.shape_type = original.shape_type
        shape.points = [QtCore.QPointF(point) for point in original.points]
        shape.direction = original.direction
        shape.center = original.center
        shape.other_data = copy.deepcopy(original.other_data)

    def _leave_brush_mode(self, cancel: bool) -> None:
        """Leave brush mode by committing or discarding mask changes."""
        target = self._brush_target_shape
        self.is_brush_mode = False
        self.override_cursor(CURSOR_DEFAULT)
        self._prev_brush_pos = None
        self._brush_target_shape = None
        self.eraser_mode = False

        if target is not None and getattr(target, "mask", None) is not None:
            if self._brush_baseline_mask is not None and np.array_equal(
                target.mask, self._brush_baseline_mask
            ):
                self._brush_modified = False
            has_geometry = True
            if cancel or not self._brush_modified:
                self._restore_brush_original_geometry(target)
            else:
                has_geometry = self._update_shape_points_from_mask(target)
            target._brush_using_mask = False
            target.mask = None
            self._invalidate_brush_cache(target)
            if self._brush_modified and not cancel:
                if not has_geometry and target in self.shapes:
                    self.shapes.remove(target)
                    self.selected_shapes = [
                        shape
                        for shape in self.selected_shapes
                        if shape is not target
                    ]
                    target.selected = False
                self.store_shapes()
                if has_geometry:
                    self.shape_moved.emit()
                else:
                    self.shapes_deleted.emit([target])

        self._brush_modified = False
        self._brush_undo_stack = []
        self._brush_redo_stack = []
        self._brush_baseline_mask = None
        self._brush_original_shape = None
        self._brush_stroke_dirty = False
        self.brush_mode_changed.emit(False)
        self.brush_history_changed.emit(self.is_shape_restorable)
        self.update()

    def cancel_brush_mode(self) -> None:
        """Discard brush changes and restore the original polygon."""
        if self.is_brush_mode:
            self._leave_brush_mode(cancel=True)
        else:
            self.brush_mode_changed.emit(False)

    def set_brush_mode(self, enabled: bool) -> None:
        """Enter or leave brush-edit mode for the selected shape.

        On enter the single selected shape (brush editing requires exactly
        one) is converted to a mask, a blank cursor is shown so the preview
        circle reads as the brush, and an undo baseline is captured. On
        exit the mask is converted back into a simplified polygon, the
        shape is stored/saved when modified, and brush state is cleared.

        Args:
            enabled: ``True`` to enter brush mode, ``False`` to leave it.
        """
        if enabled:
            if (
                len(self.selected_shapes) != 1
                or self.selected_shapes[0].shape_type != "polygon"
                or self.selected_shapes[0].locked
            ):
                self.brush_mode_changed.emit(False)
                return
            self.set_editing(True)
            self.is_brush_mode = True
            self._brush_modified = False
            self.override_cursor(QtCore.Qt.CursorShape.BlankCursor)
            self._brush_target_shape = (
                self.selected_shapes[0]
                if len(self.selected_shapes) == 1
                else None
            )
            self._brush_original_shape = (
                self._brush_target_shape.copy()
                if self._brush_target_shape is not None
                else None
            )
            self._prev_brush_pos = None
            if self._brush_target_shape is not None:
                self._ensure_brush_mask(self._brush_target_shape)
                self._invalidate_brush_cache(self._brush_target_shape)
                mask = getattr(self._brush_target_shape, "mask", None)
                if mask is not None:
                    self._brush_baseline_mask = mask.copy()
                    self._brush_undo_stack = [self._brush_baseline_mask.copy()]
                    self._brush_redo_stack = []
                else:
                    self._brush_baseline_mask = None
                    self._brush_undo_stack = []
                    self._brush_redo_stack = []
            else:
                self._brush_baseline_mask = None
                self._brush_undo_stack = []
                self._brush_redo_stack = []
            self.brush_mode_changed.emit(True)
            self.brush_history_changed.emit(False)
            self.update()
            return

        self._leave_brush_mode(cancel=False)

    def _push_brush_undo_state(self) -> None:
        """Snapshot the current mask onto the brush undo stack.

        Called once per completed stroke. Consecutive duplicate states are
        skipped, the redo stack is cleared, and the stack is trimmed to
        ``_brush_max_undo_steps`` while preserving the baseline at index 0.
        """
        shape = self._brush_target_shape
        if shape is None or getattr(shape, "mask", None) is None:
            return
        mask = shape.mask
        if not self._brush_undo_stack:
            self._brush_undo_stack = [mask.copy()]
            self._brush_redo_stack = []
            return
        last = self._brush_undo_stack[-1]
        if last.shape == mask.shape and np.array_equal(last, mask):
            return
        self._brush_undo_stack.append(mask.copy())
        self._brush_redo_stack.clear()
        while len(self._brush_undo_stack) > self._brush_max_undo_steps + 1:
            del self._brush_undo_stack[1]
        while (
            len(self._brush_undo_stack) > 2
            and sum(state.nbytes for state in self._brush_undo_stack)
            > self._brush_max_undo_bytes
        ):
            del self._brush_undo_stack[1]
        self.brush_history_changed.emit(self.brush_can_undo())

    def brush_can_undo(self) -> bool:
        """Return whether a brush stroke is available to undo."""
        return self.is_brush_mode and len(self._brush_undo_stack) > 1

    def brush_can_redo(self) -> bool:
        """Return whether a brush stroke is available to redo."""
        return self.is_brush_mode and len(self._brush_redo_stack) > 0

    def _restore_brush_mask(self, mask: np.ndarray) -> None:
        """Apply a mask snapshot to the target shape and refresh it.

        Args:
            mask: The mask snapshot to restore onto the target shape.
        """
        shape = self._brush_target_shape
        shape.mask = mask.copy()
        self._bump_brush_version(shape)
        self._update_shape_points_from_mask(shape)
        if self._brush_baseline_mask is not None:
            self._brush_modified = not np.array_equal(
                shape.mask, self._brush_baseline_mask
            )
        self.update()

    def brush_undo(self) -> None:
        """Revert the target shape's mask to the previous stroke."""
        if not self.brush_can_undo():
            return
        shape = self._brush_target_shape
        if shape is None or getattr(shape, "mask", None) is None:
            return
        current = self._brush_undo_stack.pop()
        self._brush_redo_stack.append(current)
        self._restore_brush_mask(self._brush_undo_stack[-1])
        self.brush_history_changed.emit(self.brush_can_undo())

    def brush_redo(self) -> None:
        """Re-apply the next stroke on the brush redo stack."""
        if not self.brush_can_redo():
            return
        shape = self._brush_target_shape
        if shape is None or getattr(shape, "mask", None) is None:
            return
        nxt = self._brush_redo_stack.pop()
        self._brush_undo_stack.append(nxt.copy())
        self._restore_brush_mask(nxt)
        self.brush_history_changed.emit(self.brush_can_undo())

    def _brush_mouse_press(self, ev, pos: QtCore.QPointF) -> bool:
        """Handle a mouse press while brush mode is active.

        A left press stamps the brush at ``pos`` (erasing while Ctrl is
        held); a right press is consumed so its release can leave brush
        mode without opening the context menu.

        Args:
            ev: The Qt mouse event.
            pos: Cursor position in image coordinates.

        Returns:
            ``True`` if the event was consumed by brush mode.
        """
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            return True
        if (
            ev.button() == QtCore.Qt.MouseButton.LeftButton
            and self.editing()
            and self._brush_target_shape is not None
        ):
            self._ensure_brush_mask(self._brush_target_shape)
            self.eraser_mode = bool(
                ev.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier
            )
            self._apply_brush_to_mask(
                self._brush_target_shape.mask,
                pos.x(),
                pos.y(),
                radius=max(1, int(round(self.brush_radius))),
                add=not self.eraser_mode,
            )
            self._prev_brush_pos = QtCore.QPointF(pos)
            self._brush_stroke_dirty = True
            self._brush_modified = True
            self._bump_brush_version(self._brush_target_shape)
            self.update()
            return True
        return False

    def _brush_mouse_move(self, ev, pos: QtCore.QPointF) -> bool:
        """Handle mouse movement while brush mode is active.

        With the left button held, brush stamps are interpolated between
        the previous and current positions so fast drags leave no gaps.
        Otherwise the canvas just repaints to refresh the preview circle.

        Args:
            ev: The Qt mouse event.
            pos: Cursor position in image coordinates.

        Returns:
            ``True`` (brush mode always consumes movement events).
        """
        self.prev_move_point = pos
        self.eraser_mode = bool(
            ev.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier
        )
        target = self._brush_target_shape
        if (
            QtCore.Qt.MouseButton.LeftButton & ev.buttons()
        ) and target is not None:
            self._ensure_brush_mask(target)
            add = not self.eraser_mode
            radius = max(1, int(round(self.brush_radius)))
            prev = self._prev_brush_pos
            if prev is None:
                self._apply_brush_to_mask(
                    target.mask, pos.x(), pos.y(), radius=radius, add=add
                )
            else:
                dx = pos.x() - prev.x()
                dy = pos.y() - prev.y()
                dist = float((dx * dx + dy * dy) ** 0.5)
                step = max(1.0, radius * 0.5)
                steps = int(dist // step) if dist > 0 else 0
                for i in range(steps + 1):
                    t = (i / steps) if steps > 0 else 1.0
                    x = prev.x() * (1 - t) + pos.x() * t
                    y = prev.y() * (1 - t) + pos.y() * t
                    self._apply_brush_to_mask(
                        target.mask, x, y, radius=radius, add=add
                    )
            self._prev_brush_pos = QtCore.QPointF(pos)
            self._brush_stroke_dirty = True
            self._brush_modified = True
            self._bump_brush_version(target)
        self.update()
        return True

    def _brush_mouse_release(self, ev) -> bool:
        """Finish a brush stroke or exit brush mode on mouse release.

        A right release leaves brush mode; a left release converts the
        mask to polygon points and snapshots an undo step.

        Args:
            ev: The Qt mouse event.

        Returns:
            ``True`` if the event was consumed by brush mode.
        """
        if ev.button() == QtCore.Qt.MouseButton.RightButton:
            self.set_brush_mode(False)
            return True
        if (
            ev.button() == QtCore.Qt.MouseButton.LeftButton
            and self._brush_target_shape is not None
            and getattr(self._brush_target_shape, "mask", None) is not None
        ):
            self._update_shape_points_from_mask(self._brush_target_shape)
            if self._brush_stroke_dirty:
                self._push_brush_undo_state()
            self._brush_stroke_dirty = False
            self._prev_brush_pos = None
            self.update()
            return True
        return False

    def _brush_key_press(self, ev) -> bool:
        """Handle brush-specific undo/redo shortcuts.

        ``Ctrl+Z`` undoes a stroke; ``Ctrl+Shift+Z`` and ``Ctrl+Y`` redo.

        Args:
            ev: The Qt key event.

        Returns:
            ``True`` if the shortcut was consumed by brush mode.
        """
        modifiers = ev.modifiers()
        key = ev.key()
        if key == QtCore.Qt.Key.Key_Escape:
            self.cancel_brush_mode()
            ev.accept()
            return True
        ctrl = bool(modifiers & QtCore.Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier)
        if ctrl and key == QtCore.Qt.Key.Key_Z:
            if shift:
                self.brush_redo()
            else:
                self.brush_undo()
            ev.accept()
            return True
        if ctrl and key == QtCore.Qt.Key.Key_Y:
            self.brush_redo()
            ev.accept()
            return True
        return False

    def _brush_drawing_can_close(self, pos: QtCore.QPointF) -> bool:
        """Return whether a freehand polygon stroke reaches its start."""
        if self.current is None or len(self.current) < 3:
            return False
        start = self.current[0]
        threshold = self.epsilon / self.scale
        return self.close_enough(pos, start) or (
            utils.distance_to_line(start, [self.current[-1], pos]) < threshold
        )

    def _paint_brush_overlays(self, p: QtGui.QPainter) -> None:
        """Paint live mask overlays for shapes being brush-edited.

        Args:
            p: The active painter, already translated/scaled to image space.
        """
        for shape in self.shapes:
            if not getattr(shape, "_brush_using_mask", False):
                continue
            if getattr(shape, "mask", None) is None or not shape.visible:
                continue
            outline_path = self._get_brush_render_data(shape)
            if outline_path is not None:
                outline_color = (
                    shape.select_line_color
                    if shape.selected
                    else shape.line_color
                )
                pen = QtGui.QPen(outline_color)
                pen.setWidth(
                    max(1, int(round(shape.line_width / Shape.scale)))
                )
                if getattr(shape, "difficult", False):
                    pen.setStyle(Qt.PenStyle.DashLine)
                p.setPen(pen)
                fill_color = QtGui.QColor(outline_color)
                fill_color.setAlpha(int(self.mask_opacity))
                p.setBrush(fill_color)
                p.drawPath(outline_path)

    def _paint_brush_cursor(self, p: QtGui.QPainter) -> None:
        """Draw the circular brush-size preview at the cursor.

        The circle is white while adding and red while erasing so the
        active modifier is obvious at a glance.

        Args:
            p: The active painter, already translated/scaled to image space.
        """
        if not self.is_brush_mode:
            return
        r = max(1.0, float(self.brush_radius))
        p.setOpacity(1.0)
        if self.eraser_mode:
            pen_color = QtGui.QColor(255, 100, 100, 255)
            fill_color = QtGui.QColor(255, 100, 100, 50)
        else:
            pen_color = QtGui.QColor(255, 255, 255, 255)
            fill_color = QtGui.QColor(255, 255, 255, 50)
        p.setPen(QtGui.QPen(pen_color, 2))
        p.setBrush(fill_color)
        p.drawEllipse(QtCore.QPointF(self.prev_move_point), r, r)
