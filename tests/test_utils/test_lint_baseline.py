"""The flake8 ratchet has to be right in both directions.

A gate that never fails is worse than no gate: it reads as protection while a
regression sails through.  These tests pin the reporting/parsing layer of
``scripts/check_flake8_baseline.py`` -- the part that decides "regression" from
"improvement" -- without shelling out to flake8.
"""

import importlib.util
import os

import pytest

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
SCRIPT = os.path.join(REPO_ROOT, "scripts", "check_flake8_baseline.py")


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_flake8_baseline", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


REPORT = """\
anylabeling/app.py:12:5: F841 local variable 'x' is assigned to but never used
anylabeling/app.py:40:1: C901 'main' is too complex (19)
anylabeling\\views\\labeling\\widgets\\canvas.py:7:1: B007 Loop control variable 'i' not used
"""


def test_paths_are_normalized_across_platforms():
    """A baseline written on Windows must gate a Linux runner."""
    counts = checker.count_findings(REPORT)

    assert ("anylabeling/views/labeling/widgets/canvas.py", "B007") in counts
    assert not any("\\" in path for path, _code in counts)


def test_line_numbers_are_not_part_of_the_key():
    """Editing anything above a finding must not read as a regression."""
    moved = REPORT.replace("app.py:12:5", "app.py:912:5")

    assert checker.count_findings(moved) == checker.count_findings(REPORT)


def test_repeated_codes_are_counted_not_listed():
    counts = checker.count_findings(REPORT + REPORT)

    assert counts[("anylabeling/app.py", "F841")] == 2


def test_noise_lines_are_skipped():
    counts = checker.count_findings(
        "not a flake8 line\n\nanylabeling/app.py:1:1: E999 boom\n"
    )

    assert counts == {("anylabeling/app.py", "E999"): 1}


def test_a_brand_new_finding_is_a_regression():
    regressions, improvements = checker.compare(
        {("a.py", "F401"): 1}, {}
    )

    assert regressions == [("a.py", "F401", 0, 1)]
    assert improvements == []


def test_a_higher_count_is_a_regression():
    regressions, _ = checker.compare(
        {("a.py", "F401"): 3}, {("a.py", "F401"): 2}
    )

    assert regressions == [("a.py", "F401", 2, 3)]


def test_a_lower_count_is_an_improvement_not_a_regression():
    regressions, improvements = checker.compare(
        {("a.py", "F401"): 1}, {("a.py", "F401"): 2}
    )

    assert regressions == []
    assert improvements == [("a.py", "F401", 2, 1)]


def test_a_disappeared_finding_is_an_improvement():
    _, improvements = checker.compare({}, {("a.py", "F401"): 2})

    assert improvements == [("a.py", "F401", 2, 0)]


def test_matching_counts_are_neither():
    regressions, improvements = checker.compare(
        {("a.py", "F401"): 2}, {("a.py", "F401"): 2}
    )

    assert regressions == [] and improvements == []


def test_the_baseline_round_trips_through_its_file_format(tmp_path):
    original = {
        ("anylabeling/views/labeling/label_widget.py", "F841"): 2,
        ("tests/test_utils/test_style.py", "W292"): 1,
    }
    path = tmp_path / "baseline.txt"
    path.write_text(checker.format_baseline(original), encoding="utf-8")

    assert checker.load_baseline(str(path)) == original


def test_aligned_padding_is_not_swallowed_into_the_path(tmp_path):
    """format_baseline pads paths; load_baseline must strip that padding."""
    original = {("a/very/much/longer/path.py", "C901"): 1, ("b.py", "F841"): 3}
    path = tmp_path / "baseline.txt"
    path.write_text(checker.format_baseline(original), encoding="utf-8")

    loaded = checker.load_baseline(str(path))

    assert loaded == original
    assert ("a/very/much/longer/path.py " not in {p for p, _c in loaded})


def test_a_malformed_baseline_line_fails_loudly(tmp_path):
    path = tmp_path / "baseline.txt"
    path.write_text("this line has no code or count\n", encoding="utf-8")

    with pytest.raises(SystemExit):
        checker.load_baseline(str(path))


def test_an_empty_baseline_reads_as_empty_not_as_an_error(tmp_path):
    assert checker.load_baseline(str(tmp_path / "absent.txt")) == {}
