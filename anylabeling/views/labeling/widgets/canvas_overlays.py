"""Text and crosshair overlays drawn on top of the image.

Moved out of ``Canvas`` verbatim: these four read the canvas (shapes, the
show_* flags, the attribute colors) and draw; nothing here changes canvas
state, which is what makes the split safe. ``Canvas`` keeps the one-line
methods ``_paint_*`` that call these, so ``_paint_content`` and every
existing caller read the same as before.
"""

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt

from ..shape import Shape


def paint_texts(canvas, p):
    if canvas.show_texts:
        text_color = "#FFFFFF"
        background_color = "#007BFF"
        p.setFont(
            QtGui.QFont("Arial", int(max(6.0, int(round(8.0 / Shape.scale)))))
        )
        pen = QtGui.QPen(
            QtGui.QColor(background_color), 8, Qt.PenStyle.SolidLine
        )
        p.setPen(pen)
        for shape in canvas.shapes:
            if not shape.visible:
                continue
            description = shape.description
            if description:
                bbox = shape.bounding_rect()
                fm = QtGui.QFontMetrics(p.font())
                text_rect = fm.tightBoundingRect(description)

                padding_x = 4
                padding_y = 2
                rect_width = text_rect.width() + 2 * padding_x
                rect_height = fm.height() + 2 * padding_y

                bg_x = int(bbox.x())
                bg_y = int(bbox.y() - rect_height)

                p.fillRect(
                    bg_x,
                    bg_y,
                    rect_width,
                    rect_height,
                    QtGui.QColor(background_color),
                )

        pen = QtGui.QPen(QtGui.QColor(text_color), 8, Qt.PenStyle.SolidLine)
        p.setPen(pen)
        for shape in canvas.shapes:
            if not shape.visible:
                continue
            description = shape.description
            if description:
                bbox = shape.bounding_rect()
                fm = QtGui.QFontMetrics(p.font())

                padding_x = 4
                padding_y = 2

                text_x = int(bbox.x() + padding_x)
                text_y = int(bbox.y() - padding_y - fm.descent())

                p.drawText(
                    text_x,
                    text_y,
                    description,
                )


def paint_labels(canvas, p):
    # Draw labels
    if canvas.show_labels:
        label_transform = p.transform()
        p.save()
        p.resetTransform()
        p.setFont(QtGui.QFont("Arial", 8))
        labels = []
        for shape in canvas.shapes:
            if not shape.visible:
                continue
            if shape.label in [
                "AUTOLABEL_OBJECT",
                "AUTOLABEL_ADD",
                "AUTOLABEL_REMOVE",
            ]:
                continue
            label_text = (
                (f"id:{shape.group_id} " if shape.group_id is not None else "")
                + (f"{shape.label}")
                + (
                    f" {float(shape.score):.2f}"
                    if (shape.score is not None and canvas.show_scores)
                    else ""
                )
            )
            if not label_text:
                continue
            fm = QtGui.QFontMetrics(p.font())
            text_rect = fm.tightBoundingRect(label_text)
            padding_x = 4
            padding_y = 2
            rect_width = text_rect.width() + 2 * padding_x
            rect_height = fm.height() + 2 * padding_y

            if shape.shape_type in [
                "rectangle",
                "polygon",
                "rotation",
                "quadrilateral",
                "cuboid",
            ]:
                try:
                    bbox = shape.bounding_rect()
                except IndexError:
                    continue
                point = label_transform.map(bbox.topLeft())
                rect = QtCore.QRect(
                    int(point.x()),
                    int(point.y()),
                    rect_width,
                    rect_height,
                )
                text_pos = QtCore.QPoint(
                    int(point.x() + padding_x),
                    int(point.y() + rect_height - padding_y - fm.descent()),
                )
            elif shape.shape_type == "circle":
                points = shape.points
                if not points:
                    continue
                point = label_transform.map(points[0])
                rect = QtCore.QRect(
                    int(point.x() - rect_width / 2),
                    int(point.y() - rect_height / 2),
                    rect_width,
                    rect_height,
                )
                text_pos = QtCore.QPoint(
                    int(point.x() - rect_width / 2 + padding_x),
                    int(
                        point.y() + rect_height / 2 - padding_y - fm.descent()
                    ),
                )
            elif shape.shape_type in [
                "line",
                "linestrip",
                "point",
            ]:
                points = shape.points
                if not points:
                    continue
                point = label_transform.map(points[0])
                rect = QtCore.QRect(
                    int(point.x() + shape.point_size),
                    int(point.y() - 15),
                    rect_width,
                    rect_height,
                )
                text_pos = QtCore.QPoint(
                    int(point.x() + shape.point_size + padding_x),
                    int(
                        point.y() - 15 + rect_height - padding_y - fm.descent()
                    ),
                )
            else:
                continue
            labels.append((shape, rect, text_pos, label_text))

        pen = QtGui.QPen(QtGui.QColor("#FFA500"), 8, Qt.PenStyle.SolidLine)
        p.setPen(pen)
        for shape, rect, _, _ in labels:
            if not shape.visible:
                continue
            p.fillRect(rect, shape.line_color)

        pen = QtGui.QPen(QtGui.QColor("#000000"), 8, Qt.PenStyle.SolidLine)
        p.setPen(pen)
        for shape, _, text_pos, label_text in labels:
            if not shape.visible:
                continue
            p.drawText(text_pos, label_text)
        p.restore()


def paint_cross_coordinates(canvas, p):
    # Draw mouse coordinates
    if canvas.cross_line_show:
        pen = QtGui.QPen(
            QtGui.QColor(canvas.cross_line_color),
            max(1, int(round(canvas.cross_line_width / Shape.scale))),
            Qt.PenStyle.DashLine,
        )
        p.setPen(pen)
        p.setOpacity(canvas.cross_line_opacity)
        p.drawLine(
            QtCore.QPointF(canvas.prev_move_point.x(), 0),
            QtCore.QPointF(canvas.prev_move_point.x(), canvas.pixmap.height()),
        )
        p.drawLine(
            QtCore.QPointF(0, canvas.prev_move_point.y()),
            QtCore.QPointF(canvas.pixmap.width(), canvas.prev_move_point.y()),
        )


def paint_attributes(canvas, p):  # noqa: C901
    # Draw attributes
    if canvas.show_attributes:
        font_size = int(max(8.0, int(round(10.0 / Shape.scale))))
        font = QtGui.QFont("Arial", font_size, QtGui.QFont.Weight.Bold)
        p.setFont(font)
        attributes_list = []

        for shape in canvas.shapes:
            if not shape.visible:
                continue
            if not hasattr(shape, "attributes") or not shape.attributes:
                continue
            if shape.label in [
                "AUTOLABEL_OBJECT",
                "AUTOLABEL_ADD",
                "AUTOLABEL_REMOVE",
            ]:
                continue

            attrs_text = []
            for key, value in shape.attributes.items():
                attrs_text.append(f"{key}: {value}")
            if not attrs_text:
                continue

            max_attrs_per_line = 1
            attribute_lines = []
            for i in range(0, len(attrs_text), max_attrs_per_line):
                line_attrs = attrs_text[i : i + max_attrs_per_line]
                attribute_lines.append(" | ".join(line_attrs))

            fm = QtGui.QFontMetrics(font)
            max_width = 0
            line_heights = []
            for line in attribute_lines:
                line_rect = fm.tightBoundingRect(line)
                max_width = max(max_width, line_rect.width())
                line_heights.append(fm.height())
            total_height = sum(line_heights)

            padding_x = 8
            padding_y = 2
            rect_width = max_width + 2 * padding_x
            rect_height = total_height + 2 * padding_y
            d_react = shape.point_size / shape.scale

            if shape.shape_type in [
                "rectangle",
                "polygon",
                "rotation",
                "quadrilateral",
                "cuboid",
            ]:
                try:
                    bbox = shape.bounding_rect()
                except IndexError:
                    continue

                rect = QtCore.QRect(
                    int(bbox.x()),
                    int(bbox.y() + bbox.height() + 1),
                    rect_width,
                    rect_height,
                )

                text_positions = []
                y_offset = 0
                for line_height in line_heights:
                    text_pos = QtCore.QPoint(
                        int(bbox.x() + padding_x),
                        int(
                            bbox.y()
                            + bbox.height()
                            + 1
                            + padding_y
                            + y_offset
                            + fm.ascent()
                        ),
                    )
                    text_positions.append(text_pos)
                    y_offset += line_height

            elif shape.shape_type in [
                "circle",
                "line",
                "linestrip",
                "point",
            ]:
                points = shape.points
                if not points:
                    continue
                point = points[0]

                rect = QtCore.QRect(
                    int(point.x() + d_react),
                    int(point.y() + 1),
                    rect_width,
                    rect_height,
                )

                text_positions = []
                y_offset = 0
                for line_height in line_heights:
                    text_pos = QtCore.QPoint(
                        int(point.x() + d_react + padding_x),
                        int(
                            point.y() + 1 + padding_y + y_offset + fm.ascent()
                        ),
                    )
                    text_positions.append(text_pos)
                    y_offset += line_height
            else:
                continue

            attributes_list.append(
                (shape, rect, text_positions, attribute_lines)
            )

        for shape, rect, _, _ in attributes_list:
            if not shape.visible:
                continue

            background_color = QtGui.QColor(*canvas.attr_background_color)
            p.fillRect(rect, background_color)

            pen = QtGui.QPen(
                QtGui.QColor(*canvas.attr_border_color),
                1,
                Qt.PenStyle.SolidLine,
            )
            p.setPen(pen)
            p.drawRect(rect)

        pen = QtGui.QPen(
            QtGui.QColor(*canvas.attr_text_color), 1, Qt.PenStyle.SolidLine
        )
        p.setPen(pen)
        p.setFont(font)

        for _, _, text_positions, attribute_lines in attributes_list:
            for text_pos, line_text in zip(text_positions, attribute_lines):
                p.drawText(text_pos, line_text)
