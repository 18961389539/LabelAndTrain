"""Regression guard for the training-failure dialog.

``on_training_event`` built its error box through ``QtWidgets.QMessageBox``
while the module only imported the widget classes themselves.  The name was
never supplied by any of the five ``import *`` lines either -- flake8 could
not say so, because a star import downgrades a missing name from F821
("undefined name") to F405 ("*may* be undefined").  It sat inside 157 such
warnings until the star imports were replaced with explicit ones, at which
point the four real uses turned into F821 and were fixed.

These tests exercise the branch itself, so a future edit that reaches for a
name the module does not define fails here instead of on a user's machine.
"""

from types import SimpleNamespace

from anylabeling.views.training import ultralytics_dialog as dialog_module
from anylabeling.views.training.ultralytics_dialog import UltralyticsDialog

CRASH_CODE = "Training process exited with code -1073741819"


class _Button:
    """Minimal QPushButton stand-in that records its visibility."""

    def __init__(self):
        self.visible = None
        self.text = None
        self.role = None

    def setVisible(self, value):  # noqa: N802 - Qt naming
        self.visible = value


class _Timer:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


class _MessageBox:
    """Records what the handler asked the real box to do."""

    Icon = SimpleNamespace(Critical="critical")
    ButtonRole = SimpleNamespace(AcceptRole="accept", RejectRole="reject")
    instances = []

    def __init__(self, parent=None):
        self.parent = parent
        self.icon = None
        self.title = None
        self.text = None
        self.informative = None
        self.buttons = []
        self.default_button = None
        self.executed = False
        self._clicked = None
        _MessageBox.instances.append(self)

    def setIcon(self, icon):  # noqa: N802
        self.icon = icon

    def setWindowTitle(self, title):  # noqa: N802
        self.title = title

    def setText(self, text):  # noqa: N802
        self.text = text

    def setInformativeText(self, text):  # noqa: N802
        self.informative = text

    def addButton(self, text, role=None):  # noqa: N802
        button = _Button()
        button.text = text
        button.role = role
        self.buttons.append(button)
        return button

    def setDefaultButton(self, button):  # noqa: N802
        self.default_button = button

    def exec(self):
        self.executed = True

    def clickedButton(self):  # noqa: N802
        return self._clicked


class _SpinBox:
    """Minimal spin-box stand-in for a quick fix's target widget."""

    def __init__(self, value=16):
        self._value = value

    def value(self):
        return self._value

    def setValue(self, value):  # noqa: N802 - Qt naming
        self._value = value


class _Combo:
    """Minimal combo stand-in (device)."""

    def __init__(self, items, current=0):
        self._items = list(items)
        self._current = current

    def findText(self, text):  # noqa: N802
        return self._items.index(text) if text in self._items else -1

    def setCurrentIndex(self, index):  # noqa: N802
        self._current = index


def _stub_dialog(logs, tab_jumps, config_widgets=None):
    """A dialog stub carrying only what the error branch touches."""
    stub = SimpleNamespace(
        training_status="training",
        start_training_button=_Button(),
        previous_button=_Button(),
        stop_training_button=_Button(),
        export_button=_Button(),
        progress_timer=_Timer(),
        image_timer=_Timer(),
        config_widgets=config_widgets or {},
        update_training_status_display=lambda: None,
        refresh_wizard_state=lambda: None,
        append_training_log=logs.append,
        go_to_specific_tab=tab_jumps.append,
        tr=lambda text: text,
    )
    stub._readable_training_error = (
        UltralyticsDialog._readable_training_error.__get__(stub)
    )
    stub._handle_training_error = (
        UltralyticsDialog._handle_training_error.__get__(stub)
    )
    stub._error_quick_fixes = UltralyticsDialog._error_quick_fixes.__get__(
        stub
    )
    stub._apply_error_fix = UltralyticsDialog._apply_error_fix.__get__(stub)
    # The error path persists the log before showing the box; a stub has no
    # log view to write.
    stub.save_training_logs_to_file = lambda *args, **kwargs: None
    return stub


def _run_error_event(
    monkeypatch, error=CRASH_CODE, traceback_text="", config_widgets=None
):
    """Fire one ``training_error`` event and hand back the recorded bits."""
    _MessageBox.instances = []
    monkeypatch.setattr(
        dialog_module,
        "QtWidgets",
        SimpleNamespace(QMessageBox=_MessageBox),
    )
    logs, tab_jumps = [], []
    stub = _stub_dialog(logs, tab_jumps, config_widgets)
    UltralyticsDialog.on_training_event(
        stub,
        "training_error",
        {"error": error, "traceback": traceback_text},
    )
    return stub, logs, tab_jumps


def test_the_error_branch_can_build_its_message_box(monkeypatch):
    """The handler must not reach for a name the module does not define."""
    stub, _, tab_jumps = _run_error_event(monkeypatch)

    assert stub.training_status == "error"
    assert stub.start_training_button.visible is False
    assert stub.previous_button.visible is True
    assert stub.stop_training_button.visible is False
    assert stub.export_button.visible is False
    assert stub.progress_timer.stopped and stub.image_timer.stopped
    assert tab_jumps == [1], "dismissing the box returns to the config tab"


def test_the_box_explains_a_cryptic_windows_crash_code(monkeypatch):
    _, _, _ = _run_error_event(monkeypatch)

    (box,) = _MessageBox.instances
    assert box.icon == "critical"
    assert box.title == "Training Failed"
    assert box.executed is True
    assert "access violation" in box.text
    # The crash code also carries a one-click remedy, and it is the default:
    # plain retry would hit the same worker crash again.
    assert [button.text for button in box.buttons] == [
        "Set Workers to 0 & Retry",
        "Retry Training",
        "Back to Config",
    ]
    assert [button.role for button in box.buttons] == [
        "accept",
        "accept",
        "reject",
    ]
    assert box.default_button is box.buttons[0]


def test_a_traceback_is_logged_and_mentioned_in_the_box(monkeypatch):
    trace = "Traceback (most recent call last):\n  boom"
    _, logs, _ = _run_error_event(monkeypatch, traceback_text=trace)

    (box,) = _MessageBox.instances
    assert f"ERROR: {CRASH_CODE}" in logs
    assert "--- Traceback ---" in logs
    assert any(trace in line for line in logs)
    assert "training log" in box.informative


def test_an_unknown_error_is_passed_through_unchanged(monkeypatch):
    _, _, _ = _run_error_event(monkeypatch, error="something else entirely")

    (box,) = _MessageBox.instances
    assert box.text == "Training failed:\nsomething else entirely"
    assert box.informative is None
    # Nothing we can name a remedy for: only retry and back out.
    assert [button.text for button in box.buttons] == [
        "Retry Training",
        "Back to Config",
    ]
    assert box.default_button is box.buttons[0]


def test_retrying_restarts_from_the_train_tab(monkeypatch):
    _MessageBox.instances = []
    monkeypatch.setattr(
        dialog_module,
        "QtWidgets",
        SimpleNamespace(QMessageBox=_MessageBox),
    )
    restarts = []
    stub = _stub_dialog([], [])
    stub.reset_train_tab = lambda: None
    stub.start_training_from_train_tab = lambda: restarts.append(True)

    original_add_button = _MessageBox.addButton

    def click_retry(self, text, role=None):
        button = original_add_button(self, text, role)
        if text == "Retry Training":
            self._clicked = button
        return button

    monkeypatch.setattr(_MessageBox, "addButton", click_retry)
    UltralyticsDialog.on_training_event(
        stub, "training_error", {"error": CRASH_CODE}
    )

    assert restarts == [True]


def _click_and_rerun(monkeypatch, button_text, error, config_widgets):
    """Fire the error, click ``button_text``, report (logs, restarts, stub)."""
    _MessageBox.instances = []
    monkeypatch.setattr(
        dialog_module,
        "QtWidgets",
        SimpleNamespace(QMessageBox=_MessageBox),
    )
    logs, restarts = [], []
    stub = _stub_dialog(logs, [], config_widgets)
    stub.reset_train_tab = lambda: None
    stub.start_training_from_train_tab = lambda: restarts.append(True)

    original_add_button = _MessageBox.addButton

    def click_target(self, text, role=None):
        button = original_add_button(self, text, role)
        if text == button_text:
            self._clicked = button
        return button

    monkeypatch.setattr(_MessageBox, "addButton", click_target)
    UltralyticsDialog.on_training_event(
        stub, "training_error", {"error": error}
    )
    return logs, restarts, stub


def test_an_oom_offers_a_halved_batch_and_applies_it(monkeypatch):
    batch = _SpinBox(16)
    logs, restarts, _ = _click_and_rerun(
        monkeypatch,
        "Halve Batch & Retry",
        "CUDA out of memory. Tried to allocate 2.00 GiB",
        {"batch": batch},
    )

    assert batch.value() == 8, "the fix halves what the user actually had"
    assert restarts == [True]
    assert any("batch=8" in line for line in logs)


def test_an_oom_with_auto_batch_lands_on_a_concrete_size(monkeypatch):
    batch = _SpinBox(-1)  # -1 = auto; halving it would stay negative
    _click_and_rerun(
        monkeypatch,
        "Halve Batch & Retry",
        "DefaultCPUAllocator: can't allocate memory: you tried to allocate",
        {"batch": batch},
    )

    assert batch.value() == 8


def test_a_worker_crash_offers_workers_zero_and_applies_it(monkeypatch):
    workers = _SpinBox(8)
    logs, restarts, _ = _click_and_rerun(
        monkeypatch,
        "Set Workers to 0 & Retry",
        CRASH_CODE,
        {"workers": workers},
    )

    assert workers.value() == 0
    assert restarts == [True]
    assert any("workers=0" in line for line in logs)


def test_a_missing_cuda_device_offers_switching_to_cpu(monkeypatch):
    device = _Combo(["cuda", "cpu"], current=0)
    _click_and_rerun(
        monkeypatch,
        "Switch to CPU & Retry",
        "No CUDA-capable device is detected",
        {"device": device},
    )

    assert device._current == 1, "the device now points at cpu"
