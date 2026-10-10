"""项目模板：新项目从既有项目复制标签集与训练超参。

重点钉住复制的**边界**——什么跟着走（labels/train_prefs/任务预选），
什么刻意不跟（output_dir、续点、split_seed、名字），以及对话框侧的
"选中模板即预选任务"。
"""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from anylabeling.views.labeling import project_model


def _make_project(
    root, *, task="Detect", labels=None, train_prefs=None, output_dir=None
):
    assert project_model.create(root, task=task, labels=labels)
    record = project_model.load_record(root)
    if train_prefs is not None:
        record["train_prefs"] = train_prefs
    if output_dir:
        record["output_dir"] = output_dir
    record["last_file"] = "sub/a.png"
    record["split_seed"] = 12345
    assert project_model.save_record(root, record)


# --- template_record：模板里有什么、没什么 ---------------------------------


def test_template_carries_labels_tuning_and_task(tmp_path):
    source = tmp_path / "plates"
    source.mkdir()
    _make_project(
        str(source),
        task="Segment",
        labels=["划痕", "凹坑"],
        train_prefs={"train": {"epochs": 50}},
    )

    template = project_model.template_record(str(source))
    assert template["task"] == "Segment"
    assert template["labels"] == ["划痕", "凹坑"]
    assert template["train_prefs"] == {"train": {"epochs": 50}}


def test_template_leaves_the_path_bound_fields_behind(tmp_path):
    source = tmp_path / "plates"
    source.mkdir()
    _make_project(
        str(source),
        labels=["划痕"],
        output_dir="/somewhere/else",
    )

    template = project_model.template_record(str(source))
    assert "output_dir" not in template
    assert "last_file" not in template
    assert "split_seed" not in template
    assert "name" not in template


def test_template_of_a_recordless_folder_is_just_the_default_task(tmp_path):
    folder = tmp_path / "plain"
    folder.mkdir()
    template = project_model.template_record(str(folder))
    assert template == {"task": "Detect"}


# --- apply_template：落到新记录上 ------------------------------------------


def test_apply_template_writes_labels_and_tuning(tmp_path):
    target = tmp_path / "screws"
    target.mkdir()
    assert project_model.create(str(target), name="新项目", task="Pose")

    assert project_model.apply_template(
        str(target),
        {
            "task": "Segment",
            "labels": ["划痕"],
            "train_prefs": {"train": {"epochs": 50}},
        },
    )
    record = project_model.load_record(str(target))
    assert record["labels"] == ["划痕"]
    assert record["train_prefs"] == {"train": {"epochs": 50}}
    # 向导写的名字与任务不被模板覆盖：任务由单选按钮决定，不由模板决定。
    assert record["name"] == "新项目"
    assert record["task"] == "Pose"


def test_apply_template_refuses_a_missing_record(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    assert not project_model.apply_template(str(empty), {"labels": ["划痕"]})


def test_apply_template_without_a_template_is_a_noop_success(tmp_path):
    target = tmp_path / "screws"
    target.mkdir()
    assert project_model.create(str(target), task="Pose")
    assert project_model.apply_template(str(target), None)
    assert project_model.load_record(str(target))["task"] == "Pose"


def test_apply_then_describe_round_trip(tmp_path):
    """模板标签写进记录后，describe()（切换器/标题栏的来源）就能看到。"""
    target = tmp_path / "screws"
    target.mkdir()
    project_model.create(str(target), task="Detect")
    project_model.apply_template(str(target), {"labels": ["划痕", "凹坑"]})
    assert project_model.describe(str(target))["labels"] == ["划痕", "凹坑"]


# --- 向导对话框：选中模板即预选任务 ----------------------------------------


def _ensure_qapp():
    """A QApplication that stays alive: the temporary returned by
    ``QApplication([])`` without a reference is garbage collected, and
    the next widget creation is a native crash."""
    from PyQt6 import QtWidgets

    global _QAPP
    if QtWidgets.QApplication.instance() is None:
        _QAPP = QtWidgets.QApplication([])
    return QtWidgets.QApplication.instance()


_QAPP = None


@pytest.mark.parametrize("pick", [0, 1])
def test_dialog_template_combo(pick, tmp_path):
    pytest.importorskip("PyQt6")
    from anylabeling.views.labeling.widgets.project_dialog import (
        ProjectPropertiesDialog,
    )

    _ensure_qapp()

    source = tmp_path / "plates"
    source.mkdir()
    _make_project(str(source), task="Segment", labels=["划痕", "凹坑"])

    dialog = ProjectPropertiesDialog(
        None,
        root=str(tmp_path / "fresh"),
        title="新建项目",
        templates=[
            {
                "root": str(source),
                "name": "plates",
                "task": "Segment",
                "labels": ["划痕", "凹坑"],
            }
        ],
    )
    assert dialog.template_combo is not None
    dialog.template_combo.setCurrentIndex(pick)

    values = dialog.values()
    dialog.deleteLater()
    expected_root = str(source) if pick else None
    assert values["template_root"] == expected_root
    if pick:
        # 选模板即预选任务：界面上立刻可见，创建时随之落盘。
        checked = [
            b.property("task_kind")
            for b in dialog.task_group.buttons()
            if b.isChecked()
        ]
        assert checked == ["Segment"]
        assert values["task"] == "Segment"
    else:
        assert values["task"] == "Detect"


def test_dialog_without_templates_has_no_combo():
    pytest.importorskip("PyQt6")
    from anylabeling.views.labeling.widgets.project_dialog import (
        ProjectPropertiesDialog,
    )

    _ensure_qapp()

    dialog = ProjectPropertiesDialog(None, root="")
    assert dialog.template_combo is None
    assert dialog.values()["template_root"] is None
    dialog.deleteLater()


def test_template_choices_exclude_recordless_and_self(tmp_path, monkeypatch):
    """候选只含真正有清单的项目，目标本身不在列表里。"""
    from anylabeling.views.labeling import project_registry
    from anylabeling.views.labeling.utils import project_view

    real = tmp_path / "real"
    real.mkdir()
    _make_project(str(real), task="Segment", labels=["划痕"])
    opened = tmp_path / "opened"
    opened.mkdir()  # 只被打开过、没有清单：不配当模板

    path = tmp_path / "projects.json"
    monkeypatch.setattr(project_registry, "registry_path", lambda: str(path))
    project_registry.record_project(str(real))
    project_registry.record_project(str(opened))
    project_registry.record_project(str(tmp_path / "vanished"))

    choices = project_view._template_choices(str(real))
    # 目标自己是被排除的：real 有清单但不能当自己的模板；opened 没有
    # 清单，vanished 目录已消失 —— 所以一个候选都不剩。
    assert choices == []

    # 换一个目标，real 就是唯一合格的候选。
    assert project_view._template_choices(str(tmp_path / "fresh")) == [
        {
            "root": str(real),
            "name": "real",
            "task": "Segment",
            "labels": ["划痕"],
        },
    ]
