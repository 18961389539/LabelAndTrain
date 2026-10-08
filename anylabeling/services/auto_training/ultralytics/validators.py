import os
import subprocess
import sys
import yaml
from typing import Dict, List, Tuple, Union

from .utils import get_task_valid_images
from .config import MIN_LABELED_IMAGES_THRESHOLD


def is_single_path_component(value: str) -> bool:
    """True when ``value`` names exactly one directory inside its parent.

    The training form's Project and Name fields are plain text boxes, and the
    two are joined into the directory a "Retrain (overwrite)" confirmation
    then deletes recursively. ``os.path.join`` *discards* the first part when
    the second is absolute, and ``..`` walks out of the project, so a pasted
    path in Name used to point that deletion at any directory on the disk.
    Only single-component names are accepted here.
    """
    text = (value or "").strip()
    if not text or text in (os.curdir, os.pardir):
        return False
    if text != os.path.basename(text):
        return False
    if os.path.isabs(text) or os.path.splitdrive(text)[0]:
        return False
    for separator in (os.sep, os.altsep):
        if separator and separator in text:
            return False
    return ":" not in text


def is_inside_directory(path: str, directory: str) -> bool:
    """True when ``path`` is strictly inside ``directory``.

    Used as the second guard in front of a recursive delete: even a
    single-component name must not resolve outside the project it was typed
    into (symlinks, a project that is itself a file, ...).
    """
    if not path or not directory:
        return False
    inner = os.path.normcase(os.path.abspath(path))
    outer = os.path.normcase(os.path.abspath(directory))
    if inner == outer:
        return False
    return inner.startswith(outer.rstrip(os.sep) + os.sep)


def validate_basic_config(
    config: Dict, task_type: str = None
) -> Tuple[Union[bool, str], str]:
    """Validate basic training configuration

    Args:
        config: Training configuration dictionary
        task_type: Selected task type; classification may leave Data empty
            because its dataset is built from image flags (or a directory)

    Returns:
        Tuple of (is_valid_or_status, error_message_or_path)
        - (True, "") - validation passed
        - (False, error_message) - validation failed
        - ("directory_exists", directory_path) - directory exists, needs user confirmation
    """
    basic = config.get("basic", {})

    if not basic.get("project", "").strip():
        return False, "Project field is required"

    if not basic.get("name", "").strip():
        return False, "Name field is required"

    # Refuse before anything joins the two into a path: a name carrying a
    # separator (or "..", or an absolute path) would silently redirect the
    # overwrite confirmation - and its recursive delete - at a directory the
    # user never named.
    if not is_single_path_component(basic["name"]):
        return False, (
            "Name must be a single folder name without path separators "
            "(no '/', '\\', ':' or '..')"
        )

    save_dir = os.path.join(basic["project"], basic["name"])
    if os.path.exists(save_dir):
        return "directory_exists", save_dir

    model_path = basic.get("model", "").strip()
    if not model_path:
        return False, "Valid model file is required"
    if not os.path.exists(model_path):
        # A bare asset name ("yolov8n.pt") is downloaded on demand by
        # resolve_training_model_path(); only path-like values must exist.
        bare_name = os.path.dirname(
            model_path
        ) == "" and model_path.lower().endswith(".pt")
        if not bare_name:
            return False, "Valid model file is required"

    data_path = basic.get("data", "").strip()
    if (task_type or "").lower() == "classify":
        # Classification builds its dataset from flags; the field is only
        # needed when the user points it at a pre-organized directory.
        if data_path and not os.path.exists(data_path):
            return False, "Valid data file is required"
    elif not data_path or not os.path.exists(data_path):
        return False, "Valid data file is required"

    return True, ""


def validate_classes(classes, names: List[str]) -> Tuple[bool, str]:
    """Validate class indices against available class names.

    Args:
        classes: The ``classes`` filter — the raw form string ("0,1"), an
            already-parsed list of ints (which is what the dialog holds by the
            time a run is committed), or ``None``/empty for "no filter"
        names: List of available class names to validate against; empty means
            the filter cannot be checked, which is not an error

    Returns:
        Tuple containing:
            - bool: True if validation passes, False if validation fails
            - str: Empty string if validation passes, error message if validation fails

    The index range check exists because ultralytics silently trains on
    nothing when every filter entry is out of range: a typo in this one field
    produces a run whose mAP says more about the filter than about the data.
    """
    if isinstance(classes, str):
        if not classes.strip():
            return True, ""
        from .general import parse_string_to_digit_list

        parsed = parse_string_to_digit_list(classes)
        if parsed is None:
            return False, "Invalid classes format"
    elif isinstance(classes, (list, tuple)):
        try:
            parsed = [int(item) for item in classes]
        except (TypeError, ValueError):
            return False, "Invalid classes format"
    else:
        # None: the field was left empty, so no filter is applied.
        return True, ""

    if not parsed or not names:
        return True, ""

    max_index = len(names) - 1
    for cls_idx in parsed:
        if cls_idx < 0 or cls_idx > max_index:
            return False, f"Class index {cls_idx} out of range (0-{max_index})"

    return True, ""


def validate_data_file(file_path: str) -> Tuple[bool, Union[str, List[str]]]:
    """Validate data YAML file.

    Args:
        file_path (str): Path to the data file.

    Returns:
        Tuple[bool, Union[str, List[str]]]: (is_valid, error_message_or_names_list)
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if "names" not in data:
            return False, "Data file must contain 'names' field"

        return True, list(data["names"].values())

    except Exception as e:
        return False, f"Failed to read file: {e}"


#: How long a package install may take before it is called a failure. The
#: previous 30s was shorter than a single wheel download on a slow link, so a
#: legitimate install was reported as broken (after making the user wait).
DEFAULT_INSTALL_TIMEOUT = 300


def is_frozen_build() -> bool:
    """True in a PyInstaller build, where ``sys.executable`` is the app itself.

    ``[sys.executable, "-m", "pip", "install", ...]`` cannot work there - the
    app would relaunch itself with those arguments - so callers have to say
    "install it in the environment you built from" instead of running pip.
    """
    return bool(getattr(sys, "frozen", False))


def install_packages_with_timeout(packages, timeout=DEFAULT_INSTALL_TIMEOUT):
    if is_frozen_build():
        return (
            False,
            "",
            "This is a packaged build, which cannot install packages into "
            "itself. Install them in the Python environment the app was built "
            "from and rebuild, or use the source install.",
        )

    cmd = [sys.executable, "-m", "pip", "install"] + packages

    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        stdout, stderr = process.communicate(timeout=timeout)
        return process.returncode == 0, stdout, stderr

    except subprocess.TimeoutExpired:
        process.kill()
        return False, "", f"Installation timed out after {timeout}s"
    except Exception as e:
        return False, "", str(e)


def validate_task_requirements(
    task_type: str, image_list: List[str], output_dir: str = None
) -> Tuple[bool, str]:
    if not task_type:
        return False, "Please select a task type"

    if not image_list:
        return False, "Please load images first"

    valid_images = get_task_valid_images(image_list, task_type, output_dir)

    if valid_images < MIN_LABELED_IMAGES_THRESHOLD:
        return (
            False,
            f"Need at least {MIN_LABELED_IMAGES_THRESHOLD} labeled images for {task_type} task. Found: {valid_images}",
        )

    return True, ""
