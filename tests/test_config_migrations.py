"""Config version migrations: old shipped defaults move, choices stay."""

import unittest

from anylabeling.config import _apply_config_migrations


class TestConfigMigrations(unittest.TestCase):
    def test_old_default_migrates_to_new(self):
        # No config_version stamp = pre-versioning rc.
        rc = {"canvas": {"num_backups": 10}}
        _apply_config_migrations(rc)
        self.assertEqual(rc["canvas"]["num_backups"], 100)
        self.assertEqual(rc["config_version"], 1)

    def test_user_choice_is_left_alone(self):
        rc = {"config_version": 0, "canvas": {"num_backups": 42}}
        _apply_config_migrations(rc)
        self.assertEqual(rc["canvas"]["num_backups"], 42)
        self.assertEqual(rc["config_version"], 1)

    def test_current_version_skips_migrations(self):
        rc = {"config_version": 1, "canvas": {"num_backups": 10}}
        _apply_config_migrations(rc)
        self.assertEqual(rc["canvas"]["num_backups"], 10)

    def test_missing_key_is_ignored(self):
        rc = {}
        _apply_config_migrations(rc)
        self.assertEqual(rc["config_version"], 1)
        self.assertNotIn("canvas", rc)


if __name__ == "__main__":
    unittest.main()
