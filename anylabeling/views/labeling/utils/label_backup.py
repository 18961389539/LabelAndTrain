"""Label-file backups under ``.label_backups``.

Every path that rewrites labels outside the canvas undo stack snapshots
the pre-change files here: the editor's session snapshot, the bulk tools'
delete/pre-label/rename batches, and 从备份恢复标注. Keeping the engine in
its own module lets ``session_snapshot`` depend on it without importing
the whole smart-tools UI module (which imports Qt widgets and every smart
action).
"""

import os
import os.path as osp
import re
import shutil
import time

from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils._io import copy_file_atomic

BACKUP_ROOT_NAME = ".label_backups"
# ``20260923_101112``, with a ``_1`` suffix when two snapshots land in the same
# second -- both stay prunable, and neither merges into the other.
BACKUP_STAMP_PATTERN = re.compile(r"\d{8}_\d{6}(_\d+)?$")
# Files outside the canvas undo stack can only come back from these snapshots.
BACKUP_KEEP_RUNS = 20
# ``.session-snapshot`` marks a run the editor wrote on its own, before it
# overwrote a label file (see utils/session_snapshot.py). The suffix is
# .txt on purpose: list_label_backups() counts .json files to tell the user
# how many labels a run would put back, and the marker must not inflate it.
SESSION_SNAPSHOT_MARKER = ".session-snapshot"


def is_session_snapshot(run_path):
    """True for runs the editor wrote itself before a label overwrite."""
    return osp.isfile(osp.join(run_path, SESSION_SNAPSHOT_MARKER))


def _prune_backup_runs(backup_root):
    """Drop our own oldest timestamped backup runs beyond the retention."""
    try:
        names = [
            name
            for name in os.listdir(backup_root)
            if BACKUP_STAMP_PATTERN.fullmatch(name)
            and osp.isdir(osp.join(backup_root, name))
        ]
    except OSError:
        return
    for name in sorted(names, reverse=True)[BACKUP_KEEP_RUNS:]:
        try:
            shutil.rmtree(osp.join(backup_root, name))
        except OSError as exc:
            logger.warning(f"Could not prune label backup run {name}: {exc}")


def _new_backup_dir(backup_root, stamp):
    """Reserve an empty run directory, so same-second runs do not overwrite."""
    candidate = stamp
    suffix = 1
    while osp.isdir(osp.join(backup_root, candidate)):
        candidate = f"{stamp}_{suffix}"
        suffix += 1
    return osp.join(backup_root, candidate)


def backup_label_files(label_files, label_dir, stamp):
    """Copy the label files that are about to change into a backup run.

    Returns ``None`` when the backup could not be completed, which the caller
    must treat as "do not change anything".
    """
    backup_root = osp.join(label_dir, BACKUP_ROOT_NAME)
    destination = None
    created = False
    try:
        os.makedirs(backup_root, exist_ok=True)
        destination = _new_backup_dir(backup_root, stamp)
        os.makedirs(destination)
        created = True
        for label_file in label_files:
            shutil.copy2(
                label_file, osp.join(destination, osp.basename(label_file))
            )
    except OSError as exc:
        logger.warning(f"Label backup failed: {exc}")
        # A half-filled run looks restorable in the picker while holding
        # only some of the labels -- worse than no run at all, because the
        # user believes the files it does not contain are covered too.
        if created:
            try:
                shutil.rmtree(destination)
            except OSError as cleanup_exc:
                logger.warning(
                    f"Could not remove the partial label backup "
                    f"{destination}: {cleanup_exc}"
                )
        return None
    _prune_backup_runs(backup_root)
    return destination


def list_label_backups(label_dir):
    """Snapshot runs under ``.label_backups``, newest first.

    Entries are ``(name, path, file_count)``: the picker needs to say what a
    run would put back before the user commits to overwriting labels.
    """
    backup_root = osp.join(label_dir or "", BACKUP_ROOT_NAME)
    try:
        names = os.listdir(backup_root)
    except OSError:
        return []
    runs = []
    for name in names:
        path = osp.join(backup_root, name)
        if not BACKUP_STAMP_PATTERN.fullmatch(name) or not osp.isdir(path):
            continue
        try:
            count = len([f for f in os.listdir(path) if f.endswith(".json")])
        except OSError:
            continue
        runs.append((name, path, count))
    runs.sort(key=lambda run: run[0], reverse=True)
    return runs


def plan_backup_restore(backup_dir, label_dir, skip_files=None):
    """Map a snapshot's jsons onto the label files they came from."""
    skipped = {osp.normpath(osp.abspath(path)) for path in (skip_files or ())}
    plan = {}
    try:
        names = sorted(os.listdir(backup_dir))
    except OSError:
        return plan
    for name in names:
        if not name.endswith(".json"):
            continue
        target = osp.join(label_dir, name)
        if osp.normpath(osp.abspath(target)) in skipped:
            continue
        plan[target] = osp.join(backup_dir, name)
    return plan


def restore_label_backup(backup_dir, label_dir, skip_files=None):
    """Copy a bulk-deletion snapshot back over the labels it came from.

    What gets overwritten is snapshotted first, so choosing the wrong run is
    itself reversible: the newer run in the same list is the pre-restore state.
    """
    result = {
        "restored": 0,
        "skipped": 0,
        "undo_dir": None,
        "backup_failed": False,
    }
    plan = plan_backup_restore(backup_dir, label_dir, skip_files)
    result["skipped"] += len(skip_files or ())
    if not plan:
        return result
    present = [target for target in plan if osp.isfile(target)]
    result["undo_dir"] = backup_label_files(
        present, label_dir, time.strftime("%Y%m%d_%H%M%S")
    )
    if result["undo_dir"] is None:
        result["backup_failed"] = True
        result["skipped"] += len(plan)
        return result
    for target, source in plan.items():
        try:
            copy_file_atomic(source, target)
        except OSError as exc:
            logger.warning(f"Label restore failed for {target}: {exc}")
            result["skipped"] += 1
            continue
        result["restored"] += 1
    return result
