"""Stats sinks on the VOC and COCO converters.

Both exported silently before: a point in a VOC run, a polygon in a COCO
detect run and a label outside the class list all disappeared from the
output with no counter. These pin what lands in the sink, which is what the
CLI report and (for YOLO) the manifest are built from.
"""

import json

from PIL import Image

from jllabeling.views.labeling.label_converter import LabelConverter


def _make_case(tmp_path, shapes=None):
    if shapes is None:
        shapes = [
            {
                "label": "defect",
                "shape_type": "rectangle",
                "points": [[10, 10], [40, 30]],
            },
            {
                "label": "defect",
                "shape_type": "polygon",
                "points": [[1, 1], [20, 1], [20, 20]],
            },
            {
                "label": "defect",
                "shape_type": "point",
                "points": [[5, 5]],
            },
        ]
    Image.new("RGB", (100, 80), "gray").save(tmp_path / "a.png")
    (tmp_path / "a.json").write_text(
        json.dumps(
            {
                "version": "2.4.0",
                "flags": {},
                "imagePath": "a.png",
                "imageWidth": 100,
                "imageHeight": 80,
                "shapes": shapes,
            }
        ),
        encoding="utf-8",
    )
    return str(tmp_path / "a.png"), str(tmp_path / "a.json")


def test_voc_counts_written_shapes_and_names_the_skip(tmp_path):
    image, label = _make_case(tmp_path)
    stats = {}

    is_empty = LabelConverter(classes=["defect"]).custom_to_voc(
        image, label, str(tmp_path / "a.xml"), "polygon", True, stats=stats
    )

    assert is_empty is False
    assert stats["exported"] == 2  # rectangle + polygon, both valid here
    assert stats["skipped"] == {"point is not part of a voc export": 1}


def test_voc_counts_an_image_without_a_label_file(tmp_path):
    image, _ = _make_case(tmp_path)
    (tmp_path / "a.json").unlink()
    stats = {}

    is_empty = LabelConverter(classes=["defect"]).custom_to_voc(
        image,
        str(tmp_path / "a.json"),
        str(tmp_path / "a.xml"),
        "polygon",
        True,
        stats=stats,
    )

    assert is_empty is True
    assert stats["missing_label_file"] == 1


def test_coco_counts_written_shapes_and_both_skip_reasons(tmp_path):
    image, _ = _make_case(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    stats = {}

    LabelConverter(classes=["defect"]).custom_to_coco(
        [image], str(tmp_path), str(out), "rectangle", stats=stats
    )

    assert stats["exported"] == 1
    assert stats["skipped"] == {
        "polygon is not part of a coco rectangle export": 1,
        "point is not part of a coco rectangle export": 1,
    }


def test_coco_counts_a_label_outside_the_class_list(tmp_path):
    shapes = [
        {
            "label": "other",
            "shape_type": "rectangle",
            "points": [[10, 10], [40, 30]],
        }
    ]
    image, _ = _make_case(tmp_path, shapes)
    out = tmp_path / "out"
    out.mkdir()
    stats = {}

    LabelConverter(classes=["defect"]).custom_to_coco(
        [image], str(tmp_path), str(out), "rectangle", stats=stats
    )

    assert stats.get("exported", 0) == 0
    assert stats["skipped"] == {"label not in classes: other": 1}


def test_coco_counts_images_without_a_label_file(tmp_path):
    _make_case(tmp_path)
    (tmp_path / "a.json").unlink()
    out = tmp_path / "out"
    out.mkdir()
    stats = {}

    LabelConverter(classes=["defect"]).custom_to_coco(
        [str(tmp_path / "a.png")],
        str(tmp_path),
        str(out),
        "rectangle",
        stats=stats,
    )

    assert stats["missing_label_file"] == 1
