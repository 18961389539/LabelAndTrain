"""A batch auto-label run must leave the pre-run annotations behind.

`运行全部` rewrites the label file of every image it touches, and with
「保留已有标注」 off the model's shapes *replace* whatever a person drew -- across
a whole folder, in one go. The single-image save path has snapshotted into
`.label_backups/` for a while; the batch path was the one that could destroy
hundreds of files with nothing to restore.
"""

import json
import os

import pytest

from anylabeling.services.auto_labeling.types import AutoLabelingResult
from anylabeling.views.labeling.shape import Shape
from anylabeling.views.labeling.utils import batch as batch_module
from anylabeling.views.labeling.utils import session_snapshot


class _Widget:
    """The attributes the batch writers read off the labeling widget."""

    def __init__(self):
        self.output_dir = ""
        self._config = {"store_data": False, "labels": ["scratch"]}
        self.unique_label_list = None
        self.app = None

    def _current_model_identity(self):
        return "run_07"

    def _current_model_version(self):
        return "v1"


def _image(tmp_path, name="part.png"):
    # A real PNG: the first-ever write reads the image size with PIL.
    from PIL import Image

    path = tmp_path / name
    Image.new("RGB", (100, 80), (10, 20, 30)).save(path)
    return str(path)


def _human_label(tmp_path, image_path):
    label_file = os.path.splitext(image_path)[0] + ".json"
    with open(label_file, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "version": "v1",
                "flags": {},
                "shapes": [
                    {
                        "label": "凹坑",
                        "points": [[1.0, 2.0], [3.0, 4.0]],
                        "group_id": None,
                        "shape_type": "rectangle",
                        "flags": {},
                        "source": "human",
                    }
                ],
                "imagePath": os.path.basename(image_path),
                "imageData": None,
                "imageHeight": 80,
                "imageWidth": 100,
                "checked": True,
            },
            handle,
        )
    return label_file


def _model_shape():
    from PyQt6 import QtCore

    shape = Shape("rectangle")
    shape.add_point(QtCore.QPointF(10, 20))
    shape.add_point(QtCore.QPointF(40, 60))
    shape.label = "scratch"
    return shape


def _backups(folder):
    root = os.path.join(folder, ".label_backups")
    if not os.path.isdir(root):
        return []
    return [
        os.path.join(root, run, name)
        for run in sorted(os.listdir(root))
        for name in os.listdir(os.path.join(root, run))
        if name.endswith(".json")
    ]


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(autouse=True)
def _fresh_snapshot_runs():
    session_snapshot.reset_session_snapshots()
    yield
    session_snapshot.reset_session_snapshots()


def test_batch_run_snapshots_the_file_it_is_about_to_replace(tmp_path):
    image_path = _image(tmp_path)
    label_file = _human_label(tmp_path, image_path)

    result = AutoLabelingResult([_model_shape()], replace=True)
    assert batch_module.save_auto_labeling_result(
        _Widget(), image_path, result
    )

    live = _read(label_file)
    assert [shape["label"] for shape in live["shapes"]] == ["scratch"]
    backups = _backups(str(tmp_path))
    assert len(backups) == 1, backups
    saved = _read(backups[0])
    assert [shape["label"] for shape in saved["shapes"]] == ["凹坑"]
    assert saved["checked"] is True


def test_append_mode_snapshots_too(tmp_path):
    """Extending rewrites the file as well, so the old version still goes."""
    image_path = _image(tmp_path)
    label_file = _human_label(tmp_path, image_path)

    result = AutoLabelingResult([_model_shape()], replace=False)
    assert batch_module.save_auto_labeling_result(
        _Widget(), image_path, result
    )

    assert [s["label"] for s in _read(label_file)["shapes"]] == [
        "凹坑",
        "scratch",
    ]
    assert [
        s["label"] for s in _read(_backups(str(tmp_path))[0])["shapes"]
    ] == ["凹坑"]


def test_a_first_ever_write_has_nothing_to_snapshot(tmp_path):
    image_path = _image(tmp_path)
    result = AutoLabelingResult([_model_shape()], replace=True)
    assert batch_module.save_auto_labeling_result(
        _Widget(), image_path, result
    )
    assert _backups(str(tmp_path)) == []


def test_one_batch_run_shares_one_snapshot_run(tmp_path):
    """Per-session, per-folder: the undo point is the batch, not each image."""
    widget = _Widget()
    first = _image(tmp_path, "a.png")
    second = _image(tmp_path, "b.png")
    for path in (first, second):
        _human_label(tmp_path, path)
        batch_module.save_auto_labeling_result(
            widget, path, AutoLabelingResult([_model_shape()], replace=True)
        )

    backups = _backups(str(tmp_path))
    assert sorted(os.path.basename(p) for p in backups) == ["a.json", "b.json"]
    assert len({os.path.dirname(p) for p in backups}) == 1


def test_classification_predictions_snapshot_before_rewriting(tmp_path):
    image_path = _image(tmp_path)
    label_file = _human_label(tmp_path, image_path)

    assert batch_module.save_classification_predictions(
        _Widget(), image_path, [{"label": "scratch", "confidence": 0.9}]
    )

    live = _read(label_file)
    assert [shape["label"] for shape in live["shapes"]] == [
        "凹坑"
    ], "a suggestion is not an annotation: it must not touch shapes"
    assert live["predictions"]["classes"][0]["label"] == "scratch"
    saved = _read(_backups(str(tmp_path))[0])
    assert "predictions" not in saved, "the snapshot is the pre-run file"
