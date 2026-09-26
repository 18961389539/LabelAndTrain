import os
import os.path as osp
import tempfile
import unittest

from anylabeling.views.labeling.utils.archiver import (
    ARCHIVE_DIRNAME,
    archive_duplicates_plan,
    finalize_moves,
)


class TestArchiveDuplicatesPlan(unittest.TestCase):

    def _make_dir(self, tmp):
        base = osp.join(tmp, "data")
        os.makedirs(base)
        for name in ("a", "b", "c"):
            with open(osp.join(base, f"{name}.jpg"), "wb") as f:
                f.write(b"x")
            with open(osp.join(base, f"{name}.json"), "w", encoding="utf-8") as f:
                f.write("{}")
        return base

    def test_keeps_one_representative_per_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._make_dir(tmp)
            groups = [
                [osp.join(base, "a.jpg"), osp.join(base, "b.jpg")],
                [osp.join(base, "c.jpg")],
            ]
            plan = archive_duplicates_plan(groups, base)
            sources = [src for src, _ in plan]
            # "b" is the duplicate; "a" and "c" stay in place.
            self.assertEqual(sources, [osp.join(base, "b.jpg"),
                                       osp.join(base, "b.json")])
            for _, dst in plan:
                self.assertTrue(dst.startswith(osp.join(base, ARCHIVE_DIRNAME)))

    def test_missing_files_are_filtered_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._make_dir(tmp)
            groups = [
                [osp.join(base, "a.jpg"), osp.join(base, "ghost.jpg")],
                [osp.join(base, "c.jpg")],
            ]
            plan = archive_duplicates_plan(groups, base)
            self.assertEqual(plan, [])

    def test_empty_input(self):
        self.assertEqual(archive_duplicates_plan([], "/tmp"), [])
        self.assertEqual(archive_duplicates_plan([[ "x.jpg" ]], None), [])

    def test_no_duplicate_names_collide(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._make_dir(tmp)
            sub = osp.join(base, "nested")
            os.makedirs(sub)
            with open(osp.join(sub, "a.jpg"), "wb") as f:
                f.write(b"y")
            groups = [
                [osp.join(base, "c.jpg"), osp.join(base, "a.jpg")],
                [osp.join(sub, "a.jpg")],
            ]
            plan = archive_duplicates_plan(groups, base)
            sources = [src for src, _ in plan]
            self.assertIn(osp.join(base, "a.jpg"), sources)
            self.assertNotIn(osp.join(sub, "a.jpg"), sources)


class TestFinalizeMoves(unittest.TestCase):

    def test_moves_files_and_sidecars(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = osp.join(tmp, "data")
            os.makedirs(base)
            src = osp.join(base, "b.jpg")
            with open(src, "wb") as f:
                f.write(b"x")
            archive_dir = osp.join(base, ARCHIVE_DIRNAME)
            dst = osp.join(archive_dir, "b.jpg")
            moved, skipped = finalize_moves([(src, dst)])
            self.assertEqual(skipped, [])
            self.assertEqual(moved, [(src, dst)])
            self.assertTrue(osp.exists(dst))
            self.assertFalse(osp.exists(src))

    def test_missing_source_is_skipped(self):
        moved, skipped = finalize_moves([("/no/such/a.jpg", "/tmp/a.jpg")])
        self.assertEqual(moved, [])
        self.assertEqual(skipped, ["/no/such/a.jpg"])

    def test_dry_run_plans_without_touching_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = osp.join(tmp, "a.jpg")
            with open(src, "wb") as f:
                f.write(b"x")
            dst = osp.join(tmp, "sub", "a.jpg")
            moved, skipped = finalize_moves([(src, dst)], dry_run=True)
            self.assertEqual(skipped, [])
            self.assertEqual(moved, [(src, dst)])
            self.assertFalse(osp.exists(dst))

    def test_destination_collision_gets_unique_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = osp.join(tmp, "a.jpg")
            with open(src, "wb") as f:
                f.write(b"x")
            dst = osp.join(tmp, "a.jpg")
            with open(dst, "wb") as f:
                f.write(b"existing")
            moved, _ = finalize_moves([(src, dst)])
            self.assertEqual(moved[0][1], osp.join(tmp, "a.1.jpg"))


if __name__ == "__main__":
    unittest.main()
