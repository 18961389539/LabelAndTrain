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

Run it before a machine-verification pass (or before a release) to
catch runtime wiring breaks the unit tests cannot see:

    QT_QPA_PLATFORM=offscreen python -u scripts/smoke_widget_paths.py

Exit code is 0 when every step passed. Modal confirmations are stubbed
(a human step, covered by the machine checklist); everything else runs
through the production code. Run with ``-u``: buffered stdout loses the
whole report if the process dies.
"""

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
    widget = build_widget(config_copy)

    @step("1. folder import (file_lifecycle rewires)")
    def s1():
        widget.import_image_folder(tmp)
        app.processEvents()
        assert len(widget.image_list) == 3, widget.image_list
        assert (
            widget.file_list_widget.count() == 3
        ), widget.file_list_widget.count()

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

    @step("2b. switch away and back -- view state restored")
    def s2b():
        widget.load_file(images[1])
        app.processEvents()
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

    s1()
    s2a()
    s2b()
    s3()
    s4a()
    s4b()
    s5()
    s6()

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
