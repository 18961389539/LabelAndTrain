"""Canvas geometry, independent of the canvas widget.

Extracted from ``Canvas`` (split batches 14-15, *domain* extractions
rather than mechanical moves): every function takes the image bounds,
the tuning constants, and any canvas-owned lookup as explicit arguments
-- the values Canvas used to reach for as ``self.pixmap`` /
``self.rect_scale_step`` / ``self.is_visible`` -- so the math runs, and
tests, without a widget, a pixmap, or an event loop.  Behaviour is
identical to the methods it replaces; the Canvas methods are thin
delegating stubs.
"""

from PyQt6.QtCore import QPointF

import math

from .. import utils


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


def hit_candidates(
    shapes,
    point,
    epsilon,
    is_visible,
    cuboid_vertex_lookup=None,
    cuboid_face_hit=None,
):
    """Shapes under ``point``, in interaction priority order.

    Priority tiers, exactly as Canvas ordered them: (0) a vertex within
    ``epsilon`` -- nearest vertex wins, then smaller area, then later
    stack position; (1) an edge that can take a new point (or a
    point/line/linestrip vertex at 3x epsilon); (2) the body of the
    shape.  The two cuboid lookups are canvas-owned (the cuboid mixin
    knows the control points and the face geometry); everything else is
    read off the shapes themselves.
    """
    candidates = []
    for stack_index, shape in enumerate(shapes):
        if not is_visible(shape):
            continue

        rect = shape.bounding_rect()
        area = max(0.0, rect.width()) * max(0.0, rect.height())
        vertex_distance = None
        if not shape.locked:
            if shape.shape_type == "cuboid" and len(shape.points) == 8:
                if cuboid_vertex_lookup is not None:
                    vertex_index, vertex = cuboid_vertex_lookup(
                        shape, point, epsilon
                    )
                else:
                    vertex_index, vertex = None, None
            else:
                vertex_index = shape.nearest_vertex(point, epsilon)
                vertex = (
                    shape.points[vertex_index]
                    if vertex_index is not None
                    else None
                )
            if vertex is not None:
                vertex_distance = utils.distance(vertex - point)

        if vertex_distance is not None:
            priority = (0, vertex_distance, area, -stack_index)
            candidates.append((priority, shape))
            continue

        if (
            not shape.locked
            and len(shape.points) > 1
            and shape.can_add_point()
            and shape.shape_type != "quadrilateral"
        ):
            edge_index = shape.nearest_edge(point, epsilon)
            if edge_index is not None:
                line = [
                    shape.points[edge_index - 1],
                    shape.points[edge_index],
                ]
                edge_distance = utils.distance_to_line(point, line)
                priority = (1, edge_distance, area, -stack_index)
                candidates.append((priority, shape))
                continue

        if shape.shape_type in ["point", "line", "linestrip"]:
            vertex_index = shape.nearest_vertex(point, epsilon * 3)
            if vertex_index is None:
                continue
            distance = utils.distance(shape.points[vertex_index] - point)
            priority = (1, distance, area, -stack_index)
            candidates.append((priority, shape))
            continue

        if shape.shape_type == "cuboid" and len(shape.points) == 8:
            hit = bool(cuboid_face_hit and cuboid_face_hit(shape, point))
        else:
            hit = len(shape.points) > 1 and shape.contains_point(point)
        if hit:
            priority = (2, area, 0.0, -stack_index)
            candidates.append((priority, shape))

    candidates.sort(key=lambda item: item[0])
    return [shape for _, shape in candidates]


def out_of_bounds(p, img_width, img_height):
    """Whether a position leaves the [0, w-1] x [0, h-1] image area."""
    return not (0 <= p.x() <= img_width - 1 and 0 <= p.y() <= img_height - 1)


def line_image_intersection(p1, p2, img_width, img_height):
    """Where the segment p1->p2 crosses the image border.

    ``p1`` is expected inside (it is clamped first), ``p2`` outside.
    Clockwise edge walk, exactly as Canvas did it.
    """
    corners = [
        (0, 0),
        (img_width - 1, 0),
        (img_width - 1, img_height - 1),
        (0, img_height - 1),
    ]
    x1 = min(max(p1.x(), 0), img_width - 1)
    y1 = min(max(p1.y(), 0), img_height - 1)
    x2, y2 = p2.x(), p2.y()
    _, i, (x, y) = min(_intersecting_edges((x1, y1), (x2, y2), corners))
    x3, y3 = corners[i]
    x4, y4 = corners[(i + 1) % 4]
    x1, y1 = int(x1), int(y1)
    x2, y2 = int(x2), int(y2)
    x3, y3 = int(x3), int(y3)
    x4, y4 = int(x4), int(y4)
    if (x, y) == (x1, y1):
        # Handle cases where previous point is on one of the edges.
        if x3 == x4:
            return QPointF(x3, min(max(0, y2), max(y3, y4)))
        # y3 == y4
        return QPointF(min(max(0, x2), max(x3, x4)), y3)
    return QPointF(int(x), int(y))


def _intersecting_edges(point1, point2, corners):
    """Yield (distance-to-edge-middle, edge index, intersection) for each
    image edge crossing the segment ``(point1, point2)`` -- the closest
    one wins.  Segment-segment intersection via the parametric form; both
    parameters must land in [0, 1] for the crossing to count.
    """
    x1, y1 = point1
    x2, y2 = point2
    for i in range(4):
        x3, y3 = corners[i]
        x4, y4 = corners[(i + 1) % 4]
        denom = (y4 - y3) * (x2 - x1) - (x4 - x3) * (y2 - y1)
        nua = (x4 - x3) * (y1 - y3) - (y4 - y3) * (x1 - x3)
        nub = (x2 - x1) * (y1 - y3) - (y2 - y1) * (x1 - x3)
        if denom == 0:
            # This covers two cases:
            #   nua == nub == 0: Coincident
            #   otherwise: Parallel
            continue
        ua, ub = nua / denom, nub / denom
        if 0 <= ua <= 1 and 0 <= ub <= 1:
            x = x1 + ua * (x2 - x1)
            y = y1 + ua * (y2 - y1)
            middle = QPointF((x3 + x4) / 2, (y3 + y4) / 2)
            d = utils.distance(middle - QPointF(x2, y2))
            yield d, i, (x, y)


def selection_offsets(shapes, point, img_width, img_height):
    """Offsets of the selection's bounding box to the image borders --
    what Canvas kept as ``self.offsets`` between selection and drag."""
    left = img_width - 1
    right = 0
    top = img_height - 1
    bottom = 0
    for shape in shapes:
        rect = shape.bounding_rect()
        if rect.left() < left:
            left = rect.left()
        if rect.right() > right:
            right = rect.right()
        if rect.top() < top:
            top = rect.top()
        if rect.bottom() > bottom:
            bottom = rect.bottom()

    x1 = left - point.x()
    y1 = top - point.y()
    x2 = right - point.x()
    y2 = bottom - point.y()
    return (QPointF(x1, y1), QPointF(x2, y2))


def drag_shapes_bounded(
    shapes, pos, prev_point, offsets, img_width, img_height, allowed_oop
):
    """Move a group of unlocked shapes, clamped to the image.

    Returns ``(moved, new_pos)``; ``new_pos`` is what the caller should
    store as its previous-point.  Shapes of a type in ``allowed_oop``
    may leave the image, but only when the whole selection is that type.
    """
    shapes = [shape for shape in shapes if not shape.locked]
    if not shapes:
        return False, pos
    shape_types = []
    for shape in shapes:
        if shape.shape_type in allowed_oop:
            shape_types.append(shape.shape_type)

    if out_of_bounds(pos, img_width, img_height) and len(shape_types) == 0:
        return False, pos
    if len(shape_types) > 0 and len(shapes) != len(shape_types):
        return False, pos

    if len(shape_types) == 0:
        o1 = pos + offsets[0]
        if out_of_bounds(o1, img_width, img_height):
            pos -= QPointF(min(0, int(o1.x())), min(0, int(o1.y())))
        o2 = pos + offsets[1]
        if out_of_bounds(o2, img_width, img_height):
            pos += QPointF(
                min(0, int(img_width - o2.x())),
                min(0, int(img_height - o2.y())),
            )
    dp = pos - prev_point
    if dp:
        for shape in shapes:
            shape.move_by(dp)
        return True, pos
    return False, pos


def rotate_point(p, center, theta):
    """Rotate ``p`` around ``center`` by ``theta`` radians."""
    order = p - center
    cos_theta = math.cos(theta)
    sin_theta = math.sin(theta)
    res_x = cos_theta * order.x() + sin_theta * order.y()
    res_y = -sin_theta * order.x() + cos_theta * order.y()
    return QPointF(center.x() + res_x, center.y() + res_y)


def adjoint_points(theta, p3, p1, index):
    """The two companion corners of a rotation-shape vertex being moved.

    A rotation shape keeps its four points on a rectangle aligned with
    ``theta``; moving one corner forces the two adjacent ones onto the
    perpendicular lines through it.  Returns ``(p2, p3, p4)``.
    """
    a1 = math.tan(theta)
    if a1 == 0:
        if index % 2 == 0:
            p2 = QPointF(p3.x(), p1.y())
            p4 = QPointF(p1.x(), p3.y())
        else:
            p4 = QPointF(p3.x(), p1.y())
            p2 = QPointF(p1.x(), p3.y())
    else:
        a2 = -1 / a1
        b1 = p1.y() - a1 * p1.x()
        b2 = p1.y() - a2 * p1.x()
        b3 = p3.y() - a1 * p3.x()
        b4 = p3.y() - a2 * p3.x()

        if index % 2 == 0:
            p2 = _cross_point(a1, b1, a2, b4)
            p4 = _cross_point(a2, b2, a1, b3)
        else:
            p4 = _cross_point(a1, b1, a2, b4)
            p2 = _cross_point(a2, b2, a1, b3)

    return p2, p3, p4


def _cross_point(a1, b1, a2, b2):
    x = (b2 - b1) / (a1 - a2)
    y = (a1 * b2 - a2 * b1) / (a1 - a2)
    return QPointF(x, y)


def move_vertex_bounded(shape, index, pos, img_width, img_height, allowed_oop):
    """Move one vertex, clamped to the image -- the drag math behind
    Canvas.bounded_move_vertex (locked and cuboid handling stay there).

    Rotation shapes move their two adjacent corners along the perpendicular
    lines; rectangle shapes keep the opposite edge's axis; everything else
    moves the single vertex.
    """
    point = shape[index]
    if out_of_bounds(pos, img_width, img_height) and (
        shape.shape_type not in allowed_oop
    ):
        pos = line_image_intersection(point, pos, img_width, img_height)

    if shape.shape_type == "rotation":
        sindex = (index + 2) % 4
        # Get the other 3 points after transformed
        p2, p3, p4 = adjoint_points(shape.direction, shape[sindex], pos, index)
        # Move 4 pixal one by one
        shape.move_vertex_by(index, pos - point)
        lindex = (index + 1) % 4
        rindex = (index + 3) % 4
        shape[lindex] = p2
        shape[rindex] = p4
        shape.close()
    elif shape.shape_type == "rectangle":
        shift_pos = pos - point
        shape.move_vertex_by(index, shift_pos)
        left_index = (index + 1) % 4
        right_index = (index + 3) % 4
        left_shift = None
        right_shift = None
        if index % 2 == 0:
            right_shift = QPointF(shift_pos.x(), 0)
            left_shift = QPointF(0, shift_pos.y())
        else:
            left_shift = QPointF(shift_pos.x(), 0)
            right_shift = QPointF(0, shift_pos.y())
        shape.move_vertex_by(right_index, right_shift)
        shape.move_vertex_by(left_index, left_shift)
    else:
        shape.move_vertex_by(index, pos - point)
