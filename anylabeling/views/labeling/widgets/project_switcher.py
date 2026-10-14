"""Project manager: pick a recorded dataset and jump to it.

One dialog covers the project actions that have no natural home in the
settings pages (they act on the open dataset, not on a preference):
switching, revealing the per-project settings file, resetting that file
(keeping the pinned split seed), trimming the registry, and the
show-at-startup switch. Training counts per project come from the run
history (``run_meta.json`` files), joined by path prefix -- a project the
loop never trained shows dashes, which is information too. Annotation
progress (标注进度 ``12/40``) is counted from disk by background workers
(``project_dashboard.collect_progress``) so the dialog opens instantly
no matter how big the datasets are; a row still counting shows a
placeholder, and a count that cannot be made leaves it.
"""

import os
import os.path as osp
import subprocess

from PyQt6 import QtCore, QtWidgets

from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling import (
    project_model,
    project_registry,
    project_settings,
)


class _ProgressSignals(QtCore.QObject):
    """Bridge from worker threads back to the dialog's GUI thread."""

    done = QtCore.pyqtSignal(str, dict)


class _ProgressWorker(QtCore.QRunnable):
    """Count one project's annotation progress off the GUI thread.

    ``collect_progress`` walks every image and peeks into every label
    file -- seconds on a real dataset, and the manager must open
    instantly on twenty of them. A failure just leaves the placeholder:
    a missing column beats a broken dialog.
    """

    def __init__(self, signals, root, output_dir):
        super().__init__()
        self._signals = signals
        self._root = root
        self._output_dir = output_dir

    def run(self):
        try:
            from anylabeling.views.labeling import project_dashboard

            stat = project_dashboard.collect_progress(
                self._root, self._output_dir
            )
        except Exception as e:  # noqa: BLE001 - dashes beat a broken dialog
            logger.warning(f"Could not count progress for {self._root}: {e}")
            return
        try:
            self._signals.done.emit(self._root, stat)
        except RuntimeError:
            pass  # 对话框已经关了：没人听的结果就让它消失


class ProjectSwitcherDialog(QtWidgets.QDialog):
    """List every recorded project; double-click or 打开 switches to it."""

    def __init__(self, parent):
        super().__init__(parent)
        self.widget = parent
        self.setWindowTitle(self.tr("切换项目"))
        self.resize(780, 420)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.list = QtWidgets.QTreeWidget(self)
        self.list.setColumnCount(6)
        self.list.setHeaderLabels(
            [
                self.tr("项目"),
                self.tr("任务"),
                self.tr("上次打开"),
                self.tr("标注进度"),
                self.tr("训练"),
                self.tr("最近训练"),
            ]
        )
        self.list.setRootIsDecorated(False)
        self.list.setAllColumnsShowFocus(True)
        header = self.list.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        for column in (1, 2, 3, 4, 5):
            header.setSectionResizeMode(
                column, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
        self.list.itemDoubleClicked.connect(
            lambda _item, _column: self.open_selected()
        )
        layout.addWidget(self.list, 1)

        self.startup_checkbox = QtWidgets.QCheckBox(
            self.tr("启动时显示项目管理")
        )
        self.startup_checkbox.setChecked(self._startup_pref())
        self.startup_checkbox.toggled.connect(self._on_startup_toggled)
        layout.addWidget(self.startup_checkbox)

        buttons = QtWidgets.QHBoxLayout()
        open_button = QtWidgets.QPushButton(self.tr("打开"))
        new_button = QtWidgets.QPushButton(self.tr("新建项目…"))
        browse_button = QtWidgets.QPushButton(self.tr("打开其他文件夹…"))
        reveal_button = QtWidgets.QPushButton(self.tr("打开项目设置文件夹"))
        reset_button = QtWidgets.QPushButton(self.tr("重置本项目设置"))
        forget_button = QtWidgets.QPushButton(self.tr("从列表移除"))
        delete_button = QtWidgets.QPushButton(self.tr("删除项目数据…"))
        close_button = QtWidgets.QPushButton(self.tr("关闭"))
        for button in (
            open_button,
            new_button,
            browse_button,
            reveal_button,
            reset_button,
            forget_button,
            delete_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        open_button.clicked.connect(self.open_selected)
        new_button.clicked.connect(self._new_project)
        browse_button.clicked.connect(self._browse_other_folder)
        reveal_button.clicked.connect(self._reveal_settings)
        reset_button.clicked.connect(self._reset_settings)
        forget_button.clicked.connect(self._forget_selected)
        delete_button.clicked.connect(self._delete_selected)
        close_button.clicked.connect(self.reject)

        self._progress_signals = _ProgressSignals()
        self._progress_signals.done.connect(self._apply_progress)
        self._reload()

    # --- population -------------------------------------------------------

    def _current_root(self):
        return getattr(self.widget, "_project_dataset_dir", None)

    def _selected_root(self):
        item = self.list.currentItem()
        return item.data(0, QtCore.Qt.ItemDataRole.UserRole) if item else None

    def _reload(self, keep_root=None):
        current = keep_root or self._selected_root() or self._current_root()
        self.list.clear()
        entries = project_registry.recent_projects()
        if not entries:
            empty = QtWidgets.QTreeWidgetItem(
                [self.tr("（还没有项目记录）"), "", "", "", ""]
            )
            empty.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            self.list.addTopLevelItem(empty)
            return
        stats = self._training_stats(entries)
        for entry in entries:
            root = entry["root"]
            described = project_model.describe(root)
            stat = stats.get(root) or {}
            runs = stat.get("runs") or 0
            item = QtWidgets.QTreeWidgetItem(
                [
                    described["name"],
                    project_model.task_label(described["task"]),
                    entry.get("last_opened") or "",
                    # 占位：后台线程数完由 _apply_progress 回填。
                    self.tr("计数中…"),
                    str(runs) if runs else "—",
                    stat.get("last") or "",
                ]
            )
            item.setData(0, QtCore.Qt.ItemDataRole.UserRole, root)
            tooltip = root
            if not described["has_record"]:
                # 名字与任务都是兜底值：说清楚，免得用户以为设置丢了。
                tooltip += f"\n{self.tr('（还没有项目设置文件）')}"
            if described["created_at"]:
                tooltip += f"\n{self.tr('创建于')}: {described['created_at']}"
            remembered = project_settings.remembered_file(root)
            if remembered:
                # 打开这个项目会回到哪张图 —— 续点写下来的意义就在这里。
                tooltip += (
                    f"\n{self.tr('上次看到')}: {osp.basename(remembered)}"
                )
            if entry.get("label_dir"):
                tooltip += f"\n{self.tr('标注目录')}: {entry['label_dir']}"
            item.setToolTip(0, tooltip)
            self.list.addTopLevelItem(item)
            if root == current:
                self.list.setCurrentItem(item)
        if self.list.currentItem() is None:
            self.list.setCurrentItem(self.list.topLevelItem(0))
        self._start_progress_workers(entries)

    def _start_progress_workers(self, entries):
        """Count annotation progress for every listed project in the
        background; each result lands back in its row when it arrives.

        A folder with no record still gets counted (it is a folder of
        images all the same) -- the same judgement the bundle import
        makes.
        """
        pool = QtCore.QThreadPool.globalInstance()
        for entry in entries:
            root = entry["root"]
            described = project_model.describe(root)
            worker = _ProgressWorker(
                self._progress_signals, root, described["output_dir"]
            )
            pool.start(worker)

    def _apply_progress(self, root, stat):
        """Put a finished count into its row: ``12/40`` in the column,
        the confirmed/rework split in the tooltip.

        Rows may have come and gone while the thread was walking the
        disk -- a result for a row that no longer exists is dropped,
        not an error.
        """
        from anylabeling.views.labeling import project_dashboard

        for index in range(self.list.topLevelItemCount()):
            item = self.list.topLevelItem(index)
            if item.data(0, QtCore.Qt.ItemDataRole.UserRole) != root:
                continue
            progress = project_dashboard.format_progress(stat)
            item.setText(3, progress["short"])
            item.setToolTip(
                0,
                item.toolTip(0)
                + f"\n{self.tr('已标注')}: {progress['short']}"
                + f"（{self.tr('已确认')} {stat.get('confirmed') or 0}，"
                + f"{self.tr('待复检')} {stat.get('rework') or 0}）",
            )
            return

    def _training_stats(self, entries):
        """``{root: {"runs", "last"}}`` for the listed projects.

        The training modules are imported lazily and any failure degrades
        to dashes: the project list must never depend on the trainer.
        """
        try:
            from anylabeling.services.auto_training.ultralytics.config import (
                get_default_project_dir,
            )
            from anylabeling.views.training import run_history

            return run_history.project_training_stats(
                entries, get_default_project_dir()
            )
        except Exception as e:  # noqa: BLE001 - dashes beat a broken dialog
            logger.warning(f"Training stats unavailable: {e}")
            return {}

    # --- actions ----------------------------------------------------------

    def open_selected(self):
        root = self._selected_root()
        if not root or root == self._current_root():
            self.reject()
            return
        self.accept()
        self.widget.import_image_folder(root)

    def _browse_other_folder(self):
        self.accept()
        browse = getattr(self.widget, "open_folder_dialog", None)
        if callable(browse):
            browse()

    def _new_project(self):
        """先关掉本对话框再走新建流程：新建的最后一步是打开另一个目录。

        直接调 ``project_view``（不走 widget 上的薄委托）：这两个动作
        没有快捷键、没有别处引用，多一层转发只会让 God Object 再长两行。
        """
        from anylabeling.views.labeling.utils import project_view

        self.accept()
        project_view.new_project(self.widget)

    def _reveal_settings(self):
        root = self._selected_root()
        settings_dir = osp.join(root or "", project_settings_dirname())
        if not osp.isdir(settings_dir):
            QtWidgets.QMessageBox.information(
                self,
                self.tr("暂无项目设置"),
                self.tr(
                    "该项目还没有 .jllabel 设置文件；它会在首次保存时创建。"
                ),
            )
            return
        _open_in_file_manager(settings_dir)

    def _reset_settings(self):
        root = self._selected_root()
        if not root:
            return
        confirm = QtWidgets.QMessageBox.question(
            self,
            self.tr("重置本项目设置"),
            self.tr(
                "清除该项目的标签列表与标注输出目录记录？\n\n"
                "划分种子（split_seed）会保留，训练集/验证集划分不受影响。\n%s"
            )
            % root,
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        if project_settings.reset_ui_settings(root):
            self._reload(root)
            logger.info(f"Reset per-project UI settings: {root}")
        else:
            QtWidgets.QMessageBox.warning(
                self, self.tr("失败"), self.tr("项目设置文件无法写入。")
            )

    def _forget_selected(self):
        root = self._selected_root()
        if not root:
            return
        if project_registry.forget_project(root):
            self._reload()

    def _delete_selected(self):
        """删除选中项目的整个文件夹 —— 进回收站，双重确认。

        「从列表移除」只忘记录，「删除项目数据」动的是图片与标注：所以
        有三道闸 —— 确认对话框说清范围与恢复方式（默认按钮是不删）、
        完整路径的第二次确认、以及回收站通道（``shutil.rmtree`` 在本
        应用里没有删除的资格）。当前打开的项目先安全关闭（未保存的
        改动会照常询问），回收失败则什么都没少，用户手动处理。
        """
        from anylabeling.views.labeling.utils import project_view, recycle_bin

        root = self._selected_root()
        if not root:
            return
        if not osp.isdir(root):
            QtWidgets.QMessageBox.information(
                self,
                self.tr("项目文件夹不存在"),
                self.tr("这个项目的文件夹已经不在磁盘上了：\n%s") % root,
            )
            self._reload()
            return
        described = project_model.describe(root)
        confirm = QtWidgets.QMessageBox.question(
            self,
            self.tr("删除项目数据"),
            self.tr(
                "删除项目「%s」的整个文件夹（含图片与标注）？\n\n"
                "%s\n\n"
                "文件夹将移入回收站，可随时还原；同时从最近项目列表移除。\n"
                "只想忘掉这个项目的话，请用「从列表移除」。"
            )
            % (described["name"], root),
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        confirm = QtWidgets.QMessageBox.question(
            self,
            self.tr("确认删除"),
            self.tr("再次确认：整个文件夹将移入回收站。\n%s") % root,
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        if root == self._current_root():
            if not project_view.close_project(self.widget):
                return  # 未保存的改动没处理完，删除作罢

        if not recycle_bin.send_to_recycle_bin(root):
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("删除失败"),
                self.tr(
                    "未能把文件夹移入回收站，没有删除任何内容。\n"
                    "请手动处理：\n%s"
                )
                % root,
            )
            return
        if not project_registry.forget_project(root):
            logger.warning(f"Could not forget the deleted project: {root}")
        logger.info(f"Sent project folder to the recycle bin: {root}")
        self._reload()

    # --- startup switch ---------------------------------------------------

    def _startup_pref(self):
        """Current show-at-startup choice, defaulting to off."""
        config = getattr(self.widget, "_config", None) or {}
        return bool(config.get("startup_show_project_manager", True))

    def _on_startup_toggled(self, checked):
        """Persist the switch to the app config (rc), best-effort."""
        config = getattr(self.widget, "_config", None)
        if not isinstance(config, dict):
            return
        config["startup_show_project_manager"] = bool(checked)
        try:
            from anylabeling.config import save_config

            save_config(config)
        except Exception as e:  # noqa: BLE001 - a checkbox never blocks
            logger.warning(f"Could not save startup preference: {e}")


def project_settings_dirname():
    from anylabeling.views.labeling.project import PROJECT_DIR_NAME

    return PROJECT_DIR_NAME


def _open_in_file_manager(path):
    try:
        if hasattr(os, "startfile"):
            os.startfile(path)  # noqa: S606 - Windows file manager
        elif osp.exists("/usr/bin/xdg-open"):
            subprocess.Popen(["xdg-open", path])
        else:
            subprocess.Popen(["open", path])
    except OSError as e:  # noqa: BLE001 - best effort only
        logger.warning(f"Could not open {path}: {e}")
