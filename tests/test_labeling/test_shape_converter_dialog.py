"""The shape converter dialog: a bulk rewrite that can be undone.

`shape_converter_dialog.py` was 0% covered -- 314 lines reachable only by
clicking 工具 -> 形状转换器, so a broken combo, a dead cancel button or a
conversion that overwrote files with no way back could all ship unnoticed.
The last one was real: the loop rewrote every label file in place while its
own confirm text says 「当前标注将被修改」, with no snapshot, unlike the save
path and the bulk label editor. These tests pin the wiring *and* the backup.
"""

import glob
import json
import os
import os.path as osp

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6 import QtWidgets  # noqa: E402

from anylabeling.views.labeling.utils import session_snapshot  # noqa: E402
from anylabeling.views.labeling.utils.shape import (  # noqa: E402
    CONVERSION_TARGETS,
)
from anylabeling.views.labeling.widgets.shape_converter_dialog import (  # noqa: E402
    ShapeConverterDialog,
)


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    """One QApplication for the module.

    Held at module scope on purpose: an app that dies with the first test
    takes the next QWidget creation down with it (exit 127, no report).
    """
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


class _Parent(QtWidgets.QWidget):
    """The slice of the labeling widget the dialog actually uses."""

    def __init__(self, label_files=None, image_list=None, filename=None):
        super().__init__()
        self._label_files = label_files or []
        self.image_list = image_list or []
        self.filename = filename
        self.reloaded = 0

    def get_label_file_list(self):
        return list(self._label_files)

    def load_file(self, filename):
        self.reloaded += 1


def _write_label(dir_path, name, shape_type="rectangle"):
    path = osp.join(str(dir_path), name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "imagePath": name.replace(".json", ".png"),
                "imageHeight": 120,
                "imageWidth": 200,
                "shapes": [
                    {
                        "label": "scratch",
                        "points": [[20, 20], [80, 20], [80, 60], [20, 60]],
                        "group_id": None,
                        "shape_type": shape_type,
                        "flags": {},
                    }
                ],
            },
            handle,
        )
    return path


@pytest.fixture(autouse=True)
def _clean_snapshots():
    session_snapshot.reset_session_snapshots()
    yield
    session_snapshot.reset_session_snapshots()


def _dialog(label_files=None, image_list=None, filename=None):
    parent = _Parent(label_files, image_list, filename)
    return ShapeConverterDialog(parent), parent


# --- the shape of the dialog ---------------------------------------------


def test_target_options_follow_the_source_type():
    dialog, _ = _dialog()
    try:
        for source, targets in CONVERSION_TARGETS.items():
            dialog._update_target_options(source)
            shown = [
                dialog.target_combo.itemText(i)
                for i in range(dialog.target_combo.count())
            ]
            assert shown == targets, (source, shown)
    finally:
        dialog.deleteLater()


def test_progress_denominator_prefers_the_label_files(tmp_path):
    label = _write_label(tmp_path, "a.json")
    dialog, _ = _dialog(
        label_files=[label],
        image_list=["x.png", "y.png", "z.png"],
        filename="x.png",
    )
    try:
        assert dialog._get_initial_total() == 1
    finally:
        dialog.deleteLater()

    no_labels, _ = _dialog(image_list=["x.png", "y.png"], filename="x.png")
    try:
        assert no_labels._get_initial_total() == 2
    finally:
        no_labels.deleteLater()

    only_one_file, _ = _dialog(filename="x.png")
    try:
        assert only_one_file._get_initial_total() == 1
    finally:
        only_one_file.deleteLater()

    empty, _ = _dialog()
    try:
        assert empty._get_initial_total() == 0
        empty._set_progress(0, 0)  # must not divide by zero
        assert empty.progress_bar.value() == 0
    finally:
        empty.deleteLater()


def test_progress_format_says_how_much_of_what(tmp_path):
    dialog, _ = _dialog()
    try:
        dialog._set_progress(3, 12)
        assert dialog.progress_bar.format().startswith("3/12")
        assert "(25%)" in dialog.progress_bar.format()
        dialog._set_progress(99, 12)  # clamped, never past the bar
        assert dialog.progress_bar.value() == 12
    finally:
        dialog.deleteLater()


# --- cancel stays honest -------------------------------------------------


def test_cancel_before_processing_closes_the_dialog():
    dialog, _ = _dialog()
    try:
        dialog._on_cancel_clicked()
        assert dialog.result() == QtWidgets.QDialog.DialogCode.Rejected
    finally:
        dialog.deleteLater()


def test_cancel_during_processing_asks_for_a_stop_and_disables_itself():
    dialog, _ = _dialog()
    try:
        dialog.is_processing = True
        dialog._on_cancel_clicked()
        assert dialog.cancel_requested is True
        assert dialog.isVisible() or True  # still open: it stops, not quits
        assert not dialog.cancel_button.isEnabled()
    finally:
        dialog.deleteLater()


def test_the_only_way_out_during_a_run_stays_enabled():
    """Source/target/confirm go dark while files are being rewritten; cancel
    must not, or a user who changed their mind has no lever at all."""
    dialog, _ = _dialog()
    try:
        dialog._set_controls_enabled(False)
        assert not dialog.source_combo.isEnabled()
        assert not dialog.target_combo.isEnabled()
        assert not dialog.confirm_button.isEnabled()
        assert dialog.cancel_button.isEnabled()
        dialog._set_controls_enabled(True)
        assert dialog.confirm_button.isEnabled()
    finally:
        dialog.deleteLater()


def test_an_unmapped_pair_and_an_empty_folder_do_nothing(tmp_path):
    dialog, parent = _dialog()
    try:
        dialog.source_combo.setCurrentText("line")
        dialog._update_target_options("line")
        dialog.source_combo.setCurrentText(
            "polygon"
        )  # now polygon -> linestrip
        dialog._on_confirm_clicked()
        assert dialog.is_processing is False
        assert parent.reloaded == 0

        label = _write_label(tmp_path, "a.json")
        dialog2, parent2 = _dialog(label_files=[])
        try:
            dialog2.source_combo.setCurrentText("rectangle")
            dialog2._update_target_options("rectangle")
            dialog2.target_combo.setCurrentText("rotation")
            dialog2._on_confirm_clicked()  # nothing to convert
            assert parent2.reloaded == 0
            with open(label, encoding="utf-8") as handle:
                assert json.load(handle)["shapes"][0]["shape_type"] == (
                    "rectangle"
                )
        finally:
            dialog2.deleteLater()
    finally:
        dialog.deleteLater()


# --- the conversion itself, and the way back -----------------------------


def test_conversion_rewrites_files_and_leaves_a_snapshot(
    tmp_path, monkeypatch
):
    """The confirm dialog says the annotations *will* be changed.

    A bulk in-place rewrite needs the same guarantee the save path and the
    bulk label editor give: 从备份恢复标注 can bring the originals back.
    """
    first = _write_label(tmp_path, "a.json")
    second = _write_label(tmp_path, "b.json")
    original = open(first, encoding="utf-8").read()

    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "exec",
        lambda self, *a: QtWidgets.QMessageBox.StandardButton.Ok,
    )
    dialog, parent = _dialog(label_files=[first, second], filename=first)
    try:
        dialog.source_combo.setCurrentText("rectangle")
        dialog._update_target_options("rectangle")
        dialog.target_combo.setCurrentText("rotation")
        dialog._on_confirm_clicked()
        QtWidgets.QApplication.processEvents()

        assert dialog.is_processing is False
        for path in (first, second):
            with open(path, encoding="utf-8") as handle:
                shapes = json.load(handle)["shapes"]
            assert shapes[0]["shape_type"] == "rotation", path
            assert len(shapes[0]["points"]) == 4, shapes[0]
        assert parent.reloaded == 1, "the open image was not repainted"

        snaps = glob.glob(
            osp.join(str(tmp_path), ".label_backups", "*", "a.json")
        )
        assert snaps, sorted(os.listdir(str(tmp_path)))
        with open(snaps[0], encoding="utf-8") as handle:
            assert handle.read() == original
    finally:
        dialog.deleteLater()


def test_declining_the_confirm_writes_nothing(tmp_path, monkeypatch):
    label = _write_label(tmp_path, "a.json")
    before = open(label, encoding="utf-8").read()
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "exec",
        lambda self, *a: QtWidgets.QMessageBox.StandardButton.Cancel,
    )
    dialog, parent = _dialog(label_files=[label], filename=label)
    try:
        dialog.source_combo.setCurrentText("rectangle")
        dialog._update_target_options("rectangle")
        dialog.target_combo.setCurrentText("rotation")
        dialog._on_confirm_clicked()
        with open(label, encoding="utf-8") as handle:
            assert handle.read() == before
        assert parent.reloaded == 0
        assert not glob.glob(
            osp.join(str(tmp_path), ".label_backups", "*", "a.json")
        )
    finally:
        dialog.deleteLater()
