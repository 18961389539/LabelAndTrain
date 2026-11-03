"""Read and write Ultralytics YOLO ``.txt`` labels in place.

A pure-YOLO dataset stores one ``<stem>.txt`` per image, either beside the
image or under the standard ``images/...`` + ``labels/...`` tree. The
annotator only knew the app's JSON, so opening such a folder showed blank
canvases and training treated every image as a background sample. This
module supplies the missing half: parse those lines into shapes on open
and write the same ``.txt`` back on save, keeping the dataset pure YOLO
instead of growing JSON files inside it.

Only the two layouts the app can represent without extra configuration
are handled: 5-column boxes (detect) and ``1 + 2n`` normalized polygons
(segment). Pose/OBB lines are reported as skipped rather than guessed at.
"""

from __future__ import annotations

import os
import os.path as osp

from anylabeling.views.labeling.logger import logger

from ._io import io_open
from .yolo_detect import (
    CLASSES_FILENAME,
    SKIP_LABELS,
    _atomic_write_text,
    load_class_names,
    merge_class_names,
    write_class_names,
)

DATA_YAML_FILENAMES = ("data.yaml", "data.yml")
IMAGES_DIR_NAME = "images"
LABELS_DIR_NAME = "labels"
MAX_PARENT_LEVELS = 3

BOX_SHAPE_TYPES = {"rectangle", "polygon", "rotation", "quadrilateral"}


def _ancestor_dirs(start_dir, levels=MAX_PARENT_LEVELS):
    directory = osp.abspath(start_dir)
    for _ in range(levels):
        yield directory
        parent = osp.dirname(directory)
        if parent == directory:
            break
        directory = parent


def _first_existing(start_dir, filenames):
    for directory in _ancestor_dirs(start_dir):
        for name in filenames:
            candidate = osp.join(directory, name)
            if osp.isfile(candidate):
                return candidate
    return None


def sibling_labels_dir(image_path):
    """``.../images/<split>/x.jpg`` -> ``.../labels/<split>``, else None.

    String surgery on the separator-delimited marker (not a ``split``
    and re-``join``, which drops the drive colon on Windows and the
    leading slash on POSIX).
    """
    if not image_path:
        return None
    path = osp.normpath(osp.abspath(image_path))
    marker = os.sep + IMAGES_DIR_NAME + os.sep
    index = path.lower().rfind(marker.lower())
    if index < 0:
        return None
    replaced = (
        path[:index]
        + os.sep
        + LABELS_DIR_NAME
        + os.sep
        + path[index + len(marker) :]
    )
    return osp.dirname(replaced)


def find_yolo_txt(image_path, output_dir=None):
    """Locate the YOLO txt that belongs to ``image_path``, or None.

    Mirrors the JSON lookup: an explicit output directory wins and is not
    second-guessed, otherwise the image's own folder is tried first and
    the sibling ``labels`` tree second.
    """
    if not image_path:
        return None
    stem = osp.splitext(osp.basename(image_path))[0]
    if output_dir:
        candidates = [osp.join(output_dir, stem + ".txt")]
    else:
        candidates = [osp.join(osp.dirname(image_path), stem + ".txt")]
        labels_dir = sibling_labels_dir(image_path)
        if labels_dir:
            candidates.append(osp.join(labels_dir, stem + ".txt"))
    for candidate in candidates:
        if osp.isfile(candidate):
            return candidate
    return None


def _names_from_data_yaml(yaml_path):
    try:
        import yaml

        with open(yaml_path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except Exception as exc:  # noqa: BLE001 - a broken yaml is not fatal
        logger.warning(f"Failed to read YOLO data yaml {yaml_path}: {exc}")
        return []
    names = data.get("names") if isinstance(data, dict) else None
    if isinstance(names, list):
        return [str(name) for name in names]
    if isinstance(names, dict):

        def sort_key(item):
            key = item[0]
            return int(key) if str(key).isdigit() else str(key)

        return [str(name) for _, name in sorted(names.items(), key=sort_key)]
    return []


def class_names_for(txt_path, fallback=None):
    """``(names, classes_file)`` for the dataset this txt belongs to.

    The dataset's own ``classes.txt`` (or ``data.yaml`` names) decides the
    id mapping, because the txt lines are indices into *that* list. The
    panel's labels are only a last resort; using them first would remap
    every id whenever the two disagree.
    """
    label_dir = osp.dirname(osp.abspath(txt_path))
    classes_file = _first_existing(label_dir, (CLASSES_FILENAME,))
    names = load_class_names(classes_file) if classes_file else []
    if not names:
        yaml_file = _first_existing(label_dir, DATA_YAML_FILENAMES)
        if yaml_file:
            names = _names_from_data_yaml(yaml_file)
    if not names:
        names = merge_class_names(fallback)
    if classes_file is None:
        # Saving a label the dataset does not know yet needs somewhere to
        # pin the new id; the labels folder is the standard spot.
        classes_file = osp.join(label_dir, CLASSES_FILENAME)
    return names, classes_file


def read_lines(txt_path):
    with io_open(txt_path, "r") as handle:
        return [line.strip() for line in handle if line.strip()]


def has_objects(txt_path):
    """False for a missing/empty/whitespace-only file (a negative sample)."""
    try:
        return bool(read_lines(txt_path))
    except OSError:
        return False


def _clamp(value, limit):
    return max(0.0, min(float(value), max(limit - 1, 0)))


def _label_for(class_index, class_names):
    if 0 <= class_index < len(class_names):
        return class_names[class_index]
    logger.warning(
        f"YOLO class id {class_index} has no name; using a placeholder"
    )
    return f"class_{class_index}"


def _rect_shape(parts, width, height, label):
    cx, cy, bw, bh = (float(value) for value in parts[1:5])
    xmin = _clamp((cx - bw / 2) * width, width)
    ymin = _clamp((cy - bh / 2) * height, height)
    xmax = _clamp((cx + bw / 2) * width, width)
    ymax = _clamp((cy + bh / 2) * height, height)
    return {
        "label": label,
        "points": [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]],
        "group_id": None,
        "description": "",
        "shape_type": "rectangle",
        "flags": {},
        "attributes": {},
        "difficult": False,
    }


def _polygon_shape(parts, width, height, label):
    coords = [float(value) for value in parts[1:]]
    points = [
        [
            _clamp(coords[i] * width, width),
            _clamp(coords[i + 1] * height, height),
        ]
        for i in range(0, len(coords) - 1, 2)
    ]
    if len(points) < 3:
        raise ValueError("polygon needs at least three points")
    return {
        "label": label,
        "points": points,
        "group_id": None,
        "description": "",
        "shape_type": "polygon",
        "flags": {},
        "attributes": {},
        "difficult": False,
    }


def load_shapes(txt_path, image_width, image_height, class_names=None):
    """Parse a YOLO txt into shape dicts.

    Returns ``{"shapes", "mode", "skipped"}``. ``mode`` is what saving
    must write back: ``"segment"`` as soon as one polygon line is seen,
    ``"detect"`` otherwise. Unparsable lines are counted, never invented.
    """
    lines = read_lines(txt_path)
    names = list(class_names or [])
    shapes = []
    skipped = 0
    mode = "detect"
    for line in lines:
        parts = line.replace("\t", " ").split()
        try:
            class_index = int(float(parts[0]))
        except (IndexError, ValueError):
            skipped += 1
            continue
        label = _label_for(class_index, names)
        try:
            if len(parts) == 5:
                shapes.append(
                    _rect_shape(parts, image_width, image_height, label)
                )
            elif len(parts) >= 7 and (len(parts) - 1) % 2 == 0:
                shapes.append(
                    _polygon_shape(parts, image_width, image_height, label)
                )
                mode = "segment"
            else:
                skipped += 1
        except ValueError as exc:
            logger.warning(f"Skip unparsable YOLO line in {txt_path}: {exc}")
            skipped += 1
    return {"shapes": shapes, "mode": mode, "skipped": skipped}


def _normalized_box(shape, width, height):
    shape_type = shape.get("shape_type") or "polygon"
    if shape_type not in BOX_SHAPE_TYPES:
        return None
    points = list(shape.get("points") or [])
    if shape_type == "rectangle" and len(points) == 2:
        x1, y1 = points[0]
        x2, y2 = points[1]
        points = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    if len(points) < 2:
        return None
    xs = [_clamp(point[0], width) for point in points]
    ys = [_clamp(point[1], height) for point in points]
    box_width = max(xs) - min(xs)
    box_height = max(ys) - min(ys)
    if box_width <= 0 or box_height <= 0:
        return None
    return (
        (min(xs) + max(xs)) / (2 * width),
        (min(ys) + max(ys)) / (2 * height),
        box_width / width,
        box_height / height,
    )


def _normalized_polygon(shape, width, height):
    shape_type = shape.get("shape_type") or "polygon"
    if shape_type not in BOX_SHAPE_TYPES:
        return None
    points = list(shape.get("points") or [])
    if shape_type == "rectangle" and len(points) == 2:
        x1, y1 = points[0]
        x2, y2 = points[1]
        points = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    if len(points) < 3:
        return None
    coords = []
    for point in points:
        coords.append(_clamp(point[0], width) / width)
        coords.append(_clamp(point[1], height) / height)
    return coords


def save_shapes(
    txt_path,
    shapes,
    image_width,
    image_height,
    class_names=None,
    mode="detect",
    classes_file=None,
):
    """Write shapes back to ``txt_path`` in the same layout as on open.

    Class ids come from the dataset's own name list; a label the dataset
    has never seen is appended (and persisted when ``classes_file`` is
    known) so earlier ids stay stable.
    """
    if not txt_path:
        return []
    if image_width <= 0 or image_height <= 0:
        raise ValueError(
            f"invalid image size {image_width}x{image_height} for {txt_path}"
        )
    names = merge_class_names(class_names)
    added = False
    lines = []
    skipped = 0
    for shape in shapes or []:
        if not isinstance(shape, dict):
            continue
        label = str(shape.get("label") or "").strip()
        if not label or label in SKIP_LABELS:
            continue
        if label not in names:
            names.append(label)
            added = True
        class_id = names.index(label)
        if mode == "segment":
            coords = _normalized_polygon(shape, image_width, image_height)
            if coords is None:
                skipped += 1
                continue
            payload = " ".join(f"{value:.6f}" for value in coords)
        else:
            box = _normalized_box(shape, image_width, image_height)
            if box is None:
                skipped += 1
                continue
            payload = " ".join(f"{value:.6f}" for value in box)
        lines.append(f"{class_id} {payload}\n")
    _atomic_write_text(txt_path, "".join(lines))
    if added and classes_file:
        write_class_names(classes_file, names)
    if skipped:
        logger.warning(
            f"{skipped} shape(s) in {txt_path} cannot be written as {mode}; skipped"
        )
    return names
