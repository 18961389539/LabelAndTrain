"""Train-tab feedback: the log survives, and the images are pageable.

Two behaviours that used to depend on the user doing the right thing:

* The log was written to disk only from ``closeEvent``, so a crash, a
  force-quit or a cleared log view lost the only copy. It is now written when
  a run reaches a terminal state — and identical content is not written
  twice, so the terminal save and the close-time save do not stack up.
* The six thumbnails were the whole story: everything else was one OS viewer
  window per file. The in-dialog pager walks the full set, which needs its
  index arithmetic to wrap (``step_index``).
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anylabeling.views.training.image_preview_dialog import (  # noqa: E402
    step_index,
)
from anylabeling.views.training.ultralytics_dialog import (  # noqa: E402
    UltralyticsDialog,
)


class _FakeLogDisplay:
    """Just enough of a QTextEdit for the save path."""

    def __init__(self, text=""):
        self._text = text

    def toPlainText(self):  # noqa: N802 - Qt naming
        return self._text

    def set_text(self, text):
        self._text = text


def _log_stub(tmp_path, text="epoch 1 done"):
    run_dir = tmp_path / "runs" / "exp"
    run_dir.mkdir(parents=True)
    stub = SimpleNamespace(
        log_display=_FakeLogDisplay(text),
        current_project_path=str(run_dir),
        training_status="completed",
        _last_saved_log_text=None,
    )
    stub.save_training_logs_to_file = (
        UltralyticsDialog.save_training_logs_to_file.__get__(stub)
    )
    return stub, run_dir


def _saved_logs(run_dir):
    logs_dir = run_dir / "logs"
    return (
        sorted(logs_dir.glob("training_log_*.txt"))
        if logs_dir.exists()
        else []
    )


def test_a_terminal_state_writes_the_log_to_disk(tmp_path):
    stub, run_dir = _log_stub(tmp_path)

    written = stub.save_training_logs_to_file()

    files = _saved_logs(run_dir)
    assert len(files) == 1
    assert str(files[0]) == written
    assert files[0].read_text(encoding="utf-8") == "epoch 1 done"
    assert files[0].name.startswith("training_log_completed_")


def test_identical_content_is_not_written_twice(tmp_path):
    stub, run_dir = _log_stub(tmp_path)

    stub.save_training_logs_to_file()
    again = stub.save_training_logs_to_file()

    assert again is None
    assert len(_saved_logs(run_dir)) == 1


def test_more_log_means_a_new_file(tmp_path):
    stub, run_dir = _log_stub(tmp_path)
    stub.save_training_logs_to_file()

    stub.log_display.set_text("epoch 1 done\nepoch 2 done")
    stub.save_training_logs_to_file()

    assert len(_saved_logs(run_dir)) == 2


def test_an_empty_or_missing_run_writes_nothing(tmp_path):
    stub, run_dir = _log_stub(tmp_path, text="   ")

    assert stub.save_training_logs_to_file() is None
    assert _saved_logs(run_dir) == []

    stub.log_display.set_text("something")
    stub.current_project_path = str(tmp_path / "gone")
    assert stub.save_training_logs_to_file() is None


def test_the_pager_wraps_in_both_directions():
    assert step_index(0, 1, 3) == 1
    assert step_index(2, 1, 3) == 0, "past the last image wraps to the first"
    assert step_index(0, -1, 3) == 2, "before the first wraps to the last"
    assert step_index(5, 1, 0) == 0, "no images means no index"
    assert step_index(1, 1, 1) == 0, "a single image stays put"
