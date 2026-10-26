"""One bad VOC XML must not stop the folder import."""

import json

from anylabeling.views.labeling.label_converter import LabelConverter
from anylabeling.views.labeling.utils.upload import import_voc_labels

VALID = """<annotation>
  <size><width>20</width><height>20</height></size>
  <object><name>cat</name><bndbox>
    <xmin>1</xmin><ymin>2</ymin><xmax>10</xmax><ymax>12</ymax>
  </bndbox></object>
</annotation>
"""


def _run(tmp_path, images, labels, **kwargs):
    return import_voc_labels(
        LabelConverter(),
        list(images),
        list(labels),
        str(tmp_path),
        str(tmp_path),
        "rectangle",
        **kwargs,
    )


def test_one_bad_xml_does_not_stop_the_batch(tmp_path):
    (tmp_path / "a.xml").write_text(VALID, encoding="utf-8")
    (tmp_path / "b.xml").write_text("<annotation>", encoding="utf-8")

    result = _run(tmp_path, ["a.png", "b.png"], ["a.xml", "b.xml"])

    assert result["attempted"] == 2
    assert result["imported"] == 1
    assert [name for name, _ in result["failed"]] == [str(tmp_path / "b.json")]
    with open(tmp_path / "a.json", encoding="utf-8") as handle:
        shapes = json.load(handle)["shapes"]
    assert [shape["label"] for shape in shapes] == ["cat"]
    assert shapes[0]["shape_type"] == "rectangle"
    assert not (tmp_path / "b.json").exists()


def test_an_image_without_an_xml_is_skipped_not_failed(tmp_path):
    (tmp_path / "a.xml").write_text(VALID, encoding="utf-8")

    result = _run(tmp_path, ["a.png", "b.png"], ["a.xml"])

    assert result["attempted"] == 1
    assert result["imported"] == 1
    assert result["failed"] == []


def test_cancellation_stops_after_the_current_file(tmp_path):
    for name in ("a", "b", "c"):
        (tmp_path / f"{name}.xml").write_text(VALID, encoding="utf-8")
    calls = []
    seen = []

    def cancelled():
        calls.append(1)
        return len(calls) > 1

    result = _run(
        tmp_path,
        ["a.png", "b.png", "c.png"],
        ["a.xml", "b.xml", "c.xml"],
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
