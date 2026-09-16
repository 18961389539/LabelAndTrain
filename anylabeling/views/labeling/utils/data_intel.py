"""Dataset intelligence helpers.

Complements :mod:`data_audit` (which answers "is the dataset consistent?")
with the questions that actually move model quality:

* **missing annotations** - boxes the model is confident about but nobody
  labelled (:func:`find_missing_predictions`);
* **near-duplicates** - perceptual-hash groups that inflate the apparent
  dataset size and leak between train/val (:func:`find_duplicate_groups`);
* **hard examples** - images ranked by uncertainty so review time is spent
  where it changes the model most (:func:`mine_hard_examples`);
* **distribution & balancing** - class / scale / aspect-ratio statistics plus
  concrete, actionable advice (:func:`analyze_distribution`,
  :func:`suggest_balancing`).

Only :func:`image_dhash` needs Pillow, and it imports it lazily so the rest of
the module stays testable in a bare environment.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils.active_learning import (
    DEFAULT_ACCEPT,
    DEFAULT_REVIEW,
    _shape_label,
    _shape_score,
    image_uncertainty,
)
from anylabeling.views.labeling.utils.quality import shape_bbox
from anylabeling.views.labeling.utils.yolo_detect import (
    BOX_SHAPE_TYPES,
    SKIP_LABELS,
)

__all__ = [
    "analyze_distribution",
    "box_iou",
    "find_duplicate_groups",
    "find_missing_predictions",
    "hamming_distance",
    "image_dhash",
    "mine_hard_examples",
    "suggest_balancing",
]

# COCO-style absolute pixel buckets.
SMALL_AREA = 32 * 32
LARGE_AREA = 96 * 96

EXTREME_ASPECT_RATIO = 5.0
IMBALANCE_RATIO = 10.0
IMBALANCE_MIN_MAJORITY = 20
SMALL_OBJECT_WARN_RATIO = 0.5
EXTREME_ASPECT_WARN_RATIO = 0.2
NEGATIVE_WARN_RATIO = 0.2
MIN_IMAGES_HINT = 300

DEFAULT_HASH_SIZE = 8
DEFAULT_HASH_DISTANCE = 6


def _box_of(shape):
    return shape_bbox(shape)


def _is_countable(shape):
    label = _shape_label(shape)
    if not label or label in SKIP_LABELS:
        return False
    if isinstance(shape, dict):
        shape_type = shape.get("shape_type") or "polygon"
    else:
        shape_type = getattr(shape, "shape_type", "polygon") or "polygon"
    return shape_type in BOX_SHAPE_TYPES


# --------------------------------------------------------------------------
# missing annotations
# --------------------------------------------------------------------------
def box_iou(box_a, box_b):
    """IoU of two ``(xmin, ymin, xmax, ymax)`` tuples."""
    if not box_a or not box_b:
        return 0.0
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = inter_x2 - inter_x1
    inter_h = inter_y2 - inter_y1
    if inter_w <= 0 or inter_h <= 0:
        return 0.0
    inter = inter_w * inter_h
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def find_missing_predictions(
    predictions,
    annotations,
    iou_threshold=0.5,
    min_score=DEFAULT_ACCEPT,
    match_same_label=True,
):
    """Predictions with no matching ground-truth box.

    A high-scoring prediction that overlaps nothing in the label file is the
    classic "forgot to label this" case.

    Args:
        predictions: model output shapes (dicts or ``Shape`` objects).
        annotations: shapes already stored in the label json.
        iou_threshold: minimum overlap to consider a prediction matched.
        min_score: ignore predictions below this confidence.
        match_same_label: when True a prediction only matches a box of the
            same label (recommended for multi-class datasets).

    Returns:
        list of prediction objects that look like missed annotations.
    """
    annotation_items = []
    for shape in annotations or []:
        if not _is_countable(shape):
            continue
        box = _box_of(shape)
        if box is None:
            continue
        annotation_items.append((box, _shape_label(shape)))

    missing = []
    for shape in predictions or []:
        if not _is_countable(shape):
            continue
        score = _shape_score(shape)
        if score is None or score < min_score:
            continue
        box = _box_of(shape)
        if box is None:
            continue
        label = _shape_label(shape)
        matched = False
        for other_box, other_label in annotation_items:
            if match_same_label and other_label != label:
                continue
            if box_iou(box, other_box) >= iou_threshold:
                matched = True
                break
        if not matched:
            missing.append(shape)
    return missing


# --------------------------------------------------------------------------
# near-duplicate detection
# --------------------------------------------------------------------------
def image_dhash(image_path, hash_size=DEFAULT_HASH_SIZE):
    """64-bit difference hash, or ``None`` when the image cannot be read."""
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is a runtime dependency
        logger.warning("data_intel: Pillow is unavailable, skipping hashing")
        return None
    try:
        with Image.open(image_path) as image:
            grayscale = image.convert("L").resize(
                (hash_size + 1, hash_size), Image.Resampling.LANCZOS
            )
            pixels = list(grayscale.tobytes())
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"data_intel: cannot hash {image_path}: {exc}")
        return None

    value = 0
    width = hash_size + 1
    for row in range(hash_size):
        for column in range(hash_size):
            left = pixels[row * width + column]
            right = pixels[row * width + column + 1]
            value = (value << 1) | (1 if left > right else 0)
    return value


def hamming_distance(first, second):
    return bin((first ^ second) & 0xFFFFFFFFFFFFFFFF).count("1")


def find_duplicate_groups(
    image_paths,
    hash_size=DEFAULT_HASH_SIZE,
    max_distance=DEFAULT_HASH_DISTANCE,
    progress=None,
):
    """Group visually near-identical images.

    Simple union-find over pairwise Hamming distance. ``max_distance`` of 6
    out of 64 bits is a good default: it catches re-encoded copies and
    consecutive video frames while leaving genuinely different shots alone.

    Returns a list of groups (each with 2+ paths), largest first.
    """
    hashes = {}
    for index, path in enumerate(image_paths or []):
        digest = image_dhash(path, hash_size)
        if digest is not None:
            hashes[path] = digest
        if progress is not None:
            progress(index + 1, len(image_paths))

    paths = list(hashes)
    if len(paths) < 2:
        return []

    parent = {path: path for path in paths}

    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(first, second):
        root_first, root_second = find(first), find(second)
        if root_first != root_second:
            parent[root_second] = root_first

    for index in range(len(paths)):
        for other in range(index + 1, len(paths)):
            if (
                hamming_distance(hashes[paths[index]], hashes[paths[other]])
                <= max_distance
            ):
                union(paths[index], paths[other])

    groups = defaultdict(list)
    for path in paths:
        groups[find(path)].append(path)

    result = [sorted(group) for group in groups.values() if len(group) > 1]
    result.sort(key=lambda group: (-len(group), group[0]))
    return result


# --------------------------------------------------------------------------
# hard-example mining
# --------------------------------------------------------------------------
def mine_hard_examples(
    entries,
    thresholds=None,
    accept=DEFAULT_ACCEPT,
    review=DEFAULT_REVIEW,
    top_k=50,
    min_uncertainty=0.15,
):
    """Rank images by uncertainty and keep the top ``top_k``.

    ``entries`` is an iterable of ``(path, shapes_or_None)``; ``None`` means
    the image has no label file and therefore counts as maximally uncertain.
    """
    scored = []
    for path, shapes in entries:
        if shapes is None:
            score = 1.0
        else:
            score = image_uncertainty(shapes, accept, review, thresholds)
        if score >= min_uncertainty:
            scored.append((path, score))
    scored.sort(key=lambda item: (-item[1], str(item[0])))
    if top_k and top_k > 0:
        return scored[:top_k]
    return scored


# --------------------------------------------------------------------------
# distribution & balancing
# --------------------------------------------------------------------------
def analyze_distribution(entries):
    """Summarise a dataset.

    ``entries`` is an iterable of ``(image_path, data_or_None)`` where
    ``data`` is the parsed label json (``None`` = not labelled yet).
    """
    total_images = 0
    labeled_images = 0
    negative_images = 0
    missing_json = 0
    total_shapes = 0
    class_counts = Counter()
    buckets = {"small": 0, "medium": 0, "large": 0}
    extreme_aspect = 0
    objects_per_image = []

    for _path, data in entries:
        total_images += 1
        if not isinstance(data, dict):
            missing_json += 1
            continue
        shapes = data.get("shapes") or []
        labeled_images += 1
        if not shapes:
            negative_images += 1
            objects_per_image.append(0)
            continue

        count = 0
        for shape in shapes:
            if not isinstance(shape, dict) or not _is_countable(shape):
                continue
            box = shape_bbox(shape)
            if box is None:
                continue
            count += 1
            total_shapes += 1
            class_counts[_shape_label(shape)] += 1

            xmin, ymin, xmax, ymax = box
            width = max(0.0, xmax - xmin)
            height = max(0.0, ymax - ymin)
            area = width * height
            if area < SMALL_AREA:
                buckets["small"] += 1
            elif area < LARGE_AREA:
                buckets["medium"] += 1
            else:
                buckets["large"] += 1

            if height > 0:
                ratio = width / height
                if (
                    ratio > EXTREME_ASPECT_RATIO
                    or ratio < 1.0 / EXTREME_ASPECT_RATIO
                ):
                    extreme_aspect += 1
        objects_per_image.append(count)

    avg_objects = (
        sum(objects_per_image) / len(objects_per_image)
        if objects_per_image
        else 0.0
    )
    return {
        "total_images": total_images,
        "labeled_images": labeled_images,
        "negative_images": negative_images,
        "missing_json": missing_json,
        "total_shapes": total_shapes,
        "class_counts": dict(class_counts),
        "area_buckets": buckets,
        "extreme_aspect": extreme_aspect,
        "objects_per_image": {
            "avg": round(avg_objects, 2),
            "max": max(objects_per_image) if objects_per_image else 0,
        },
    }


def suggest_balancing(stats):
    """Turn distribution statistics into concrete next actions."""
    if not isinstance(stats, dict) or not stats:
        return []

    suggestions = []
    class_counts = stats.get("class_counts") or {}
    total_shapes = stats.get("total_shapes") or 0
    total_images = stats.get("total_images") or 0

    if class_counts:
        majority_label, majority = max(
            class_counts.items(), key=lambda item: item[1]
        )
        if majority >= IMBALANCE_MIN_MAJORITY:
            minority_label, minority = min(
                class_counts.items(), key=lambda item: item[1]
            )
            if minority_label != majority_label and majority >= max(
                minority, 1
            ) * IMBALANCE_RATIO:
                suggestions.append(
                    f"类别严重失衡：「{minority_label}」只有 {minority} 个，"
                    f"而「{majority_label}」有 {majority} 个。"
                    f"建议再补「{minority_label}」约 "
                    f"{max(majority // 2 - minority, 20)} 个样本，"
                    f"或训练时开启类别权重/过采样。"
                )
        if total_shapes:
            per_class_avg = total_shapes / len(class_counts)
            thin = [
                f"{label}({count})"
                for label, count in sorted(
                    class_counts.items(), key=lambda item: item[1]
                )
                if count < per_class_avg * 0.3
            ]
            if thin and len(thin) <= 6:
                suggestions.append(
                    "样本偏少的类别：" + "、".join(thin) + "，优先补充这几类。"
                )

    buckets = stats.get("area_buckets") or {}
    small = buckets.get("small") or 0
    if total_shapes and small / total_shapes >= SMALL_OBJECT_WARN_RATIO:
        suggestions.append(
            f"小目标占比 {small / total_shapes * 100:.0f}%（{small}/{total_shapes}）。"
            f"建议训练 imgsz 提到 960 或 1280，并开启 copy-paste 增强；"
            f"标注时不要直接丢弃小目标。"
        )

    if total_shapes:
        extreme_ratio = (stats.get("extreme_aspect") or 0) / total_shapes
        if extreme_ratio >= EXTREME_ASPECT_WARN_RATIO:
            suggestions.append(
                f"极端长宽比（>{EXTREME_ASPECT_RATIO:.0f}:1）的框占 "
                f"{extreme_ratio * 100:.0f}%，建议确认是目标本身的形状还是标注习惯问题。"
            )

    labeled = stats.get("labeled_images") or 0
    negative = stats.get("negative_images") or 0
    if labeled and negative / labeled > NEGATIVE_WARN_RATIO:
        suggestions.append(
            f"负样本（空标注）占比 {negative / labeled * 100:.0f}%"
            f"（{negative}/{labeled}）。YOLO 需要一定负样本，但超过 20% 会稀释正样本，"
            f"建议控制在 5%~20%。"
        )

    missing = stats.get("missing_json") or 0
    if missing:
        suggestions.append(
            f"还有 {missing} 张图片没有标注文件，完成它们再训练效果更稳。"
        )

    if 0 < total_images < MIN_IMAGES_HINT:
        suggestions.append(
            f"图片总量仅 {total_images} 张，偏少；一般建议每类至少 200~300 个实例。"
        )

    if not suggestions:
        suggestions.append("分布未见明显问题，可以进入下一轮训练。")
    return suggestions
