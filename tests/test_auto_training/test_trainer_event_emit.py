"""Worker event reporting must survive a missing or broken stdout.

A windowed (``console=False``) frozen build can hand the worker a stream whose
handle is invalid; ``flush()`` then raises ``OSError``. Before this was fixed,
that exception replaced the real training error with a misleading startup-crash
dialog, so these cases are pinned here.
"""

import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anylabeling.services.auto_training.ultralytics import trainer

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _BrokenStream:
    """Accepts writes but fails on flush, like an invalid Win32 handle."""

    def write(self, _text):
        return len(_text)

    def flush(self):
        raise OSError(22, "Invalid argument")


def _parse_event(line):
    assert line.startswith(trainer.TRAINING_WORKER_EVENT_PREFIX)
    payload = line[len(trainer.TRAINING_WORKER_EVENT_PREFIX) :]
    return json.loads(payload)


class TestEmitTrainingWorkerEvent(unittest.TestCase):
    def test_writes_prefixed_json_line(self):
        stream = io.StringIO()
        trainer.emit_training_worker_event(
            "training_log", output_stream=stream, message="hi"
        )
        event = _parse_event(stream.getvalue().strip())
        self.assertEqual(event, {"event": "training_log", "message": "hi"})

    def test_flush_error_falls_back_to_sys_stdout(self):
        fallback = io.StringIO()
        with mock.patch.object(sys, "__stdout__", fallback):
            trainer.emit_training_worker_event(
                "training_error",
                output_stream=_BrokenStream(),
                error="boom",
            )
        event = _parse_event(fallback.getvalue().strip())
        self.assertEqual(event, {"event": "training_error", "error": "boom"})

    def test_flush_error_without_fallback_is_noop(self):
        with mock.patch.object(sys, "__stdout__", None):
            trainer.emit_training_worker_event(
                "training_error",
                output_stream=_BrokenStream(),
                error="boom",
            )


if __name__ == "__main__":
    unittest.main()
