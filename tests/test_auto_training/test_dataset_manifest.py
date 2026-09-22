import json
import os

import cv2
import numpy as np
import pytest
import yaml

from anylabeling.services.auto_training.ultralytics import general
from anylabeling.services.auto_training.ultralytics.general import (
    create_yolo_dataset,
    load_dataset_manifest,
)

CLASSES = ["cat", "dog"]


def _make_dataset(tmp_path, count=8, checked=True):
    images = []
    for i in range(count):
        name = f"img_{i:03d}"
        image_path = tmp_path / f"{name}.jpg"
        canvas = np.zeros((30, 20, 3), dtype=np.uint8)
        canvas[i % 30, i % 20] = (255, 255, 255)
        cv2.imwrite(str(image_path), canvas)
        label = {
            "version": "1",
            "flags": {},
            "checked": checked,
            "shapes": [
                {
                    "label": CLASSES[i % 2],
                    "points": [[2, 3], [12, 20]],
                    "group_id": None,
                    "description": "",
                    "shape_type": "rectangle",
                    "flags": {},
                    "attributes": {},
                    "kie_linking": [],
                }
            ],
            "imagePath": f"{name}.jpg",
            "imageData": None,
            "imageHeight": 30,
            "imageWidth": 20,
        }
        (tmp_path / f"{name}.json").write_text(
            json.dumps(label), encoding="utf-8"
        )
        images.append(str(image_path))
    return images


def _data_file(tmp_path):
    path = tmp_path / "classes.yaml"
    path.write_text(
        yaml.safe_dump({"names": {0: "cat", 1: "dog"}, "nc": 2}),
        encoding="utf-8",
    )
    return str(path)


@pytest.fixture
def dataset_root(tmp_path, monkeypatch):
    root = tmp_path / "trainer_datasets"
    root.mkdir()
    monkeypatch.setattr(general, "get_dataset_path", lambda: str(root))
    return root


def _build(tmp_path, dataset_root, seed=None, count=8):
    images = _make_dataset(tmp_path, count=count)
    out = create_yolo_dataset(
        images,
        "Detect",
        0.5,
        _data_file(tmp_path),
        None,
        None,
        False,
        False,
        seed=seed,
    )
    return out, images


def _manifest(out):
    with open(os.path.join(out, "manifest.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def _split_map(manifest):
    return {entry["image"]: entry["split"] for entry in manifest["files"]}


def test_manifest_records_the_exact_annotations(dataset_root, tmp_path):
    out, images = _build(tmp_path, dataset_root, seed=42)
    manifest = _manifest(out)

    assert manifest["seed"] == 42
    assert manifest["task"] == "Detect"
    assert manifest["classes"] == CLASSES
    assert manifest["counts"]["train"] == 4
    assert manifest["counts"]["val"] == 4
    assert len(manifest["files"]) == len(images)
    # Every label that fed the run is hashed, so a later edit is detectable.
    for entry in manifest["files"]:
        assert entry["sha1"]
        assert entry["label"].endswith(".json")
    assert manifest["data_yaml_sha1"]
    assert os.path.isfile(manifest["data_yaml"])


def test_same_seed_reproduces_the_split(dataset_root, tmp_path):
    first, _ = _build(tmp_path, dataset_root, seed=7)
    second, _ = _build(tmp_path, dataset_root, seed=7)
    assert _split_map(_manifest(first)) == _split_map(_manifest(second))


def test_different_seed_changes_the_split(dataset_root, tmp_path):
    first, _ = _build(tmp_path, dataset_root, seed=1, count=20)
    second, _ = _build(tmp_path, dataset_root, seed=2, count=20)
    assert _split_map(_manifest(first)) != _split_map(_manifest(second))


def test_seed_is_recorded_when_the_caller_does_not_pick_one(
    dataset_root, tmp_path
):
    out, _ = _build(tmp_path, dataset_root, seed=None)
    manifest = _manifest(out)
    assert isinstance(manifest["seed"], int)
    assert manifest["seed"] > 0


def test_hash_reveals_annotations_edited_after_the_run(dataset_root, tmp_path):
    out, images = _build(tmp_path, dataset_root, seed=3)
    manifest = _manifest(out)
    entry = manifest["files"][0]
    recorded = entry["sha1"]

    label_path = entry["label"]
    data = json.loads(open(label_path, "r", encoding="utf-8").read())
    data["shapes"].append(dict(data["shapes"][0], label="extra"))
    with open(label_path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    assert general.file_sha1(label_path) != recorded


def test_manifest_loader_accepts_dir_or_yaml(dataset_root, tmp_path):
    out, _ = _build(tmp_path, dataset_root, seed=11)
    assert load_dataset_manifest(out)["seed"] == 11
    assert (
        load_dataset_manifest(os.path.join(out, "data.yaml"))["seed"] == 11
    )


def test_two_builds_in_the_same_second_do_not_overwrite(
    dataset_root, tmp_path
):
    # Directory names only carry second precision, so without a uniqueness
    # suffix the second build would reuse the first one's directory and replace
    # its manifest -- silently breaking reproducibility.
    first, _ = _build(tmp_path, dataset_root, seed=1, count=6)
    second, _ = _build(tmp_path, dataset_root, seed=2, count=6)
    assert first != second
    assert _manifest(first)["seed"] == 1
    assert _manifest(second)["seed"] == 2
    assert _split_map(_manifest(first)) != _split_map(_manifest(second))


def test_manifest_loader_returns_none_for_legacy_datasets(tmp_path):
    legacy = tmp_path / "old_dataset"
    legacy.mkdir()
    assert load_dataset_manifest(str(legacy)) is None
    assert load_dataset_manifest(str(legacy / "data.yaml")) is None
    assert load_dataset_manifest("") is None


def test_manifest_loader_survives_a_corrupt_file(tmp_path):
    (tmp_path / "manifest.json").write_text("{oops", encoding="utf-8")
    assert load_dataset_manifest(str(tmp_path)) is None


def _make_run(root, name, mtime, size=1024):
    path = root / name
    path.mkdir(parents=True)
    (path / "images_train.jpg").write_bytes(b"\0" * size)
    os.utime(path, (mtime, mtime))
    return str(path)


def test_prune_keeps_the_newest_and_protects_the_current_run(tmp_path):
    root = tmp_path / "detect"
    newest = _make_run(root, "classes_20260922_120000", 300)
    middle = _make_run(root, "classes_20260921_120000", 200)
    oldest = _make_run(root, "classes_20260920_120000", 100)

    planned = general.plan_dataset_prune(
        general.collect_dataset_runs(str(root)), 2, None
    )
    assert planned == [oldest]

    # `keep` counts the builds kept *besides* the current run, so with keep=1
    # the newest is protected as current and one more survives as history.
    planned = general.plan_dataset_prune(
        general.collect_dataset_runs(str(root)), 1, newest
    )
    assert newest not in planned
    assert middle not in planned
    assert planned == [oldest]


def test_prune_ignores_unrelated_directories(tmp_path):
    root = tmp_path / "detect"
    run = _make_run(root, "classes_20260920_120000", 100)
    other = root / "handmade_export"
    other.mkdir()
    assert general.collect_dataset_runs(str(root)) == [run]
    assert general.collect_dataset_runs(str(root / "missing")) == []


def test_prune_reports_undeletable_directories(tmp_path, monkeypatch):
    root = tmp_path / "detect"
    for day in range(18, 22):
        _make_run(root, f"classes_202609{day}_120000", day * 100)

    def _fail(path):
        raise OSError("in use")

    monkeypatch.setattr(general.shutil, "rmtree", _fail)
    deleted, freed, failed = general.prune_datasets(str(root), 1, None)
    assert deleted == []
    assert len(failed) == 3
    assert freed == 0


def test_real_prune_frees_the_expected_bytes(tmp_path):
    root = tmp_path / "detect"
    keep = _make_run(root, "classes_20260922_120000", 400, size=2048)
    drop = _make_run(root, "classes_20260921_120000", 300, size=1024)
    deleted, freed, failed = general.prune_datasets(str(root), 1, None)
    assert deleted == [drop]
    assert failed == []
    assert freed == 1024
    assert os.path.isdir(keep)
    assert not os.path.exists(drop)


def test_run_metadata_ties_a_finished_run_to_its_data(tmp_path):
    from anylabeling.views.training.ultralytics_dialog import (
        UltralyticsDialog,
    )

    project = tmp_path / "runs" / "detect" / "exp"
    (project / "weights").mkdir(parents=True)
    (project / "weights" / "best.pt").write_bytes(b"weights-payload")
    dataset_dir = tmp_path / "datasets" / "detect" / "classes_20260922_120000"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "data.yaml").write_text("path: x\n", encoding="utf-8")
    (dataset_dir / "manifest.json").write_text(
        json.dumps(
            {
                "seed": 99,
                "classes": CLASSES,
                "counts": {"train": 4, "val": 4},
                "data_yaml": str(dataset_dir / "data.yaml"),
            }
        ),
        encoding="utf-8",
    )
    (project / "results.csv").write_text(
        "epoch,train/box_loss,metrics/mAP50(B)\n" "1,0.5,0.75\n",
        encoding="utf-8",
    )

    fake = type(
        "Dialog",
        (),
        {
            "current_project_path": str(project),
            "selected_task_type": "Detect",
            "_training_started_at": 1_700_000_000,
            "_last_train_args": {"epochs": 2, "seed": 99, "device": "cpu"},
            "_last_dataset_manifest": load_dataset_manifest(str(dataset_dir)),
        },
    )()
    fake.write_run_metadata = UltralyticsDialog.write_run_metadata.__get__(
        fake
    )

    meta_path = fake.write_run_metadata()
    assert meta_path and os.path.isfile(meta_path)
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    assert meta["weights"]["sha1"] == general.file_sha1(
        str(project / "weights" / "best.pt")
    )
    assert meta["dataset"]["seed"] == 99
    assert meta["dataset"]["counts"] == {"train": 4, "val": 4}
    assert meta["dataset"]["manifest_sha1"]
    assert meta["train_args"] == {"epochs": 2, "seed": 99, "device": "cpu"}
    assert float(meta["metrics"]["map50"]) == 0.75
    assert meta["task"] == "Detect"


def test_run_metadata_is_skipped_for_a_missing_project(tmp_path):
    from anylabeling.views.training.ultralytics_dialog import (
        UltralyticsDialog,
    )

    fake = type(
        "Dialog",
        (),
        {
            "current_project_path": str(tmp_path / "nowhere"),
            "selected_task_type": "Detect",
            "_last_train_args": {},
            "_last_dataset_manifest": None,
        },
    )()
    fake.write_run_metadata = UltralyticsDialog.write_run_metadata.__get__(
        fake
    )
    assert fake.write_run_metadata() is None
