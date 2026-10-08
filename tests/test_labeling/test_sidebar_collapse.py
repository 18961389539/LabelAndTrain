"""One-click collapse for the whole right sidebar.

The sidebar is three dock panels plus a thumbnail box; giving the canvas
the full window width used to mean hiding each piece by hand. These tests
pin the single control that replaces that, the state it writes down, and
the fact that the way back is still on screen while the panel is gone.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets

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

#: Everything the collapse claims to hide, by widget attribute.
SIDEBAR_MEMBERS = (
    "thumbnail_panel",
    "flag_dock",
    "label_dock",
    "shape_dock",
    "file_dock",
    "file_search",
)


def build_labeling_widget():
    """Construct the real widget headlessly (the wiring tests' hooks)."""
    from anylabeling import config as app_config
    from anylabeling.views.labeling.label_widget import LabelingWidget

    app_config.current_config_file = TEMPLATE_CONFIG
    LabelingWidget.menu = lambda self, title: QtWidgets.QMenu(title)
    parent = QtWidgets.QWidget()
    return LabelingWidget(parent), parent


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestRightSidebarCollapse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])
        # A toggle persists the state to the config file; keep that off the
        # real user config and record the writes instead.
        cls.writes = []
        cls._real_save_config = panel_visibility.save_config
        panel_visibility.save_config = lambda config: cls.writes.append(
            dict(config.get("sidebar") or {})
        )
        cls.widget, cls.parent = build_labeling_widget()

    @classmethod
    def tearDownClass(cls):
        panel_visibility.save_config = cls._real_save_config

    def setUp(self):
        panel_visibility.set_sidebar_collapsed(self.widget, False)
        self.writes.clear()

    def test_the_container_owns_everything_it_claims_to_collapse(self):
        # If a panel is not inside the widget that gets hidden, the
        # collapse silently stops covering the whole sidebar.
        for member in SIDEBAR_MEMBERS:
            self.assertTrue(
                self.widget.right_sidebar.isAncestorOf(
                    getattr(self.widget, member)
                ),
                member,
            )

    def test_one_click_collapses_the_whole_sidebar(self):
        self.assertFalse(self.widget.right_sidebar.isHidden())
        self.widget.sidebar_collapse_button.click()
        self.assertTrue(self.widget.right_sidebar.isHidden())

    def test_the_way_back_survives_the_collapse(self):
        self.widget.sidebar_collapse_button.click()
        self.assertFalse(self.widget.sidebar_collapse_strip.isHidden())
        self.assertFalse(self.widget.sidebar_collapse_button.isHidden())

    def test_a_second_click_restores_the_sidebar(self):
        self.widget.sidebar_collapse_button.click()
        self.widget.sidebar_collapse_button.click()
        self.assertFalse(self.widget.right_sidebar.isHidden())

    def test_the_button_describes_the_action_it_offers(self):
        button = self.widget.sidebar_collapse_button
        self.assertIn("收起", button.toolTip())
        expanded_icon = button.icon().cacheKey()
        button.click()
        self.assertIn("展开", button.toolTip())
        self.assertNotEqual(expanded_icon, button.icon().cacheKey())

    def test_every_change_is_written_down(self):
        panel_visibility.set_sidebar_collapsed(self.widget, True)
        self.assertTrue(self.writes[-1]["collapsed"])
        panel_visibility.set_sidebar_collapsed(self.widget, False)
        self.assertFalse(self.writes[-1]["collapsed"])

    def test_the_startup_replay_does_not_rewrite_the_config(self):
        self.widget._config["sidebar"] = {"collapsed": True}
        panel_visibility.restore_sidebar_state(self.widget)
        self.assertTrue(self.widget.right_sidebar.isHidden())
        self.assertEqual(self.writes, [])
        self.widget._config["sidebar"] = {"collapsed": False}
        panel_visibility.restore_sidebar_state(self.widget)
        self.assertFalse(self.widget.right_sidebar.isHidden())


if __name__ == "__main__":
    unittest.main()
