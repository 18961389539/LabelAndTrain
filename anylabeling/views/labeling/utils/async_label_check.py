"""Background checker that reads label-JSON "checked" flags for file rows.

Opening a folder used to block the UI thread for seconds because every
file row synchronously opened its label JSON to look for
``"checked": true`` (the green review dot).  On a 3000-image folder that
single step costs ~9s while scanning+populating the list takes <0.05s.
This module moves that IO to a worker thread and streams results back so
the file panel appears instantly and the dots fill in shortly after.
"""

import json
import os.path as osp
import re
from typing import List, Optional

from PyQt6 import QtCore
from PyQt6.QtCore import QObject, pyqtSignal

from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.schema import (
    REVIEW_CONFIRMED,
    REVIEW_REJECTED,
    REVIEW_UNCHECKED,
)
from .active_learning import needs_review
from .quality import shapes_have_low_confidence

CHECKED_FIELD_PATTERN = re.compile(r'"checked"\s*:\s*(true|false)')
REVIEW_STATE_PATTERN = re.compile(
    r'"review_state"\s*:\s*"(unchecked|confirmed|rejected)"'
)
REVIEWED_AT_PATTERN = re.compile(r'"reviewed_at"\s*:\s*"([^"]*)"')
REVIEW_NOTE_PATTERN = re.compile(
    r'"review_note"\s*:\s*(?:"((?:[^"\\]|\\.)*)"|null)'
)

#: The review header (state / timestamp / reason) is written before
#: ``shapes``, so a bounded head read always holds all three.
HEAD_SCAN_BYTES = 8192
HEAD_SCAN_LIMIT = 65536


def label_file_review_info(label_file):
    """``(review_state, reviewed_at, review_note)`` from one head read.

    All three fields sit together at the top of the template, ahead of
    ``shapes``, so a bounded read of the head answers every question the
    file row has -- and that bound is what keeps this affordable on a
    folder of thousands of rows. A full parse per row is the cost the
    background checker exists to avoid.
    """
    if not osp.exists(label_file):
        return REVIEW_UNCHECKED, None, None
    try:
        with open(label_file, "r", encoding="utf-8") as f:
            head = ""
            while len(head) < HEAD_SCAN_LIMIT:
                chunk = f.read(HEAD_SCAN_BYTES)
                if not chunk:
                    break
                head += chunk
                if '"shapes"' in head:
                    break
    except Exception:  # noqa: BLE001
        return REVIEW_UNCHECKED, None, None

    match = REVIEW_STATE_PATTERN.search(head)
    if match:
        state = match.group(1)
    else:
        match = CHECKED_FIELD_PATTERN.search(head)
        state = (
            REVIEW_CONFIRMED
            if match and match.group(1) == "true"
            else REVIEW_UNCHECKED
        )
    match = REVIEWED_AT_PATTERN.search(head)
    reviewed_at = (match.group(1) or None) if match else None
    match = REVIEW_NOTE_PATTERN.search(head)
    note = (match.group(1) or None) if match else None
    if state != REVIEW_REJECTED:
        # A reason only means something on a rejected file; a hand-edited
        # JSON must not leak one onto a confirmed row's tooltip.
        note = None
    return state, reviewed_at, note


def label_file_low_conf(label_file, thresholds=None):
    """Whether a label file holds a box the review band flags as uncertain.

    This is the expensive half of the row metadata: it needs the shapes, not
    just the review header. The background checker runs it after the cheap
    review pass, so opening a folder no longer parses every JSON on the UI
    thread; an unreadable file is not low-confidence here (data_audit and
    export_check report it as corrupted separately).
    """
    try:
        # Close the file before parsing: json.load() would keep it open for
        # the whole parse, and on Windows that window is enough for a delete
        # or a temp-folder cleanup to fail with "file in use".
        with open(label_file, "r", encoding="utf-8") as handle:
            raw = handle.read()
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    shapes = data.get("shapes")
    if thresholds:
        return needs_review(shapes, thresholds=thresholds)
    return shapes_have_low_confidence(shapes)


def _label_file_review_state(label_file: str) -> str:
    """Scan a label JSON for its review state without a full parse.

    ``review_state`` sits right after ``checked`` in the template, so it is
    always in the first few bytes; files written before that field existed
    fall back on the legacy ``checked`` flag.
    """
    return label_file_review_info(label_file)[0]


def _label_file_checked(label_file: str) -> bool:
    """Scan a label JSON for its review "checked" flag without full parse."""
    return _label_file_review_state(label_file) == REVIEW_CONFIRMED


class LabelCheckWorker(QObject):
    """Checks label files on a background thread, in batches.

    Two passes share one job: the cheap review-header pass first (the dots
    appear quickly), then the shape-scoring pass that fills the
    low-confidence roles. Both are off the UI thread; the low-confidence
    count in the progress label is allowed to stay ``…`` until the second
    pass finishes.
    """

    batch_ready = pyqtSignal(
        int, list
    )  # (start_index, [(state, ts, note), ...])
    low_conf_ready = pyqtSignal(int, list)  # (start_index, [bool, ...])
    finished = pyqtSignal()

    def __init__(
        self,
        label_files: List[str],
        batch_size: int = 200,
        thresholds=None,
        parent=None,
    ):
        super().__init__(parent)
        self.label_files = label_files
        self.batch_size = batch_size
        self.thresholds = thresholds
        self._should_stop = False

    def stop(self):
        self._should_stop = True

    def run(self):
        results = []
        for i, label_file in enumerate(self.label_files):
            if self._should_stop:
                break
            results.append(label_file_review_info(label_file))
            if len(results) >= self.batch_size:
                self.batch_ready.emit(i + 1 - len(results), results)
                results = []
        if results and not self._should_stop:
            self.batch_ready.emit(
                len(self.label_files) - len(results), results
            )

        low_conf = []
        batch_start = 0
        for i, label_file in enumerate(self.label_files):
            if self._should_stop:
                break
            low_conf.append(label_file_low_conf(label_file, self.thresholds))
            if len(low_conf) >= self.batch_size:
                self.low_conf_ready.emit(batch_start, low_conf)
                batch_start = i + 1
                low_conf = []
        if low_conf and not self._should_stop:
            self.low_conf_ready.emit(batch_start, low_conf)
        self.finished.emit()


class AsyncLabelChecker(QObject):
    """Coordinates one background label-check pass at a time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.thread = None
        self._cleanup_slot = None

    def start(
        self,
        label_files: List[str],
        on_batch=None,
        on_low_conf=None,
        thresholds=None,
    ):
        """Start a background pass.  Any previous pass is stopped first.

        Args:
            label_files: Label JSON paths aligned with the file list rows.
            on_batch: Optional callable(start_index, checked_list) invoked
                from the main thread as review batches arrive.
            on_low_conf: Optional callable(start_index, flags) for the
                shape-scoring pass.
            thresholds: Per-class calibration for the low-confidence pass.
        """
        self.stop()
        self._on_batch = on_batch
        self._on_low_conf = on_low_conf

        self.thread = QtCore.QThread(self)
        self.worker = LabelCheckWorker(label_files, thresholds=thresholds)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        if on_batch is not None:
            self.worker.batch_ready.connect(
                lambda start, checks: self._forward_batch(start, checks)
            )
        if on_low_conf is not None:
            self.worker.low_conf_ready.connect(
                lambda start, flags: self._forward_low_conf(start, flags)
            )
        self.worker.finished.connect(self._cleanup)
        self.thread.start()

    def _forward_batch(self, start, checks):
        cb = getattr(self, "_on_batch", None)
        if cb is not None:
            try:
                cb(start, checks)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Label-check batch callback failed: {e}")

    def _forward_low_conf(self, start, flags):
        cb = getattr(self, "_on_low_conf", None)
        if cb is not None:
            try:
                cb(start, flags)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    f"Label-check low-confidence callback failed: {e}"
                )

    def _cleanup(self):
        try:
            if self.worker is not None:
                self.worker.finished.disconnect(self._cleanup)
        except (RuntimeError, TypeError):
            pass
        thread, worker = self.thread, self.worker
        self.thread = None
        self.worker = None
        if thread is not None:
            try:
                if thread.isRunning():
                    thread.quit()
                    if not thread.wait(3000):
                        thread.terminate()
                        thread.wait()
                thread.deleteLater()
            except RuntimeError:
                pass
        if worker is not None:
            try:
                worker.deleteLater()
            except RuntimeError:
                pass

    def stop(self):
        if self.worker is not None:
            try:
                self.worker.stop()
            except RuntimeError:
                pass
        self._cleanup()
