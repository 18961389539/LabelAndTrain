"""ViewStateStore: the per-image view memory, tested on its own.

The three dicts it replaces were written and read from three different
files (label_widget, file_lifecycle, file_navigation) with no test on
the memory itself -- the round trip "leave an image, come back, land
where you were" was only ever checked by hand.
"""

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from PyQt6.QtCore import Qt  # noqa: E402

from anylabeling.views.labeling.widgets.view_state import (  # noqa: E402
    ViewStateStore,
)


class TestViewStateStore(unittest.TestCase):
    def setUp(self):
        self.state = ViewStateStore()

    def test_starts_empty(self):
        self.assertTrue(self.state.is_empty())
        self.assertIsNone(
            self.state.scroll_for(Qt.Orientation.Horizontal, "a.jpg")
        )

    def test_zoom_marks_the_session_as_started(self):
        self.state.zoom["a.jpg"] = (0, 1.5)
        self.assertFalse(self.state.is_empty())

    def test_scroll_round_trip_per_orientation(self):
        self.state.remember_scroll(Qt.Orientation.Horizontal, "a.jpg", 120)
        self.state.remember_scroll(Qt.Orientation.Vertical, "a.jpg", 40)

        self.assertEqual(
            self.state.scroll_for(Qt.Orientation.Horizontal, "a.jpg"), 120
        )
        self.assertEqual(
            self.state.scroll_for(Qt.Orientation.Vertical, "a.jpg"), 40
        )
        # another image is not affected
        self.assertIsNone(
            self.state.scroll_for(Qt.Orientation.Horizontal, "b.jpg")
        )

    def test_brightness_contrast_is_per_file(self):
        self.state.brightness_contrast["a.jpg"] = (1.2, 0.8)
        self.state.brightness_contrast["b.jpg"] = (1.0, 1.1)
        self.assertEqual(self.state.brightness_contrast["a.jpg"], (1.2, 0.8))
        self.assertEqual(self.state.brightness_contrast["b.jpg"], (1.0, 1.1))

    def test_states_do_not_leak_between_images(self):
        self.state.zoom["a.jpg"] = (1, 2.0)
        self.state.remember_scroll(Qt.Orientation.Horizontal, "a.jpg", 10)
        self.assertNotIn("b.jpg", self.state.zoom)
        self.assertNotIn("b.jpg", self.state.scroll[Qt.Orientation.Horizontal])


if __name__ == "__main__":
    unittest.main()
