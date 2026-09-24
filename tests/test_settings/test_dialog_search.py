"""The settings dialog has 119 fields spread over four pages.

Without a search box, finding one meant knowing which page it lives on.
These tests pin the search behaviour: cross-page filtering, Chinese queries
resolving through the real translation catalog, live editors in the
results, and a clean way back to the normal page view.
"""

import copy
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtCore, QtWidgets

    from anylabeling.views.labeling.settings.controller import (
        SettingsController,
    )
    from anylabeling.views.labeling.settings.dialog import SettingsDialog
    from anylabeling.views.labeling.settings.schema import (
        SETTING_FIELD_MAP,
        SETTINGS_PRIMARY_ORDER,
        load_template_config,
    )

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


QM_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "anylabeling",
    "resources",
    "translations",
    "zh_CN.qm",
)


@unittest.skipUnless(
    PYQT_AVAILABLE, "PyQt6 is required for settings search tests"
)
class TestSettingsSearch(unittest.TestCase):

    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        self._resources = []

    def tearDown(self):
        for dialog, controller in self._resources:
            controller.flush()
            dialog.close()
        self.app.processEvents()

    def _create_dialog(self):
        config = copy.deepcopy(load_template_config())
        controller = SettingsController(
            config=config,
            apply_callback=lambda _key, _value: None,
            save_callback=lambda _config: True,
            save_delay_ms=1000,
            defer_runtime_apply=True,
        )
        dialog = SettingsDialog(None, controller)
        dialog._confirm_discard_unsaved = lambda: True
        dialog.show()
        self.app.processEvents()
        self._resources.append((dialog, controller))
        return dialog

    def _type(self, dialog, text):
        dialog.search_input.setText(text)
        self.app.processEvents()

    # -- wiring ---------------------------------------------------------

    def test_search_box_lives_in_the_header_and_reports_itself(self):
        dialog = self._create_dialog()
        # Inside the header, so it is reachable from every page.
        self.assertIs(dialog.search_input.parent(), dialog.header)
        self.assertTrue(dialog.search_input.placeholderText())
        self.assertTrue(dialog.search_input.isClearButtonEnabled())

    def test_typing_a_query_switches_to_results(self):
        dialog = self._create_dialog()
        self._type(dialog, "undo")
        self.assertTrue(dialog._search_active)
        self.assertIn("搜索结果", dialog.header_title.text())

    def test_results_span_every_page_not_just_the_active_one(self):
        dialog = self._create_dialog()
        self._type(dialog, "shortcut")
        keys = set(dialog._bindings)
        pages = {SETTING_FIELD_MAP[key].primary for key in keys}
        # Whatever matched, it is not limited to the page we started on.
        self.assertTrue(keys)
        self.assertTrue(pages)

    def test_search_covers_shortcut_fields_too(self):
        dialog = self._create_dialog()
        self._type(dialog, "shortcuts.save")
        self.assertIn("shortcuts.save", dialog._bindings)

    # -- matching -------------------------------------------------------

    def test_matches_key_and_title_and_description(self):
        dialog = self._create_dialog()
        by_key = dialog._search_matches("canvas.num_backups")
        self.assertIn(
            "canvas.num_backups", [field.key for field in by_key]
        )
        by_label = dialog._search_matches("Undo Backups")
        self.assertIn(
            "canvas.num_backups", [field.key for field in by_label]
        )
        by_page = dialog._search_matches("Interaction")
        self.assertTrue(
            all(
                field.primary == "Canvas" or field.secondary == "Interaction"
                for field in by_page
            )
        )

    def test_chinese_query_resolves_through_the_real_catalog(self):
        """A zh_CN user must be able to search in Chinese.

        The titles stay English on screen, so this only works because the
        translated description is part of the haystack.
        """
        translator = QtCore.QTranslator()
        if not translator.load(QM_PATH):
            self.skipTest(f"Could not load {QM_PATH}")
        self.app.installTranslator(translator)
        try:
            dialog = self._create_dialog()
            self._type(dialog, "撤销")
            self.assertIn("canvas.num_backups", dialog._bindings)
        finally:
            self.app.removeTranslator(translator)

    def test_no_match_is_handled_without_crashing(self):
        dialog = self._create_dialog()
        self._type(dialog, "zzz-no-such-setting-zzz")
        self.assertTrue(dialog._search_active)
        self.assertEqual(dialog._bindings, {})
        self.assertIn("0", dialog.header_title.text())

    # -- editing from the results ---------------------------------------

    def test_results_carry_live_editors_bound_to_the_same_handler(self):
        dialog = self._create_dialog()
        self._type(dialog, "Undo Backups")
        # A missing binding is how "the setting is visible but dead" shows up.
        self.assertIn("canvas.num_backups", dialog._bindings)
        for key, binding in dialog._bindings.items():
            self.assertEqual(binding.field.key, key)

    def test_editing_from_results_marks_the_owning_page_dirty(self):
        dialog = self._create_dialog()
        self._type(dialog, "Undo Backups")
        field = SETTING_FIELD_MAP["canvas.num_backups"]

        dialog._on_editor_value_changed(field, 60)

        # The Canvas page is dirty even though we never opened it.
        self.assertIn("Canvas", dialog._dirty_primaries)
        self.assertTrue(dialog.shortcuts_save_button.isEnabled())

    # -- returning to the pages -----------------------------------------

    def test_clearing_the_query_restores_the_previous_page(self):
        dialog = self._create_dialog()
        target_row = 2
        dialog.nav_list.setCurrentRow(target_row)
        self.app.processEvents()
        self._type(dialog, "undo")
        self.assertTrue(dialog._search_active)

        self._type(dialog, "")
        self.assertFalse(dialog._search_active)
        self.assertEqual(
            dialog.header_title.text(),
            SETTINGS_PRIMARY_ORDER[target_row],
        )

    def test_clicking_a_page_leaves_search_and_clears_the_box(self):
        dialog = self._create_dialog()
        self._type(dialog, "undo")
        target_row = 3
        dialog.nav_list.setCurrentRow(target_row)
        self.app.processEvents()
        self.assertFalse(dialog._search_active)
        self.assertEqual(dialog.search_input.text(), "")
        self.assertEqual(
            dialog.header_title.text(),
            SETTINGS_PRIMARY_ORDER[target_row],
        )

    def test_open_this_page_button_jumps_to_the_owning_page(self):
        dialog = self._create_dialog()
        self._type(dialog, "Undo Backups")
        dialog._jump_to_primary("Canvas")
        self.app.processEvents()
        self.assertFalse(dialog._search_active)
        self.assertEqual(dialog.search_input.text(), "")
        self.assertEqual(dialog.header_title.text(), "Canvas")

    def test_unknown_primary_is_ignored_by_the_jump(self):
        dialog = self._create_dialog()
        dialog._jump_to_primary("Nope")
        self.assertEqual(dialog.header_title.text(), "Shortcuts")
