"""The folder scan can report progress and be cancelled."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from jllabeling.views.labeling.utils.qt import scan_all_images


def _touch(path):
    path.write_bytes(b"")
    return path


def test_scan_reports_progress_and_keeps_the_list_contract(tmp_path):
    for index in range(520):
        _touch(tmp_path / f"{index:04d}.png")

    seen = []
    result = scan_all_images(
        str(tmp_path), on_progress=lambda found: seen.append(found)
    )

    assert len(result) == 520
    assert seen and seen[-1] <= 520


def test_scan_cancel_returns_none(tmp_path):
    for index in range(600):
        _touch(tmp_path / f"{index:04d}.png")

    result = scan_all_images(str(tmp_path), on_progress=lambda found: False)

    assert result is None


def test_scan_without_callback_is_unchanged(tmp_path):
    _touch(tmp_path / "a.png")
    _touch(tmp_path / "b.txt")

    assert scan_all_images(str(tmp_path)) == [str(tmp_path / "a.png")]
