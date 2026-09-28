"""Auto-save is debounced: schedule, flush, and explicit-save wins.

``set_dirty()`` used to run a full mkstemp+fsync+replace cycle on *every*
edit -- on a mechanical or network drive that is a visible stutter per drag
step, and it amplified the keep_prev pollution path. Now each edit arms a
~400ms single-shot timer; the write lands once, and every path that leaves
the image (switching, closing, exporting, explicit save) flushes or
supersedes it first.
"""

import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets

    PYQT_AVAILABLE = True
except Exception:  # noqa: BLE001
    PYQT_AVAILABLE = False

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
TEMPLATE_CONFIG = os.path.join(
    REPO_ROOT, "anylabeling", "configs", "jllabeling_config.yaml"
)


def build_labeling_widget(filename=None):
    """Construct the real widget headlessly (same hooks as test_widget_wiring)."""
    from anylabeling import config as app_config
    from anylabeling.views.labeling.label_widget import LabelingWidget

    app_config.current_config_file = TEMPLATE_CONFIG
    LabelingWidget.menu = lambda self, title: QtWidgets.QMenu(title)
    parent = QtWidgets.QWidget()
    return LabelingWidget(parent, filename=filename), parent


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestAutoSaveDebounce(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        from PIL import Image

        self.tmp = tempfile.TemporaryDirectory()
        self.image = os.path.join(self.tmp.name, "a.png")
        self.label = os.path.join(self.tmp.name, "a.json")
        Image.new("RGB", (20, 20), "white").save(self.image)

        self.widget, self.parent = build_labeling_widget()
        main = QtWidgets.QMainWindow()
        self.widget.parent = SimpleNamespace(parent=main)
        self.widget.output_dir = self.tmp.name
        self.widget.image_dir = self.tmp.name
        self.widget._config["auto_save"] = True
        self.widget.load_file(self.image)

    def tearDown(self):
        for attr in ("_auto_save_feedback_timer", "_auto_save_timer"):
            timer = getattr(self.widget, attr, None)
            if timer is not None:
                timer.stop()
        self.widget.parent = None
        self.tmp.cleanup()

    def _on_disk(self):
        with open(self.label, "r", encoding="utf-8") as handle:
            return [s["label"] for s in json.load(handle)["shapes"]]

    def test_set_dirty_does_not_write_immediately(self):
        self.widget.set_dirty()

        self.assertFalse(
            os.path.exists(self.label),
            "set_dirty() under auto_save still wrote on the same edit",
        )
        self.assertTrue(self.widget._auto_save_pending)
        self.assertTrue(self.widget._auto_save_timer.isActive())
        self.assertTrue(self.widget.dirty)

    def test_flush_writes_and_clears_the_pending_state(self):
        self.widget.set_dirty()

        self.assertTrue(self.widget.flush_pending_auto_save())

        self.assertTrue(os.path.exists(self.label))
        self.assertFalse(self.widget._auto_save_pending)
        self.assertFalse(self.widget.dirty)
        self.assertFalse(self.widget._auto_save_timer.isActive())

    def test_rapid_edits_collapse_into_one_write(self):
        with mock.patch.object(
            self.widget, "save_labels", return_value=True
        ) as save:
            for _ in range(5):
                self.widget.set_dirty()
            self.assertEqual(save.call_count, 0)

            self.widget.flush_pending_auto_save()
            self.assertEqual(save.call_count, 1)

    def test_timer_callback_writes_once(self):
        self.widget.set_dirty()
        self.widget._flush_auto_save()

        self.assertTrue(os.path.exists(self.label))
        # A second callback with nothing pending is a no-op.
        self.widget._flush_auto_save()
        self.assertFalse(self.widget.dirty)

    def test_explicit_save_supersedes_the_scheduled_write(self):
        with mock.patch.object(
            self.widget, "save_labels", return_value=True
        ) as save:
            self.widget.set_dirty()
            self.widget._save_file(self.label)
            self.assertEqual(save.call_count, 1)
            self.assertFalse(self.widget._auto_save_pending)
            # The timer must not fire afterwards and write again.
            self.widget._flush_auto_save()
            self.assertEqual(save.call_count, 1)

    def test_may_continue_flushes_instead_of_asking(self):
        self.widget.set_dirty()

        with mock.patch.object(QtWidgets.QMessageBox, "question") as question:
            self.assertTrue(self.widget.may_continue(silent=True))

        question.assert_not_called()
        self.assertTrue(os.path.exists(self.label))

    def test_autosave_off_keeps_the_plain_dirty_flow(self):
        self.widget._config["auto_save"] = False

        self.widget.set_dirty()

        self.assertFalse(os.path.exists(self.label))
        self.assertFalse(self.widget._auto_save_pending)
        self.assertTrue(self.widget.dirty)

    def test_flush_with_nothing_pending_reports_success(self):
        self.assertTrue(self.widget.flush_pending_auto_save())


if __name__ == "__main__":
    unittest.main()
