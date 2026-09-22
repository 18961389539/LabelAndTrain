import copy
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtGui, QtWidgets

    from anylabeling.views.labeling.settings.controller import SettingsController
    from anylabeling.views.labeling.settings.dialog import SettingsDialog
    from anylabeling.views.labeling.settings.schema import load_template_config

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required for settings dialog tests")
class TestSettingsDialogLayout(unittest.TestCase):

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
        # Closing now prompts about pending edits; tests opt into the prompt
        # explicitly so a stray dirty page cannot block the suite on a modal.
        dialog._confirm_discard_unsaved = lambda: True
        dialog.show()
        self.app.processEvents()
        self._resources.append((dialog, controller))
        return dialog

    def test_general_uses_viewport_gap_and_fixed_bottom_height(self):
        dialog = self._create_dialog()
        dialog._render_primary("General")
        self.app.processEvents()

        viewport_margins = dialog.content_scroll.viewportMargins()
        self.assertEqual(viewport_margins.top(), 8)
        self.assertEqual(viewport_margins.bottom(), 8)

        body_margins = dialog.content_body_layout.contentsMargins()
        self.assertEqual(body_margins.left(), 0)
        self.assertEqual(body_margins.top(), 0)
        self.assertEqual(body_margins.right(), 0)
        self.assertEqual(body_margins.bottom(), 0)
        self.assertEqual(dialog._content_bottom_spacer.height(), 16)
        bottom_margins = dialog.shortcuts_bottom_layout.contentsMargins()
        self.assertEqual(bottom_margins.left(), 0)
        self.assertEqual(bottom_margins.right(), 0)
        self.assertEqual(bottom_margins.top(), 8)
        self.assertEqual(bottom_margins.bottom(), 8)

        self.assertEqual(dialog.shortcuts_bottom_panel.minimumHeight(), 56)
        self.assertEqual(dialog.shortcuts_bottom_panel.maximumHeight(), 56)
        self.assertEqual(dialog.shortcuts_bottom_panel.height(), 56)

    def test_canvas_uses_same_viewport_gap(self):
        dialog = self._create_dialog()
        dialog._render_primary("Canvas")
        self.app.processEvents()

        viewport_margins = dialog.content_scroll.viewportMargins()
        self.assertEqual(viewport_margins.top(), 8)
        self.assertEqual(viewport_margins.bottom(), 8)

        body_margins = dialog.content_body_layout.contentsMargins()
        self.assertEqual(body_margins.left(), 0)
        self.assertEqual(body_margins.top(), 0)
        self.assertEqual(body_margins.right(), 0)
        self.assertEqual(body_margins.bottom(), 0)
        self.assertEqual(dialog._content_bottom_spacer.height(), 16)
        bottom_margins = dialog.shortcuts_bottom_layout.contentsMargins()
        self.assertEqual(bottom_margins.left(), 0)
        self.assertEqual(bottom_margins.right(), 0)
        self.assertEqual(bottom_margins.top(), 8)
        self.assertEqual(bottom_margins.bottom(), 8)

    def test_shape_uses_same_viewport_gap(self):
        dialog = self._create_dialog()
        dialog._render_primary("Shape")
        self.app.processEvents()

        viewport_margins = dialog.content_scroll.viewportMargins()
        self.assertEqual(viewport_margins.top(), 8)
        self.assertEqual(viewport_margins.bottom(), 8)

        body_margins = dialog.content_body_layout.contentsMargins()
        self.assertEqual(body_margins.left(), 0)
        self.assertEqual(body_margins.top(), 0)
        self.assertEqual(body_margins.right(), 0)
        self.assertEqual(body_margins.bottom(), 0)
        self.assertEqual(dialog._content_bottom_spacer.height(), 16)
        bottom_margins = dialog.shortcuts_bottom_layout.contentsMargins()
        self.assertEqual(bottom_margins.left(), 0)
        self.assertEqual(bottom_margins.right(), 0)
        self.assertEqual(bottom_margins.top(), 8)
        self.assertEqual(bottom_margins.bottom(), 8)

    def test_general_titles_remain_english_while_descriptions_translate(self):
        with mock.patch.object(
            SettingsDialog,
            "tr",
            lambda _self, text: f"zh:{text}",
        ):
            dialog = self._create_dialog()
            dialog._render_primary("General")
            self.app.processEvents()

        first_row = dialog.content_body_layout.itemAt(0).widget()
        self.assertIsNotNone(first_row)
        first_row_texts = [
            label.text() for label in first_row.findChildren(QtWidgets.QLabel)
        ]
        self.assertIn("Auto Highlight Shape", first_row_texts)
        self.assertNotIn("zh:Auto Highlight Shape", first_row_texts)
        self.assertIn(
            "zh:In edit mode, automatically highlight vertices of selected objects.",
            first_row_texts,
        )

    def test_general_optional_integer_shows_qt_default_value(self):
        dialog = self._create_dialog()
        dialog._render_primary("General")
        self.app.processEvents()

        spinboxes = dialog.content_body.findChildren(QtWidgets.QSpinBox)
        self.assertEqual(len(spinboxes), 1)
        self.assertEqual(spinboxes[0].value(), 256)

    def test_general_font_selector_lists_available_font_families(self):
        dialog = self._create_dialog()
        dialog._render_primary("General")
        self.app.processEvents()

        font_combo = next(
            combo
            for combo in dialog.content_body.findChildren(QtWidgets.QComboBox)
            if combo.findData(None) >= 0
        )
        available_families = QtGui.QFontDatabase.families()
        listed_families = [
            font_combo.itemData(index)
            for index in range(1, font_combo.count())
        ]
        self.assertIsNone(font_combo.itemData(0))
        self.assertEqual(listed_families, available_families)

        if available_families:
            font_combo.setCurrentIndex(1)
            self.assertEqual(
                dialog._controller.get_value("font_family"),
                available_families[0],
            )

    def test_shortcuts_reset_viewport_margins(self):
        dialog = self._create_dialog()
        dialog._render_primary("General")
        self.app.processEvents()

        viewport_margins = dialog.content_scroll.viewportMargins()
        self.assertEqual(viewport_margins.top(), 8)
        self.assertEqual(viewport_margins.bottom(), 8)

        dialog._render_primary("Shortcuts")
        self.app.processEvents()
        viewport_margins = dialog.content_scroll.viewportMargins()
        self.assertEqual(viewport_margins.top(), 0)
        self.assertEqual(viewport_margins.bottom(), 0)
        self.assertEqual(dialog._content_bottom_spacer.height(), 0)
        bottom_margins = dialog.shortcuts_bottom_layout.contentsMargins()
        self.assertEqual(bottom_margins.left(), 16)
        self.assertEqual(bottom_margins.right(), 16)
        self.assertEqual(bottom_margins.top(), 8)
        self.assertEqual(bottom_margins.bottom(), 8)

    def test_shortcuts_reset_handles_transient_conflict(self):
        dialog = self._create_dialog()
        dialog._render_primary("Shortcuts")
        self.app.processEvents()

        group_list = dialog._shortcut_group_list
        self.assertIsNotNone(group_list)
        for row in range(group_list.count()):
            if group_list.item(row).text().startswith("View"):
                group_list.setCurrentRow(row)
                break
        self.app.processEvents()

        controller = dialog._controller
        controller.update_field(
            "shortcuts.show_masks",
            "Alt+M",
            schedule_save=False,
        )
        controller.update_field(
            "shortcuts.show_labels",
            "Ctrl+M",
            schedule_save=False,
        )
        dialog._confirm_reset = lambda *_args, **_kwargs: True

        dialog._on_shortcuts_reset_clicked()
        self.app.processEvents()

        self.assertEqual(controller.get_value("shortcuts.show_masks"), "Ctrl+M")
        self.assertEqual(
            controller.get_value("shortcuts.show_labels"),
            "Ctrl+L",
        )

    def test_close_discards_unsaved_changes(self):
        dialog = self._create_dialog()
        controller = dialog._controller
        initial_value = controller.get_value("model_hub")
        # Pick any option that differs from the current value.
        options = controller._field_map["model_hub"].options
        next_value = next(v for v in options if v != initial_value)

        controller.update_field("model_hub", next_value, schedule_save=False)
        self.assertEqual(controller.get_value("model_hub"), next_value)

        dialog._confirm_discard_unsaved = lambda: True
        dialog.close()
        self.app.processEvents()

        self.assertEqual(controller.get_value("model_hub"), initial_value)

    def _mark_hub_dirty(self, dialog):
        """Change model_hub through the editor path, as the UI does."""
        controller = dialog._controller
        field = controller._field_map["model_hub"]
        initial_value = controller.get_value(field.key)
        next_value = next(
            v for v in field.options if v != initial_value
        )
        dialog._on_editor_value_changed(field, next_value)
        self.app.processEvents()
        return field, initial_value, next_value

    def test_close_with_unsaved_changes_asks_before_discarding(self):
        dialog = self._create_dialog()
        controller = dialog._controller
        _field, initial_value, next_value = self._mark_hub_dirty(dialog)

        self.assertEqual(controller.get_value("model_hub"), next_value)
        self.assertEqual(dialog._dirty_primaries, {"General"})

        asked = []

        def fake_confirm():
            asked.append(sorted(dialog._dirty_primaries))
            return False

        dialog._confirm_discard_unsaved = fake_confirm
        dialog.close()
        self.app.processEvents()

        self.assertEqual(asked, [["General"]])
        self.assertTrue(dialog._dirty_primaries)
        self.assertEqual(controller.get_value("model_hub"), next_value)
        self.assertTrue(dialog.isVisible())

    def test_prompt_names_the_dirty_pages(self):
        dialog = self._create_dialog()
        dialog._set_primary_dirty("Canvas", True)
        dialog._set_primary_dirty("General", True)
        text = dialog._dirty_pages_text()
        self.assertIn(dialog._display_primary_text("Canvas"), text)
        self.assertIn(dialog._display_primary_text("General"), text)
        self.assertLess(
            text.index(dialog._display_primary_text("Canvas")),
            text.index(dialog._display_primary_text("General")),
        )

    def test_clean_close_does_not_ask(self):
        dialog = self._create_dialog()
        calls = []
        dialog._confirm_discard_unsaved = lambda: calls.append(1) or True
        dialog.close()
        self.app.processEvents()
        self.assertEqual(calls, [1])
        self.assertFalse(dialog.isVisible())

    def test_save_and_close_persists_edits(self):
        dialog = self._create_dialog()
        del dialog._confirm_discard_unsaved
        controller = dialog._controller
        saved = []
        controller._save_callback = lambda cfg: saved.append(cfg) or True
        self._mark_hub_dirty(dialog)

        dialog._on_save_clicked()
        self.app.processEvents()

        self.assertEqual(len(saved), 1)
        self.assertFalse(dialog._dirty_primaries)
        # Nothing pending anymore, so closing must not prompt.
        dialog.close()
        self.app.processEvents()
        self.assertEqual(controller.get_value("model_hub"), saved[0]["model_hub"])
