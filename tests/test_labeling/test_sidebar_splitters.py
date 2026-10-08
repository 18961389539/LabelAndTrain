"""Splitters and section-visibility memory for the right sidebar.

The sidebar used to be a fixed-width column whose labels / objects / files
sections split the leftover height by size hint. These tests pin the two
handles that replaced that, the sizes they remember, and the one key the
section checkbox and the settings page now share for "should this dock be
visible".
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import yaml
    from PyQt6 import QtTest, QtWidgets

    from anylabeling.views.labeling.utils import panel_visibility

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
TEMPLATE_CONFIG = os.path.join(
    REPO_ROOT, "anylabeling", "configs", "jllabeling_config.yaml"
)


def build_labeling_widget(config_path=None):
    """Construct the real widget headlessly against a config file."""
    from anylabeling import config as app_config
    from anylabeling.views.labeling.label_widget import LabelingWidget

    app_config.current_config_file = config_path or TEMPLATE_CONFIG
    LabelingWidget.menu = lambda self, title: QtWidgets.QMenu(title)
    parent = QtWidgets.QWidget()
    return LabelingWidget(parent), parent


def _record_writes(sink):
    """A save_config stand-in that snapshots the sidebar/dock sections."""

    def record(config):
        sink.append(
            {
                "sidebar": dict(config.get("sidebar") or {}),
                "label_dock": dict(config.get("label_dock") or {}),
                "shape_dock": dict(config.get("shape_dock") or {}),
            }
        )

    return record


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestSidebarSplitters(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])
        cls.writes = []
        cls._real_save_config = panel_visibility.save_config
        panel_visibility.save_config = _record_writes(cls.writes)
        cls.widget, cls.parent = build_labeling_widget()

    @classmethod
    def tearDownClass(cls):
        panel_visibility.save_config = cls._real_save_config

    def setUp(self):
        self.writes.clear()
        timer = getattr(self.widget, "_sidebar_save_timer", None)
        if timer is not None:
            timer.stop()
        self.widget.resize(1280, 800)
        self.widget.layout().activate()
        self.widget.right_sidebar.layout().activate()

    def test_the_handles_own_the_canvas_and_every_section(self):
        main = self.widget.main_splitter
        lists = self.widget.lists_splitter
        self.assertIsInstance(main, QtWidgets.QSplitter)
        self.assertIsInstance(lists, QtWidgets.QSplitter)
        self.assertEqual(main.count(), 2)
        self.assertEqual(lists.count(), 3)
        self.assertTrue(
            main.widget(0).isAncestorOf(self.widget._canvas_scroll_area)
        )
        self.assertTrue(main.widget(1).isAncestorOf(self.widget.right_sidebar))
        for index, member in (
            (0, "label_dock"),
            (1, "shape_dock"),
            (2, "file_dock"),
        ):
            self.assertTrue(
                lists.widget(index).isAncestorOf(getattr(self.widget, member)),
                member,
            )
        # The file search row belongs to the files section, not to the
        # whole column.
        self.assertTrue(lists.widget(2).isAncestorOf(self.widget.file_search))

    def test_neither_side_can_be_dragged_away(self):
        self.assertFalse(self.widget.main_splitter.childrenCollapsible())
        self.assertFalse(self.widget.lists_splitter.childrenCollapsible())

    def test_a_drag_is_written_down_once(self):
        splitter = self.widget.main_splitter
        splitter.splitterMoved.emit(100, 1)
        splitter.splitterMoved.emit(130, 1)
        splitter.splitterMoved.emit(160, 1)
        QtTest.QTest.qWait(panel_visibility.SIZE_SAVE_DELAY_MS + 150)
        self.assertEqual(len(self.writes), 1)
        self.assertIn("width", self.writes[0]["sidebar"])
        self.assertEqual(len(self.writes[0]["sidebar"]["lists"]), 3)

    def test_the_remembered_width_is_replayed(self):
        self.widget._config["sidebar"]["width"] = 320
        panel_visibility.apply_sidebar_sizes(self.widget)
        self.assertAlmostEqual(
            self.widget.main_splitter.sizes()[1],
            320,
            delta=12,
        )

    def test_the_strip_only_exists_while_collapsed(self):
        widget = self.widget
        panel_visibility.set_sidebar_collapsed(widget, False)
        self.assertTrue(widget.sidebar_collapse_strip.isHidden())
        panel_visibility.set_sidebar_collapsed(widget, True)
        self.assertFalse(widget.sidebar_collapse_strip.isHidden())
        panel_visibility.set_sidebar_collapsed(widget, False)

    def test_the_footer_owns_the_gear_and_the_collapse_button(self):
        widget = self.widget
        files_panel = widget.file_dock.parent()
        # The gear no longer sits beside the file search box, where it
        # read as "settings for this list".
        self.assertFalse(files_panel.isAncestorOf(widget.settings_button))
        self.assertTrue(
            widget.right_sidebar.isAncestorOf(widget.settings_button)
        )
        button = widget.findChild(
            QtWidgets.QToolButton, "SidebarFooterCollapse"
        )
        self.assertIsNotNone(button)
        panel_visibility.set_sidebar_collapsed(widget, True)
        self.assertTrue(widget.right_sidebar.isHidden())
        button.click()
        self.assertFalse(widget.right_sidebar.isHidden())

    def test_the_files_section_has_a_matching_header(self):
        files_panel = self.widget.file_dock.parent()
        titles = [
            label.text()
            for label in files_panel.findChildren(QtWidgets.QLabel)
        ]
        self.assertIn("文件", titles)

    def test_the_flags_dock_wears_our_header(self):
        # The last native title bar in the column is gone: the dock gets
        # the same styled, centered header the other sections have.
        header = self.widget.flag_dock.titleBarWidget()
        self.assertIsNotNone(header)
        self.assertIsNotNone(header.layout())

    def test_both_search_boxes_offer_a_clear_button(self):
        # One had it, the other did not, and the built-in button (the only
        # tool button a SearchBar owns) carries no tooltip of its own.
        for search_box in (
            self.widget.label_search,
            self.widget.file_search,
        ):
            self.assertTrue(search_box.isClearButtonEnabled())
            button = search_box.findChild(QtWidgets.QToolButton)
            self.assertIsNotNone(button)
            self.assertTrue(button.toolTip().strip())

    def test_the_remembered_section_heights_are_replayed(self):
        self.widget._config["sidebar"]["lists"] = [260, 160, 320]
        panel_visibility.apply_sidebar_sizes(self.widget)
        sizes = self.widget.lists_splitter.sizes()
        self.assertGreater(sizes[2], sizes[0], sizes)
        self.assertGreater(sizes[0], sizes[1], sizes)

    def test_a_collapse_hands_the_width_back_to_the_canvas(self):
        main = self.widget.main_splitter
        panel_visibility.set_sidebar_collapsed(self.widget, False)
        expanded = main.sizes()
        self.assertGreater(expanded[1], 100, expanded)
        panel_visibility.set_sidebar_collapsed(self.widget, True)
        collapsed = main.sizes()
        self.assertAlmostEqual(
            collapsed[1],
            panel_visibility.SIDEBAR_STRIP_WIDTH,
            delta=2,
        )
        self.assertGreater(collapsed[0], expanded[0])
        self.assertFalse(main.handle(1).isEnabled())
        panel_visibility.set_sidebar_collapsed(self.widget, False)
        self.assertGreater(main.sizes()[1], 100)
        self.assertTrue(main.handle(1).isEnabled())

    def test_the_settings_switch_applies_without_a_restart(self):
        widget = self.widget
        widget._config["label_dock"]["show"] = False
        widget._settings_runtime_applier.apply_change("label_dock.show", False)
        self.assertTrue(widget.label_dock.isHidden())
        # The section checkbox follows the same state, without a write.
        self.assertFalse(widget.labels_checkbox.isChecked())
        widget._config["label_dock"]["show"] = True
        widget._settings_runtime_applier.apply_change("label_dock.show", True)
        self.assertFalse(widget.label_dock.isHidden())
        self.assertTrue(widget.labels_checkbox.isChecked())
        self.assertEqual(self.writes, [])


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestSectionVisibilityMemory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])
        cls.writes = []
        cls._real_save_config = panel_visibility.save_config
        panel_visibility.save_config = _record_writes(cls.writes)
        cls.widget, cls.parent = build_labeling_widget()

    @classmethod
    def tearDownClass(cls):
        panel_visibility.save_config = cls._real_save_config

    def setUp(self):
        self.writes.clear()

    def test_the_checkbox_and_the_settings_page_share_one_key(self):
        widget = self.widget
        widget.labels_checkbox.setChecked(False)
        self.assertTrue(widget.label_dock.isHidden())
        self.assertFalse(widget._config["label_dock"]["show"])
        self.assertFalse(self.writes[-1]["label_dock"]["show"])
        widget.labels_checkbox.setChecked(True)
        self.assertFalse(widget.label_dock.isHidden())
        self.assertTrue(self.writes[-1]["label_dock"]["show"])

    def test_a_saved_hidden_section_starts_hidden(self):
        """A config that last saved ``show: false`` must come up that way.

        Built through the constructor's ``config`` argument on purpose:
        ``get_config()`` merges the file onto the bundled defaults and
        rewrites back when the work directory has no rc, which would hide
        the very value this test is about.
        """
        from anylabeling import config as app_config
        from anylabeling.views.labeling.label_widget import LabelingWidget

        # The build reaches for get_config() in a few places of its own
        # (the auto-labeling model manager); point those at the template
        # while the widget itself is built from the modified copy.
        app_config.current_config_file = TEMPLATE_CONFIG
        with open(TEMPLATE_CONFIG, encoding="utf-8") as handle:
            config = yaml.safe_load(handle)
        config["label_dock"]["show"] = False
        parent = QtWidgets.QWidget()
        widget = LabelingWidget(parent, config=config)
        self.assertTrue(widget.label_dock.isHidden())
        self.assertFalse(widget.labels_checkbox.isChecked())


if __name__ == "__main__":
    unittest.main()
