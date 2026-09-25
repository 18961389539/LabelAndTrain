import unittest

try:
    from anylabeling.views.labeling.utils.shortcuts_help import (
        SHORTCUT_GROUPS,
    )
    from anylabeling.views.labeling.settings.schema import (
        EXCLUDED_KEYS,
        SETTING_FIELD_MAP,
        SETTING_FIELDS,
        SETTINGS_KEYS,
        SETTINGS_GENERAL_KEYS,
        SETTINGS_SHAPE_KEYS,
        SETTINGS_PRIMARY_ORDER,
        SETTINGS_SHORTCUT_KEYS_CORE,
        defaults_map,
        fields_for_primary,
    )

    SCHEMA_AVAILABLE = True
except Exception:
    SCHEMA_AVAILABLE = False


@unittest.skipUnless(
    SCHEMA_AVAILABLE, "Settings schema dependencies are unavailable"
)
class TestSettingsSchema(unittest.TestCase):

    def test_field_count(self):
        # No exact count: the schema is derived from the template yaml, so a
        # field change is an explicit yaml edit. This only guards against a
        # wholesale regression (e.g. derivation returning an empty/broken set).
        self.assertGreater(len(SETTING_FIELDS), 100)

    def test_shortcut_and_non_shortcut_count(self):
        shortcut_fields = [
            field for field in SETTING_FIELDS if field.primary == "Shortcuts"
        ]
        # Single explicit anchor for shortcut-count changes: bump this number
        # when the yaml shortcut section is deliberately edited. The real
        # invariant (every advertised key is rebindable) lives in
        # test_fields_for_primary.
        # +mark_checked_and_next, +show_shortcuts_help: both used to be
        # hard-coded literals on the QAction, so nothing could rebind them.
        # +mark_rejected_and_next: the "send back for rework" quick action.
        # +open_project: the project switcher (Ctrl+Shift+O).
        # -show_linking, -toggle_compare_view: no action ever bound them
        # (KIE linking is off in this YOLO-only fork and the compare view was
        # never implemented), so they were dropped instead of advertised.
        self.assertEqual(len(shortcut_fields), 74)
        keys = {field.key for field in shortcut_fields}
        self.assertIn("shortcuts.open_project", keys)
        self.assertIn("shortcuts.mark_checked_and_next", keys)
        self.assertIn("shortcuts.mark_rejected_and_next", keys)
        self.assertIn("shortcuts.show_shortcuts_help", keys)
        self.assertIn("shortcuts.show_attributes", keys)
        self.assertNotIn("shortcuts.show_linking", keys)
        self.assertNotIn("shortcuts.toggle_compare_view", keys)
        for shape_mode in (
            "create_cuboid",
            "create_rotation",
            "create_quadrilateral",
            "create_circle",
            "create_line",
            "create_linestrip",
        ):
            self.assertIn(f"shortcuts.{shape_mode}", keys)

    def test_defaults_cover_all_keys(self):
        defaults = defaults_map()
        self.assertEqual(set(defaults.keys()), set(SETTINGS_KEYS))

    def test_undo_depth_default_is_deeper_than_the_old_ten(self):
        defaults = defaults_map()
        # 10 snapshots ran out after a handful of edits on one frame; 100 is
        # the new shipped default and stays inside the field's 0..200 range.
        self.assertEqual(defaults["canvas.num_backups"], 100)
        field = SETTING_FIELD_MAP["canvas.num_backups"]
        self.assertLessEqual(100, field.maximum)

    def test_included_and_excluded_keys(self):
        expected_keys = {
            "display_label_popup",
            "auto_switch_to_edit_mode",
            "system_clipboard",
            "font_family",
            "shape.line_color",
            "canvas.mask.opacity",
            "canvas.crosshair.show",
            "canvas.crosshair.width",
            "canvas.crosshair.color",
            "canvas.crosshair.opacity",
            "canvas.brush.point_distance",
            "canvas.brush.simplify_epsilon",
            "model_hub",
            "logger_level",
            "shortcuts.open",
            "shortcuts.zoom_in",
            "shortcuts.add_point_to_edge",
            "shortcuts.quit",
            "shortcuts.open_settings",
            "shortcuts.auto_labeling_add_point",
            "shortcuts.auto_labeling_finish_object",
        }
        for key in expected_keys:
            self.assertIn(key, SETTINGS_KEYS)

        for key in EXCLUDED_KEYS:
            self.assertNotIn(key, SETTINGS_KEYS)

    def test_primary_and_key_sets(self):
        self.assertEqual(
            SETTINGS_PRIMARY_ORDER,
            ("Shortcuts", "General", "Shape", "Canvas"),
        )
        for key in SETTINGS_GENERAL_KEYS:
            self.assertIn(key, SETTINGS_KEYS)
        for key in SETTINGS_SHAPE_KEYS:
            self.assertIn(key, SETTINGS_KEYS)
        for key in SETTINGS_SHORTCUT_KEYS_CORE:
            self.assertIn(key, SETTINGS_KEYS)

    def test_fields_for_primary(self):
        general_fields = fields_for_primary("General")
        shape_fields = fields_for_primary("Shape")
        shortcut_fields = fields_for_primary("Shortcuts")
        canvas_fields = fields_for_primary("Canvas")
        self.assertEqual(
            [field.key for field in general_fields],
            list(SETTINGS_GENERAL_KEYS),
        )
        self.assertEqual(
            [field.key for field in shape_fields], list(SETTINGS_SHAPE_KEYS)
        )
        shape_keys = {field.key for field in shape_fields}
        self.assertIn("shape.line_color", shape_keys)
        self.assertIn("shape.point_size", shape_keys)
        self.assertIn("shape.line_width", shape_keys)
        for key in SETTINGS_SHORTCUT_KEYS_CORE:
            self.assertIn(key, [field.key for field in shortcut_fields])
        # Every advertised key must be rebindable, or the help dialog points at
        # a shortcut the Shortcuts page cannot change.
        shortcut_keys = {field.key for field in shortcut_fields}
        advertised = {
            f"shortcuts.{key}"
            for _title, entries in SHORTCUT_GROUPS
            for key, _desc in entries
        }
        self.assertEqual(
            sorted(advertised - shortcut_keys),
            [],
        )
        canvas_keys = {field.key for field in canvas_fields}
        self.assertIn("canvas.crosshair.show", canvas_keys)
        self.assertIn("canvas.crosshair.width", canvas_keys)
        self.assertIn("canvas.crosshair.color", canvas_keys)
        self.assertIn("canvas.crosshair.opacity", canvas_keys)
        self.assertIn("canvas.brush.point_distance", canvas_keys)
        self.assertIn("canvas.brush.simplify_epsilon", canvas_keys)

    def test_visible_non_shortcut_fields_have_descriptions(self):
        fields = (
            fields_for_primary("General")
            + fields_for_primary("Shape")
            + fields_for_primary("Canvas")
        )
        self.assertTrue(all(field.description for field in fields))
