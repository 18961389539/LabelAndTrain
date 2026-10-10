"""项目界面层：项目名、标题前缀、最近项目合并、关闭项目。

只测纯逻辑（不启动 Qt 窗口）：项目身份是目录路径，本模块的价值在于
把两套最近记录合成一套，所以这里重点是"合并"和"迁移"的边界。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from anylabeling.views.labeling import project_registry
from anylabeling.views.labeling.utils import project_view


@pytest.fixture()
def registry_file(tmp_path, monkeypatch):
    """把项目注册表重定向到临时文件（与 test_project_settings 一致）。"""
    path = tmp_path / "projects.json"
    monkeypatch.setattr(project_registry, "registry_path", lambda: str(path))
    return path


class FakeSettings:
    """最小 QSettings 替身：project_view 只用到 value / remove。"""

    def __init__(self, legacy=None):
        self.store = {}
        if legacy is not None:
            self.store[project_view.LEGACY_RECENT_KEY] = list(legacy)

    def value(self, key, default=None):
        return self.store.get(key, default)

    def remove(self, key):
        self.store.pop(key, None)


class FakeWidget:
    """只带 project_view 会读的字段，不启动 Qt。"""

    def __init__(self, settings=None, root=None, filename=None):
        self.settings = settings
        self._project_dataset_dir = root
        self.filename = filename
        self.last_open_dir = None
        self.output_dir = None


# --- 项目身份 -------------------------------------------------------------


def test_project_name_is_the_folder_name(tmp_path):
    root = tmp_path / "人脸检测"
    root.mkdir()
    assert project_view.project_name(str(root)) == "人脸检测"
    assert project_view.project_name(None) == ""
    assert project_view.project_name("") == ""


def test_current_root_prefers_the_dataset_dir(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    widget = FakeWidget(root=str(root), filename=str(other / "a.png"))
    assert project_view.current_root(widget) == str(root)


def test_current_root_falls_back_to_the_image_folder(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    widget = FakeWidget(filename=str(root / "a.jpg"))
    assert project_view.current_root(widget) == str(root)


def test_current_root_ignores_last_open_dir(tmp_path):
    """关闭项目后 last_open_dir 仍然在，不能据此说项目还开着。"""
    root = tmp_path / "proj"
    root.mkdir()
    widget = FakeWidget()
    widget.last_open_dir = str(root)
    assert project_view.current_root(widget) is None


def test_title_prefix_is_empty_without_a_project(tmp_path):
    assert project_view.title_project_prefix(FakeWidget()) == ""
    root = tmp_path / "proj"
    root.mkdir()
    assert project_view.title_project_prefix(FakeWidget(root=str(root))) == (
        "[proj] "
    )


# --- 最近项目：两套记录合成一套 -------------------------------------------


def test_recent_dirs_reads_the_registry(registry_file, tmp_path):
    a = tmp_path / "a"
    a.mkdir()
    project_registry.record_project(str(a))
    widget = FakeWidget(settings=FakeSettings())
    assert project_view.recent_dirs(widget) == [str(a)]


def test_recent_dirs_migrates_the_legacy_qsettings_list(
    registry_file, tmp_path
):
    """老键里的目录被补进 registry，随后老键被清掉。"""
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    settings = FakeSettings(legacy=[str(legacy)])
    widget = FakeWidget(settings=settings)

    assert project_view.recent_dirs(widget) == [str(legacy)]
    assert settings.store == {}
    assert [e["root"] for e in project_registry.recent_projects()] == [
        str(legacy)
    ]


def test_recent_dirs_does_not_duplicate_a_recorded_dir(
    registry_file, tmp_path
):
    a = tmp_path / "a"
    a.mkdir()
    project_registry.record_project(str(a))
    settings = FakeSettings(legacy=[str(a)])
    widget = FakeWidget(settings=settings)

    assert project_view.recent_dirs(widget) == [str(a)]
    # 已经在 registry 里了，所以只清键、不重复记录，顺序也不被打乱。
    assert settings.store == {}
    assert [e["root"] for e in project_registry.recent_projects()] == [str(a)]


def test_recent_dirs_drops_the_legacy_key_when_every_path_is_gone(
    registry_file, tmp_path
):
    settings = FakeSettings(legacy=[str(tmp_path / "ghost")])
    widget = FakeWidget(settings=settings)
    assert project_view.recent_dirs(widget) == []
    assert settings.store == {}


def test_recent_dirs_survives_a_broken_settings_store(registry_file, tmp_path):
    class Broken:
        def value(self, key, default=None):
            raise OSError("unreadable")

        def remove(self, key):
            raise OSError("unreadable")

    assert project_view.recent_dirs(FakeWidget(settings=Broken())) == []


def test_recent_dirs_keeps_working_without_a_settings_object(registry_file):
    assert project_view.recent_dirs(FakeWidget()) == []


def test_recent_limit_is_applied(registry_file, tmp_path):
    for index in range(4):
        folder = tmp_path / f"p{index}"
        folder.mkdir()
        project_registry.record_project(str(folder))
    widget = FakeWidget(settings=FakeSettings())
    assert project_view.recent_dirs(widget, limit=2) == [
        str(tmp_path / "p3"),
        str(tmp_path / "p2"),
    ]


def test_record_recent_rejects_an_empty_path(registry_file):
    widget = FakeWidget(settings=FakeSettings())
    assert project_view.record_recent(widget, "") is False


def test_record_recent_remembers_the_output_dir(registry_file, tmp_path):
    root = tmp_path / "a"
    root.mkdir()
    widget = FakeWidget(settings=FakeSettings())
    widget.output_dir = str(tmp_path / "labels")
    assert project_view.record_recent(widget, str(root)) is True
    assert project_registry.recent_projects()[0]["label_dir"] == str(
        tmp_path / "labels"
    )
