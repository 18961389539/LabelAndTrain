"""A pure-YOLO folder has no label JSON, and the training side must not
report it as empty: ``partition_images`` builds the dataset from the txt, so
the counting passes the pre-flight check and the panels use have to read the
same files.
"""

import json
import os

from jllabeling.services.auto_training.ultralytics.utils import (
    collect_class_names,
    dataset_overview_stats,
    get_label_infos,
    get_task_valid_images,
)

DETECT_LINE = "0 0.5 0.5 0.2 0.4\n"
SEGMENT_LINE = "0 0.1 0.1 0.9 0.1 0.9 0.2 0.1 0.2\n"


def _folder(tmp_path, specs, classes=None, record_labels=None):
    """``specs`` is ``{stem: txt_body or None}``; None means no label file."""
    for stem, body in specs.items():
        (tmp_path / f"{stem}.jpg").write_bytes(b"")
        if body is not None:
            (tmp_path / f"{stem}.txt").write_text(body, encoding="utf-8")
    if classes is not None:
        (tmp_path / "classes.txt").write_text(
            "\n".join(classes), encoding="utf-8"
        )
    if record_labels is not None:
        record = tmp_path / ".jllabel"
        record.mkdir(exist_ok=True)
        (record / "project.json").write_text(
            json.dumps({"labels": record_labels, "task": "Segment"}),
            encoding="utf-8",
        )
    return sorted(
        os.path.join(str(tmp_path), name)
        for name in os.listdir(str(tmp_path))
        if name.endswith(".jpg")
    )


def test_segment_task_counts_polygon_txt(tmp_path):
    image_list = _folder(
        tmp_path,
        {"a": SEGMENT_LINE, "b": SEGMENT_LINE + SEGMENT_LINE, "c": None},
        classes=["huahen"],
    )
    assert get_task_valid_images(image_list, "Segment") == 2
    # The same folder is not usable for Detect: the build rejects a segment
    # line in a detect run, so counting it here would promise a dataset that
    # then drops every image.
    assert get_task_valid_images(image_list, "Detect") == 0


def test_detect_task_counts_box_txt(tmp_path):
    image_list = _folder(
        tmp_path, {"a": DETECT_LINE, "b": DETECT_LINE}, classes=["huahen"]
    )
    assert get_task_valid_images(image_list, "Detect") == 2
    assert get_task_valid_images(image_list, "Segment") == 0


def test_empty_txt_is_a_negative_sample_not_a_label(tmp_path):
    image_list = _folder(
        tmp_path, {"a": DETECT_LINE, "b": "", "c": "   \n"}, classes=["cat"]
    )
    assert get_task_valid_images(image_list, "Detect") == 1
    total, labeled, empty, classes = dataset_overview_stats(image_list)
    assert (total, labeled, empty, classes) == (3, 1, 2, 1)


def test_json_wins_over_the_txt_of_the_same_image(tmp_path):
    image_list = _folder(tmp_path, {"a": SEGMENT_LINE}, classes=["cat"])
    (tmp_path / "a.json").write_text(
        json.dumps({"shapes": [{"label": "cat", "shape_type": "polygon"}]}),
        encoding="utf-8",
    )
    assert get_task_valid_images(image_list, "Segment") == 1
    assert get_label_infos(image_list, ["polygon"]) == {"cat": {"polygon": 1}}


def test_pose_and_classify_ignore_txt(tmp_path):
    image_list = _folder(tmp_path, {"a": DETECT_LINE}, classes=["cat"])
    assert get_task_valid_images(image_list, "Pose") == 0
    assert get_task_valid_images(image_list, "Classify") == 0


def test_class_names_come_from_classes_txt_in_id_order(tmp_path):
    image_list = _folder(
        tmp_path,
        {"a": "1 0.5 0.5 0.2 0.4\n", "b": "0 0.5 0.5 0.2 0.4\n"},
        classes=["cat", "dog"],
    )
    assert collect_class_names(image_list) == ["cat", "dog"]


def test_class_names_fall_back_to_the_project_record(tmp_path):
    image_list = _folder(
        tmp_path, {"a": SEGMENT_LINE}, record_labels=["huahen"]
    )
    assert collect_class_names(image_list) == ["huahen"]


def test_unnamed_class_id_keeps_its_slot(tmp_path):
    """An id past classes.txt must not shift the names after it."""
    image_list = _folder(
        tmp_path,
        {"a": "2 0.5 0.5 0.2 0.4\n", "b": "0 0.5 0.5 0.2 0.4\n"},
        classes=["cat"],
    )
    assert collect_class_names(image_list) == ["cat", "class_1", "class_2"]


def test_label_infos_counts_txt_shapes(tmp_path):
    image_list = _folder(
        tmp_path,
        {"a": SEGMENT_LINE * 2, "b": DETECT_LINE},
        classes=["huahen"],
    )
    assert get_label_infos(image_list, ["polygon"]) == {
        "huahen": {"polygon": 2}
    }
    assert get_label_infos(image_list, ["rectangle"]) == {
        "huahen": {"rectangle": 1}
    }


def test_overview_stats_counts_txt_and_their_classes(tmp_path):
    image_list = _folder(
        tmp_path,
        {"a": SEGMENT_LINE, "b": "1 " + SEGMENT_LINE.split(" ", 1)[1]},
        classes=["cat", "dog"],
    )
    total, labeled, empty, classes = dataset_overview_stats(image_list)
    assert (total, labeled, empty, classes) == (2, 2, 0, 2)


def test_unreadable_label_is_left_out_not_counted(tmp_path):
    image_list = _folder(tmp_path, {"a": DETECT_LINE}, classes=["cat"])
    broken = os.path.join(str(tmp_path), "a.json")
    os.remove(os.path.join(str(tmp_path), "a.txt"))
    with open(broken, "w", encoding="utf-8") as handle:
        handle.write("{ not json")
    assert get_task_valid_images(image_list, "Detect") == 0
    assert dataset_overview_stats(image_list) == (1, 0, 1, 0)
    assert collect_class_names(image_list) == []
