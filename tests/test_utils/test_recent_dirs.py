import os
import os.path as osp
import tempfile
import unittest

from anylabeling.views.labeling.utils.recent_dirs import (
    DEFAULT_MAX_ITEMS,
    drop_recent_dir,
    push_recent_dir,
)


class TestPushRecentDir(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.a = osp.join(self._tmp.name, "alpha")
        self.b = osp.join(self._tmp.name, "beta")
        os.makedirs(self.a)
        os.makedirs(self.b)

    def test_returns_newest_first(self):
        result = push_recent_dir([self.b], self.a)
        self.assertEqual(result, [osp.normpath(self.a), osp.normpath(self.b)])

    def test_dedupes_and_moves_to_front(self):
        result = push_recent_dir([self.b, self.a], self.a)
        self.assertEqual(result, [osp.normpath(self.a), osp.normpath(self.b)])

    def test_case_insensitive_dedupe(self):
        upper = osp.join(self._tmp.name, "ALPHA")
        result = push_recent_dir([upper], self.a)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], osp.normpath(self.a))

    def test_trims_to_max(self):
        dirs = []
        for index in range(DEFAULT_MAX_ITEMS + 3):
            path = osp.join(self._tmp.name, f"d{index}")
            os.makedirs(path)
            dirs.append(path)
        result = push_recent_dir(dirs, self.a)
        self.assertEqual(len(result), DEFAULT_MAX_ITEMS)
        self.assertEqual(result[0], osp.normpath(self.a))

    def test_drops_missing_paths(self):
        ghost = osp.join(self._tmp.name, "ghost")
        result = push_recent_dir([ghost], self.a)
        self.assertEqual(result, [osp.normpath(self.a)])

    def test_empty_directory_returns_unchanged(self):
        result = push_recent_dir([self.b], None)
        self.assertEqual(result, [self.b])
        self.assertEqual(push_recent_dir([], ""), [])


class TestDropRecentDir(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.a = osp.join(self._tmp.name, "alpha")
        os.makedirs(self.a)

    def test_removes_entry(self):
        result = drop_recent_dir([self.a, "/no/such"], self.a)
        self.assertEqual(result, ["/no/such"])

    def test_case_insensitive_removal(self):
        upper = osp.join(self._tmp.name, "ALPHA")
        self.assertEqual(drop_recent_dir([self.a], upper), [])

    def test_no_match_returns_same(self):
        self.assertEqual(drop_recent_dir([self.a], "/elsewhere"), [self.a])


if __name__ == "__main__":
    unittest.main()
