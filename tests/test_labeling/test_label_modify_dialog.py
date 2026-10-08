"""The label-change manager must not be a one-click data loss.

"Go" rewrites every label file in range and there is no undo for the batch.
The old default range was the whole folder, so a single stray click could
strip a label from thousands of files. These tests pin the three guards that
replaced that: the range defaults to the image on screen, the write is
preceded by an impact count the user has to approve, and each file is
snapshotted before it is overwritten.
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

SNAPSHOT_TARGET = (
    "anylabeling.views.labeling.utils.session_snapshot."
    "snapshot_before_label_write"
)


def _make_folder():
    """Two images; a.json has cat+dog, b.json has cat."""
    from PIL import Image

    holder = tempfile.TemporaryDirectory()
    tmp = holder.name
    for name in ("a.png", "b.png"):
        Image.new("RGB", (20, 20), "gray").save(os.path.join(tmp, name))
    for stem, labels in (("a", ["cat", "dog"]), ("b", ["cat"])):
        with open(
            os.path.join(tmp, stem + ".json"), "w", encoding="utf-8"
        ) as handle:
            json.dump(
                {
                    "shapes": [
                        {"label": label, "points": [[0, 0], [1, 1]]}
                        for label in labels
                    ],
                    "review_state": "unchecked",
                },
                handle,
            )
    return tmp, holder


def _build_widget(folder):
    from tests.test_labeling.test_widget_wiring import build_labeling_widget

    return build_labeling_widget(folder)


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestLabelModifyDialogSafety(unittest.TestCase):
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
        self.folder, holder = _make_folder()
        self.addCleanup(holder.cleanup)
        self.widget, widget_holder = _build_widget(self.folder)
        self.addCleanup(self.widget.deleteLater)
        self.addCleanup(widget_holder.deleteLater)
        self.widget.file_list_widget.setCurrentRow(1)

        from anylabeling.views.labeling.widgets.label_dialog import (
            LabelModifyDialog,
        )

        self.dialog = LabelModifyDialog(parent=self.widget, opacity=128)
        self.addCleanup(self.dialog.deleteLater)

    def test_range_defaults_to_the_open_image(self):
        self.assertEqual(self.widget.file_list_widget.currentRow(), 1)
        self.assertEqual(self.dialog.start_index, 2)
        self.assertEqual(self.dialog.end_index, 2)
        self.assertEqual(self.dialog.from_input.value(), 2)
        self.assertEqual(self.dialog.to_input.value(), 2)

    def _row_for(self, label):
        table = self.dialog.table_widget
        for row in range(table.rowCount()):
            if table.item(row, 0).text() == label:
                return row
        self.fail(f"no row for {label}")

    def _set_delete(self, label):
        row = self._row_for(label)
        self.dialog.table_widget.cellWidget(row, 1).setChecked(True)

    def _set_value(self, label, value):
        row = self._row_for(label)
        self.dialog._get_value_edit(row).setText(value)

    def test_impact_counts_read_the_table_not_stale_label_info(self):
        self._set_delete("dog")
        self._set_value("cat", "feline")
        files, deleted, renamed = self.dialog._impact_counts(1, 1)
        self.assertEqual(files, 1)
        self.assertEqual(deleted, 1)
        self.assertEqual(renamed, 1)

    def test_impact_counts_stay_within_the_selected_range(self):
        self._set_delete("cat")
        files, deleted, _renamed = self.dialog._impact_counts(2, 2)
        self.assertEqual(files, 1)
        self.assertEqual(deleted, 1)

    def test_declining_the_confirmation_cancels_the_write(self):
        with mock.patch.object(
            QtWidgets.QMessageBox,
            "warning",
            return_value=QtWidgets.QMessageBox.StandardButton.No,
        ):
            self.assertFalse(self.dialog._confirm_scope(1, 2))

    def test_accepting_the_confirmation_proceeds(self):
        with mock.patch.object(
            QtWidgets.QMessageBox,
            "warning",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ):
            self.assertTrue(self.dialog._confirm_scope(1, 2))

    def test_update_range_stops_when_the_confirmation_is_declined(self):
        self._set_delete("dog")
        with (
            mock.patch.object(
                QtWidgets.QMessageBox,
                "warning",
                return_value=QtWidgets.QMessageBox.StandardButton.No,
            ),
            mock.patch.object(self.dialog, "confirm_changes") as confirm,
        ):
            self.dialog.from_input.setValue(1)
            self.dialog.to_input.setValue(2)
            self.dialog.update_range()
        confirm.assert_not_called()

    def test_modify_label_snapshots_each_file_before_overwriting_it(self):
        # ``modify_label`` reads ``label_info``, which is only synced from
        # the table by ``confirm_changes``; set it the way that step would.
        self.dialog.parent.label_info["dog"]["delete"] = True
        with mock.patch(SNAPSHOT_TARGET) as snapshot:
            self.assertTrue(self.dialog.modify_label(1, 1))
        snapshot.assert_called_once()
        target = snapshot.call_args.args[0]
        self.assertEqual(os.path.basename(target), "a.json")

        with open(
            os.path.join(self.folder, "a.json"), encoding="utf-8"
        ) as handle:
            data = json.load(handle)
        self.assertEqual([s["label"] for s in data["shapes"]], ["cat"])


if __name__ == "__main__":
    unittest.main()
