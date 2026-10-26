"""Overview export must not use the user's folder as scratch space."""

import os
import zipfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from anylabeling.views.labeling.widgets import overview_dialog


def test_export_does_not_touch_existing_files(tmp_path):
    (tmp_path / "classes.txt").write_text("REAL\n", encoding="utf-8")
    (tmp_path / "export_data.zip").write_bytes(b"old zip")
    label_infos = [["image", "count"], ["a.png", 1], ["total", 1]]
    headers = ["shape", "label"]
    shape_infos = [["box", "cat"]]

    path = overview_dialog.write_overview_export(
        str(tmp_path), label_infos, shape_infos, headers
    )

    assert os.path.basename(path) == "export_data_2.zip"
    assert (tmp_path / "classes.txt").read_text(encoding="utf-8") == "REAL\n"
    assert (tmp_path / "export_data.zip").read_bytes() == b"old zip"
    with zipfile.ZipFile(path) as bundle:
        assert sorted(bundle.namelist()) == [
            "classes.txt",
            "label_infos.csv",
            "shape_infos.csv",
        ]
        assert bundle.read("classes.txt").decode("utf-8") == "a.png"
    assert not (tmp_path / "label_infos.csv").exists()
    assert not (tmp_path / "shape_infos.csv").exists()
    assert [n for n in os.listdir(tmp_path) if n.endswith(".part")] == []


def test_a_failed_archive_leaves_nothing_behind(tmp_path, monkeypatch):
    class Boom:
        def __init__(self, *args, **kwargs):
            raise OSError("disk full")

    monkeypatch.setattr(overview_dialog.zipfile, "ZipFile", Boom)

    with pytest.raises(OSError):
        overview_dialog.write_overview_export(
            str(tmp_path), [["h"], ["total"]], [], ["h"]
        )

    assert os.listdir(tmp_path) == []
