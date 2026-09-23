import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets

    from anylabeling import config as app_config
    from anylabeling.config import get_config
    from anylabeling.views.labeling.widgets.auto_labeling.auto_labeling import (  # noqa: E501
        AutoLabelingWidget,
    )

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


@unittest.skipUnless(
    PYQT_AVAILABLE, "PyQt6 is required for auto labeling state tests"
)
class TestMorePanelState(unittest.TestCase):
    """The conf/IoU thresholds live behind 更多; expanding it must survive a
    restart instead of collapsing on every launch."""

    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        app_config.current_config_file = (
            "anylabeling/configs/jllabeling_config.yaml"
        )
        self._widgets = []

    def tearDown(self):
        for widget in self._widgets:
            widget.close()
        self.app.processEvents()

    def make_widget(self, expanded):
        config = copy.deepcopy(get_config())
        config.setdefault("auto_labeling", {})[
            "more_panel_expanded"
        ] = expanded
        parent = type(
            "Parent",
            (),
            {
                "_config": config,
                "new_shapes_from_auto_labeling": lambda _self, _r: None,
            },
        )()
        widget = AutoLabelingWidget(parent)
        self._widgets.append(widget)
        self.app.processEvents()
        return widget, parent

    def test_starts_collapsed_by_default(self):
        widget, _parent = self.make_widget(False)
        self.assertTrue(widget._more_panel.isHidden())
        self.assertFalse(widget._more_button.isChecked())

    def test_starts_expanded_when_saved(self):
        widget, _parent = self.make_widget(True)
        self.assertFalse(widget._more_panel.isHidden())
        self.assertTrue(widget._more_button.isChecked())
        self.assertIn("▴", widget._more_button.text())

    def test_toggle_persists_to_config(self):
        widget, parent = self.make_widget(False)
        with patch(
            "anylabeling.views.labeling.widgets.auto_labeling."
            "auto_labeling.save_config"
        ) as save:
            widget._more_button.click()

        self.assertTrue(parent._config["auto_labeling"]["more_panel_expanded"])
        self.assertFalse(widget._more_panel.isHidden())
        save.assert_called_once_with(parent._config)

    def test_toggle_back_to_collapsed(self):
        widget, parent = self.make_widget(True)
        with patch(
            "anylabeling.views.labeling.widgets.auto_labeling."
            "auto_labeling.save_config"
        ):
            widget._more_button.click()

        self.assertFalse(
            parent._config["auto_labeling"]["more_panel_expanded"]
        )
        self.assertTrue(widget._more_panel.isHidden())


if __name__ == "__main__":
    unittest.main()
