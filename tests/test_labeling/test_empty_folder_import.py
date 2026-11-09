"""Opening a folder with no images must clear the previous image.

The old path cleared the file list but left the canvas, its shapes and the
window title describing the previous image, so the panel and the canvas
disagreed about what was open.
"""

import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtGui, QtWidgets

    PYQT_AVAILABLE = True
except Exception:  # noqa: BLE001
    PYQT_AVAILABLE = False


def _make_image(folder, name):
    from PIL import Image

    path = os.path.join(folder, name)
    Image.new("RGB", (24, 24), "white").save(path)
    return path


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestEmptyFolderImport(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])

        import tempfile

        self.holder = tempfile.TemporaryDirectory()
        self.addCleanup(self.holder.cleanup)
        self.empty = os.path.join(self.holder.name, "empty")
        self.images = os.path.join(self.holder.name, "images")
        os.makedirs(self.empty)
        os.makedirs(self.images)
        self.image = _make_image(self.images, "a.png")

        from tests.test_labeling.test_widget_wiring import (
            build_labeling_widget,
        )

        main = QtWidgets.QMainWindow()
        self.addCleanup(main.deleteLater)
        self.widget, self.parent = build_labeling_widget()
        # Cleanups run LIFO: delete the widget before the main window it
        # reports through, or a late statusBar() hits a destroyed parent.
        self.addCleanup(self.widget.deleteLater)
        self.widget.parent = SimpleNamespace(parent=main)
        self.main = main

        # Do not write the temp folder into the user's recent list.
        patcher = mock.patch(
            "jllabeling.views.labeling.utils.file_lifecycle."
            "_record_recent_dir",
            lambda *a, **k: None,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self._show_previous_image()

    def _show_previous_image(self):
        image = QtGui.QImage(self.image)
        self.widget.filename = self.image
        self.widget.image_path = self.image
        self.widget.image = image
        self.widget.canvas.load_pixmap(QtGui.QPixmap.fromImage(image))
        self.widget.update_progress_title()

    def test_empty_folder_clears_the_canvas_and_says_so(self):
        self.assertIsNotNone(self.widget.canvas.pixmap)

        self.widget.import_image_folder(self.empty)

        self.assertIsNone(self.widget.filename)
        self.assertIsNone(self.widget.canvas.pixmap)
        self.assertTrue(self.widget.image.isNull())
        self.assertEqual(self.widget.file_list_widget.count(), 0)
        self.assertNotIn(os.path.basename(self.image), self.main.windowTitle())
        self.assertIn(
            "该目录没有找到支持的图片",
            self.main.statusBar().currentMessage(),
        )
        self.assertFalse(self.widget.empty_canvas_state.isHidden())

    def test_window_title_starts_with_the_image_name(self):
        self._show_previous_image()

        title = self.widget._window_title()

        self.assertTrue(title.startswith("a.png"), title)
        self.assertIn("JLLabelingAndTrain", title)

    def test_a_search_with_no_hits_keeps_the_open_image(self):
        self.widget.import_image_folder(self.images, pattern="no-such-row")

        self.assertEqual(self.widget.filename, self.image)
        self.assertIsNotNone(self.widget.canvas.pixmap)
        self.assertEqual(self.widget.file_list_widget.count(), 0)
        self.assertIn(
            "没有匹配的图片",
            self.main.statusBar().currentMessage(),
        )


if __name__ == "__main__":
    unittest.main()
