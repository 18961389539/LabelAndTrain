"""Integration smoke: walk the split batches' paths on a real widget.

Unit tests cover the pieces; this runs the real ``LabelingWidget``
offscreen against a real image folder and walks the seams between
them -- the paths that only exist when everything is wired together:

  1. folder import          -> file_lifecycle (batch 17 rewires)
  2. load_file round trip   -> ViewStateStore (batch 19)
  3. thumbnail panel        -> ThumbnailPanel (batch 18)
  4. review state + quality -> filelist items / getattr path (17)
  5. canvas rectangle edits -> canvas_geometry (14-16)
  6. delete_image_file      -> file_lifecycle (batch 9)
  7. YOLO export            -> export_check / manifest (batch 23)
  8. project identity       -> registry / name / title bar (project L1+L2)
  9. project resume         -> last_file round trip (project L3)
 10. close project          -> back to an empty canvas (project L1)
 11. project task           -> training window, both ways (project L4)
 12. auto label -> provenance -> review -> YOLO export (the loop's own seam)
 13. union selection      -> shape_union (refuses loss, merges one region)
 14. uploaded class list  -> config copy + project record
 15. imported image flags -> config copy + real flag dock

Run it before a machine-verification pass (or before a release) to
catch runtime wiring breaks the unit tests cannot see:

    QT_QPA_PLATFORM=offscreen python -u scripts/smoke_widget_paths.py

Exit code is 0 when every step passed. Modal confirmations are stubbed
(a human step, covered by the machine checklist); everything else runs
through the production code. Step 7 replaces only the two clicks the
export dialog asks a human for -- the dialog itself is built for real,
so its checkbox wiring is what runs. Run with ``-u``: buffered stdout
loses the whole report if the process dies.
"""

import json
import os
import shutil
import sys
import tempfile
import traceback

import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from PyQt6 import QtCore, QtGui, QtWidgets  # noqa: E402

TEMPLATE_CONFIG = os.path.join(
    REPO, "anylabeling", "configs", "jllabeling_config.yaml"
)

RESULTS = []


def step(name):
    def deco(fn):
        def run(*a, **kw):
            try:
                fn(*a, **kw)
                RESULTS.append((name, "OK", ""))
                print(f"[OK]   {name}", flush=True)
            except Exception as exc:  # noqa: BLE001
                RESULTS.append((name, "FAIL", repr(exc)))
                print(f"[FAIL] {name}: {exc!r}", flush=True)
                traceback.print_exc()

        return run

    return deco


def make_images(tmp):
    """Three real PNGs, one with a label file already."""
    paths = []
    for i in range(3):
        img = QtGui.QImage(200, 120, QtGui.QImage.Format.Format_RGB32)
        img.fill(QtGui.QColor(30 + i * 40, 60, 90))
        path = os.path.join(tmp, f"img_{i}.png")
        img.save(path)
        paths.append(path)
    label = QtCore.QJsonDocument(
        {
            "version": "2.4.0",
            "flags": {},
            "shapes": [
                {
                    "label": "box",
                    "points": [[10, 10], [80, 60]],
                    "group_id": None,
                    "shape_type": "rectangle",
                    "flags": {},
                }
            ],
            "imagePath": "img_0.png",
            "imageData": None,
            "imageHeight": 120,
            "imageWidth": 200,
        }
    )
    with open(os.path.join(tmp, "img_0.json"), "w", encoding="utf-8") as fh:
        fh.write(
            label.toJson(QtCore.QJsonDocument.JsonFormat.Indented)
            .data()
            .decode()
        )
    return paths


def build_widget(config_path, filename=None):
    from anylabeling import config as app_config
    from anylabeling.views.labeling.label_widget import LabelingWidget

    app_config.current_config_file = config_path
    LabelingWidget.menu = lambda self, title: QtWidgets.QMenu(title)
    parent = QtWidgets.QFrame()
    widget = LabelingWidget(parent, filename=filename)
    widget.parent = type("P", (), {"parent": QtWidgets.QMainWindow()})()
    return widget


def stub_export_dialogs(export_mod, classes, converter, out_dir, messages):
    """Replace the two clicks a human supplies, and nothing else.

    The export dialog itself is built for real, so the checkbox wiring that
    decides whether a manifest is written is the production one. Returns a
    callable that puts the module back the way it was.
    """

    def fake_resolve(_widget, _mode):
        return list(classes), "smoke", converter

    def auto_accept(dialog):
        for edit in dialog.findChildren(QtWidgets.QLineEdit):
            edit.setText(out_dir)
        return 1

    class _Popup:
        def __init__(self, message, *a, **kw):
            messages.append(message)

        def show_popup(self, *a, **kw):
            pass

    original = {
        "resolve": export_mod.resolve_classes_for_yolo,
        "exec": QtWidgets.QDialog.exec,
        "popup": export_mod.Popup,
    }
    export_mod.resolve_classes_for_yolo = fake_resolve
    QtWidgets.QDialog.exec = auto_accept
    export_mod.Popup = _Popup

    def restore():
        export_mod.resolve_classes_for_yolo = original["resolve"]
        QtWidgets.QDialog.exec = original["exec"]
        export_mod.Popup = original["popup"]

    return restore


def check_export_output(out_dir, classes, messages):
    """The summary named the record, and the record matches the run."""
    assert messages, "the export told the user nothing"
    summary = messages[-1]
    assert "export_manifest.json" in summary, summary

    with open(
        os.path.join(out_dir, "export_manifest.json"), encoding="utf-8"
    ) as fh:
        manifest = json.load(fh)
    assert manifest["classes"]["names"] == classes, manifest["classes"]
    assert manifest["mode"] == "hbb", manifest["mode"]
    assert manifest["result"]["images_exported"] == 3, manifest["result"]
    assert manifest["source_data"]["no_label_file"] == 2, manifest[
        "source_data"
    ]
    assert manifest["source_data"]["labels_not_in_classes"] == {}

    # The class list and the label file are what make the manifest checkable
    # rather than decorative.
    for name in ("classes.txt", "data.yaml", "img_0.txt"):
        assert os.path.exists(os.path.join(out_dir, name)), os.listdir(out_dir)
    with open(os.path.join(out_dir, "img_0.txt"), encoding="utf-8") as fh:
        first = fh.readline().split()
    assert first and first[0] == "0", first


def run_yolo_export(widget, app, tmp):
    from anylabeling.views.labeling.label_converter import LabelConverter
    from anylabeling.views.labeling.utils import export as export_mod

    # A folder of its own: two images without a label file are the point (they
    # exercise the "no label file" count without blocking), and the default
    # export path is derived from the folder, so keep it inside the temp tree
    # rather than at its parent.
    source_dir = os.path.join(tmp, "export_src")
    out_dir = os.path.join(tmp, "export_out")
    os.makedirs(source_dir)
    make_images(source_dir)
    widget.import_image_folder(source_dir)
    app.processEvents()

    classes = ["box"]
    messages = []
    restore = stub_export_dialogs(
        export_mod, classes, LabelConverter(classes=classes), out_dir, messages
    )
    try:
        export_mod.export_yolo_annotation(widget, "hbb")
    finally:
        restore()
    app.processEvents()

    check_export_output(out_dir, classes, messages)


def answer_modals(titles):
    """Answer every message box this step raises, and record that it did.

    Production code blocks on ``exec()``, and offscreen there is no hand to
    click: a step that reaches a modal silently hangs, which reads exactly
    like a crash in the report. The dialogs themselves are behavior the
    machine checklist covers; here only the click is supplied -- and the
    titles are collected so an unexpected one is at least named in the log.
    """
    original = QtWidgets.QMessageBox.exec

    def auto_exec(self):
        titles.append(self.windowTitle())
        print(f"       弹窗（自动应答）：{self.windowTitle()}", flush=True)
        return QtWidgets.QMessageBox.StandardButton.No

    QtWidgets.QMessageBox.exec = auto_exec

    def restore():
        QtWidgets.QMessageBox.exec = original

    return restore


def run_auto_label_seam(widget, app, tmp):
    """auto label -> provenance written to disk -> review -> YOLO export.

    Only the inference is faked: a real ``AutoLabelingResult`` goes through
    the real ``new_shapes_from_auto_labeling``, the real save writes the real
    label file, and the real export path turns that file into a YOLO row. This
    is the chain the loop is sold on -- "one click less labeling" -- and until
    now no gate walked any of it in one piece: unit tests covered the model
    panel's plumbing, and step 7 exported shapes a human had drawn.
    """
    from PyQt6 import QtCore

    from anylabeling.services.auto_labeling.types import AutoLabelingResult
    from anylabeling.views.labeling import provenance
    from anylabeling.views.labeling.label_converter import LabelConverter
    from anylabeling.views.labeling.shape import Shape
    from anylabeling.views.labeling.utils import export as export_mod

    source_dir = os.path.join(tmp, "loop_src")
    out_dir = os.path.join(tmp, "loop_out")
    os.makedirs(source_dir)
    images = make_images(source_dir)  # img_0 has a label file, img_1 does not
    clean = images[1]

    modals = []
    restore_modals = answer_modals(modals)
    weights = os.path.join(tmp, "smoke-yolov8.onnx")
    with open(weights, "wb") as handle:
        handle.write(b"smoke-weights-for-the-digest")
    manager = widget.auto_labeling_widget.model_manager
    original_config = getattr(manager, "loaded_model_config", None)
    manager.loaded_model_config = {
        "name": "smoke-yolov8",
        "model_path": weights,
    }

    shape = Shape()
    shape.label = "box"
    shape.shape_type = "rectangle"
    shape.points = [
        QtCore.QPointF(10, 10),
        QtCore.QPointF(80, 10),
        QtCore.QPointF(80, 60),
        QtCore.QPointF(10, 60),
    ]
    try:
        widget.import_image_folder(source_dir)
        app.processEvents()
        widget.load_file(clean)
        app.processEvents()
        assert not widget.canvas.shapes, "the clean image arrived pre-labeled"

        widget.new_shapes_from_auto_labeling(
            AutoLabelingResult(
                shapes=[shape], replace=True, image_path=widget.filename
            )
        )
        app.processEvents()
        produced = widget.canvas.shapes
        assert len(produced) == 1, [s.label for s in produced]
        assert produced[0].source == provenance.SOURCE_MODEL, produced[
            0
        ].source
        assert produced[0].model == "smoke-yolov8", produced[0].model

        # The write the annotator gets is the debounced auto-save, not Ctrl+S:
        # on an image that never had a label file, save_file() falls through to
        # a "Choose File" dialog, which is why this step flushes the pending
        # auto-save the way the 400 ms timer would.
        if widget._auto_save_pending:
            widget._flush_auto_save()
        else:
            assert widget.save_labels(
                os.path.splitext(clean)[0] + ".json"
            ), "auto-save off and the explicit write failed"
        app.processEvents()
        label_path = os.path.splitext(clean)[0] + ".json"
        with open(label_path, encoding="utf-8") as handle:
            stored = json.load(handle)["shapes"][0]
        assert (
            stored[provenance.SOURCE_FIELD] == provenance.SOURCE_MODEL
        ), stored
        assert stored[provenance.MODEL_FIELD] == "smoke-yolov8", stored
        # The digest is what answers "which weights made this box" after a
        # retrain lands on the same path -- the name alone cannot.
        assert stored.get(provenance.MODEL_VERSION_FIELD), stored

        # The row's UserRole is its checked flag, not its path (see step 4a),
        # so the row is found through the widget's own filename index.
        from anylabeling.views.labeling.filelist.roles import FILE_REVIEW_ROLE
        from anylabeling.views.labeling.schema import REVIEW_CONFIRMED

        index = widget.fn_to_index[clean]
        item = widget.file_list_widget.item(index)
        widget._set_file_item_checked(item, True)
        app.processEvents()
        assert (
            item.data(QtCore.Qt.ItemDataRole.UserRole) is True
        ), "the auto-labeled file did not take the confirmed state"
        assert item.data(FILE_REVIEW_ROLE) == REVIEW_CONFIRMED, item.data(
            FILE_REVIEW_ROLE
        )

        classes = ["box"]
        messages = []
        restore = stub_export_dialogs(
            export_mod,
            classes,
            LabelConverter(classes=classes),
            out_dir,
            messages,
        )
        try:
            export_mod.export_yolo_annotation(widget, "hbb")
        finally:
            restore()
        app.processEvents()

        with open(
            os.path.join(out_dir, "img_1.txt"), encoding="utf-8"
        ) as handle:
            row = handle.read().split()
        assert row and row[0] == "0" and len(row) == 5, row
        with open(
            os.path.join(out_dir, "export_manifest.json"), encoding="utf-8"
        ) as handle:
            manifest = json.load(handle)
        assert manifest["result"]["shapes_exported"] == 2, manifest["result"]

        # Offscreen the widget is never shown, so the 还没有类别 hint defers
        # itself rather than raising -- and no other dialog may block this step.
        # The hint's own rules are guarded by acceptance step 14 on a real
        # window; here the stub exists so a surprise modal is named, not fatal.
        assert modals.count("还没有类别") <= 1, modals
        for title in modals:
            if title != "还没有类别":
                raise AssertionError(
                    f"unexpected dialog in this step: {title}"
                )
    finally:
        restore_modals()
        manager.loaded_model_config = original_config


def run_project_identity(widget, app, tmp):
    """Step 8: opening a folder makes it the project, name and all."""
    from anylabeling.views.labeling import project_model, project_registry
    from anylabeling.views.labeling.utils import project_view

    # A folder nothing has written to yet, so the fallback is the thing
    # under test: the name has to come from the folder itself.
    fresh = os.path.join(tmp, "fresh")
    os.makedirs(fresh, exist_ok=True)
    make_images(fresh)
    widget.import_image_folder(fresh)
    app.processEvents()

    root = project_view.current_root(widget)
    assert root == os.path.normpath(fresh), root
    assert project_model.has_record(root) is False, "wrote a record"
    assert project_view.project_name(root) == "fresh"

    recorded = [
        os.path.normcase(entry["root"])
        for entry in project_registry.recent_projects()
    ]
    assert os.path.normcase(fresh) in recorded, recorded

    widget.update_progress_title()
    title = widget.parent.parent.windowTitle()
    assert "fresh" in title, title


def run_project_resume(widget, app, tmp, target):
    """Step 9: leave a project on a frame, come back to that frame."""
    from anylabeling.views.labeling import project_settings

    widget.import_image_folder(tmp)
    app.processEvents()
    widget.load_file(target)
    app.processEvents()

    # Leaving writes the position into *this* dataset's own record...
    other = os.path.join(tmp, "another")
    os.makedirs(other, exist_ok=True)
    make_images(other)
    widget.import_image_folder(other)
    app.processEvents()
    remembered = project_settings.remembered_file(tmp)
    assert remembered == target, remembered

    # ...and coming back opens it instead of the first image.
    widget.import_image_folder(tmp)
    app.processEvents()
    assert widget.filename == target, widget.filename


def run_close_project(widget, app, tmp):
    """Step 10: closing a project leaves a genuinely empty canvas."""
    from anylabeling.views.labeling.utils import project_view

    widget.import_image_folder(tmp)
    app.processEvents()
    assert project_view.current_root(widget) is not None

    assert project_view.close_project(widget) is True
    app.processEvents()

    assert project_view.current_root(widget) is None
    assert widget.file_list_widget.count() == 0
    assert widget.filename is None
    assert os.path.basename(tmp) not in widget.parent.parent.windowTitle()


def run_project_task(widget, app, tmp):
    """Step 11: the task kind, project -> dialog -> project."""
    from anylabeling.views.labeling import project_model
    from anylabeling.views.training import ultralytics_dialog as dialog_mod
    from anylabeling.views.training.ultralytics_dialog import (
        UltralyticsDialog,
    )

    if project_model.has_record(tmp):
        record = project_model.load_record(tmp)
        record["task"] = "Segment"
        project_model.save_record(tmp, record)
    else:
        project_model.create(tmp, name="smoke project", task="Segment")
    assert project_model.describe(tmp)["task"] == "Segment"

    widget.import_image_folder(tmp)
    app.processEvents()
    # Importing must not disturb what the record already says.
    assert project_model.describe(tmp)["task"] == "Segment"

    originals = {
        name: getattr(dialog_mod, name)
        for name in (
            "get_trainer_root_dir",
            "load_config",
            "get_config",
            "DEVICE_OPTIONS",
        )
    }
    dialog_mod.get_trainer_root_dir = lambda: os.path.join(tmp, "trainer")
    dialog_mod.load_config = lambda: {}
    dialog_mod.get_config = lambda: {"training": {}}
    dialog_mod.DEVICE_OPTIONS = ["cpu"]
    dialog = None
    try:
        dialog = UltralyticsDialog(widget)
        # The dialog is handed an image list whose first entry can sit in a
        # sub-folder (the scan recurses), so this assertion also pins "the
        # project context wins over image_list[0]".
        assert dialog.selected_task_type == "Segment", (
            dialog.selected_task_type,
            list(widget.image_list),
            project_model.describe(tmp),
        )
        # And the other direction: committing writes the kind back.
        dialog.on_task_type_selected("Detect")
        dialog._save_project_train_prefs({"basic": {}})
        assert project_model.describe(tmp)["task"] == "Detect"
    finally:
        for name, original in originals.items():
            setattr(dialog_mod, name, original)
        if dialog is not None:
            dialog.deleteLater()
        app.processEvents()


@step("15. imported image flags persist and stay on the canvas")
def run_image_flags(widget, tmp, config_path):
    """The real dialog-free tail: config write, flag dock, dirty state."""
    from unittest import mock

    from anylabeling.views.labeling.utils import upload as upload_module

    flags_path = os.path.join(tmp, "flags.txt")
    with open(flags_path, "w", encoding="utf-8") as handle:
        handle.write("occluded\n\n lost \noccluded\n")

    with (
        mock.patch.object(
            upload_module.QtWidgets.QFileDialog,
            "getOpenFileName",
            return_value=(flags_path, ""),
        ),
        mock.patch.object(upload_module, "Popup"),
    ):
        upload_module.upload_image_flags_file(widget)

    assert widget.image_flags == ["occluded", "lost"]
    assert widget.flag_widget.count() == 2
    assert [
        widget.flag_widget.item(index).text()
        for index in range(widget.flag_widget.count())
    ] == ["occluded", "lost"]
    with open(config_path, encoding="utf-8") as handle:
        saved = yaml.safe_load(handle)
    assert saved["flags"] == ["occluded", "lost"], saved.get("flags")
    assert widget.dirty, "imported flags must reach the save path"


@step("14. uploaded class list persists to config and project record")
def run_uploaded_classes(widget, folder, config_path):
    """The real save path, not a stubbed one: config file + project record."""
    from anylabeling.views.labeling import project_model
    from anylabeling.views.labeling.utils import upload

    widget.import_image_folder(folder)
    upload.apply_uploaded_labels(widget, ["smoke_a", "smoke_b"])

    assert widget._config["labels"] == ["smoke_a", "smoke_b"]
    with open(config_path, encoding="utf-8") as handle:
        saved = yaml.safe_load(handle)
    assert saved["labels"] == ["smoke_a", "smoke_b"], saved.get("labels")
    assert project_model.describe(folder)["labels"] == [
        "smoke_a",
        "smoke_b",
    ]


@step("13. union selection -- disjoint refused, connected merged")
def run_union_selection(widget, image_path):
    """A disjoint merge is refused; a connected one replaces both shapes."""
    from anylabeling.views.labeling.shape import Shape

    widget.load_file(image_path)

    def polygon(points):
        shape = Shape(label="merge", shape_type="polygon")
        shape.points = [QtCore.QPointF(x, y) for x, y in points]
        shape.close()
        return shape

    def reset(shapes):
        widget.label_list.clear()
        widget.canvas.selected_shapes = []
        widget.canvas.shapes = []
        widget.load_shapes(shapes)
        widget.shape_selection_changed(shapes)

    left = polygon([(10, 10), (60, 10), (60, 60), (10, 60)])
    far = polygon([(100, 10), (160, 10), (160, 60), (100, 60)])
    reset([left, far])
    assert widget.actions.union_selection.isEnabled()
    widget.union_selection()
    assert (
        len(widget.canvas.shapes) == 2
    ), "a disjoint union must leave every shape in place"
    assert len(widget.label_list) == 2

    a = polygon([(10, 10), (60, 10), (60, 60), (10, 60)])
    b = polygon([(40, 40), (100, 40), (100, 100), (40, 100)])
    reset([a, b])
    widget.union_selection()
    assert (
        len(widget.canvas.shapes) == 1
    ), "a connected union must replace both shapes with one"
    assert len(widget.label_list) == 1
    merged = widget.canvas.shapes[0]
    assert merged.label == "merge" and merged.shape_type == "polygon"
    xs = [p.x() for p in merged.points]
    ys = [p.y() for p in merged.points]
    for actual, expected in zip(
        (min(xs), min(ys), max(xs), max(ys)), (10, 10, 100, 100)
    ):
        assert abs(actual - expected) < 2, (actual, expected)

    # The merge is one edit: a single Ctrl+Z must bring both originals back
    # rather than resurrect one and then empty the image.
    widget.undo_shape_edit()
    app = QtWidgets.QApplication.instance()
    app.processEvents()
    assert (
        len(widget.canvas.shapes) == 2
    ), "one undo must restore both merged shapes"
    assert len(widget.label_list) == 2


def _stop_background_scanners(widget, app):
    """Stop the workers that can hold the temp folder open at exit.

    The low-confidence pass reads label files after the visible steps have
    finished; a QThread still running while the interpreter shuts down is
    how this harness exited 127 on the Windows CI runner.
    """
    for attribute, stop_name in (
        ("async_exif_scanner", "stop_scan"),
        ("async_label_checker", "stop"),
    ):
        scanner = getattr(widget, attribute, None)
        if scanner is None:
            continue
        try:
            getattr(scanner, stop_name)()
        except (RuntimeError, AttributeError):
            pass
    app.processEvents()


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tmp = tempfile.mkdtemp(prefix="smoke_widget_paths_")
    images = make_images(tmp)
    # NEVER point the app at the factory template: the widget writes back
    # (digit-shortcut auto-assign, recent dirs) and this script once
    # polluted anylabeling/configs/jllabeling_config.yaml that way.
    # Work on a copy inside the temp dir.
    config_copy = os.path.join(tmp, "smoke_config.yaml")
    shutil.copy(TEMPLATE_CONFIG, config_copy)
    # Same reasoning one level up: the project registry lives in
    # ``<work directory>/.jllabel/projects.json``, so without this every
    # run recorded its throwaway folders in the *real* recent-project
    # list. Found in the wild: a registry holding nine smoke paths, the
    # oldest from 2026-09-29 -- the leak predates the project batches.
    from anylabeling.config import set_work_directory

    set_work_directory(tmp)
    widget = build_widget(config_copy)

    @step("1. folder import (file_lifecycle rewires)")
    def s1():
        # A project that declares its labels must answer to 1-9 straight
        # away, not only once the first box has been drawn by hand.
        widget._config["labels"] = ["scratch", "dent"]
        widget.import_image_folder(tmp)
        app.processEvents()
        assert len(widget.image_list) == 3, widget.image_list
        assert (
            widget.file_list_widget.count() == 3
        ), widget.file_list_widget.count()
        assert (
            widget.drawing_digit_shortcuts.get(1, {}).get("label") == "scratch"
        ), widget.drawing_digit_shortcuts
        assert (
            widget.drawing_digit_shortcuts.get(2, {}).get("label") == "dent"
        ), widget.drawing_digit_shortcuts

    @step("2a. load first image + set view state")
    def s2a():
        widget.load_file(images[0])
        app.processEvents()
        assert widget.filename == images[0]
        assert len(widget.canvas.shapes) == 1, "label file not loaded"
        widget.set_zoom(150)
        widget.set_scroll(QtCore.Qt.Orientation.Horizontal, 42)
        widget._on_inline_brightness_contrast(
            65, 35
        )  # int slider values -> 1.30x / 0.70x
        assert widget.view_state.zoom[images[0]] == (widget.MANUAL_ZOOM, 150)

    @step("2b. switch away and back -- view state and undo history survive")
    def s2b():
        # Undo needs two states before it means anything: canvas stores the
        # state AFTER each edit, and a fresh load pushes exactly one.
        widget.canvas.store_shapes()
        assert (
            widget.canvas.is_shape_restorable
        ), "undo not armed before switch"
        widget.load_file(images[1])
        app.processEvents()
        assert (
            not widget.canvas.is_shape_restorable
        ), "another image's history leaked in"
        widget.load_file(images[0])
        app.processEvents()
        assert widget.zoom_widget.value() == 150, widget.zoom_widget.value()
        assert (
            widget.view_state.scroll[QtCore.Qt.Orientation.Horizontal][
                images[0]
            ]
            == 42
        )
        assert widget.view_state.brightness_contrast[images[0]] == (65, 35)
        # The stacks come back, and the menu entry that reaches them is live
        # again -- a restorable stack behind a disabled action is no undo.
        assert (
            widget.canvas.is_shape_restorable
        ), "undo history was dropped on the file switch"
        assert widget.actions.undo.isEnabled(), "Ctrl+Z stayed disabled"

    @step("3. thumbnail panel show / reset")
    def s3():
        pix = QtGui.QPixmap(80, 50)
        pix.fill(QtGui.QColor(200, 100, 50))
        widget.thumbnail_panel.set_pixmap(pix)
        assert not widget.thumbnail_panel.isHidden(), "panel did not show"
        widget.update_thumbnail_display()  # no model loaded -> reset path
        assert widget.thumbnail_panel.isHidden(), "panel did not reset"
        assert widget.thumbnail_panel.pixmap() is None

    @step("4a. review state via filelist items")
    def s4a():
        item = widget.file_list_widget.item(0)
        widget._set_file_item_checked(item, True)
        app.processEvents()
        # review state lives in the UserRole + FILE_REVIEW_ROLE, not checkState
        assert item.data(QtCore.Qt.ItemDataRole.UserRole) is True
        from anylabeling.views.labeling.schema import REVIEW_CONFIRMED
        from anylabeling.views.labeling.filelist.roles import FILE_REVIEW_ROLE

        assert item.data(FILE_REVIEW_ROLE) == REVIEW_CONFIRMED

    @step("4b. quality note path (getattr keep-alive stub)")
    def s4b():
        note = getattr(widget, "_note_save_quality", None)
        assert note is not None, "stub vanished"
        note(widget.canvas.shapes, widget.file_list_widget.item(0))

    @step("5. canvas rectangle wheel edits (canvas_geometry)")
    def s5():
        widget.load_file(images[0])
        shape = widget.canvas.shapes[0]
        before = shape.bounding_rect()
        widget.canvas._scale_rectangle(shape, scale_up=True)
        after = shape.bounding_rect()
        assert after.width() >= before.width(), (before, after)
        widget.canvas._adjust_rectangle_edge(
            shape,
            QtCore.QPointF(after.center().x(), after.center().y() - 200),
            move_outward=True,
        )
        rect = shape.bounding_rect()
        assert (
            rect.top() >= 0 and rect.bottom() < widget.canvas.pixmap.height()
        )

    @step("6. delete current image -> _delete_ folder, label snapshotted")
    def s6():
        # the modal confirm is a human step (machine checklist); stub it
        widget._confirm_destructive_action = lambda *a, **k: True
        # The image lands in _delete_ "so you can get it back", so the
        # annotation must not simply vanish. The version key matters: a label
        # JSON without it takes load_file's error path, which is a modal --
        # correct for a user, fatal for an offscreen run.
        doomed_label = os.path.splitext(images[2])[0] + ".json"
        with open(doomed_label, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "version": "2.4.0",
                    "flags": {},
                    "shapes": [
                        {
                            "label": "scratch",
                            "points": [[0, 0], [1, 1]],
                            "group_id": None,
                            "shape_type": "rectangle",
                            "flags": {},
                        }
                    ],
                    "imagePath": os.path.basename(images[2]),
                    "imageData": None,
                    "imageHeight": 160,
                    "imageWidth": 5328,
                    "checked": True,
                },
                handle,
            )
        widget.load_file(images[2])
        app.processEvents()
        widget.delete_image_file()
        app.processEvents()
        # NOTE: delete_image_file moves the image into "<image_dir>/../_delete_",
        # one level ABOVE the image folder (upstream behaviour, kept as-is)
        deleted_dir = os.path.join(os.path.dirname(tmp), "_delete_")
        assert os.path.isdir(deleted_dir), f"no _delete_ at {deleted_dir}"
        moved = [f for f in os.listdir(deleted_dir) if f.startswith("img_2")]
        assert moved, "image not moved into _delete_"
        assert not os.path.exists(images[2]), "image still in place"
        assert not os.path.exists(doomed_label), "label still in place"
        # The deletion is not the end of the annotation: the pre-delete
        # content sits in the session snapshot that 从备份恢复标注 reads.
        runs = os.path.join(tmp, ".label_backups")
        snapshots = (
            [
                os.path.join(runs, run, "img_2.json")
                for run in sorted(os.listdir(runs))
                if os.path.isfile(os.path.join(runs, run, "img_2.json"))
            ]
            if os.path.isdir(runs)
            else []
        )
        assert snapshots, f"no snapshot of {doomed_label} under {runs}"
        with open(snapshots[0], "r", encoding="utf-8") as handle:
            saved = json.load(handle)
        assert [s["label"] for s in saved["shapes"]] == ["scratch"], saved
        for name in moved:  # clean up after ourselves
            os.remove(os.path.join(deleted_dir, name))
        os.rmdir(deleted_dir)
        shutil.rmtree(runs, ignore_errors=True)

    @step("7. YOLO export -- readiness check, manifest, summary")
    def s7():
        run_yolo_export(widget, app, tmp)

    @step("8. project identity -- registry entry, name, title bar")
    def s8():
        run_project_identity(widget, app, tmp)

    @step("9. project resume -- left on this frame, came back to it")
    def s9():
        run_project_resume(widget, app, tmp, images[1])

    @step("10. close project -- empty canvas, plain title")
    def s10():
        run_close_project(widget, app, tmp)

    @step("11. project task reaches the training window, and comes back")
    def s11():
        run_project_task(widget, app, tmp)

    @step("12. auto label -> provenance -> review -> YOLO export, one seam")
    def s12():
        run_auto_label_seam(widget, app, tmp)

    s1()
    s2a()
    s2b()
    s3()
    s4a()
    s4b()
    s5()
    s6()
    s7()
    s8()
    s9()
    s10()
    s11()
    s12()
    run_union_selection(widget, images[0])
    run_uploaded_classes(widget, tmp, config_copy)
    run_image_flags(widget, tmp, config_copy)

    print("")
    print("=== smoke summary ===", flush=True)
    failures = [r for r in RESULTS if r[1] == "FAIL"]
    for name, status, info in RESULTS:
        line = f"{status:4s} {name}"
        if info:
            line += f"  -- {info}"
        print(line, flush=True)
    print(f"{len(RESULTS) - len(failures)}/{len(RESULTS)} passed", flush=True)
    _stop_background_scanners(widget, app)
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
