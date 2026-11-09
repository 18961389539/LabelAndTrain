"""The training dialog exposes determinate preparation progress and cancel."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QCloseEvent

from jllabeling.views.training import ultralytics_dialog as dialog_module


def _dialog(tmp_path, monkeypatch):
    from tests.test_auto_training.test_training_safety_guards import (
        _build_dialog,
    )

    return _build_dialog(tmp_path, monkeypatch)


class _AliveThread:
    def is_alive(self):
        return True


def test_progress_update_shows_counts_on_the_bar(tmp_path, monkeypatch):
    _parent, dialog = _dialog(tmp_path, monkeypatch)
    dialog.training_status = "preparing"
    dialog._dataset_progress = ("copying", 3, 10)

    dialog._update_dataset_progress()

    assert dialog.progress_bar.maximum() == 10
    assert dialog.progress_bar.value() == 3
    assert dialog.progress_bar.format() == "3/10"
    assert "3/10" in dialog.metrics_label.text()


def test_cancel_button_stops_the_worker_once(tmp_path, monkeypatch):
    _parent, dialog = _dialog(tmp_path, monkeypatch)
    dialog.training_status = "preparing"
    dialog._dataset_thread = _AliveThread()
    dialog._set_preparation_controls(True)

    dialog.cancel_dataset_preparation()

    assert dialog._dataset_cancel_event.is_set()
    assert dialog.cancel_preparation_button.isEnabled() is False
    assert "取消" in dialog.cancel_preparation_button.text()


def test_close_during_preparation_cancels_then_closes(tmp_path, monkeypatch):
    _parent, dialog = _dialog(tmp_path, monkeypatch)
    stub = dialog_module.QMessageBox
    stub.answer = stub.StandardButton.Yes
    dialog.training_status = "preparing"
    dialog._dataset_thread = _AliveThread()
    dialog._dataset_cancel_event.clear()

    event = QCloseEvent()
    dialog.closeEvent(event)

    assert not event.isAccepted(), "the worker still owns the dialog"
    assert dialog._dataset_cancel_event.is_set()
    assert dialog._close_after_prepare

    closed = []
    monkeypatch.setattr(dialog, "close", lambda: closed.append(True))
    dialog._on_dataset_preparation_finished("", "", True)

    assert closed == [True]
    assert dialog.training_status == "idle"
    assert dialog._close_after_prepare is False


def test_declining_the_close_keeps_preparation_running(tmp_path, monkeypatch):
    _parent, dialog = _dialog(tmp_path, monkeypatch)
    stub = dialog_module.QMessageBox
    stub.answer = stub.StandardButton.No
    dialog.training_status = "preparing"
    dialog._dataset_thread = _AliveThread()
    dialog._dataset_cancel_event.clear()

    event = QCloseEvent()
    dialog.closeEvent(event)

    assert not event.isAccepted()
    assert not dialog._dataset_cancel_event.is_set()
    assert dialog._close_after_prepare is False


def test_worker_forwards_progress_and_reports_cancellation(
    tmp_path, monkeypatch
):
    from jllabeling.services.auto_training.ultralytics.general import (
        DatasetPreparationCancelled,
    )
    from jllabeling.views.training import (
        dataset_preparation as preparation_module,
    )

    _parent, dialog = _dialog(tmp_path, monkeypatch)
    dialog.image_list = []
    dialog.selected_task_type = "Classify"
    monkeypatch.setattr(dialog, "_project_split_seed", lambda: (1, "test"))

    def cancelled_build(*args, **kwargs):
        assert callable(kwargs["progress_callback"])
        assert callable(kwargs["cancel_check"])
        raise DatasetPreparationCancelled()

    monkeypatch.setattr(
        preparation_module, "create_yolo_dataset", cancelled_build
    )
    received = []
    dialog.dataset_preparation_finished.connect(
        lambda *args: received.append(args)
    )

    dialog._prepare_dataset_worker(
        {"basic": {"dataset_ratio": 1.0, "data": ""}, "checkpoint": {}}
    )

    assert received == [("", "", True)]
