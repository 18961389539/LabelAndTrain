"""The Help menu exposes the shortcut sheet and the on-disk folders."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import QtWidgets


def test_help_menu_has_shortcuts_and_folder_entries():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    from jllabeling.views.labeling.utils import help_menu

    class _Widget:
        def status(self, *_args, **_kwargs):
            pass

    menu = QtWidgets.QMenu()
    shortcut = menu.addAction("快捷键速查")
    help_menu.populate_help_menu(_Widget(), menu, shortcut)

    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert texts[0] == "快捷键速查"
    assert "打开日志目录" in texts
    assert "打开工作目录" in texts
