"""「工具 → 设备」子菜单：选择自动标注跑哪块硬件。

设备清单是**运行时**才知道的（这台机器有几张卡、卡叫什么），而设置页的
schema 用的是静态 `options` 元组（枚举校验要求取值在表里）——所以设备选择
放在菜单里用 `QActionGroup` 做单选，清单每次填充时现问 `device_manager`。

菜单只做两件事：勾一个可用设备、或要求重新检测。检测结果全部走缓存，
纯 CPU 机器上打开菜单不会 import torch。
"""

import logging

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QMenu

from anylabeling.views.common.device_manager import device_manager

logger = logging.getLogger(__name__)


def populate_device_menu(widget):
    """Attach the 设备 submenu under 工具 and fill it.

    Called once while menus are built; 「重新检测设备」rebuilds it in place
    for the case that motivated `refresh_devices` -- plugging in /
    installing a GPU runtime without restarting the app.
    """
    tool_menu = getattr(getattr(widget, "menus", None), "tool", None)
    if tool_menu is None:
        return None

    menu = tool_menu.addMenu(
        QCoreApplication.translate("LabelingWidget", "设备")
    )
    _fill_menu(widget, menu)
    return menu


def _fill_menu(widget, menu: QMenu):
    menu.clear()
    current = device_manager.get_device()

    group = QActionGroup(menu)
    group.setExclusive(True)
    for spec, label in device_manager.describe_available():
        action = QAction(label, menu)
        action.setCheckable(True)
        action.setChecked(spec == current)
        action.triggered.connect(
            lambda _checked=False, target=spec: _select_device(widget, target)
        )
        group.addAction(action)
        menu.addAction(action)

    menu.addSeparator()
    refresh = QAction(
        QCoreApplication.translate("LabelingWidget", "重新检测设备"), menu
    )
    refresh.setToolTip(
        QCoreApplication.translate(
            "LabelingWidget",
            "重新探测显卡与 onnxruntime 的 CUDA 支持（装完 onnxruntime-gpu "
            "不必重启程序）",
        )
    )
    refresh.triggered.connect(lambda: _refresh(widget, menu))
    menu.addAction(refresh)


def _refresh(widget, menu):
    device_manager.refresh_devices()
    _fill_menu(widget, menu)
    _notify(
        widget,
        QCoreApplication.translate("LabelingWidget", "设备列表已重新检测：%s")
        % device_manager.get_device(),
    )


def _select_device(widget, spec):
    """Pin the device, persist it, and say what actually took effect."""
    try:
        actual = device_manager.set_device(spec)
    except ValueError as error:
        _notify(
            widget,
            QCoreApplication.translate("LabelingWidget", "无法切换到 %s：%s")
            % (spec, error),
        )
        return

    try:
        from anylabeling.config import get_config, save_config

        config = get_config()
        config["device"] = actual
        save_config(config)
    except Exception as error:  # noqa: BLE001 - 记住选择不是关键路径
        logger.warning(f"Could not persist the device choice: {error}")

    if actual != spec:
        # 越界回退已经发生过：说清楚实际用的是哪个，别让勾选看着成功。
        _notify(
            widget,
            QCoreApplication.translate(
                "LabelingWidget", "设备 %s 不可用，已改用 %s"
            )
            % (spec, actual),
        )
        return
    _notify(
        widget,
        QCoreApplication.translate(
            "LabelingWidget", "自动标注设备已切换为 %s（下次加载模型时生效）"
        )
        % actual,
    )


def _notify(widget, message):
    status = getattr(widget, "status", None)
    if callable(status):
        status(message, 4000)
        return
    logger.info(message)
