"""项目内搜索的匹配逻辑：状态与标签名，纯函数、纯盘读。

状态词与文件列表/概览同源（同一个 head 读法）；这里钉住四种状态的
判定、标签子串匹配的大小写规则、以及两个条件叠加时的行为。
"""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from anylabeling.views.labeling.utils import project_search


def _label(root, image, shapes, review_state=None):
    """One image plus its label file in the layout the widget uses."""
    image_file = root / image
    image_file.write_bytes(b"x")
    data = {
        "version": "0.0",
        "shapes": [{"label": lb} for lb in shapes],
    }
    if review_state:
        data["review_state"] = review_state
    (root / (image_file.stem + ".json")).write_text(
        json.dumps(data), encoding="utf-8"
    )
    return str(image_file)


def _project(tmp_path, monkeypatch):
    """A four-image project whose states cover the whole board."""
    root = tmp_path / "plates"
    (root / ".jllabel").mkdir(parents=True)
    files = [
        _label(root, "a.png", ["划痕"], "unchecked"),  # 未复检
        _label(root, "b.png", ["凹坑"], "confirmed"),  # 已确认
        _label(root, "c.png", []),  # 空标注 = 未标注
        str(root / "d.png"),  # 无标注文件 = 未标注
    ]
    (root / "d.png").write_bytes(b"x")
    return root, files


def test_states_match_the_list_and_the_dashboard(tmp_path, monkeypatch):
    root, files = _project(tmp_path, monkeypatch)
    rows = project_search.search_project(root, files=files)
    states = {r["file"]: r["state"] for r in rows}
    assert states[str(root / "a.png")] == "未复检"
    assert states[str(root / "b.png")] == "已确认"
    assert states[str(root / "c.png")] == "未标注"
    assert states[str(root / "d.png")] == "未标注"


def test_state_query_filters(tmp_path, monkeypatch):
    root, files = _project(tmp_path, monkeypatch)
    rows = project_search.search_project(
        root, files=files, state_query="未标注"
    )
    assert {r["file"] for r in rows} == {
        str(root / "c.png"),
        str(root / "d.png"),
    }


def test_label_query_matches_any_shape_case_insensitively(
    tmp_path, monkeypatch
):
    root = tmp_path / "plates"
    (root / ".jllabel").mkdir(parents=True)
    files = [
        _label(root, "a.png", ["Weld"]),
        _label(root, "b.png", ["凹坑", "小划痕"]),
        _label(root, "c.png", ["凹坑"]),
    ]
    rows = project_search.search_project(root, files=files, label_query="weld")
    assert [r["file"] for r in rows] == [str(root / "a.png")]


def test_state_and_label_query_stack(tmp_path, monkeypatch):
    """两个条件是"且"：状态对但标签不对的图也要被排除。"""
    root = tmp_path / "plates"
    (root / ".jllabel").mkdir(parents=True)
    files = [
        _label(root, "a.png", ["划痕"], "confirmed"),
        _label(root, "b.png", ["凹坑"], "confirmed"),
        _label(root, "c.png", ["划痕"], "unchecked"),
    ]
    rows = project_search.search_project(
        root, files=files, label_query="划痕", state_query="已确认"
    )
    assert [r["file"] for r in rows] == [str(root / "a.png")]


def test_a_damaged_label_file_is_data_not_an_error(tmp_path, monkeypatch):
    root, files = _project(tmp_path, monkeypatch)
    (root / "a.json").write_text("{ not json", encoding="utf-8")
    rows = project_search.search_project(
        root, files=files, state_query="未标注"
    )
    assert str(root / "a.png") in {r["file"] for r in rows}


def test_empty_query_means_everything_in_order(tmp_path, monkeypatch):
    root, files = _project(tmp_path, monkeypatch)
    rows = project_search.search_project(root, files=files)
    assert [r["file"] for r in rows] == files
