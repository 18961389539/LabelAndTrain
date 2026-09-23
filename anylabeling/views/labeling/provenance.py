"""Provenance of a shape: who drew it, and with which model.

Shapes carry ``source`` (``human`` / ``model`` / ``unknown``) plus the model
name that produced them. Older label files have neither, so anything reading
these fields must treat a missing ``source`` as ``unknown`` rather than as a
human box -- otherwise a cleanup pass could delete work nobody claimed.
"""

import os.path as osp

SOURCE_HUMAN = "human"
SOURCE_MODEL = "model"
SOURCE_UNKNOWN = "unknown"
SOURCES = (SOURCE_HUMAN, SOURCE_MODEL, SOURCE_UNKNOWN)

SOURCE_FIELD = "source"
MODEL_FIELD = "model"


def get_source(shape):
    """Read the source of a ``Shape`` or a plain dict payload."""
    if isinstance(shape, dict):
        value = shape.get(SOURCE_FIELD)
    else:
        value = getattr(shape, SOURCE_FIELD, None)
    return value if value in SOURCES else SOURCE_UNKNOWN


def model_of(shape):
    if isinstance(shape, dict):
        return shape.get(MODEL_FIELD)
    return getattr(shape, MODEL_FIELD, None)


def stamp_model_shapes(shapes, model_name):
    """Attribute freshly produced shapes to ``model_name``.

    Callers pass only what a model just returned, so this overwrites the
    ``human`` default a programmatically built ``Shape`` carries. Never call
    it on shapes loaded from disk: those already carry their own history.
    """
    for shape in shapes or []:
        if isinstance(shape, dict):
            shape[SOURCE_FIELD] = SOURCE_MODEL
            shape[MODEL_FIELD] = model_name
        else:
            setattr(shape, SOURCE_FIELD, SOURCE_MODEL)
            setattr(shape, MODEL_FIELD, model_name)
    return len(shapes or [])


def is_from_other_model(shape, current_model_name):
    """A model box that the currently loaded model did not produce."""
    if get_source(shape) != SOURCE_MODEL:
        return False
    producer = model_of(shape) or SOURCE_UNKNOWN
    return producer != current_model_name


def is_deletable_stale_shape(shape, current_model_name):
    """Stale model box that neither a lock nor human work protects.

    ``locked`` shapes and anything not explicitly attributed to another model
    are never deletable here: a hand-corrected box still carries the old
    model's name, and silently removing it would destroy the correction.
    """
    if isinstance(shape, dict):
        if shape.get("locked"):
            return False
    elif getattr(shape, "locked", False):
        return False
    return is_from_other_model(shape, current_model_name)


def collect_other_model_shapes(label_data, current_model_name):
    """Return ``(index, payload)`` for stale model boxes in one label dict."""
    stale = []
    for index, shape in enumerate(label_data.get("shapes") or []):
        if is_from_other_model(shape, current_model_name):
            stale.append((index, shape))
    return stale


def shape_points(shape):
    """Points of a ``Shape`` or a dict payload, as ``(x, y)`` tuples."""
    if isinstance(shape, dict):
        return [
            (point[0], point[1])
            for point in shape.get("points") or []
            if isinstance(point, (list, tuple)) and len(point) >= 2
        ]
    return [
        (point.x(), point.y())
        for point in getattr(shape, "points", [])
        if hasattr(point, "x")
    ]


def shape_marker(shape):
    """Identity of a box: its label plus rounded geometry.

    Report rows carry this so a later deletion can honour it: a box that was
    moved or relabelled between reporting and deleting no longer matches, and is
    skipped rather than removed. Works on both the dict payloads read from disk
    and the ``Shape`` objects held by the canvas.
    """
    points = shape_points(shape)
    if not points:
        return None
    if isinstance(shape, dict):
        label = shape.get("label")
    else:
        label = getattr(shape, "label", None)
    return (
        str(label or ""),
        tuple((round(float(x), 2), round(float(y), 2)) for x, y in points),
    )


def describe_shape(shape):
    """Short human-readable summary used by the stale-shape report rows."""
    label = ""
    score = None
    if isinstance(shape, dict):
        label = shape.get("label") or ""
        score = shape.get("score")
    else:
        label = getattr(shape, "label", "") or ""
        score = getattr(shape, "score", None)
    points = shape_points(shape)
    width = height = None
    if len(points) >= 2:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
    parts = []
    if width is not None:
        parts.append(f"{int(round(width))}x{int(round(height))}")
    if score is not None:
        parts.append(f"置信度 {score:.2f}")
    return label, " · ".join(parts)


def model_display_name(model_config):
    """Best available identity for the currently loaded model."""
    if not model_config:
        return None
    name = model_config.get("display_name") or model_config.get("name")
    if not name and model_config.get("model_path"):
        name = osp.basename(model_config["model_path"])
    return name
