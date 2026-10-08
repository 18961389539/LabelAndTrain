"""The export recap toast offers its two follow-ups.

The recap used to be a three-second toast whose only output was the
output path printed in its text: nothing to click, nothing to copy, and
gone before it could be read.
"""

import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets

    from anylabeling.views.labeling.utils import export

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


class _Widget(QtWidgets.QWidget):
    """Stand-in with only what the popup helper reaches for."""

    def __init__(self):
        super().__init__()
        self.status_message = None

    def tr(self, text):
        return text

    def status(self, message, delay=5000):
        self.status_message = message


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestExportDonePopup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])

    def _popup(self, save_path):
        # Both references live on the test: the popup is a child of the
        # stub widget, so letting the stub go would take the popup with it.
        self.stub = _Widget()
        popup = export._show_export_done_popup(
            self.stub, "导出完成", save_path, None, 65
        )
        self.addCleanup(self._close_quietly, popup)
        return self.stub, popup

    @staticmethod
    def _close_quietly(popup):
        try:
            popup.close()
        except RuntimeError:
            pass

    def test_the_popup_offers_open_and_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            _widget, popup = self._popup(folder)
            labels = [
                button.text()
                for button in popup.findChildren(QtWidgets.QPushButton)
            ]
            self.assertEqual(labels, ["打开输出目录", "复制输出路径"])
            # A button that disappears in three seconds is a button nobody
            # clicks, so the toast waits when it carries actions.
            self.assertGreaterEqual(popup._msec, 15000)

    def test_the_open_button_calls_the_platform_opener(self):
        with tempfile.TemporaryDirectory() as folder:
            _widget, popup = self._popup(folder)
            with mock.patch.object(export, "open_path") as opener:
                popup.findChildren(QtWidgets.QPushButton)[0].click()
            opener.assert_called_once_with(folder)

    def test_the_copy_button_reports_through_the_status_bar(self):
        with tempfile.TemporaryDirectory() as folder:
            widget, popup = self._popup(folder)
            with mock.patch.object(
                export, "copy_text_to_system_clipboard", return_value=True
            ):
                popup.findChildren(QtWidgets.QPushButton)[1].click()
            self.assertEqual(widget.status_message, "已复制输出路径")

    def test_a_missing_folder_leaves_the_plain_toast(self):
        _widget, popup = self._popup(
            os.path.join("no", "such", "folder", "anywhere")
        )
        self.assertEqual(
            popup.findChildren(QtWidgets.QPushButton),
            [],
        )


if __name__ == "__main__":
    unittest.main()
