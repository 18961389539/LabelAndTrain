"""The backup engine is its own module; the editor must not load the
smart-action stack."""

import ast
from pathlib import Path

from anylabeling.views.labeling.utils import label_backup
from anylabeling.views.labeling.utils import session_snapshot


def test_the_engine_lives_in_label_backup():
    for name in (
        "backup_label_files",
        "list_label_backups",
        "plan_backup_restore",
        "restore_label_backup",
        "is_session_snapshot",
    ):
        assert callable(getattr(label_backup, name))


def test_session_snapshot_does_not_reach_into_the_smart_actions():
    tree = ast.parse(
        Path(session_snapshot.__file__).read_text(encoding="utf-8")
    )
    modules = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    ]
    assert not any(".smart_" in module for module in modules), modules
