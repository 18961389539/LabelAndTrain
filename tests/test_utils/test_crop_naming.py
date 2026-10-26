"""Two images with the same stem must not share a crop file."""

import json
import os

import cv2
import numpy as np

from anylabeling.views.labeling.utils.crop import (
    duplicate_stem_suffixes,
    process_single_image,
)


def _image(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.zeros((20, 20, 3), dtype=np.uint8)
    path.write_bytes(cv2.imencode(".png", data)[1].tobytes())
    return str(path)


def _label(image_path):
    label = os.path.splitext(image_path)[0] + ".json"
    with open(label, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "shapes": [
                    {
                        "label": "cat",
                        "points": [[2, 2], [10, 2], [10, 10], [2, 10]],
                        "shape_type": "rectangle",
                    }
                ]
            },
            handle,
        )


def test_suffixes_only_for_colliding_stems(tmp_path):
    first = _image(tmp_path / "a" / "photo.png")
    second = _image(tmp_path / "b" / "photo.png")
    unique = _image(tmp_path / "c" / "other.png")

    suffixes = duplicate_stem_suffixes([first, second, unique])

    assert set(suffixes) == {first, second}
    assert suffixes[first] != suffixes[second]
    assert suffixes[first].startswith("_")


def test_same_stem_images_produce_two_crop_files(tmp_path):
    paths = [_image(tmp_path / name / "photo.png") for name in ("a", "b")]
    for path in paths:
        _label(path)
    suffixes = duplicate_stem_suffixes(paths)
    output = tmp_path / "crops"

    for path in paths:
        assert process_single_image(
            (
                path,
                os.path.dirname(path),
                str(output),
                0,
                0,
                {"cat": 1},
                suffixes[path],
            )
        )

    crops = sorted((output / "cat").iterdir())
    assert len(crops) == 2, crops
    assert crops[0].name != crops[1].name
    assert all(crop.stat().st_size > 0 for crop in crops)
