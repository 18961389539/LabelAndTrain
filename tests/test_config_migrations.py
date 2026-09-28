"""Config version migrations: old shipped defaults move, choices stay."""

import unittest

from anylabeling.config import _apply_config_migrations


class TestConfigMigrations(unittest.TestCase):
    def test_old_default_migrates_to_new(self):
        # No config_version stamp = pre-versioning rc. It is brought all
        # the way up to the template's current version.
        rc = {"canvas": {"num_backups": 10}}
        _apply_config_migrations(rc)
        self.assertEqual(rc["canvas"]["num_backups"], 100)
        self.assertEqual(rc["config_version"], 2)

    def test_version2_null_digit_shortcuts_enable_auto_assign(self):
        # v2: the shipped default was null, which left the 0-9 keys dead
        # with no hint they existed. An rc still carrying that untouched
        # default is flipped to {} (auto-assign on).
        rc = {"config_version": 1, "digit_shortcuts": None}
        _apply_config_migrations(rc)
        self.assertEqual(rc["digit_shortcuts"], {})
        self.assertEqual(rc["config_version"], 2)

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
        # rc is stamped version 2, so a hand-edited null is never flipped
        # back.
        rc = {"config_version": 2, "digit_shortcuts": None}
        _apply_config_migrations(rc)
        self.assertIsNone(rc["digit_shortcuts"])

    def test_user_choice_is_left_alone(self):
        rc = {"config_version": 0, "canvas": {"num_backups": 42}}
        _apply_config_migrations(rc)
        self.assertEqual(rc["canvas"]["num_backups"], 42)
        self.assertEqual(rc["config_version"], 2)

    def test_current_version_skips_migrations(self):
        rc = {"config_version": 1, "canvas": {"num_backups": 10}}
        _apply_config_migrations(rc)
        self.assertEqual(rc["canvas"]["num_backups"], 10)

    def test_missing_key_is_ignored(self):
        rc = {}
        _apply_config_migrations(rc)
        self.assertEqual(rc["config_version"], 2)
        self.assertNotIn("canvas", rc)


if __name__ == "__main__":
    unittest.main()
