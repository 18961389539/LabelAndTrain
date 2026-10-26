"""One malformed YOLO file must not abort the whole folder import."""

import json

from PIL import Image

from anylabeling.views.labeling.label_converter import LabelConverter
from anylabeling.views.labeling.utils.upload import import_yolo_labels

VALID = "0 0.5 0.5 0.2 0.2\n"


def _image(tmp_path, name):
    path = tmp_path / name
    Image.new("RGB", (20, 20), "white").save(path)
    return str(path)


def _label(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def _run(tmp_path, images, labels, **kwargs):
    converter = LabelConverter(classes=["cat"])
    preserve = kwargs.pop("preserve_existing", False)
    return import_yolo_labels(
        converter,
        image_file_list=list(images),
        label_file_list=list(labels),
        label_dir_path=str(tmp_path),
        image_dir_path=str(tmp_path),
        output_dir_path=str(tmp_path),
        mode="hbb",
        preserve_existing=preserve,
        **kwargs,
    )


def test_one_malformed_file_does_not_stop_the_batch(tmp_path):
    _image(tmp_path, "a.png")
    _image(tmp_path, "b.png")
    _label(tmp_path, "a.txt", VALID)
    _label(tmp_path, "b.txt", "this is not a yolo line\n")

    result = _run(tmp_path, ["a.png", "b.png"], ["a.txt", "b.txt"])

    assert result["attempted"] == 2
    assert result["imported"] == 1
    assert [name for name, _ in result["failed"]] == [str(tmp_path / "b.json")]
    with open(tmp_path / "a.json", encoding="utf-8") as handle:
        assert json.load(handle)["shapes"][0]["label"] == "cat"
    assert not (tmp_path / "b.json").exists()


def test_a_missing_image_is_reported_and_the_rest_continue(tmp_path):
    _image(tmp_path, "a.png")
    _label(tmp_path, "a.txt", VALID)
    _label(tmp_path, "b.txt", VALID)

    result = _run(tmp_path, ["a.png", "b.png"], ["a.txt", "b.txt"])

    assert result["imported"] == 1
    assert [name for name, _ in result["failed"]] == [str(tmp_path / "b.json")]


def test_preserve_existing_merges_the_new_shapes(tmp_path):
    _image(tmp_path, "a.png")
    _label(tmp_path, "a.txt", VALID)
    (tmp_path / "a.json").write_text(
        json.dumps(
            {
                "shapes": [
                    {
                        "label": "old",
                        "points": [[1, 2], [3, 4]],
                        "shape_type": "rectangle",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = _run(
        tmp_path,
        ["a.png"],
        ["a.txt"],
        preserve_existing=True,
    )

    assert result["imported"] == 1
    with open(tmp_path / "a.json", encoding="utf-8") as handle:
        labels = [shape["label"] for shape in json.load(handle)["shapes"]]
    assert labels == ["old", "cat"]


def test_cancellation_reports_the_partial_run(tmp_path):
    for name in ("a", "b", "c"):
        _image(tmp_path, f"{name}.png")
        _label(tmp_path, f"{name}.txt", VALID)
    calls = []
    seen = []

    def cancelled():
        calls.append(1)
        return len(calls) > 1

    result = _run(
        tmp_path,
        ["a.png", "b.png", "c.png"],
        ["a.txt", "b.txt", "c.txt"],
        progress=lambda index, total: seen.append(index),
        is_cancelled=cancelled,
    )

    assert result["cancelled"] is True
    assert result["imported"] == 1
    assert result["attempted"] == 1
    assert seen == [0]
    assert (tmp_path / "a.json").exists()
    assert not (tmp_path / "b.json").exists()
    assert not (tmp_path / "c.json").exists()
