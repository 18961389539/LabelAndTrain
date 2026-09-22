import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from anylabeling.services.auto_labeling.model_manager import (
        ModelManager,
        pick_eviction_index,
    )

    MANAGER_AVAILABLE = True
except Exception:
    MANAGER_AVAILABLE = False


@unittest.skipUnless(MANAGER_AVAILABLE, "PyQt6 is required")
class TestCustomModelEviction(unittest.TestCase):
    def test_least_recently_used_wins(self):
        models = [
            {"config_file": "a.yaml", "last_used": 30},
            {"config_file": "b.yaml", "last_used": 10},
            {"config_file": "c.yaml", "last_used": 20},
        ]
        self.assertEqual(pick_eviction_index(models), 1)

    def test_entry_without_a_timestamp_is_oldest(self):
        models = [
            {"config_file": "a.yaml", "last_used": 1},
            {"config_file": "b.yaml"},
        ]
        self.assertEqual(pick_eviction_index(models), 1)

    def test_pinned_iterations_are_never_candidates(self):
        models = [
            {"config_file": "run01.yaml", "last_used": 1, "keep": True},
            {"config_file": "scratch.yaml", "last_used": 5},
        ]
        self.assertEqual(pick_eviction_index(models), 1)

    def test_all_pinned_returns_none(self):
        models = [
            {"config_file": "run01.yaml", "last_used": 1, "keep": True},
            {"config_file": "run02.yaml", "last_used": 2, "keep": True},
        ]
        self.assertIsNone(pick_eviction_index(models))

    def test_ties_resolve_to_the_first_index(self):
        models = [
            {"config_file": "a.yaml", "last_used": 7},
            {"config_file": "b.yaml", "last_used": 7},
        ]
        self.assertEqual(pick_eviction_index(models), 0)

    def test_empty_registry(self):
        self.assertIsNone(pick_eviction_index([]))

    def test_limit_leaves_room_for_several_iterations(self):
        # Five slots were too few: a handful of training rounds filled the
        # list and started evicting models the history still referenced.
        self.assertGreaterEqual(ModelManager.MAX_NUM_CUSTOM_MODELS, 30)


if __name__ == "__main__":
    unittest.main()
