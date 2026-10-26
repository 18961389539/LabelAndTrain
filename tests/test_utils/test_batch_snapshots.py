"""A batch auto-label run must leave the pre-run annotations behind.

`运行全部` rewrites the label file of every image it touches, and with
「保留已有标注」 off the model's shapes *replace* whatever a person drew -- across
a whole folder, in one go. The single-image save path has snapshotted into
`.label_backups/` for a while; the batch path was the one that could destroy
hundreds of files with nothing to restore.
"""

import json
import os
from unittest import mock

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


def test_class_rename_snapshots_every_file_it_rewrites(tmp_path):
    from anylabeling.views.labeling.utils import yolo_detect

    label_dir = tmp_path / "labels"
    label_dir.mkdir()
    (label_dir / "classes.txt").write_text("凹坑\n", encoding="utf-8")
    image = _image(tmp_path, "part.png")
    target = label_dir / "part.json"
    target.write_text(
        json.dumps(
            {
                "shapes": [
                    {
                        "label": "凹坑",
                        "points": [[1.0, 2.0], [3.0, 4.0]],
                        "shape_type": "rectangle",
                        "flags": {},
                    }
                ],
                "imageWidth": 100,
                "imageHeight": 80,
            }
        ),
        encoding="utf-8",
    )

    changed = yolo_detect.rename_label_across_folder(
        [image], str(label_dir), "凹坑", "dented"
    )
    assert changed >= 1
    assert [s["label"] for s in _read(str(target))["shapes"]] == ["dented"]
    backups = _backups(str(label_dir))
    assert len(backups) == 1, backups
    assert [s["label"] for s in _read(backups[0])["shapes"]] == [
        "凹坑"
    ], "a rename across a folder is one undo point, not one per file"


def test_template_prelabels_snapshot_their_target(tmp_path):
    from anylabeling.views.labeling.utils import smart_prelabel

    image = _image(tmp_path)
    label_file = _human_label(tmp_path, image)
    item = {
        "label_file": label_file,
        "target": image,
        "shapes": [
            {
                "label": "scratch",
                "points": [[10.0, 20.0], [40.0, 60.0]],
                "shape_type": "rectangle",
                "flags": {},
                "source": "model",
            }
        ],
    }

    written, failed = smart_prelabel._write_prelabels(None, [item])
    assert (written, failed) == (1, 0)
    assert [s["label"] for s in _read(label_file)["shapes"]] == [
        "凹坑",
        "scratch",
    ]
    saved = _read(_backups(str(tmp_path))[0])
    assert [s["label"] for s in saved["shapes"]] == ["凹坑"]


def test_template_prelabels_count_a_failed_write(tmp_path):
    from anylabeling.views.labeling.utils import smart_prelabel

    image = _image(tmp_path)
    label_file = _human_label(tmp_path, image)
    item = {
        "label_file": label_file,
        "target": image,
        "shapes": [
            {
                "label": "scratch",
                "points": [[10.0, 20.0], [40.0, 60.0]],
                "shape_type": "rectangle",
                "flags": {},
                "source": "model",
            }
        ],
    }

    with mock.patch.object(
        smart_prelabel,
        "save_json",
        side_effect=OSError("disk full"),
    ):
        result = smart_prelabel._write_prelabels(None, [item])

    assert result == (0, 1)
    assert [s["label"] for s in _read(label_file)["shapes"]] == ["凹坑"]


class _Parent:
    """What ``label_dir_for`` reads: an open file, no separate output dir."""

    def __init__(self, image_path):
        self.output_dir = None
        self.filename = image_path

    def _current_model_identity(self):
        return "run_07"

    def _current_model_version(self):
        return "v1"


def test_missing_scan_write_snapshots_its_file(tmp_path):
    from anylabeling.views.labeling.utils import smart_missing

    image = _image(tmp_path)
    label_file = _human_label(tmp_path, image)
    payload = {
        "label": "scratch",
        "points": [[5.0, 5.0], [9.0, 9.0]],
        "shape_type": "rectangle",
        "flags": {},
        "source": "model",
    }

    written, failed = smart_missing._write_missing(
        _Parent(image), [(image, [payload])]
    )

    assert (written, failed) == (1, 0)
    assert [s["label"] for s in _read(label_file)["shapes"]] == [
        "凹坑",
        "scratch",
    ]
    saved = _read(_backups(str(tmp_path))[0])
    assert [s["label"] for s in saved["shapes"]] == ["凹坑"]


def test_missing_scan_counts_a_failed_write(tmp_path):
    from anylabeling.views.labeling.utils import smart_missing

    image = _image(tmp_path)
    label_file = _human_label(tmp_path, image)
    payload = {
        "label": "scratch",
        "points": [[5.0, 5.0], [9.0, 9.0]],
        "shape_type": "rectangle",
        "flags": {},
        "source": "model",
    }

    with mock.patch.object(
        smart_missing,
        "save_json",
        side_effect=OSError("disk full"),
    ):
        result = smart_missing._write_missing(
            _Parent(image), [(image, [payload])]
        )

    assert result == (0, 1)
    assert [s["label"] for s in _read(label_file)["shapes"]] == ["凹坑"]
