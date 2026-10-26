"""The shared result dialog and task thread live in smart_ui."""

import ast
from pathlib import Path

from anylabeling.views.labeling.utils import smart_ui


def test_the_dialog_lives_in_smart_ui():
    assert (
        smart_ui._ResultDialog.__module__
        == "anylabeling.views.labeling.utils.smart_ui"
    )


def test_smart_ui_does_not_import_the_action_module():
    tree = ast.parse(Path(smart_ui.__file__).read_text(encoding="utf-8"))
    modules = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    ]
    assert not any(".smart_" in module for module in modules), modules
