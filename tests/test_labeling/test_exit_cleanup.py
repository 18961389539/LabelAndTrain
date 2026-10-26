"""Closing the window must stop background work in the right order."""

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from anylabeling.views.labeling import label_widget  # noqa: E402
from anylabeling.views.labeling.label_widget import (  # noqa: E402
    LabelingWidget,
)
from anylabeling.views.labeling.utils import exit_cleanup  # noqa: E402


class _Event:
    def __init__(self):
        self.ignored = False

    def ignore(self):
        self.ignored = True


class _Thread:
    def __init__(self, running=True, raises=False):
        self.running = running
        self.raises = raises

    def isRunning(self):
        if self.raises:
            raise RuntimeError("already deleted")
        return self.running


class _Manager:
    def __init__(self):
        self.calls = []

    def cancel_download(self):
        self.calls.append("download")

    def cancel_prediction(self):
        self.calls.append("prediction")


def _batch_widget(active=True, thread=None):
    return SimpleNamespace(
        _batch_processing_active=active,
        _batch_thread=thread,
        cancel_processing=False,
    )


def test_an_idle_widget_closes_without_touching_the_batch_flag():
    widget = _batch_widget(active=False)

    assert exit_cleanup.batch_allows_close(widget) is True
    assert widget.cancel_processing is False


def test_a_running_batch_refuses_the_close_and_requests_cancel():
    widget = _batch_widget(thread=_Thread(running=True))

    assert exit_cleanup.batch_allows_close(widget) is False
    assert widget.cancel_processing is True


def test_a_batch_thread_that_already_stopped_allows_the_close():
    widget = _batch_widget(thread=_Thread(running=False))

    assert exit_cleanup.batch_allows_close(widget) is True
    assert widget.cancel_processing is True


def test_a_deleted_thread_wrapper_is_not_a_reason_to_refuse():
    widget = _batch_widget(thread=_Thread(raises=True))

    assert exit_cleanup.batch_allows_close(widget) is True


def test_cancel_model_work_asks_both_operations_to_stop():
    manager = _Manager()
    widget = SimpleNamespace(
        auto_labeling_widget=SimpleNamespace(model_manager=manager)
    )

    exit_cleanup.cancel_model_work(widget)

    assert manager.calls == ["download", "prediction"]


def test_cancel_model_work_tolerates_no_auto_labeling_panel():
    exit_cleanup.cancel_model_work(SimpleNamespace())


def test_close_is_refused_while_the_batch_thread_runs(monkeypatch):
    warnings = []
    may_continue_called = []
    monkeypatch.setattr(
        label_widget.QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(args),
    )
    monkeypatch.setattr(
        label_widget.exit_cleanup,
        "batch_allows_close",
        lambda widget: False,
    )
    widget = SimpleNamespace(
        may_continue=lambda: may_continue_called.append(True) or True,
        tr=lambda text: text,
    )
    event = _Event()

    LabelingWidget.closeEvent(widget, event)

    assert event.ignored is True
    assert may_continue_called == []
    assert warnings
    assert "正在停止批量标注" in warnings[0][2]


def test_a_proceeding_close_cancels_model_work(monkeypatch):
    manager = _Manager()

    class _Settings:
        def setValue(self, *args):
            pass

    monkeypatch.setattr(
        label_widget,
        "project_settings",
        SimpleNamespace(flush_open_project=lambda widget: None),
    )
    monkeypatch.setattr(label_widget, "save_config", lambda config: True)
    widget = SimpleNamespace(
        may_continue=lambda: True,
        settings=_Settings(),
        filename=None,
        recent_files=[],
        last_open_dir=None,
        _settings_controller=None,
        _config={},
        auto_labeling_widget=SimpleNamespace(model_manager=manager),
    )

    LabelingWidget.closeEvent(widget, _Event())

    assert manager.calls == ["download", "prediction"]


def test_a_cancelled_save_prompt_does_not_cancel_model_work(monkeypatch):
    manager = _Manager()
    widget = SimpleNamespace(
        may_continue=lambda: False,
        auto_labeling_widget=SimpleNamespace(model_manager=manager),
    )
    event = _Event()

    LabelingWidget.closeEvent(widget, event)

    assert event.ignored is True
    assert manager.calls == []
