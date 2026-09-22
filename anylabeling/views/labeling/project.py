"""Per-project settings kept beside the data instead of in the global config.

The app has one `.xanylabelingrc` for everything, so opening a second dataset
inherits the first one's choices. This module holds the few settings that are
genuinely per-dataset. The file lives in the label folder, so it travels with
the data and a moved or synced folder keeps its settings.

It is created lazily: browsing a folder never writes into it.
"""

import os.path as osp
import random

from anylabeling.views.labeling.utils._io import load_json, save_json

PROJECT_DIR_NAME = ".jllabel"
PROJECT_FILE_NAME = "project.json"
SCHEMA = 1


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


def load_project(label_dir):
    """Return the project record, or ``{}`` when there is none."""
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
    data.setdefault("schema", SCHEMA)
    return data


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
