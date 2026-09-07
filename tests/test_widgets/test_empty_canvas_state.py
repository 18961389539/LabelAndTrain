import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets

    from anylabeling.views.labeling.widgets.canvas_empty_state import (
        CanvasEmptyStateWidget,
    )

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestCanvasEmptyStateWidget(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        self.widget = CanvasEmptyStateWidget()
        self._clicked = False
        self.widget.open_folder_requested.connect(self._on_open)
        self.widget.show()
        self.app.processEvents()

    def _on_open(self):
        self._clicked = True

    def tearDown(self):
        self.widget.close()
        self.app.processEvents()

    def test_open_button_emits_signal(self):
        self.widget.open_button.click()
        self.app.processEvents()
        self.assertTrue(self._clicked)

    def test_copy_describes_three_steps(self):
        self.assertIn("打开文件夹", self.widget.open_button.text())


class TestFileListHelpers(unittest.TestCase):
    def test_fill_progress_template(self):
        from anylabeling.views.labeling.label_widget import (
            fill_progress_template,
        )

        text = fill_progress_template("已标 %1/%2 · 已检查 %3", 12, 50, 3)
        self.assertEqual(text, "已标 12/50 · 已检查 3")

    def test_move_file_to_delete_folder(self):
        from anylabeling.views.labeling.label_widget import (
            move_file_to_delete_folder,
        )

        with tempfile.TemporaryDirectory() as directory:
            src = os.path.join(directory, "demo.json")
            with open(src, "w", encoding="utf-8") as handle:
                handle.write("{}")
            dest = move_file_to_delete_folder(src, directory)
            self.assertIsNotNone(dest)
            self.assertFalse(os.path.exists(src))
            self.assertTrue(os.path.exists(dest))
            self.assertEqual(os.path.basename(os.path.dirname(dest)), "_delete_")


if __name__ == "__main__":
    unittest.main()
