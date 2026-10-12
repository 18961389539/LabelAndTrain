"""注册中心满员的淘汰策略：消失的先让位，最旧的其次，谁走要说出来。

registry 只是使用记录（数据永远在项目文件夹里），但一行记录悄悄
消失依旧是"静默"——所以淘汰必须有次序、可观察。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from anylabeling.views.labeling import project_registry


def _make_dirs(tmp_path, count, prefix="p"):
    roots = []
    for i in range(count):
        root = tmp_path / f"{prefix}{i:02d}"
        root.mkdir()
        roots.append(str(root))
    return roots


def _record_all(roots, **kwargs):
    for root in roots:
        assert project_registry.record_project(root, **kwargs)


def _listed_roots():
    return [e["root"] for e in project_registry.load_registry()["projects"]]


def test_overflow_evicts_the_oldest(tmp_path, monkeypatch):
    monkeypatch.setattr(project_registry, "MAX_ENTRIES", 3)
    _record_all(_make_dirs(tmp_path, 3))
    new = tmp_path / "fresh"
    new.mkdir()
    assert project_registry.record_project(str(new))
    roots = _listed_roots()
    assert len(roots) == 3
    assert roots[0] == str(new)  # 新条目在头
    assert str(tmp_path / "p00") not in roots  # 最旧的走了


def test_the_recorded_root_is_never_evicted(tmp_path, monkeypatch):
    monkeypatch.setattr(project_registry, "MAX_ENTRIES", 2)
    _record_all(_make_dirs(tmp_path, 2))
    # 再次记录已在列表里的项目：touch 到头，不淘汰自己
    first = str(tmp_path / "p00")
    assert project_registry.record_project(first)
    roots = _listed_roots()
    assert roots[0] == first
    assert len(roots) == 2


def test_vanished_folders_make_way_before_the_oldest(tmp_path, monkeypatch):
    monkeypatch.setattr(project_registry, "MAX_ENTRIES", 5)
    roots = _make_dirs(tmp_path, 5)
    _record_all(roots)
    # 两个文件夹从盘上消失（移动硬盘拔了 / 数据删了）
    for gone in ("p03", "p04"):
        os.rmdir(tmp_path / gone)
    new = tmp_path / "fresh"
    new.mkdir()
    assert project_registry.record_project(str(new))
    listed = _listed_roots()
    # 消失的让了位，实体条目一个没少，也不用挤最旧的
    assert len(listed) == 4
    assert all(str(tmp_path / "p03") != r for r in listed)
    assert all(str(tmp_path / "p04") != r for r in listed)
    assert str(tmp_path / "p00") in listed  # 最旧的还在
    assert listed[0] == str(new)


def test_under_the_limit_vanished_entries_are_kept(tmp_path, monkeypatch):
    """没满就先不清：盘可能接回来（移动硬盘的常态）。"""
    _record_all(_make_dirs(tmp_path, 3))
    os.rmdir(tmp_path / "p02")
    new = tmp_path / "fresh"
    new.mkdir()
    assert project_registry.record_project(str(new))
    assert str(tmp_path / "p02") in _listed_roots()


def test_callback_hears_about_every_eviction(tmp_path, monkeypatch):
    monkeypatch.setattr(project_registry, "MAX_ENTRIES", 3)
    _record_all(_make_dirs(tmp_path, 3))
    os.rmdir(tmp_path / "p01")
    new = tmp_path / "fresh"
    new.mkdir()
    seen = []
    assert project_registry.record_project(str(new), on_evicted=seen.extend)
    # 只有 p01 消失让位：名额已经够了，最旧的 p00 不用挤
    assert seen == [str(tmp_path / "p01")]
    assert str(tmp_path / "p00") in _listed_roots()


def test_no_eviction_never_calls_the_callback(tmp_path, monkeypatch):
    _record_all(
        _make_dirs(tmp_path, 2),
        on_evicted=lambda roots: (_ for _ in ()).throw(
            AssertionError("called")
        ),
    )
    new = tmp_path / "fresh"
    new.mkdir()
    assert project_registry.record_project(
        str(new),
        on_evicted=lambda roots: (_ for _ in ()).throw(
            AssertionError("called")
        ),
    )
    assert len(_listed_roots()) == 3


def test_a_failing_callback_never_blocks_the_record(tmp_path, monkeypatch):
    monkeypatch.setattr(project_registry, "MAX_ENTRIES", 2)
    _record_all(_make_dirs(tmp_path, 2))
    new = tmp_path / "fresh"
    new.mkdir()

    def _boom(roots):
        raise RuntimeError("status bar is gone")

    assert project_registry.record_project(str(new), on_evicted=_boom)
    assert _listed_roots()[0] == str(new)


def test_record_recent_reports_eviction_in_the_status_bar(
    tmp_path, monkeypatch
):
    """经 project_view.record_recent 的路径：挤掉谁，状态条要说。"""
    from anylabeling.views.labeling.utils import project_view

    monkeypatch.setattr(project_registry, "MAX_ENTRIES", 2)
    _record_all(_make_dirs(tmp_path, 2))
    new = tmp_path / "fresh"
    new.mkdir()
    messages = []

    class _Widget:
        output_dir = None

        def status(self, message, delay=5000):
            messages.append(message)

    assert project_view.record_recent(_Widget(), str(new))
    assert any("已移出列表" in m and "p00" in m for m in messages)
