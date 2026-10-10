"""项目包：整目录打包、不解包先看、解包还原（含 zip-slip 防护）。

包的契约来自项目化第一原则——清单随数据走，所以包里什么都不用组装，
``.jllabel/project.json`` 原样进、原样出。这里钉住：包的形状（单顶层
目录）、往返一致性、读不了的输入按"不是包"拒绝、以及恶意归档名必须
**整体拒绝**而不是跳过落盘。
"""

import json
import os
import zipfile

import pytest

from anylabeling.views.labeling import project_bundle, project_model


def _make_project(root, *, task="Segment", labels=("划痕", "凹坑")):
    os.makedirs(os.path.join(root, "images"), exist_ok=True)
    for name in ("a.png", "b.png"):
        with open(os.path.join(root, "images", name), "wb") as handle:
            handle.write(b"fake-image-" + name.encode())
    with open(
        os.path.join(root, "images", "a.json"), "w", encoding="utf-8"
    ) as handle:
        json.dump({"review_state": "confirmed", "shapes": []}, handle)
    assert project_model.create(root, task=task, labels=list(labels))


# --- 导出 -------------------------------------------------------------------


def test_export_packs_the_whole_folder_with_record(tmp_path):
    root = tmp_path / "plates"
    _make_project(str(root))
    target = tmp_path / "plates.zip"

    result = project_bundle.export_bundle(str(root), str(target))

    assert result["files"] == 4  # a.png b.png a.json project.json
    assert result["skipped"] == []
    with zipfile.ZipFile(str(target)) as bundle:
        names = set(bundle.namelist())
    assert "plates/images/a.png" in names
    assert "plates/.jllabel/project.json" in names


def test_export_progress_and_cancel(tmp_path):
    root = tmp_path / "plates"
    _make_project(str(root))
    target = tmp_path / "plates.zip"

    seen = []
    project_bundle.export_bundle(
        str(root),
        str(target),
        progress=lambda done, total, name: seen.append((done, total)),
    )
    assert seen[-1] == (4, 4)

    # 取消后半成品必须被删除：残缺 zip 不能自称项目包。
    result = project_bundle.export_bundle(
        str(root), str(target), cancel=lambda: True
    )
    assert result.get("cancelled") is True
    assert not target.exists()


def test_export_skips_its_own_target(tmp_path):
    """包写到项目文件夹里面时，不能把自己也打进去。"""
    root = tmp_path / "plates"
    _make_project(str(root))
    target = root / "plates.zip"

    result = project_bundle.export_bundle(str(root), str(target))
    assert result["files"] == 4
    with zipfile.ZipFile(str(target)) as bundle:
        assert "plates/plates.zip" not in bundle.namelist()


def test_export_refuses_a_missing_folder(tmp_path):
    with pytest.raises(OSError):
        project_bundle.export_bundle(str(tmp_path / "gone"), "out.zip")


# --- 检查 -------------------------------------------------------------------


def test_inspect_reads_the_record_without_unpacking(tmp_path):
    root = tmp_path / "plates"
    _make_project(str(root), task="Pose", labels=["点1"])
    target = tmp_path / "plates.zip"
    project_bundle.export_bundle(str(root), str(target))

    info = project_bundle.inspect_bundle(str(target))
    assert info["top"] == "plates"
    assert info["record"]["task"] == "Pose"
    assert info["record"]["labels"] == ["点1"]


def test_inspect_rejects_flat_and_multi_top_zips(tmp_path):
    flat = tmp_path / "flat.zip"
    with zipfile.ZipFile(str(flat), "w") as bundle:
        bundle.writestr("loose.txt", b"x")
    assert project_bundle.inspect_bundle(str(flat))["top"] is None

    multi = tmp_path / "multi.zip"
    with zipfile.ZipFile(str(multi), "w") as bundle:
        bundle.writestr("a/x.txt", b"x")
        bundle.writestr("b/y.txt", b"y")
    assert project_bundle.inspect_bundle(str(multi))["top"] is None


def test_inspect_of_a_damaged_zip_is_none(tmp_path):
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"not a zip at all")
    assert project_bundle.inspect_bundle(str(broken)) is None


def test_inspect_reports_recordless_bundles(tmp_path):
    """只打开过、没建清单的文件夹也能打包；导入时由调用方提示。"""
    root = tmp_path / "plain"
    root.mkdir()
    (root / "a.png").write_bytes(b"x")
    target = tmp_path / "plain.zip"
    project_bundle.export_bundle(str(root), str(target))

    info = project_bundle.inspect_bundle(str(target))
    assert info["top"] == "plain"
    assert info["record"] == {}


# --- 导入 -------------------------------------------------------------------


def test_import_round_trips_into_a_real_project(tmp_path):
    root = tmp_path / "plates"
    _make_project(str(root), task="Pose", labels=["点1"])
    target = tmp_path / "plates.zip"
    project_bundle.export_bundle(str(root), str(target))

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    result = project_bundle.import_bundle(str(target), str(elsewhere))

    restored = elsewhere / "plates"
    assert result["root"] == str(restored)
    assert (restored / "images" / "a.png").read_bytes() == b"fake-image-a.png"
    # 解包出来就是一个真项目：describe 全部能答。
    described = project_model.describe(str(restored))
    assert described["has_record"]
    assert described["task"] == "Pose"
    assert described["labels"] == ["点1"]


def test_import_refuses_an_existing_target(tmp_path):
    root = tmp_path / "plates"
    _make_project(str(root))
    target = tmp_path / "plates.zip"
    project_bundle.export_bundle(str(root), str(target))

    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "plates").mkdir(parents=True)
    with pytest.raises(ValueError):
        project_bundle.import_bundle(str(target), str(elsewhere))


def test_import_refuses_zip_slip(tmp_path):
    """越界条目必须整体拒绝：跳过落盘比失败更糟。"""
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(str(evil), "w") as bundle:
        bundle.writestr("plates/.jllabel/project.json", "{}")
        bundle.writestr("plates/../escaped.txt", b"x")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    with pytest.raises(ValueError):
        project_bundle.import_bundle(str(evil), str(elsewhere))
    # 什么都不能留下，尤其是目标之外的东西。
    assert not (elsewhere / "plates").exists()
    assert not (tmp_path / "escaped.txt").exists()


def test_import_cancels_cleanly(tmp_path):
    root = tmp_path / "plates"
    _make_project(str(root))
    target = tmp_path / "plates.zip"
    project_bundle.export_bundle(str(root), str(target))

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    result = project_bundle.import_bundle(
        str(target), str(elsewhere), cancel=lambda: True
    )
    assert result["cancelled"] is True
    assert not (elsewhere / "plates").exists()


# --- 清单摘要 ---------------------------------------------------------------


def test_describe_from_record_tolerates_damage():
    described = project_model.describe_from_record(
        "plates", {"task": "Segment", "name": "钢板"}
    )
    assert described["name"] == "钢板"
    assert described["task"] == "Segment"
    assert described["has_record"]

    fallback = project_model.describe_from_record("plates", None)
    assert fallback["name"] == "plates"
    assert fallback["task"] == "Detect"
    assert not fallback["has_record"]
