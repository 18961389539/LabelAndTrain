"""Run provenance and dataset-copy maintenance for the training dialog.

These two jobs write beside a finished run rather than paint the wizard:
``run_meta.json`` ties a completed or stopped run to the annotations and
arguments it saw, and the cleanup offer bounds the dataset copies every
Windows training leaves behind. They live here so the dialog keeps the
wiring (its stubs) without owning the file formats and the prune policy.
"""

from __future__ import annotations

import os
import time

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QMessageBox

from anylabeling.services.auto_training.ultralytics._io import (
    save_json_atomic,
)
from anylabeling.services.auto_training.ultralytics.config import (
    get_dataset_path,
)
from anylabeling.services.auto_training.ultralytics.general import (
    collect_dataset_runs,
    directory_size,
    file_sha1,
    plan_dataset_prune,
    prune_datasets,
)
from anylabeling.services.auto_training.ultralytics.utils import (
    parse_training_metrics,
)
from anylabeling.views.labeling.logger import logger

KEEP_DATASET_BUILDS = 5
MIN_CLEANUP_OFFER_BYTES = 100 * 1024 * 1024
#: Shared with the dataset-skip report in the dialog: the same short list
#: keeps both lists readable.
MAX_LISTED_SKIPS = 5


def offer_dataset_cleanup(dialog):
    """Ask before dropping old dataset builds the loop left behind.

    Every training copies the images on Windows and never reclaims them, so
    without this the folder only grows. The build the finished run used is
    excluded regardless of age.
    """
    task_root = os.path.join(
        get_dataset_path(), (dialog.selected_task_type or "").lower()
    )
    manifest = getattr(dialog, "_last_dataset_manifest", None) or {}
    current = None
    if manifest.get("data_yaml"):
        current = os.path.dirname(manifest["data_yaml"])
    candidates = plan_dataset_prune(
        collect_dataset_runs(task_root), KEEP_DATASET_BUILDS, current
    )
    if not candidates:
        return
    size = sum(directory_size(path) for path in candidates)
    if size < MIN_CLEANUP_OFFER_BYTES:
        return

    # Name the directories: "5 old builds" is not something anyone can
    # check before agreeing to delete them.
    listed = list(candidates[:MAX_LISTED_SKIPS])
    extra = len(candidates) - len(listed)
    body = [
        QCoreApplication.translate(
            "LabelingWidget",
            "Training left dataset copies taking %1 across %2 old directories.",
        )
        .replace("%1", f"{size / (1024 * 1024):.1f} MB")
        .replace("%2", str(len(candidates))),
        "",
    ]
    body.extend(f"  {os.path.basename(path)}" for path in listed)
    if extra > 0:
        body.append(
            "  "
            + QCoreApplication.translate(
                "LabelingWidget", "... and %1 more"
            ).replace("%1", str(extra))
        )
    body.extend(
        [
            "",
            QCoreApplication.translate(
                "LabelingWidget",
                "Delete the old copies beyond this run? The most recent %1 are kept.",
            ).replace("%1", str(KEEP_DATASET_BUILDS)),
        ]
    )

    answer = QMessageBox.question(
        dialog,
        QCoreApplication.translate(
            "LabelingWidget", "Clean up old dataset copies"
        ),
        "\n".join(body),
    )
    if answer != QMessageBox.StandardButton.Yes:
        return

    deleted, freed, failed = prune_datasets(
        task_root, KEEP_DATASET_BUILDS, current
    )
    dialog.append_training_log(
        QCoreApplication.translate(
            "LabelingWidget", "Cleaned %1 dataset copies, freeing %2 MB."
        )
        .replace("%1", str(len(deleted)))
        .replace("%2", f"{freed / (1024 * 1024):.1f}")
    )
    if failed:
        dialog.append_training_log(
            QCoreApplication.translate(
                "LabelingWidget",
                "%1 directories could not be deleted (possibly in use).",
            ).replace("%1", str(len(failed)))
        )


def write_run_metadata(dialog, status="completed"):
    """Record what this run trained on, beside its weights.

    The dataset is a mutable set of label JSONs that keeps being edited
    after training, so without this snapshot a completed run cannot be
    tied back to the annotations and arguments that produced it.

    ``status`` distinguishes a finished run from one the user stopped.
    A stopped run writes this too: it has a ``results.csv``, a resumable
    ``last.pt``, and it is the very run someone wants to compare against
    the full one — leaving it out of the history made "round 2, interrupted
    vs round 3, finished" unanswerable.
    """
    project_path = dialog.current_project_path
    if not project_path or not os.path.isdir(project_path):
        return None

    manifest = getattr(dialog, "_last_dataset_manifest", None) or {}
    dataset_dir = os.path.dirname(manifest.get("data_yaml") or "") or None
    from anylabeling.views.labeling.project import label_dir_for_dataset

    label_dir = label_dir_for_dataset(
        getattr(dialog, "output_dir", None),
        getattr(dialog, "image_list", None),
    )
    manifest_path = (
        os.path.join(dataset_dir, "manifest.json") if dataset_dir else None
    )
    weights = os.path.join(project_path, "weights", "best.pt")
    metrics = parse_training_metrics(os.path.join(project_path, "results.csv"))
    started_at = getattr(dialog, "_training_started_at", None)
    meta = {
        "schema": 1,
        "task": dialog.selected_task_type,
        "status": status,
        "project": os.path.dirname(project_path),
        "name": os.path.basename(project_path),
        "started_at": (
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_at))
            if started_at
            else None
        ),
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "weights": {
            "path": weights if os.path.isfile(weights) else None,
            "sha1": file_sha1(weights),
        },
        "train_args": dict(getattr(dialog, "_last_train_args", None) or {}),
        "dataset": {
            "dir": dataset_dir,
            "label_dir": label_dir,
            "manifest": manifest_path,
            "manifest_sha1": (
                file_sha1(manifest_path) if manifest_path else None
            ),
            "seed": manifest.get("seed"),
            "classes": manifest.get("classes"),
            "counts": manifest.get("counts"),
        },
        "metrics": (
            None
            if metrics is None
            else {
                "loss": metrics[0],
                "map50": metrics[1],
                "epochs": metrics[2],
            }
        ),
    }

    meta_path = os.path.join(project_path, "run_meta.json")
    try:
        save_json_atomic(meta, meta_path)
    except OSError as e:  # noqa: BLE001
        logger.warning(f"Failed to write run metadata: {e}")
        return None
    return meta_path
