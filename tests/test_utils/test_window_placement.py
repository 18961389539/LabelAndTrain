"""The main window reopens where it was closed.

It used to start maximized unconditionally -- the geometry save was a
commented-out line -- so a window sized for a second monitor came back
filling the primary one on every launch.

``app.py`` reaches the window settings through
``utils/qt.py:app_settings``, which builds ``QSettings`` in this fork's own
domain; on Windows that is a registry key. The tests used to write there and
snapshot/restore the machine's real values by hand, so a case that failed
midway left a trace behind. They run against a file-backed settings object in
a temp directory now, by patching the factory module (``utils.qt.QtCore``).
"""

import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtCore, QtWidgets

    from jllabeling import app as app_module
    from jllabeling.views.labeling.utils import qt as qt_module

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestWindowPlacement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.settings = QtCore.QSettings(
            os.path.join(self._tmp.name, "window.ini"),
            QtCore.QSettings.Format.IniFormat,
        )
        patcher = mock.patch.object(qt_module, "QtCore")
        fake_qtcore = patcher.start()
        fake_qtcore.QSettings.return_value = self.settings
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)

    def test_a_sized_window_comes_back_at_its_size(self):
        window = QtWidgets.QMainWindow()
        window.resize(900, 700)
        window.show()
        self.app.processEvents()
        app_module.save_window_placement(window)
        window.close()

        reopened = QtWidgets.QMainWindow()
        app_module.restore_window_placement(reopened)
        self.app.processEvents()
        # The offscreen screen is smaller than 900 px, so Qt may clamp the
        # width onto it; the height and the not-maximized flag are what
        # prove the placement was remembered rather than defaulted.
        self.assertEqual(reopened.height(), 700)
        self.assertTrue(600 <= reopened.width() <= 900)
        self.assertFalse(reopened.isMaximized())
        reopened.close()

    def test_a_first_run_still_opens_maximized(self):
        window = QtWidgets.QMainWindow()
        app_module.restore_window_placement(window)
        self.app.processEvents()
        self.assertTrue(window.isMaximized())
        window.close()

    def test_a_maximized_close_reopens_maximized(self):
        window = QtWidgets.QMainWindow()
        window.showMaximized()
        self.app.processEvents()
        app_module.save_window_placement(window)
        window.close()

        reopened = QtWidgets.QMainWindow()
        app_module.restore_window_placement(reopened)
        self.app.processEvents()
        self.assertTrue(reopened.isMaximized())
        reopened.close()

    def test_nothing_is_written_to_the_machine(self):
        """The point of the temp file: the real keys must stay untouched."""
        real_legacy = QtCore.QSettings("jllabeling", "jllabeling")
        real_current = QtCore.QSettings("jllabeling", "jllabeling")
        before = (
            real_legacy.value("window/geometry"),
            real_current.value("window/geometry"),
        )

        window = QtWidgets.QMainWindow()
        window.resize(800, 600)
        window.show()
        self.app.processEvents()
        app_module.save_window_placement(window)
        window.close()

        after = (
            QtCore.QSettings("jllabeling", "jllabeling").value(
                "window/geometry"
            ),
            QtCore.QSettings("jllabeling", "jllabeling").value(
                "window/geometry"
            ),
        )
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
