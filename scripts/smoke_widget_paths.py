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

    @step("6. delete current image -> _delete_ folder")
    def s6():
        # the modal confirm is a human step (machine checklist); stub it
        widget._confirm_destructive_action = lambda *a, **k: True
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
        for name in moved:  # clean up after ourselves
            os.remove(os.path.join(deleted_dir, name))
        os.rmdir(deleted_dir)

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

    print("")
    print("=== smoke summary ===", flush=True)
    failures = [r for r in RESULTS if r[1] == "FAIL"]
    for name, status, info in RESULTS:
        line = f"{status:4s} {name}"
        if info:
            line += f"  -- {info}"
        print(line, flush=True)
    print(f"{len(RESULTS) - len(failures)}/{len(RESULTS)} passed", flush=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
