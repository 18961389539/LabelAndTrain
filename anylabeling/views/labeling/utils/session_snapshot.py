"""A snapshot of each label file, taken before this session first overwrites it.

The canvas undo stack does not survive a file switch (``canvas.py`` says so
outright), and an auto-save overwrites the only copy on disk a few hundred
milliseconds after an edit. Together that left the worst failure in the tool
with no way back: annotate thirty images, notice on the thirty-first that
the third one lost a row of boxes, and neither Ctrl+Z nor any file on disk
remembers what it looked like.

So the write path takes one cheap copy per (session, label file): the state
the file had when this session first touched it. That is the granularity
that answers "I broke this an hour ago" -- per-edit snapshots would be
hundreds of copies for the same answer, and would fight the 400ms
auto-save debounce for no gain. The run lives in the same
``.label_backups`` namespace the batch tools use, under an ordinary
timestamp name, so it shows up in the existing "从备份恢复标注" picker,
obeys the same retention, and needs no new recovery UI.

Keyed by label directory, not by process: a project switch must not fold two
folders into one run, and a run has to sit inside the folder it snapshots.

Disk cost is bounded by the label files, not the images: at most one copy
per file the session writes, in a run the existing 20-run retention prunes.
Only the current image's label file reaches this path (auto-save, Ctrl+S,
review toggle) -- the bulk review writer does not go through
``file_lifecycle.save_labels``, so a 5000-image batch check does not copy
5000 files.
"""

import os.path as osp
import shutil
import time

from anylabeling.views.labeling.logger import logger

from anylabeling.views.labeling.utils.smart_tools import (
    SESSION_SNAPSHOT_MARKER,
    backup_label_files,
)

#: label_dir -> the run directory this session is filling.
_SESSION_SNAPSHOT_RUNS = {}


def reset_session_snapshots():
    """Forget which runs this session opened (tests, and a project switch)."""
    _SESSION_SNAPSHOT_RUNS.clear()


def snapshot_before_label_write(label_file):
    """Copy ``label_file`` into this session's run, at most once per file.

    Returns the run directory, or ``None`` when there was nothing to copy
    (a file that does not exist yet -- a first save has no earlier state)
    or when the copy failed. A failure never stops the write: losing the
    snapshot is bad, refusing to save the annotation is worse.
    """
    label_file = osp.abspath(str(label_file))
    if not osp.isfile(label_file):
        return None

    label_dir = osp.dirname(label_file)
    run = _SESSION_SNAPSHOT_RUNS.get(label_dir)
    if run is None or not osp.isdir(run):
        run = _open_session_run(label_file, label_dir)
        return run
    return _copy_once(label_file, run)


def _open_session_run(label_file, label_dir):
    run = backup_label_files(
        [label_file], label_dir, time.strftime("%Y%m%d_%H%M%S")
    )
    if run is None:
        return None
    try:
        with open(osp.join(run, SESSION_SNAPSHOT_MARKER), "w") as handle:
            handle.write(
                "The editor wrote this run before it first overwrote a "
                "label file in this session.\n"
            )
    except OSError as exc:
        logger.warning(f"Could not mark the session snapshot run: {exc}")
    _SESSION_SNAPSHOT_RUNS[label_dir] = run
    return run


def _copy_once(label_file, run):
    """Add ``label_file`` to an existing run, unless it is already there."""
    target = osp.join(run, osp.basename(label_file))
    if osp.exists(target):
        return run
    try:
        shutil.copy2(label_file, target)
    except OSError as exc:
        logger.warning(f"Session snapshot failed for {label_file}: {exc}")
    return run
