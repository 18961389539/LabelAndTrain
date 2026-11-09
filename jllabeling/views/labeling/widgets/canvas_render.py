"""Render state and paint methods for the labeling canvas.

The canvas used to keep every show/color/loading flag in ``Canvas.__init__``
and all ``_paint_*`` methods in the same class. This module owns that state
(``CanvasRenderState``) and the methods that read it (``CanvasRenderMixin``).
``Canvas`` inherits the mixin, so callers keep using ``canvas.show_labels``,
``canvas.render_visualization(...)`` and the private paint helpers exactly as
before.
"""

import copy
import math

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt

from jllabeling.views.labeling.utils.colormap import label_colormap
from jllabeling.views.labeling.utils.theme import get_theme

from ..shape import Shape
from . import canvas_overlays

LABEL_COLORMAP = label_colormap()


def smooth_pixmap_transform_enabled(pixelated_zoom, scale):
    """Whether QPainter's smooth pixmap hint should stay on.

    Nearest-neighbour sampling only makes sense once one image pixel maps to
    at least one screen pixel. Below 100% Qt's smooth path does area
    averaging; switching it off there point-samples the image and produces
    severe aliasing on large industrial images.
    """
    return (not pixelated_zoom) or scale < 1.0


def pixel_view_config(canvas):
    """Return ``(pixelated_zoom, pixel_grid_threshold)`` for ``canvas``.

    The settings live in the owning widget's config. Reading them here keeps
    the two size-budgeted god objects (label_widget.py and canvas.py) free of
    a display-only feature, and a freshly created scratch canvas in
    render_visualization sees the same policy as the visible one. Explicit
    canvas attributes win so the runtime applier can change the view live.
    """
    parent = getattr(canvas, "parent", None)
    widget_config = getattr(parent, "_config", {}) or {}
    canvas_config = widget_config.get("canvas", {}) or {}
    pixelated = getattr(
        canvas, "pixelated_zoom", canvas_config.get("pixelated_zoom", True)
    )
    threshold = getattr(
        canvas,
        "pixel_grid_threshold",
        canvas_config.get("pixel_grid_threshold", 8.0),
    )
    return bool(pixelated), float(threshold or 0.0)


class _RenderField:
    """Delegate one render flag to ``CanvasRenderState``.

    Keeping the historical names as descriptors means the paint methods and
    external callers (actions, settings, tests) do not have to learn a new
    path such as ``canvas.render_state.show_labels``.
    """

    def __init__(self, name):
        self.name = name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        return getattr(obj.render_state, self.name)

    def __set__(self, obj, value):
        setattr(obj.render_state, self.name, value)


class CanvasRenderState:
    """Values used only by painting."""

    def __init__(self, attributes_config, mask_config, loading_text):
        self.show_groups = False
        self.show_masks = True
        self.show_texts = True
        self.show_labels = True
        self.show_scores = True
        self.show_degrees = False
        self.show_attributes = True

        self.cross_line_show = True
        self.cross_line_width = 2.0
        self.cross_line_color = "#00FF00"
        self.cross_line_opacity = 0.5

        self.attr_background_color = attributes_config.get(
            "background_color", [33, 33, 33, 255]
        )
        self.attr_border_color = attributes_config.get(
            "border_color", [66, 66, 66, 255]
        )
        self.attr_text_color = attributes_config.get(
            "text_color", [33, 150, 243, 255]
        )

        self.mask_opacity = mask_config.get("opacity", 102)
        self.shape_opacity = 1.0

        self.is_loading = False
        self.loading_text = loading_text
        self.loading_angle = 0

        self.compare_pixmap = None
        self.split_position = 0.5


class CanvasRenderMixin:
    """Paint methods for ``Canvas``; state lives in ``CanvasRenderState``."""

    show_groups = _RenderField("show_groups")
    show_masks = _RenderField("show_masks")
    show_texts = _RenderField("show_texts")
    show_labels = _RenderField("show_labels")
    show_scores = _RenderField("show_scores")
    show_degrees = _RenderField("show_degrees")
    show_attributes = _RenderField("show_attributes")

    cross_line_show = _RenderField("cross_line_show")
    cross_line_width = _RenderField("cross_line_width")
    cross_line_color = _RenderField("cross_line_color")
    cross_line_opacity = _RenderField("cross_line_opacity")

    attr_background_color = _RenderField("attr_background_color")
    attr_border_color = _RenderField("attr_border_color")
    attr_text_color = _RenderField("attr_text_color")

    mask_opacity = _RenderField("mask_opacity")
    shape_opacity = _RenderField("shape_opacity")

    is_loading = _RenderField("is_loading")
    loading_text = _RenderField("loading_text")
    loading_angle = _RenderField("loading_angle")

    compare_pixmap = _RenderField("compare_pixmap")
    split_position = _RenderField("split_position")

    def _paint_groups(self, painter):
        if not self.show_groups:
            return

        painter.save()
        theme = get_theme()
        active_shapes = self._active_group_shapes()
        for group_id, group_shapes in self._grouped_shapes().items():
            visible_shapes = [shape for shape in group_shapes if shape.visible]
            if not visible_shapes:
                continue
            group_rect = self._group_rect(visible_shapes)
            group_color = QtGui.QColor(
                *LABEL_COLORMAP[int(group_id) % len(LABEL_COLORMAP)]
            )
            selected = bool(
                active_shapes and group_id == self._selected_group_id
            )
            hovered = group_id == self._hovered_group_id

            for shape in visible_shapes:
                rect = shape.bounding_rect()
                center = rect.center()
                radius = max(1.0, 3.0 / self.scale)
                triangle = [
                    QtCore.QPointF(center.x(), center.y() - radius),
                    QtCore.QPointF(center.x() - radius, center.y() + radius),
                    QtCore.QPointF(center.x() + radius, center.y() + radius),
                ]
                painter.setPen(
                    QtGui.QPen(
                        group_color,
                        max(1.0, 4.0 / self.scale),
                        Qt.PenStyle.SolidLine,
                    )
                )
                painter.drawPolygon(triangle)

            if selected or hovered:
                color = QtGui.QColor(
                    theme["selection" if selected else "primary_hover"]
                )
                glow = QtGui.QColor(color)
                glow.setAlpha(80 if selected else 50)
                painter.setPen(
                    QtGui.QPen(
                        glow,
                        (6.0 if selected else 4.0) / self.scale,
                        Qt.PenStyle.SolidLine,
                    )
                )
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(group_rect)
                width = (2.5 if selected else 2.0) / self.scale
                style = Qt.PenStyle.SolidLine
            else:
                color = QtGui.QColor("#EEEEEE")
                width = 1.0 / self.scale
                style = Qt.PenStyle.DashLine

            painter.setPen(QtGui.QPen(color, width, style))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(group_rect)

            label_rect = self._group_label_rect(
                group_id, len(group_shapes), group_rect
            )
            label_color = color if selected or hovered else group_color
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(label_color)
            painter.drawRoundedRect(
                label_rect, 3.0 / self.scale, 3.0 / self.scale
            )
            painter.setFont(self._group_label_font())
            painter.setPen(QtGui.QColor(theme["selection_text"]))
            painter.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignCenter,
                self._group_label(group_id, len(group_shapes)),
            )
        painter.restore()

    # QT Overload
    def paintEvent(self, event):  # noqa: C901
        """Paint event for canvas"""
        if (
            self.pixmap is None
            or self.pixmap.width() == 0
            or self.pixmap.height() == 0
        ):
            super().paintEvent(event)
            self._paint_empty_state()
            return

        self._paint_content()

    def _paint_empty_state(self):
        """Fill the canvas while the overlay CTA is shown on the viewport."""
        t = get_theme()
        p = self._painter
        p.begin(self)
        p.fillRect(self.rect(), QtGui.QColor(t["background"]))
        p.end()

    def _paint_content(self):
        """Paint the loaded pixmap and all annotations."""
        p = self._painter
        p.begin(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        # At 100% zoom and above use nearest-neighbour sampling so individual
        # pixels stay hard-edged for pixel-level inspection. Below 100% keep
        # Qt's smooth path: without it a downscaled industrial image is
        # point-sampled and shows severe aliasing instead of area averaging.
        pixelated, _ = pixel_view_config(self)
        p.setRenderHint(
            QtGui.QPainter.RenderHint.SmoothPixmapTransform,
            smooth_pixmap_transform_enabled(pixelated, self.scale),
        )

        p.scale(self.scale, self.scale)
        p.translate(self.offset_to_center())

        p.drawPixmap(0, 0, self.pixmap)

        self._paint_compare_view(p)
        self._paint_pixel_grid(p)
        Shape.scale = self.scale

        self._paint_loading(p)

        # Apply the global label/shape opacity to every annotation drawn
        # below (masks, shapes, degrees, groups, brush overlays). Image text
        # labels are restored to full opacity before being painted.
        p.setOpacity(self.shape_opacity)

        self._paint_masks(p)

        self._paint_degrees(p)

        self._paint_current_shapes(p)

        self._paint_texts(p)

        self._paint_labels(p)

        self._paint_cross_coordinates(p)

        self._paint_attributes(p)

        self._paint_compare_split_line(p)

        self._paint_brush_cursor(p)

        p.end()

    def _paint_compare_view(self, p):
        # Draw compare view: left side shows compare image, right side shows original
        # split_position: 0 = all original, 1 = all compare
        if (
            self.compare_pixmap is not None
            and not self.compare_pixmap.isNull()
        ):
            split_x = int(self.split_position * self.pixmap.width())
            if split_x > 0:
                p.drawPixmap(
                    0,
                    0,
                    self.compare_pixmap,
                    0,
                    0,
                    split_x,
                    self.pixmap.height(),
                )

        Shape.scale = self.scale

    def _paint_pixel_grid(self, p):
        """Overlay one-screen-pixel grid lines at very high zoom.

        Only the clipped region is iterated. A 10k x 10k inspection image
        has twenty thousand grid lines; drawing all of them on every repaint
        would stall scrolling. ``clipBoundingRect`` is in logical (image)
        coordinates, so it can be used directly after ``p.scale``.
        """
        _, threshold = pixel_view_config(self)
        if threshold <= 0 or self.scale < threshold:
            return
        if self.pixmap is None or self.pixmap.isNull():
            return

        width, height = self.pixmap.width(), self.pixmap.height()
        clip = p.clipBoundingRect()
        if not clip.isValid() or clip.isEmpty():
            clip = QtCore.QRectF(0, 0, width, height)
        x0 = max(0, int(math.floor(clip.left())) - 1)
        x1 = min(width, int(math.ceil(clip.right())) + 1)
        y0 = max(0, int(math.floor(clip.top())) - 1)
        y1 = min(height, int(math.ceil(clip.bottom())) + 1)
        if x1 <= x0 or y1 <= y0:
            return
        # Hard ceiling so a hand-edited threshold cannot freeze repaints.
        if (x1 - x0) + (y1 - y0) > 4000:
            return

        p.save()
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        pen = QtGui.QPen(QtGui.QColor(128, 128, 128, 110))
        pen.setWidthF(1.0 / max(self.scale, 1e-6))
        p.setPen(pen)
        for x in range(x0, x1 + 1):
            p.drawLine(QtCore.QLineF(x, y0, x, y1))
        for y in range(y0, y1 + 1):
            p.drawLine(QtCore.QLineF(x0, y, x1, y))
        p.restore()
        # Vector annotations below rely on antialiasing; make sure the grid
        # did not leave it switched off even if save/restore differs by engine.
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

    def _paint_loading(self, p):
        # Draw loading/waiting screen
        if self.is_loading:
            # Draw a semi-transparent rectangle
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QColor(0, 0, 0, 20))
            p.drawRect(self.pixmap.rect())

            # Draw a spinning wheel
            p.setPen(QtGui.QColor(255, 255, 255))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.save()
            p.translate(self.pixmap.width() / 2, self.pixmap.height() / 2 - 50)
            p.rotate(self.loading_angle)
            p.drawEllipse(-20, -20, 40, 40)
            p.drawLine(0, 0, 0, -20)
            p.restore()
            self.loading_angle += 30
            if self.loading_angle >= 360:
                self.loading_angle = 0

            # Draw the loading text
            p.setPen(QtGui.QColor(255, 255, 255))
            p.setFont(QtGui.QFont("Arial", 20))
            p.drawText(
                self.pixmap.rect(),
                Qt.AlignmentFlag.AlignCenter,
                self.loading_text,
            )
            p.end()
            self.update()
            return

    def _paint_masks(self, p):  # noqa: C901
        # Draw shape masks
        if self.show_masks:
            for shape in self.shapes:
                if not shape.visible:
                    continue
                # Shapes under live brush editing render their own overlay.
                if getattr(shape, "_brush_using_mask", False):
                    continue
                if shape.shape_type not in [
                    "polygon",
                    "rectangle",
                    "rotation",
                    "quadrilateral",
                    "circle",
                ]:
                    continue
                if shape.shape_type == "polygon" and len(shape.points) < 3:
                    continue
                if shape.shape_type == "rectangle" and len(shape.points) < 2:
                    continue
                if shape.shape_type == "rotation" and len(shape.points) < 2:
                    continue
                if (
                    shape.shape_type == "quadrilateral"
                    and len(shape.points) < 4
                ):
                    continue
                if shape.shape_type == "circle" and len(shape.points) < 2:
                    continue
                if not self.is_visible(shape):
                    continue

                mask_path = QtGui.QPainterPath()
                if shape.shape_type == "polygon":
                    mask_path.moveTo(shape.points[0])
                    for point in shape.points[1:]:
                        mask_path.lineTo(point)
                    if shape.is_closed() or len(shape.points) >= 3:
                        mask_path.closeSubpath()
                elif shape.shape_type == "rectangle":
                    if len(shape.points) == 2:
                        rectangle = shape.get_rect_from_line(*shape.points)
                        mask_path.addRect(rectangle)
                    elif len(shape.points) == 4:
                        mask_path.moveTo(shape.points[0])
                        for point in shape.points[1:]:
                            mask_path.lineTo(point)
                        mask_path.closeSubpath()
                elif shape.shape_type == "rotation":
                    if len(shape.points) == 2:
                        rectangle = shape.get_rect_from_line(*shape.points)
                        mask_path.addRect(rectangle)
                    elif len(shape.points) == 4:
                        mask_path.moveTo(shape.points[0])
                        for point in shape.points[1:]:
                            mask_path.lineTo(point)
                        mask_path.closeSubpath()
                elif shape.shape_type == "quadrilateral":
                    if len(shape.points) == 4:
                        mask_path.moveTo(shape.points[0])
                        for point in shape.points[1:]:
                            mask_path.lineTo(point)
                        mask_path.closeSubpath()
                elif shape.shape_type == "circle":
                    if len(shape.points) == 2:
                        rectangle = shape.get_circle_rect_from_line(
                            shape.points
                        )
                        mask_path.addEllipse(rectangle)

                fill_color = (
                    shape.select_line_color
                    if shape.selected
                    else shape.line_color
                )
                fill_color_alpha = QtGui.QColor(
                    fill_color.red(),
                    fill_color.green(),
                    fill_color.blue(),
                    self.mask_opacity,
                )
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(fill_color_alpha)
                p.drawPath(mask_path)

                outline_color = (
                    shape.select_line_color
                    if shape.selected
                    else shape.line_color
                )
                pen = QtGui.QPen(outline_color)
                pen.setWidth(
                    max(1, int(round(shape.line_width / Shape.scale)))
                )
                if shape.difficult:
                    pen.setStyle(Qt.PenStyle.DashLine)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(mask_path)

    def _paint_degrees(self, p):
        # Draw degrees
        for shape in self.shapes:
            if self.is_visible(shape):
                shape.hovered = shape == self.h_shape
                shape.fill = (
                    self._fill_drawing
                    and (shape.selected or shape == self.h_shape)
                    and not (self.selected_vertex() and self.moving_shape)
                )
                # Brush-edited shapes are drawn from their mask instead.
                if not getattr(shape, "_brush_using_mask", False):
                    shape.paint(p)

            if (
                shape.shape_type == "rotation"
                and len(shape.points) == 4
                and self.is_visible(shape)
            ):
                d = shape.point_size / shape.scale
                center = QtCore.QPointF(
                    (shape.points[0].x() + shape.points[2].x()) / 2,
                    (shape.points[0].y() + shape.points[2].y()) / 2,
                )
                if self.show_degrees:
                    degrees = math.degrees(shape.direction)
                    if abs(degrees - 360.0) < 0.1:
                        degrees = 0.0
                    degrees = f"{degrees:.2f}°"
                    p.setFont(
                        QtGui.QFont(
                            "Arial",
                            int(max(6.0, int(round(8.0 / Shape.scale)))),
                        )
                    )
                    pen = QtGui.QPen(
                        QtGui.QColor("#FF9900"),
                        8,
                        QtCore.Qt.PenStyle.SolidLine,
                    )
                    p.setPen(pen)
                    fm = QtGui.QFontMetrics(p.font())
                    rect = fm.boundingRect(degrees)
                    p.fillRect(
                        int(rect.x() + center.x() - d),
                        int(rect.y() + center.y() + d),
                        int(rect.width()),
                        int(rect.height()),
                        QtGui.QColor("#FF9900"),
                    )
                    pen = QtGui.QPen(
                        QtGui.QColor("#FFFFFF"),
                        7,
                        QtCore.Qt.PenStyle.SolidLine,
                    )
                    p.setPen(pen)
                    p.drawText(
                        int(center.x() - d),
                        int(center.y() + d),
                        degrees,
                    )
                else:
                    cp = QtGui.QPainterPath()
                    cp.addRect(
                        int(center.x() - d / 2),
                        int(center.y() - d / 2),
                        int(d),
                        int(d),
                    )
                    p.drawPath(cp)
                    p.fillPath(cp, QtGui.QColor(255, 153, 0, 255))

        self._paint_rotation_handles(p)

        self._paint_groups(p)

    def _paint_current_shapes(self, p):
        # Draw live brush-edit overlays on top of the regular shapes.
        self._paint_brush_overlays(p)

        if self.current:
            self.current.paint(p)
            self.line.paint(p)

            if (
                self.create_mode == "quadrilateral"
                and len(self.current.points) == 3
                and len(self.line.points) >= 2
            ):
                color = (
                    self.current.select_line_color
                    if self.current.selected
                    else self.current.line_color
                )
                pen = QtGui.QPen(color)
                pen.setWidth(
                    max(1, int(round(self.current.line_width / Shape.scale)))
                )
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawLine(QtCore.QLineF(self.line[1], self.current.points[0]))
        if self.selected_shapes_copy:
            for s in self.selected_shapes_copy:
                s.paint(p)

        if (
            self.fill_drawing()
            and self.create_mode == "polygon"
            and self.current is not None
            and len(self.current.points) >= 2
        ):
            drawing_shape = copy.copy(self.current)
            drawing_shape.points = self.current.points + [self.line[1]]
            drawing_shape.fill = True
            drawing_shape.paint(p)
        if (
            self.fill_drawing()
            and self.create_mode == "quadrilateral"
            and self.current is not None
            and len(self.current.points) == 3
            and len(self.line.points) >= 2
        ):
            drawing_shape = copy.copy(self.current)
            drawing_shape.points = list(self.current.points) + [
                QtCore.QPointF(self.line[1].x(), self.line[1].y())
            ]
            drawing_shape.fill = True
            drawing_shape._closed = True
            drawing_shape.paint(p)

        # Restore full opacity so labels/scores/attributes stay readable.
        p.setOpacity(1.0)

        # Draw texts

    def _paint_texts(self, p):
        canvas_overlays.paint_texts(self, p)

    def _paint_labels(self, p):
        canvas_overlays.paint_labels(self, p)

    def _paint_cross_coordinates(self, p):
        canvas_overlays.paint_cross_coordinates(self, p)

    def _paint_attributes(self, p):  # noqa: C901
        canvas_overlays.paint_attributes(self, p)

    def _paint_compare_split_line(self, p):
        # Draw compare view split line
        if (
            self.compare_pixmap is not None
            and not self.compare_pixmap.isNull()
        ):
            split_x = int(self.split_position * self.pixmap.width())
            img_h = self.pixmap.height()
            if 0 < split_x < self.pixmap.width():
                p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                line_pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 180), 1.5)
                line_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(line_pen)
                p.drawLine(split_x, 0, split_x, img_h)
                handle_radius = 16
                handle_y = img_h // 2
                gradient = QtGui.QRadialGradient(
                    split_x, handle_y, handle_radius
                )
                gradient.setColorAt(0, QtGui.QColor(255, 255, 255, 200))
                gradient.setColorAt(1, QtGui.QColor(255, 255, 255, 0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(gradient)
                p.drawEllipse(
                    split_x - handle_radius,
                    handle_y - handle_radius,
                    handle_radius * 2,
                    handle_radius * 2,
                )
                p.setBrush(QtGui.QColor(255, 255, 255, 200))
                p.drawEllipse(split_x - 8, handle_y - 8, 16, 16)
                arrow_pen = QtGui.QPen(QtGui.QColor(100, 100, 100, 180), 1.5)
                arrow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                arrow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                p.setPen(arrow_pen)
                arrow_size = 4
                p.drawLine(
                    split_x - arrow_size, handle_y, split_x - 1, handle_y
                )
                p.drawLine(
                    split_x - arrow_size,
                    handle_y,
                    split_x - arrow_size + 2,
                    handle_y - 2,
                )
                p.drawLine(
                    split_x - arrow_size,
                    handle_y,
                    split_x - arrow_size + 2,
                    handle_y + 2,
                )
                p.drawLine(
                    split_x + 1, handle_y, split_x + arrow_size, handle_y
                )
                p.drawLine(
                    split_x + arrow_size,
                    handle_y,
                    split_x + arrow_size - 2,
                    handle_y - 2,
                )
                p.drawLine(
                    split_x + arrow_size,
                    handle_y,
                    split_x + arrow_size - 2,
                    handle_y + 2,
                )
                p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)

        # Brush-size preview circle follows the cursor in brush mode.

    def render_visualization(
        self,
        pixmap,
        shapes,
        show_labels=True,
        show_scores=True,
        show_groups=False,
        show_texts=True,
        show_masks=True,
    ):
        old_shape_scale = Shape.scale
        scratch = type(self)(parent=self.parent)
        scratch.resize(pixmap.size())
        scratch.pixmap = pixmap
        scratch.shapes = list(shapes)
        scratch.scale = 1.0
        # Keep the exported snapshot on the same sampling policy as the
        # on-screen canvas, but never burn the grid overlay into an image.
        scratch.pixelated_zoom = pixel_view_config(self)[0]
        scratch.pixel_grid_threshold = 0.0
        scratch.current = None
        scratch.selected_shapes = []
        scratch.selected_shapes_copy = []
        scratch.h_shape = None
        scratch.h_vertex = None
        scratch.h_edge = None
        scratch.h_cuboid_face = None
        scratch.compare_pixmap = None
        scratch.cross_line_show = False
        scratch.show_labels = show_labels
        scratch.show_scores = show_scores
        scratch.show_groups = show_groups
        scratch.show_texts = show_texts
        scratch.show_masks = show_masks
        scratch.show_degrees = self.show_degrees
        scratch.show_attributes = self.show_attributes
        scratch.mask_opacity = self.mask_opacity
        scratch.shape_opacity = self.shape_opacity
        scratch.attr_background_color = self.attr_background_color
        scratch.attr_border_color = self.attr_border_color
        scratch.attr_text_color = self.attr_text_color
        scratch.visible = {shape: shape.visible for shape in scratch.shapes}

        image = QtGui.QImage(pixmap.size(), QtGui.QImage.Format.Format_ARGB32)
        image.fill(QtCore.Qt.GlobalColor.transparent)

        painter = QtGui.QPainter(image)
        try:
            scratch.render(painter)
        finally:
            painter.end()
            Shape.scale = old_shape_scale
            scratch.deleteLater()

        return image
