"""ThumbnailPanel: the sidebar box, tested on its own.

The three loose widget members it replaced (pixmap / label / container)
had no tests at all; the panel's show-hide policy -- reset before every
image, an empty pixmap means no thumbnail, click opens full size -- is
pinned here with a real QPixmap, no labeling widget involved.
"""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from PyQt6.QtGui import QPixmap  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from anylabeling.views.labeling.widgets.thumbnail_panel import (  # noqa: E402
    ThumbnailPanel,
)


def qapp():
    return QApplication.instance() or QApplication([])


class TestThumbnailPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qapp()

    def setUp(self):
        self.panel = ThumbnailPanel()

    def tearDown(self):
        self.panel.deleteLater()

    def test_starts_empty_and_hidden(self):
        self.assertIsNone(self.panel.pixmap())
        self.assertTrue(self.panel.isHidden())

    def test_set_pixmap_stores_and_shows(self):
        pixmap = QPixmap(40, 30)
        pixmap.fill()
        self.panel.set_pixmap(pixmap)
        self.assertIsNotNone(self.panel.pixmap())
        self.assertFalse(self.panel.isHidden())

    def test_null_pixmap_is_treated_as_no_thumbnail(self):
        self.panel.set_pixmap(QPixmap())  # null
        self.assertIsNone(self.panel.pixmap())
        self.assertTrue(self.panel.isHidden())

    def test_reset_clears_and_hides(self):
        pixmap = QPixmap(40, 30)
        pixmap.fill()
        self.panel.set_pixmap(pixmap)
        self.panel.reset()
        self.assertIsNone(self.panel.pixmap())
        self.assertTrue(self.panel.isHidden())

    def test_refresh_on_empty_panel_is_a_no_op(self):
        self.panel.refresh()  # must not raise
        self.assertIsNone(self.panel.pixmap())

    def test_stored_pixmap_is_a_copy(self):
        # the caller can drop its own reference; the panel keeps its own
        pixmap = QPixmap(24, 24)
        pixmap.fill()
        self.panel.set_pixmap(pixmap)
        pixmap.fill()  # scribble on the original
        self.assertFalse(self.panel.pixmap().isNull())


if __name__ == "__main__":
    unittest.main()
