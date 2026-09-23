import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtCore, QtWidgets

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
TEMPLATE_CONFIG = os.path.join(
    REPO_ROOT, "anylabeling", "configs", "jllabeling_config.yaml"
)


def build_labeling_widget(filename=None):
    """Construct the real widget headlessly.

    Needs two hooks: it reaches for ``self.parent.parent.menuBar()`` through
    ``menu()``, and ``get_config()`` returns ``None`` unless the config module
    already knows which yaml to read.
    """
    from anylabeling import config as app_config
    from anylabeling.views.labeling.label_widget import LabelingWidget

    app_config.current_config_file = TEMPLATE_CONFIG
    LabelingWidget.menu = lambda self, title: QtWidgets.QMenu(title)
    parent = QtWidgets.QWidget()
    return LabelingWidget(parent, filename=filename), parent


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestWidgetWiring(unittest.TestCase):
    """Guards against config keys and menu entries that bind to nothing."""

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])
        cls.widget, cls.parent = build_labeling_widget()

    def test_review_shortcut_is_bound_to_a_qaction(self):
        action = self.widget.actions.mark_rejected_and_next
        shortcuts = [s.toString() for s in action.shortcuts()]
        self.assertIn("Ctrl+Shift+K", shortcuts)
        self.assertFalse(action.isEnabled())

    def test_every_smart_tool_entry_exists(self):
        titles = [
            menu.text()
            for menu in self.widget.menus.smart_tools.actions()
            if menu.text()
        ]
        self.assertEqual(len(titles), 12, titles)
        self.assertTrue(
            any(title.startswith("10.") for title in titles),
            titles,
        )
        self.assertTrue(
            any(title.startswith("11.") for title in titles),
            titles,
        )

    def test_train_menu_offers_run_history(self):
        # Like the smart-tools entries, this action is menu-only and is not
        # part of the actions Struct; what must not drift is the menu item and
        # its handler on the widget.
        self.assertTrue(callable(self.widget.show_run_history))
        texts = [
            menu.text()
            for menu in self.widget.menus.train.actions()
            if menu.text()
        ]
        self.assertIn("实验历史", texts)
        self.assertIn("Ultralytics", texts)

    def test_run_history_handler_opens_the_dialog_with_the_label_dir(self):
        # exec() blocks, so the handler is verified by capturing the dialog
        # instance it builds rather than showing it.
        import shutil
        import tempfile

        import anylabeling.views.training.run_history_dialog as module

        original_root = module.get_default_project_dir
        original_exec = module.RunHistoryDialog.exec
        opened = []
        runs_root = tempfile.mkdtemp()
        module.get_default_project_dir = lambda: runs_root
        module.RunHistoryDialog.exec = lambda self, *a: opened.append(self)
        try:
            self.widget.show_run_history()
        finally:
            module.get_default_project_dir = original_root
            module.RunHistoryDialog.exec = original_exec
            shutil.rmtree(runs_root, ignore_errors=True)
        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0].label_dir, self.widget._active_label_dir())

    def test_model_identity_is_safe_without_a_loaded_model(self):
        self.assertIsNone(self.widget._current_model_identity())

    def test_classification_confirm_action_is_bound_and_off_by_default(self):
        action = self.widget.actions.confirm_classification
        self.assertFalse(action.isEnabled())
        # Deliberately no shortcut: an advertised key with no binding is the
        # drift this test file exists to catch, so do not add one here.
        self.assertEqual(list(action.shortcuts()), [])
        texts = [
            menu.text()
            for menu in self.widget.menus.file.actions()
            if menu.text()
        ]
        self.assertTrue(
            any("确认分类建议" in text for text in texts),
            texts,
        )

    def test_no_suggestion_until_predictions_are_recorded(self):
        self.widget.other_data = {}
        self.assertEqual(self.widget._classification_suggestions(), ([], None))
        self.widget._update_classification_action()
        self.assertFalse(
            self.widget.actions.confirm_classification.isEnabled()
        )

        self.widget.other_data = {
            "predictions": {
                "model": "run_07_best",
                "classes": [{"label": "cat", "score": 0.91}],
            }
        }
        suggestions, model_name = self.widget._classification_suggestions()
        self.assertEqual(model_name, "run_07_best")
        self.assertEqual(suggestions[0]["label"], "cat")

    def test_review_state_reader_defaults_to_unchecked(self):
        self.widget.other_data = {}
        self.assertEqual(self.widget._current_review_state(), "unchecked")
        self.widget.other_data = {"checked": True}
        self.assertEqual(self.widget._current_review_state(), "confirmed")
        self.widget.other_data = {"review_state": "rejected", "checked": True}
        self.assertEqual(self.widget._current_review_state(), "rejected")


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestStaleCleanupOnOpenFile(unittest.TestCase):
    """Deleting a stale box must keep disk and canvas in agreement."""

    def setUp(self):
        import tempfile

        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        from PIL import Image

        from anylabeling.views.labeling.utils import smart_tools

        self.smart_tools = smart_tools
        self.tmp = tempfile.TemporaryDirectory()
        self.image = os.path.join(self.tmp.name, "a.png")
        Image.new("RGB", (20, 20), "white").save(self.image)
        self.label = os.path.join(self.tmp.name, "a.json")
        self.widget, self.parent = build_labeling_widget()
        # The real parent chain is LabelingWidget -> central widget ->
        # QMainWindow, and status() walks it. A QMainWindow supplies statusBar()
        # and menuBar() like the app does; a bare QWidget does not.
        main = QtWidgets.QMainWindow()
        self.widget.parent = SimpleNamespace(parent=main)
        self.main = main
        self.widget.output_dir = self.tmp.name
        self.widget.image_dir = self.tmp.name
        self.widget._current_model_identity = lambda: "run_07"

    def tearDown(self):
        # The auto-save feedback is debounced by a timer: left running, it
        # fires inside a later test's event loop against a widget whose parent
        # chain has already been dropped here.
        timer = getattr(self.widget, "_auto_save_feedback_timer", None)
        if timer is not None:
            timer.stop()
        self.widget.parent = None
        self.tmp.cleanup()

    def _write_label(self, shapes):
        import json

        with open(self.label, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "version": "1",
                    "flags": {},
                    "checked": False,
                    "shapes": shapes,
                    "imagePath": "a.png",
                    "imageData": None,
                    "imageHeight": 20,
                    "imageWidth": 20,
                },
                handle,
            )

    def _stale_box(self, label="cat"):
        return {
            "label": label,
            "shape_type": "rectangle",
            "points": [[0, 0], [10, 10]],
            "flags": {},
            "group_id": None,
            "description": "",
            "difficult": False,
            "attributes": {},
            "kie_linking": [],
            "source": "model",
            "model": "run_01",
        }

    def _run_delete(self, dirty):
        from unittest import mock

        shapes = [self._stale_box()]
        self._write_label(shapes)
        self.widget.load_file(self.image)
        # Set after loading: load_file() ends with set_clean().
        self.widget.dirty = dirty
        ref = {
            "index": 0,
            "marker": self.smart_tools.shape_marker(shapes[0]),
            "label_file": self.label,
        }
        dialog = SimpleNamespace(
            selected_rows=lambda: [{"shape_ref": ref}],
            reject=lambda: None,
        )
        with mock.patch.object(
            self.smart_tools.QMessageBox,
            "question",
            return_value=self.smart_tools.QMessageBox.StandardButton.Yes,
        ):
            self.smart_tools._delete_reported_stale(self.widget, dialog)
        import json

        with open(self.label, "r", encoding="utf-8") as handle:
            return json.load(handle)["shapes"]

    def test_open_clean_file_deletes_on_disk_and_canvas(self):
        remaining = self._run_delete(dirty=False)
        self.assertEqual(remaining, [])
        self.assertEqual(
            [shape.label for shape in self.widget.canvas.shapes], []
        )

    def test_bulk_delete_on_the_open_image_is_undoable(self):
        # The point of mirroring the deletion on the canvas instead of
        # reloading: load_file() resets the shape history, so Ctrl+Z after a
        # batch delete used to be a dead key.
        self._run_delete(dirty=False)
        self.assertTrue(self.widget.actions.undo.isEnabled())

        self.widget.undo_shape_edit()

        self.assertEqual(
            [shape.label for shape in self.widget.canvas.shapes], ["cat"]
        )
        self.assertEqual(len(self.widget.label_list), 1)
        # set_dirty() saves at once under this build's auto_save: true default,
        # so the undone box is back on disk too, not just on the canvas.
        import json

        with open(self.label, "r", encoding="utf-8") as handle:
            restored = [s["label"] for s in json.load(handle)["shapes"]]
        self.assertEqual(restored, ["cat"])

        self.widget.redo_shape_edit()
        self.assertEqual(self.widget.canvas.shapes, [])

    def test_undo_is_not_offered_when_nothing_was_deleted(self):
        self._write_label([self._stale_box()])
        self.widget.load_file(self.image)
        before = self.widget.actions.undo.isEnabled()

        self.assertEqual(self.widget.delete_reported_shapes([9]), 0)

        self.assertEqual(self.widget.actions.undo.isEnabled(), before)
        self.assertEqual(len(self.widget.canvas.shapes), 1)

    def test_open_dirty_file_is_left_alone(self):
        remaining = self._run_delete(dirty=True)
        self.assertEqual([shape["label"] for shape in remaining], ["cat"])


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestWidgetLaunchedWithFolder(unittest.TestCase):
    """``--filename <folder>`` is a documented entry point, so it must boot.

    Opening a folder records it as a recent directory through ``self.settings``,
    which used to be created *after* the import ran: every folder launch died
    with AttributeError, and only in a built executable -- the packaged crash log
    was how it surfaced.
    """

    def setUp(self):
        import tempfile

        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        from PIL import Image

        self.tmp = tempfile.TemporaryDirectory()
        for index in range(2):
            Image.new("RGB", (16, 16), "white").save(
                os.path.join(self.tmp.name, f"a{index}.png")
            )
        # Keep QSettings writes out of the real registry for the duration.
        QtCore.QSettings.setPath(
            QtCore.QSettings.Format.IniFormat,
            QtCore.QSettings.Scope.UserScope,
            self.tmp.name,
        )
        # Loading an image from inside a queued signal corrupts the heap under
        # offscreen Qt (its error path opens a modal QMessageBox), and the
        # invariant here is startup order, not decoding pixels.
        from anylabeling.views.labeling.label_widget import LabelingWidget

        self._real_load_file = LabelingWidget.load_file
        LabelingWidget.load_file = lambda self, *a, **k: False
        self.widget, self.parent = build_labeling_widget(self.tmp.name)

    def tearDown(self):
        from anylabeling.views.labeling.label_widget import LabelingWidget

        LabelingWidget.load_file = self._real_load_file
        QtCore.QSettings.setPath(
            QtCore.QSettings.Format.IniFormat,
            QtCore.QSettings.Scope.UserScope,
            None,
        )
        self.widget.deleteLater()
        self.app.processEvents()
        # QSettings keeps its ini file open on Windows, so the folder it lives
        # in cannot always be removed the moment the widget is released.
        self.tmp.ignore_cleanup_errors = True
        self.tmp.cleanup()

    def test_folder_contents_are_loaded(self):
        self.assertEqual(self.widget.file_list_widget.count(), 2)
        self.assertEqual(
            sorted(os.path.basename(p) for p in self.widget.image_list),
            ["a0.png", "a1.png"],
        )

    def test_folder_is_recorded_as_recent(self):
        recorded = [
            os.path.normcase(path) for path in self.widget._recent_dir_list()
        ]
        self.assertIn(os.path.normcase(self.tmp.name), recorded)


if __name__ == "__main__":
    unittest.main()
