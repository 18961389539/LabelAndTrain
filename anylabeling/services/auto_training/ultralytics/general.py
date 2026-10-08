import hashlib
import json
import os
import re
import shutil
import random
from datetime import datetime
from typing import List

from ._io import load_yaml_config, save_yaml_config
from .config import (
    get_dataset_path,
    TASK_LABEL_MAPPINGS,
    TASK_SHAPE_MAPPINGS,
)

MANIFEST_NAME = "manifest.json"


def load_dataset_manifest(dataset_path: str):
    """Read the manifest for a dataset given its dir or its ``data.yaml``.

    Returns ``None`` for datasets built before manifests existed, so callers
    keep working with older runs instead of failing on them.
    """
    if not dataset_path:
        return None
    directory = (
        dataset_path
        if os.path.isdir(dataset_path)
        else os.path.dirname(os.path.abspath(dataset_path))
    )
    manifest_file = os.path.join(directory, MANIFEST_NAME)
    if not os.path.isfile(manifest_file):
        return None
    try:
        with open(manifest_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


DATASET_RUN_PATTERN = re.compile(r".+_\d{8}_\d{6}(_\d+)?$")


def collect_dataset_runs(task_root: str):
    """Dataset build directories under ``task_root``, newest first."""
    if not os.path.isdir(task_root):
        return []
    runs = []
    for name in os.listdir(task_root):
        path = os.path.join(task_root, name)
        if not os.path.isdir(path) or not DATASET_RUN_PATTERN.fullmatch(name):
            continue
        try:
            runs.append((os.path.getmtime(path), path))
        except OSError:
            continue
    runs.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in runs]


def directory_size(path: str) -> int:
    """Bytes actually reclaimed by deleting ``path``.

    Symlinks count as zero.  On Linux/macOS the dataset is assembled from
    ``os.symlink`` entries, so following them reports the size of the *source*
    images and promises the user space that removing the links never frees.
    """
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            full = os.path.join(root, name)
            if os.path.islink(full):
                continue
            try:
                total += os.path.getsize(full)
            except OSError:
                continue
    return total


def plan_dataset_prune(runs, keep: int, current_dir: str = None):
    """Pick old builds to drop, keeping the newest ``keep`` *besides* the
    current one.

    The run the just-finished training used is never a candidate, whatever its
    age, so the answer can never delete the data a result refers to.
    """
    current = os.path.normpath(current_dir) if current_dir else None
    candidates = [path for path in runs if os.path.normpath(path) != current]
    to_delete = candidates[keep:] if keep and keep > 0 else list(candidates)
    return to_delete


def prune_datasets(task_root: str, keep: int, current_dir: str = None):
    """Delete old builds; returns ``(deleted_paths, reclaimed_bytes, failed)``."""
    runs = collect_dataset_runs(task_root)
    deleted = []
    failed = []
    reclaimed = 0
    for path in plan_dataset_prune(runs, keep, current_dir):
        size = directory_size(path)
        try:
            shutil.rmtree(path)
        except OSError:
            failed.append(path)
            continue
        deleted.append(path)
        reclaimed += size
    return deleted, reclaimed, failed


def file_sha1(path: str):
    """Content hash of a file, or ``None`` when it cannot be read."""
    digest = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _drop_unusable(image_path: str, label_path: str):
    """Remove a half-built pair from the dataset being written.

    A label file that fails halfway through leaves either an empty or a
    truncated ``.txt``; both read as "this image has no objects" to
    ultralytics, which is exactly the guess this module refuses to make. The
    copied image goes with it, so the sample is absent rather than wrong.
    """
    for path in (label_path, image_path):
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            continue


def _manifest_entries(pairs, split: str, label_digests: dict) -> List[dict]:
    entries = []
    for image_file, label_file in pairs:
        entries.append(
            {
                "image": os.path.abspath(image_file),
                "label": (os.path.abspath(label_file) if label_file else None),
                "sha1": (
                    label_digests.get(label_file) if label_file else None
                ),
                "split": split,
            }
        )
    return entries


def _read_label_info(label_file: str):
    """``(raw_bytes, parsed_dict)`` for a label file, ``None`` when unusable.

    A file that exists but cannot be parsed is reported by the caller as
    unusable rather than being treated as an empty annotation: its presence
    means someone annotated this image, and "unreadable" is not the same
    statement as "there is nothing here".
    """
    try:
        with open(label_file, "rb") as f:
            label_bytes = f.read()
        label_info = json.loads(label_bytes.decode("utf-8"))
        if not isinstance(label_info, dict):
            raise ValueError("label file is not a JSON object")
    except Exception:  # noqa: BLE001
        return None
    return label_bytes, label_info


def partition_images(
    image_list: List[str],
    task_type: str,
    output_dir: str = None,
    only_checked_files: bool = False,
) -> dict:
    """Group the image list the way a dataset build needs it.

    Returns a dict with ``background`` (no label file at all - a legitimate
    negative sample), ``valid`` (``(image, label)`` pairs with an annotation
    this task can use), ``label_digests``, and the two groups that are *not*
    in the dataset: ``unreadable_labels`` (present but unparsable) and
    ``unchecked_files``. The last two used to be silently folded into
    ``background``, which trained an annotated image as an empty one.
    """
    valid_shapes = TASK_SHAPE_MAPPINGS.get(task_type, [])
    background_images = []
    valid_images = []
    label_digests = {}
    unreadable_labels = []
    unchecked_files = []

    for image_file in image_list:
        label_dir, filename = os.path.split(image_file)
        if output_dir:
            label_dir = output_dir
        label_file = os.path.join(
            label_dir, os.path.splitext(filename)[0] + ".json"
        )

        if not os.path.exists(label_file):
            if only_checked_files:
                unchecked_files.append(image_file)
                continue
            background_images.append(image_file)
            continue

        parsed = _read_label_info(label_file)
        if parsed is None:
            unreadable_labels.append(label_file)
            continue
        label_bytes, label_info = parsed
        label_digests[label_file] = hashlib.sha1(label_bytes).hexdigest()

        if only_checked_files and label_info.get("checked", False) is not True:
            unchecked_files.append(image_file)
            continue

        if task_type == "Classify":
            flags = label_info.get("flags", {})
            has_valid_shape = any(flag_value for flag_value in flags.values())
        else:
            shapes = label_info.get("shapes", [])
            has_valid_shape = any(
                shape.get("shape_type") in valid_shapes
                for shape in shapes
                if "shape_type" in shape
            )

        if has_valid_shape:
            valid_images.append((image_file, label_file))
        else:
            background_images.append(image_file)

    return {
        "background": background_images,
        "valid": valid_images,
        "label_digests": label_digests,
        "unreadable_labels": unreadable_labels,
        "unchecked_files": unchecked_files,
    }


def create_yolo_dataset(
    image_list: List[str],
    task_type: str,
    dataset_ratio: float,
    data_file: str,
    output_dir: str = None,
    pose_cfg_file: str = None,
    skip_empty_files: bool = False,
    only_checked_files: bool = False,
    seed: int = None,
    seed_source: str = "generated",
    report: dict = None,
) -> str:
    """Create YOLO dataset from image list and annotations.

    Args:
        image_list: List of image paths
        task_type: Type of detection task
        dataset_ratio: Ratio to split train/val data
        data_file: Path to data config file
        output_dir: Optional output directory for labels
        pose_cfg_file: Optional pose config file for pose detection
        skip_empty_files: Whether to skip empty label files
        only_checked_files: Whether to use only checked files
        seed: Split seed; a random one is drawn and recorded when omitted
        seed_source: "project" when the seed is pinned per dataset, so the
            manifest says whether rounds are comparable by construction
        report: Optional dict used as an out-parameter, filled with what the
            build could not use: ``unreadable_labels`` (present but
            unparsable), ``unchecked_files``, ``conversion_errors`` and
            ``dropped_shapes``. Written to disk too, so a caller that forgets
            the out-parameter still leaves a record.

    Returns:
        Path to created dataset directory. ``manifest.json`` inside it records
        the exact annotations the run was built from, so a completed training
        can be tied back to the data it actually saw.

    A label file that exists but cannot be read is **left out of the dataset**
    and reported, never trained as an empty sample: the file's presence means
    an annotation was intended, and "we could not read it" is not the same
    statement as "there is nothing in this image". Only images with no label
    file at all become background samples.
    """
    if seed is None:
        seed = random.SystemRandom().randrange(1, 2**31 - 1)
    from anylabeling.views.labeling.label_converter import LabelConverter

    # What the build could not use. ``unreadable_labels`` and
    # ``conversion_errors`` both mean "this image is not in the dataset", and
    # both are told to the caller (and written to disk) instead of being
    # folded into the background count, where they were indistinguishable.
    conversion_errors = []
    conversion_stats = {}

    def _process_images_batch(
        image_label_pairs, images_dir, labels_dir, converter, mode, skip_empty
    ):
        used_names = set()
        for image_file, label_file in image_label_pairs:
            filename = os.path.basename(image_file)
            stem, ext = os.path.splitext(filename)
            dst_image_path = os.path.join(images_dir, filename)
            if filename in used_names:
                digest = hashlib.md5(
                    os.path.abspath(image_file).encode("utf-8")
                ).hexdigest()[:8]
                filename = f"{stem}_{digest}{ext}"
                dst_image_path = os.path.join(images_dir, filename)
            used_names.add(filename)

            if os.name == "nt":  # Windows
                shutil.copy2(image_file, dst_image_path)
            else:
                os.symlink(image_file, dst_image_path)

            if label_file and os.path.exists(label_file):
                dst_label_path = os.path.join(
                    labels_dir, os.path.splitext(filename)[0] + ".txt"
                )
                try:
                    converter.custom_to_yolo(
                        label_file,
                        dst_label_path,
                        mode,
                        skip_empty_files=skip_empty,
                        stats=conversion_stats,
                    )
                except Exception as exc:  # noqa: BLE001
                    # One unreadable label file used to take the whole build
                    # down with it (a KeyError on a missing imageWidth did
                    # exactly that, on a label a converter had produced).
                    # Drop that one image instead of the batch: a partial or
                    # empty .txt left behind would silently train the image as
                    # having no objects, so both files go.
                    conversion_errors.append(
                        {
                            "label": label_file,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
                    _drop_unusable(dst_image_path, dst_label_path)

    def _process_classify_images_batch(image_label_pairs, base_dir):
        used_names = set()
        for image_file, label_file in image_label_pairs:
            filename = os.path.basename(image_file)
            stem, ext = os.path.splitext(filename)

            if not label_file or not os.path.exists(label_file):
                continue

            try:
                with open(label_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                flags = data.get("flags", {})

                for flag_name, flag_value in flags.items():
                    if flag_value:
                        class_dir = os.path.join(base_dir, flag_name)
                        os.makedirs(class_dir, exist_ok=True)
                        dst_filename = filename
                        if filename in used_names:
                            digest = hashlib.md5(
                                os.path.abspath(image_file).encode("utf-8")
                            ).hexdigest()[:8]
                            dst_filename = f"{stem}_{digest}{ext}"
                        used_names.add(dst_filename)
                        dst_image_path = os.path.join(class_dir, dst_filename)

                        if os.name == "nt":  # Windows
                            shutil.copy2(image_file, dst_image_path)
                        else:
                            os.symlink(image_file, dst_image_path)
                        break
            except (json.JSONDecodeError, IOError):
                continue

    if task_type == "Classify":
        data = {"names": {}, "nc": 0}
        converter = None
        data_file_name = "classification"
    else:
        data = load_yaml_config(data_file)
        if data is None:
            raise ValueError(f"Failed to read data file: {data_file}")
        if task_type.lower() == "pose":
            if not pose_cfg_file:
                raise ValueError(
                    "Pose configuration file is required for pose detection tasks"
                )
            converter = LabelConverter(pose_cfg_file=pose_cfg_file)
        else:
            converter = LabelConverter()
        names = data["names"]
        converter.classes = (
            list(names.values())
            if isinstance(names, list)
            else [names[i] for i in sorted(names.keys())]
        )
        data_file_name = os.path.splitext(os.path.basename(data_file))[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_dir = os.path.join(
        get_dataset_path(), task_type.lower(), f"{data_file_name}_{timestamp}"
    )
    # The name only carries second precision: two builds in the same second
    # would share a directory and the second one would overwrite the first,
    # including its manifest.
    if os.path.exists(temp_dir):
        suffix = 2
        while os.path.exists(f"{temp_dir}_{suffix}"):
            suffix += 1
        temp_dir = f"{temp_dir}_{suffix}"

    if task_type == "Classify":
        train_dir = os.path.join(temp_dir, "train")
        val_dir = os.path.join(temp_dir, "val")
        os.makedirs(train_dir, exist_ok=True)
        os.makedirs(val_dir, exist_ok=True)
    else:
        train_images_dir = os.path.join(temp_dir, "images", "train")
        val_images_dir = os.path.join(temp_dir, "images", "val")
        train_labels_dir = os.path.join(temp_dir, "labels", "train")
        val_labels_dir = os.path.join(temp_dir, "labels", "val")
        for dir_path in [
            train_images_dir,
            val_images_dir,
            train_labels_dir,
            val_labels_dir,
        ]:
            os.makedirs(dir_path, exist_ok=True)

    partitioned = partition_images(
        image_list, task_type, output_dir, only_checked_files
    )
    background_images = partitioned["background"]
    valid_images = partitioned["valid"]
    label_digests = partitioned["label_digests"]
    unreadable_labels = partitioned["unreadable_labels"]
    unchecked_files = partitioned["unchecked_files"]

    # ensure train/val split is randomized, but reproducible from the seed
    # recorded in the manifest
    valid_images = random.Random(seed).sample(
        valid_images, k=len(valid_images)
    )

    train_count = int(len(valid_images) * dataset_ratio)
    train_valid_images = valid_images[:train_count]
    val_valid_images = valid_images[train_count:]

    if task_type == "Classify":
        _process_classify_images_batch(train_valid_images, train_dir)
        _process_classify_images_batch(val_valid_images, val_dir)
    else:
        if skip_empty_files:
            all_train_images = train_valid_images
        else:
            all_train_images = [
                (img, None) for img in background_images
            ] + train_valid_images

        mode = TASK_LABEL_MAPPINGS.get(task_type, "hbb")
        _process_images_batch(
            all_train_images,
            train_images_dir,
            train_labels_dir,
            converter,
            mode,
            skip_empty_files,
        )
        _process_images_batch(
            val_valid_images,
            val_images_dir,
            val_labels_dir,
            converter,
            mode,
            skip_empty_files,
        )

    info_file = os.path.join(temp_dir, "dataset_info.txt")
    dropped_shapes = conversion_stats.get("skipped", {}) or {}
    with open(info_file, "w", encoding="utf-8") as f:
        f.write(
            f"Dataset created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        )
        f.write(f"Task type: {task_type}\n")
        f.write(f"Total images: {len(image_list)}\n")
        if task_type == "Classify":
            f.write(f"Train images: {len(train_valid_images)}\n")
            f.write(f"Val images: {len(val_valid_images)}\n")
        else:
            f.write(f"Train images: {len(all_train_images)}\n")
            f.write(f"Val images: {len(val_valid_images)}\n")
            f.write(f"Background images: {len(background_images)}\n")
            f.write(f"Skip empty files: {skip_empty_files}\n")
            f.write(f"Only checked files: {only_checked_files}\n")
        f.write(f"Valid labeled images: {len(valid_images)}\n")
        f.write(f"Dataset ratio: {dataset_ratio}\n")
        # What the build could not use. Without these lines a bad label file
        # looked exactly like an image nobody had annotated yet.
        f.write(f"Unreadable label files: {len(unreadable_labels)}\n")
        f.write(f"Images skipped (unchecked): {len(unchecked_files)}\n")
        f.write(
            f"Images dropped (conversion failed): {len(conversion_errors)}\n"
        )
        f.write(
            f"Shapes dropped by the converter: {sum(dropped_shapes.values())}\n"
        )
        for reason, count in sorted(
            dropped_shapes.items(), key=lambda item: (-item[1], item[0])
        ):
            f.write(f"  {count} × {reason}\n")
        for path in unreadable_labels:
            f.write(f"  unreadable: {path}\n")
        for entry in conversion_errors:
            f.write(f"  failed: {entry['label']} ({entry['error']})\n")

    yaml_file = os.path.join(temp_dir, "data.yaml")

    if task_type == "Classify":
        class_names = {}
        train_dir = os.path.join(temp_dir, "train")
        if os.path.exists(train_dir):
            class_dirs = [
                d
                for d in os.listdir(train_dir)
                if os.path.isdir(os.path.join(train_dir, d))
            ]
            for i, class_name in enumerate(sorted(class_dirs)):
                class_names[i] = class_name

        data = {
            "path": temp_dir,
            "train": "train",
            "val": "val",
            "names": class_names,
            "nc": len(class_names),
        }
    else:
        data["path"] = temp_dir
        data["train"] = "images/train"
        data["val"] = "images/val"

    save_yaml_config(data, yaml_file)

    if task_type == "Classify":
        train_pairs = train_valid_images
        classes = [class_names[i] for i in sorted(class_names)]
    else:
        train_pairs = all_train_images
        classes = list(getattr(converter, "classes", []) or [])
    manifest = {
        "schema": 1,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "task": task_type,
        "dataset_ratio": dataset_ratio,
        "seed": seed,
        "seed_source": seed_source,
        "only_checked_files": only_checked_files,
        "skip_empty_files": skip_empty_files,
        "classes": classes,
        "counts": {
            "requested": len(image_list),
            "valid": len(valid_images),
            "train": len(train_pairs),
            "val": len(val_valid_images),
            "background": len(background_images),
        },
        "skipped": {
            "unreadable_labels": list(unreadable_labels),
            "unreadable_labels_count": len(unreadable_labels),
            "unchecked_files_count": len(unchecked_files),
            "conversion_errors": list(conversion_errors),
            "dropped_shapes": dict(dropped_shapes),
        },
        "data_yaml": yaml_file,
        "data_yaml_sha1": file_sha1(yaml_file),
        "files": _manifest_entries(train_pairs, "train", label_digests)
        + _manifest_entries(val_valid_images, "val", label_digests),
    }
    manifest_file = os.path.join(temp_dir, "manifest.json")
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    if report is not None:
        report.update(
            {
                "dataset_dir": temp_dir,
                "requested": len(image_list),
                "valid": len(valid_images),
                "train": len(train_pairs),
                "val": len(val_valid_images),
                "background": len(background_images),
                "unreadable_labels": list(unreadable_labels),
                "unreadable_labels_count": len(unreadable_labels),
                "unchecked_files_count": len(unchecked_files),
                "conversion_errors": list(conversion_errors),
                "dropped_shapes": dict(dropped_shapes),
            }
        )

    return temp_dir


def format_classes_display(classes_value) -> str:
    """Formats class values for display.

    This function takes a classes value and formats it into a string representation.
    It handles None values, empty values, lists, and single values.

    Args:
        classes_value: The value to format. Can be None, a list, or a single value.

    Returns:
        A string representation of the classes value:
        - Empty string if input is None or empty
        - Comma-separated string if input is a list
        - String conversion of the input value otherwise
    """
    if classes_value is None or not classes_value:
        return ""
    if isinstance(classes_value, list):
        return ",".join(map(str, classes_value))
    return str(classes_value) if classes_value else ""


def parse_string_to_digit_list(input_string: str) -> List[int]:
    """Parses a string containing numbers into a list of integers.

    This function uses regular expressions to find all numerical digits
    in the input string, treating any non-digit characters as delimiters.
    It then converts the found sequences of digits into integers.

    Args:
        input_string: The string to parse. It can contain numbers
            separated by commas, spaces, or any other non-digit symbols.
            Example: "1, 2 3-4".

    Returns:
        A list of integers found in the string. For example, for the input
        "1, 2 3-4", the output would be [1, 2, 3, 4]. Returns None if
        no numbers are found, input is empty, or parsing fails.
    """
    try:
        if not input_string:
            return None

        numbers_as_strings = re.findall(r"\d+", input_string)
        if not numbers_as_strings:
            return None

        return [int(num) for num in numbers_as_strings]

    except Exception:
        return None
