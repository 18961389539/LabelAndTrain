"""Active-learning core: uncertainty scoring, per-class threshold
calibration and iteration bookkeeping.

Three ideas live here:

1. **Uncertainty instead of a fixed band.** The legacy ``0.25 <= score <=
   0.45`` rule throws away everything outside the band. :func:`shape_uncertainty`
   turns a score into a continuous ``0..1`` value so images can be *ranked*
   instead of merely filtered.
2. **Per-class thresholds.** A score of 0.4 means different things for a
   well-trained class and a rare one. :func:`calibrate_thresholds` derives an
   ``accept`` / ``review`` pair per class from the score distribution actually
   present in the folder, optionally sharpened by boxes a human already
   confirmed.
3. **Iteration memory.** Each train -> relabel round is appended to
   ``active_learning_history.json`` so the marginal gain of another round can
   be estimated instead of guessed.

The module is intentionally free of Qt imports: everything here is pure data
and can be unit-tested head-less.
"""

from __future__ import annotations

import csv
import json
import os.path as osp
import time

from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils.quality import shape_bbox
from anylabeling.views.labeling.utils.yolo_detect import (
    BOX_SHAPE_TYPES,
    SKIP_LABELS,
    _atomic_write_text,
)

__all__ = [
    "DEFAULT_ACCEPT",
    "DEFAULT_REVIEW",
    "HISTORY_FILENAME",
    "THRESHOLDS_FILENAME",
    "append_iteration",
    "calibrate_thresholds",
    "collect_score_samples",
    "count_annotations",
    "format_iteration_summary",
    "image_uncertainty",
    "load_history",
    "load_thresholds",
    "needs_review",
    "rank_by_uncertainty",
    "read_last_map50",
    "save_thresholds",
    "shape_uncertainty",
    "suggest_next_step",
    "thresholds_for",
    "update_last_iteration",
]

# Fallback thresholds, kept aligned with the legacy low-confidence band so
# behaviour is unchanged until a folder has been calibrated.
DEFAULT_ACCEPT = 0.45
DEFAULT_REVIEW = 0.25

THRESHOLDS_FILENAME = "classes_thresholds.json"
HISTORY_FILENAME = "active_learning_history.json"

MIN_CALIBRATION_SAMPLES = 8
MIN_GAP = 0.03
MIN_MARGIN = 0.05
ACCEPT_QUANTILE = 0.75
REVIEW_QUANTILE = 0.35
CONFIRMED_ACCEPT_QUANTILE = 0.10

# Weight of the worst box when summarising a whole image: a single very
# uncertain box is what makes an image worth opening.
UNCERTAINTY_MAX_WEIGHT = 0.7

STOP_GAIN_RATIO = 0.02
SHARP_DROP_RATIO = 0.5


# --------------------------------------------------------------------------
# shape helpers (accept both raw dicts from JSON and live ``Shape`` objects)
# --------------------------------------------------------------------------
def _shape_label(shape):
    if isinstance(shape, dict):
        label = shape.get("label")
    else:
        label = getattr(shape, "label", None)
    if label is None:
        return ""
    return str(label).strip()


def _shape_score(shape):
    if isinstance(shape, dict):
        score = shape.get("score")
    else:
        score = getattr(shape, "score", None)
    if isinstance(score, bool) or score is None:
        return None
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    return value


def _is_scored_box(shape):
    """True for rectangle-ish shapes that carry a model score."""
    if _shape_score(shape) is None:
        return False
    label = _shape_label(shape)
    if not label or label in SKIP_LABELS:
        return False
    if isinstance(shape, dict):
        shape_type = shape.get("shape_type") or "polygon"
    else:
        shape_type = getattr(shape, "shape_type", "polygon") or "polygon"
    return shape_type in BOX_SHAPE_TYPES


def _clamp(value, low, high):
    return max(low, min(high, value))


def _quantile(sorted_values, q):
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = (len(sorted_values) - 1) * _clamp(q, 0.0, 1.0)
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    fraction = position - low
    return float(
        sorted_values[low]
        + (sorted_values[high] - sorted_values[low]) * fraction
    )


def _largest_gap_threshold(values):
    """Midpoint of the widest gap in the score distribution.

    Returns ``None`` when the distribution is smooth (no natural split), in
    which case callers fall back to pure quantiles.
    """
    ordered = sorted(values)
    if len(ordered) < 4:
        return None
    best_gap = 0.0
    best_index = -1
    for index in range(len(ordered) - 1):
        gap = ordered[index + 1] - ordered[index]
        if gap > best_gap:
            best_gap = gap
            best_index = index
    if best_index < 0 or best_gap < MIN_GAP:
        return None
    return (ordered[best_index] + ordered[best_index + 1]) / 2.0


# --------------------------------------------------------------------------
# uncertainty
# --------------------------------------------------------------------------
def shape_uncertainty(shape, accept=DEFAULT_ACCEPT, review=DEFAULT_REVIEW):
    """Continuous uncertainty in ``[0, 1]`` for a single box.

    0 means "confident enough to auto-accept", 1 means "model is guessing".
    Shapes without a score (drawn or confirmed by a human) are 0.
    """
    score = _shape_score(shape)
    if score is None:
        return 0.0
    if accept <= review:
        accept = review + MIN_MARGIN
    if score >= accept:
        return 0.0
    if score <= review:
        return 1.0
    return (accept - score) / (accept - review)


def image_uncertainty(
    shapes,
    accept=DEFAULT_ACCEPT,
    review=DEFAULT_REVIEW,
    thresholds=None,
):
    """Uncertainty of a whole image.

    Averaging alone hides a single bad box among many good ones, so the worst
    box dominates (70%) and the mean breaks ties (30%).
    """
    values = []
    for shape in shapes or []:
        if thresholds:
            shape_accept, shape_review = thresholds_for(
                _shape_label(shape), thresholds, accept, review
            )
        else:
            shape_accept, shape_review = accept, review
        values.append(shape_uncertainty(shape, shape_accept, shape_review))
    if not values:
        return 0.0
    worst = max(values)
    mean = sum(values) / len(values)
    return UNCERTAINTY_MAX_WEIGHT * worst + (1 - UNCERTAINTY_MAX_WEIGHT) * mean


def needs_review(
    shapes,
    accept=DEFAULT_ACCEPT,
    review=DEFAULT_REVIEW,
    thresholds=None,
):
    """True when at least one box is below the auto-accept threshold."""
    for shape in shapes or []:
        if not _is_scored_box(shape):
            continue
        if thresholds:
            shape_accept, shape_review = thresholds_for(
                _shape_label(shape), thresholds, accept, review
            )
        else:
            shape_accept, shape_review = accept, review
        if shape_uncertainty(shape, shape_accept, shape_review) > 0:
            return True
    return False


def rank_by_uncertainty(
    entries,
    accept=DEFAULT_ACCEPT,
    review=DEFAULT_REVIEW,
    thresholds=None,
    unlabeled_score=1.0,
):
    """Sort ``(path, shapes_or_None)`` pairs by descending uncertainty.

    ``shapes=None`` marks an image that has no label file yet; those are the
    most valuable targets of all, hence ``unlabeled_score`` defaults to 1.
    """
    scored = []
    for path, shapes in entries:
        if shapes is None:
            score = unlabeled_score
        else:
            score = image_uncertainty(
                shapes, accept, review, thresholds
            )
        scored.append((path, score))
    scored.sort(key=lambda item: (-item[1], str(item[0])))
    return scored


# --------------------------------------------------------------------------
# threshold calibration
# --------------------------------------------------------------------------
def collect_score_samples(entries):
    """Gather per-class model scores from ``(data_dict, confirmed)`` pairs.

    ``entries`` is an iterable of ``(label_json_dict, confirmed_bool)``. Boxes
    from confirmed (human-checked) images are kept in a separate bucket
    because they are the only trustworthy signal for the accept threshold.

    Returns ``(class_scores, confirmed_scores)``.
    """
    class_scores = {}
    confirmed_scores = {}
    for data, confirmed in entries:
        if not isinstance(data, dict):
            continue
        for shape in data.get("shapes") or []:
            if not isinstance(shape, dict):
                continue
            if not _is_scored_box(shape):
                continue
            label = _shape_label(shape)
            score = _shape_score(shape)
            class_scores.setdefault(label, []).append(score)
            if confirmed:
                confirmed_scores.setdefault(label, []).append(score)
    return class_scores, confirmed_scores


def calibrate_thresholds(
    class_scores,
    confirmed_scores=None,
    min_samples=MIN_CALIBRATION_SAMPLES,
):
    """Derive per-class ``accept`` / ``review`` thresholds.

    Strategy, in order of preference:
    * accept  <- low quantile of *human-confirmed* scores when enough exist;
    * accept  <- widest-gap split of the distribution when it is bimodal;
    * accept  <- 75th percentile otherwise.
    ``review`` always sits at or below the gap / 35th percentile.
    """
    result = {}
    if not isinstance(class_scores, dict):
        return result
    confirmed_scores = confirmed_scores if isinstance(confirmed_scores, dict) else {}

    global_pool = sorted(
        value
        for values in class_scores.values()
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    )
    global_confirmed = sorted(
        value
        for values in confirmed_scores.values()
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    )

    for label, values in class_scores.items():
        pool = sorted(
            value
            for value in values
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        )
        if not pool:
            continue
        # Small classes borrow the global distribution instead of overfitting
        # to a handful of boxes.
        effective = pool if len(pool) >= min_samples else global_pool
        if not effective:
            continue

        gap = _largest_gap_threshold(effective)

        confirmed_pool = sorted(
            value
            for value in confirmed_scores.get(label) or []
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ) or global_confirmed

        if len(confirmed_pool) >= min_samples:
            accept = _quantile(confirmed_pool, CONFIRMED_ACCEPT_QUANTILE)
        elif gap is not None:
            accept = max(gap, _quantile(effective, ACCEPT_QUANTILE))
        else:
            accept = _quantile(effective, ACCEPT_QUANTILE)

        if gap is not None:
            review = min(gap, _quantile(effective, REVIEW_QUANTILE))
        else:
            review = _quantile(effective, REVIEW_QUANTILE)

        accept = _clamp(accept, 0.10, 0.95)
        review = _clamp(review, 0.03, 0.80)
        if review >= accept - MIN_MARGIN:
            review = max(0.03, accept - MIN_MARGIN)

        result[label] = {
            "accept": round(float(accept), 4),
            "review": round(float(review), 4),
            "samples": len(pool),
        }
    return result


def thresholds_for(label, thresholds, accept=DEFAULT_ACCEPT, review=DEFAULT_REVIEW):
    """Look up ``(accept, review)`` for a label, falling back to defaults."""
    if isinstance(thresholds, dict):
        entry = thresholds.get(label) or thresholds.get(str(label).strip())
        if isinstance(entry, dict):
            try:
                return (
                    float(entry.get("accept", accept)),
                    float(entry.get("review", review)),
                )
            except (TypeError, ValueError):
                pass
    return accept, review


def load_thresholds(directory):
    """Read ``classes_thresholds.json``; ``{}`` when missing or broken."""
    if not directory:
        return {}
    path = osp.join(directory, THRESHOLDS_FILENAME)
    if not osp.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning(f"Active learning: failed to read {path}: {exc}")
        return {}
    if not isinstance(data, dict):
        return {}
    entries = data.get("thresholds")
    return entries if isinstance(entries, dict) else {}


def save_thresholds(directory, thresholds):
    """Persist calibrated thresholds next to ``classes.txt``."""
    if not directory or not isinstance(thresholds, dict):
        return None
    payload = {
        "version": 1,
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "thresholds": thresholds,
    }
    path = osp.join(directory, THRESHOLDS_FILENAME)
    try:
        _atomic_write_text(
            path, json.dumps(payload, ensure_ascii=False, indent=2)
        )
    except OSError as exc:
        logger.warning(f"Active learning: failed to write {path}: {exc}")
        return None
    return path


# --------------------------------------------------------------------------
# iteration history
# --------------------------------------------------------------------------
def _history_path(directory):
    return osp.join(directory, HISTORY_FILENAME)


def _write_history(directory, history):
    path = _history_path(directory)
    try:
        _atomic_write_text(
            path, json.dumps(history, ensure_ascii=False, indent=2)
        )
    except OSError as exc:
        logger.warning(f"Active learning: failed to write {path}: {exc}")
    return history


def load_history(directory):
    """Return ``{"rounds": [...]}`` for a project folder."""
    empty = {"rounds": []}
    if not directory:
        return empty
    path = _history_path(directory)
    if not osp.isfile(path):
        return empty
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning(f"Active learning: failed to read {path}: {exc}")
        return empty
    if not isinstance(data, dict):
        return empty
    rounds = data.get("rounds")
    data["rounds"] = rounds if isinstance(rounds, list) else []
    return data


def append_iteration(directory, **fields):
    """Start a new round and return the updated history."""
    history = load_history(directory)
    rounds = history.setdefault("rounds", [])
    record = {
        "round": len(rounds) + 1,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    record.update({key: value for key, value in fields.items() if value is not None})
    rounds.append(record)
    return _write_history(directory, history)


def update_last_iteration(directory, **fields):
    """Merge extra numbers into the most recent round (e.g. after relabel)."""
    history = load_history(directory)
    rounds = history.setdefault("rounds", [])
    if not rounds:
        return append_iteration(directory, **fields)
    rounds[-1].update(
        {key: value for key, value in fields.items() if value is not None}
    )
    return _write_history(directory, history)


def _round_gain(record, previous=None):
    """Effective new annotations produced by a round."""
    gain = record.get("new_shapes")
    if gain is None and previous is not None:
        gain = (record.get("labeled_images") or 0) - (
            previous.get("labeled_images") or 0
        )
    try:
        return float(gain or 0)
    except (TypeError, ValueError):
        return 0.0


def suggest_next_step(history):
    """Decide whether another train -> relabel round still pays off."""
    rounds = (history or {}).get("rounds") or []
    if len(rounds) < 2:
        return {
            "action": "continue",
            "reason": "迭代轮数不足，继续积累数据后再判断。",
            "suggested_images": None,
            "gain": None,
            "rounds": len(rounds),
        }

    last = rounds[-1]
    previous = rounds[-2]
    gain = _round_gain(last, previous)
    previous_gain = _round_gain(previous)
    total = last.get("total_shapes") or 0
    ratio = (gain / total) if total else 0.0

    suggested = _suggested_image_count(last)

    if gain <= 0:
        return {
            "action": "stop",
            "reason": "本轮没有新增有效标注，继续训练收益很小，建议改补难例或新场景数据。",
            "suggested_images": None,
            "gain": gain,
            "rounds": len(rounds),
        }
    if ratio < STOP_GAIN_RATIO:
        return {
            "action": "stop",
            "reason": (
                f"边际收益仅 {ratio * 100:.1f}%（低于 2%），"
                "模型已趋于饱和，建议停止迭代。"
            ),
            "suggested_images": None,
            "gain": gain,
            "rounds": len(rounds),
        }
    if previous_gain > 0 and gain < previous_gain * SHARP_DROP_RATIO:
        return {
            "action": "stop",
            "reason": (
                f"新增标注从上一轮 {int(previous_gain)} 降到 {int(gain)}，"
                "收益快速衰减，建议转去补充短板类别。"
            ),
            "suggested_images": None,
            "gain": gain,
            "rounds": len(rounds),
        }
    return {
        "action": "continue",
        "reason": (
            f"本轮新增 {int(gain)} 个有效标注（{ratio * 100:.1f}%），"
            f"建议下一轮再标约 {suggested} 张。"
        ),
        "suggested_images": suggested,
        "gain": gain,
        "rounds": len(rounds),
    }


def _suggested_image_count(record):
    reviewed = record.get("reviewed_images")
    if not reviewed:
        reviewed = record.get("labeled_images") or 0
    try:
        value = int(float(reviewed) * 0.8)
    except (TypeError, ValueError):
        return None
    return max(20, value)


def format_iteration_summary(history):
    """Human-readable, one line per round."""
    rounds = (history or {}).get("rounds") or []
    if not rounds:
        return ["还没有迭代记录。训练一次并选择「用于自动标注」后会自动记录。"]

    lines = []
    for record in rounds:
        parts = [f"第 {record.get('round', '?')} 轮"]
        if record.get("timestamp"):
            parts.append(record["timestamp"])
        if record.get("model"):
            parts.append(f"模型 {record['model']}")
        if record.get("map50") is not None:
            parts.append(f"mAP50 {float(record['map50']):.3f}")
        if record.get("labeled_images") is not None:
            parts.append(f"已标注 {record['labeled_images']} 张")
        if record.get("total_shapes") is not None:
            parts.append(f"共 {record['total_shapes']} 个框")
        if record.get("new_shapes") is not None:
            parts.append(f"新增 {record['new_shapes']} 个")
        lines.append(" · ".join(parts))

    suggestion = suggest_next_step(history)
    prefix = "建议停止：" if suggestion["action"] == "stop" else "建议："
    lines.append(f"{prefix}{suggestion['reason']}")
    return lines


def read_last_map50(results_csv):
    """Best-effort read of the final mAP50 from an Ultralytics results.csv."""
    if not results_csv or not osp.isfile(results_csv):
        return None
    try:
        with open(results_csv, "r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            last_row = None
            for row in reader:
                last_row = row
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        logger.warning(f"Active learning: failed to read {results_csv}: {exc}")
        return None
    if not last_row:
        return None
    for key in ("metrics/mAP50(B)", "metrics/mAP50(B)".strip()):
        value = last_row.get(key)
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                break
    for key, value in last_row.items():
        if not key or "mAP50" not in key or "mAP50-95" in key:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def bbox_of(shape):
    """Convenience re-export so callers need not import ``quality`` too."""
    return shape_bbox(shape)


def count_annotations(image_files, label_dir=None):
    """Count labelled images and boxes for a list of images.

    Used before/after a relabel pass to derive ``new_shapes``.
    """
    labeled = 0
    boxes = 0
    for image_file in image_files or []:
        label_file = osp.splitext(image_file)[0] + ".json"
        if label_dir:
            label_file = osp.join(label_dir, osp.basename(label_file))
        if not osp.isfile(label_file):
            continue
        try:
            with open(label_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        labeled += 1
        boxes += len(data.get("shapes") or [])
    return {"labeled_images": labeled, "total_shapes": boxes}
