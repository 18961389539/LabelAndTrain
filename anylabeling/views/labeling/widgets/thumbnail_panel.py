"""The right-sidebar thumbnail box.

Since split batch 4 the widget body held three loose members for this
one feature -- ``thumbnail_pixmap``, ``thumbnail_image_label`` and
``thumbnail_container`` -- and two module functions reached into all
three.  The panel owns them now: one object, one place to look, and the
contract no longer carries three untyped names (roadmap stage two's
first slice).

The *policy* of which file gets a thumbnail stays where it was
(``file_list_ops.update_thumbnail_display``) -- that needs the model
config and the project layout.  This class only shows and hides.
"""

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtGui import QPixmap

from ..utils.qt import on_thumbnail_click


class ThumbnailPanel(QtWidgets.QWidget):
    """One thumbnail image; click opens it full size."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = None
        self._label = QtWidgets.QLabel(self)
        self._label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._label.mousePressEvent = on_thumbnail_click(self)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self._label)

        self.hide()

    def pixmap(self):
        """The current thumbnail, or None (the click handler asks)."""
        return self._pixmap

    def reset(self):
        """Forget the current thumbnail (before loading another image)."""
        self._pixmap = None
        self._label.clear()
        self.hide()

    def set_pixmap(self, pixmap):
        """Show a thumbnail; an empty pixmap is treated as no thumbnail."""
        if pixmap is None or pixmap.isNull():
            self.reset()
            return
        self._pixmap = QPixmap(pixmap)
        self.show()
        self.refresh()

    def refresh(self):
        """Re-scale the current pixmap to the label's width.

        Called on every resize / model switch: the sidebar can be narrow
        while the pixmap is a full-resolution snapshot.
        """
        if self._pixmap is None or self._pixmap.isNull():
            return
        width = self._label.width()
        if width <= 0:
            return
        self._label.setPixmap(
            self._pixmap.scaledToWidth(
                width,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
        )
