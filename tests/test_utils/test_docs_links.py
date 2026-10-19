"""Every relative link in the documentation has to resolve in this repository.

478 of them did not. `model_zoo.md` and `custom_model.md` still linked the
~90 upstream auto-labeling config files and service modules this fork deleted,
so the two pages a new reader follows into "which model do I load" pointed at
nothing at all. The fix re-pointed the links that describe *upstream* at
upstream; this test is what keeps a local path from being written down again
without the file behind it.
"""

import io
import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
RELATIVE_LINK = re.compile(r"\]\((?!https?:|#|mailto:)([^)\s]+)")


def resolves_with_exact_case(path, target):
    """True when every component of the relative link matches on disk.

    ``Path.exists()`` is case-insensitive on Windows and macOS, so a link to
    ``assets/annotations`` passed there while Linux CI failed on
    ``assets/Annotations`` -- the same class of bug the Windows machine cannot
    see without this walk.
    """
    current = path.parent
    for part in target.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            current = current.parent
            continue
        try:
            names = os.listdir(current)
        except OSError:
            return False
        if part not in names:
            return False
        current = current / part
    return current.exists()


def doc_files():
    paths = sorted((REPO / "docs").rglob("*.md"))
    for name in ("README.md", "README_zh-CN.md"):
        candidate = REPO / name
        if candidate.is_file():
            paths.append(candidate)
    return paths


def test_the_case_check_is_exact_not_just_existing():
    """Windows answers True to the lowercase spelling; this walk must not."""
    page = REPO / "docs" / "zh_cn" / "page.md"
    assert resolves_with_exact_case(page, "../../assets/Annotations")
    assert not resolves_with_exact_case(page, "../../assets/annotations")


def test_the_guard_itself_has_something_to_check():
    """An empty file list would make every parametrized case pass vacuously."""
    assert len(doc_files()) >= 20, doc_files()


@pytest.mark.parametrize(
    "path", doc_files(), ids=lambda p: str(p.relative_to(REPO))
)
def test_relative_links_resolve(path):
    text = io.open(path, encoding="utf-8", errors="replace").read()
    broken = []
    for match in RELATIVE_LINK.finditer(text):
        target = match.group(1).split("#")[0]
        if target and (
            not (path.parent / target).resolve().exists()
            or not resolves_with_exact_case(path, target)
        ):
            broken.append(match.group(1))
    assert not broken, (
        f"{path.relative_to(REPO)}: {len(broken)} broken relative link(s), "
        f"e.g. {broken[:3]}. Write the real path, or link upstream explicitly "
        f"-- a relative link is a claim that this repository has the file."
    )


def test_upstream_only_pages_say_so():
    """The archived pages must keep the banner that makes them honest."""
    for name in ("docs/zh_cn/model_zoo.md", "docs/en/model_zoo.md"):
        text = io.open(REPO / name, encoding="utf-8", errors="replace").read()
        head = text[:600]
        assert "上游" in head or "upstream" in head.lower(), (
            f"{name} describes models this build cannot load; it has to say so "
            f"in its first lines."
        )
