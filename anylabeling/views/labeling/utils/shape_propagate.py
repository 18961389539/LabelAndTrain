"""Shape propagation between images (L2 interactive intelligence).

Copies annotations from a previous image into the current one, scaling the
coordinates when the two images differ in size. Pure logic: no Qt/UI
dependencies, so it can be unit-tested and reused by other tooling.
"""

from __future__ import annotations

import json
import os.path as osp


def load_shapes_from_file(label_file):
    """Load ``(imageWidth, imageHeight, shapes)`` from a label json file.

    Missing/corrupt files degrade to ``(0, 0, [])`` instead of raising so
    callers can keep going.
    """
    if not label_file or not osp.exists(label_file):
        return 0, 0, []
    try:
        with open(label_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return 0, 0, []
    if not isinstance(data, dict):
        return 0, 0, []
    shapes = data.get("shapes")
    if not isinstance(shapes, list):
        shapes = []
    return (
        int(data.get("imageWidth") or 0),
        int(data.get("imageHeight") or 0),
        [shape for shape in shapes if isinstance(shape, dict)],
    )


def scale_shape(shape, src_w, src_h, dst_w, dst_h):
    """Return a new shape dict with points rescaled into the target size.

    Coordinates are clamped into ``[0, dst_w] x [0, dst_h]``; zero-sized
    dimensions fall back to an identity scale on that axis.
    """
    sx = (dst_w / src_w) if src_w > 0 and dst_w > 0 else 1.0
    sy = (dst_h / src_h) if src_h > 0 and dst_h > 0 else 1.0
    new_points = []
    for point in shape.get("points") or []:
        try:
            x, y = float(point[0]), float(point[1])
        except (TypeError, IndexError, ValueError):
            continue
        if dst_w > 0:
            x = max(0.0, min(x * sx, float(dst_w)))
        if dst_h > 0:
            y = max(0.0, min(y * sy, float(dst_h)))
        new_points.append([x, y])
    new_shape = {key: value for key, value in shape.items() if key != "points"}
    new_shape["points"] = new_points
    if not new_shape.get("shape_type"):
        new_shape["shape_type"] = "rectangle"
    return new_shape


def bbox_signature(shape, img_w, img_h):
    """Normalized, rounded bounding box used to detect duplicate shapes."""
    points = shape.get("points") or []
    xs = [
        p[0]
        for p in points
        if isinstance(p, (list, tuple)) and len(p) >= 2
    ]
    ys = [
        p[1]
        for p in points
        if isinstance(p, (list, tuple)) and len(p) >= 2
    ]
    if not xs or not ys:
        return ("", (0, 0, 0, 0))
    if img_w > 0 and img_h > 0:
        norm = (
            round(min(xs) / img_w, 2),
            round(min(ys) / img_h, 2),
            round(max(xs) / img_w, 2),
            round(max(ys) / img_h, 2),
        )
    else:
        norm = (round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1))
    return (shape.get("label") or "", norm)


def propagate_labels(prev_file, prev_size, dst_w, dst_h, existing_shapes=None):
    """Plan shapes copied from ``prev_file`` into the current image.

    Args:
        prev_file: Label json to copy from.
        prev_size: ``(w, h)`` of the source image; overrides the size stored
            in the file (useful when the source image is not the file yet).
        dst_w/dst_h: Size of the target image.
        existing_shapes: Iterable of shape dicts already on the target; any
            planned shape whose label+normalized bbox already exists there is
            skipped so propagation never duplicates objects.

    Returns:
        List of new shape dicts (already scaled/clamped to the target size).
    """
    src_w, src_h, shapes = load_shapes_from_file(prev_file)
    if prev_size:
        src_w, src_h = prev_size
    if dst_w <= 0 or dst_h <= 0 or src_w <= 0 or src_h <= 0:
        return []

    seen = set()
    for shape in existing_shapes or []:
        seen.add(bbox_signature(shape, dst_w, dst_h))

    planned = []
    for shape in shapes:
        scaled = scale_shape(shape, src_w, src_h, dst_w, dst_h)
        if not scaled["points"]:
            continue
        signature = bbox_signature(scaled, dst_w, dst_h)
        if signature in seen:
            continue
        seen.add(signature)
        planned.append(scaled)
    return planned


# --------------------------------------------------------------------------
# smart template selection (dhash similarity)
# --------------------------------------------------------------------------
#: Max dhash Hamming distance (out of 64 bits) before a candidate is
#: considered "not the same scene" and rejected.
TEMPLATE_MAX_DISTANCE = 10


def _image_size(path):
    """``(w, h)`` of an image via Pillow, or ``None`` when unreadable."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is a runtime dependency
        return None
    try:
        with Image.open(path) as image:
            return image.size
    except Exception:  # noqa: BLE001
        return None


def template_candidates(target_path, labeled_paths, top_k=None):
    """Rank labeled images by visual similarity to ``target_path``.

    Uses the same 64-bit dhash as the duplicate scanner. Unreadable images
    are skipped. Returns a list of ``(path, distance)`` sorted by distance;
    only matches at or below :data:`TEMPLATE_MAX_DISTANCE` are returned.
    """
    from anylabeling.views.labeling.utils.data_intel import (
        hamming_distance,
        image_dhash,
    )

    target_hash = image_dhash(target_path)
    if target_hash is None:
        return []
    matches = []
    for path in labeled_paths:
        candidate_hash = image_dhash(path)
        if candidate_hash is None:
            continue
        distance = hamming_distance(target_hash, candidate_hash)
        if distance <= TEMPLATE_MAX_DISTANCE:
            matches.append((path, distance))
    matches.sort(key=lambda item: (item[1], item[0]))
    if top_k is not None:
        matches = matches[:top_k]
    return matches


def plan_template_propagation(label_dir, targets, templates, progress=None):
    """Plan pre-labels for unlabeled images by template matching.

    Args:
        label_dir: Folder holding the ``.json`` label files.
        targets: Unlabeled image paths to pre-label.
        templates: Labeled image paths to copy from.
        progress: Optional ``(done, total)`` callback for UI feedback.

    Returns:
        List of dicts: ``{"target", "template", "distance", "label_file",
        "shapes"}`` where ``shapes`` are already scaled/clamped to the target
        and de-duplicated against whatever the target json already holds.
    """
    from anylabeling.views.labeling.utils.data_intel import image_dhash

    template_hashes = {}
    for template in templates:
        image_hash = image_dhash(template)
        if image_hash is not None:
            template_hashes[template] = image_hash

    plan = []
    total = max(1, len(targets))
    for index, target in enumerate(targets, start=1):
        if callable(progress):
            progress(index, total)
        target_hash = image_dhash(target)
        if target_hash is None or not template_hashes:
            continue
        best_path, best_hash = min(
            template_hashes.items(),
            key=lambda item: (_hamming(target_hash, item[1]), item[0]),
        )
        distance = _hamming(target_hash, best_hash)
        if distance > TEMPLATE_MAX_DISTANCE:
            continue

        template_json = osp.join(
            label_dir, osp.splitext(osp.basename(best_path))[0] + ".json"
        )
        target_json = osp.join(
            label_dir, osp.splitext(osp.basename(target))[0] + ".json"
        )
        target_size = _image_size(target)
        if target_size is None or target_size[0] <= 0 or target_size[1] <= 0:
            continue
        existing = load_shapes_from_file(target_json)[2]
        planned = propagate_labels(
            template_json, None, target_size[0], target_size[1], existing
        )
        if planned:
            plan.append(
                {
                    "target": target,
                    "template": best_path,
                    "distance": distance,
                    "label_file": target_json,
                    "shapes": planned,
                }
            )
    return plan


def _hamming(first, second):
    return bin((first ^ second) & 0xFFFFFFFFFFFFFFFF).count("1")
