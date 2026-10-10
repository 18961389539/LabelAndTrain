"""What a project *is*: its name, its task kind, when it was created.

``project.py`` owns the storage (where the record lives, how it is
written); this module owns the meaning. Every question the UI asks about
a project — what to print in the title bar, which task the wizard should
preselect, whether this folder already *is* a project — is answered here,
so the title bar, the switcher and the wizard cannot each invent their
own answer.

Same split as ``project_settings.py``: storage in ``project.py``, policy
here, and the widget/dialogs only delegate.

Identity is still the folder path: a name is a display label and never
takes part in a path, which is what lets it be renamed, truncated or
absent without anything on disk going stale.
"""

from __future__ import annotations

import os.path as osp
from datetime import datetime

from anylabeling.views.labeling import project as project_store
from anylabeling.views.labeling.project import DEFAULT_TASK, TASK_TYPES

#: Chinese names for the task kinds, for the interface. Kept in step with
#: ``TASK_TYPES`` by a test rather than by hope.
TASK_LABELS = {
    "Detect": "目标检测",
    "Segment": "实例分割",
    "Pose": "关键点",
    "Classify": "图像分类",
}

#: One line of "what you will be drawing", shown in the new-project wizard.
TASK_HINTS = {
    "Detect": "画矩形框",
    "Segment": "画多边形",
    "Pose": "点关键点",
    "Classify": "整图打类别标记",
}

#: A display label, not a path: truncating it loses nothing.
NAME_MAX_LENGTH = 60

#: Timestamp format, matching the project registry's ``last_opened``.
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def task_label(task):
    """Chinese name of a task kind; unknown kinds come back unchanged."""
    return TASK_LABELS.get(task, task or "")


def task_hint(task):
    return TASK_HINTS.get(task, "")


def normalize_task(raw):
    """Coerce anything to a task kind in ``TASK_TYPES`` (case-folded)."""
    if not raw:
        return DEFAULT_TASK
    text = str(raw).strip().lower()
    for task in TASK_TYPES:
        if task.lower() == text:
            return task
    return DEFAULT_TASK


def default_name(root):
    """What a project without a name is called: its folder's name."""
    if not root:
        return ""
    return osp.basename(osp.normpath(str(root))) or str(root)


def normalize_name(raw, root=None):
    """Clean a project name: one line, trimmed, bounded, never empty.

    Whitespace is collapsed rather than rejected, so a pasted name with a
    stray tab still works; a name that is empty after that falls back to
    the folder name, because "unnamed project" in a list of twelve is
    worse than the folder's own name.
    """
    text = " ".join(str(raw or "").split())
    text = text[:NAME_MAX_LENGTH].strip()
    if text:
        return text
    return default_name(root)


def new_record(
    root, name=None, task=None, labels=None, output_dir=None, now=None
):
    """The draft a new project starts from (schema 2). Nothing is written.

    ``now`` is injectable so a test can pin the timestamp.
    """
    record = {
        "schema": project_store.SCHEMA,
        "name": normalize_name(name, root),
        "task": normalize_task(task),
        "created_at": now or datetime.now().strftime(TIME_FORMAT),
    }
    names = [str(item) for item in (labels or []) if str(item)]
    if names:
        record["labels"] = names
    if output_dir:
        record["output_dir"] = str(output_dir)
    return record


def load_record(root):
    """The record with schema-2 defaults applied, or ``{}``."""
    if not root:
        return {}
    return project_store.load_project(root)


def save_record(root, record):
    return project_store.save_project(root, record)


def has_record(root):
    """Whether this folder already carries a project record.

    Deliberately different from "the folder exists": the switcher lists
    folders that were merely opened, and the title bar needs to tell a
    real project from a folder someone once looked at.
    """
    path = project_store.project_path(root) if root else None
    return bool(path and osp.isfile(path))


def create(root, name=None, task=None, labels=None, output_dir=None):
    """Write a new project record. Refuses to overwrite an existing one.

    Returns False when the folder is missing, a record is already there,
    or the write failed. The caller can tell those apart with
    :func:`has_record` — the wizard does exactly that, rather than this
    function guessing which message to show.
    """
    if not root or not osp.isdir(str(root)):
        return False
    if has_record(root):
        return False
    return save_record(
        root,
        new_record(
            root,
            name=name,
            task=task,
            labels=labels,
            output_dir=output_dir,
        ),
    )


def rename(root, name):
    """Change the display name; the folder on disk is untouched."""
    record = load_record(root)
    if not record:
        return False
    new_name = normalize_name(name, root)
    if new_name == record.get("name"):
        return True
    record["name"] = new_name
    return save_record(root, record)


def set_task(root, task):
    """Change the declared task kind."""
    record = load_record(root)
    if not record:
        return False
    new_task = normalize_task(task)
    if new_task == record.get("task"):
        return True
    record["task"] = new_task
    return save_record(root, record)


def describe(root):
    """One summary for the UI, tolerant of a missing or damaged record.

    ``has_record`` says whether a record file is really there; the name
    and the task always come back usable (folder name, default task), so
    a caller never has to write its own fallback.
    """
    root = str(root) if root else ""
    record = load_record(root) if root else {}
    return {
        "root": root,
        "name": record.get("name") or default_name(root),
        "task": normalize_task(record.get("task")),
        "has_record": has_record(root),
        "created_at": record.get("created_at") or "",
        "labels": list(record.get("labels") or []),
        "output_dir": record.get("output_dir") or "",
    }


__all__ = [
    "NAME_MAX_LENGTH",
    "TASK_HINTS",
    "TASK_LABELS",
    "create",
    "default_name",
    "describe",
    "has_record",
    "load_record",
    "new_record",
    "normalize_name",
    "normalize_task",
    "rename",
    "save_record",
    "set_task",
    "task_hint",
    "task_label",
]
