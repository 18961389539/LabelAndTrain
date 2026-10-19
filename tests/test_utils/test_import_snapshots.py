"""An import that lands on annotated files has to leave the old version behind.

Every ``*_to_custom`` conversion writes its label JSONs into the image folder,
which is where a project's real annotations live -- so re-running 导入 COCO /
VOC / YOLO over an annotated project truncated those files with nothing to
restore, and the CLI does the same to whatever ``--output-dir`` points at. The
GUI's bulk editors and the shape converter already snapshot first; this is the
same rule on the import side.
"""

import json
import os

import pytest

from anylabeling.views.labeling import label_converter as lc
from anylabeling.views.labeling.label_converter import LabelConverter
from anylabeling.views.labeling.utils import session_snapshot


def _coco_document(bbox):
    return {
        "images": [
            {"id": 1, "file_name": "part.png", "width": 100, "height": 80}
        ],
        "categories": [{"id": 1, "name": "scratch"}],
        "annotations": [
            {
                "id": 1,
                "image_id": 1,
                "category_id": 1,
                "bbox": bbox,
                "area": 100,
                # --mode polygon reads this key; a bbox alone is not enough.
                "segmentation": [[10, 20, 40, 20, 40, 60, 10, 60]],
            }
        ],
    }


def _import(tmp_path, document, out_dir):
    source = tmp_path / "annotations.json"
    source.write_text(json.dumps(document), encoding="utf-8")
    LabelConverter(classes=["scratch"]).coco_to_custom(
        str(source), str(out_dir), "polygon"
    )


def _backups(root):
    base = os.path.join(str(root), ".label_backups")
    if not os.path.isdir(base):
        return []
    return [
        os.path.join(base, run, name)
        for run in sorted(os.listdir(base))
        for name in os.listdir(os.path.join(base, run))
        if name.endswith(".json")
    ]


def test_reimporting_over_a_label_file_keeps_the_previous_version(tmp_path):
    out_dir = tmp_path / "labels"
    out_dir.mkdir()
    target = out_dir / "part.json"
    human_work = {
        "version": "2.4.0",
        "flags": {},
        "shapes": [
            {
                "label": "凹坑",
                "points": [[1.0, 2.0], [3.0, 4.0]],
                "group_id": None,
                "shape_type": "rectangle",
                "flags": {},
            }
        ],
        "checked": True,
        "imagePath": "part.png",
    }
    target.write_text(json.dumps(human_work), encoding="utf-8")

    _import(tmp_path, _coco_document([10, 20, 30, 40]), out_dir)

    imported = json.loads(target.read_text(encoding="utf-8"))
    assert [shape["label"] for shape in imported["shapes"]] == ["scratch"]
    assert imported["checked"] is False, "the import replaced the file"

    backups = _backups(out_dir)
    assert len(backups) == 1, backups
    saved = json.loads(open(backups[0], encoding="utf-8").read())
    assert [shape["label"] for shape in saved["shapes"]] == ["凹坑"], (
        "the snapshot must hold what the user had before the import, "
        "recoverable through 智能工具 → 从备份恢复标注"
    )
    assert saved["checked"] is True


def test_a_failing_snapshot_still_lets_the_import_through(
    tmp_path, monkeypatch
):
    out_dir = tmp_path / "labels"
    out_dir.mkdir()
    (out_dir / "part.json").write_text(json.dumps({"shapes": []}), "utf-8")

    def refuse(*_args, **_kwargs):
        raise OSError("read-only backup folder")

    monkeypatch.setattr(session_snapshot.shutil, "copy2", refuse)
    _import(tmp_path, _coco_document([10, 20, 30, 40]), out_dir)

    imported = json.loads((out_dir / "part.json").read_text(encoding="utf-8"))
    assert [shape["label"] for shape in imported["shapes"]] == ["scratch"]
    assert _backups(out_dir) == []


def test_the_plain_writer_stays_unprotected_for_export_artifacts(tmp_path):
    """``custom_to_coco`` writes one aggregate file the user chose a path for;
    snapshotting export artifacts would bury the label snapshots in noise."""
    target = tmp_path / "coco_out.json"
    target.write_text(json.dumps({"images": []}), encoding="utf-8")
    LabelConverter().save_json({"images": [1]}, str(target))
    assert json.loads(target.read_text(encoding="utf-8")) == {"images": [1]}
    assert _backups(tmp_path) == []


def test_every_label_writer_in_the_converter_goes_through_the_helper():
    """A new ``*_to_custom`` branch that forgets the snapshot is the bug."""
    import ast
    import inspect

    source = inspect.getsource(lc)
    tree = ast.parse(source)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.name.endswith("_to_custom"):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "save_json"
            ):
                offenders.append(f"{node.name}:{inner.lineno}")
    assert (
        offenders == []
    ), f"label writers bypassing the snapshot: {offenders}"
