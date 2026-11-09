"""Ctrl+A selects annotations; focusable controls carry accessible names."""

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtCore, QtWidgets

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestSelectAllAndFocus(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])

    def _widget(self):
        from tests.test_labeling.test_widget_wiring import (
            build_labeling_widget,
        )

        widget, holder = build_labeling_widget()
        for stop in (
            widget.async_label_checker.stop,
            widget.async_exif_scanner.stop_scan,
        ):
            self.addCleanup(stop)
        self.addCleanup(widget.deleteLater)
        self.addCleanup(holder.deleteLater)
        # The headless harness has no MainWindow behind parent.parent, so the
        # status-bar refresh in update_labeling_instruction cannot run.
        widget.update_labeling_instruction = lambda: None
        return widget

    def test_ctrl_a_selects_every_shape(self):
        from jllabeling.views.labeling.shape import Shape

        widget = self._widget()
        shapes = [Shape("rectangle"), Shape("polygon")]
        widget.canvas.shapes = shapes

        widget.actions.select_all.trigger()

        self.assertEqual(
            widget.actions.select_all.shortcut().toString(), "Ctrl+A"
        )
        self.assertEqual(widget.canvas.selected_shapes, shapes)

    def test_ctrl_a_in_a_text_field_still_selects_text(self):
        widget = self._widget()
        edit = QtWidgets.QLineEdit(widget)
        edit.setText("annotation")
        widget.canvas.selected_shapes = []

        with mock.patch.object(
            QtWidgets.QApplication, "focusWidget", return_value=edit
        ):
            widget.select_all_shapes()

        self.assertEqual(edit.selectedText(), "annotation")
        self.assertEqual(widget.canvas.selected_shapes, [])

    def test_previously_no_focus_controls_are_tab_reachable(self):
        widget = self._widget()
        controls = (
            widget.tools_panel._collapse_btn,
            widget.sidebar_collapse_button,
            widget.canvas_adjustment.opacity_slider,
            widget.canvas_adjustment.toggle_button,
        )
        for control in controls:
            with self.subTest(control=type(control).__name__):
                self.assertNotEqual(
                    control.focusPolicy(),
                    QtCore.Qt.FocusPolicy.NoFocus,
                )
                self.assertTrue(control.accessibleName())

        self.assertTrue(widget.canvas.accessibleName())
