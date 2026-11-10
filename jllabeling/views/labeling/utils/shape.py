import json
import math

import numpy as np

from PyQt6 import QtWidgets
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QDialog, QProgressDialog

from jllabeling.core.labels.geometry import (
    masks_to_bboxes,
    rectangle_from_diagonal,
    shape_to_mask,
    shapes_to_label,
)
from jllabeling.views.labeling.logger import logger
from jllabeling.views.labeling.utils.opencv import get_bounding_boxes
from jllabeling.views.labeling.widgets.polygon_sides_dialog import (
    PolygonSidesDialog,
)
from jllabeling.views.labeling.widgets.popup import Popup
from jllabeling.views.labeling.utils.qt import new_icon_path
from jllabeling.views.labeling.utils.style import *
from jllabeling.services.auto_labeling.utils import calculate_rotation_theta

CONVERSION_TARGETS = {
    "polygon": ["rectangle", "rotation"],
    "rectangle": ["rotation", "polygon", "circle", "quadrilateral"],
    "rotation": ["rectangle", "quadrilateral", "polygon", "circle"],
    "line": ["linestrip"],
    "circle": ["rectangle", "rotation", "quadrilateral", "polygon"],
    "quadrilateral": ["polygon"],
}

CONVERSION_MODE_MAP = {
    (source_type, target_type): f"{source_type}_to_{target_type}"
    for source_type, target_types in CONVERSION_TARGETS.items()
    for target_type in target_types
}

LEGACY_MODE_MAP = {
    "hbb_to_obb": "rectangle_to_rotation",
    "obb_to_hbb": "rotation_to_rectangle",
    "polygon_to_hbb": "polygon_to_rectangle",
    "polygon_to_obb": "polygon_to_rotation",
}


def _normalize_mode(mode):
    return LEGACY_MODE_MAP.get(mode, mode)


def _to_axis_aligned_box(points):
    points = np.asarray(points, dtype=np.float32)
    if len(points) == 0:
        return None
    xmin = int(np.min(points[:, 0]))
    ymin = int(np.min(points[:, 1]))
    xmax = int(np.max(points[:, 0]))
    ymax = int(np.max(points[:, 1]))
    return [
        [xmin, ymin],
        [xmax, ymin],
        [xmax, ymax],
        [xmin, ymax],
    ]


def _circle_center_radius(points):
    points = np.asarray(points, dtype=np.float32)
    if len(points) != 2:
        return None, None, None
    center_x, center_y = points[0]
    edge_x, edge_y = points[1]
    radius = math.sqrt((edge_x - center_x) ** 2 + (edge_y - center_y) ** 2)
    if radius <= 0:
        return None, None, None
    return float(center_x), float(center_y), float(radius)


def _circle_points(center_x, center_y, radius):
    return [[center_x, center_y], [center_x + radius, center_y]]


def _rotation_center_inscribed_radius(points):
    points = np.asarray(points, dtype=np.float32)
    if len(points) != 4:
        return None, None, None
    center_x = float(np.mean(points[:, 0]))
    center_y = float(np.mean(points[:, 1]))
    side_lengths = []
    for i in range(4):
        side_lengths.append(
            float(np.linalg.norm(points[(i + 1) % 4] - points[i]))
        )
    radius = min(side_lengths) / 2.0 if side_lengths else 0.0
    if radius <= 0:
        return None, None, None
    return center_x, center_y, radius


def _apply_shape_conversion(data, mode, params):
    normalized_mode = _normalize_mode(mode)
    for j in range(len(data["shapes"])):
        shape = data["shapes"][j]
        if shape.get("locked", False):
            continue
        shape_type = shape.get("shape_type")
        points = shape.get("points", [])

        if (
            normalized_mode == "rectangle_to_rotation"
            and shape_type == "rectangle"
        ):
            points = _to_axis_aligned_box(points)
            if points is None:
                continue
            shape["shape_type"] = "rotation"
            shape["points"] = points
            shape["direction"] = 0

        elif (
            normalized_mode == "rotation_to_rectangle"
            and shape_type == "rotation"
        ):
            points = _to_axis_aligned_box(points)
            if points is None:
                continue
            shape.pop("direction", None)
            shape["shape_type"] = "rectangle"
            shape["points"] = points

        elif (
            normalized_mode == "polygon_to_rectangle"
            and shape_type == "polygon"
        ):
            if len(points) < 3:
                continue
            points = _to_axis_aligned_box(points)
            if points is None:
                continue
            shape["shape_type"] = "rectangle"
            shape["points"] = points

        elif (
            normalized_mode == "polygon_to_rotation"
            and shape_type == "polygon"
        ):
            points = np.asarray(points)
            if len(points) < 3:
                continue
            contours = points.reshape((-1, 1, 2)).astype(np.float32)
            _, rotation_box = get_bounding_boxes(contours)
            shape["shape_type"] = "rotation"
            shape["points"] = rotation_box.tolist()
            shape["direction"] = calculate_rotation_theta(rotation_box)

        elif normalized_mode == "circle_to_polygon" and shape_type == "circle":
            center_x, center_y, radius = _circle_center_radius(points)
            if radius is None:
                continue
            num_sides = params.get("num_sides", 32)
            polygon_points = []
            for i in range(num_sides):
                angle = 2 * math.pi * i / num_sides
                x = center_x + radius * math.cos(angle)
                y = center_y + radius * math.sin(angle)
                polygon_points.append([x, y])
            shape["shape_type"] = "polygon"
            shape["points"] = polygon_points
            shape.pop("direction", None)

        elif (
            normalized_mode == "rectangle_to_polygon"
            and shape_type == "rectangle"
        ):
            points = _to_axis_aligned_box(points)
            if points is None:
                continue
            shape["shape_type"] = "polygon"
            shape["points"] = points
            shape.pop("direction", None)

        elif (
            normalized_mode == "rotation_to_polygon"
            and shape_type == "rotation"
        ):
            points = np.asarray(points).tolist()
            if len(points) != 4:
                continue
            shape["shape_type"] = "polygon"
            shape["points"] = points
            shape.pop("direction", None)

        elif (
            normalized_mode == "rectangle_to_quadrilateral"
            and shape_type == "rectangle"
        ):
            points = _to_axis_aligned_box(points)
            if points is None:
                continue
            shape["shape_type"] = "quadrilateral"
            shape["points"] = points
            shape.pop("direction", None)

        elif (
            normalized_mode == "rotation_to_quadrilateral"
            and shape_type == "rotation"
        ):
            points = np.asarray(points).tolist()
            if len(points) != 4:
                continue
            shape["shape_type"] = "quadrilateral"
            shape["points"] = points
            shape.pop("direction", None)

        elif (
            normalized_mode == "quadrilateral_to_polygon"
            and shape_type == "quadrilateral"
        ):
            points = np.asarray(points).tolist()
            if len(points) != 4:
                continue
            shape["shape_type"] = "polygon"
            shape["points"] = points
            shape.pop("direction", None)

        elif normalized_mode == "line_to_linestrip" and shape_type == "line":
            points = np.asarray(points).tolist()
            if len(points) < 2:
                continue
            shape["shape_type"] = "linestrip"
            shape["points"] = points
            shape.pop("direction", None)

        elif (
            normalized_mode == "rectangle_to_circle"
            and shape_type == "rectangle"
        ):
            points = _to_axis_aligned_box(points)
            if points is None:
                continue
            width = abs(points[1][0] - points[0][0])
            height = abs(points[2][1] - points[1][1])
            radius = min(width, height) / 2.0
            if radius <= 0:
                continue
            center_x = (points[0][0] + points[2][0]) / 2.0
            center_y = (points[0][1] + points[2][1]) / 2.0
            shape["shape_type"] = "circle"
            shape["points"] = _circle_points(center_x, center_y, radius)
            shape.pop("direction", None)

        elif (
            normalized_mode == "rotation_to_circle"
            and shape_type == "rotation"
        ):
            center_x, center_y, radius = _rotation_center_inscribed_radius(
                points
            )
            if radius is None:
                continue
            shape["shape_type"] = "circle"
            shape["points"] = _circle_points(center_x, center_y, radius)
            shape.pop("direction", None)

        elif (
            normalized_mode == "circle_to_rectangle" and shape_type == "circle"
        ):
            center_x, center_y, radius = _circle_center_radius(points)
            if radius is None:
                continue
            shape["shape_type"] = "rectangle"
            shape["points"] = [
                [int(center_x - radius), int(center_y - radius)],
                [int(center_x + radius), int(center_y - radius)],
                [int(center_x + radius), int(center_y + radius)],
                [int(center_x - radius), int(center_y + radius)],
            ]
            shape.pop("direction", None)

        elif (
            normalized_mode == "circle_to_rotation" and shape_type == "circle"
        ):
            center_x, center_y, radius = _circle_center_radius(points)
            if radius is None:
                continue
            shape["shape_type"] = "rotation"
            shape["points"] = [
                [int(center_x - radius), int(center_y - radius)],
                [int(center_x + radius), int(center_y - radius)],
                [int(center_x + radius), int(center_y + radius)],
                [int(center_x - radius), int(center_y + radius)],
            ]
            shape["direction"] = 0

        elif (
            normalized_mode == "circle_to_quadrilateral"
            and shape_type == "circle"
        ):
            center_x, center_y, radius = _circle_center_radius(points)
            if radius is None:
                continue
            shape["shape_type"] = "quadrilateral"
            shape["points"] = [
                [int(center_x - radius), int(center_y - radius)],
                [int(center_x + radius), int(center_y - radius)],
                [int(center_x + radius), int(center_y + radius)],
                [int(center_x - radius), int(center_y + radius)],
            ]
            shape.pop("direction", None)


def open_shape_converter(self):
    from jllabeling.views.labeling.widgets.shape_converter_dialog import (
        ShapeConverterDialog,
    )

    dialog = ShapeConverterDialog(self)
    dialog.exec()


def get_conversion_params(self, mode: str):
    """Get parameters required for specific conversion modes.

    Args:
        mode (str): The conversion mode

    Returns:
        dict: Parameters dictionary, or None if user cancelled
    """
    if mode == "circle_to_polygon":
        dialog = PolygonSidesDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return {"num_sides": dialog.get_value()}
        else:
            return None

    return {}


def polygons_to_mask(img_shape, polygons, shape_type=None):
    logger.warning(
        "The 'polygons_to_mask' function is deprecated, "
        "use 'shape_to_mask' instead."
    )
    return shape_to_mask(img_shape, points=polygons, shape_type=shape_type)
