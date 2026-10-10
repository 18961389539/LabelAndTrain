"""项目身份层：名字、任务类型、清单的创建与 schema 迁移。

重点在两条边界：老记录（schema 1）读出来必须补齐字段但**不动文件**，
以及 create 拒绝覆盖已有清单 —— 后者是"新建项目"不会抹掉别人的设置
的唯一保证。
"""

import json
import os
import os.path as osp

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from anylabeling.views.labeling import project, project_model

PROJECT_FILE = osp.join(project.PROJECT_DIR_NAME, project.PROJECT_FILE_NAME)


def _write_record(root, payload):
    """手写一份项目清单，返回它的路径（用来造老版本的文件）。"""
    directory = osp.join(str(root), project.PROJECT_DIR_NAME)
    os.makedirs(directory, exist_ok=True)
    path = osp.join(directory, project.PROJECT_FILE_NAME)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    return path


def _write_schema1(root):
    """一份 schema 1 的老记录：只有 labels / output_dir / split_seed。"""
    return _write_record(
        root, {"schema": 1, "labels": ["cat", "dog"], "split_seed": 7}
    )


# --- 任务类型 ---------------------------------------------------------------


def test_task_types_match_the_training_side():
    """标注侧刻意不 import 训练包，所以两个集合靠这条断言锁在一起。"""
    from anylabeling.services.auto_training.ultralytics.config import (
        TASK_TYPES as TRAINING_TASK_TYPES,
    )

    assert set(project.TASK_TYPES) == set(TRAINING_TASK_TYPES)


def test_every_task_type_has_a_label_and_a_hint():
    for task in project.TASK_TYPES:
        assert project_model.task_label(task)
        assert project_model.task_hint(task)
    assert project_model.task_label("Detect") == "目标检测"


def test_task_label_keeps_an_unknown_kind():
    assert project_model.task_label("Whatever") == "Whatever"
    assert project_model.task_label(None) == ""


def test_normalize_task_folds_case_and_falls_back():
    assert project_model.normalize_task("segment") == "Segment"
    assert project_model.normalize_task("POSE") == "Pose"
    assert project_model.normalize_task("nope") == project.DEFAULT_TASK
    assert project_model.normalize_task(None) == project.DEFAULT_TASK
    assert project_model.normalize_task("") == project.DEFAULT_TASK


# --- 项目名 -----------------------------------------------------------------


def test_normalize_name_collapses_whitespace_and_falls_back(tmp_path):
    root = tmp_path / "螺丝划痕"
    root.mkdir()
    assert project_model.normalize_name("  螺丝\n划痕  ", str(root)) == (
        "螺丝 划痕"
    )
    assert project_model.normalize_name("", str(root)) == "螺丝划痕"
    assert project_model.normalize_name("   ", str(root)) == "螺丝划痕"
    assert project_model.normalize_name(None, str(root)) == "螺丝划痕"


def test_normalize_name_truncates_instead_of_refusing(tmp_path):
    long_name = "x" * (project_model.NAME_MAX_LENGTH + 40)
    cleaned = project_model.normalize_name(long_name, str(tmp_path))
    assert len(cleaned) == project_model.NAME_MAX_LENGTH


def test_default_name_is_the_folder_name(tmp_path):
    root = tmp_path / "plates"
    root.mkdir()
    assert project_model.default_name(str(root)) == "plates"
    assert project_model.default_name(None) == ""


# --- 新建 -------------------------------------------------------------------


def test_new_record_carries_the_schema_2_fields(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    record = project_model.new_record(
        str(root), name=" 螺丝 ", task="segment", now="2026-10-10 09:00:00"
    )
    assert record["schema"] == project.SCHEMA
    assert record["name"] == "螺丝"
    assert record["task"] == "Segment"
    assert record["created_at"] == "2026-10-10 09:00:00"
    assert "labels" not in record
    assert "output_dir" not in record


def test_new_record_keeps_labels_and_output_dir_when_given(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    record = project_model.new_record(
        str(root),
        labels=["a", "", "b"],
        output_dir=str(tmp_path / "labels"),
    )
    assert record["labels"] == ["a", "b"]
    assert record["output_dir"] == str(tmp_path / "labels")


def test_create_writes_the_record_and_refuses_to_overwrite(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    assert project_model.create(str(root), name="甲", task="Pose") is True
    assert project_model.has_record(str(root)) is True
    # 第二遍拒绝覆盖：那是别人攒下来的设置。
    assert project_model.create(str(root), name="乙") is False
    assert project_model.describe(str(root))["name"] == "甲"


def test_create_refuses_a_missing_folder(tmp_path):
    ghost = str(tmp_path / "ghost")
    assert project_model.create(ghost) is False
    assert project_model.has_record(ghost) is False


def test_has_record_is_not_the_same_as_the_folder_existing(tmp_path):
    root = tmp_path / "只是打开过"
    root.mkdir()
    assert project_model.has_record(str(root)) is False
    assert project_model.describe(str(root))["has_record"] is False


# --- 改名与改任务 -----------------------------------------------------------


def test_rename_and_set_task_keep_the_folder_untouched(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    project_model.create(str(root), name="甲", task="Detect")

    assert project_model.rename(str(root), "乙") is True
    assert project_model.set_task(str(root), "segment") is True

    described = project_model.describe(str(root))
    assert described["name"] == "乙"
    assert described["task"] == "Segment"
    # 名字只是标签：目录没有跟着改。
    assert osp.basename(described["root"]) == "proj"
    assert osp.isdir(str(root))


def test_rename_and_set_task_without_a_record_change_nothing(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    assert project_model.rename(str(root), "乙") is False
    assert project_model.set_task(str(root), "Pose") is False
    assert project_model.has_record(str(root)) is False


def test_describe_falls_back_for_a_plain_folder(tmp_path):
    root = tmp_path / "只用过的文件夹"
    root.mkdir()
    described = project_model.describe(str(root))
    assert described["name"] == "只用过的文件夹"
    assert described["task"] == project.DEFAULT_TASK
    assert described["has_record"] is False
    assert described["created_at"] == ""
    assert described["labels"] == []


# --- schema 1 → 2 -----------------------------------------------------------


def test_schema_1_record_is_completed_in_memory_only(tmp_path):
    """老记录读出来补齐字段，但文件一个字节都不动（浏览即只读）。"""
    root = tmp_path / "老项目"
    root.mkdir()
    path = _write_schema1(root)
    with open(path, "rb") as handle:
        before = handle.read()

    record = project.load_project(str(root))

    assert record["name"] == "老项目"
    assert record["task"] == project.DEFAULT_TASK
    assert record["created_at"]
    assert record["schema"] == project.SCHEMA
    # 原有字段原样保留
    assert record["labels"] == ["cat", "dog"]
    assert record["split_seed"] == 7
    with open(path, "rb") as handle:
        assert handle.read() == before


def test_schema_1_record_is_upgraded_on_the_next_save(tmp_path):
    root = tmp_path / "老项目"
    root.mkdir()
    path = _write_schema1(root)

    record = project.load_project(str(root))
    assert project.save_project(str(root), record) is True

    with open(path, encoding="utf-8") as handle:
        on_disk = json.load(handle)
    assert on_disk["schema"] == project.SCHEMA
    assert on_disk["name"] == "老项目"
    assert on_disk["task"] == project.DEFAULT_TASK
    assert on_disk["split_seed"] == 7


def test_an_existing_name_survives_the_migration(tmp_path):
    root = tmp_path / "目录名"
    root.mkdir()
    _write_record(root, {"schema": 1, "name": "改过的名字"})
    assert project.load_project(str(root))["name"] == "改过的名字"


def test_an_unknown_task_falls_back_to_the_default(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _write_record(root, {"schema": 2, "task": "OBB"})
    assert project.load_project(str(root))["task"] == project.DEFAULT_TASK


def test_an_empty_name_falls_back_to_the_folder(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    _write_record(root, {"schema": 2, "name": "   "})
    assert project.load_project(str(root))["name"] == "proj"


def test_split_seed_still_round_trips_through_schema_2(tmp_path):
    """升级不该碰划分种子 —— 它决定了两次训练能不能对比。"""
    root = tmp_path / "proj"
    root.mkdir()
    seed, created = project.get_or_create_split_seed(str(root))
    assert created is True
    assert project.load_project(str(root))["split_seed"] == seed
    again, created_again = project.get_or_create_split_seed(str(root))
    assert (again, created_again) == (seed, False)
