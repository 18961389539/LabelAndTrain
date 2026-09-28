"""Rectangle geometry constraints, independent of the canvas widget.

Extracted from ``Canvas`` (split batch 14, the first *domain* extraction
rather than a mechanical move): every function takes the image bounds
and the tuning constants as explicit arguments -- the values Canvas used
to reach for as ``self.pixmap`` / ``self.rect_scale_step`` /
``self.rect_adjust_step`` -- so the math runs, and tests, without a
widget, a pixmap, or an event loop.  Behaviour is identical to the
methods it replaces; the Canvas methods are thin delegating stubs.
"""

from PyQt6.QtCore import QPointF


def clip_rectangle_to_pixmap(shape, img_width, img_height):
    """Clip a rectangle shape to image boundaries, in place.

    Returns True when the shape is still a usable rectangle afterwards
    (including "nothing to do"); False when clipping would collapse it
    to zero area -- the caller keeps the original in that case.
    """
    if shape.shape_type != "rectangle":
        return True

    points = shape.points
    if len(points) != 4:
        return True

    x_coords = [p.x() for p in points]
    y_coords = [p.y() for p in points]
    min_x, max_x = min(x_coords), max(x_coords)
    min_y, max_y = min(y_coords), max(y_coords)

    clipped_min_x = max(0, min_x)
    clipped_min_y = max(0, min_y)
    clipped_max_x = min(img_width - 1, max_x)
    clipped_max_y = min(img_height - 1, max_y)

    if clipped_max_x <= clipped_min_x or clipped_max_y <= clipped_min_y:
        return False

    shape.points = [
        QPointF(clipped_min_x, clipped_min_y),
        QPointF(clipped_max_x, clipped_min_y),
        QPointF(clipped_max_x, clipped_max_y),
        QPointF(clipped_min_x, clipped_max_y),
    ]
    return True


def scale_from_center(shape, scale_up, step, img_width, img_height):
    """Scale a rectangle from its center by ``step``, in place.

    Atomic: if any scaled vertex would leave the image, nothing changes.
    Returns True when the shape moved.
    """
    if len(shape.points) < 4:
        return False

    x_coords = [p.x() for p in shape.points]
    y_coords = [p.y() for p in shape.points]
    center_x = sum(x_coords) / 4
    center_y = sum(y_coords) / 4
    center = QPointF(center_x, center_y)

    scale_factor = 1.0 + step if scale_up else 1.0 - step
    scale_factor = max(0.1, scale_factor)

    new_points = []
    for i in range(len(shape.points)):
        point = shape.points[i]
        offset = point - center
        scaled_offset = offset * scale_factor
        new_point = center + scaled_offset

        if (
            new_point.x() < 0
            or new_point.x() >= img_width
            or new_point.y() < 0
            or new_point.y() >= img_height
        ):
            return False

        new_points.append(new_point)

    for i, new_point in enumerate(new_points):
        shape.points[i] = new_point
    return True


def adjust_edge(shape, cursor_pos, move_outward, step, img_width, img_height):
    """Move the rectangle edge closest to ``cursor_pos`` by ``step``.

    In place.  The edge choice is exactly the original heuristic: an
    edge the cursor is beyond counts as closest, otherwise the nearer
    one wins.  Vertices are clamped to the image; vertices not on the
    chosen edge do not move.
    """
    if len(shape.points) < 4:
        return

    rect = shape.bounding_rect()
    min_x, max_x = rect.left(), rect.right()
    min_y, max_y = rect.top(), rect.bottom()

    distances = {}

    if cursor_pos.x() < min_x:
        distances["left"] = min_x - cursor_pos.x()
    elif cursor_pos.x() > max_x:
        distances["right"] = cursor_pos.x() - max_x
    else:
        distances["left"] = abs(cursor_pos.x() - min_x)
        distances["right"] = abs(cursor_pos.x() - max_x)

    if cursor_pos.y() < min_y:
        distances["top"] = min_y - cursor_pos.y()
    elif cursor_pos.y() > max_y:
        distances["bottom"] = cursor_pos.y() - max_y
    else:
        distances["top"] = abs(cursor_pos.y() - min_y)
        distances["bottom"] = abs(cursor_pos.y() - max_y)

    if (
        cursor_pos.x() < min_x
        and cursor_pos.y() >= min_y
        and cursor_pos.y() <= max_y
    ):
        closest_edge = "left"
    elif (
        cursor_pos.x() > max_x
        and cursor_pos.y() >= min_y
        and cursor_pos.y() <= max_y
    ):
        closest_edge = "right"
    elif (
        cursor_pos.y() < min_y
        and cursor_pos.x() >= min_x
        and cursor_pos.x() <= max_x
    ):
        closest_edge = "top"
    elif (
        cursor_pos.y() > max_y
        and cursor_pos.x() >= min_x
        and cursor_pos.x() <= max_x
    ):
        closest_edge = "bottom"
    else:
        closest_edge = min(distances, key=distances.get)

    signed_step = step if move_outward else -step

    for i, point in enumerate(shape.points):
        new_point = None

        if closest_edge == "left" and abs(point.x() - min_x) < 1e-6:
            new_x = max(0, point.x() - signed_step)
            new_point = QPointF(new_x, point.y())
        elif closest_edge == "right" and abs(point.x() - max_x) < 1e-6:
            new_x = min(img_width - 1, point.x() + signed_step)
            new_point = QPointF(new_x, point.y())
        elif closest_edge == "top" and abs(point.y() - min_y) < 1e-6:
            new_y = max(0, point.y() - signed_step)
            new_point = QPointF(point.x(), new_y)
        elif closest_edge == "bottom" and abs(point.y() - max_y) < 1e-6:
            new_y = min(img_height - 1, point.y() + signed_step)
            new_point = QPointF(point.x(), new_y)

        if new_point is not None:
            shape.points[i] = new_point
