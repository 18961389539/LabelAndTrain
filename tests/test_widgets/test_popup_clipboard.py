"""Copy-to-clipboard must report what actually happened.

The clipboard write used to swallow every failure and return None either
way, so the "Copy Successful" popup appeared even when nothing had been
copied. These tests pin the contract: a bool result, a logged reason, and
an honest message at the call site.
"""

import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets

    from anylabeling.views.labeling.label_widget import LabelingWidget
    from anylabeling.views.labeling.widgets import popup as popup_module
    from anylabeling.views.labeling.widgets.popup import (
        Popup,
        copy_text_to_system_clipboard,
    )

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


POPUP = "anylabeling.views.labeling.widgets.popup"


@unittest.skipUnless(
    PYQT_AVAILABLE, "PyQt6 is required for clipboard tests"
)
class TestClipboardResult(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])

    def test_empty_text_is_a_failure_not_a_silent_no_op(self):
        self.assertFalse(copy_text_to_system_clipboard(""))

    def test_qt_clipboard_success_returns_true(self):
        clipboard = Mock()
        clipboard.text.return_value = "hello"
        with patch.object(
            popup_module, "QApplication"
        ) as qapp:
            qapp.clipboard.return_value = clipboard
            self.assertTrue(copy_text_to_system_clipboard("hello"))
        clipboard.setText.assert_called_once_with("hello")

    def test_qt_clipboard_mismatch_falls_back_and_logs(self):
        clipboard = Mock()
        clipboard.text.return_value = "something else"
        with patch.object(
            popup_module, "_copy_via_command", return_value=True
        ) as helper, patch.object(
            popup_module, "is_wsl", return_value=False
        ), patch.object(
            popup_module, "QApplication"
        ) as qapp, patch.object(
            popup_module, "logger"
        ) as logger:
            qapp.clipboard.return_value = clipboard
            self.assertTrue(copy_text_to_system_clipboard("hello"))
        helper.assert_called()
        self.assertTrue(logger.warning.called)

    def test_qt_clipboard_exception_falls_back_instead_of_passing(self):
        clipboard = Mock()
        clipboard.setText.side_effect = RuntimeError("clipboard gone")
        with patch.object(
            popup_module, "_copy_via_command", return_value=True
        ) as helper, patch.object(
            popup_module, "is_wsl", return_value=False
        ), patch.object(
            popup_module, "QApplication"
        ) as qapp, patch.object(
            popup_module, "logger"
        ) as logger:
            qapp.clipboard.return_value = clipboard
            self.assertTrue(copy_text_to_system_clipboard("hello"))
        helper.assert_called()
        self.assertTrue(logger.warning.called)

    def test_every_backend_failing_returns_false(self):
        with patch.object(
            popup_module, "QApplication"
        ) as qapp, patch.object(
            popup_module, "_copy_via_command", return_value=False
        ), patch.object(
            popup_module, "is_wsl", return_value=False
        ):
            qapp.clipboard.return_value = None
            self.assertFalse(copy_text_to_system_clipboard("hello"))

    def test_helper_process_failure_is_logged(self):
        with patch.object(
            popup_module.shutil, "which", return_value="/usr/bin/clip"
        ), patch.object(
            popup_module.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=1),
        ), patch.object(popup_module, "logger") as logger:
            self.assertFalse(
                popup_module._copy_via_command(["clip"], "hello")
            )
        self.assertTrue(logger.warning.called)


@unittest.skipUnless(
    PYQT_AVAILABLE, "PyQt6 is required for popup tests"
)
class TestShowPopupResult(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])

    def test_no_copy_requested_returns_none(self):
        parent = QtWidgets.QWidget()
        popup = Popup("hi", parent=parent)
        self.assertIsNone(popup.show_popup(parent))
        popup.close()

    def test_copy_result_is_returned_to_the_caller(self):
        parent = QtWidgets.QWidget()
        for expected in (True, False):
            with self.subTest(expected=expected):
                popup = Popup("hi", parent=parent)
                with patch.object(
                    popup_module,
                    "copy_text_to_system_clipboard",
                    return_value=expected,
                ):
                    self.assertIs(
                        popup.show_popup(parent, copy_msg="/tmp/a.jpg"),
                        expected,
                    )
                popup.close()


@unittest.skipUnless(
    PYQT_AVAILABLE, "PyQt6 is required for label widget tests"
)
class TestCopyFilePathFeedback(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])

    def _call(self, copy_result):
        widget = SimpleNamespace(tr=lambda text: text)
        with patch(
            "anylabeling.views.labeling.label_widget.Popup"
        ) as popup_class, patch(
            "anylabeling.views.labeling.label_widget"
            ".copy_text_to_system_clipboard",
            return_value=copy_result,
        ) as copy_mock:
            LabelingWidget.copy_file_path(widget, "/tmp/a.jpg")
        message = popup_class.call_args[0][0]
        return message, popup_class, copy_mock

    def test_success_message_only_after_a_real_copy(self):
        message, popup_class, copy_mock = self._call(True)
        self.assertEqual(message, "Copy Successful")
        copy_mock.assert_called_once_with("/tmp/a.jpg")
        popup_class.return_value.show_popup.assert_called_once()

    def test_failure_is_reported_instead_of_claimed_as_success(self):
        message, popup_class, _copy = self._call(False)
        self.assertNotEqual(message, "Copy Successful")
        self.assertIn("复制失败", message)
        popup_class.return_value.show_popup.assert_called_once()

    def test_success_and_failure_use_different_icons(self):
        _m, popup_class, _c = self._call(True)
        success_icon = popup_class.call_args.kwargs["icon"]
        _m, popup_class, _c = self._call(False)
        failure_icon = popup_class.call_args.kwargs["icon"]
        self.assertNotEqual(success_icon, failure_icon)
