"""Write Ultralytics YOLO-detect ``.txt`` files next to JSON labels."""

from __future__ import annotations

import json
import os
import os.path as osp
import tempfile

from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils._io import safe_replace

SKIP_LABELS = {
    "AUTOLABEL_OBJECT",
    "AUTOLABEL_ADD",
    "AUTOLABEL_REMOVE",
}
BOX_SHAPE_TYPES = {
    "rectangle",
    "polygon",
    "rotation",
    "quadrilateral",
}
CLASSES_FILENAME = "classes.txt"


def _clean_label(name):
    if name is None:
        return None
    text = str(name).strip()
    if not text or text in SKIP_LABELS:
        return None
    return text


def merge_class_names(*groups):
    """Keep first-seen order; later groups only append new names."""
    names = []
    seen = set()
    for group in groups:
        if not group:
            continue
        for name in group:
            text = _clean_label(name)
            if text is None or text in seen:
                continue
            seen.add(text)
            names.append(text)
    return names


def load_class_names(classes_file):
    if not classes_file or not osp.isfile(classes_file):
        return []
    with open(classes_file, "r", encoding="utf-8") as handle:
        return merge_class_names(handle.read().splitlines())


def _atomic_write_text(path, content):
    directory = osp.dirname(osp.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, temporary_file = tempfile.mkstemp(
        prefix=".yolo_",
        suffix=".tmp",
        dir=directory,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        safe_replace(temporary_file, path)
    finally:
        if temporary_file and osp.exists(temporary_file):
            try:
                os.remove(temporary_file)
            except OSError:
                pass


def write_class_names(classes_file, class_names):
    names = merge_class_names(class_names)
    if not names:
        return []
    if load_class_names(classes_file) == names:
        return names
    _atomic_write_text(classes_file, "".join(f"{name}\n" for name in names))
    return names


def _rectangle_from_diagonal(points):
    x1, y1 = points[0]
    x2, y2 = points[1]
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _clamp_points(points, image_width, image_height):
    max_x = max(0, image_width - 1)
    max_y = max(0, image_height - 1)
    return [
        [max(0, min(p[0], max_x)), max(0, min(p[1], max_y))]
        for p in points
    ]


def _normalized_xywh(points, image_width, image_height):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    width = xmax - xmin
    height = ymax - ymin
    if width <= 0 or height <= 0:
        return None
    x_center = (xmin + xmax) / (2 * image_width)
    y_center = (ymin + ymax) / (2 * image_height)
    return (
        x_center,
        y_center,
        width / image_width,
        height / image_height,
    )


def shape_to_yolo_detect_line(shape, class_names, image_width, image_height):
    if image_width <= 0 or image_height <= 0 or not isinstance(shape, dict):
        return None
    label = _clean_label(shape.get("label"))
    if label is None or label not in class_names:
        return None
    shape_type = shape.get("shape_type") or "polygon"
    if shape_type not in BOX_SHAPE_TYPES:
        return None
    points = list(shape.get("points") or [])
    if shape_type == "rectangle" and len(points) == 2:
        points = _rectangle_from_diagonal(points)
    if len(points) < 2:
        return None
    clamped = _clamp_points(points, image_width, image_height)
    xywh = _normalized_xywh(clamped, image_width, image_height)
    if xywh is None:
        return None
    x_center, y_center, width, height = xywh
    class_id = class_names.index(label)
    return (
        f"{class_id} {x_center:.6f} {y_center:.6f} "
        f"{width:.6f} {height:.6f}"
    )


def shapes_to_yolo_detect_text(shapes, image_width, image_height, class_names):
    lines = []
    for shape in shapes or []:
        line = shape_to_yolo_detect_line(
            shape, class_names, image_width, image_height
        )
        if line:
            lines.append(line)
    return "".join(f"{line}\n" for line in lines)


def write_yolo_detect_sidecar(
    json_path,
    shapes,
    image_width,
    image_height,
    extra_class_names=None,
):
    """Write ``<stem>.txt`` and keep ``classes.txt`` beside the JSON file.

    Existing ``classes.txt`` order is preserved; new names are appended so
    previously saved class ids stay stable. An image with no boxes still
    gets an empty txt (YOLO negative sample).
    """
    if not json_path:
        return None
    directory = osp.dirname(osp.abspath(json_path))
    classes_file = osp.join(directory, CLASSES_FILENAME)
    txt_path = osp.splitext(json_path)[0] + ".txt"
    shape_labels = [
        shape.get("label")
        for shape in (shapes or [])
        if isinstance(shape, dict)
    ]
    class_names = merge_class_names(
        load_class_names(classes_file),
        extra_class_names,
        shape_labels,
    )
    if class_names:
        write_class_names(classes_file, class_names)
    if image_width <= 0 or image_height <= 0:
        logger.warning(
            "Skip YOLO txt for %s: invalid image size %sx%s",
            json_path,
            image_width,
            image_height,
        )
        return txt_path
    _atomic_write_text(
        txt_path,
        shapes_to_yolo_detect_text(
            shapes, image_width, image_height, class_names
        ),
    )
    return txt_path


def rename_class_in_classes_txt(classes_file, old_label, new_label):
    """Replace ``old_label`` with ``new_label`` at the same index.

    If ``new_label`` already exists, the old slot is dropped (merge) and
    later ids shift. Returns the updated name list.
    """
    old_name = _clean_label(old_label)
    new_name = _clean_label(new_label)
    names = load_class_names(classes_file)
    if not old_name or not new_name or old_name == new_name:
        return names
    mapped = []
    seen = set()
    found = False
    for name in names:
        value = new_name if name == old_name else name
        if name == old_name:
            found = True
        if value in seen:
            continue
        seen.add(value)
        mapped.append(value)
    if not found:
        return names
    write_class_names(classes_file, mapped)
    return mapped


def apply_class_renames_in_classes_txt(
    classes_file, mapping=None, deleted=None
):
    names = load_class_names(classes_file)
    mapping = mapping or {}
    deleted = set(deleted or [])
    mapped = []
    seen = set()
    for name in names:
        if name in deleted:
            continue
        value = mapping.get(name) or name
        value = _clean_label(value) or name
        if value in seen:
            continue
        seen.add(value)
        mapped.append(value)
    if mapped:
        write_class_names(classes_file, mapped)
    return mapped


def rewrite_yolo_sidecars_for_images(
    image_paths, label_dir, extra_class_names=None
):
    rewritten = 0
    if not label_dir:
        return rewritten
    extra = merge_class_names(
        load_class_names(osp.join(label_dir, CLASSES_FILENAME)),
        extra_class_names,
    )
    for image_path in image_paths or []:
        json_path = osp.join(
            label_dir,
            osp.splitext(osp.basename(image_path))[0] + ".json",
        )
        if not osp.isfile(json_path):
            continue
        try:
            with open(json_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Skip YOLO rewrite for {json_path}: {exc}")
            continue
        if not isinstance(data, dict):
            continue
        write_yolo_detect_sidecar(
            json_path,
            data.get("shapes") or [],
            int(data.get("imageWidth") or 0),
            int(data.get("imageHeight") or 0),
            extra_class_names=extra,
        )
        rewritten += 1
    return rewritten


def rename_label_across_folder(
    image_paths, label_dir, old_label, new_label, extra_class_names=None
):
    """Rename a class in every JSON, keep YOLO ids stable, rewrite txt."""
    if not label_dir or not old_label or not new_label:
        return 0
    os.makedirs(label_dir, exist_ok=True)
    classes_file = osp.join(label_dir, CLASSES_FILENAME)
    old_name = _clean_label(old_label)
    new_name = _clean_label(new_label) or new_label
    names = rename_class_in_classes_txt(classes_file, old_label, new_label)
    mapped_extra = [
        new_name if _clean_label(name) == old_name else name
        for name in (extra_class_names or [])
    ]
    names = merge_class_names(names, mapped_extra)
    if names:
        write_class_names(classes_file, names)

    json_changed = 0
    for image_path in image_paths or []:
        json_path = osp.join(
            label_dir,
            osp.splitext(osp.basename(image_path))[0] + ".json",
        )
        if not osp.isfile(json_path):
            continue
        try:
            with open(json_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Skip rename for {json_path}: {exc}")
            continue
        if not isinstance(data, dict):
            continue
        changed = False
        for shape in data.get("shapes") or []:
            if isinstance(shape, dict) and shape.get("label") == old_label:
                shape["label"] = new_label
                changed = True
        if changed:
            with open(json_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False)
            json_changed += 1
        write_yolo_detect_sidecar(
            json_path,
            data.get("shapes") or [],
            int(data.get("imageWidth") or 0),
            int(data.get("imageHeight") or 0),
            extra_class_names=names,
        )
    return json_changed
