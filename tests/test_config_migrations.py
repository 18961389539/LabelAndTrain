"""Config version migrations: old shipped defaults move, choices stay."""

import copy
import unittest

from jllabeling.config import _apply_config_migrations

#: Bump together with ``config_version`` in jllabeling_config.yaml.
CURRENT_VERSION = 3

#: Every old shipped default replaced in v3, and its replacement.
V3_OLD_DEFAULTS = {
    "qt_image_allocation_limit": None,
    "exif_scan_enabled": True,
    "startup_show_project_manager": True,
    "file_list_checkbox_editable": False,
    "training": {"ultralytics": {"project_readonly": True}},
    "canvas": {"num_backups": 100, "brush": {"max_undo_memory_mb": 128}},
    "shortcuts": {
        "undo_last_point": "Ctrl+Z",
        "auto_labeling_run": "I",
    },
}
V3_NEW_DEFAULTS = {
    "qt_image_allocation_limit": 1024,
    "exif_scan_enabled": False,
    "startup_show_project_manager": False,
    "file_list_checkbox_editable": True,
    "training": {"ultralytics": {"project_readonly": False}},
    "canvas": {"num_backups": 30, "brush": {"max_undo_memory_mb": 64}},
    "shortcuts": {
        "undo_last_point": "Ctrl+Shift+Backspace",
        "auto_labeling_run": "Ctrl+Shift+I",
    },
}


def _assert_defaults(testcase, rc, expected):
    for key, value in expected.items():
        if isinstance(value, dict):
            _assert_defaults(testcase, rc[key], value)
        else:
            testcase.assertEqual(
                rc[key], value, f"default {key!r} did not migrate"
            )


class TestConfigMigrations(unittest.TestCase):
    def test_old_default_migrates_to_new(self):
        # No config_version stamp = pre-versioning rc. It is brought all
        # the way up: v1 (10 -> 100) then v3 (100 -> 30).
        rc = {"canvas": {"num_backups": 10}}
        _apply_config_migrations(rc)
        self.assertEqual(rc["canvas"]["num_backups"], 30)
        self.assertEqual(rc["config_version"], CURRENT_VERSION)

    def test_version2_null_digit_shortcuts_enable_auto_assign(self):
        # v2: the shipped default was null, which left the 0-9 keys dead
        # with no hint they existed. An rc still carrying that untouched
        # default is flipped to {} (auto-assign on).
        rc = {"config_version": 1, "digit_shortcuts": None}
        _apply_config_migrations(rc)
        self.assertEqual(rc["digit_shortcuts"], {})
        self.assertEqual(rc["config_version"], CURRENT_VERSION)

    def test_version2_pre_versioning_rc_also_migrates(self):
        # A rc with no config_version stamp at all gets every generation.
        rc = {"digit_shortcuts": None}
        _apply_config_migrations(rc)
        self.assertEqual(rc["digit_shortcuts"], {})

    def test_version2_configured_map_is_left_alone(self):
        # A deliberately configured map is a user choice, not the old
        # shipped default.
        chosen = {"1": {"label": "scratch", "mode": "rectangle"}}
        rc = {"config_version": 1, "digit_shortcuts": chosen}
        _apply_config_migrations(rc)
        self.assertEqual(rc["digit_shortcuts"], chosen)

    def test_version2_hand_edited_null_survives_once_stamped(self):
        # null is the feature's off switch. After the one-time v2 pass the
        # rc is stamped, so a hand-edited null is never flipped back.
        rc = {"config_version": 2, "digit_shortcuts": None}
        _apply_config_migrations(rc)
        self.assertIsNone(rc["digit_shortcuts"])

    def test_user_choice_is_left_alone(self):
        rc = {"config_version": 0, "canvas": {"num_backups": 42}}
        _apply_config_migrations(rc)
        self.assertEqual(rc["canvas"]["num_backups"], 42)
        self.assertEqual(rc["config_version"], CURRENT_VERSION)

    def test_current_version_skips_migrations(self):
        rc = {
            "config_version": CURRENT_VERSION,
            "canvas": {"num_backups": 42},
        }
        _apply_config_migrations(rc)
        self.assertEqual(rc["canvas"]["num_backups"], 42)
        self.assertEqual(rc["config_version"], CURRENT_VERSION)

    def test_missing_key_is_ignored(self):
        rc = {}
        _apply_config_migrations(rc)
        self.assertEqual(rc["config_version"], CURRENT_VERSION)
        self.assertNotIn("canvas", rc)

    # --- v3 -------------------------------------------------------------

    def test_version3_migrates_every_old_shipped_default(self):
        rc = copy.deepcopy(V3_OLD_DEFAULTS)
        rc["config_version"] = 2
        _apply_config_migrations(rc)
        _assert_defaults(self, rc, V3_NEW_DEFAULTS)
        self.assertEqual(rc["config_version"], CURRENT_VERSION)

    def test_version3_pre_versioning_rc_gets_every_generation(self):
        rc = copy.deepcopy(V3_OLD_DEFAULTS)
        rc["canvas"]["num_backups"] = 10  # the original v1 default
        rc["digit_shortcuts"] = None  # the original v2 default
        _apply_config_migrations(rc)
        self.assertEqual(rc["canvas"]["num_backups"], 30)
        self.assertFalse(rc["exif_scan_enabled"])
        self.assertEqual(rc["digit_shortcuts"], {})
        self.assertEqual(rc["config_version"], CURRENT_VERSION)

    def test_version3_leaves_user_choices_alone(self):
        """A value that differs from the old default is a user choice.

        Boolean keys cannot express "I deliberately kept the old default":
        there are only two values, and the migration has no way to tell an
        untouched rc from a deliberate choice. That limitation is pinned by
        the next test; here we cover everything that CAN be distinguished.
        """
        rc = {
            "config_version": 2,
            "qt_image_allocation_limit": 2048,
            "canvas": {
                "num_backups": 200,
                "brush": {"max_undo_memory_mb": 256},
            },
            "shortcuts": {
                "undo_last_point": "Alt+Z",
                "auto_labeling_run": "F2",
            },
        }
        _apply_config_migrations(rc)
        self.assertEqual(rc["qt_image_allocation_limit"], 2048)
        self.assertEqual(rc["canvas"]["num_backups"], 200)
        self.assertEqual(rc["canvas"]["brush"]["max_undo_memory_mb"], 256)
        self.assertEqual(rc["shortcuts"]["undo_last_point"], "Alt+Z")
        self.assertEqual(rc["shortcuts"]["auto_labeling_run"], "F2")

    def test_version3_bool_defaults_cannot_distinguish_explicit_choice(self):
        """Documented limitation of the default-value migration mechanism.

        Flipping a bool shipped default also flips a user who explicitly set
        the OLD value. They can set it back afterwards; once the rc is stamped
        v3 it will never be flipped again. Keeping the behaviour visible in a
        test is better than discovering it in a bug report.
        """
        rc = {
            "config_version": 2,
            "exif_scan_enabled": True,
            "startup_show_project_manager": True,
            "file_list_checkbox_editable": False,
            "training": {"ultralytics": {"project_readonly": True}},
        }
        _apply_config_migrations(rc)
        self.assertFalse(rc["exif_scan_enabled"])
        self.assertFalse(rc["startup_show_project_manager"])
        self.assertTrue(rc["file_list_checkbox_editable"])
        self.assertFalse(rc["training"]["ultralytics"]["project_readonly"])
        self.assertEqual(rc["config_version"], CURRENT_VERSION)

    def test_version3_already_current_keeps_old_looking_values(self):
        """Once stamped v3, even an old-looking value is a user choice."""
        rc = {
            "config_version": CURRENT_VERSION,
            "shortcuts": {"undo_last_point": "Ctrl+Z"},
            "exif_scan_enabled": True,
        }
        _apply_config_migrations(rc)
        self.assertEqual(rc["shortcuts"]["undo_last_point"], "Ctrl+Z")
        self.assertTrue(rc["exif_scan_enabled"])


if __name__ == "__main__":
    unittest.main()
