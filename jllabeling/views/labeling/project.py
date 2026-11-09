# flake8: noqa
"""Compatibility re-exports for :mod:`jllabeling.core.projects.project`."""

from jllabeling.core.io import load_json, save_json
from jllabeling.core.projects.project import (
    DEFAULT_TASK,
    PROJECT_DIR_NAME,
    PROJECT_FILE_NAME,
    SCHEMA,
    TASK_TYPES,
    get_or_create_split_seed,
    label_dir_for_dataset,
    load_project,
    project_path,
    save_project,
)
