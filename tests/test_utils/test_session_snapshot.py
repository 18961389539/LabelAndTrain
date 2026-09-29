"""Pre-write session snapshots: the recovery path the undo stack cannot be.

``canvas.py`` says outright that the undo history does not survive a file
switch, and an auto-save overwrites the only copy on disk a few hundred
milliseconds after an edit. These tests pin the resulting contract: one
copy per (session, label file) of the state it had before this session
first wrote to it, in the same ``.label_backups`` namespace the batch tools
use, so the existing restore picker already reaches it.
"""

import os
import os.path as osp
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from anylabeling.views.labeling.utils import file_lifecycle
from anylabeling.views.labeling.utils import session_snapshot
from anylabeling.views.labeling.utils import smart_tools


class SessionSnapshotTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="session-snapshot-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.label_dir = osp.join(self.root, "labels")
        os.makedirs(self.label_dir)
        session_snapshot.reset_session_snapshots()
        self.addCleanup(session_snapshot.reset_session_snapshots)

    def write_label(self, name, body, directory=None):
        path = osp.join(directory or self.label_dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
        return path

    def read(self, path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def json_names(self, run):
        return sorted(
            name for name in os.listdir(run) if name.endswith(".json")
        )

    def runs(self):
        return smart_tools.list_label_backups(self.label_dir)


class TestSnapshotBeforeWrite(SessionSnapshotTestCase):
    def test_a_first_save_has_no_earlier_state_to_keep(self):
        path = osp.join(self.label_dir, "new.json")
        self.assertIsNone(session_snapshot.snapshot_before_label_write(path))
        self.assertEqual(self.runs(), [])

    def test_the_snapshot_holds_the_state_before_the_write(self):
        path = self.write_label("a.json", "before")
        run = session_snapshot.snapshot_before_label_write(path)
        self.assertTrue(osp.isdir(run))
        self.assertEqual(self.read(osp.join(run, "a.json")), "before")

    def test_a_later_edit_never_replaces_the_baseline(self):
        path = self.write_label("a.json", "before")
        run = session_snapshot.snapshot_before_label_write(path)
        # The user edits; the edit is what lands on disk.
        self.write_label("a.json", "after")
        self.assertEqual(
            session_snapshot.snapshot_before_label_write(path), run
        )
        self.assertEqual(self.read(osp.join(run, "a.json")), "before")

    def test_a_second_file_joins_the_same_run(self):
        first = self.write_label("a.json", "a")
        second = self.write_label("b.json", "b")
        run = session_snapshot.snapshot_before_label_write(first)
        self.assertEqual(
            session_snapshot.snapshot_before_label_write(second), run
        )
        self.assertEqual(self.json_names(run), ["a.json", "b.json"])

    def test_each_directory_gets_its_own_run(self):
        other = osp.join(self.root, "other-labels")
        os.makedirs(other)
        first = self.write_label("a.json", "a")
        second = self.write_label("b.json", "b", directory=other)
        run_a = session_snapshot.snapshot_before_label_write(first)
        run_b = session_snapshot.snapshot_before_label_write(second)
        self.assertNotEqual(run_a, run_b)
        self.assertEqual(
            osp.dirname(run_a),
            osp.join(self.label_dir, smart_tools.BACKUP_ROOT_NAME),
        )
        self.assertEqual(
            osp.dirname(run_b),
            osp.join(other, smart_tools.BACKUP_ROOT_NAME),
        )

    def test_a_new_session_starts_a_new_run(self):
        path = self.write_label("a.json", "before")
        first = session_snapshot.snapshot_before_label_write(path)
        session_snapshot.reset_session_snapshots()
        self.write_label("a.json", "even later")
        second = session_snapshot.snapshot_before_label_write(path)
        self.assertNotEqual(first, second)


class TestSessionRunsReachThePicker(SessionSnapshotTestCase):
    def test_the_run_is_listed_and_marked_as_a_session_snapshot(self):
        path = self.write_label("a.json", "before")
        run = session_snapshot.snapshot_before_label_write(path)
        runs = self.runs()
        self.assertEqual([name for name, _p, _c in runs], [osp.basename(run)])
        self.assertTrue(smart_tools.is_session_snapshot(runs[0][1]))

    def test_the_marker_is_not_counted_as_a_label(self):
        path = self.write_label("a.json", "before")
        session_snapshot.snapshot_before_label_write(path)
        _name, _path, count = self.runs()[0]
        self.assertEqual(count, 1)

    def test_a_batch_run_carries_no_marker(self):
        path = self.write_label("a.json", "before")
        run = smart_tools.backup_label_files(
            [path], self.label_dir, "20260929_101112"
        )
        self.assertFalse(smart_tools.is_session_snapshot(run))

    def test_a_failed_copy_does_not_stop_the_write(self):
        path = self.write_label("a.json", "before")
        with mock.patch.object(
            session_snapshot.shutil, "copy2", side_effect=OSError("no space")
        ):
            self.assertIsNone(
                session_snapshot.snapshot_before_label_write(path)
            )
        # Nothing was remembered, so the next write tries again rather than
        # believing this session already has a baseline.
        self.assertIsNotNone(
            session_snapshot.snapshot_before_label_write(path)
        )


class TestSaveLabelsTakesItFirst(SessionSnapshotTestCase):
    def build_widget(self):
        return SimpleNamespace(
            label_list=[],
            flag_widget=SimpleNamespace(count=lambda: 0),
            other_data={},
            _annotation_checked=lambda: True,
            image_path=osp.join(self.root, "images", "a.jpg"),
            _config={"store_data": False},
            image=SimpleNamespace(height=lambda: 10, width=lambda: 10),
            file_list_widget=SimpleNamespace(
                findItems=lambda *args, **kwargs: []
            ),
        )

    def test_the_snapshot_is_taken_before_the_write(self):
        path = self.write_label("a.json", "before")
        order = []
        captured = {}

        class FakeLabelFile:
            def __init__(self, *args, **kwargs):
                pass

            def save(self, **kwargs):
                order.append("save")
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("after")
                return True

        real_snapshot = session_snapshot.snapshot_before_label_write

        def recorder(label_file):
            captured["run"] = real_snapshot(label_file)
            order.append("snapshot")
            return captured["run"]

        with mock.patch.object(file_lifecycle, "LabelFile", FakeLabelFile):
            with mock.patch.object(
                file_lifecycle, "snapshot_before_label_write", recorder
            ):
                with mock.patch.object(
                    file_lifecycle.file_list_ops,
                    "_note_save_quality",
                    lambda *a, **k: None,
                ):
                    self.assertTrue(
                        file_lifecycle.save_labels(self.build_widget(), path)
                    )

        self.assertEqual(order, ["snapshot", "save"])
        self.assertEqual(
            self.read(osp.join(captured["run"], "a.json")), "before"
        )
        self.assertEqual(self.read(path), "after")


if __name__ == "__main__":
    unittest.main()
