"""The OBB boundary choice is a real export option, not a dead parameter.

``custom_to_yolo`` had ``obb_boundary_policy`` from the start, but no caller
passed it, so only "skip" was reachable. These tests walk the path the user
takes: the checkbox only appears in an OBB export, the remembered choice comes
back pre-checked, and accepting the dialog changes what lands in the ``.txt``.
"""

import json
import os
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
import pytest
from PyQt6 import QtWidgets

from anylabeling.views.labeling import project_model
from anylabeling.views.labeling.label_converter import LabelConverter
from anylabeling.views.labeling.utils import export

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

CLAMP_LABEL = "越界旋转框裁剪到图像内"


def _source(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    Image.new("RGB", (100, 50), "gray").save(images / "img.png")
    (images / "img.json").write_text(
        json.dumps(
            {
                "version": "2.4.0",
                "flags": {},
                "shapes": [
                    {
                        "label": "plane",
                        "points": [[-10, 10], [20, 10], [20, 20], [10, -5]],
                        "group_id": None,
                        "shape_type": "rotation",
                        "flags": {},
                    }
                ],
                "imagePath": "img.png",
                "imageData": None,
                "imageHeight": 50,
                "imageWidth": 100,
            }
        ),
        encoding="utf-8",
    )
    return images


def _widget(images, project=None):
    widget = QtWidgets.QWidget()
    widget.filename = str(images / "img.png")
    widget.image_list = [str(images / "img.png")]
    widget.output_dir = str(images)
    widget.dirty = False
    if project is not None:
        widget._project_dataset_dir = str(project)
    return widget


def _patches(capture=None, accept=False):
    def fake_exec(dialog):
        boxes = {
            box.text(): box.isChecked()
            for box in dialog.findChildren(QtWidgets.QCheckBox)
        }
        if capture is not None:
            capture.setdefault("dialogs", []).append(boxes)
        return int(accept)

    return (
        mock.patch.object(export, "_check_filename_exist", lambda _: True),
        mock.patch.object(
            export,
            "resolve_classes_for_yolo",
            lambda w, m: (
                ["plane"],
                "test",
                LabelConverter(classes=["plane"]),
            ),
        ),
        # The real one asks a message box when the directory exists; that
        # policy has its own tests, and here the answer is "merge".
        mock.patch.object(
            export, "resolve_existing_output_dir", lambda *a, **k: "merge"
        ),
        mock.patch.object(QtWidgets.QDialog, "exec", fake_exec),
    )


def test_the_clamp_option_only_exists_for_obb_exports(tmp_path):
    images = _source(tmp_path)
    seen = {}
    checker, resolver, output_dir, dialog_exec = _patches(capture=seen)

    with checker, resolver, output_dir, dialog_exec:
        export.export_yolo_annotation(_widget(images), "hbb")
        assert all(
            CLAMP_LABEL not in boxes for boxes in seen["dialogs"]
        ), "a plain hbb export has nothing to do with OBB bounds"

        seen["dialogs"].clear()
        export.export_yolo_annotation(_widget(images), "obb")
        option_dialogs = [
            boxes for boxes in seen["dialogs"] if CLAMP_LABEL in boxes
        ]
        assert option_dialogs, "the OBB export must offer the boundary policy"
        assert option_dialogs[0][CLAMP_LABEL] is False


def test_the_remembered_clamp_choice_reaches_the_exported_file(tmp_path):
    images = _source(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    assert project_model.create(str(project), task="Detect", labels=["plane"])
    assert project_model.remember_export(
        str(project), {"save_path": str(out), "obb_boundary": "clamp"}
    )

    seen = {}
    checker, resolver, output_dir, dialog_exec = _patches(
        capture=seen, accept=True
    )
    with checker, resolver, output_dir, dialog_exec:
        export.export_yolo_annotation(_widget(images, project), "obb")

    option_dialogs = [
        boxes for boxes in seen["dialogs"] if CLAMP_LABEL in boxes
    ]
    assert option_dialogs and option_dialogs[0][CLAMP_LABEL] is True
    text = (out / "img.txt").read_text(encoding="utf-8")
    assert text == "0 0.0 0.2 0.2 0.2 0.2 0.4 0.1 0.0\n"
