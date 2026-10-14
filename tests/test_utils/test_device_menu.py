"""「工具 → 设备」子菜单：可选项、勾选、切换与重新检测。

菜单是设备选择的落点（设置页 schema 的 options 是静态的，装不下运行时
才知道的设备清单）。测试用真 QMenu + 桩 widget，探测结果全部注入。
"""

import os
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6 import QtWidgets

from anylabeling.views.common import device_manager as dm_module
from anylabeling.views.labeling.utils import device_menu

_QAPP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class _Widget:
    """A labeling widget as far as the menu is concerned."""

    def __init__(self):
        self.menus = types.SimpleNamespace(tool=QtWidgets.QMenu())
        self.messages = []

    def status(self, message, delay=5000):
        self.messages.append(message)


@pytest.fixture()
def dm(monkeypatch):
    manager = dm_module.DeviceManager()
    manager.refresh_devices()
    monkeypatch.delenv("X_ANYLABELING_DEVICE", raising=False)
    import anylabeling.config as app_config

    # 绝不读用户的真实 rc：设备从测试自己的 config 来。
    monkeypatch.setattr(
        app_config, "get_config", lambda *a, **k: {"device": None}
    )
    monkeypatch.setattr(app_config, "save_config", lambda *a, **k: True)
    yield manager
    manager.refresh_devices()


def _fake_gpu(dm, names):
    dm._available_providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    dm._torch_cuda_devices = list(names)


def _no_gpu(dm):
    dm._available_providers = ["CPUExecutionProvider"]
    dm._torch_cuda_devices = []


def _menu_actions(widget):
    menu = widget.menus.tool.actions()[0].menu()
    return [a for a in menu.actions() if not a.isSeparator()], menu


def test_cpu_only_machine_gets_one_choice(dm):
    _no_gpu(dm)
    widget = _Widget()
    device_menu.populate_device_menu(widget)
    actions, _ = _menu_actions(widget)
    assert [a.text() for a in actions] == ["CPU", "重新检测设备"]
    assert actions[0].isChecked()
    assert actions[0].isCheckable()


def test_each_card_is_its_own_entry_with_its_name(dm):
    _fake_gpu(dm, ["RTX 4090", "RTX 3060"])
    widget = _Widget()
    device_menu.populate_device_menu(widget)
    actions, _ = _menu_actions(widget)
    assert [a.text() for a in actions] == [
        "CPU",
        "GPU · RTX 4090",
        "GPU:1 · RTX 3060",
        "重新检测设备",
    ]
    # 自动探测遇到可用的 CUDA provider 就默认选 GPU
    assert [a.text() for a in actions if a.isChecked()] == ["GPU · RTX 4090"]


def test_the_current_device_is_the_checked_one(dm):
    _fake_gpu(dm, ["RTX 4090"])
    dm.set_device("gpu")
    widget = _Widget()
    device_menu.populate_device_menu(widget)
    actions, _ = _menu_actions(widget)
    checked = [a.text() for a in actions if a.isChecked()]
    assert checked == ["GPU · RTX 4090"]


def test_selecting_a_card_pins_it_and_says_so(dm):
    _fake_gpu(dm, ["RTX 4090", "RTX 3060"])
    widget = _Widget()
    device_menu.populate_device_menu(widget)
    actions, _ = _menu_actions(widget)
    actions[2].trigger()  # GPU:1
    assert dm.get_device() == "GPU:1"
    assert any("GPU:1" in m and "下次加载模型" in m for m in widget.messages)


def test_selecting_an_impossible_card_reports_the_fallback(dm):
    _fake_gpu(dm, ["RTX 4090"])
    widget = _Widget()
    device_menu.populate_device_menu(widget)
    actions, _ = _menu_actions(widget)
    # 只有一张卡时不会列出 GPU:1；直接走内部选择，模拟手写 rc 的情况
    device_menu._select_device(widget, "GPU:5")
    assert dm.get_device() == "GPU"
    assert any("不可用" in m and "GPU" in m for m in widget.messages)


def test_refresh_clears_the_cache_and_rebuilds_the_menu(dm, monkeypatch):
    monkeypatch.setattr(dm, "_is_gpu_available", lambda: False)
    monkeypatch.setattr(dm, "_probe_torch_cuda", lambda: [])
    widget = _Widget()
    device_menu.populate_device_menu(widget)
    _, menu = _menu_actions(widget)
    before = [a.text() for a in menu.actions() if not a.isSeparator()]

    # 用户刚装好显卡：重新探测应当看到它（清缓存也不该回到旧答案）
    monkeypatch.setattr(dm, "_is_gpu_available", lambda: True)
    monkeypatch.setattr(dm, "_probe_torch_cuda", lambda: ["RTX 4090"])
    refresh = [a for a in menu.actions() if a.text() == "重新检测设备"][0]
    refresh.trigger()

    after = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert before != after
    assert any("RTX 4090" in t for t in after)
    assert any("已重新检测" in m for m in widget.messages)


def test_a_widget_without_a_tool_menu_is_left_alone():
    assert device_menu.populate_device_menu(_WidgetBroken()) is None


class _WidgetBroken:
    menus = None
