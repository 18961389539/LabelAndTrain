import csv
import json

import yaml

from anylabeling.services.auto_training.ultralytics.utils import (
    autolabel_type_for_task,
    collect_class_names,
    dataset_overview_stats,
    parse_training_metrics,
    sanitize_custom_model_name,
    write_autolabel_model_yaml,
)


def test_dataset_overview_stats_counts_labeled_and_empty(tmp_path):
    image_a = tmp_path / "a.jpg"
    image_b = tmp_path / "b.jpg"
    image_c = tmp_path / "c.jpg"
    image_a.write_bytes(b"")
    image_b.write_bytes(b"")
    image_c.write_bytes(b"")
    (tmp_path / "a.json").write_text(
        json.dumps({"shapes": [{"label": "cat", "points": [[0, 0]]}]}),
        encoding="utf-8",
    )
    (tmp_path / "b.json").write_text(
        json.dumps({"shapes": [], "flags": {"dog": True}}),
        encoding="utf-8",
    )
    total, labeled, empty, class_count = dataset_overview_stats(
        [str(image_a), str(image_b), str(image_c)]
    )
    assert total == 3
    assert labeled == 2
    assert empty == 1
    assert class_count == 2


def test_collect_class_names_preserves_first_seen_order(tmp_path):
    image_a = tmp_path / "a.jpg"
    image_b = tmp_path / "b.jpg"
    image_a.write_bytes(b"")
    image_b.write_bytes(b"")
    (tmp_path / "a.json").write_text(
        json.dumps(
            {
                "shapes": [
                    {"label": "cat"},
                    {"label": "dog"},
                    {"label": "cat"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "b.json").write_text(
        json.dumps({"shapes": [{"label": "bird"}]}),
        encoding="utf-8",
    )
    assert collect_class_names([str(image_a), str(image_b)]) == [
        "cat",
        "dog",
        "bird",
    ]


def test_parse_training_metrics_reads_last_row(tmp_path):
    csv_path = tmp_path / "results.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "epoch",
                "train/box_loss",
                "metrics/mAP50(B)",
                "metrics/mAP50-95(B)",
            ]
        )
        writer.writerow(["1", "1.2", "0.4", "0.2"])
        writer.writerow(["2", "0.8", "0.6", "0.3"])
    loss, map50, epochs = parse_training_metrics(str(csv_path))
    assert loss == "0.8"
    assert map50 == "0.6"
    assert epochs == 2


def test_write_autolabel_model_yaml(tmp_path):
    onnx_path = tmp_path / "best.onnx"
    onnx_path.write_bytes(b"")
    yaml_path = tmp_path / "best.yaml"
    write_autolabel_model_yaml(
        str(yaml_path),
        model_type="yolov8",
        name="project_best",
        display_name="trained weights",
        model_path=str(onnx_path),
        classes=["cat", "dog"],
    )
    with yaml_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    assert payload["type"] == "yolov8"
    assert payload["name"] == "project_best"
    assert payload["classes"] == ["cat", "dog"]
    assert payload["model_path"].endswith("best.onnx")


def test_autolabel_type_and_name_helpers():
    assert autolabel_type_for_task("Detect") == "yolov8"
    assert autolabel_type_for_task("Segment") == "yolov8_seg"
    assert autolabel_type_for_task("Pose") is None
    assert sanitize_custom_model_name("detect run #1") == "detect_run_1"
