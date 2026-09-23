"""User-visible text must stay reachable from tr(), or say why it cannot be.

Upstream writes ``tr("English")`` and ships ``zh_CN.ts``; this fork writes
Chinese directly, so the Chinese text *is* the source string. That is a
deliberate choice for a Chinese-only build -- but a bare literal handed straight
to ``setText()`` can never be translated even in principle, so it needs a
reason, and the reason lives in ``EXEMPT`` below.

The catalog check that makes this safe: ``zh_CN.ts`` has no Chinese ``<source>``
entries, so wrapping a Chinese literal in ``tr()`` renders exactly the same
text. It is a mechanism change, not a wording change.
"""

import os
import re
import unittest

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
PACKAGE = os.path.join(REPO_ROOT, "anylabeling")

# The setters Qt shows to the user. Anything in this list must hand over either
# a tr() call or a variable, never a bare Chinese literal.
SETTERS = (
    "setText",
    "setWindowTitle",
    "setToolTip",
    "setStatusTip",
    "setPlaceholderText",
    "setAccessibleName",
    "addItem",
    "setLabel",
    "setTitle",
)
CALL = re.compile(r"\b(" + "|".join(SETTERS) + r")\s*\(\s*")
LITERAL = re.compile(r"([\"'])(.+?)\1", re.S)
CJK = re.compile(r"[\u4e00-\u9fff]")

# (file, reason). Keep this list short and never add to it because a test is
# annoying: a new entry means shipping text that no locale can ever replace.
EXEMPT = {
    "anylabeling/views/labeling/widgets/auto_labeling/auto_labeling.py": (
        "The captions there are written straight in Chinese on purpose: the "
        "panel labels must not depend on the embedded catalog."
    ),
    "anylabeling/app.py": (
        "Startup and crash dialogs may be raised before the translator is "
        "installed, from module scope where no QObject can translate."
    ),
}


def _scan(path):
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    offenders = []
    for match in CALL.finditer(text):
        head = text[match.end() : match.end() + 120]
        literal = LITERAL.match(head)
        if not literal:
            continue
        if CJK.search(literal.group(2)):
            offenders.append(text[: match.start()].count("\n") + 1)
    return offenders


class TestBareUiLiterals(unittest.TestCase):
    def test_no_unexplained_chinese_literals(self):
        found = {}
        for root, dirs, files in os.walk(PACKAGE):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(root, name)
                relative = os.path.relpath(path, REPO_ROOT).replace(
                    os.sep, "/"
                )
                offenders = _scan(path)
                if offenders:
                    found[relative] = offenders
        unexplained = {
            path: lines for path, lines in found.items() if path not in EXEMPT
        }
        self.assertEqual(
            unexplained,
            {},
            "Chinese UI literals handed to a widget without tr() can never be "
            f"translated: {unexplained}. Wrap them in self.tr(...) -- with no "
            "Chinese <source> in zh_CN.ts the visible text does not change.",
        )

    def test_exemptions_are_still_needed(self):
        # An exemption whose reason has evaporated should be deleted, not left
        # to hide whatever gets written there next.
        for relative, reason in EXEMPT.items():
            self.assertTrue(reason, relative)
            offenders = _scan(os.path.join(REPO_ROOT, relative))
            self.assertTrue(
                offenders,
                f"{relative} no longer has bare Chinese literals; drop it from "
                "EXEMPT so the rule keeps its teeth",
            )


if __name__ == "__main__":
    unittest.main()
