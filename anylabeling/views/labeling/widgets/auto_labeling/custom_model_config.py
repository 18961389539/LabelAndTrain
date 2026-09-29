"""Derive a YOLO custom-model config from ONNX weights.

Split out of auto_labeling.py (batch 9): eleven module-level functions
that classify an ``.onnx`` file, read or derive its class names, and
write the custom-model yaml.  They are pure helpers -- the only Qt they
touch is ``Qt.ItemDataRole`` while reading the Labels dock -- so they
move verbatim with no transform, and auto_labeling.py imports the names
back, which keeps every call site *and*
``tests/test_auto_labeling/test_custom_class_names.py`` working unchanged.
"""

import os
import re
import yaml
from pathlib import Path

from PyQt6.QtCore import Qt

from anylabeling.config import get_work_directory
from anylabeling.services.auto_labeling.types import AutoLabelingMode
from anylabeling.views.labeling.logger import logger

_UNNAMED_CLASS = "unname"
_PLACEHOLDER_CLASS_RE = re.compile(r"^class_\d+$")
_SKIP_UNIQUE_LABELS = {
    AutoLabelingMode.OBJECT,
    AutoLabelingMode.ADD,
    AutoLabelingMode.REMOVE,
}


def _infer_custom_model_type(stem: str) -> str:
    s = stem.lower()
    if "pose" in s:
        return "yolo26_pose"
    # SAM hints must be checked BEFORE the generic "seg"/"segment" rule,
    # otherwise files like "segment_anything_2" are mis-classified as
    # yolov8_seg.
    if "sam2" in s or "sam_" in s or "segment_anything" in s:
        return "segment_anything_2"
    if "seg" in s:
        return "yolov8_seg"
    return "yolov8"


def _safe_custom_model_name(stem: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", stem or "")
    text = text.strip("._-") or "custom_model"
    return text[:80]


def _classify_yolo_onnx(weights_path: str):
    """Classify an ``.onnx`` file into a concrete supported model type.

    The YOLO runtime dispatch in this app depends on the yaml ``type``:

    - ``yolov8`` family  → ``non_max_suppression_v8`` (anchor-grid decode +
      NMS in the app). Export outputs carry a large grid axis (e.g. 8400).
    - ``yolo26`` family  → ``non_max_suppression_end2end`` (NMS is already
      baked into the export). Outputs are flat end-to-end boxes/scores.

    So "which YOLO is it" is NOT cosmetic: the wrong family decodes
    garbage. This helper inspects the graph's outputs/metadata (no
    inference) and returns the exact type to put in the yaml, or ``None``
    when it cannot be determined (caller then keeps the filename hint):

    - ``kpt_shape`` metadata            → pose. Only the end-to-end pose
      (``yolo26_pose``) is supported here, so a *classic* (grid) pose
      export cannot be mapped → ``None``.
    - a 4-D output (proto/mask head)    → seg: classic grid → ``yolov8_seg``,
      end-to-end → ``yolo26_seg``.
    - a large grid axis (>= 1000)       → classic detection → ``yolov8``.
    - otherwise flat outputs            → end-to-end detection → ``yolo26``.
    """
    try:
        import onnxruntime as ort

        sess_options = ort.SessionOptions()
        sess_options.log_severity_level = 3
        sess_options.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        )
        session = ort.InferenceSession(
            weights_path,
            sess_options,
            providers=["CPUExecutionProvider"],
        )
        meta = session.get_modelmeta().custom_metadata_map or {}
        has_kpt = any("kpt_shape" in key.lower() for key in meta)

        def _dims(shape):
            return [d for d in shape if isinstance(d, int) and d > 0]

        shapes = [_dims(o.shape) for o in session.get_outputs()]
        has_grid = any(
            dims and max(dims) >= 1000 for dims in shapes
        )  # e.g. anchor-axis 8400 / 25200
        has_4d = any(len(dims) == 4 for dims in shapes)  # proto/mask head

        if has_kpt:
            # Only end-to-end pose decode (yolo26_pose) is whitelisted.
            return "yolo26_pose" if not has_grid else None
        if has_4d:
            return "yolov8_seg" if has_grid else "yolo26_seg"
        if has_grid:
            return "yolov8"
        return "yolo26"
    except Exception:  # noqa: BLE001
        return None


def _parse_ultralytics_names(raw):
    """Parse the ``names`` field Ultralytics writes into ONNX metadata.

    The value is usually a Python dict repr like ``"{'person': 0, 'cat': 1}"``
    (single quotes, single-line), but it can also be JSON, or already be a
    list. Returns a list of names ordered by their integer index, or
    ``None`` if the format cannot be recognised.
    """
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)) and all(isinstance(s, str) for s in raw):
        return list(raw)
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    # Normalise common single-quoted Python repr to JSON-friendly.
    if text.startswith("{") and text.endswith("}"):
        try:
            import ast

            obj = ast.literal_eval(text)
            if isinstance(obj, dict):
                names = [None] * len(obj)
                for name, index in obj.items():
                    try:
                        names[int(index)] = str(name)
                    except (ValueError, IndexError):
                        return None
                if any(n is None for n in names):
                    return None
                return names
        except (ValueError, SyntaxError):
            pass
        try:
            import json

            obj = json.loads(text)
            if isinstance(obj, dict):
                names = [None] * len(obj)
                for name, index in obj.items():
                    try:
                        names[int(index)] = str(name)
                    except (ValueError, IndexError):
                        return None
                if any(n is None for n in names):
                    return None
                return names
        except json.JSONDecodeError:
            return None
    if text.startswith("["):
        try:
            import ast

            obj = ast.literal_eval(text)
            if isinstance(obj, list):
                return [str(n) for n in obj]
        except (ValueError, SyntaxError):
            pass
        try:
            import json

            obj = json.loads(text)
            if isinstance(obj, list):
                return [str(n) for n in obj]
        except json.JSONDecodeError:
            return None
    return None


def _derive_nc_from_outputs(model_type, shapes, has_grid):
    """Guess ``nc`` (class count) from ONNX output shapes.

    Returns ``nc`` as a positive int, or ``None`` if it cannot be
    determined. Handles classic v8 / classic seg / E2E variants and the
    yolo26 family.
    """
    # Most outputs: 3D (classic) [1, 4+nc+nm, N] or 2D (e2e) [1, 300, 4+nc+nm]
    for dims in shapes:
        if not dims:
            continue
        n = len(dims)
        if n == 3 and has_grid:
            # classic det/seg/pose output axis
            c = dims[1]
            if c <= 4:
                continue  # not enough channels to be a useful output
            if model_type in ("yolov8_seg", "yolo26_seg"):
                nm = 32  # default Ultralytics seg mask-coeff count
                nc = c - 4 - nm
                if nc > 0:
                    return nc
            else:  # det / pose classic
                nc = c - 4
                if nc > 0:
                    return nc
        elif n == 2:
            # E2E: [1, 300, 4+nc] (or 4+nc+nm for seg)
            c = dims[2] if len(dims) >= 3 else None
            if c is not None and c > 4:
                if model_type in ("yolov8_seg", "yolo26_seg"):
                    nm = 32
                    nc = c - 4 - nm
                else:
                    nc = c - 4
                if nc > 0:
                    return nc
    return None


def _extract_class_names_from_onnx(weights_path, model_type):
    """Return a list of class names for a custom model, sourced from the
    ONNX metadata when available, otherwise derived from output shapes.

    Returns a 3-tuple ``(names, source, nc)`` where ``source`` is one of
    ``"metadata"`` / ``"shape"`` / ``"none"``. The list is always sized
    to match the actual class count (or empty if nothing could be
    determined).
    """
    try:
        import onnx
    except Exception:  # noqa: BLE001
        return [], "none", None

    try:
        model = onnx.load(weights_path)
    except Exception:  # noqa: BLE001
        return [], "none", None

    # 1) Ultralytics writes "names" into custom metadata props.
    for prop in model.metadata_props:
        if prop.key == "names":
            parsed = _parse_ultralytics_names(prop.value)
            if parsed is not None:
                return parsed, "metadata", len(parsed)

    # 2) Fall back to reading the output shapes to derive nc.
    shapes = []
    for o in model.graph.output:
        if o.type.tensor_type.shape:
            shapes.append(
                [
                    d.dim_value
                    for d in o.type.tensor_type.shape.dim
                    if isinstance(d.dim_value, int) and d.dim_value > 0
                ]
            )
    has_grid = any(s and max(s) >= 1000 for s in shapes)
    nc = _derive_nc_from_outputs(model_type, shapes, has_grid)
    if nc and nc > 0:
        return [f"class_{i}" for i in range(nc)], "shape", nc

    return [], "none", None


def _first_user_label(labels):
    """Return the first real class name from a label-list sequence."""
    if not labels:
        return None
    for name in labels:
        if name is None:
            continue
        text = str(name).strip()
        if not text or text in _SKIP_UNIQUE_LABELS:
            continue
        return text
    return None


def _labels_from_parent(parent):
    """Collect class names from the Labels dock, then from saved config."""
    labels = []
    unique_list = (
        getattr(parent, "unique_label_list", None) if parent else None
    )
    if unique_list is not None:
        try:
            count = unique_list.count()
        except Exception:  # noqa: BLE001
            count = 0
        for row in range(count):
            item = unique_list.item(row)
            if item is None:
                continue
            labels.append(item.data(Qt.ItemDataRole.UserRole))
    first = _first_user_label(labels)
    if first:
        return labels
    config = getattr(parent, "_config", None) if parent else None
    if isinstance(config, dict):
        return list(config.get("labels") or [])
    return labels


def _classes_need_name_fallback(classes) -> bool:
    """True when names came from placeholders rather than model metadata."""
    if isinstance(classes, dict):
        return False
    if not classes:
        return False
    for name in classes:
        text = "" if name is None else str(name).strip()
        if not text:
            continue
        if text == _UNNAMED_CLASS:
            continue
        if _PLACEHOLDER_CLASS_RE.fullmatch(text):
            continue
        return False
    return True


def _resolve_custom_model_classes(classes, source, nc, first_label):
    """Replace missing ONNX ``names`` with the first Labels-dock class.

    Metadata names are kept. Otherwise every class id uses the first
    label in the list, or ``unname`` when the list is empty.
    """
    if source == "metadata" and classes:
        return list(classes), "metadata"
    name = _first_user_label([first_label]) if first_label else None
    if name:
        resolved_source = "label_list"
    else:
        name = _UNNAMED_CLASS
        resolved_source = "unname"
    if isinstance(nc, int) and nc > 0:
        count = nc
    elif classes:
        count = len(classes)
    else:
        count = 1
    return [name] * count, resolved_source


def _build_custom_model_yaml_from_weights(
    weights_path: str, fallback_label: str | None = None
) -> str:
    """Create a custom-model yaml pointing at ``weights_path``.

    The user is allowed to pick an ``.onnx`` weights file directly from the
    file dialog (custom models are ONNX-only); this helper materialises the yaml that ``ModelManager.load_custom_model`` requires
    and writes it under ``<work_dir>/custom_models/`` so it survives
    restart and participates in the existing custom-models list/eviction
    logic.

    The yaml ``type`` starts from the filename hint and is then refined
    against the real ONNX graph when the file is ``.onnx`` and the hint is
    not SAM2: ``_classify_yolo_onnx`` returns the exact supported type
    (family + task), so both "yolov8 vs yolo26" and "det vs seg vs pose"
    are decided by the model itself, not by the filename.
    """
    weights_abs = os.path.abspath(weights_path)
    weights = Path(weights_abs)
    if not weights.is_file():
        raise FileNotFoundError(f"Model file not found: {weights_abs}")

    try:
        work_dir = get_work_directory()
    except Exception:
        work_dir = os.path.dirname(weights_abs) or "."

    custom_dir = os.path.join(work_dir, "custom_models")
    os.makedirs(custom_dir, exist_ok=True)

    name = _safe_custom_model_name(weights.stem)

    type_hint = _infer_custom_model_type(weights.stem)
    model_type = type_hint
    if weights.suffix.lower() == ".onnx" and type_hint != "segment_anything_2":
        # Prefer ground truth from the graph over filename guessing.
        classified = _classify_yolo_onnx(weights_abs)
        if classified:
            model_type = classified
            if model_type != type_hint:
                logger.info(
                    f"Custom-model type refined for {weights.name}: "
                    f"{type_hint} → {model_type} (from ONNX graph analysis)"
                )

    # Read or derive class names. Seg models reject empty classes (nc=0)
    # at decode time, so an auto-generated yaml must include a non-empty
    # ``classes`` list whenever we can.
    classes, classes_source, nc = _extract_class_names_from_onnx(
        weights_abs, model_type
    )
    classes, classes_source = _resolve_custom_model_classes(
        classes, classes_source, nc, fallback_label
    )
    if classes:
        logger.info(
            f"Custom-model classes for {weights.name}: "
            f"{len(classes)} entries (from {classes_source})"
        )

    yaml_path = os.path.join(custom_dir, f"{name}.yaml")
    # Avoid clobbering an existing user-authored yaml with the same name.
    n = 2
    while os.path.exists(yaml_path):
        yaml_path = os.path.join(custom_dir, f"{name}_{n}.yaml")
        n += 1

    payload = {
        "type": model_type,
        "name": name,
        "display_name": f"Custom \u00b7 {weights.stem}",
        "model_path": weights_abs,
        "engine": "ort",
        "conf_threshold": 0.25,
        "iou_threshold": 0.45,
        "classes": classes,
    }

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)
    logger.info(
        f"Auto-generated custom-model yaml for {weights.name} → {yaml_path}"
    )
    return yaml_path
