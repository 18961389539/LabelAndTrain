"""The auto-labeling class filter is reachable, remembered and honest.

Both halves of the feature existed without a caller: ``ClassesFilterDialog``
was a dialog nothing constructed, and
``YOLO.set_auto_labeling_filter_classes`` was a setter no user could reach.
Wiring them together is where the interesting failures live, so these tests
drive the real panel with a model that copies the production index
semantics:

* a selection that matches no class of *this* model must not become an empty
  index list -- the mask built from that suppresses every class, so a stale
  memory would read as "the model broke";
* a filter belongs to a project, so switching projects has to reset it as
  well as restore it.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets
    from PyQt6.QtCore import Qt

    from anylabeling import config
    from anylabeling.views.labeling import project_settings
    from anylabeling.views.labeling.widgets.classes_filter_dialog import (
        ClassesFilterDialog,
    )
    from anylabeling.views.labeling.widgets.auto_labeling.auto_labeling import (  # noqa: E501
        AutoLabelingWidget,
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
MODULE = "anylabeling.views.labeling.widgets.auto_labeling.auto_labeling"


class _YoloLikeModel:
    """Carries the class list and the index filter the way ``YOLO`` does.

    The body is copied from ``__base__/yolo.py`` on purpose: the panel is
    only correct against the semantics it actually drives, and "empty
    selection means all classes" is the part a friendly stand-in would hide.
    """

    def __init__(self, classes):
        self.classes = list(classes)
        self.filter_classes = "unset"

    def set_auto_labeling_filter_classes(self, class_names):
        if not class_names or len(class_names) == len(self.classes):
            self.filter_classes = None
        else:
            self.filter_classes = [
                i for i, c in enumerate(self.classes) if c in class_names
            ]


class _PlainModel:
    """A model that has classes but no notion of filtering them."""

    def __init__(self, classes):
        self.classes = list(classes)


class TestProjectClassFilterStorage(unittest.TestCase):
    """``project_settings`` side: a missing key means "all classes"."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="class_filter_store_")

    def test_written_names_read_back_in_order(self):
        self.assertTrue(
            project_settings.remember_class_filter(None, self.tmp, ["b", "a"])
        )
        self.assertEqual(project_settings.class_filter(self.tmp), ["b", "a"])

    def test_empty_selection_removes_the_key(self):
        project_settings.remember_class_filter(None, self.tmp, ["a"])
        project_settings.remember_class_filter(None, self.tmp, None)
        self.assertIsNone(project_settings.class_filter(self.tmp))
        self.assertNotIn(
            project_settings.CLASS_FILTER_KEY,
            project_settings.load_settings(self.tmp),
        )

    def test_junk_in_the_project_file_reads_as_no_filter(self):
        project_settings.update_values(
            self.tmp, **{project_settings.CLASS_FILTER_KEY: {"a": 1}}
        )
        self.assertIsNone(project_settings.class_filter(self.tmp))

    def test_reset_forgets_the_filter(self):
        """重置本项目设置 promises to drop this module's keys."""
        project_settings.remember_class_filter(None, self.tmp, ["a"])
        project_settings.reset_ui_settings(self.tmp)
        self.assertIsNone(project_settings.class_filter(self.tmp))

    def test_restore_needs_a_project_and_a_panel(self):
        class _Widget:
            pass

        self.assertFalse(
            project_settings.restore_class_filter(_Widget(), None)
        )
        self.assertFalse(
            project_settings.restore_class_filter(_Widget(), self.tmp)
        )

    def test_restore_swallows_a_panel_that_raises(self):
        """Opening a project must not fail because a memory is broken."""

        class _Panel:
            def apply_project_class_filter(self):
                raise RuntimeError("no model yet")

        class _Widget:
            auto_labeling_widget = _Panel()

        self.assertFalse(
            project_settings.restore_class_filter(_Widget(), self.tmp)
        )

    def test_restore_calls_the_panel(self):
        calls = []

        class _Panel:
            def apply_project_class_filter(self):
                calls.append(1)
                return True

        class _Widget:
            auto_labeling_widget = _Panel()

        self.assertTrue(
            project_settings.restore_class_filter(_Widget(), self.tmp)
        )
        self.assertEqual(calls, [1])


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestPanelClassFilter(unittest.TestCase):
    """The real panel: entry, application, memory and the marks it leaves."""

    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        config.current_config_file = TEMPLATE_CONFIG
        self.tmp = tempfile.mkdtemp(prefix="panel_class_filter_")
        self.status_lines = []
        self.panel = self._build_panel(self.tmp)
        self.model = _YoloLikeModel(["person", "car", "dog"])
        self._load(self.model)

    def tearDown(self):
        self.panel.close()
        self.app.processEvents()

    def _build_panel(self, dataset_dir):
        parent = type(
            "Parent",
            (),
            {
                "_config": {},
                "new_shapes_from_auto_labeling": lambda _self, _r: None,
                "_project_dataset_dir": dataset_dir,
                "status": lambda _self, text: self.status_lines.append(text),
            },
        )()
        panel = AutoLabelingWidget(parent)
        panel.new_model_selected.disconnect()
        return panel

    def _load(self, model):
        # ``type`` is outside every _AUTO_LABELING_*_MODELS set, so the
        # threshold slots in on_new_model_loaded leave the stand-in alone.
        self.panel.model_manager.loaded_model_config = {
            "model": model,
            "type": "test",
            "display_name": "Test Model",
            "classes": getattr(model, "classes", []),
        }
        return model

    # --- the model side -------------------------------------------------

    def test_subset_becomes_an_index_filter(self):
        self.assertTrue(self.panel.set_class_filter(["car"]))
        self.assertEqual(self.model.filter_classes, [1])
        self.assertEqual(self.panel._class_filter, ["car"])

    def test_selecting_everything_disables_the_filter(self):
        self.panel.set_class_filter(["person", "car", "dog"])
        self.assertIsNone(self.model.filter_classes)
        self.assertIsNone(self.panel._class_filter)

    def test_deselecting_everything_disables_the_filter(self):
        self.panel.set_class_filter(["car"])
        self.panel.set_class_filter([])
        self.assertIsNone(self.model.filter_classes)

    def test_names_this_model_lacks_are_not_passed_through(self):
        """A stale memory must not silence the model.

        ``["bicycle"]`` against ``[person, car, dog]`` is an empty index
        list, and the mask built from it drops every detection -- the
        annotator would see a model that suddenly finds nothing.
        """
        self.panel.set_class_filter(["bicycle"])
        self.assertIsNone(self.model.filter_classes)
        self.assertIsNone(self.panel._class_filter)

    def test_partial_overlap_keeps_the_classes_this_model_has(self):
        self.panel.set_class_filter(["dog", "bicycle"])
        self.assertEqual(self.model.filter_classes, [2])

    def test_selection_order_follows_the_model(self):
        self.panel.set_class_filter(["dog", "person"])
        self.assertEqual(self.model.filter_classes, [0, 2])

    def test_dict_class_names_are_flattened(self):
        """A config written as ``{id: name}`` still lists its names."""
        model = _YoloLikeModel([])
        model.classes = {"person": "p", "car": "c"}
        self._load(model)
        self.assertEqual(self.panel._loaded_model_classes(), ["p", "c"])
        self.assertTrue(self.panel.set_class_filter(["c"]))

    def test_a_model_without_the_setter_has_no_entry(self):
        self._load(_PlainModel(["person", "car"]))
        self.panel._refresh_class_filter_button()
        self.assertFalse(self.panel.set_class_filter(["person"]))
        self.assertTrue(self.panel.button_class_filter.isHidden())

    def test_entry_lives_in_the_more_panel(self):
        """Not in the primary row: that row was just freed of overflow."""
        self.assertIs(
            self.panel.button_class_filter.parent(), self.panel._more_panel
        )
        self.assertIn("button_class_filter", self.panel._MORE_PANEL_WIDGETS)

    def test_entry_is_laid_out_when_the_panel_is_open(self):
        """Parented is not the same as reachable: it has to have a box."""
        self.panel.on_new_model_loaded(
            self.panel.model_manager.loaded_model_config
        )
        self.panel._more_panel.setVisible(True)
        self.panel.resize(1400, 120)
        self.panel.show()
        self.app.processEvents()
        try:
            self.assertTrue(self.panel.button_class_filter.isVisible())
            self.assertGreater(self.panel.button_class_filter.width(), 0)
            self.assertGreater(self.panel.button_class_filter.height(), 0)
        finally:
            self.panel.hide()

    def test_a_model_without_classes_has_no_entry(self):
        self._load(_YoloLikeModel([]))
        self.panel._refresh_class_filter_button()
        self.assertFalse(self.panel.set_class_filter(["person"]))

    # --- what the user sees ---------------------------------------------

    def test_active_filter_is_named_on_the_button(self):
        self.panel.set_class_filter(["car", "dog"])
        button = self.panel.button_class_filter
        self.assertFalse(button.isHidden())
        self.assertIn("2/3", button.text())
        self.assertIn("car", button.toolTip())

    def test_inactive_filter_leaves_a_plain_button(self):
        self.panel.set_class_filter(["person", "car", "dog"])
        button = self.panel.button_class_filter
        self.assertNotIn("/", button.text())
        self.assertNotIn("car", button.toolTip())

    def test_collapsed_more_panel_marks_the_toggle(self):
        """A hidden filter is still a filter: say so on the visible button."""
        self.assertTrue(self.panel._more_panel.isHidden())
        self.panel.set_class_filter(["car"])
        self.assertIn("类别筛选", self.panel._more_button.toolTip())

    def test_expanded_more_panel_does_not_need_the_mark(self):
        self.panel._more_panel.setVisible(True)
        self.panel.set_class_filter(["car"])
        self.assertNotIn("类别筛选", self.panel._more_button.toolTip())

    def test_applying_reports_in_the_status_line(self):
        self.panel.set_class_filter(["car"])
        self.assertTrue(
            any("car" in line for line in self.status_lines),
            self.status_lines,
        )

    def test_switching_models_clears_the_mark(self):
        self.panel.set_class_filter(["car"])
        self.panel.hide_labeling_widgets()
        self.assertIsNone(self.panel._class_filter)
        self.assertNotIn("类别筛选", self.panel._more_button.toolTip())

    # --- the project memory ---------------------------------------------

    def test_choice_is_remembered_on_the_project(self):
        self.panel.set_class_filter(["car"])
        self.assertEqual(project_settings.class_filter(self.tmp), ["car"])

    def test_restoring_a_project_reapplies_its_filter(self):
        project_settings.remember_class_filter(None, self.tmp, ["dog"])
        self.assertTrue(self.panel.apply_project_class_filter())
        self.assertEqual(self.model.filter_classes, [2])

    def test_a_project_without_memory_resets_the_filter(self):
        """The previous project's selection must not follow the model here."""
        self.panel.set_class_filter(["car"], persist=False)
        self.assertEqual(self.model.filter_classes, [1])
        self.assertTrue(self.panel.apply_project_class_filter())
        self.assertIsNone(self.model.filter_classes)

    def test_persist_false_leaves_the_project_alone(self):
        self.panel.set_class_filter(["car"], persist=False)
        self.assertIsNone(project_settings.class_filter(self.tmp))

    def test_model_load_applies_the_project_filter(self):
        project_settings.remember_class_filter(None, self.tmp, ["person"])
        self.panel.on_new_model_loaded(
            self.panel.model_manager.loaded_model_config
        )
        self.assertEqual(self.model.filter_classes, [0])
        self.assertIn("1/3", self.panel.button_class_filter.text())

    def test_a_stale_memory_survives_gracefully_on_load(self):
        """Remembered names this model never had fall back to all classes."""
        project_settings.remember_class_filter(None, self.tmp, ["giraffe"])
        self.panel.on_new_model_loaded(
            self.panel.model_manager.loaded_model_config
        )
        self.assertIsNone(self.model.filter_classes)

    def test_no_project_means_no_persistence(self):
        panel = self._build_panel(None)
        panel.model_manager.loaded_model_config = {
            "model": self.model,
            "type": "test",
            "classes": self.model.classes,
        }
        self.assertTrue(panel.set_class_filter(["car"]))
        self.assertEqual(self.model.filter_classes, [1])
        self.assertIsNone(project_settings.class_filter(self.tmp))
        panel.close()

    # --- the dialog seam --------------------------------------------------

    def test_dialog_gets_the_classes_and_the_active_selection(self):
        seen = {}

        class _Dialog:
            def __init__(self, classes, filter_classes, parent):
                seen["classes"] = list(classes)
                seen["filter"] = filter_classes
                seen["parent"] = parent

            def exec(self):
                return QtWidgets.QDialog.DialogCode.Rejected

            def get_selected_classes(self):
                raise AssertionError("cancelled dialog must not apply")

        self.panel.set_class_filter(["car"], persist=False)
        with patch(f"{MODULE}.ClassesFilterDialog", _Dialog):
            self.panel.open_class_filter_dialog()

        self.assertEqual(seen["classes"], ["person", "car", "dog"])
        self.assertEqual(seen["filter"], ["car"])
        self.assertIs(seen["parent"], self.panel)
        self.assertEqual(self.model.filter_classes, [1])

    def test_dialog_selection_is_applied(self):
        class _Dialog:
            def __init__(self, classes, filter_classes, parent):
                pass

            def exec(self):
                return QtWidgets.QDialog.DialogCode.Accepted

            def get_selected_classes(self):
                return ["dog"]

        with patch(f"{MODULE}.ClassesFilterDialog", _Dialog):
            self.panel.open_class_filter_dialog()
        self.assertEqual(self.model.filter_classes, [2])
        self.assertEqual(project_settings.class_filter(self.tmp), ["dog"])

    def test_dialog_stays_closed_for_an_unsupported_model(self):
        self._load(_PlainModel(["person"]))
        with patch(f"{MODULE}.ClassesFilterDialog") as dialog:
            self.panel.open_class_filter_dialog()
        dialog.assert_not_called()


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestClassesFilterDialog(unittest.TestCase):
    """The dialog the panel now opens, in the states the panel hands it."""

    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        config.current_config_file = TEMPLATE_CONFIG
        self.classes = ["person", "car", "dog"]

    def _dialog(self, filter_classes):
        return ClassesFilterDialog(self.classes, filter_classes)

    def test_no_filter_starts_with_everything_checked(self):
        dialog = self._dialog(None)
        self.assertEqual(dialog.get_selected_classes(), self.classes)

    def test_an_empty_filter_list_also_means_everything(self):
        """``[]`` and ``None`` agree here, and the panel relies on that:
        both mean "no filter", never "filter out every class"."""
        dialog = self._dialog([])
        self.assertEqual(dialog.get_selected_classes(), self.classes)

    def test_a_subset_pre_checks_only_those_rows(self):
        dialog = self._dialog(["car"])
        self.assertEqual(dialog.get_selected_classes(), ["car"])

    def test_unchecking_a_row_drops_it_from_the_result(self):
        dialog = self._dialog(None)
        dialog._list.item(1).setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual(dialog.get_selected_classes(), ["person", "dog"])

    def test_deselecting_every_row_reports_nothing(self):
        dialog = self._dialog(None)
        for i in range(dialog._list.count()):
            dialog._list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual(dialog.get_selected_classes(), [])

    def test_search_hides_rows_and_keeps_the_selection(self):
        dialog = self._dialog(None)
        dialog._search_bar.setText("car")
        visible = [
            dialog._list.item(i).text()
            for i in range(dialog._list.count())
            if not dialog._list.item(i).isHidden()
        ]
        self.assertEqual(visible, ["car"])
        self.assertEqual(dialog.get_selected_classes(), self.classes)

    def test_toggle_button_only_touches_the_visible_rows(self):
        """取消全选 while searching must not clear the hidden rows."""
        dialog = self._dialog(None)
        dialog._search_bar.setText("person")
        dialog._toggle_btn.click()
        self.assertEqual(dialog.get_selected_classes(), ["car", "dog"])
        dialog._toggle_btn.click()
        self.assertEqual(dialog.get_selected_classes(), self.classes)

    def test_toggle_label_follows_the_visible_rows(self):
        """The label names the action the button will perform.

        Asserted against the source strings: these are inherited English
        sources, and no ``.qm`` is loaded in a test run.
        """
        dialog = self._dialog(["car"])
        self.assertEqual(dialog._toggle_btn.text(), "Select All")
        dialog._list.item(0).setCheckState(Qt.CheckState.Checked)
        dialog._list.item(2).setCheckState(Qt.CheckState.Checked)
        self.assertEqual(dialog._toggle_btn.text(), "Deselect All")


if __name__ == "__main__":
    unittest.main()
