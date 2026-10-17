"""Importing COCO segmentations that are RLE-encoded must not lose objects.

`convert --task coco2xlabel --mode segment` is a shipped CLI path, and the
*standard* COCO distribution files store `segmentation` as an RLE dict rather
than a polygon list -- the branch that used to say `# TODO: Handle RLE format
segmentation` skipped every one of them and the object vanished without a
word. The encoder below is written straight from the format description, so a
match against the decoder is not a self-fulfilling check.
"""

import json
import os

import numpy as np
import pytest

from anylabeling.views.labeling.label_converter import (
    LabelConverter,
    _rle_run_counts,
    _rle_to_mask,
    _rle_to_polygons,
)


def _encode_runs(counts):
    """COCO compressed-RLE encoder: zig-zag, then 5-bit LEB128 groups."""
    out = []
    for value in counts:
        zigzag = (value << 1) if value >= 0 else (((-value) << 1) - 1)
        while True:
            chunk = zigzag & 0x1F
            zigzag >>= 5
            if zigzag:
                chunk |= 0x20
            out.append(chr(chunk + 48))
            if not zigzag:
                break
    return "".join(out)


def _rle_from_mask(mask):
    """An RLE dict (compressed counts) for a 2-D 0/1 mask, column-major."""
    flat = np.asarray(mask).reshape(-1, order="F")
    runs = []
    current = 0
    length = 0
    for value in flat:
        if int(value) == current:
            length += 1
        else:
            runs.append(length)
            current = int(value)
            length = 1
    runs.append(length)
    height, width = np.asarray(mask).shape
    return {
        "size": [height, width],
        "counts": _encode_runs(runs),
        "num": list(runs),
    }


def _rect_mask(height, width, rows, cols):
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[rows[0] : rows[1] + 1, cols[0] : cols[1] + 1] = 1
    return mask


# --- the encoding --------------------------------------------------------


def test_run_counts_round_trip_both_forms():
    mask = _rect_mask(40, 60, (10, 19), (20, 39))
    rle = _rle_from_mask(mask)
    assert _rle_run_counts(rle["counts"]) == rle["num"]
    assert _rle_run_counts(rle["num"]) == rle["num"]


def test_decoded_mask_equals_the_source():
    mask = _rect_mask(40, 60, (10, 19), (20, 39))
    rle = _rle_from_mask(mask)
    assert np.array_equal(_rle_to_mask(rle), mask)
    uncompressed = {"size": rle["size"], "counts": rle["num"]}
    assert np.array_equal(_rle_to_mask(uncompressed), mask)


def test_unreadable_encodings_return_none_not_an_exception():
    assert _rle_to_mask({"size": [4, 4], "counts": "!!!"}) is None
    assert _rle_to_mask({"size": [0, 0], "counts": [0]}) is None
    assert _rle_to_mask({"counts": [1, 1]}) is None
    # runs that do not add up to h*w are not a mask of this image
    assert _rle_to_mask({"size": [4, 4], "counts": [3, 2]}) is None
    assert _rle_to_polygons({"size": [4, 4], "counts": 17}) is None


# --- the import path -----------------------------------------------------


def _coco_document(rle):
    return {
        "images": [
            {
                "id": 1,
                "file_name": "part.png",
                "width": 60,
                "height": 40,
            }
        ],
        "categories": [{"id": 7, "name": "scratch"}],
        "annotations": [
            {
                "id": 1,
                "image_id": 1,
                "category_id": 7,
                "segmentation": [rle],
                "bbox": [20, 10, 20, 10],
                "area": 200,
                "iscrowd": 0,
            }
        ],
    }


def _import(tmp_path, document):
    source = tmp_path / "annotations.json"
    source.write_text(json.dumps(document), encoding="utf-8")
    out_dir = tmp_path / "labels"
    out_dir.mkdir()
    LabelConverter(classes=["scratch"]).coco_to_custom(
        str(source), str(out_dir), "polygon"
    )
    files = sorted(os.listdir(out_dir))
    return out_dir, files


def test_rle_segmentation_imports_as_a_polygon(tmp_path):
    mask = _rect_mask(40, 60, (10, 19), (20, 39))
    out_dir, files = _import(tmp_path, _coco_document(_rle_from_mask(mask)))
    assert files == ["part.json"], files
    shapes = json.loads((out_dir / files[0]).read_text(encoding="utf-8"))[
        "shapes"
    ]
    assert len(shapes) == 1, shapes
    shape = shapes[0]
    assert shape["shape_type"] == "polygon"
    xs = [p[0] for p in shape["points"]]
    ys = [p[1] for p in shape["points"]]
    # The contour traces the pixel centres at the edge of the filled block.
    assert min(xs) == pytest.approx(20, abs=1.5), xs
    assert max(xs) == pytest.approx(39, abs=1.5), xs
    assert min(ys) == pytest.approx(10, abs=1.5), ys
    assert max(ys) == pytest.approx(19, abs=1.5), ys


def test_unreadable_rle_is_reported_and_the_rest_still_imports(
    tmp_path, caplog
):
    good = _rle_from_mask(_rect_mask(40, 60, (10, 19), (20, 39)))
    document = _coco_document(good)
    document["annotations"].append(
        {
            "id": 2,
            "image_id": 1,
            "category_id": 7,
            "segmentation": [{"size": [40, 60], "counts": "!!!"}],
            "bbox": [0, 0, 5, 5],
            "area": 25,
            "iscrowd": 0,
        }
    )
    out_dir, files = _import(tmp_path, document)
    shapes = json.loads((out_dir / files[0]).read_text(encoding="utf-8"))[
        "shapes"
    ]
    assert len(shapes) == 1, shapes
    assert any(
        "Unreadable COCO RLE" in record.message for record in caplog.records
    ), [r.message for r in caplog.records]


def test_polygon_segmentations_still_work(tmp_path):
    document = _coco_document([])
    document["annotations"][0]["segmentation"] = [
        [20, 10, 40, 10, 40, 20, 20, 20]
    ]
    out_dir, files = _import(tmp_path, document)
    shapes = json.loads((out_dir / files[0]).read_text(encoding="utf-8"))[
        "shapes"
    ]
    assert len(shapes) == 1, shapes
