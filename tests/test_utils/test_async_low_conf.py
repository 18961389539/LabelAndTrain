"""The low-confidence half of the file-row metadata runs in the background."""

import json
import os
import os.path as osp
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtCore, QtWidgets

    from anylabeling.views.labeling.filelist.controller import (
        FileReviewController,
    )
    from anylabeling.views.labeling.filelist.roles import (
        FILE_ANNOTATION_ROLE,
        FILE_LOW_CONF_ROLE,
        FILE_REVIEW_ROLE,
    )
    from anylabeling.views.labeling.schema import REVIEW_UNCHECKED
    from anylabeling.views.labeling.utils.async_label_check import (
        LabelCheckWorker,
        label_file_low_conf,
    )
    from anylabeling.views.labeling.utils.file_list_ops import (
        refresh_file_progress,
    )

    PYQT_AVAILABLE = True
except Exception:  # pragma: no cover - import guard, mirrors sibling tests
    PYQT_AVAILABLE = False


def _write_label(path, score=None, shape_type="rectangle"):
    shape = {
        "label": "defect",
        "shape_type": shape_type,
        "points": [[0, 0], [10, 10]],
    }
    if score is not None:
        shape["score"] = score
    payload = {
        "version": "2.4.0",
        "flags": {},
        "checked": False,
        "review_state": "unchecked",
        "shapes": [shape],
        "imagePath": "a.png",
        "imageData": None,
        "imageHeight": 20,
        "imageWidth": 20,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestLowConfidencePass(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])

    def test_a_scored_box_in_the_band_is_low_confidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = osp.join(tmp, "a.json")
            _write_label(path, 0.3)
            assert label_file_low_conf(path) is True

    def test_a_confident_box_is_not_low_confidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = osp.join(tmp, "a.json")
            _write_label(path, 0.9)
            assert label_file_low_conf(path) is False

    def test_an_unscored_human_box_is_not_low_confidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = osp.join(tmp, "a.json")
            _write_label(path)
            assert label_file_low_conf(path) is False

    def test_calibrated_thresholds_can_flag_a_higher_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = osp.join(tmp, "a.json")
            _write_label(path, 0.6)
            assert label_file_low_conf(path) is False
            assert (
                label_file_low_conf(
                    path, {"defect": {"accept": 0.8, "review": 0.3}}
                )
                is True
            )

    def test_an_unreadable_file_is_not_stamped_clean_or_low(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = osp.join(tmp, "a.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{not json")
            assert label_file_low_conf(path) is False
            assert label_file_low_conf(osp.join(tmp, "missing.json")) is False

    def test_the_worker_emits_review_and_low_confidence_batches(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = []
            for index, score in enumerate((0.3, 0.9, None)):
                path = osp.join(tmp, f"a{index}.json")
                _write_label(path, score)
                files.append(path)

            worker = LabelCheckWorker(files, batch_size=2)
            review_batches = []
            low_batches = []
            finished = []
            worker.batch_ready.connect(
                lambda _start, rows: review_batches.extend(rows)
            )
            worker.low_conf_ready.connect(
                lambda _start, flags: low_batches.extend(flags)
            )
            worker.finished.connect(lambda: finished.append(True))

            worker.run()

            assert len(review_batches) == 3
            assert low_batches == [True, False, False]
            assert finished == [True]

    def test_the_batch_controller_sets_the_row_role(self):
        class _List:
            def __init__(self, items):
                self.items = items

            def item(self, row):
                return self.items[row]

        class _Widget:
            def __init__(self, items):
                self.file_list_widget = _List(items)
                self.refreshed = 0
                self._syncing_file_item = False

            def _refresh_file_progress(self):
                self.refreshed += 1

        items = [
            QtWidgets.QListWidgetItem("a.png"),
            QtWidgets.QListWidgetItem("b.png"),
        ]
        widget = _Widget(items)
        FileReviewController(widget).apply_low_conf_batch(0, [True, False])

        assert items[0].data(FILE_LOW_CONF_ROLE) is True
        assert items[1].data(FILE_LOW_CONF_ROLE) is False
        assert widget.refreshed == 1

    def test_progress_shows_a_placeholder_until_the_pass_finishes(self):
        class _Combo:
            def currentText(self):
                return "全部"

        class _Widget:
            def __init__(self, items):
                self.file_list_widget = type(
                    "L",
                    (),
                    {
                        "count": lambda self: len(items),
                        "item": lambda self, row: items[row],
                    },
                )()
                self.file_progress_label = QtWidgets.QLabel()
                self.file_filter_combo = _Combo()
                self._file_item_annotation_checked = lambda item: bool(
                    item.data(QtCore.Qt.ItemDataRole.UserRole)
                )
                self._load_active_thresholds = lambda: {}
                self._low_conf_scan_pending = True

        item = QtWidgets.QListWidgetItem("a.png")
        item.setData(FILE_ANNOTATION_ROLE, True)
        item.setData(FILE_REVIEW_ROLE, REVIEW_UNCHECKED)
        item.setData(FILE_LOW_CONF_ROLE, True)
        widget = _Widget([item])

        refresh_file_progress(widget)
        assert "待复核 …" in widget.file_progress_label.text()

        widget._low_conf_scan_pending = False
        refresh_file_progress(widget)
        assert "待复核 1" in widget.file_progress_label.text()
