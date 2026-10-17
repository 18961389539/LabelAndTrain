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
import os.path as osp
import time

from anylabeling.config import get_work_directory
from anylabeling.views.labeling.utils._io import save_json

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
    """Write the registry atomically; a crash cannot truncate it.

    The write goes through the shared ``save_json`` helper (temp file +
    fsync + replace), so a partial write never lands in ``projects.json``
    -- the one file both the switcher and the recent list read. The
    on-disk format stays the registry's own (two-space indent, Chinese
    kept readable), and a failed write returns ``False`` rather than
    raising, matching the module's damage-tolerance contract.
    """
    payload = {"schema": SCHEMA, "projects": data["projects"]}
    try:
        save_json(payload, registry_path(), indent=2, ensure_ascii=False)
        return True
    except OSError:
        return False


def record_project(root, label_dir=None, on_evicted=None):
    """Touch (or prepend) ``root`` and remember where its labels live.

    The list is bounded by ``MAX_ENTRIES``. When it overflows, entries
    whose folder has vanished from disk make way first -- the switcher
    never shows them, yet they occupy real slots -- and only then does
    the oldest entry go. The entry being recorded is never evicted:
    it sits at the head and the cut stops short of it.

    Eviction is not silent: ``on_evicted(roots)`` hears about every
    entry that left, so the caller can put a line in the status bar
    instead of letting rows disappear without a word. The dataset
    itself -- labels, settings, the ``.jllabel`` record -- is never
    touched by an eviction; only the convenience list shrinks.
    """
    if not root:
        return False
    root = osp.normpath(str(root))
    registry = load_registry()
    previous = next(
        (entry for entry in registry["projects"] if entry.get("root") == root),
        {},
    )
    projects = [
        entry for entry in registry["projects"] if entry.get("root") != root
    ]
    projects.insert(
        0,
        {
            "root": root,
            "label_dir": label_dir or previous.get("label_dir"),
            "last_opened": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )
    evicted = []
    if len(projects) > MAX_ENTRIES:
        # 目录已不在的条目先让位：数据可能回来了，但名额是现在占着的。
        kept, gone = [], []
        for entry in projects[1:]:
            (gone if not osp.isdir(entry.get("root") or "") else kept).append(
                entry
            )
        evicted.extend(gone)
        projects = [projects[0]] + kept
        while len(projects) > MAX_ENTRIES:
            evicted.append(projects.pop())
    if evicted and on_evicted is not None:
        try:
            on_evicted([entry.get("root") or "" for entry in evicted])
        except Exception:  # noqa: BLE001 - 提示永远不是关键路径
            pass
    registry["projects"] = projects
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
