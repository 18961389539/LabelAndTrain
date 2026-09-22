import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TEMPLATE_CONFIG = os.path.join(
    REPO_ROOT, "anylabeling", "configs", "xanylabeling_config.yaml"
)


def build_labeling_widget():
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
    return LabelingWidget(parent), parent


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
        self.assertEqual(len(titles), 11, titles)
        self.assertTrue(
            any(title.startswith("10.") for title in titles),
            titles,
        )

    def test_model_identity_is_safe_without_a_loaded_model(self):
        self.assertIsNone(self.widget._current_model_identity())

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
        main = QtWidgets.QWidget()
        main.setWindowTitle = lambda _title: None
        self.widget.parent = SimpleNamespace(parent=main)
        self.widget.output_dir = self.tmp.name
        self.widget.image_dir = self.tmp.name
        self.widget._current_model_identity = lambda: "run_07"

    def tearDown(self):
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
            "marker": self.smart_tools._shape_marker(shapes[0]),
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
        self.assertEqual([shape.label for shape in self.widget.canvas.shapes], [])

    def test_open_dirty_file_is_left_alone(self):
        remaining = self._run_delete(dirty=True)
        self.assertEqual([shape["label"] for shape in remaining], ["cat"])


if __name__ == "__main__":
    unittest.main()
