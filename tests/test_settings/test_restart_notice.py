"""Saving a restart-only setting tells the user why nothing changed yet."""

import copy
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import QtWidgets

from jllabeling.views.labeling.settings.controller import SettingsController
from jllabeling.views.labeling.settings.dialog import SettingsDialog
from jllabeling.views.labeling.settings.schema import load_template_config


class TestRestartRequiredNotice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])

    def setUp(self):
        config = copy.deepcopy(load_template_config())
        self.controller = SettingsController(
            config=config,
            apply_callback=lambda _key, _value: None,
            save_callback=lambda _config: True,
            save_delay_ms=1000,
            defer_runtime_apply=True,
        )
        self.dialog = SettingsDialog(None, self.controller)
        self.dialog._confirm_discard_unsaved = lambda: True

    def tearDown(self):
        self.controller.flush()
        self.dialog.close()
        self.app.processEvents()

    def test_ui_scale_asks_for_a_restart(self):
        shown = []

        def fake_exec(box):
            shown.append(box.text())
            return 0

        with mock.patch.object(QtWidgets.QMessageBox, "exec", fake_exec):
            self.dialog._show_restart_required_notice(["ui_scale"])

        self.assertEqual(len(shown), 1)
        self.assertIn("重启", shown[0])

    def test_other_keys_do_not_ask_for_a_restart(self):
        shown = []

        def fake_exec(box):
            shown.append(box.text())
            return 0

        with mock.patch.object(QtWidgets.QMessageBox, "exec", fake_exec):
            self.dialog._show_restart_required_notice(["labels"])

        self.assertEqual(shown, [])
