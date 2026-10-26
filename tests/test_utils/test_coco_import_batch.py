"""A bad COCO annotation must be counted, not abort the whole file."""

import json
from unittest import mock

from anylabeling.views.labeling.label_converter import LabelConverter


def _doc(annotations, images=None, categories=None):
    return {
        "categories": categories or [{"id": 1, "name": "cat"}],
        "images": images
        or [
            {
                "id": 1,
                "file_name": "a.png",
                "width": 20,
                "height": 20,
            },
            {
                "id": 2,
                "file_name": "b.png",
                "width": 20,
                "height": 20,
            },
        ],
        "annotations": annotations,
    }


def _import(tmp_path, document, mode="rectangle", converter=None, **kwargs):
    source = tmp_path / "coco.json"
    source.write_text(json.dumps(document), encoding="utf-8")
    out = tmp_path / "labels"
    out.mkdir(exist_ok=True)
    converter = converter or LabelConverter(classes=["cat"])
    report = converter.coco_to_custom(str(source), str(out), mode, **kwargs)
    return report, out


def _annotation(image_id, category_id=1, bbox=None, **extra):
    annotation = {
        "image_id": image_id,
        "category_id": category_id,
        "bbox": bbox or [1, 2, 3, 4],
        "segmentation": [],
    }
    annotation.update(extra)
    return annotation


def test_a_bad_annotation_does_not_stop_the_file(tmp_path):
    document = _doc(
        [
            _annotation(1),
            _annotation(2, bbox=[1, 2]),
            _annotation(2, bbox=[5, 6, 7, 8]),
        ]
    )

    report, out = _import(tmp_path, document)

    assert report["written"] == 2
    assert len(report["skipped"]) == 1
    assert report["failed"] == []
    with open(out / "a.json", encoding="utf-8") as handle:
        assert len(json.load(handle)["shapes"]) == 1
    with open(out / "b.json", encoding="utf-8") as handle:
        assert len(json.load(handle)["shapes"]) == 1


def _one_image():
    return [{"id": 1, "file_name": "a.png", "width": 20, "height": 20}]


def test_an_unknown_category_is_skipped(tmp_path):
    document = _doc(
        [_annotation(1, category_id=99), _annotation(1)],
        images=_one_image(),
    )

    report, out = _import(tmp_path, document)

    assert report["written"] == 1
    assert len(report["skipped"]) == 1
    with open(out / "a.json", encoding="utf-8") as handle:
        assert len(json.load(handle)["shapes"]) == 1


def test_an_unknown_image_id_is_skipped(tmp_path):
    document = _doc([_annotation(3), _annotation(1)], images=_one_image())

    report, _out = _import(tmp_path, document)

    assert report["written"] == 1
    assert len(report["skipped"]) == 1


def test_cancel_stops_before_writing(tmp_path):
    document = _doc([_annotation(1), _annotation(2)])
    calls = []

    def cancel():
        calls.append(1)
        return len(calls) > 1

    report, out = _import(tmp_path, document, cancel=cancel)

    assert report["cancelled"] is True
    assert report["written"] == 0
    assert not (out / "a.json").exists()
    assert not (out / "b.json").exists()


def test_a_write_failure_is_reported_and_does_not_crash(tmp_path):
    document = _doc([_annotation(1)], images=_one_image())
    converter = LabelConverter(classes=["cat"])
    source = tmp_path / "coco.json"
    source.write_text(json.dumps(document), encoding="utf-8")
    out = tmp_path / "labels"
    out.mkdir()

    with mock.patch.object(
        converter, "save_label_json", side_effect=OSError("disk full")
    ):
        report = converter.coco_to_custom(str(source), str(out), "rectangle")

    assert report["written"] == 0
    assert len(report["failed"]) == 1
    assert "disk full" in report["failed"][0][1]


def test_pose_import_still_builds_the_box_and_keypoints(tmp_path):
    categories = [
        {
            "id": 1,
            "name": "person",
            "keypoints": ["nose", "eye"],
        }
    ]
    annotation = _annotation(
        1,
        bbox=[1, 2, 3, 4],
        keypoints=[5, 6, 2, 0, 0, 0],
    )
    document = _doc(
        [annotation],
        images=[
            {
                "id": 1,
                "file_name": "a.png",
                "width": 20,
                "height": 20,
            }
        ],
        categories=categories,
    )

    report, out = _import(
        tmp_path, document, mode="pose", converter=LabelConverter()
    )

    assert report["written"] == 1
    with open(out / "a.json", encoding="utf-8") as handle:
        shapes = json.load(handle)["shapes"]
    assert [shape["label"] for shape in shapes] == ["person", "nose"]
    assert [shape["shape_type"] for shape in shapes] == [
        "rectangle",
        "point",
    ]
    assert shapes[1]["group_id"] == shapes[0]["group_id"]
