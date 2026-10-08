"""This module defines the main application window"""

import os

from PyQt6 import QtCore
from PyQt6.QtWidgets import QMainWindow, QStatusBar, QVBoxLayout, QWidget

from ..app_info import (
    __appdescription__,
    __appname__,
    __upstream_name__,
    __upstream_version__,
    __version__,
)
from .labeling.label_wrapper import LabelingWrapper


def _is_wsl_environment() -> bool:
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        with open("/proc/version", encoding="utf-8") as file_obj:
            return "microsoft" in file_obj.read().lower()
    except OSError:
        return False


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(
        self,
        app,
        config=None,
        filename=None,
        output=None,
        output_file=None,
        output_dir=None,
    ):
        super().__init__()
        self.app = app
        self.config = config

        self.setContentsMargins(0, 0, 0, 0)
        self.setWindowTitle(__appname__)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        self.labeling_widget = LabelingWrapper(
            self,
            config=config,
            filename=filename,
            output=output,
            output_file=output_file,
            output_dir=output_dir,
        )
        main_layout.addWidget(self.labeling_widget)
        widget = QWidget()
        widget.setLayout(main_layout)
        self.setCentralWidget(widget)
        self.settings = self.labeling_widget.view.settings
        self._is_wsl_environment = _is_wsl_environment()
        if self._is_wsl_environment:
            # WSLg has no stable geometry to restore.  Drop app.py's keys too
            # (``window/geometry`` / ``window/maximized``) — otherwise app.py
            # puts the window back anyway and this branch is cosmetic.
            for key in (
                "window/size",
                "window/position",
                "window/state",
                "window/geometry",
                "window/maximized",
            ):
                self.settings.remove(key)
            self.settings.sync()

        status_bar = QStatusBar()
        status_bar.showMessage(
            f"{__appname__} v{__version__}"
            f" (based on {__upstream_name__} {__upstream_version__})"
            f" - {__appdescription__}"
        )
        self.setStatusBar(status_bar)
        self._restore_window_state()

    def closeEvent(self, event):
        self.labeling_widget.closeEvent(event)
        if not event.isAccepted():
            return
        if self._is_wsl_environment:
            self.settings.remove("window/state")
            self.settings.remove("window/geometry")
            self.settings.remove("window/maximized")
        else:
            # Window *geometry* belongs to app.py (``window/geometry`` +
            # ``window/maximized``).  This side only remembers the dock
            # layout, so the two stop overwriting each other on startup.
            self.settings.setValue("window/state", self.saveState())
        super().closeEvent(event)

    def _restore_window_state(self):
        if self._is_wsl_environment:
            return
        if self.settings.contains("window/state"):
            state = self.settings.value("window/state", type=QtCore.QByteArray)
            if state:
                self.restoreState(state)
