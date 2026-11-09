"""Provider logos must never collapse into an empty slot.

Vendor logos are static PNG resources. A provider that arrives through a model
config (a name this build ships no logo for) used to render a null pixmap and
leave a gap in the header, with nothing in the log to explain it.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets

    import jllabeling.resources.resources  # noqa: F401
    from jllabeling.views.labeling.widgets.searchable_model_dropdown import (
        ProviderSection,
    )

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestProviderSectionIcon(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])

    def _pixmap(self, provider_name):
        section = ProviderSection(provider_name)
        self.addCleanup(section.deleteLater)
        return section.icon_label.pixmap()

    def test_shipped_provider_uses_its_logo(self):
        self.assertFalse(self._pixmap("CVHub").isNull())

    def test_unknown_provider_gets_a_drawn_initial(self):
        with self.assertLogs("JLLabelingAndTrain", level="WARNING") as logs:
            pixmap = self._pixmap("NoSuchVendor")
        self.assertFalse(pixmap.isNull())
        self.assertTrue(
            any("NoSuchVendor" in line for line in logs.output), logs.output
        )
        image = pixmap.toImage()
        painted = sum(
            1
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y).alpha() > 0
        )
        self.assertGreater(painted, 0)


if __name__ == "__main__":
    unittest.main()
