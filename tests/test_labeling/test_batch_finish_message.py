"""A stopped batch must not report itself as a completed one."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from jllabeling.views.labeling.utils.batch import batch_finish_message


def test_stopped_with_progress_says_stopped():
    message = batch_finish_message(3, 1, stopped=True)
    assert "已停止" in message
    assert "3" in message and "1" in message


def test_stopped_without_progress_is_not_success():
    message = batch_finish_message(0, 0, stopped=True)
    assert "已停止" in message
    assert "completed successfully" not in message


def test_completed_still_reports_success():
    assert (
        batch_finish_message(5, 0, stopped=False)
        == "Processing completed successfully! (5 images processed)"
    )


def test_failures_stay_visible():
    message = batch_finish_message(2, 1, stopped=False)
    assert "2" in message and "1" in message


def test_failed_images_dialog_shows_the_reason():
    from PyQt6 import QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    from jllabeling.views.labeling.utils.batch import FailedImagesDialog

    dialog = FailedImagesDialog(None, [("a.png", "模型未返回结果"), "b.png"])
    tree = dialog.list_widget

    assert tree.topLevelItemCount() == 2
    assert tree.topLevelItem(0).text(0) == "a.png"
    assert tree.topLevelItem(0).text(1) == "模型未返回结果"
    assert tree.topLevelItem(1).text(0) == "b.png"
    tree.setCurrentItem(tree.topLevelItem(0))
    assert dialog.selected_path() == "a.png"
