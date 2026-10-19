"""The range editors must leave the pre-edit file behind, not just call.

`tests/test_utils/test_label_writer_invariant.py` proves these methods contain
a call to the snapshot helper. That is not the same as proving the snapshot
holds the shapes that are about to disappear -- an argument typo passes a
static scan. These tests read the file back out of ``.label_backups/``.
"""

import json
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


def _box(label, group_id=None, points=None):
    return {
        "label": label,
        "points": points if points is not None else [[0, 0], [4, 4]],
        "group_id": group_id,
        "shape_type": "rectangle",
        "flags": {},
    }


def _make_folder(shapes_by_stem):
    from PIL import Image

    holder = tempfile.TemporaryDirectory()
    # Nested: delete_images_in_range writes its _delete_ sibling next to the
    # image folder, so the images must not sit at the temp root itself.
    tmp = os.path.join(holder.name, "images")
    os.makedirs(tmp)
    for stem, shapes in shapes_by_stem.items():
        Image.new("RGB", (20, 20), "gray").save(
            os.path.join(tmp, stem + ".png")
        )
        with open(
            os.path.join(tmp, stem + ".json"), "w", encoding="utf-8"
        ) as handle:
            json.dump(
                {
                    "version": "2.4.0",
                    "flags": {},
                    "shapes": shapes,
                    "imagePath": stem + ".png",
                    "imageData": None,
                    "imageHeight": 20,
                    "imageWidth": 20,
                    "checked": True,
                },
                handle,
            )
    return tmp, holder


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestRangeEditorSnapshots(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        from anylabeling.views.labeling.label_widget import LabelingWidget

        patcher = mock.patch.object(
            LabelingWidget, "load_file", lambda self, *a, **k: False
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _widget_with(self, shapes_by_stem):
        from tests.test_labeling.test_widget_wiring import (
            build_labeling_widget,
        )

        self.folder, holder = _make_folder(shapes_by_stem)
        self.addCleanup(holder.cleanup)
        self.widget, widget_holder = build_labeling_widget(self.folder)
        self.addCleanup(self.widget.deleteLater)
        self.addCleanup(widget_holder.deleteLater)
        self.widget.file_list_widget.setCurrentRow(0)

    def _read(self, stem):
        path = os.path.join(self.folder, stem + ".json")
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)

    def _snapshot(self, stem):
        root = os.path.join(self.folder, ".label_backups")
        name = stem + ".json"
        for run in sorted(os.listdir(root)):
            candidate = os.path.join(root, run, name)
            if os.path.isfile(candidate):
                with open(candidate, encoding="utf-8") as handle:
                    return json.load(handle)
        self.fail(f"no snapshot of {name} under {root}")

    def test_modify_group_id_snapshots_before_dropping_a_group(self):
        from anylabeling.views.labeling.widgets.label_dialog import (
            GroupIDModifyDialog,
        )

        self._widget_with(
            {
                "a": [_box("cat", group_id=1), _box("dog", group_id=2)],
            }
        )
        dialog = GroupIDModifyDialog(parent=self.widget)
        self.addCleanup(dialog.deleteLater)

        self.assertTrue(
            dialog.modify_group_id({}, [2], start_index=1, end_index=1)
        )

        live = self._read("a")
        self.assertEqual([s["label"] for s in live["shapes"]], ["cat"])
        saved = self._snapshot("a")
        self.assertEqual(
            [s["label"] for s in saved["shapes"]],
            ["cat", "dog"],
            "the snapshot must hold the group that was about to be dropped",
        )

    def test_modify_group_id_keeps_the_shape_order(self):
        """Renumbering a group must not shuffle the shapes it touched.

        The order the user drew them in is the order the label list shows, so
        rewriting the file with the shapes reversed is a silent change to
        every frame in the range.
        """
        from anylabeling.views.labeling.widgets.label_dialog import (
            GroupIDModifyDialog,
        )

        self._widget_with(
            {
                "a": [
                    _box("cat", group_id=1),
                    _box("dog", group_id=2),
                    _box("panda"),
                ]
            }
        )
        dialog = GroupIDModifyDialog(parent=self.widget)
        self.addCleanup(dialog.deleteLater)

        self.assertTrue(
            dialog.modify_group_id(
                {1: {"new_gid": 9}}, [], start_index=1, end_index=1
            )
        )

        live = self._read("a")
        self.assertEqual(
            [s["label"] for s in live["shapes"]], ["cat", "dog", "panda"]
        )
        self.assertEqual(
            [s.get("group_id") for s in live["shapes"]], [9, 2, None]
        )
        self.assertEqual(
            [s["label"] for s in self._snapshot("a")["shapes"]],
            ["cat", "dog", "panda"],
        )

    def test_add_to_range_snapshots_the_file_it_extends(self):
        from anylabeling.views.labeling.shape import Shape
        from anylabeling.views.labeling.widgets.shape_dialog import (
            ShapeModifyDialog,
        )

        self._widget_with({"a": [_box("cat")], "b": [_box("cat")]})
        dialog = ShapeModifyDialog(parent=self.widget)
        self.addCleanup(dialog.deleteLater)

        from PyQt6.QtCore import QPointF

        template = Shape("rectangle")
        template.add_point(QPointF(1, 1))
        template.add_point(QPointF(3, 3))
        template.label = "scratch"
        self.widget.canvas.selected_shapes = [template]

        dialog.add_selected_shapes_to_range(1, 1)

        live = self._read("a")
        self.assertEqual(
            [s["label"] for s in live["shapes"]], ["cat", "scratch"]
        )
        saved = self._snapshot("a")
        self.assertEqual(
            [s["label"] for s in saved["shapes"]],
            ["cat"],
            "the file before the append has to be recoverable",
        )

    def test_remove_from_range_snapshots_the_shapes_it_takes_away(self):
        from anylabeling.views.labeling.shape import Shape
        from anylabeling.views.labeling.widgets.shape_dialog import (
            ShapeModifyDialog,
        )

        dog = _box("dog", points=[[1, 1], [3, 3]])
        self._widget_with({"a": [_box("cat"), dog]})
        dialog = ShapeModifyDialog(parent=self.widget)
        self.addCleanup(dialog.deleteLater)

        selected = Shape().load_from_dict(dog, close=False)
        self.widget.canvas.selected_shapes = [selected]

        dialog.remove_selected_shapes_in_range(1, 1)

        live = self._read("a")
        self.assertEqual([s["label"] for s in live["shapes"]], ["cat"])
        saved = self._snapshot("a")
        self.assertEqual([s["label"] for s in saved["shapes"]], ["cat", "dog"])

    def test_delete_images_in_range_keeps_the_removed_label_recoverable(self):
        """The image is moved to _delete_, but its JSON is destroyed.

        The move message promises the picture can be found again; that is only
        true for the annotation if it survives in .label_backups/ too.
        """
        from anylabeling.views.labeling.label_widget import LabelingWidget
        from anylabeling.views.labeling.utils import missing_classes_hint
        from anylabeling.views.labeling.widgets.shape_dialog import (
            ShapeModifyDialog,
        )

        self._widget_with({"a": [_box("cat")], "b": [_box("dog")]})
        dialog = ShapeModifyDialog(parent=self.widget)
        self.addCleanup(dialog.deleteLater)

        # The refresh after a delete reports through the main window's status
        # bar; the headless harness has no such grandparent.
        status_patcher = mock.patch.object(
            LabelingWidget, "statusBar", lambda self: mock.Mock()
        )
        status_patcher.start()
        self.addCleanup(status_patcher.stop)

        # import_image_folder re-runs the open-folder path, and the hint's
        # retry would outlive this widget.
        with mock.patch.object(
            missing_classes_hint, "_schedule", lambda *a, **k: None
        ):
            dialog.delete_images_in_range(2, 2)

        self.assertFalse(os.path.exists(os.path.join(self.folder, "b.json")))
        self.assertFalse(os.path.exists(os.path.join(self.folder, "b.png")))
        moved = os.path.join(os.path.dirname(self.folder), "_delete_", "b.png")
        self.assertTrue(os.path.exists(moved), "the image is moved, not lost")
        self.assertEqual(
            [s["label"] for s in self._read("a")["shapes"]], ["cat"]
        )
        saved = self._snapshot("b")
        self.assertEqual(
            [s["label"] for s in saved["shapes"]],
            ["dog"],
            "the removed annotation has to be readable back out of the backup",
        )


if __name__ == "__main__":
    unittest.main()
