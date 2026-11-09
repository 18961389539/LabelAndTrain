import os
import csv
import json
import re
import yaml
import importlib.metadata
from packaging.specifiers import SpecifierSet
from typing import List, Dict, Optional

from jllabeling.services.auto_labeling.thresholds import (
    DEFAULT_CONF_THRESHOLD,
    DEFAULT_IOU_THRESHOLD,
)

from .config import TASK_SHAPE_MAPPINGS

#: A pure-YOLO dataset keeps its annotations in ``<stem>.txt``, and
#: ``partition_images`` trains Detect/Segment straight from those lines. The
#: counting passes below have to agree with it, or a fully labelled folder is
#: reported as empty and the pre-flight check blocks the run. Pose keypoints
#: and Classify flags have no txt equivalent, so they stay JSON-only.
YOLO_TXT_TASKS = ("Detect", "Segment")

#: Column count of a YOLO detect line; ``1 + 2n`` with n >= 3 is a polygon.
YOLO_DETECT_COLUMNS = 5


def _yolo_labels_module():
    """The txt reader lives with the labeling views; import it late so the
    training service keeps no import-time dependency on the UI package."""
    from jllabeling.views.labeling.utils import yolo_labels

    return yolo_labels


def _json_label_path(image_file, output_dir=None):
    label_dir, filename = os.path.split(image_file)
    if output_dir:
        label_dir = output_dir
    return os.path.join(label_dir, os.path.splitext(filename)[0] + ".json")


def yolo_txt_shapes(txt_path):
    """``(shape_type, class_index)`` for each usable line of a YOLO txt.

    The column count alone decides the shape type -- the same split
    ``yolo_labels.load_shapes`` makes -- so no image is decoded and a folder of
    thousands stays cheap. An unreadable file or an unparsable line yields
    nothing instead of raising: counting is a preview, the build pass is the
    one that reports a broken label.
    """
    try:
        lines = _yolo_labels_module().read_lines(txt_path)
    except OSError:
        return []
    shapes = []
    for line in lines:
        parts = line.replace("\t", " ").split()
        try:
            class_index = int(float(parts[0]))
        except (IndexError, ValueError):
            continue
        if len(parts) == YOLO_DETECT_COLUMNS:
            shapes.append(("rectangle", class_index))
        elif len(parts) >= 7 and (len(parts) - 1) % 2 == 0:
            shapes.append(("polygon", class_index))
    return shapes


def project_record_labels(image_list):
    """The ``labels`` of the folder's own project record, or ``[]``.

    The last-resort name list for a txt that ships no ``classes.txt``: it is
    what the label panel opens with, so the class names written into
    ``data.yaml`` match the names the user has been looking at. The record
    sits on the folder the user opened, which for an ``images/<split>`` tree
    is above the image itself, so the walk goes up a few levels.
    """
    if not image_list:
        return []
    try:
        from jllabeling.views.labeling.project import load_project

        directory = os.path.dirname(os.path.abspath(image_list[0]))
        for _level in range(4):
            names = load_project(directory).get("labels") or []
            if names:
                return [str(name) for name in names if str(name)]
            parent = os.path.dirname(directory)
            if parent == directory:
                break
            directory = parent
    except Exception:  # noqa: BLE001 - a preview must not fail on a record
        return []
    return []


class _YoloNames:
    """class id -> name, resolved once per labels directory."""

    def __init__(self, image_list):
        self._fallback = project_record_labels(image_list)
        self._by_dir = {}

    def names_for(self, txt_path):
        directory = os.path.dirname(os.path.abspath(txt_path))
        cached = self._by_dir.get(directory)
        if cached is None:
            try:
                names, _file = _yolo_labels_module().class_names_for(
                    txt_path, fallback=self._fallback
                )
            except Exception:  # noqa: BLE001 - see yolo_txt_shapes
                names = []
            cached = [str(name) for name in names or []]
            self._by_dir[directory] = cached
        return cached

    def label_for(self, txt_path, class_index):
        names = self.names_for(txt_path)
        if 0 <= class_index < len(names):
            return names[class_index]
        return f"class_{class_index}"

    def names_up_to(self, txt_path, max_index):
        """Dataset names ordered by class id, padded to cover ``max_index``.

        An id with no name in ``classes.txt`` still has to occupy its own slot,
        or every name after it would shift by one against the txt lines.
        """
        names = list(self.names_for(txt_path))
        for index in range(len(names), max_index + 1):
            names.append(f"class_{index}")
        return names


def _label_file_data(label_file):
    """Parsed label JSON, or ``None`` when it cannot be read."""
    try:
        with open(label_file, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, IOError):
        return None


def check_package_installed(package_name, version_spec=None):
    """Check if a Python package is installed and optionally verify its version.

    Args:
        package_name: Name of the package to check
        version_spec: Optional version specification string (e.g. ">=1.0.0")

    Returns:
        bool: True if package is installed and version matches spec (if provided), False otherwise
    """
    try:
        __import__(package_name)

        if version_spec:
            try:
                installed_version = importlib.metadata.version(package_name)
                spec_set = SpecifierSet(version_spec)
                return installed_version in spec_set
            except importlib.metadata.PackageNotFoundError:
                return False

        return True
    except ImportError:
        return False


def get_label_infos(
    image_list: List[str], supported_shape: List[str], output_dir: str = None
) -> Dict[str, Dict[str, int]]:
    """Get statistics about labels and shapes from a list of labeled images.

    Args:
        image_list: List of image file paths
        supported_shape: List of supported shape types
        output_dir: Optional output directory for label files

    Returns:
        Dict mapping label names to counts of each shape type
    """
    initial_nums = [0 for _ in range(len(supported_shape))]
    label_infos = {}
    is_classify_task = "flags" in supported_shape
    yolo_labels = None if is_classify_task else _yolo_labels_module()
    names = None if is_classify_task else _YoloNames(image_list)

    def _count(label, shape_type):
        if label not in label_infos:
            label_infos[label] = dict(zip(supported_shape, initial_nums))
        label_infos[label][shape_type] += 1

    for image_file in image_list:
        label_file = _json_label_path(image_file, output_dir)

        if not os.path.exists(label_file):
            if yolo_labels is None:
                continue
            txt_path = yolo_labels.find_yolo_txt(image_file, output_dir)
            if not txt_path:
                continue
            for shape_type, class_index in yolo_txt_shapes(txt_path):
                if shape_type in supported_shape:
                    _count(names.label_for(txt_path, class_index), shape_type)
            continue

        data = _label_file_data(label_file)
        if data is None:
            continue

        if is_classify_task:
            flags = data.get("flags", {})
            selected_flag = None
            for flag_name, flag_value in flags.items():
                if flag_value:
                    selected_flag = flag_name
                    break

            if selected_flag:
                if selected_flag not in label_infos:
                    label_infos[selected_flag] = dict(
                        zip(supported_shape, initial_nums.copy())
                    )
                    label_infos[selected_flag]["_total"] = 0
                label_infos[selected_flag]["_total"] += 1
        else:
            for shape in data.get("shapes", []):
                if "label" not in shape or "shape_type" not in shape:
                    continue
                shape_type = shape["shape_type"]
                if shape_type not in supported_shape:
                    continue
                _count(shape["label"], shape_type)

    label_infos = {k: label_infos[k] for k in sorted(label_infos)}
    return label_infos


def get_task_valid_images(
    image_list: List[str], task_type: str, output_dir: str = None
) -> int:
    """Count number of images that have valid shapes for a given task type.

    Args:
        image_list: List of image file paths
        task_type: Type of task (e.g. 'detection', 'segmentation')
        output_dir: Optional output directory for label files

    Returns:
        Number of images that have at least one valid shape for the task
    """
    if task_type not in TASK_SHAPE_MAPPINGS:
        return 0

    valid_shapes = TASK_SHAPE_MAPPINGS[task_type]
    yolo_labels = (
        _yolo_labels_module() if task_type in YOLO_TXT_TASKS else None
    )
    valid_image_count = 0

    for image_file in image_list:
        label_file = _json_label_path(image_file, output_dir)

        if not os.path.exists(label_file):
            # Same rule as the dataset build: with no JSON, the image counts
            # when its YOLO txt carries a shape this task can train on.
            if yolo_labels is None:
                continue
            txt_path = yolo_labels.find_yolo_txt(image_file, output_dir)
            if txt_path and any(
                shape_type in valid_shapes
                for shape_type, _index in yolo_txt_shapes(txt_path)
            ):
                valid_image_count += 1
            continue

        data = _label_file_data(label_file)
        if data is None:
            continue

        if "flags" in valid_shapes:
            flags = data.get("flags", {})
            has_valid_flag = any(flag_value for flag_value in flags.values())
            if has_valid_flag:
                valid_image_count += 1
        else:
            has_valid_shape = any(
                shape.get("shape_type") in valid_shapes
                for shape in data.get("shapes", [])
                if "shape_type" in shape
            )
            if has_valid_shape:
                valid_image_count += 1

    return valid_image_count


def get_statistics_table_data(
    image_list: List[str], supported_shape: List[str], output_dir: str = None
) -> List[List[str]]:
    """Generate statistics table data about labels and shapes.

    Args:
        image_list: List of image file paths
        supported_shape: List of supported shape types
        output_dir: Optional output directory for label files

    Returns:
        List of rows containing label statistics, with headers and totals
    """
    label_infos = get_label_infos(image_list, supported_shape, output_dir)

    if not label_infos:
        return []

    total_infos = [["Label"] + supported_shape + ["Total"]]
    shape_counter = [0 for _ in range(len(supported_shape) + 1)]
    is_classify_task = "flags" in supported_shape

    for label, infos in label_infos.items():
        if is_classify_task:
            counter = [
                infos.get(shape_type, 0) for shape_type in supported_shape
            ]
            total_count = infos.get("_total", 0)
            counter.append(total_count)
        else:
            counter = [infos[shape_type] for shape_type in supported_shape]
            counter.append(sum(counter))

        row = [label] + [str(c) for c in counter]
        total_infos.append(row)
        shape_counter = [x + y for x, y in zip(counter, shape_counter)]

    total_infos.append(["Total"] + [str(c) for c in shape_counter])
    return total_infos


def dataset_overview_stats(image_list, output_dir=None):
    """Return (total, labeled, empty, class_count) for the current folder."""
    total = len(image_list or [])
    labeled = 0
    classes = set()
    yolo_labels = _yolo_labels_module()
    names = _YoloNames(image_list)
    for image_file in image_list or []:
        label_file = _json_label_path(image_file, output_dir)
        if not os.path.exists(label_file):
            txt_path = yolo_labels.find_yolo_txt(image_file, output_dir)
            if not txt_path:
                continue
            shapes = yolo_txt_shapes(txt_path)
            if shapes:
                labeled += 1
            for _shape_type, class_index in shapes:
                classes.add(names.label_for(txt_path, class_index))
            continue
        data = _label_file_data(label_file)
        if data is None:
            continue
        shapes = data.get("shapes") or []
        flags = data.get("flags") or {}
        if shapes or any(flags.values()):
            labeled += 1
        for shape in shapes:
            label = shape.get("label")
            if label:
                classes.add(label)
        for flag_name, flag_value in flags.items():
            if flag_value:
                classes.add(flag_name)
    return total, labeled, max(0, total - labeled), len(classes)


def collect_class_names(image_list, output_dir=None):
    """Unique class names, in the order that becomes ``data.yaml``'s ids.

    The JSON side is first-seen because that is the order the exporter numbers
    labels in. A YOLO txt cannot be renumbered that way: its lines are indices
    into *its own* name list, so the txt contributes the dataset's names in
    that list's order, padded with the ``class_<id>`` placeholders the
    annotator itself shows for an unnamed id.
    """
    names = []
    seen = set()
    yolo_labels = _yolo_labels_module()
    resolver = _YoloNames(image_list)

    def _append(candidate):
        for name in candidate:
            if name and name not in seen:
                seen.add(name)
                names.append(name)

    for image_file in image_list or []:
        label_file = _json_label_path(image_file, output_dir)
        if not os.path.exists(label_file):
            txt_path = yolo_labels.find_yolo_txt(image_file, output_dir)
            if not txt_path:
                continue
            shapes = yolo_txt_shapes(txt_path)
            if not shapes:
                continue
            max_index = max(index for _type, index in shapes)
            _append(resolver.names_up_to(txt_path, max_index))
            continue
        data = _label_file_data(label_file)
        if data is None:
            continue
        _append(
            [
                shape.get("label")
                for shape in data.get("shapes") or []
                if shape.get("label")
            ]
        )
        _append(
            [
                flag_name
                for flag_name, flag_value in (data.get("flags") or {}).items()
                if flag_value
            ]
        )
    return names


def autolabel_type_for_task(task_type) -> Optional[str]:
    """Map a training task to a custom auto-labeling model type."""
    mapping = {
        "Detect": "yolov8",
        "Segment": "yolov8_seg",
        "Pose": "yolo26_pose",
        "Classify": "yolov8_cls",
    }
    return mapping.get(task_type)


def sanitize_custom_model_name(raw: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", raw or "")
    text = text.strip("._-") or "trained_model"
    return text[:80]


def write_autolabel_model_yaml(
    yaml_path,
    *,
    model_type,
    name,
    display_name,
    model_path,
    classes,
    has_visible: bool = None,
    kpt_threshold: float = None,
    conf_threshold: float = DEFAULT_CONF_THRESHOLD,
):
    """Write a custom-model yaml that ModelManager.load_custom_model can load.

    ``classes`` stays a mapping for pose models, which read it as
    ``{class: [keypoint names]}``; flattening it to a list breaks them.
    """
    payload = {
        "type": model_type,
        "name": name,
        "display_name": display_name,
        "model_path": os.path.abspath(model_path),
        "conf_threshold": conf_threshold,
        "iou_threshold": DEFAULT_IOU_THRESHOLD,
        "classes": (
            dict(classes) if isinstance(classes, dict) else list(classes or [])
        ),
    }
    if isinstance(classes, dict):
        # The pose adapter derives kpt_shape from these when the ONNX carries
        # no metadata, so the visibility flag has to agree with the names.
        payload["has_visible"] = (
            True if has_visible is None else bool(has_visible)
        )
        if kpt_threshold is not None:
            payload["kpt_threshold"] = float(kpt_threshold)
    parent = os.path.dirname(yaml_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(yaml_path, "w", encoding="utf-8") as handle:
        yaml.dump(
            payload, handle, allow_unicode=True, default_flow_style=False
        )
    return yaml_path


#: How many recent epoch deltas the ETA averages over: enough to smooth the
#: (slow) first epochs out without lagging far behind a changing pace.
ETA_SAMPLE_ROWS = 5


def estimate_remaining_seconds(results_csv_path, total_epochs):
    """Seconds left before ``total_epochs``, or ``None`` when unknowable.

    Ultralytics writes ``time`` as *cumulative* seconds for the current
    session, so a per-epoch duration is the delta between rows. Dividing the
    total by the epoch count would be wrong twice over: the first epochs are
    the slowest (model load, cache build), and a resumed run restarts the
    clock while the epoch counter continues. The last few deltas are averaged
    for the same reason, and the epoch column (not the row count) decides how
    much is left — a resumed run can repeat a row.
    """
    if not results_csv_path or not os.path.exists(results_csv_path):
        return None
    if not total_epochs or total_epochs <= 0:
        return None
    try:
        with open(results_csv_path, "r", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except Exception:
        return None
    if len(rows) < 2:
        return None

    try:
        done = int(float(rows[-1].get("epoch") or 0))
    except (TypeError, ValueError):
        done = len(rows)
    todo = total_epochs - done
    if todo <= 0:
        return None

    samples = []
    for row in rows[-(ETA_SAMPLE_ROWS + 1) :]:
        try:
            samples.append(float(row.get("time") or 0.0))
        except (TypeError, ValueError):
            return None
    deltas = [
        later - earlier
        for earlier, later in zip(samples, samples[1:])
        if later > earlier
    ]
    if not deltas:
        return None
    return todo * (sum(deltas) / len(deltas))


def parse_training_metrics(results_csv_path):
    """Read the last row of ultralytics results.csv as (loss, map50, epochs).

    ``epochs`` comes from the ``epoch`` column, not from the row count: a
    resumed run repeats one row, because the interrupted epoch is written
    again when the run picks up from the checkpoint. Counting rows therefore
    reported 51 epochs for a 50-epoch run — measured on a real interrupted and
    resumed run on 2026-09-30 (epoch 7 appears twice) — and that number is
    what ``run_meta.json`` records and the experiment history displays, i.e.
    the field a run's length is compared on across rounds.
    """
    if not results_csv_path or not os.path.exists(results_csv_path):
        return None
    try:
        with open(results_csv_path, "r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
    except Exception:
        return None
    if not rows:
        return None
    last = {
        (key or "").strip(): (value or "").strip()
        for key, value in rows[-1].items()
    }
    loss = None
    map50 = None
    fallback_loss = None
    for key, value in last.items():
        if not value:
            continue
        lowered = key.lower()
        if loss is None and "box_loss" in lowered:
            loss = value
        if fallback_loss is None and lowered.endswith("loss"):
            fallback_loss = value
        if (
            map50 is None
            and "map50" in lowered
            and "map50-95" not in lowered
            and "map50_95" not in lowered
        ):
            map50 = value
    if loss is None:
        loss = fallback_loss

    epochs = len(rows)
    try:
        if last.get("epoch"):
            epochs = int(float(last["epoch"]))
    except (TypeError, ValueError):
        pass
    return loss, map50, epochs
