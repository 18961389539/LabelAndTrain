"""Time-left estimation from ultralytics ``results.csv``.

The estimate is deliberately built from *deltas* of the cumulative ``time``
column rather than from ``total / epochs``: the first epochs are the slowest
(model load, cache build), and a resumed run restarts the clock while the
epoch counter continues — dividing would be wrong in both cases.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anylabeling.services.auto_training.ultralytics.utils import (  # noqa: E402
    estimate_remaining_seconds,
)

HEADER = "epoch,time,train/box_loss,metrics/mAP50(B)\n"


def _write_csv(tmp_path, rows):
    path = tmp_path / "results.csv"
    body = "".join(f"{epoch},{elapsed},1.5,0.5\n" for epoch, elapsed in rows)
    path.write_text(HEADER + body, encoding="utf-8")
    return str(path)


def test_two_epochs_are_enough_to_extrapolate(tmp_path):
    # 10s per epoch, 5 of 10 done -> 50s left.
    path = _write_csv(tmp_path, [(1, 10), (2, 20), (3, 30), (4, 40), (5, 50)])

    assert estimate_remaining_seconds(path, 10) == 50


def test_a_single_epoch_is_not_enough(tmp_path):
    path = _write_csv(tmp_path, [(1, 35)])

    assert estimate_remaining_seconds(path, 10) is None


def test_the_slow_first_epoch_does_not_dominate(tmp_path):
    # Epoch 1 costs 100s (cold start), later epochs 10s; 4 of 20 done.
    path = _write_csv(tmp_path, [(1, 100), (2, 110), (3, 120), (4, 130)])

    remaining = estimate_remaining_seconds(path, 20)

    assert remaining == 160, "16 epochs x 10s, not 16 x ~32s"


def test_a_resumed_run_uses_deltas_not_the_total(tmp_path):
    # The clock restarted at resume: epoch 6 shows 10s, not 6 x epoch time.
    path = _write_csv(tmp_path, [(6, 10), (7, 20), (8, 30), (9, 40), (10, 50)])

    assert estimate_remaining_seconds(path, 20) == 100


def test_a_finished_run_has_nothing_left(tmp_path):
    path = _write_csv(tmp_path, [(1, 10), (2, 20), (3, 30)])

    assert estimate_remaining_seconds(path, 3) is None


def test_a_repeated_row_after_resume_is_tolerated(tmp_path):
    # Resume can repeat the row it continued from; the duplicate delta is 0
    # and must not drag the average down.
    path = _write_csv(tmp_path, [(1, 10), (2, 20), (2, 20), (3, 30), (4, 40)])

    assert estimate_remaining_seconds(path, 10) == 60


def test_missing_file_or_unknown_total_is_quiet(tmp_path):
    assert estimate_remaining_seconds(str(tmp_path / "nope.csv"), 10) is None
    path = _write_csv(tmp_path, [(1, 10), (2, 20)])
    assert estimate_remaining_seconds(path, 0) is None
    assert estimate_remaining_seconds(path, None) is None


def test_unparseable_rows_are_refused(tmp_path):
    path = tmp_path / "results.csv"
    path.write_text(
        HEADER + "1,abc,1.5,0.5\n2,def,1.4,0.6\n", encoding="utf-8"
    )

    assert estimate_remaining_seconds(str(path), 10) is None
