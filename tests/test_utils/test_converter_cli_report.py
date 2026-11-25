"""The XLABEL->YOLO CLI: one image once, and a report of what it dropped.

``get_image_files`` used to glob both ``*.png`` and ``*.PNG``; on a
case-insensitive filesystem (Windows, macOS) that listed every image twice,
so the conversion count and the shape statistics doubled.  The report is the
other half: the CLI printed only "Converted N files", which made a run that
discarded every polygon look identical to a clean one.
"""

import os

from PIL import Image

from jllabeling.views.common.converter import (
    _report_conversion_skips,
    get_image_files,
)


def _save(directory, name):
    Image.new("RGB", (8, 8), "gray").save(os.path.join(directory, name))


def test_an_image_is_listed_once_on_case_insensitive_filesystems(tmp_path):
    _save(tmp_path, "a.png")

    files = get_image_files(str(tmp_path))

    assert [os.path.basename(path) for path in files] == ["a.png"]


def test_the_uppercase_extension_is_still_found(tmp_path):
    _save(tmp_path, "b.PNG")

    files = get_image_files(str(tmp_path))

    assert [os.path.basename(path) for path in files] == ["b.PNG"]


def test_a_mixed_directory_lists_every_file_once(tmp_path):
    _save(tmp_path, "a.png")
    _save(tmp_path, "b.PNG")
    _save(tmp_path, "c.jpg")

    names = [os.path.basename(path) for path in get_image_files(str(tmp_path))]

    assert names == ["a.png", "b.PNG", "c.jpg"]


def test_the_report_names_every_skip_reason(capsys):
    _report_conversion_skips(
        {
            "exported": 2,
            "skipped": {
                "polygon is not part of a hbb export": 3,
                "label not in classes: other": 1,
            },
        },
        images_without_labels=1,
    )

    out = capsys.readouterr().out

    assert "shapes written: 2" in out
    assert "images without a label file (skipped): 1" in out
    assert "skipped shapes: 4" in out
    assert "3 × polygon is not part of a hbb export" in out
    assert "1 × label not in classes: other" in out


def test_a_clean_run_reports_only_the_shape_count(capsys):
    """One extra line is deliberate: it proves boxes were written, not just
    files created (an all-empty export would otherwise read as success)."""
    _report_conversion_skips({"exported": 5})

    out = capsys.readouterr().out

    assert "shapes written: 5" in out
    assert "skipped" not in out
