"""Every function that rewrites a label JSON has to snapshot it first.

This fork has now fixed the same defect five times in five places: bulk
auto-label, the COCO/VOC/YOLO imports, the missed-label scan, template
propagation, class rename, and the two range editors in 形状管理器/标签管理器.
Each was a loop that wrote `shapes` over a folder's files with no undo, and
each was found by asking a different question. This test asks it once, for
everywhere: if a function opens a label file for writing, it must call
``snapshot_before_label_write()`` -- or be listed below with a reason.
"""

import ast
import io
import os

REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
ROOT = os.path.join(REPO, "anylabeling", "views", "labeling")

#: Functions the scan flags that write a label-shaped JSON without
#: snapshotting, and why that is correct. A new entry needs a reason; a stale
#: one fails too -- which is how the two "obvious" exemptions below turned out
#: to be functions the scan never matches (they write text and marker files,
#: not `json.dump`).
EXEMPT = {
    # 导入 YOLO merges the imported shapes with the ones it read back. The
    # converter already copied that file's pre-import state in this same run,
    # so a second copy of import output buries the undo point in noise.
    "anylabeling/views/labeling/utils/upload.py::upload_yolo_annotation": (
        "merge after import; the converter snapshotted pre-import state"
    ),
}

LABEL_TOKENS = (
    "label_file",
    "json_path",
    "output_file",
    "label_path",
    ".json",
)


def _snapshots_a_label(node):
    """Does this function actually *call* the snapshot helper?

    A substring test on the source is not enough: the import statement names
    the helper too, so a function that imports it and forgets to call it would
    pass. That is the bug this scan exists to catch, and it passed once.
    """
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        name = getattr(inner.func, "attr", None) or getattr(
            inner.func, "id", None
        )
        if name == "snapshot_before_label_write":
            return True
    return False


def _writer_functions():
    """[(path, func, has_snapshot)] for functions that rewrite label JSONs."""
    found = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            src = io.open(path, encoding="utf-8").read()
            tree = ast.parse(src)
            relative = os.path.relpath(path, REPO).replace(os.sep, "/")
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                body = ast.get_source_segment(src, node) or ""
                if "json.dump(" not in body:
                    continue
                if not any(token in body for token in LABEL_TOKENS):
                    continue
                if "open(" not in body or '"w"' not in body:
                    continue
                found.append(
                    (
                        f"{relative}::{node.name}",
                        node,
                        _snapshots_a_label(node),
                    )
                )
    return found


def test_the_scan_finds_the_writers_this_fork_fixed():
    """A scan that matches nothing would pass every later assertion."""
    keys = {key for key, _node, _snap in _writer_functions()}
    for expected in (
        "anylabeling/views/labeling/utils/batch.py::save_auto_labeling_result",
        "anylabeling/views/labeling/utils/yolo_detect.py::rename_label_across_folder",
        "anylabeling/views/labeling/widgets/shape_dialog.py::remove_selected_shapes_in_range",
        "anylabeling/views/labeling/widgets/label_dialog.py::modify_group_id",
    ):
        assert expected in keys, f"the scan no longer covers {expected}"


def test_every_label_writer_snapshots_before_it_rewrites():
    offenders = [
        key
        for key, _node, snapshotted in _writer_functions()
        if not snapshotted and key not in EXEMPT
    ]
    assert offenders == [], (
        f"{len(offenders)} label writer(s) rewrite files with no undo point: "
        f"{offenders}. Call snapshot_before_label_write() before the write, or "
        f"add an exemption with a reason."
    )


def test_no_exemption_is_still_carried_without_a_reason():
    keys = {key for key, _node, _snap in _writer_functions()}
    stale = sorted(set(EXEMPT) - keys)
    assert stale == [], f"exemption(s) no longer needed, drop them: {stale}"
