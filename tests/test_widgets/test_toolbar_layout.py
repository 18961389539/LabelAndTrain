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

    def _make_panel(self):
        """Floating panel over a roomy parent, with a fixed content area."""
        parent = QtWidgets.QWidget()
        parent.resize(400, 400)
        parent.show()
        self._widgets.append(parent)

        panel = FloatingToolPanel(parent)
        content = QtWidgets.QFrame()
        content.setFixedSize(40, 200)
        panel.set_content_widget(content)
        panel.show()
        self._widgets.append(panel)
        self.app.processEvents()
        return panel, content

    @staticmethod
    def _fake_mouse_event(evt_type, global_pos):
        return QtGui.QMouseEvent(
            evt_type,
            QtCore.QPointF(10, 10),
            QtCore.QPointF(global_pos),
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier,
        )

    def test_floating_toolbar_double_click_on_handle_resets_position(self):
        panel, _ = self._make_panel()
        committed = []
        panel.positionCommitted.connect(
            lambda x, y: committed.append((x, y))
        )

        panel.set_saved_position(60, 40)
        self.assertEqual(panel.pos(), QtCore.QPoint(60, 40))
        self.assertTrue(panel._user_moved)

        self.assertTrue(
            panel.eventFilter(
                panel._handle,
                self._fake_mouse_event(
                    QtCore.QEvent.Type.MouseButtonDblClick,
                    QtCore.QPoint(70, 50),
                ),
            )
        )
        self.assertEqual(panel.pos(), panel.default_position())
        self.assertFalse(panel._user_moved)
        self.assertEqual(
            committed, [(panel.default_position().x(), panel.default_position().y())]
        )

    def test_floating_toolbar_drag_release_commits_position(self):
        panel, _ = self._make_panel()
        committed = []
        panel.positionCommitted.connect(
            lambda x, y: committed.append((x, y))
        )
        self.assertEqual(panel.pos(), QtCore.QPoint(8, 8))

        # Synthetic press/move/release over the grip, mimicking a real drag.
        fg = panel.frameGeometry()
        press_global = fg.topLeft() + QtCore.QPoint(5, 5)
        self.assertTrue(
            panel.eventFilter(
                panel._handle,
                self._fake_mouse_event(
                    QtCore.QEvent.Type.MouseButtonPress, press_global
                ),
            )
        )
        self.assertTrue(panel._dragging)

        move_global = press_global + QtCore.QPoint(20, 10)
        self.assertTrue(
            panel.eventFilter(
                panel._handle,
                self._fake_mouse_event(
                    QtCore.QEvent.Type.MouseMove, move_global
                ),
            )
        )
        self.assertTrue(panel._user_moved)
        self.assertNotEqual(panel.pos(), QtCore.QPoint(8, 8))

        self.assertTrue(
            panel.eventFilter(
                panel._handle,
                self._fake_mouse_event(
                    QtCore.QEvent.Type.MouseButtonRelease, move_global
                ),
            )
        )
        self.assertFalse(panel._dragging)
        # The committed position matches where the panel actually landed.
        self.assertEqual(committed, [(panel.x(), panel.y())])
        self.assertEqual(len(committed), 1)

    @staticmethod
    def _icon_pixels(icon):
        image = (
            icon.pixmap(QtCore.QSize(16, 16))
            .toImage()
            .convertToFormat(QtGui.QImage.Format.Format_ARGB32)
        )
        return bytes(
            image.constBits().asarray(
                image.height() * image.bytesPerLine()
            )
        )

    def test_floating_toolbar_collapse_hides_content_and_toggles(self):
        panel, content = self._make_panel()
        toggled = []
        panel.collapseToggled.connect(toggled.append)

        self.assertTrue(content.isVisible())
        expanded_icon = panel._collapse_btn.icon()
        self.assertFalse(expanded_icon.isNull())
        self.assertEqual(panel._collapse_btn.toolTip(), "收起工具栏")

        panel.set_collapsed(True)
        self.assertTrue(panel.is_collapsed())
        self.assertFalse(content.isVisible())
        collapsed_icon = panel._collapse_btn.icon()
        self.assertFalse(collapsed_icon.isNull())
        # The two states must render different artwork, otherwise the button
        # gives no clue whether the panel is open or shut.
        self.assertNotEqual(
            self._icon_pixels(collapsed_icon),
            self._icon_pixels(expanded_icon),
        )
        self.assertEqual(panel._collapse_btn.toolTip(), "展开工具栏")

        # Idempotent: collapsing again emits nothing.
        panel.set_collapsed(True)
        self.assertEqual(toggled, [True])

        panel.set_collapsed(False)
        self.assertFalse(panel.is_collapsed())
        self.assertTrue(content.isVisible())
        self.assertEqual(panel._collapse_btn.toolTip(), "收起工具栏")
        self.assertEqual(
            self._icon_pixels(panel._collapse_btn.icon()),
            self._icon_pixels(expanded_icon),
        )
        self.assertEqual(toggled, [True, False])

        # toggle_collapse flips back to collapsed.
        panel.toggle_collapse()
        self.assertTrue(panel.is_collapsed())
        self.assertFalse(content.isVisible())

    def test_floating_toolbar_saved_position_survives_sync(self):
        panel, _ = self._make_panel()
        panel.set_saved_position(30, 22)
        panel.sync_to_parent()
        self.assertEqual(panel.pos(), QtCore.QPoint(30, 22))
        self.assertTrue(panel._user_moved)
        self.assertEqual(panel.user_position(), QtCore.QPoint(30, 22))

    def test_config_roundtrip_persists_tools_panel_state(self):
        import os.path as osp
        import tempfile

        from anylabeling import config as cfg_module

        old_config_file = cfg_module.current_config_file
        old_work_dir = cfg_module.get_work_directory()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cfg_module.set_work_directory(tmp)
                # Point the loader at the per-user rc file like the real app.
                cfg_module.current_config_file = osp.join(tmp, ".xanylabelingrc")
                cfg = cfg_module.get_config()
                self.assertIn("tools_panel", cfg)
                self.assertIsNone(cfg["tools_panel"].get("position"))
                self.assertFalse(cfg["tools_panel"].get("collapsed"))

                cfg["tools_panel"]["position"] = [42, 17]
                cfg["tools_panel"]["collapsed"] = True
                self.assertTrue(cfg_module.save_config(cfg))

                reloaded = cfg_module.get_config()
                self.assertEqual(reloaded["tools_panel"]["position"], [42, 17])
                self.assertTrue(reloaded["tools_panel"]["collapsed"])
        finally:
            cfg_module.current_config_file = old_config_file
            cfg_module.set_work_directory(old_work_dir)


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required for toolbar tests")
class TestPanelWithScrollAreaContent(unittest.TestCase):
    """The real panel content is a QScrollArea, not a fixed-size frame.

    ``QScrollArea.sizeHint()`` reports its own small default instead of the
    toolbar inside it, so a panel sized from that hint showed one of 26 tools
    and hid the rest behind a scrollbar. Every earlier test handed the panel a
    fixed-size frame, which is why none of them caught it.
    """

    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        self._widgets = []

    def tearDown(self):
        for widget in self._widgets:
            widget.close()
        self.app.processEvents()

    def _panel(self, parent_height, tools=10):
        parent = QtWidgets.QWidget()
        parent.resize(400, parent_height)
        parent.show()
        self._widgets.append(parent)

        toolbar = ToolBar("Tools")
        toolbar.setOrientation(QtCore.Qt.Orientation.Vertical)
        for index in range(tools):
            action = QtGui.QAction(f"tool_{index}", toolbar)
            action.setIcon(new_icon("ok", "svg"))
            toolbar.addAction(action)
        toolbar.setMinimumHeight(toolbar.sizeHint().height())
        self._widgets.append(toolbar)

        scroll = QtWidgets.QScrollArea()
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        scroll.setFixedWidth(toolbar.maximumWidth() + 4)
        scroll.setWidget(toolbar)

        panel = FloatingToolPanel(parent)
        panel.set_content_widget(scroll)
        panel.show()
        self._widgets.append(panel)
        self.app.processEvents()
        return panel, scroll, toolbar

    def test_tall_parent_shows_every_tool(self):
        panel, scroll, toolbar = self._panel(700)
        needed = toolbar.sizeHint().height()
        self.assertGreaterEqual(panel.height(), needed)
        self.assertGreaterEqual(scroll.height(), needed)

    def test_short_parent_clamps_and_keeps_scrolling(self):
        panel, scroll, toolbar = self._panel(240)
        needed = toolbar.sizeHint().height()
        self.assertLessEqual(panel.height(), 240 - 8)
        self.assertLess(scroll.maximumHeight(), needed)
        self.assertGreaterEqual(scroll.maximumHeight(), 72)

    def test_panel_resyncs_when_the_parent_grows(self):
        panel, scroll, toolbar = self._panel(240)
        short = panel.height()
        parent = panel.parentWidget()
        parent.resize(400, 700)
        panel.sync_to_parent()
        self.app.processEvents()
        needed = toolbar.sizeHint().height()
        self.assertGreater(panel.height(), short)
        self.assertGreaterEqual(scroll.height(), needed)
