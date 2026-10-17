"""A ratchet against English leaking into the Chinese UI.

The fork's source text is Chinese, so an untranslated English literal is
visible exactly where the user is looking at it: a tooltip in the auto-
labeling panel, a `From:` label beside a spin box, the button that starts
training. Nothing checked for it -- ``test_fork_ui_strings`` guards the
*reverse* problem (bare Chinese that cannot be translated), so English
literals were invisible to the gates.

The list below is the residue: values that are not UI copy at all. It is a
baseline in the style of ``scripts/flake8_baseline.txt`` -- it may only
shrink, and the test says so when it could.
"""

import ast
import os
import re
import unittest

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
PACKAGE = os.path.join(REPO_ROOT, "anylabeling")

#: Setters Qt shows to the user, plus the widget constructors that take a
#: caption as their first argument.
SETTERS = {
    "setText",
    "setWindowTitle",
    "setToolTip",
    "setStatusTip",
    "setPlaceholderText",
    "setAccessibleName",
    "setWhatsThis",
    "addItem",
    "setLabel",
    "setTitle",
}
CONSTRUCTORS = {
    "QLabel",
    "QCheckBox",
    "QPushButton",
    "QToolButton",
    "QAction",
    "QGroupBox",
    "QRadioButton",
}

#: (file, literal) pairs that are allowed to stay ASCII -- none of them is
#: translatable copy. Prune an entry when its reason goes away.
ALLOWED = {
    # A zoom percentage shown as a number, not a sentence.
    ("views/labeling/widgets/navigator_widget.py", "100"),
    # Ultralytics run name / a confidence threshold: both are values the
    # training command carries, and translating them would break them.
    ("views/training/ultralytics_dialog.py", "exp"),
    ("views/training/ultralytics_dialog.py", "0.8"),
}

CJK = re.compile(r"[一-鿿]")
SKIP_DIRS = {"__pycache__"}


def _is_caption(node):
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and bool(node.value.strip())
        and not CJK.search(node.value)
        and not node.value.startswith(
            ("%", "<", "http", "/", "./", "C:", "f:")
        )
        and len(node.value.strip()) > 2
    )


def _scan():
    found = []
    for base, dirs, files in os.walk(PACKAGE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if not name.endswith(".py") or name == "resources.py":
                continue
            path = os.path.join(base, name)
            rel = os.path.relpath(path, PACKAGE).replace("\\", "/")
            try:
                tree = ast.parse(open(path, encoding="utf-8").read(), path)
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                callee = getattr(node.func, "attr", None) or getattr(
                    node.func, "id", None
                )
                if callee not in SETTERS | CONSTRUCTORS:
                    continue
                if _is_caption(node.args[0]):
                    found.append((rel, node.args[0].value.strip()))
    return found


class TestNoEnglishUICopy(unittest.TestCase):
    def test_only_baselined_literals_are_english(self):
        offenders = sorted(set(_scan()) - ALLOWED)
        self.assertEqual(
            offenders,
            [],
            f"{len(offenders)} user-visible literal(s) are English text in a "
            "Chinese-only UI. Write them in Chinese (the fork's source "
            "language) and, inside a class, wrap them in self.tr(...) so "
            "they reach zh_CN.ts: "
            + "; ".join(f"{f}: {t!r}" for f, t in offenders[:6]),
        )

    def test_the_baseline_is_not_stale(self):
        live = set(_scan())
        stale = sorted(ALLOWED - live)
        self.assertEqual(
            stale,
            [],
            "these entries no longer exist in the source -- delete them from "
            "ALLOWED so the ratchet keeps shrinking: "
            + ", ".join(f"{f}: {t!r}" for f, t in stale),
        )


if __name__ == "__main__":
    unittest.main()
