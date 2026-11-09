"""Remaining training time uses hours once minutes stop being readable."""

from jllabeling.views.training.eta_format import format_remaining


def _tr(text):
    return text


def test_under_a_minute():
    assert format_remaining(30, _tr) == "剩余不到 1 分钟"


def test_minutes():
    assert format_remaining(12 * 60, _tr) == "约剩余 12 分钟"


def test_hours_and_minutes():
    assert format_remaining((2 * 60 + 5) * 60, _tr) == "约剩余 2 小时 5 分钟"


def test_whole_hours():
    assert format_remaining(3 * 60 * 60, _tr) == "约剩余 3 小时"
