#!/usr/bin/env python3
"""Ratchet flake8 against a checked-in baseline.

The fork inherited a few hundred findings from upstream and has no appetite
for a big-bang cleanup.  So the current state is frozen in
``scripts/flake8_baseline.txt`` as ``<path> <code> <count>`` triples, and this
script fails only when a finding gets *worse*:

* a ``(path, code)`` pair that is not in the baseline at all, or
* a higher count for one that is.

Line numbers are deliberately not part of the key -- they move whenever
anything above them is edited, which would make the baseline useless.

Fixes are always welcome: the run reports what got better and invites you to
re-freeze the baseline with ``--update``.

Usage
-----
    python scripts/check_flake8_baseline.py            # gate: exit 1 on regression
    python scripts/check_flake8_baseline.py --update   # re-freeze the baseline
    python scripts/check_flake8_baseline.py --quiet    # only report regressions

The same rule set must be installed wherever this runs, otherwise the numbers
are not comparable -- keep the ``dev`` extra in ``pyproject.toml`` and the
flake8 hook in ``.pre-commit-config.yaml`` in sync with each other.
"""

from __future__ import annotations

import argparse
import collections
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE_PATH = os.path.join(REPO_ROOT, "scripts", "flake8_baseline.txt")

#: Everything this fork owns.  ``anylabeling/resources/resources.py`` is
#: generated and excluded by flake8's own config.
DEFAULT_TARGETS = ("anylabeling", "tests", "scripts", "tools")

_HEADER = """\
# flake8 findings this fork has inherited but not yet cleaned up.
# Regenerate with: python scripts/check_flake8_baseline.py --update
# Format: <path> <code> <count>   (line numbers intentionally omitted)
"""


def run_flake8(targets, repo_root=REPO_ROOT):
    """Return flake8's raw report for ``targets``."""
    command = [sys.executable, "-m", "flake8", *targets]
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            capture_output=True,
            text=True,
        )
    except OSError as error:  # pragma: no cover - only on a broken install
        raise SystemExit(f"Could not run flake8: {error}") from error

    if completed.returncode not in (0, 1):
        # 0 = clean, 1 = findings.  Anything else is flake8 itself failing.
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise SystemExit(
            "flake8 did not run correctly "
            f"(exit {completed.returncode}):\n{detail}"
        )
    return completed.stdout


def count_findings(report):
    """Collapse a flake8 report into ``{(path, code): count}``.

    Expected line shape: ``path:line:col: CODE message``.
    """
    counts = collections.Counter()
    for line in report.splitlines():
        parts = line.split(":", 3)
        if len(parts) < 4:
            continue
        path, lineno, column, rest = parts
        if not lineno.strip().isdigit() or not column.strip().isdigit():
            continue
        code = rest.strip().split(" ", 1)[0]
        if not code:
            continue
        # Windows flake8 separates with "\", Linux with "/".  Normalize so a
        # baseline generated on one platform gates the other.
        counts[(path.replace("\\", "/"), code)] += 1
    return counts


def load_baseline(path=BASELINE_PATH):
    counts = collections.Counter()
    if not os.path.isfile(path):
        return counts
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.rsplit(None, 2)
            if len(parts) != 3:
                raise SystemExit(f"Malformed baseline line: {line!r}")
            file_path, code, count = parts
            try:
                counts[(file_path, code)] = int(count)
            except ValueError:
                raise SystemExit(
                    f"Malformed baseline line (count is not a number): "
                    f"{line!r}"
                ) from None
    return counts


def format_baseline(counts):
    lines = [_HEADER]
    width = max((len(path) for path, _code in counts), default=0)
    for (path, code), count in sorted(counts.items()):
        lines.append(f"{path.ljust(width)} {code} {count}")
    return "\n".join(lines) + "\n"


def compare(current, baseline):
    """Split the difference into regressions and improvements.

    Returns ``(regressions, improvements)`` where each entry is
    ``(path, code, was, now)``.
    """
    regressions = []
    improvements = []
    for (path, code), now in sorted(current.items()):
        was = baseline.get((path, code), 0)
        if now > was:
            regressions.append((path, code, was, now))
    for (path, code), was in sorted(baseline.items()):
        now = current.get((path, code), 0)
        if now < was:
            improvements.append((path, code, was, now))
    return regressions, improvements


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--update",
        action="store_true",
        help="rewrite the baseline from the current findings",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="only report regressions",
    )
    parser.add_argument(
        "targets",
        nargs="*",
        default=list(DEFAULT_TARGETS),
        help=f"paths to lint (default: {' '.join(DEFAULT_TARGETS)})",
    )
    args = parser.parse_args(argv)

    current = count_findings(run_flake8(args.targets))

    if args.update:
        with open(BASELINE_PATH, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(format_baseline(current))
        total = sum(current.values())
        print(
            f"baseline written: {len(current)} entries, {total} findings "
            f"-> {os.path.relpath(BASELINE_PATH, REPO_ROOT)}"
        )
        return 0

    baseline = load_baseline()
    if not baseline:
        print(
            "No baseline yet -- create one with "
            "python scripts/check_flake8_baseline.py --update"
        )
        return 0

    regressions, improvements = compare(current, baseline)

    if improvements and not args.quiet:
        print(f"Improved ({len(improvements)} entries -- refresh the baseline):")
        for path, code, was, now in improvements:
            print(f"  {path} {code}: {was} -> {now}")
        print()

    if regressions:
        print(f"flake8 regressions ({len(regressions)}):")
        for path, code, was, now in regressions:
            if was == 0:
                print(f"  {path} {code}: new ({now})")
            else:
                print(f"  {path} {code}: {was} -> {now}")
        print()
        print(
            "Fix the new findings, or -- if they are deliberate -- re-freeze "
            "with --update."
        )
        return 1

    if not args.quiet:
        total = sum(current.values())
        print(
            f"no regressions ({total} findings across {len(current)} "
            "file/code pairs, at or below baseline)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
