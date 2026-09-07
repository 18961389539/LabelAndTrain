"""Atomic save helper: transient Windows-style lock errors must self-heal."""
import json
import os
import unittest
from unittest import mock

from anylabeling.views.labeling.utils._io import safe_replace, save_json


class FakeWindowsLockError(PermissionError):
    """Simulate WinError 5 (ERROR_ACCESS_DENIED)."""

    def __init__(self, path):
        super().__init__(5, "Access is denied", path)
        self.winerror = 5


class TestSafeReplace(unittest.TestCase):
    def test_succeeds_on_first_try(self):
        with mock.patch("os.replace") as m:
            safe_replace("src", "dst", attempts=3, delay=0)
            m.assert_called_once_with("src", "dst")

    def test_retries_then_succeeds_on_transient_lock(self):
        calls = {"n": 0}

        def fake_replace(src, dst):
            calls["n"] += 1
            if calls["n"] < 3:
                raise FakeWindowsLockError(dst)

        with mock.patch("os.replace", side_effect=fake_replace):
            with mock.patch("time.sleep") as sleep:
                safe_replace("src", "dst", attempts=5, delay=0.01)
                self.assertEqual(calls["n"], 3)
                # two sleeps before the successful third call
                self.assertEqual(sleep.call_count, 2)

    def test_exhausts_budget_and_raises_with_hint(self):
        with mock.patch(
            "os.replace", side_effect=FakeWindowsLockError("dst")
        ):
            with mock.patch("time.sleep"):
                with self.assertRaises(OSError) as cm:
                    safe_replace("src", "dst", attempts=4, delay=0)
        self.assertIn("无法替换", str(cm.exception))
        self.assertIn("杀软", str(cm.exception))

    def test_non_lock_oserror_propagates_immediately(self):
        with mock.patch(
            "os.replace",
            side_effect=OSError(2, "No such file or directory", "dst"),
        ):
            with self.assertRaises(OSError) as cm:
                safe_replace("src", "dst", attempts=5, delay=0)
            self.assertNotIn("无法替换", str(cm.exception))


class TestSaveJsonRetriesOnLock(unittest.TestCase):
    def test_save_json_survives_transient_replace_lock(self, tmp_dir=None):
        # Uses a real temp directory via tempfile under cwd for portability.
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "out.json")
            tmp_path_holder = {}

            real_replace = os.replace
            calls = {"n": 0}

            def fake_replace(src, dst):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise FakeWindowsLockError(dst)
                return real_replace(src, dst)

            with mock.patch("time.sleep"), mock.patch(
                "os.replace", side_effect=fake_replace
            ):
                save_json({"k": 1}, target)
            self.assertEqual(calls["n"], 2)
            self.assertTrue(os.path.exists(target))
            with open(target, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"k": 1})


if __name__ == "__main__":
    unittest.main()