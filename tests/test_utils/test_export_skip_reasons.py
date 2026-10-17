"""Export skip reasons are explained in Chinese, not dumped as codes.

``LabelConverter`` records one English reason string per shape it cannot
represent, and the manifest keeps those keys on purpose -- they are
machine-readable and must not change with the UI language. The recap dialog
is the one place a person reads them, and until this batch it printed
``- 2 × rotation reaching outside the image`` into an otherwise Chinese
sentence: true, but the line the annotator has to act on.
"""

import os
import re

import pytest

from anylabeling.views.labeling.utils.export import _skip_reason_text

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
CONVERTER = os.path.join(
    REPO_ROOT, "anylabeling", "views", "labeling", "label_converter.py"
)

#: What each f-string hole in a reason template stands for, so the guard can
#: build a real reason out of the source. A hole that is not listed here
#: renders as ``???`` and fails the guard -- that is the point.
SAMPLES = {
    "label": "划痕",
    "len(points)": "3",
    "shape_type": "polygon",
    "mode": "hbb",
}

REASON = re.compile(
    r"_bump_skip\(\s*stats,\s*(f?)([\"'])(.+?)\2",
    re.S,
)


def _emitted_reasons():
    source = open(CONVERTER, encoding="utf-8").read()
    reasons = []
    for is_f, _quote, body in REASON.findall(source):
        text = body.replace("\n", " ").strip()
        if is_f:
            text = re.sub(
                r"\{([^}]*)\}",
                lambda m: SAMPLES.get(m.group(1).strip(), "???"),
                text,
            )
        reasons.append(text)
    return reasons


def test_every_reason_the_converter_can_emit_is_explained():
    reasons = sorted(set(_emitted_reasons()))
    assert reasons, "no skip reasons found -- the pattern needs updating"
    unexplained = [r for r in reasons if _skip_reason_text(r) == r]
    assert unexplained == [], f"raw English reaches the dialog: {unexplained}"


def test_an_unknown_reason_is_still_shown_rather_than_hidden():
    """A reason nobody mapped must surface, not disappear behind the table."""
    assert (
        _skip_reason_text("polygon needs an closed contour")
        == "polygon needs an closed contour"
    )


def test_the_offending_class_name_survives_the_rewording():
    text = _skip_reason_text("label not in classes: 气泡")
    assert "气泡" in text
    assert text != "label not in classes: 气泡"


def test_the_rotation_vertex_count_is_not_lost():
    assert "3" in _skip_reason_text("rotation with 3 points")


def test_the_summary_line_is_chinese_end_to_end():
    from types import SimpleNamespace

    from anylabeling.views.labeling.utils import export

    stats = {
        "exported": 7,
        "skipped": {
            "rotation reaching outside the image": 2,
            "label not in classes: 气泡": 1,
        },
    }
    text = export._format_yolo_export_summary(
        SimpleNamespace(),
        5,
        5,
        stats,
        copied_images=0,
        classes_target=None,
    )
    assert "2 ×" in text
    assert "旋转框有顶点落在画面外" in text
    assert "类别不在导出类别表里：气泡" in text
    assert "rotation reaching outside the image" not in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
