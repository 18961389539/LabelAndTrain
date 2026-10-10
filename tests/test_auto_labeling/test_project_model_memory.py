"""A project remembers the auto-labeling model it was worked with.

The panel's model choice used to live only in memory
(``_last_model_selection``), so switching projects and coming back meant
finding the model again — the same gap L3 closed for the image position
and L4 for the task kind.
"""

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets

    from anylabeling import config
    from anylabeling.views.labeling import project_settings
    from anylabeling.views.labeling.widgets.auto_labeling.auto_labeling import (  # noqa: E501
        AutoLabelingWidget,
        _dataset_dir_for,
    )

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
TEMPLATE_CONFIG = os.path.join(
    REPO_ROOT, "anylabeling", "configs", "jllabeling_config.yaml"
)


class _Panel:
    """A stand-in carrying the attributes ``_dataset_dir_for`` reads."""

    def __init__(self, **attrs):
        self.parent = type("Parent", (), attrs)()


class TestWhichProjectIsThis(unittest.TestCase):
    """``_dataset_dir_for`` — pure, so it needs neither Qt nor a window."""

    def test_prefers_the_open_project_context(self):
        panel = _Panel(
            _project_dataset_dir=os.path.dirname(os.path.abspath(__file__)),
            filename=os.path.join("C:", os.sep, "elsewhere", "a.png"),
        )
        self.assertEqual(
            _dataset_dir_for(panel), os.path.dirname(os.path.abspath(__file__))
        )

    def test_falls_back_to_the_image_folder(self):
        folder = os.path.dirname(os.path.abspath(__file__))
        panel = _Panel(
            _project_dataset_dir=None,
            filename=os.path.join(folder, "a.png"),
        )
        self.assertEqual(_dataset_dir_for(panel), folder)

    def test_an_empty_folder_context_falls_through(self):
        """``_project_dataset_dir`` 指向已消失的目录时按没有处理。"""
        folder = os.path.dirname(os.path.abspath(__file__))
        panel = _Panel(
            _project_dataset_dir=os.path.join(folder, "gone-forever"),
            filename=os.path.join(folder, "a.png"),
        )
        self.assertEqual(_dataset_dir_for(panel), folder)

    def test_no_parent_no_project(self):
        self.assertEqual(_dataset_dir_for(_Panel()), "")


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestPanelRemembersItsProject(unittest.TestCase):
    """The real panel: recording on selection, restoring on project open."""

    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        # The panel's constructor builds a ModelManager, which reads
        # ``get_config()``; the isolation fixture leaves
        # ``current_config_file`` at None, where that call raises
        # AttributeError. Point it at the shipped template for the length
        # of the test, the way test_layout does. The fixture restores it.
        config.current_config_file = TEMPLATE_CONFIG
        self.tmp = tempfile.mkdtemp(prefix="panel_model_")
        self.panel = self._build_panel(self.tmp)

    def _build_panel(self, dataset_dir):
        # Same shape as test_layout's stand-in. Construction reads exactly
        # one key off ``_config`` (``shortcuts``), so this does not need
        # ``get_config()`` -- which raises when ``current_config_file`` is
        # None, as the isolation fixture deliberately leaves it.
        parent = type(
            "Parent",
            (),
            {
                "_config": {},
                "new_shapes_from_auto_labeling": lambda _self, _result: None,
                "_project_dataset_dir": dataset_dir,
            },
        )()
        panel = AutoLabelingWidget(parent)
        # A model the panel can name without touching models.yaml.
        panel.model_info["test_model"] = {
            "display_name": "Test Model",
            "config_path": "test_model.yaml",
        }
        # Loading is the one thing this test does not want: only "who was
        # asked to load" matters here.
        panel.new_model_selected.disconnect()
        self.loaded = []
        panel.new_model_selected.connect(self.loaded.append)
        return panel

    def test_selecting_a_model_records_it_on_the_project(self):
        self.panel.on_model_selected("YOLO", "test_model")
        self.assertEqual(
            project_settings.get_value(self.tmp, project_settings.MODEL_KEY),
            {"provider": "YOLO", "model": "test_model"},
        )

    def test_restoring_selects_the_remembered_model(self):
        self.assertTrue(self.panel.restore_project_model("YOLO", "test_model"))
        self.assertEqual(self.loaded, ["test_model.yaml"])
        self.assertEqual(
            self.panel._last_model_selection,
            ("YOLO", "test_model", "test_model.yaml"),
        )

    def test_restoring_skips_a_model_that_is_already_selected(self):
        """切走再切回同一个模型不该重新加载一遍。"""
        self.panel._last_model_selection = ("YOLO", "test_model", "x.yaml")
        self.assertTrue(self.panel.restore_project_model("YOLO", "test_model"))
        self.assertEqual(self.loaded, [])

    def test_restoring_gives_up_on_a_model_that_is_gone(self):
        """模型被删掉/移出列表时保持不选，不打扰打开项目。"""
        self.assertFalse(self.panel.restore_project_model("YOLO", "missing"))
        self.assertEqual(self.loaded, [])

    def test_restoring_nothing_selects_nothing(self):
        self.assertFalse(self.panel.restore_project_model("", ""))
        self.assertEqual(self.loaded, [])

    def test_without_a_project_nothing_is_recorded(self):
        panel = self._build_panel(None)
        self.assertEqual(_dataset_dir_for(panel), "")
        # 只是不能抛异常 —— 没有项目就没有可以记住的地方。
        panel._remember_model("YOLO", "test_model")
        self.assertEqual(
            project_settings.get_value(self.tmp, project_settings.MODEL_KEY),
            None,
        )
