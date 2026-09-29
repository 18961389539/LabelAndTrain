"""Per-image view memory.

``zoom_values``, ``brightness_contrast_values`` and ``scroll_values``
were three dicts on the widget -- all keyed by filename, all written
when the annotator leaves an image and read back when they return to
it (``file_lifecycle.load_file``).  They are one object now: the
"where was I on this picture" memory, in one place, with a surface
that can be cleared or inspected without reaching for three names.
"""

from PyQt6.QtCore import Qt


class ViewStateStore:
    """Zoom, brightness/contrast and scroll remembered per filename."""

    def __init__(self):
        #: filename -> (zoom_mode, zoom_value)
        self.zoom = {}
        #: filename -> (brightness, contrast)
        self.brightness_contrast = {}
        #: orientation -> {filename: scroll_value}
        self.scroll = {
            Qt.Orientation.Horizontal: {},
            Qt.Orientation.Vertical: {},
        }

    def is_empty(self):
        """True before the first image was ever shown.

        ``load_file`` uses this to tell "first load of the session"
        (fit the image) from "returning to a known image" (restore the
        remembered view).
        """
        return not self.zoom

    def remember_scroll(self, orientation, filename, value):
        self.scroll[orientation][filename] = value

    def scroll_for(self, orientation, filename):
        return self.scroll[orientation].get(filename)
