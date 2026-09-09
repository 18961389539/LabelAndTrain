"""Lightweight annotation quality checks for save-time and folder audit."""

from __future__ import annotations

import json
import os.path as osp
from collections import Counter

from anylabeling.views.labeling.utils.yolo_detect import (
    BOX_SHAPE_TYPES,
    SKIP_LABELS,
    load_class_names,
    merge_class_names,
    shapes_to_yolo_detect_text,
)

LOW_CONF_MIN = 0.25
LOW_CONF_MAX = 0.45
TINY_AREA_RATIO = 0.0004
EDGE_PX = 2
IMBALANCE_MIN_MAJORITY = 20
IMBALANCE_RATIO = 10.0


def _shape_points(shape):
    if not isinstance(shape, dict):
        return []
    points = shape.get("points") or []
    if shape.get("shape_type") == "rectangle" and len(points) == 2:
        (x1, y1), (x2, y2) = points[0], points[1]
        return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    return list(points)


def shape_bbox(shape):
    points = _shape_points(shape)
    if len(points) < 2:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def score_in_low_confidence_range(score, lo=LOW_CONF_MIN, hi=LOW_CONF_MAX):
    if not isinstance(score, (int, float)):
        return False
    value = float(score)
    return lo <= value <= hi


def _shape_score(shape):
    if isinstance(shape, dict):
        return shape.get("score")
    return getattr(shape, "score", None)


def shapes_have_low_confidence(shapes, lo=LOW_CONF_MIN, hi=LOW_CONF_MAX):
    for shape in shapes or []:
        if score_in_low_confidence_range(_shape_score(shape), lo, hi):
            return True
    return False


def inspect_shape_quality(shapes, image_width, image_height):
    """Return counts of tiny / edge boxes for the current image."""
    tiny = 0
    edge = 0
    labels = Counter()
    if image_width <= 0 or image_height <= 0:
        return {"tiny": 0, "edge": 0, "labels": labels}
    image_area = float(image_width * image_height)
    tiny_area = TINY_AREA_RATIO * image_area
    for shape in shapes or []:
        if not isinstance(shape, dict):
            continue
        label = str(shape.get("label") or "").strip()
        if not label or label in SKIP_LABELS:
            continue
        if (shape.get("shape_type") or "polygon") not in BOX_SHAPE_TYPES:
            continue
        box = shape_bbox(shape)
        if box is None:
            continue
        xmin, ymin, xmax, ymax = box
        width = xmax - xmin
        height = ymax - ymin
        if width <= 0 or height <= 0:
            continue
        labels[label] += 1
        if width * height < tiny_area:
            tiny += 1
        if (
            xmin <= EDGE_PX
            or ymin <= EDGE_PX
            or xmax >= image_width - EDGE_PX
            or ymax >= image_height - EDGE_PX
        ):
            edge += 1
    return {"tiny": tiny, "edge": edge, "labels": labels}


def yolo_exportable_line_count(shapes, image_width, image_height, class_names):
    text = shapes_to_yolo_detect_text(
        shapes, image_width, image_height, class_names
    )
    return len([line for line in text.splitlines() if line.strip()])


def json_txt_mismatch(json_path, data=None, class_names=None):
    """True when the YOLO sidecar is missing or has a different line count."""
    if not json_path:
        return False
    txt_path = osp.splitext(json_path)[0] + ".txt"
    if data is None:
        try:
            with open(json_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return False
    if not isinstance(data, dict):
        return False
    shapes = data.get("shapes") or []
    image_width = int(data.get("imageWidth") or 0)
    image_height = int(data.get("imageHeight") or 0)
    names = class_names
    if names is None:
        names = merge_class_names(
            load_class_names(
                osp.join(osp.dirname(json_path), "classes.txt")
            ),
            [
                shape.get("label")
                for shape in shapes
                if isinstance(shape, dict)
            ],
        )
    expected = yolo_exportable_line_count(
        shapes, image_width, image_height, names
    )
    if not osp.isfile(txt_path):
        return expected > 0
    try:
        with open(txt_path, "r", encoding="utf-8") as handle:
            actual = len(
                [line for line in handle.read().splitlines() if line.strip()]
            )
    except OSError:
        return True
    return actual != expected


def file_needs_re_autolabel(image_file, output_dir=None):
    """Unlabeled images and files with low-confidence boxes should be rerun."""
    label_file = osp.splitext(image_file)[0] + ".json"
    if output_dir:
        label_file = osp.join(output_dir, osp.basename(label_file))
    if not osp.isfile(label_file):
        return True
    try:
        with open(label_file, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return True
    shapes = data.get("shapes") or []
    if not shapes:
        return False
    return shapes_have_low_confidence(shapes)


def format_save_quality_status(stats):
    parts = []
    tiny = int((stats or {}).get("tiny") or 0)
    edge = int((stats or {}).get("edge") or 0)
    if tiny:
        parts.append(f"{tiny} 个极小框")
    if edge:
        parts.append(f"{edge} 个贴边框")
    if not parts:
        return ""
    return "注意：" + "，".join(parts)
