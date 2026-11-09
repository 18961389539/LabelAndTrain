"""Switching themes rebuilds the UI without stacking menus."""

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import QtWidgets

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
TEMPLATE_CONFIG = os.path.join(
    REPO_ROOT, "jllabeling", "configs", "jllabeling_config.yaml"
)

_APP = None


class TestThemeHotSwitch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global _APP
        _APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_switch_rebuilds_the_widget_and_keeps_the_menu_count(self):
        from jllabeling import config as app_config
        from jllabeling.views.labeling.utils.theme import (
            apply_theme_to_app,
            get_mode,
        )
        from jllabeling.views.mainwindow import MainWindow

        app_config.current_config_file = TEMPLATE_CONFIG
        original = get_mode()
        target = "dark" if original == "light" else "light"
        main = MainWindow(_APP)
        self.addCleanup(main.deleteLater)
        old_view = main.labeling_widget.view
        # The rebuild reopens filename-or-last-dir. The latter comes from the
        # real QSettings registry, which another test (or the developer's
        # session) may point at a folder that no longer exists; opening it
        # raises a modal and would hang an offscreen run.
        old_view.last_open_dir = ""
        menu_count = len(main.menuBar().actions())
        _APP.processEvents()
        old_save_labels = main.statusBar().findChildren(
            QtWidgets.QLabel, "SaveStateLabel"
        )
        self.assertEqual(len(old_save_labels), 1)

        try:
            with mock.patch.object(
                QtWidgets.QDialog,
                "exec",
                lambda self: QtWidgets.QDialog.DialogCode.Accepted,
            ):
                old_view._on_theme_changed(target)

            new_view = main.labeling_widget.view
            _APP.processEvents()
            self.assertIsNot(new_view, old_view)
            self.assertEqual(get_mode(), target)
            self.assertEqual(new_view._config["theme"], target)
            self.assertEqual(len(main.menuBar().actions()), menu_count)
            status_bar = main.statusBar()
            for object_name in ("SaveStateLabel", "StatusContextLabel"):
                self.assertEqual(
                    len(
                        status_bar.findChildren(QtWidgets.QLabel, object_name)
                    ),
                    1,
                    object_name,
                )
        finally:
            apply_theme_to_app(_APP, original, initial=False)
