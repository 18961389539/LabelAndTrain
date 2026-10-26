"""The recovery is only half the fix; the user has to be told about it."""

import logging
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import QtWidgets

from anylabeling.app import _show_config_recovery_warning


class TestConfigRecoveryWarning:
    def setup_method(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])

    def test_the_dialog_names_the_file_and_its_backup(self, monkeypatch):
        monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: 0)
        warning = {
            "path": r"C:\data\.xanylabelingrc",
            "backup": r"C:\data\.xanylabelingrc.invalid-20261023",
            "error": "ParserError: while parsing a flow sequence",
        }

        box = _show_config_recovery_warning(
            warning, logging.getLogger(__name__)
        )

        assert box is not None
        # QMessageBox.windowTitle is empty under the macOS offscreen
        # platform; the visible warning is the body text.
        assert "配置文件无法读取" in box.text()
        assert warning["path"] in box.text()
        assert warning["backup"] in box.text()
        assert warning["error"] in box.detailedText()

    def test_a_missing_backup_does_not_pretend_one_exists(self, monkeypatch):
        monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: 0)

        box = _show_config_recovery_warning(
            {"path": "rc", "backup": None, "error": "denied"},
            logging.getLogger(__name__),
        )

        assert "未能备份" in box.text()
