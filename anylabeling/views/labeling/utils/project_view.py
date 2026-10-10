"""项目视角的界面层：项目名、项目菜单、最近项目、关闭项目。

项目化改造的第一层。它只把已有的机制翻译成"项目"语言，不引入新的
数据模型：

* 项目身份仍然是打开的那个文件夹 —— 路径即身份，没有 uuid，也没有
  别名表，所以同一个文件夹在两台机器上都是同一个项目；
* 事实来源是 ``project_registry``（工作目录下的 ``projects.json``），
  本模块不另存一份；
* 本模块负责的是"呈现"：标题栏里的项目名、File 菜单里的「项目」子
  菜单、两套最近记录（QSettings ``recent_dirs`` 与 registry）的合并，
  以及一个显式的"关闭项目"动作。

放在 ``utils`` 而不是 ``label_widget`` 里，是因为后者已经是六千多行
的 God Object：新功能一律以独立模块 + 薄委托的形式落地，既不继续
膨胀，也不打断既有测试对 ``LabelingWidget`` 属性的直接依赖。
"""

from __future__ import annotations

import os.path as osp

from PyQt6 import QtCore, QtGui, QtWidgets

from anylabeling.views.labeling import project_registry
from anylabeling.views.labeling.logger import logger

#: 老版本存放"最近文件夹"的 QSettings 键。读取时会被迁移进 registry，
#: 迁移完成后即被删除，此后只剩 registry 一个列表。
LEGACY_RECENT_KEY = "recent_dirs"

#: 项目菜单里最多列出多少个最近项目。
RECENT_LIMIT = 10


def _tr(text):
    return QtCore.QCoreApplication.translate("ProjectUI", text)


def project_name(root):
    """项目的显示名：数据集目录名。

    路径即身份，所以显示名直接取目录名 —— 不做可编辑别名，避免同一
    个项目在不同机器上叫不同名字。
    """
    if not root:
        return ""
    return osp.basename(osp.normpath(str(root))) or str(root)


def current_root(widget):
    """当前项目的根目录；没有打开数据集时返回 ``None``。

    刻意不看 ``last_open_dir``：那是"上次打开过什么"，关闭项目之后它
    依然存在，会把已经关掉的项目重新显示成当前项目。
    """
    root = getattr(widget, "_project_dataset_dir", None)
    if root and osp.isdir(str(root)):
        return str(root)
    filename = getattr(widget, "filename", None)
    if filename:
        folder = osp.dirname(str(filename))
        if folder and osp.isdir(folder):
            return folder
    return None


def current_name(widget):
    """当前项目名；没有项目时为空串。"""
    return project_name(current_root(widget))


def title_project_prefix(widget):
    """标题栏里的项目片段，无项目时为空串（标题保持原样）。"""
    name = current_name(widget)
    return f"[{name}] " if name else ""


def record_recent(widget, directory):
    """把一个目录记入最近项目。

    registry 是唯一的事实来源；老 QSettings 键只在读取时迁移一次
    （见 :func:`recent_dirs`），此后不再写入，两个列表不会再次分叉。
    """
    if not directory:
        return False
    directory = osp.normpath(str(directory))
    try:
        return project_registry.record_project(
            directory, label_dir=getattr(widget, "output_dir", None)
        )
    except Exception as e:  # noqa: BLE001 - registry 永远不是关键路径
        logger.warning(f"Could not record project {directory}: {e}")
        return False


def _legacy_recent(widget):
    """老 QSettings 列表里的目录（只在迁移路径上读一次）。"""
    settings = getattr(widget, "settings", None)
    if settings is None:
        return []
    try:
        raw = settings.value(LEGACY_RECENT_KEY, []) or []
    except Exception as e:  # noqa: BLE001 - 坏掉的 QSettings 不该挡住菜单
        logger.warning(f"Could not read legacy recent dirs: {e}")
        return []
    if isinstance(raw, str):
        raw = [raw]
    return [str(item) for item in raw if str(item)]


def _migrate_legacy(widget, paths):
    """把老列表里的目录补进 registry，全部成功后才清掉老键。"""
    for path in paths:
        if not record_recent(widget, path):
            # 一条没写进去就把老键留着，下次还有机会补齐；清单本身不会
            # 因此重复（record_project 是幂等的 touch）。
            return
    settings = getattr(widget, "settings", None)
    if settings is None:
        return
    try:
        settings.remove(LEGACY_RECENT_KEY)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not drop the legacy recent list: {e}")


def recent_dirs(widget, limit=RECENT_LIMIT):
    """最近项目目录，最新在前 —— 只有 registry 一个来源。

    老版本把最近文件夹写在 QSettings 里，跟 registry 各存一份、顺序
    互不相干（文件菜单和"切换项目"对话框经常对不上）。这里把老列表
    里仍然存在、registry 里又没有的目录补录一次，随后删掉老键，从此
    两个入口读的是同一份数据。
    """
    try:
        entries = project_registry.recent_projects()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not read recent projects: {e}")
        entries = []

    roots = [entry["root"] for entry in entries]
    known = {osp.normcase(osp.normpath(root)) for root in roots}
    legacy_raw = _legacy_recent(widget)
    missing = [
        path
        for path in legacy_raw
        if osp.isdir(path) and osp.normcase(osp.normpath(path)) not in known
    ]
    if legacy_raw:
        # 老键里还有内容，读一次就完成迁移：能用的补进 registry，然后
        # 把键清掉（全是被删掉的旧目录时也清，免得每次读都白跑一趟）。
        _migrate_legacy(widget, missing)
        roots.extend(missing)
    return roots[:limit]


def populate_recent_menu(widget, menu):
    """用最近项目填充菜单（每次弹出前重建，列表始终是新的）。"""
    menu.clear()
    dirs = recent_dirs(widget)
    if not dirs:
        empty = menu.addAction(_tr("（还没有项目记录）"))
        empty.setEnabled(False)
        return
    current = current_root(widget)
    for path in dirs:
        # 路径即身份，所以目录名就是项目名；重名时靠 tooltip 的完整
        # 路径区分，不去改显示名。
        label = project_name(path)
        if current and osp.normcase(osp.normpath(path)) == osp.normcase(
            osp.normpath(current)
        ):
            label = _tr("%s（当前）") % label
        action = menu.addAction(label)
        action.setToolTip(path)
        action.triggered.connect(
            lambda _checked=False, p=path: widget.load_recent_dir(p)
        )


def open_settings_folder(widget):
    """在文件管理器里打开当前项目的 ``.jllabel`` 目录。"""
    root = current_root(widget)
    if not root:
        QtWidgets.QMessageBox.information(
            widget,
            _tr("没有打开的项目"),
            _tr("先打开一个项目文件夹，再来看它的项目设置。"),
        )
        return
    from anylabeling.views.labeling.project import PROJECT_DIR_NAME
    from anylabeling.views.labeling.widgets.project_switcher import (
        _open_in_file_manager,
    )

    settings_dir = osp.join(root, PROJECT_DIR_NAME)
    if not osp.isdir(settings_dir):
        QtWidgets.QMessageBox.information(
            widget,
            _tr("暂无项目设置"),
            _tr("该项目还没有 .jllabel 设置文件；它会在首次保存时创建。\n%s")
            % root,
        )
        return
    _open_in_file_manager(settings_dir)


def close_project(widget):
    """关闭当前项目：确认未保存改动，然后回到空画布。

    L1 阶段只做到"干净地退出到没有项目的状态"，不做项目生命周期管理
    （新建/重命名/删除属于后续批次）。项目记录本身留在最近项目列表
    里，随时可以再打开。
    """
    if not current_root(widget):
        widget.status(_tr("当前没有打开的项目"), 3000)
        return False
    if not widget.may_continue():
        return False

    # 项目上下文必须先清掉：否则标题栏与菜单勾选会在文件列表已经清空
    # 之后仍然指着刚关闭的那个项目。
    widget._project_dataset_dir = None
    widget.file_list_widget.clear()
    widget.fn_to_index.clear()
    widget.reset_state()
    widget.set_clean()
    widget.toggle_actions(False)
    widget.canvas.setEnabled(False)
    widget.actions.save_as.setEnabled(False)
    widget.update_progress_title()
    widget.status(_tr("已关闭项目"), 3000)
    return True


def build_project_menu(widget):
    """创建「项目」菜单，插到 File 菜单最前面，并返回它。

    菜单项刻意保持少而稳：后续批次会在这里加"新建项目"与"项目设置"，
    但那些需要先有项目实体（L2）；现在放进去只会是个改了名字的
    "打开文件夹"。
    """
    from anylabeling.views.labeling.utils import new_action

    menu = QtWidgets.QMenu(_tr("项目"), widget)

    # 复用 File 菜单里原有的"切换项目"动作对象：快捷键、设置页对
    # ``actions.open_project`` 的引用都跟着走，不必两处各建一个。
    switch = getattr(widget.actions, "open_project", None)
    if switch is None:
        shortcuts = getattr(widget, "_config", {}).get("shortcuts", {}) or {}
        switch = new_action(
            widget,
            _tr("切换项目…"),
            slot=widget.open_project_switcher,
            shortcut=shortcuts.get("open_project") or None,
            icon="open",
            tip=_tr("在最近打开的项目之间切换"),
        )
        widget.actions.open_project = switch
    menu.addAction(switch)

    recent_menu = QtWidgets.QMenu(_tr("打开最近项目"), menu)
    recent_menu.aboutToShow.connect(
        lambda: populate_recent_menu(widget, recent_menu)
    )
    menu.addMenu(recent_menu)

    menu.addSeparator()

    # 项目动作挂在 widget 上而不是菜单里：菜单只在菜单栏可见时才拥有
    # 快捷键，而关闭项目/打开设置目录不依赖菜单是否打开。
    close_action = new_action(
        widget,
        _tr("关闭项目"),
        slot=lambda: close_project(widget),
        tip=_tr("关闭当前项目并回到空画布"),
    )
    settings_action = new_action(
        widget,
        _tr("打开项目设置文件夹"),
        slot=lambda: open_settings_folder(widget),
        tip=_tr("在文件管理器里打开当前项目的 .jllabel 目录"),
    )
    menu.addAction(settings_action)
    menu.addAction(close_action)

    widget.actions.close_project = close_action
    widget.actions.open_project_settings_folder = settings_action

    file_menu = widget.menus.file
    first = file_menu.actions()
    if first:
        file_menu.insertMenu(first[0], menu)
        file_menu.insertSeparator(first[0])
    else:
        file_menu.addMenu(menu)
    return menu


__all__ = [
    "build_project_menu",
    "close_project",
    "current_name",
    "current_root",
    "open_settings_folder",
    "populate_recent_menu",
    "project_name",
    "recent_dirs",
    "record_recent",
    "title_project_prefix",
]
