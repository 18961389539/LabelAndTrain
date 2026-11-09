"""Byte sizes adapt to their unit instead of always reading MB."""

from jllabeling.views.common.formatting import format_size


def test_bytes_stay_bytes():
    assert format_size(512) == "512 B"


def test_kilobytes_keep_one_decimal():
    assert format_size(1536) == "1.5 KB"


def test_megabytes_and_gigabytes_switch_units():
    assert format_size(5 * 1024 * 1024) == "5.0 MB"
    assert format_size(int(1.5 * 1024**3)) == "1.5 GB"


def test_negative_values_do_not_render_negative_sizes():
    assert format_size(-1) == "0 B"
