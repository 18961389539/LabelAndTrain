"""项目续点：每个项目记住自己看到哪张图。

改造前只有一个全局的"最后一张"（QSettings ``filename``），切一次项目
就把它顶掉了；这里钉住的是"项目自己的位置"这条路径 —— 写在哪、怎么
解析、什么时候落回默认行为。
"""

import os
import os.path as osp

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from anylabeling.views.labeling import project_settings
from anylabeling.views.labeling.utils import file_lifecycle, project_view


class FakeSettings:
    """最小 QSettings 替身：只要 value。"""

    def __init__(self, values=None):
        self.store = dict(values or {})

    def value(self, key, default=None):
        return self.store.get(key, default)


class FakeWidget:
    """够续点逻辑用的替身（不启动 Qt）。"""

    def __init__(self, root=None, filename=None):
        self._project_dataset_dir = root
        self._project_resume_file = None
        self._image_list = []
        self.filename = filename
        self.settings = FakeSettings()
        self.loaded = []
        self.next_calls = 0
        self.statuses = []

    @property
    def image_list(self):
        return list(self._image_list)

    def load_file(self, filename):
        self.loaded.append(filename)
        return True

    def open_next_image(self, load=True):
        self.next_calls += 1

    def _refresh_file_panel(self):
        pass

    def status(self, message, timeout=0):
        self.statuses.append(message)


def _make_image(root, name):
    path = osp.join(str(root), name)
    with open(path, "wb") as handle:
        handle.write(b"x")
    return path


# --- 写下来 ---------------------------------------------------------------


def test_save_last_file_stores_a_project_relative_path(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    image = _make_image(root, "b.png")
    widget = FakeWidget(root=str(root), filename=image)

    assert project_settings.save_last_file(widget, str(root)) is True
    assert project_settings.load_settings(str(root))["last_file"] == "b.png"


def test_save_last_file_skips_an_unchanged_position(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    image = _make_image(root, "b.png")
    widget = FakeWidget(root=str(root), filename=image)

    assert project_settings.save_last_file(widget, str(root)) is True
    # 第二次没有变化：不写盘（离开路径会被调用很多次）。
    assert project_settings.save_last_file(widget, str(root)) is False


def test_save_last_file_ignores_a_vanished_image(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    widget = FakeWidget(
        root=str(root), filename=osp.join(str(root), "ghost.png")
    )
    assert project_settings.save_last_file(widget, str(root)) is False
    assert "last_file" not in project_settings.load_settings(str(root))


def test_save_last_file_without_a_filename_does_nothing(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    widget = FakeWidget(root=str(root), filename=None)
    assert project_settings.save_last_file(widget, str(root)) is False


# --- 读回来 ---------------------------------------------------------------


def test_remembered_file_resolves_relative_and_absolute(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    inside = _make_image(root, "a.png")
    outside = _make_image(elsewhere, "b.png")

    widget = FakeWidget(root=str(root), filename=inside)
    project_settings.save_last_file(widget, str(root))
    assert project_settings.remembered_file(str(root)) == inside

    # 项目之外的图片（例如单独浏览的输出目录）只能记绝对路径。
    widget.filename = outside
    project_settings.save_last_file(widget, str(root))
    record = project_settings.load_settings(str(root))
    assert osp.isabs(record["last_file"])
    assert project_settings.remembered_file(str(root)) == outside


def test_remembered_file_disappears_with_the_image(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    image = _make_image(root, "a.png")
    widget = FakeWidget(root=str(root), filename=image)
    project_settings.save_last_file(widget, str(root))

    os.remove(image)
    assert project_settings.remembered_file(str(root)) is None
    # 记录本身留着：盘接回来或文件改名回来，位置还在。
    assert project_settings.load_settings(str(root))["last_file"] == "a.png"


def test_remembered_file_without_a_record_is_none(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    assert project_settings.remembered_file(str(root)) is None
    assert project_settings.remembered_file(None) is None


# --- 离开时写、进入时读 ---------------------------------------------------


def test_flush_writes_both_labels_and_position(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    image = _make_image(root, "a.png")

    class PanelWidget(FakeWidget):
        def _panel_label_names(self):
            return ["cat"]

    widget = PanelWidget(root=str(root), filename=image)
    project_settings.flush_open_project(widget)

    record = project_settings.load_settings(str(root))
    assert record["labels"] == ["cat"]
    assert record["last_file"] == "a.png"


def test_begin_project_switch_reads_the_resume_target(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    image = _make_image(root, "a.png")
    project_settings.save_last_file(
        FakeWidget(root=str(root), filename=image), str(root)
    )

    widget = FakeWidget()
    project_settings.begin_project_switch(widget, str(root))

    assert widget._project_dataset_dir == str(root)
    assert widget._project_resume_file == image


def test_begin_project_switch_leaves_no_target_without_a_record(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    widget = FakeWidget()
    project_settings.begin_project_switch(widget, str(root))
    assert widget._project_resume_file is None


# --- 导入时消费 -----------------------------------------------------------


def test_resume_opens_the_remembered_image(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    image = _make_image(root, "a.png")
    widget = FakeWidget(root=str(root))
    widget._image_list = [osp.join(str(root), "z.png"), image]
    widget._project_resume_file = image

    assert file_lifecycle._resume_remembered_file(widget) is True
    assert widget.loaded == [image]
    # 消费掉：同一次导入不会重复回到那张图。
    assert widget._project_resume_file is None


def test_resume_falls_through_when_the_image_is_gone(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    widget = FakeWidget(root=str(root))
    widget._image_list = []
    widget._project_resume_file = osp.join(str(root), "ghost.png")

    assert file_lifecycle._resume_remembered_file(widget) is False
    assert widget.loaded == []


def test_resume_without_a_target_is_a_no_op(tmp_path):
    widget = FakeWidget(root=str(tmp_path))
    assert file_lifecycle._resume_remembered_file(widget) is False
    assert widget.loaded == []


# --- 启动恢复：先项目，后全局 ---------------------------------------------


def test_continue_last_session_prefers_the_project_position(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    remembered = _make_image(root, "remembered.png")
    stale = _make_image(root, "stale.png")
    project_settings.save_last_file(
        FakeWidget(root=str(root), filename=remembered), str(root)
    )

    widget = FakeWidget(root=str(root))
    widget.settings = FakeSettings(
        {"last_open_dir": str(root), "filename": stale}
    )
    widget.import_image_folder = lambda directory, load=True: None

    assert project_view.continue_last_session(widget) is True
    assert widget.loaded == [remembered]
    assert widget.next_calls == 0


def test_continue_last_session_falls_back_to_the_global_filename(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    legacy = _make_image(root, "legacy.png")

    widget = FakeWidget(root=str(root))
    widget.settings = FakeSettings(
        {"last_open_dir": str(root), "filename": legacy}
    )
    widget.import_image_folder = lambda directory, load=True: None

    # 项目清单里没有 last_file（老会话 / 从没离开过）：退回全局记忆。
    assert project_view.continue_last_session(widget) is True
    assert widget.loaded == [legacy]


def test_continue_last_session_opens_the_first_image_when_nothing_is_known(
    tmp_path,
):
    root = tmp_path / "proj"
    root.mkdir()
    widget = FakeWidget(root=str(root))
    widget.settings = FakeSettings({"last_open_dir": str(root)})
    widget.import_image_folder = lambda directory, load=True: None

    assert project_view.continue_last_session(widget) is True
    assert widget.next_calls == 1
    assert widget.loaded == []


def test_continue_last_session_without_a_directory_does_nothing(tmp_path):
    widget = FakeWidget()
    widget.settings = FakeSettings({"last_open_dir": str(tmp_path / "ghost")})
    widget.import_image_folder = lambda directory, load=True: None

    assert project_view.continue_last_session(widget) is False
    assert widget.next_calls == 0


def test_has_session_follows_the_recorded_directory(tmp_path):
    widget = FakeWidget()
    widget.settings = FakeSettings({"last_open_dir": str(tmp_path)})
    assert project_view.has_session(widget) is True

    widget.settings = FakeSettings({"last_open_dir": str(tmp_path / "ghost")})
    assert project_view.has_session(widget) is False
