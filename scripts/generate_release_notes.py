#!/usr/bin/env python3

import argparse
import re
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CHANGELOG_PATTERN = re.compile(r"^## `([^`]+)`[^\n]*$", re.MULTILINE)


def read_app_info_field(name: str) -> str:
    app_info = ROOT_DIR / "anylabeling" / "app_info.py"
    match = re.search(
        rf'^__{name}__\s*=\s*["\']([^"\']+)["\']',
        app_info.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not match:
        raise ValueError(f"Failed to read __{name}__ from {app_info}")
    return match.group(1)


def read_version() -> str:
    return read_app_info_field("version")


def read_changelog_section(tag: str) -> str:
    changelog_path = ROOT_DIR / "CHANGELOG.md"
    changelog = changelog_path.read_text(encoding="utf-8")
    matches = list(CHANGELOG_PATTERN.finditer(changelog))
    if not matches:
        raise ValueError(f"No release entries found in {changelog_path}")
    if matches[0].group(1) != tag:
        raise ValueError(
            f"Latest changelog version is {matches[0].group(1)}, expected {tag}"
        )
    end = matches[1].start() if len(matches) > 1 else len(changelog)
    section = changelog[matches[0].end() : end].strip()
    if not section:
        raise ValueError(f"Changelog entry for {tag} is empty")
    return section


def find_previous_tag(tag: str):
    """The tag this one follows, or ``None`` for the first release.

    ``git describe`` exits non-zero when no older tag is reachable, which is
    exactly the state of the very first tag on a fork checkout.
    """
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0", f"{tag}^"],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None


def generate_notes(tag: str, repository: str) -> str:
    version = read_version()
    expected_tag = f"v{version}"
    if tag != expected_tag:
        raise ValueError(f"Tag is {tag}, expected {expected_tag}")

    changelog = read_changelog_section(tag)
    previous_tag = find_previous_tag(tag)
    lines = [
        "> [!NOTE]\n"
        "> Fork build of "
        f"[{read_app_info_field('upstream_name')}]({read_app_info_field('url')})"
        f" at upstream {read_app_info_field('upstream_version')}; the "
        "interface is Simplified Chinese only, and the binaries here are not "
        "the upstream PyPI releases.\n"
        "> If a prebuilt package does not run on your machine, build from "
        "source following the installation guide.\n\n"
        f"{changelog}\n"
    ]
    if previous_tag:
        lines.append(
            f"\n**Full Changelog**: "
            f"https://github.com/{repository}/compare/"
            f"{previous_tag}...{tag}\n"
        )
    return "".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    notes = generate_notes(args.tag, args.repository)
    args.output.write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    main()
