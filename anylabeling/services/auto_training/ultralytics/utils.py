import os
import csv
import json
import re
import yaml
import importlib.metadata
from packaging.specifiers import SpecifierSet
from typing import List, Dict, Optional

from .config import TASK_SHAPE_MAPPINGS


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

    for image_file in image_list:
        label_dir, filename = os.path.split(image_file)
        if output_dir:
            label_dir = output_dir
        label_file = os.path.join(
            label_dir, os.path.splitext(filename)[0] + ".json"
        )

        if not os.path.exists(label_file):
            continue

        try:
            with open(label_file, "r", encoding="utf-8") as f:
                data = json.load(f)

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
                shapes = data.get("shapes", [])
                for shape in shapes:
                    if "label" not in shape or "shape_type" not in shape:
                        continue
                    shape_type = shape["shape_type"]
                    if shape_type not in supported_shape:
                        continue
                    label = shape["label"]

                    if label not in label_infos:
                        label_infos[label] = dict(
                            zip(supported_shape, initial_nums.copy())
                        )
                    label_infos[label][shape_type] += 1

        except (json.JSONDecodeError, IOError):
            continue

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
    valid_image_count = 0

    for image_file in image_list:
        label_dir, filename = os.path.split(image_file)
        if output_dir:
            label_dir = output_dir
        label_file = os.path.join(
            label_dir, os.path.splitext(filename)[0] + ".json"
        )

        if not os.path.exists(label_file):
            continue

        try:
            with open(label_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "flags" in valid_shapes:
                flags = data.get("flags", {})
                has_valid_flag = any(
                    flag_value for flag_value in flags.values()
                )
                if has_valid_flag:
                    valid_image_count += 1
            else:
                shapes = data.get("shapes", [])
                has_valid_shape = any(
                    shape.get("shape_type") in valid_shapes
                    for shape in shapes
                    if "shape_type" in shape
                )
                if has_valid_shape:
                    valid_image_count += 1
        except (json.JSONDecodeError, IOError):
            continue

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
    for image_file in image_list or []:
        label_dir, filename = os.path.split(image_file)
        if output_dir:
            label_dir = output_dir
        label_file = os.path.join(
            label_dir, os.path.splitext(filename)[0] + ".json"
        )
        if not os.path.exists(label_file):
            continue
        try:
            with open(label_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
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
    """Return unique class names in first-seen order from label JSON files."""
    names = []
    seen = set()
    for image_file in image_list or []:
        label_dir, filename = os.path.split(image_file)
        if output_dir:
            label_dir = output_dir
        label_file = os.path.join(
            label_dir, os.path.splitext(filename)[0] + ".json"
        )
        if not os.path.exists(label_file):
            continue
        try:
            with open(label_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            continue
        for shape in data.get("shapes") or []:
            label = shape.get("label")
            if label and label not in seen:
                seen.add(label)
                names.append(label)
        for flag_name, flag_value in (data.get("flags") or {}).items():
            if flag_value and flag_name not in seen:
                seen.add(flag_name)
                names.append(flag_name)
    return names


def autolabel_type_for_task(task_type) -> Optional[str]:
    """Map a training task to a custom auto-labeling model type."""
    mapping = {
        "Detect": "yolov8",
        "Segment": "yolov8_seg",
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
):
    """Write a custom-model yaml that ModelManager.load_custom_model can load."""
    payload = {
        "type": model_type,
        "name": name,
        "display_name": display_name,
        "model_path": os.path.abspath(model_path),
        "conf_threshold": 0.25,
        "iou_threshold": 0.45,
        "classes": list(classes or []),
    }
    parent = os.path.dirname(yaml_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(yaml_path, "w", encoding="utf-8") as handle:
        yaml.dump(payload, handle, allow_unicode=True, default_flow_style=False)
    return yaml_path


def parse_training_metrics(results_csv_path):
    """Read the last row of ultralytics results.csv as (loss, map50, epochs)."""
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
    return loss, map50, len(rows)
