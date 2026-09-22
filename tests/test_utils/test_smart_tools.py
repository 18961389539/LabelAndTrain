import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets

    from anylabeling.views.labeling.utils.smart_tools import (
        RESULT_CATEGORY_ROLE,
        RESULT_PATH_ROLE,
        _ResultDialog,
    )

    SMART_TOOLS_AVAILABLE = True
except Exception:
    SMART_TOOLS_AVAILABLE = False


@unittest.skipUnless(
    SMART_TOOLS_AVAILABLE, "PyQt6 is required for smart tools tests"
)
class TestResultDialog(unittest.TestCase):
    """Every smart-tool action renders through this dialog."""

    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        self.parent = QtWidgets.QWidget()

    def _dialog(self):
        return _ResultDialog(self.parent, "阈值校准", "双击条目可跳转")

    def test_add_category_fills_tree_without_error(self):
        dialog = self._dialog()
        root = dialog.add_category(
            "各类阈值",
            [("cat", ">= 0.5", "a.jpg"), ("dog", "< 0.5", None)],
        )
        self.assertEqual(dialog.tree.topLevelItemCount(), 1)
        self.assertEqual(root.childCount(), 2)
        self.assertEqual(root.child(0).text(0), "cat")
        self.assertEqual(root.child(1).text(1), "< 0.5")

    def test_rows_carry_jump_targets_and_category(self):
        dialog = self._dialog()
        root = dialog.add_category("难例", [("a.jpg", "不确定性 0.9", "a.jpg")])
        child = root.child(0)
        self.assertEqual(child.data(0, RESULT_PATH_ROLE), "a.jpg")
        self.assertEqual(child.data(0, RESULT_CATEGORY_ROLE), "难例")
        # A row without an image still stays selectable, just not jumpable.
        other = dialog.add_category("配平建议", [("多标一些猫", "", None)])
        self.assertEqual(other.child(0).data(0, RESULT_PATH_ROLE), "")

    def test_selected_rows_follow_the_tree(self):
        dialog = self._dialog()
        root = dialog.add_category("类别", [("a", "1", "a.jpg")])
        dialog.tree.setCurrentItem(root.child(0))
        self.assertEqual(len(dialog.selected_rows()), 1)
        self.assertEqual(len(dialog.all_rows()), 1)


if __name__ == "__main__":
    unittest.main()


class TestApplyStaleDeletions(unittest.TestCase):
    """The cleanup must only ever remove what the report actually showed."""

    def setUp(self):
        import tempfile

        from anylabeling.views.labeling.utils import smart_tools

        self.smart_tools = smart_tools
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, shapes, **extra):
        import json
        import os

        path = os.path.join(self.tmp.name, name)
        data = {"shapes": shapes, "checked": False}
        data.update(extra)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        return path

    def _read(self, path):
        import json

        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _model_box(self, label="cat", x=0.0):
        return {
            "label": label,
            "shape_type": "rectangle",
            "points": [[x, 0], [x + 10, 10]],
            "source": "model",
            "model": "run_01",
        }

    def _ref(self, shape, index):
        return {"index": index, "marker": self.smart_tools._shape_marker(shape)}

    def test_removes_only_the_referenced_stale_box(self):
        stale = self._model_box()
        human = {"label": "cat", "points": [[0, 0], [5, 5]], "source": "human"}
        legacy = {"label": "dog", "points": [[1, 1], [2, 2]]}
        current = {
            "label": "pig",
            "points": [[3, 3], [4, 4]],
            "source": "model",
            "model": "run_07",
        }
        path = self._write("a.json", [stale, human, legacy, current])
        counts = self.smart_tools.apply_stale_deletions(
            {path: [self._ref(stale, 0)]}, "run_07"
        )
        self.assertEqual(counts["deleted"], 1)
        self.assertEqual(counts["files"], 1)
        remaining = self._read(path)["shapes"]
        self.assertEqual([shape["label"] for shape in remaining], ["cat", "dog", "pig"])

    def test_locked_box_is_never_deleted(self):
        stale = self._model_box()
        stale["locked"] = True
        path = self._write("b.json", [stale])
        counts = self.smart_tools.apply_stale_deletions(
            {path: [self._ref(stale, 0)]}, "run_07"
        )
        self.assertEqual(counts["deleted"], 0)
        self.assertEqual(counts["skipped_locked"], 1)
        self.assertEqual(len(self._read(path)["shapes"]), 1)

    def test_box_moved_after_the_report_is_skipped(self):
        reported = self._model_box()
        moved = dict(reported, points=[[99, 99], [120, 140]])
        path = self._write("c.json", [moved])
        counts = self.smart_tools.apply_stale_deletions(
            {path: [self._ref(reported, 0)]}, "run_07"
        )
        self.assertEqual(counts["deleted"], 0)
        self.assertEqual(counts["skipped_changed"], 1)
        self.assertEqual(
            self._read(path)["shapes"][0]["points"], [[99, 99], [120, 140]]
        )

    def test_unattributed_and_human_boxes_are_not_deletable(self):
        legacy = {"label": "dog", "points": [[1, 1], [2, 2]]}
        human = {"label": "cat", "points": [[0, 0], [5, 5]], "source": "human"}
        path = self._write("d.json", [legacy, human])
        counts = self.smart_tools.apply_stale_deletions(
            {path: [self._ref(legacy, 0), self._ref(human, 1)]}, "run_07"
        )
        self.assertEqual(counts["deleted"], 0)
        self.assertEqual(counts["skipped_changed"], 2)
        self.assertEqual(len(self._read(path)["shapes"]), 2)

    def test_dirty_open_file_is_left_untouched(self):
        stale = self._model_box()
        path = self._write("e.json", [stale])
        counts = self.smart_tools.apply_stale_deletions(
            {path: [self._ref(stale, 0)]}, "run_07", skip_files={path}
        )
        self.assertEqual(counts["deleted"], 0)
        self.assertEqual(counts["skipped_changed"], 1)
        self.assertEqual(len(self._read(path)["shapes"]), 1)

    def test_other_top_level_fields_survive_the_rewrite(self):
        stale = self._model_box()
        path = self._write(
            "f.json",
            [stale],
            review_state="confirmed",
            checked=True,
            reviewed_at="2026-09-22T10:00:00",
        )
        self.smart_tools.apply_stale_deletions(
            {path: [self._ref(stale, 0)]}, "run_07"
        )
        data = self._read(path)
        self.assertEqual(data["review_state"], "confirmed")
        self.assertIs(data["checked"], True)
        self.assertEqual(data["reviewed_at"], "2026-09-22T10:00:00")
        self.assertEqual(data["shapes"], [])

    def test_missing_or_corrupt_label_file_is_reported_not_raised(self):
        import os

        corrupt = os.path.join(self.tmp.name, "g.json")
        with open(corrupt, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        missing = os.path.join(self.tmp.name, "nope.json")
        ref = {"index": 0, "marker": None}
        counts = self.smart_tools.apply_stale_deletions(
            {corrupt: [ref], missing: [ref]}, "run_07"
        )
        self.assertEqual(counts["deleted"], 0)
        self.assertEqual(counts["skipped_unavailable"], 2)

    def test_empty_input_is_a_no_op(self):
        counts = self.smart_tools.apply_stale_deletions({}, "run_07")
        self.assertEqual(counts["deleted"], 0)
        self.assertEqual(counts["files"], 0)
        self.assertEqual(self.smart_tools.apply_stale_deletions(None, None)["deleted"], 0)


class TestStaleAuditDialog(unittest.TestCase):
    """Runs the whole action, not just its helpers: the menu entry must not
    raise on the branch that counts the current model's own boxes."""

    def setUp(self):
        import os
        import tempfile

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6 import QtWidgets

        from anylabeling.views.labeling.utils import smart_tools

        self.smart_tools = smart_tools
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        self.parent = QtWidgets.QWidget()
        self.tmp = tempfile.TemporaryDirectory()
        self.image = os.path.join(self.tmp.name, "a.png")
        with open(self.image, "wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\n")
        self.label = os.path.join(self.tmp.name, "a.json")

    def tearDown(self):
        self.tmp.cleanup()
        self.parent.deleteLater()

    def _write_label(self, shapes):
        import json

        with open(self.label, "w", encoding="utf-8") as handle:
            json.dump({"shapes": shapes, "checked": False}, handle)

    def _run(self, shapes, current_model="run_07"):
        from unittest import mock

        from PyQt6 import QtWidgets

        self._write_label(shapes)
        self.parent.output_dir = self.tmp.name
        self.parent.filename = self.image
        self.parent.image_list = [self.image]
        self.parent._current_model_identity = lambda: current_model

        captured = []

        def _capture(self_dialog, *_args, **_kwargs):
            captured.append(self_dialog)
            return 0

        with mock.patch.object(
            self.smart_tools._ResultDialog, "exec", _capture
        ):
            self.smart_tools.run_stale_model_audit(self.parent)
        self.assertEqual(len(captured), 1)
        return captured[0]

    def test_lists_other_model_boxes_and_keeps_the_delete_button(self):
        stale = {
            "label": "cat",
            "shape_type": "rectangle",
            "points": [[0, 0], [10, 10]],
            "score": 0.9,
            "source": "model",
            "model": "run_01",
        }
        current = dict(stale, label="pig", model="run_07")
        human = dict(stale, label="dog", source="human")
        legacy = {"label": "ox", "points": [[1, 1], [2, 2]]}
        dialog = self._run([stale, current, human, legacy])

        titles = [
            dialog.tree.topLevelItem(row).text(0)
            for row in range(dialog.tree.topLevelItemCount())
        ]
        self.assertTrue(any("run_01" in title for title in titles), titles)
        rows = dialog.all_rows()
        self.assertEqual(len([row for row in rows if row["shape_ref"]]), 1)
        labels = [
            button.text() for button in dialog.findChildren(
                self.smart_tools.QPushButton
            )
        ]
        self.assertIn("删除所选", labels)

    def test_model_with_all_current_boxes_reports_nothing_deletable(self):
        current = {
            "label": "cat",
            "points": [[0, 0], [10, 10]],
            "source": "model",
            "model": "run_07",
        }
        dialog = self._run([current], current_model="run_07")
        self.assertEqual(
            [row for row in dialog.all_rows() if row["shape_ref"]], []
        )

    def test_locked_boxes_are_not_offered_for_deletion(self):
        stale = {
            "label": "cat",
            "points": [[0, 0], [10, 10]],
            "source": "model",
            "model": "run_01",
            "locked": True,
        }
        dialog = self._run([stale])
        self.assertEqual(
            [row for row in dialog.all_rows() if row["shape_ref"]], []
        )


class TestStaleDeleteBackup(unittest.TestCase):
    """Bulk deletion bypasses undo, so the snapshot is the only way back."""

    def setUp(self):
        import json
        import os
        import tempfile

        from anylabeling.views.labeling.utils import smart_tools

        self.json = json
        self.os = os
        self.smart_tools = smart_tools
        self.tmp = tempfile.TemporaryDirectory()
        self.label = os.path.join(self.tmp.name, "a.json")
        self.stale = {
            "label": "cat",
            "points": [[0, 0], [10, 10]],
            "source": "model",
            "model": "run_01",
        }
        keep = {"label": "dog", "points": [[1, 1], [2, 2]], "source": "human"}
        with open(self.label, "w", encoding="utf-8") as handle:
            json.dump({"shapes": [self.stale, keep], "checked": False}, handle)
        self.ref = {
            "index": 0,
            "marker": smart_tools._shape_marker(self.stale),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def _live_labels(self):
        path = self.os.path.join(self.tmp.name, "a.json")
        with open(path, "r", encoding="utf-8") as handle:
            return [shape["label"] for shape in self.json.load(handle)["shapes"]]

    def _backups(self):
        root = self.os.path.join(self.tmp.name, ".label_backups")
        if not self.os.path.isdir(root):
            return []
        out = []
        for run in sorted(self.os.listdir(root)):
            for name in self.os.listdir(self.os.path.join(root, run)):
                out.append(self.os.path.join(root, run, name))
        return out

    def test_backup_holds_the_pre_delete_content(self):
        counts = self.smart_tools.apply_stale_deletions(
            {self.label: [self.ref]}, "run_07", label_dir=self.tmp.name
        )
        self.assertEqual(counts["deleted"], 1)
        self.assertEqual(self._live_labels(), ["dog"])
        backups = self._backups()
        self.assertEqual(len(backups), 1)
        with open(backups[0], "r", encoding="utf-8") as handle:
            saved = self.json.load(handle)
        self.assertEqual(
            [shape["label"] for shape in saved["shapes"]], ["cat", "dog"]
        )
        self.assertTrue(counts["backup_dir"])

    def test_failed_backup_aborts_the_whole_batch(self):
        from unittest import mock

        with mock.patch.object(
            self.smart_tools.shutil, "copy2", side_effect=OSError("locked")
        ):
            counts = self.smart_tools.apply_stale_deletions(
                {self.label: [self.ref]}, "run_07", label_dir=self.tmp.name
            )
        self.assertTrue(counts["backup_failed"])
        self.assertEqual(counts["deleted"], 0)
        self.assertEqual(self._live_labels(), ["cat", "dog"])
        self.assertEqual(self._backups(), [])

    def test_nothing_to_delete_creates_no_backup(self):
        human_only = {"label": "dog", "points": [[1, 1], [2, 2]], "source": "human"}
        with open(self.label, "w", encoding="utf-8") as handle:
            self.json.dump({"shapes": [human_only], "checked": False}, handle)
        ref = {"index": 0, "marker": self.smart_tools._shape_marker(human_only)}
        counts = self.smart_tools.apply_stale_deletions(
            {self.label: [ref]}, "run_07", label_dir=self.tmp.name
        )
        self.assertEqual(counts["deleted"], 0)
        self.assertFalse(self.os.path.exists(self.os.path.join(self.tmp.name, ".label_backups")))

    def test_retention_prunes_only_our_own_backup_runs(self):
        from unittest import mock

        root = self.os.path.join(self.tmp.name, ".label_backups")
        for name in ("20260101_000000", "20260102_000000", "20260103_000000"):
            self.os.makedirs(self.os.path.join(root, name), exist_ok=True)
        self.os.makedirs(self.os.path.join(root, "notes"), exist_ok=True)

        with mock.patch.object(self.smart_tools, "BACKUP_KEEP_RUNS", 1):
            self.smart_tools.apply_stale_deletions(
                {self.label: [self.ref]}, "run_07", label_dir=self.tmp.name
            )

        runs = sorted(
            name
            for name in self.os.listdir(root)
            if self.os.path.isdir(self.os.path.join(root, name))
        )
        self.assertIn("notes", runs)
        stamped = [name for name in runs if name != "notes"]
        self.assertEqual(len(stamped), 1)
        # What survives must be the run this call just wrote, i.e. the copy of
        # the label file, not one of the synthetic older folders.
        self.assertTrue(
            self.os.path.isfile(
                self.os.path.join(root, stamped[0], "a.json")
            )
        )
