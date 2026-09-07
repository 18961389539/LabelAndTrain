"""Background checker that reads label-JSON "checked" flags for file rows.

Opening a folder used to block the UI thread for seconds because every
file row synchronously opened its label JSON to look for
``"checked": true`` (the green review dot).  On a 3000-image folder that
single step costs ~9s while scanning+populating the list takes <0.05s.
This module moves that IO to a worker thread and streams results back so
the file panel appears instantly and the dots fill in shortly after.
"""

import os.path as osp
import re
from typing import List, Optional

from PyQt6 import QtCore
from PyQt6.QtCore import QObject, pyqtSignal

from anylabeling.views.labeling.logger import logger

CHECKED_FIELD_PATTERN = re.compile(r'"checked"\s*:\s*(true|false)')


def _label_file_checked(label_file: str) -> bool:
    """Scan a label JSON for its review "checked" flag without full parse."""
    if not osp.exists(label_file):
        return False
    try:
        buffer = ""
        with open(label_file, "r", encoding="utf-8") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                buffer = buffer[-32:] + chunk
                match = CHECKED_FIELD_PATTERN.search(buffer)
                if match:
                    return match.group(1) == "true"
    except Exception:  # noqa: BLE001
        return False
    return False


class LabelCheckWorker(QObject):
    """Checks label files on a background thread, in batches."""

    batch_ready = pyqtSignal(int, list)  # (start_index, [bool, ...])
    finished = pyqtSignal()

    def __init__(
        self,
        label_files: List[str],
        batch_size: int = 200,
        parent=None,
    ):
        super().__init__(parent)
        self.label_files = label_files
        self.batch_size = batch_size
        self._should_stop = False

    def stop(self):
        self._should_stop = True

    def run(self):
        results = []
        for i, label_file in enumerate(self.label_files):
            if self._should_stop:
                break
            results.append(_label_file_checked(label_file))
            if len(results) >= self.batch_size:
                self.batch_ready.emit(i + 1 - len(results), results)
                results = []
        if results:
            start = len(self.label_files) - len(results)
            if not self._should_stop:
                self.batch_ready.emit(start, results)
        self.finished.emit()


class AsyncLabelChecker(QObject):
    """Coordinates one background label-check pass at a time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.thread = None
        self._cleanup_slot = None

    def start(self, label_files: List[str], on_batch=None):
        """Start a background pass.  Any previous pass is stopped first.

        Args:
            label_files: Label JSON paths aligned with the file list rows.
            on_batch: Optional callable(start_index, checked_list) invoked
                from the main thread as batches arrive.
        """
        self.stop()
        self._on_batch = on_batch

        self.thread = QtCore.QThread(self)
        self.worker = LabelCheckWorker(label_files)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        if on_batch is not None:
            self.worker.batch_ready.connect(
                lambda start, checks: self._forward_batch(start, checks)
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
