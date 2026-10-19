"""导出参数快照跟着项目走：白名单、覆盖、无记录即拒绝。

"自动导出"在这批里落成"第二次导出零配置"：上次成功导出的参数
存进项目记录，对话框预填，用户只剩确认。这里钉住记录层。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from anylabeling.views.labeling import project_model


def _project(tmp_path):
    root = tmp_path / "plates"
    root.mkdir()
    assert project_model.create(str(root), task="Segment", labels=["划痕"])
    return str(root)


def test_remember_export_stores_whitelist_keys(tmp_path):
    root = _project(tmp_path)
    assert project_model.remember_export(
        root,
        {
            "save_path": "G:/out/labels",
            "save_images": True,
            "skip_empty": False,
            "obb_boundary": "clamp",
            "only_confirmed": True,
            "write_classes": True,
            "manifest": True,
            "mode": "yolo",
            "classes": ["划痕", "凹坑"],  # 不在白名单：丢弃
            "stats": {"exported": 12},  # 同上
        },
    )
    snapshot = project_model.last_export(root)
    assert snapshot["save_path"] == "G:/out/labels"
    assert snapshot["only_confirmed"] is True
    assert snapshot["obb_boundary"] == "clamp"
    assert snapshot["mode"] == "yolo"
    assert "classes" not in snapshot
    assert "stats" not in snapshot


def test_last_export_of_a_folder_without_record_is_empty(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    assert project_model.last_export(str(root)) == {}


def test_remember_export_refuses_a_folder_without_record(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    assert not project_model.remember_export(str(root), {"save_path": "G:/x"})


def test_a_new_snapshot_overwrites_the_previous_one(tmp_path):
    root = _project(tmp_path)
    assert project_model.remember_export(root, {"save_path": "G:/old"})
    assert project_model.remember_export(
        root, {"save_path": "G:/new", "only_confirmed": True}
    )
    snapshot = project_model.last_export(root)
    assert snapshot["save_path"] == "G:/new"
    assert snapshot["only_confirmed"] is True


def test_a_damaged_snapshot_reads_as_empty(tmp_path):
    root = _project(tmp_path)
    record = project_model.load_record(root)
    record["last_export"] = "不是字典"
    assert project_model.save_record(root, record)
    assert project_model.last_export(root) == {}
