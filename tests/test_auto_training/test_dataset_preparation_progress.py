"""Dataset preparation must report determinate progress and stop on cancel."""

import json
import os

import pytest

from jllabeling.services.auto_training.ultralytics import general
from jllabeling.services.auto_training.ultralytics.general import (
    DatasetPreparationCancelled,
    create_yolo_dataset,
)


def _classification_tree(tmp_path, count):
    images = []
    for index in range(count):
        image = tmp_path / f"img{index}.jpg"
        image.write_bytes(b"not-a-real-jpeg")
        label = tmp_path / f"img{index}.json"
        label.write_text(
            json.dumps(
                {
                    "version": "2.4.0",
                    "flags": {"cat": True},
                    "shapes": [],
                    "imagePath": image.name,
                    "imageData": None,
                }
            ),
            encoding="utf-8",
        )
        images.append(str(image))
    return images


@pytest.fixture
def dataset_root(tmp_path, monkeypatch):
    root = tmp_path / "datasets"
    monkeypatch.setattr(general, "get_dataset_path", lambda: str(root))
    return root


def test_build_reports_scanning_and_copying_progress(tmp_path, dataset_root):
    images = _classification_tree(tmp_path, 3)
    progress = []
    report = {}

    created = create_yolo_dataset(
        images,
        "Classify",
        1.0,
        "",
        str(tmp_path),
        report=report,
        progress_callback=lambda stage, done, total: progress.append(
            (stage, done, total)
        ),
    )

    assert os.path.isdir(created)
    scanning = [entry for entry in progress if entry[0] == "scanning"]
    copying = [entry for entry in progress if entry[0] == "copying"]
    assert scanning[0] == ("scanning", 0, 3)
    assert scanning[-1] == ("scanning", 3, 3)
    assert copying[0] == ("copying", 0, 3)
    assert copying[-1] == ("copying", 3, 3)
    assert [done for _stage, done, _total in copying] == sorted(
        done for _stage, done, _total in copying
    )


def test_cancel_during_copy_stops_and_removes_the_partial_dataset(
    tmp_path, dataset_root
):
    images = _classification_tree(tmp_path, 3)
    state = {"cancel": False}
    report = {}

    def progress(stage, done, _total):
        if stage == "copying" and done >= 1:
            state["cancel"] = True

    with pytest.raises(DatasetPreparationCancelled):
        create_yolo_dataset(
            images,
            "Classify",
            1.0,
            "",
            str(tmp_path),
            report=report,
            progress_callback=progress,
            cancel_check=lambda: state["cancel"],
        )

    assert report.get("dataset_dir")
    assert not os.path.exists(report["dataset_dir"])


def test_cancel_during_scan_never_creates_a_dataset(tmp_path, dataset_root):
    images = _classification_tree(tmp_path, 4)
    report = {}

    with pytest.raises(DatasetPreparationCancelled):
        create_yolo_dataset(
            images,
            "Classify",
            1.0,
            "",
            str(tmp_path),
            report=report,
            cancel_check=lambda: True,
        )

    assert report.get("dataset_dir")
    assert not os.path.exists(report["dataset_dir"])
