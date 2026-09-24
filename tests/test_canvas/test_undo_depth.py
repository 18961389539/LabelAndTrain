"""Undo depth must survive a realistic frame-by-frame labelling session.

The default used to be 10 snapshots, which filled up after a handful of
edits and silently turned Ctrl+Z into a no-op for anything older.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets

    from anylabeling.views.labeling.shape import Shape
    from anylabeling.views.labeling.widgets.canvas import Canvas

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


@unittest.skipUnless(
    PYQT_AVAILABLE, "PyQt6 is required for canvas tests"
)
class TestUndoDepth(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])

    def test_default_depth_is_100(self):
        canvas = Canvas(parent=None)
        self.assertEqual(canvas.num_backups, 100)

    def test_history_is_bounded_but_far_deeper_than_the_old_default(self):
        canvas = Canvas(parent=None)
        canvas.shapes = [Shape(label="car", shape_type="rectangle")]
        for _ in range(150):
            canvas.store_shapes()
        self.assertGreater(len(canvas.shapes_backups), 10)
        self.assertLessEqual(
            len(canvas.shapes_backups), canvas.num_backups + 2
        )

    def test_explicit_depth_still_wins(self):
        canvas = Canvas(parent=None, num_backups=3)
        self.assertEqual(canvas.num_backups, 3)
        canvas.shapes = [Shape(label="car", shape_type="rectangle")]
        for _ in range(20):
            canvas.store_shapes()
        self.assertLessEqual(len(canvas.shapes_backups), 5)
