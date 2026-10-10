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

from anylabeling.views.labeling import (
    project_model,
    project_registry,
    project_settings,
)
from anylabeling.views.labeling.logger import logger

#: 老版本存放"最近文件夹"的 QSettings 键。读取时会被迁移进 registry，
#: 迁移完成后即被删除，此后只剩 registry 一个列表。
LEGACY_RECENT_KEY = "recent_dirs"

#: 项目菜单里最多列出多少个最近项目。
RECENT_LIMIT = 10


def _tr(text):
    return QtCore.QCoreApplication.translate("ProjectUI", text)


def project_name(root):
    """项目的显示名：清单里记的名字，缺清单时回退目录名。

    名字只是显示标签，不参与任何路径拼接（身份始终是目录路径），所以
    改名、截断、缺失都不会让磁盘上的东西失联。

    没有清单时 :func:`project_model.describe` 只 stat 一次、不读文件：
    标题栏每次切图都会重建，"这个文件夹只是个打开过的目录"是常态，
    不该为它付一次 IO。
    """
    if not root:
        return ""
    return project_model.describe(root)["name"]


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
        described = project_model.describe(path)
        label = described["name"]
        if current and osp.normcase(osp.normpath(path)) == osp.normcase(
            osp.normpath(current)
        ):
            label = _tr("%s（当前）") % label
        action = menu.addAction(label)
        # 显示名可以重复，路径不会：重名时靠 tooltip 里的完整路径区分。
        action.setToolTip(
            "%s\n%s：%s"
            % (path, _tr("任务"), project_model.task_label(described["task"]))
        )
        action.triggered.connect(
            lambda _checked=False, p=path: widget.load_recent_dir(p)
        )


def session_resume_path(widget):
    """上次工作过的目录，不可用时返回 None。

    这是"上次打开过什么"的**全局**记忆（QSettings），只用来决定启动
    时该动哪个项目；项目内部的续点由项目清单里的 ``last_file`` 负责，
    两者刻意分开 —— 一个是"哪个项目"，一个是"项目里的哪张图"。
    """
    try:
        directory = widget.settings.value("last_open_dir", None)
        if directory and osp.isdir(str(directory)):
            return str(directory)
    except Exception as e:  # noqa: BLE001 - 坏设置不该挡住启动
        logger.warning(f"session_resume_path failed: {e}")
    return None


def has_session(widget):
    """启动时有没有可恢复的现场。"""
    return bool(session_resume_path(widget))


def continue_last_session(widget):
    """恢复上次的现场：打开那个项目，再回到**那个项目自己的**位置。

    先问项目清单（``last_file``），再退回 QSettings 的 ``filename`` ——
    后者是改造前的全局记忆，只为老会话留一条路。切换过项目的人在这里
    受益最明显：以前只有一个全局"最后一张"，切回来就找不着了。
    """
    directory = session_resume_path(widget)
    if not directory:
        return False
    try:
        widget.import_image_folder(directory, load=False)
        target = project_settings.remembered_file(directory) or ""
        if not target:
            fallback = widget.settings.value("filename", "") or ""
            if fallback and osp.isfile(str(fallback)):
                target = str(fallback)
        if target:
            widget.load_file(target)
        else:
            widget.open_next_image(load=True)
        widget._refresh_file_panel()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Session resume failed: {e}")
        widget.status(_tr("恢复上次工作现场失败"), 4000)
        return False


def _template_choices(target_root, limit=RECENT_LIMIT):
    """Existing projects worth offering as templates, registry order.

    Only folders that really carry a record qualify — a merely-opened
    folder has no labels or tuning to give. The target itself is
    excluded (a fresh folder cannot be its own template). Read failures
    degrade to a shorter list, never an error: the wizard must open
    even when the registry is unreadable.
    """
    choices = []
    try:
        entries = project_registry.recent_projects(limit=limit)
    except Exception as e:  # noqa: BLE001 - 模板列表不是关键路径
        logger.warning(f"Could not list template candidates: {e}")
        return choices
    target = osp.normcase(osp.normpath(str(target_root or "")))
    for entry in entries:
        source = entry.get("root")
        if not source:
            continue
        if target and osp.normcase(osp.normpath(source)) == target:
            continue
        described = project_model.describe(source)
        if not described["has_record"]:
            continue
        choices.append(
            {
                "root": source,
                "name": described["name"],
                "task": described["task"],
                "labels": described["labels"],
            }
        )
    return choices


def _apply_chosen_template(root, template_root):
    """Copy the template's labels and tuning onto the fresh record.

    Best effort by design: the project was created either way, so a
    failed template copy is a warning in the log and a project with
    defaults — never a dialog in front of a just-created project.
    """
    if not template_root:
        return True
    try:
        template = project_model.template_record(template_root)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not read template {template_root}: {e}")
        return False
    if not project_model.apply_template(root, template):
        logger.warning(f"Could not apply template {template_root} to {root}")
        return False
    logger.info(
        f"Applied template {template_root} to {root} "
        f"(task={template['task']}, "
        f"labels={len(template.get('labels') or [])})"
    )
    return True


def new_project(widget):
    """新建项目：选文件夹 → 起名/选任务 → 打开它。

    目标文件夹已经有项目清单时**不覆盖** —— 那是别人攒下来的设置；
    这里只提供"打开它"，换个目录由用户决定。（``project_model.create``
    拒绝覆盖，正好把"已存在"和"写失败"这两种 False 留给调用方分辨。）

    向导里可以选一个既有项目作为模板：标签集与训练超参在创建后拷入，
    任务类型在选中的那一刻就预选好 —— 同类任务的第二个项目不再从
    空白开始。
    """
    from anylabeling.views.labeling.widgets.project_dialog import (
        ProjectPropertiesDialog,
    )

    start_dir = getattr(widget, "last_open_dir", None) or ""
    root = QtWidgets.QFileDialog.getExistingDirectory(
        widget, _tr("选择项目文件夹"), start_dir
    )
    if not root:
        return False
    root = osp.normpath(str(root))

    if project_model.has_record(root):
        answer = QtWidgets.QMessageBox.question(
            widget,
            _tr("已经是项目"),
            _tr("这个文件夹已经是一个项目了，直接打开它吗？\n%s") % root,
        )
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return False
        widget.import_image_folder(root)
        return True

    dialog = ProjectPropertiesDialog(
        widget,
        name=project_model.default_name(root),
        root=root,
        title=_tr("新建项目"),
        templates=_template_choices(root),
    )
    if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return False

    values = dialog.values()
    if not project_model.create(
        root, name=values["name"], task=values["task"]
    ):
        QtWidgets.QMessageBox.warning(
            widget,
            _tr("新建项目失败"),
            _tr("无法写入项目设置，请检查该目录是否可写：\n%s") % root,
        )
        return False
    _apply_chosen_template(root, values.get("template_root"))

    logger.info(f"Created project: {root} ({values['task']})")
    widget.import_image_folder(root)
    return True


def edit_project(widget):
    """改当前项目的名字与任务类型。

    还不是正式项目（没有清单）时顺手建一个：这条路径是用户第一次
    明确表达"把当前这个文件夹当成一个项目"，比默默等某次保存更清楚。
    """
    from anylabeling.views.labeling.widgets.project_dialog import (
        ProjectPropertiesDialog,
    )

    root = current_root(widget)
    if not root:
        QtWidgets.QMessageBox.information(
            widget,
            _tr("没有打开的项目"),
            _tr("先打开一个文件夹，再来设置项目属性。"),
        )
        return False

    described = project_model.describe(root)
    note = None
    overview = None
    if not described["has_record"]:
        note = _tr(
            "这个文件夹还不是正式项目；保存后会在其中创建 "
            ".jllabel/project.json（只是多一个隐藏目录）。"
        )
    else:
        # 只读快照：进度与训练轮次都从盘上现数，不另存一份。任何一路
        # 读不了都按"没有"处理 —— 概览不能成为打不开属性对话框的理由。
        try:
            from anylabeling.views.labeling import project_dashboard

            overview = project_dashboard.collect(
                root,
                output_dir=project_settings.get_value(root, "output_dir"),
            )
        except Exception as e:  # noqa: BLE001 - 概览永远不是关键路径
            logger.warning(f"Could not build the project overview: {e}")
            overview = None
    dialog = ProjectPropertiesDialog(
        widget,
        name=described["name"],
        task=described["task"],
        root=root,
        title=_tr("项目属性"),
        note=note,
        overview=overview,
    )
    if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return False

    values = dialog.values()
    if described["has_record"]:
        ok = project_model.rename(root, values["name"])
        if not project_model.set_task(root, values["task"]):
            ok = False
    else:
        ok = project_model.create(
            root, name=values["name"], task=values["task"]
        )
    if not ok:
        QtWidgets.QMessageBox.warning(
            widget,
            _tr("保存失败"),
            _tr("无法写入项目设置，请检查该目录是否可写：\n%s") % root,
        )
        return False

    widget.update_progress_title()
    widget.status(_tr("已更新项目：%s") % values["name"], 3000)
    return True


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


def _bundle_progress_dialog(widget, title):
    """A progress dialog for pack/unpack, driven by the bundle callbacks.

    Synchronous-with-progress rather than a worker thread: packing is
    per-file IO, ``setValue`` keeps the window alive, and the cancel
    button routes through the bundle's own cancel hook.
    """
    dialog = QtWidgets.QProgressDialog(widget)
    dialog.setWindowTitle(title)
    dialog.setLabelText(_tr("正在处理…"))
    dialog.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
    dialog.setMinimumDuration(0)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    return dialog


def _run_bundle_step(widget, total, work, title):
    """Drive ``work(progress, cancel)`` with a progress dialog.

    ``work`` receives a ``(done, total, name)`` progress callback and a
    ``cancel()`` predicate, and returns its own result. Returns
    ``None`` when the user cancelled, otherwise whatever ``work`` did.
    """
    dialog = _bundle_progress_dialog(widget, title)
    dialog.setRange(0, max(total, 1))

    def progress(done, _total, name):
        dialog.setValue(done)
        dialog.setLabelText(name)

    result = work(progress, dialog.wasCanceled)
    dialog.cancel()
    if dialog.wasCanceled():
        return None
    return result


def export_project_bundle(widget):
    """把当前项目打包成 zip：图片、标签、.jllabel 设置一起走。

    包是"整个数据集目录"的原样快照 —— 项目化的第一原则（清单随数据
    走）让它不需要任何额外的组装步骤。导出在界面上有进度与取消；取消
    会删掉半成品，一个自称项目包的残缺 zip 比没有包更糟。
    """
    from anylabeling.views.labeling import project_bundle

    root = current_root(widget)
    if not root:
        QtWidgets.QMessageBox.information(
            widget,
            _tr("没有打开的项目"),
            _tr("先打开一个项目文件夹，再来导出项目包。"),
        )
        return False

    suggested = osp.join(osp.dirname(root), f"{osp.basename(root)}.zip")
    path, _ = QtWidgets.QFileDialog.getSaveFileName(
        widget, _tr("导出项目包"), suggested, _tr("项目包 (*.zip)")
    )
    if not path:
        return False
    if not path.lower().endswith(".zip"):
        path += ".zip"

    total = sum(1 for _ in project_bundle._iter_files(root))

    def work(progress, cancel):
        return project_bundle.export_bundle(
            root, path, progress=progress, cancel=cancel
        )

    result = _run_bundle_step(widget, total, work, _tr("导出项目包"))
    if result is None:
        widget.status(_tr("已取消导出"), 3000)
        return False
    widget.status(_tr("已导出项目包（%d 个文件）") % result["files"], 5000)
    logger.info(
        f"Exported project bundle: {root} -> {path} "
        f"({result['files']} files, {result['bytes']} bytes, "
        f"{len(result['skipped'])} skipped)"
    )
    return True


def import_project_bundle(widget):
    """从项目包 zip 还原一个项目，并打开它。

    解包目标由包的顶层目录名决定（同名已存在则拒绝——绝不合并别人
    的半成品）；条目逐一做 zip-slip 校验，越界即整体失败。成功后
    直接打开还原出的项目。
    """
    from anylabeling.views.labeling import project_bundle

    path, _ = QtWidgets.QFileDialog.getOpenFileName(
        widget, _tr("从项目包导入"), "", _tr("项目包 (*.zip)")
    )
    if not path:
        return False
    info = project_bundle.inspect_bundle(path)
    if not info or not info["top"]:
        QtWidgets.QMessageBox.warning(
            widget,
            _tr("不是项目包"),
            _tr("这个 zip 不是单文件夹的项目包，无法导入：\n%s") % path,
        )
        return False
    described = project_model.describe_from_record(info["top"], info["record"])
    answer = QtWidgets.QMessageBox.question(
        widget,
        _tr("导入项目包"),
        _tr("将导入项目「%s」（%s），解包后立即打开。继续吗？")
        % (described["name"], project_model.task_label(described["task"])),
    )
    if answer != QtWidgets.QMessageBox.StandardButton.Yes:
        return False

    parent = QtWidgets.QFileDialog.getExistingDirectory(
        widget,
        _tr("选择解包位置"),
        getattr(widget, "last_open_dir", None) or "",
    )
    if not parent:
        return False

    def work(progress, cancel):
        return project_bundle.import_bundle(
            path, parent, progress=progress, cancel=cancel
        )

    try:
        result = _run_bundle_step(
            widget, info["entries"], work, _tr("导入项目包")
        )
    except ValueError as e:
        QtWidgets.QMessageBox.warning(widget, _tr("导入失败"), str(e))
        return False
    if result is None:
        widget.status(_tr("已取消导入"), 3000)
        return False
    widget.import_image_folder(result["root"])
    widget.status(_tr("已导入项目并打开"), 5000)
    logger.info(f"Imported project bundle: {path} -> {result['root']}")
    return True


def close_project(widget):
    """关闭当前项目：确认未保存改动，写回项目状态，回到空画布。

    项目记录留在最近项目列表里，随时可以再打开 —— 而且因为离开时写下
    了位置，再打开会回到关掉时看的那张图。
    """
    if not current_root(widget):
        widget.status(_tr("当前没有打开的项目"), 3000)
        return False
    if not widget.may_continue():
        return False

    # 先把状态写回项目：下面的 reset_state 只清界面，不会替项目留续点，
    # 而清掉 _project_dataset_dir 之后就不知道写给谁了。
    project_settings.flush_open_project(widget)
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

    三段式：先是对项目本身做的两件事（新建 / 属性），再是在项目之间
    走动（切换 / 最近项目），最后是两个收尾动作（打开设置目录 / 关闭
    项目）。不加自建快捷键 —— 键位是四层同步的活儿（yaml / 启动绑定 /
    运行时改键 / F1 表），值得单独一批，不该顺手塞进来。
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
    else:
        # 复用的动作来自 File 菜单，源串是英文 "Switch Project"，翻译表里
        # 没有省略号；它和同一菜单里的另两项一样会打开对话框，按 Qt 惯例
        # 应带省略号。两处共用这一个动作对象，所以一起变。
        switch.setText(_tr("切换项目…"))
    new_action_item = new_action(
        widget,
        _tr("新建项目…"),
        slot=lambda: new_project(widget),
        tip=_tr("选一个文件夹，为它起名并指定任务类型"),
    )
    properties_action = new_action(
        widget,
        _tr("项目属性…"),
        slot=lambda: edit_project(widget),
        tip=_tr("修改当前项目的名字与任务类型"),
    )
    menu.addAction(new_action_item)
    menu.addAction(properties_action)

    menu.addSeparator()
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
    export_action = new_action(
        widget,
        _tr("导出项目包…"),
        slot=lambda: export_project_bundle(widget),
        tip=_tr("把整个项目（图片、标签、设置）打包成一个 zip"),
    )
    import_action = new_action(
        widget,
        _tr("从项目包导入…"),
        slot=lambda: import_project_bundle(widget),
        tip=_tr("从项目包 zip 还原一个项目并打开它"),
    )
    menu.addAction(settings_action)
    menu.addAction(export_action)
    menu.addAction(import_action)
    menu.addAction(close_action)

    widget.actions.new_project = new_action_item
    widget.actions.project_properties = properties_action
    widget.actions.close_project = close_action
    widget.actions.open_project_settings_folder = settings_action
    widget.actions.export_project_bundle = export_action
    widget.actions.import_project_bundle = import_action

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
    "continue_last_session",
    "current_name",
    "current_root",
    "edit_project",
    "export_project_bundle",
    "has_session",
    "import_project_bundle",
    "new_project",
    "open_settings_folder",
    "populate_recent_menu",
    "project_name",
    "recent_dirs",
    "record_recent",
    "session_resume_path",
    "title_project_prefix",
]
