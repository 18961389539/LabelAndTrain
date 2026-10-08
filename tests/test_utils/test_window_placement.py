"""The main window reopens where it was closed.

It used to start maximized unconditionally -- the geometry save was a
commented-out line -- so a window sized for a second monitor came back
filling the primary one on every launch.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtCore, QtWidgets

    from anylabeling.app import (
        restore_window_placement,
        save_window_placement,
    )

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
        cls.settings = QtCore.QSettings("anylabeling", "anylabeling")
        # Snapshot whatever this machine had, so the test leaves no trace.
        cls.saved_geometry = cls.settings.value("window/geometry")
        cls.saved_maximized = cls.settings.value("window/maximized")

    @classmethod
    def tearDownClass(cls):
        for key, value in (
            ("window/geometry", cls.saved_geometry),
            ("window/maximized", cls.saved_maximized),
        ):
            if value is None:
                cls.settings.remove(key)
            else:
                cls.settings.setValue(key, value)
        cls.settings.sync()

    def setUp(self):
        self.settings.remove("window/geometry")
        self.settings.remove("window/maximized")
        self.settings.sync()

    def test_a_sized_window_comes_back_at_its_size(self):
        window = QtWidgets.QMainWindow()
        window.resize(900, 700)
        window.show()
        self.app.processEvents()
        save_window_placement(window)
        window.close()

        reopened = QtWidgets.QMainWindow()
        restore_window_placement(reopened)
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
        restore_window_placement(window)
        self.app.processEvents()
        self.assertTrue(window.isMaximized())
        window.close()

    def test_a_maximized_close_reopens_maximized(self):
        window = QtWidgets.QMainWindow()
        window.showMaximized()
        self.app.processEvents()
        save_window_placement(window)
        window.close()

        reopened = QtWidgets.QMainWindow()
        restore_window_placement(reopened)
        self.app.processEvents()
        self.assertTrue(reopened.isMaximized())
        reopened.close()


if __name__ == "__main__":
    unittest.main()
