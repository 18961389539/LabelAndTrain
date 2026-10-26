"""A partially failed duplicate archive must say so."""

from unittest import mock

from anylabeling.views.labeling.utils import smart_archive


def test_all_moved_reports_success():
    with (
        mock.patch.object(smart_archive, "_notify") as notify,
        mock.patch.object(smart_archive.QMessageBox, "warning") as warning,
    ):
        smart_archive.report_archive_result(None, [("a.jpg", "b.jpg")], [])

    notify.assert_called_once()
    warning.assert_not_called()


def test_skipped_files_are_named_not_hidden():
    skipped = ["/data/photo.json", "/data/photo_2.json"]

    with (
        mock.patch.object(smart_archive, "_notify") as notify,
        mock.patch.object(smart_archive.QMessageBox, "warning") as warning,
    ):
        smart_archive.report_archive_result(
            None, [("a.jpg", "b.jpg")], skipped
        )

    notify.assert_not_called()
    warning.assert_called_once()
    text = warning.call_args.args[2]
    assert "photo.json" in text
    assert "photo_2.json" in text
    assert "1" in text
    assert "2" in text
