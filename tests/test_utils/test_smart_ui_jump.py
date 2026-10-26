"""Smart-tool jumps must not skip the unsaved-changes prompt."""

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from anylabeling.views.labeling.utils import smart_ui


def _parent(allowed, calls):
    return SimpleNamespace(
        may_continue=lambda: allowed,
        load_file=lambda path: calls.append(path),
    )


def test_a_cancelled_prompt_blocks_the_jump():
    calls = []

    assert smart_ui.load_result_image(_parent(False, calls), "x.png") is False
    assert calls == []


def test_a_allowed_parent_loads_the_image():
    calls = []

    assert smart_ui.load_result_image(_parent(True, calls), "x.png") is True
    assert calls == ["x.png"]


def test_a_stub_without_may_continue_still_loads():
    calls = []
    parent = SimpleNamespace(load_file=lambda path: calls.append(path))

    assert smart_ui.load_result_image(parent, "x.png") is True
    assert calls == ["x.png"]


def test_double_click_keeps_the_dialog_open_when_cancelled(tmp_path):
    image = tmp_path / "a.png"
    image.write_bytes(b"x")
    calls = []
    accepted = []
    dialog = SimpleNamespace(
        _parent=_parent(False, calls),
        accept=lambda: accepted.append(True),
    )
    item = SimpleNamespace(data=lambda role, path: str(image))

    smart_ui._ResultDialog._on_double_click(dialog, item, 0)

    assert calls == []
    assert accepted == []

    dialog._parent = _parent(True, calls)
    smart_ui._ResultDialog._on_double_click(dialog, item, 0)

    assert calls == [str(image)]
    assert accepted == [True]
