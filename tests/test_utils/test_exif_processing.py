"""EXIF rotation is destructive; these hold its safety and its accounting.

The feature rewrites the user's images. Three promises matter: every
original gets its own recoverable backup, a failed encode never damages
the file it was rewriting, and the result dialog reports what happened
rather than always saying "successfully processed".
"""

import os
import os.path as osp

import PIL.Image
import pytest
from PyQt6 import QtWidgets

from anylabeling.views.labeling.utils.async_exif import ExifProcessingDialog

ORIENTATION = 0x0112
MAKE = 0x010F


def _oriented_jpeg(path, color=(200, 10, 10), orientation=6, make=None):
    path = str(path)
    os.makedirs(osp.dirname(path), exist_ok=True)
    exif = PIL.Image.Exif()
    exif[ORIENTATION] = orientation
    if make:
        exif[MAKE] = make
    PIL.Image.new("RGB", (40, 20), color).save(path, quality=95, exif=exif)
    return path


def _process(paths, **kwargs):
    return ExifProcessingDialog._process_files(paths, **kwargs)


class TestExifProcessing:
    def test_nested_same_names_get_separate_backups(self, tmp_path):
        first = _oriented_jpeg(tmp_path / "sub1" / "photo.jpg")
        second = _oriented_jpeg(tmp_path / "sub2" / "photo.jpg")

        result = _process([first, second])

        assert len(result["processed"]) == 2
        assert result["failed"] == []
        backup_dir = result["backup_dir"]
        assert backup_dir
        backups = sorted(
            osp.relpath(osp.join(root, name), backup_dir)
            for root, _, files in os.walk(backup_dir)
            for name in files
        )
        assert backups == [
            osp.join("sub1", "photo.jpg"),
            osp.join("sub2", "photo.jpg"),
        ]
        for filename in (first, second):
            backup = osp.join(backup_dir, osp.relpath(filename, tmp_path))
            with PIL.Image.open(backup) as image:
                assert image.getexif().get(ORIENTATION) == 6
            with PIL.Image.open(filename) as image:
                assert image.size == (20, 40)
                assert image.getexif().get(ORIENTATION) in (None, 1)

    def test_the_rewrite_keeps_the_jpeg_quantisation(self, tmp_path):
        filename = _oriented_jpeg(tmp_path / "photo.jpg", make="ProbeCam")
        with PIL.Image.open(filename) as image:
            qtables = dict(image.quantization)

        assert _process([filename])["processed"] == [filename]

        with PIL.Image.open(filename) as image:
            assert dict(image.quantization) == qtables
            assert image.getexif().get(MAKE) == "ProbeCam"
            assert image.getexif().get(ORIENTATION) in (None, 1)

    def test_backups_from_a_second_run_do_not_replace_the_first(
        self, tmp_path
    ):
        filename = _oriented_jpeg(tmp_path / "photo.jpg")
        first = _process([filename])
        _oriented_jpeg(filename)

        second = _process([filename])

        assert first["backup_dir"] != second["backup_dir"]
        assert osp.isfile(osp.join(first["backup_dir"], "photo.jpg"))
        assert osp.isfile(osp.join(second["backup_dir"], "photo.jpg"))

    def test_cancel_stops_after_the_current_file_and_says_so(self, tmp_path):
        files = [
            _oriented_jpeg(tmp_path / name / "photo.jpg")
            for name in ("one", "two", "three")
        ]
        seen = []

        def on_file(index, filename):
            seen.append(filename)

        def cancel():
            return len(seen) >= 1

        result = _process(files, cancel=cancel, on_file=on_file)

        assert result["cancelled"] is True
        assert result["processed"] == [files[0]]
        assert result["backup_dir"]
        for untouched in files[1:]:
            with PIL.Image.open(untouched) as image:
                assert image.getexif().get(ORIENTATION) == 6

    def test_backups_do_not_come_back_as_dataset_images(self, tmp_path):
        flat = _oriented_jpeg(tmp_path / "photo.jpg")
        nested = _oriented_jpeg(tmp_path / "sub" / "photo.jpg")
        _process([flat, nested])

        from anylabeling.views.labeling.utils.qt import scan_all_images

        assert sorted(scan_all_images(str(tmp_path))) == sorted([flat, nested])

    def test_one_broken_file_does_not_stop_the_batch(self, tmp_path):
        good = _oriented_jpeg(tmp_path / "good.jpg")
        bad = tmp_path / "bad.jpg"
        bad.write_bytes(b"not an image")

        result = _process([str(bad), good])

        assert result["processed"] == [good]
        assert [osp.basename(name) for name, _ in result["failed"]] == [
            "bad.jpg"
        ]
        assert bad.read_bytes() == b"not an image"
        assert osp.isfile(osp.join(result["backup_dir"], "good.jpg"))


@pytest.fixture()
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    yield app


class TestExifResultDialog:
    def _result(self, **overrides):
        result = {
            "processed": ["a.jpg"],
            "skipped": [],
            "failed": [],
            "cancelled": False,
            "backup_dir": "backups",
            "total": 1,
        }
        result.update(overrides)
        return result

    def test_failures_are_reported_with_real_counts_and_paths(
        self, qapp, monkeypatch
    ):
        monkeypatch.setattr(QtWidgets.QMessageBox, "exec", lambda self: 0)

        box = ExifProcessingDialog._report_result(
            None,
            self._result(
                failed=[("bad.jpg", "UnidentifiedImageError")],
                total=2,
            ),
        )

        assert box is not None
        assert "1 succeeded, 1 failed (of 2 total)" in box.text()
        assert "bad.jpg" in box.detailedText()
        assert "UnidentifiedImageError" in box.detailedText()

    def test_success_counts_processed_images_not_the_requested_list(
        self, qapp, monkeypatch
    ):
        calls = []
        monkeypatch.setattr(
            QtWidgets.QMessageBox,
            "information",
            lambda parent, title, text: calls.append((title, text)),
        )

        box = ExifProcessingDialog._report_result(
            None,
            self._result(
                processed=["a.jpg", "b.jpg"],
                skipped=["c.jpg"],
                backup_dir="backups",
                total=3,
            ),
        )

        assert box is None
        assert len(calls) == 1
        assert "processed 2 images" in calls[0][1]
        assert "backups" in calls[0][1]

    def test_a_cancelled_run_does_not_announce_success(
        self, qapp, monkeypatch
    ):
        calls = []
        monkeypatch.setattr(
            QtWidgets.QMessageBox,
            "information",
            lambda *args: calls.append(args),
        )

        box = ExifProcessingDialog._report_result(
            None, self._result(cancelled=True)
        )

        assert box is None
        assert calls == []
