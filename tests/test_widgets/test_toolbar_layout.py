import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtCore, QtGui, QtWidgets

    import anylabeling.resources.resources  # noqa: F401
    from anylabeling.views.labeling.utils.qt import new_icon
    from anylabeling.views.labeling.utils.theme import init_theme
    from anylabeling.views.labeling.widgets.toolbar import (
        FloatingToolPanel,
        ToolBar,
    )
    from anylabeling.views.labeling.widgets.zoom_widget import ZoomWidget

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required for toolbar tests")
class TestToolBarLayout(unittest.TestCase):

    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        self._widgets = []

    def tearDown(self):
        for widget in self._widgets:
            widget.close()
        init_theme("light")
        self.app.processEvents()

    def test_first_tool_button_stays_inside_vertical_toolbar(self):
        init_theme("dark")
        toolbar = ToolBar("Tools")
        self._widgets.append(toolbar)
        toolbar.setOrientation(QtCore.Qt.Orientation.Vertical)
        toolbar.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        toolbar.setIconSize(QtCore.QSize(24, 24))
        toolbar.setMaximumWidth(40)

        action = QtGui.QAction("Open Dir", toolbar)
        action.setIcon(new_icon("open"))
        toolbar.addAction(action)

        toolbar.resize(40, 80)
        toolbar.show()
        self.app.processEvents()

        button = toolbar.widgetForAction(action)
        self.assertIsNotNone(button)
        self.assertGreaterEqual(button.height(), toolbar.iconSize().height() + 4)
        # Button geometry is relative to the inner content widget, so map
        # its corners into the toolbar's coordinate system.
        top_left = button.mapTo(toolbar, QtCore.QPoint(0, 0))
        bottom_right = button.mapTo(
            toolbar, QtCore.QPoint(button.width(), button.height())
        )
        self.assertGreater(top_left.y(), 0)
        self.assertGreaterEqual(top_left.x(), 0)
        self.assertLessEqual(bottom_right.x(), toolbar.width())

    def test_vertical_toolbar_uses_refined_button_metrics(self):
        init_theme("dark")
        toolbar = ToolBar("Tools")
        self._widgets.append(toolbar)

        action = QtGui.QAction("Save", toolbar)
        action.setIcon(new_icon("save", "svg"))
        toolbar.addAction(action)

        toolbar.show()
        self.app.processEvents()

        button = toolbar.widgetForAction(action)
        self.assertGreaterEqual(button.width(), 30)
        self.assertGreaterEqual(button.height(), 30)
        self.assertEqual(toolbar.iconSize(), QtCore.QSize(24, 24))

    def test_zoom_widget_matches_toolbar_module_width(self):
        init_theme("dark")
        widget = ZoomWidget()
        self._widgets.append(widget)

        self.assertEqual(widget.size(), QtCore.QSize(30, 24))
        self.assertEqual(widget.alignment(), QtCore.Qt.AlignmentFlag.AlignCenter)

    def test_floating_toolbar_panel_stays_clamped_in_parent(self):
        init_theme("dark")
        parent = QtWidgets.QWidget()
        parent.resize(120, 180)
        parent.show()
        self._widgets.append(parent)

        panel = FloatingToolPanel(parent)
        content = QtWidgets.QFrame()
        content.setFixedSize(40, 260)
        panel.set_content_widget(content)
        panel.show()
        self._widgets.append(panel)
        self.app.processEvents()

        self.assertEqual(panel.pos(), QtCore.QPoint(8, 8))

        panel.move(999, 999)
        panel._user_moved = True
        panel.sync_to_parent()
        self.app.processEvents()

        self.assertGreaterEqual(panel.x(), 8)
        self.assertGreaterEqual(panel.y(), 8)
        self.assertLessEqual(panel.x() + panel.width(), parent.width() - 8)
        self.assertLessEqual(panel.y() + panel.height(), parent.height() - 8)
