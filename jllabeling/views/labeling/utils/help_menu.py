"""帮助菜单：快捷键速查、日志与工作目录入口。

The two folders were previously discoverable only from a crash dialog. Keeping
them one menu item away makes "where did the log go?" answerable without a
support round-trip.
"""

import os

from PyQt6.QtCore import QCoreApplication, QUrl
from PyQt6.QtGui import QDesktopServices

from jllabeling.config import get_log_dir_name, get_work_directory


def _open_folder(widget, path):
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as exc:
        widget.status(
            QCoreApplication.translate(
                "LabelingWidget", "无法打开目录：%1"
            ).replace("%1", str(exc)),
            5000,
        )
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def populate_help_menu(widget, menu, shortcut_action):
    """Fill the Help menu; called once while menus are assembled."""
    menu.addAction(shortcut_action)
    menu.addSeparator()
    for label, path in (
        (
            "打开日志目录",
            os.path.join(get_work_directory(), get_log_dir_name()),
        ),
        ("打开工作目录", get_work_directory()),
    ):
        action = menu.addAction(
            QCoreApplication.translate("LabelingWidget", label)
        )
        action.triggered.connect(
            lambda _checked=False, target=path: _open_folder(widget, target)
        )
