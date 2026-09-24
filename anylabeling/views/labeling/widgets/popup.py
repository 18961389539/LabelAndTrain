import os
import shutil
import subprocess
import sys

from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils.theme import get_theme
from PyQt6.QtWidgets import (
    QWidget,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QGraphicsDropShadowEffect,
    QApplication,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, QRectF, QSize, QPoint
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QIcon


def is_wsl():
    """Check if running in WSL"""
    if os.path.exists("/proc/version"):
        with open("/proc/version", "r") as f:
            if "microsoft" in f.read().lower():
                return True
    return False


def _copy_via_command(command, text):
    if isinstance(command, str):
        command = [command]
    executable = command[0]
    if os.sep in executable:
        exists = os.path.exists(executable)
    else:
        exists = shutil.which(executable) is not None
    if not exists:
        return False
    try:
        result = subprocess.run(
            command,
            input=text,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Clipboard helper {executable} failed: {exc}")
        return False
    if result.returncode != 0:
        logger.warning(
            f"Clipboard helper {executable} exited with {result.returncode}"
        )
    return result.returncode == 0


def copy_text_to_system_clipboard(text):
    """Copy ``text`` to the system clipboard.

    Returns True on success. Callers must surface a failure instead of
    silently reporting success -- this used to return None either way, which
    made "Copy Successful" a lie whenever the clipboard was unavailable.
    """
    if not text:
        return False

    clipboard = QApplication.clipboard()
    if clipboard is not None:
        try:
            clipboard.setText(text)
            if clipboard.text() == text:
                return True
            logger.warning(
                "Qt clipboard accepted the text but returned a different "
                "value; falling back to a platform helper"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Qt clipboard write failed: {exc}")

    if is_wsl():
        if _copy_via_command(["clip.exe"], text):
            return True
        return _copy_via_command(["/mnt/c/Windows/System32/clip.exe"], text)

    if sys.platform.startswith("win"):
        return _copy_via_command(["clip"], text)

    if sys.platform == "darwin":
        return _copy_via_command(["pbcopy"], text)

    if _copy_via_command(["wl-copy"], text):
        return True
    if _copy_via_command(["xclip", "-selection", "clipboard"], text):
        return True
    return _copy_via_command(["xsel", "--clipboard", "--input"], text)


class Popup(QWidget):
    def __init__(self, text, parent=None, msec=3000, icon=None):
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )

        t = get_theme()
        self._bg_color = t["surface_hover"]
        self._text_color = t["text"]
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {self._bg_color};
                border-radius: 16px;
            }}
            QLabel {{
                background-color: transparent;
                color: {self._text_color};
            }}
        """)

        # Use horizontal layout to place icon and text side by side
        hbox = QHBoxLayout()
        hbox.setContentsMargins(12, 8, 12, 8)  # Add spacing on both sides

        # Add icon if provided
        self.icon_label = None
        if icon:
            self.icon_label = QLabel()
            self.icon_label.setPixmap(QIcon(icon).pixmap(QSize(16, 16)))
            self.icon_label.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
            )
            hbox.addWidget(self.icon_label)
            hbox.addSpacing(1)  # Space between icon and text

        # Add text label
        self.label = QLabel(text)
        self.label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        hbox.addWidget(self.label)

        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(hbox)
        self.setLayout(layout)

        # Set window properties
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )

        # Add drop shadow effect
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(16)
        self.shadow.setColor(QColor(0, 0, 0, 80))
        self.shadow.setOffset(0, 3)
        self.setGraphicsEffect(self.shadow)

        # Create auto-close timer
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.close)
        self._msec = msec
        self.timer.start(msec)

    def set_text(self, text):
        self.label.setText(text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        rect = QRectF(self.rect())
        path.addRoundedRect(rect, 10, 10)

        painter.fillPath(path, QColor(self._bg_color))

    def show_popup(
        self,
        parent_widget,
        copy_msg="",
        popup_height=36,
        position="default",
        top_offset=100,
    ):
        """Show the popup, optionally copying ``copy_msg`` first.

        Returns the clipboard result: True when the copy succeeded, False
        when it was attempted and failed, None when no copy was requested.
        """
        copied = None
        if copy_msg:
            copied = copy_text_to_system_clipboard(copy_msg)

        # Calculate position based on preference
        parent_origin = parent_widget.mapToGlobal(QPoint(0, 0))
        parent_rect = parent_widget.rect()

        # Auto-adjust width based on content
        self.adjustSize()
        popup_width = self.sizeHint().width()

        # Set position based on specified option
        if position == "center":
            x = parent_origin.x() + (parent_rect.width() - popup_width) // 2
            y = parent_origin.y() + (parent_rect.height() - popup_height) // 2
        elif position == "bottom":
            x = parent_origin.x() + (parent_rect.width() - popup_width) // 2
            y = parent_origin.y() + parent_rect.height() - popup_height - 20
        else:  # "default" - top position
            x = parent_origin.x() + (parent_rect.width() - popup_width) // 2
            y = parent_origin.y() + top_offset

        self.setGeometry(x, y, popup_width, popup_height)
        self.show()
        self.timer.start(self._msec)
        return copied
