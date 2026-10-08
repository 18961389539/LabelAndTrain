"""Page through a training run's images without leaving the application.

The Train tab shows six thumbnails; the interesting set is usually larger
(every train batch, the PR/F1 curves, the confusion matrix), and opening them
one by one in the system viewer loses the "flip through them" that makes them
readable at all. This dialog is that flip-through, with the system viewer one
click away for zooming.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from anylabeling.views.training.platform_open import open_path
from anylabeling.views.training.widgets.ultralytics_widgets import (
    PrimaryButton,
    SecondaryButton,
)


def step_index(current, step, count):
    """Wrap-around index for the pager (``count`` images, ``step`` of +/-1)."""
    if count <= 0:
        return 0
    return (current + step) % count


class TrainingImagePreviewDialog(QDialog):
    """One training image at a time, with paging and an external open."""

    def __init__(self, image_paths, index=0, parent=None):
        super().__init__(parent)
        self.image_paths = [path for path in (image_paths or []) if path]
        self.index = index if self.image_paths else 0
        self._pixmap = None

        self.setWindowTitle(self.tr("Training Images"))
        self.resize(900, 640)
        self.setSizeGripEnabled(True)

        layout = QVBoxLayout(self)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(320, 240)
        self.image_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
        )
        layout.addWidget(self.image_label, 1)

        self.caption_label = QLabel()
        self.caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption_label.setWordWrap(True)
        layout.addWidget(self.caption_label)

        buttons = QHBoxLayout()
        self.previous_button = SecondaryButton(self.tr("Previous"))
        self.previous_button.clicked.connect(lambda: self._step(-1))
        buttons.addWidget(self.previous_button)

        self.next_button = SecondaryButton(self.tr("Next"))
        self.next_button.clicked.connect(lambda: self._step(1))
        buttons.addWidget(self.next_button)

        buttons.addStretch()

        self.open_button = SecondaryButton(self.tr("Open in System Viewer"))
        self.open_button.clicked.connect(self._open_externally)
        buttons.addWidget(self.open_button)

        close_button = PrimaryButton(self.tr("Close"))
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._refresh()

    # -- paging ------------------------------------------------------------
    def _step(self, step):
        self.index = step_index(self.index, step, len(self.image_paths))
        self._refresh()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Left:
            self._step(-1)
            return
        if event.key() == Qt.Key.Key_Right:
            self._step(1)
            return
        if event.key() in (Qt.Key.Key_Escape,):
            self.reject()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()

    # -- painting ----------------------------------------------------------
    def _refresh(self):
        count = len(self.image_paths)
        has_image = count > 0
        self.previous_button.setEnabled(count > 1)
        self.next_button.setEnabled(count > 1)
        self.open_button.setEnabled(has_image)
        if not has_image:
            self._pixmap = None
            self.image_label.setText(self.tr("No image"))
            self.caption_label.setText("")
            return

        path = self.image_paths[self.index]
        pixmap = QPixmap(path)
        self._pixmap = pixmap if not pixmap.isNull() else None
        if self._pixmap is None:
            self.image_label.setText(self.tr("No image"))
            self.caption_label.setText(path)
            return
        self.caption_label.setText(f"{self.index + 1} / {count} · {path}")
        self._rescale()

    def _rescale(self):
        if self._pixmap is None:
            return
        area = self.image_label.size()
        if area.width() <= 0 or area.height() <= 0:
            return
        self.image_label.setPixmap(
            self._pixmap.scaled(
                area,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _open_externally(self):
        if not self.image_paths:
            return
        open_path(self.image_paths[self.index])
