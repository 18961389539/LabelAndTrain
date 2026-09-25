"""Registry of opened projects, so datasets can be switched deliberately.

The app has no explicit project entity: opening a folder *is* opening a
project. This module records the folders that were opened (root, label dir,
last-opened time) into one JSON under the work directory, which is what the
project switcher and the recent-projects list read. It intentionally does not
live beside the data: the registry describes *usage*, not the datasets
themselves, and it must keep working when a dataset folder is deleted.

Same principles as ``project.py``: lazy writes, damage tolerance (a broken
registry degrades to an empty list, never an error dialog), bounded size.
"""

import json
import os
import os.path as osp
import time

from anylabeling.config import get_work_directory

REGISTRY_DIR_NAME = ".jllabel"
REGISTRY_FILE_NAME = "projects.json"
SCHEMA = 1
MAX_ENTRIES = 20


def registry_path():
    return osp.join(
        get_work_directory(), REGISTRY_DIR_NAME, REGISTRY_FILE_NAME
    )


def load_registry():
    """``{"projects": [...]}`` newest first; damaged file reads as empty."""
    path = registry_path()
    if not osp.isfile(path):
        return {"projects": []}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {"projects": []}
    if not isinstance(data, dict) or not isinstance(
        data.get("projects"), list
    ):
        return {"projects": []}
    projects = [
        entry
        for entry in data["projects"]
        if isinstance(entry, dict) and entry.get("root")
    ]
    return {"projects": projects}


def save_registry(data):
    path = registry_path()
    try:
        os.makedirs(osp.dirname(path), exist_ok=True)
        payload = {"schema": SCHEMA, "projects": data["projects"]}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def record_project(root, label_dir=None):
    """Touch (or prepend) ``root`` and remember where its labels live."""
    if not root:
        return False
    root = osp.normpath(str(root))
    registry = load_registry()
    projects = [
        entry for entry in registry["projects"] if entry.get("root") != root
    ]
    previous = next(
        (
            entry
            for entry in registry["projects"]
            if entry.get("root") == root
        ),
        {},
    )
    projects.insert(
        0,
        {
            "root": root,
            "label_dir": label_dir or previous.get("label_dir"),
            "last_opened": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )
    registry["projects"] = projects[:MAX_ENTRIES]
    return save_registry(registry)


def recent_projects(limit=None):
    """Recorded projects, newest first, skipping vanished folders."""
    entries = [
        entry
        for entry in load_registry()["projects"]
        if osp.isdir(entry.get("root") or "")
    ]
    if limit is not None:
        entries = entries[:limit]
    return entries


def forget_project(root):
    """Drop ``root`` from the list; the dataset itself is untouched."""
    if not root:
        return False
    root = osp.normpath(str(root))
    registry = load_registry()
    remaining = [
        entry for entry in registry["projects"] if entry.get("root") != root
    ]
    if len(remaining) == len(registry["projects"]):
        return True
    registry["projects"] = remaining
    return save_registry(registry)


def decide_startup_action(has_session, always_show_manager, has_registry):
    """What the startup flow should do; one of ``restore``/``manager``/``none``.

    ``restore``  - reopen the last session directly, no questions asked (the
                   common "keep annotating" path must stay one launch long);
    ``manager``  - open the project manager dialog so the user picks a dataset;
    ``none``     - stay on the empty canvas, whose CTA already says to open a
                   folder (a first run gains nothing from an empty dialog).

    The always-show switch wins over everything: the manager dialog lists the
    last project preselected, so nothing is hidden behind it.
    """
    if always_show_manager:
        return "manager"
    if has_session:
        return "restore"
    if has_registry:
        return "manager"
    return "none"
