"""The upstream name must not survive as this build's command or artifact name.

Renaming the fork is only meaningful where a human or another program actually
types the name. Three surfaces are pinned here:

- the console script installed by ``pyproject.toml`` -- there is one entry point,
  ``jllabelingandtrain``, and no ``xanylabeling`` alias, so the docs cannot
  describe a command that a fresh install does not provide;
- the packaged default config, which is the file an unconfigured run reads;
- every ``.py`` / ``.md`` / ``.toml`` / packaging file, where the bare word
  ``xanylabeling`` may not appear as anything anyone should run. In Markdown a
  backticked occurrence is treated as a mention of the name, which is how these
  notes can explain that the alias is gone.

Deliberately *not* covered: ``~/.xanylabelingrc``, ``xanylabeling_data``,
``xanylabeling_logs`` (on-disk locations whose rename needs a migration
decision), ``X-AnyLabeling`` and ``x-anylabeling-cvhub`` (GPL attribution and
upstream's own identifiers), the Python package ``anylabeling`` itself, and the
``X_ANYLABELING_ROOT`` build-time variable shared by the specs and the script
that exports it.
"""

import os
import re
import unittest

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
BARE_NAME = re.compile(r"(?<![\w.\-])xanylabeling(?![\w.\-])")
INLINE_CODE = re.compile(r"`[^`]*`")
SUFFIXES = (".py", ".md", ".toml", ".cfg", ".yaml", ".yml", ".sh", ".bat")
SKIP_DIRS = {".git", "__pycache__", ".venv", "build", "dist"}
# A generated file: rewriting it means re-running rcc, which this checkout
# cannot do (no Qt resource compiler installed).
SKIP_PATHS = {
    "anylabeling/resources/resources.py",
    # This file has to spell the forbidden token to assert on it.
    "tests/test_utils/test_fork_naming.py",
}


def _tracked_text_files():
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if not name.endswith(SUFFIXES):
                continue
            path = os.path.relpath(
                os.path.join(root, name), REPO_ROOT
            ).replace(os.sep, "/")
            if path in SKIP_PATHS:
                continue
            yield path


class TestForkNaming(unittest.TestCase):
    def test_no_bare_upstream_command_name_anywhere(self):
        offenders = {}
        for path in _tracked_text_files():
            with open(
                os.path.join(REPO_ROOT, path), "r", encoding="utf-8"
            ) as handle:
                text = handle.read()
            lines = []
            for number, line in enumerate(text.splitlines(), 1):
                # In Markdown a backticked name is a mention ("there is no
                # `xanylabeling` alias"); anything else -- prose, a shell block,
                # a Python string -- is telling someone to run it.
                haystack = (
                    INLINE_CODE.sub("", line) if path.endswith(".md") else line
                )
                if BARE_NAME.search(haystack):
                    lines.append(number)
            if lines:
                offenders[path] = lines
        self.assertEqual(
            offenders,
            {},
            "the only installed command is jllabelingandtrain; text that "
            f"tells anyone to run xanylabeling is wrong: {offenders}",
        )

    def test_exactly_one_console_script(self):
        pyproject = os.path.join(REPO_ROOT, "pyproject.toml")
        with open(pyproject, "r", encoding="utf-8") as handle:
            section = handle.read().split("[project.scripts]")[1]
        section = section.split("[", 1)[0]
        self.assertIn("jllabelingandtrain", section)
        self.assertNotIn("xanylabeling", section)

    def test_packaged_default_config_is_the_fork_named_file(self):
        config = os.path.join(
            REPO_ROOT, "anylabeling", "configs", "jllabeling_config.yaml"
        )
        self.assertTrue(os.path.isfile(config))
        self.assertFalse(
            os.path.exists(
                os.path.join(
                    REPO_ROOT,
                    "anylabeling",
                    "configs",
                    "xanylabeling_config.yaml",
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
