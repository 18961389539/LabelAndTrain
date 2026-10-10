"""Per-project settings kept beside the data instead of in the global config.

The app has one `.xanylabelingrc` for everything, so opening a second dataset
inherits the first one's choices. This module holds the few settings that are
genuinely per-dataset. The file lives in the label folder, so it travels with
the data and a moved or synced folder keeps its settings.

It is created lazily: browsing a folder never writes into it.
"""

import os.path as osp
import random
import time

from anylabeling.views.labeling.utils._io import load_json, save_json

PROJECT_DIR_NAME = ".jllabel"
PROJECT_FILE_NAME = "project.json"
SCHEMA = 2

#: The task kinds a project can declare. Deliberately a copy of the
#: training side's ``TASK_TYPES`` rather than an import: annotating must
#: not depend on the training package (a project can be labeled and never
#: trained), and a test pins the two sets together so they cannot drift.
TASK_TYPES = ("Detect", "Segment", "Pose", "Classify")
DEFAULT_TASK = "Detect"


def project_path(label_dir):
    if not label_dir:
        return None
    return osp.join(label_dir, PROJECT_DIR_NAME, PROJECT_FILE_NAME)


def label_dir_for_dataset(output_dir=None, image_list=None, filename=None):
    """The folder that actually holds the label JSONs of a dataset."""
    if output_dir:
        return output_dir
    if image_list:
        return osp.dirname(image_list[0])
    if filename:
        return osp.dirname(filename)
    return None


def _record_timestamp(label_dir):
    """The record file's own mtime, or now when it cannot be read.

    Used as ``created_at`` for records written before schema 2: the file
    time is the closest thing to a real creation date that survived, and
    it beats stamping every old project with "today".
    """
    try:
        return time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(osp.getmtime(project_path(label_dir))),
        )
    except (OSError, TypeError, ValueError):
        return time.strftime("%Y-%m-%d %H:%M:%S")


def _with_defaults(data, label_dir):
    """Complete a record to schema 2 — in memory, never on disk.

    Schema 1 knew only ``labels`` / ``output_dir`` / ``split_seed``; the
    name, the task kind and the creation date arrived with schema 2. The
    defaults are filled here rather than at each call site, because three
    call sites each inventing their own answer to "what is this project
    called" is exactly how the two recent-project lists drifted apart.
    Existing values are never overwritten, and nothing is written:
    browsing a dataset stays read-only, and the new fields land on disk
    with whatever save comes next.
    """
    # A whitespace-only name counts as missing: the title bar would
    # otherwise show a gap where the project name should be.
    if not str(data.get("name") or "").strip():
        data["name"] = osp.basename(osp.normpath(str(label_dir))) or ""
    if data.get("task") not in TASK_TYPES:
        data["task"] = DEFAULT_TASK
    if not data.get("created_at"):
        data["created_at"] = _record_timestamp(label_dir)
    data["schema"] = SCHEMA
    return data


def load_project(label_dir):
    """Return the project record, or ``{}`` when there is none.

    A record written before schema 2 comes back completed in memory; the
    file itself is left untouched until the next save.
    """
    path = project_path(label_dir)
    if not path or not osp.isfile(path):
        return {}
    try:
        data = load_json(path)
    except (OSError, ValueError):
        # A damaged settings file must not block annotating or training;
        # fall back to defaults and let the next write repair it.
        return {}
    if not isinstance(data, dict):
        return {}
    return _with_defaults(data, label_dir)


def save_project(label_dir, data):
    path = project_path(label_dir)
    if not path:
        return False
    payload = dict(data)
    payload["schema"] = SCHEMA
    try:
        save_json(payload, path)
    except OSError:
        return False
    return True


def get_or_create_split_seed(label_dir):
    """Read the pinned split seed, creating one on first use.

    Returning the same seed across rounds is what makes two runs comparable:
    with a fresh random split every round, an mAP change can just be a change
    in which images sat in val.
    """
    project = load_project(label_dir)
    seed = project.get("split_seed")
    if isinstance(seed, int) and seed > 0:
        return seed, False
    seed = random.SystemRandom().randrange(1, 2**31 - 1)
    project["split_seed"] = seed
    if not save_project(label_dir, project):
        return seed, False
    return seed, True
