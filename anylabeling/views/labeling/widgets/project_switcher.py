"""Project switcher: pick a recorded dataset and jump to it.

One dialog covers the project actions that have no natural home in the
settings pages (they act on the open dataset, not on a preference):
switching, revealing the per-project settings file, resetting that file
(keeping the pinned split seed), and trimming the registry.
"""

import os
import os.path as osp
import subprocess

from PyQt6 import QtCore, QtWidgets

from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling import project_registry, project_settings


class ProjectSwitcherDialog(QtWidgets.QDialog):
    """List every recorded project; double-click or 打开 switches to it."""

    def __init__(self, parent):
        super().__init__(parent)
        self.widget = parent
        self.setWindowTitle(self.tr("切换项目"))
        self.resize(520, 380)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.list = QtWidgets.QListWidget(self)
        self.list.itemDoubleClicked.connect(lambda _item: self.open_selected())
        layout.addWidget(self.list, 1)

        buttons = QtWidgets.QHBoxLayout()
        open_button = QtWidgets.QPushButton(self.tr("打开"))
        browse_button = QtWidgets.QPushButton(self.tr("打开其他文件夹…"))
        reveal_button = QtWidgets.QPushButton(self.tr("打开项目设置文件夹"))
        reset_button = QtWidgets.QPushButton(self.tr("重置本项目设置"))
        forget_button = QtWidgets.QPushButton(self.tr("从列表移除"))
        close_button = QtWidgets.QPushButton(self.tr("关闭"))
        for button in (
            open_button,
            browse_button,
            reveal_button,
            reset_button,
            forget_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        open_button.clicked.connect(self.open_selected)
        browse_button.clicked.connect(self._browse_other_folder)
        reveal_button.clicked.connect(self._reveal_settings)
        reset_button.clicked.connect(self._reset_settings)
        forget_button.clicked.connect(self._forget_selected)
        close_button.clicked.connect(self.reject)

        self._reload()

    # --- population -------------------------------------------------------

    def _current_root(self):
        return getattr(self.widget, "_project_dataset_dir", None)

    def _selected_root(self):
        item = self.list.currentItem()
        return item.data(QtCore.Qt.ItemDataRole.UserRole) if item else None

    def _reload(self, keep_root=None):
        current = keep_root or self._selected_root() or self._current_root()
        self.list.clear()
        entries = project_registry.recent_projects()
        if not entries:
            empty = QtWidgets.QListWidgetItem(self.tr("（还没有项目记录）"))
            empty.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            self.list.addItem(empty)
            return
        for entry in entries:
            root = entry["root"]
            name = osp.basename(osp.normpath(root)) or root
            item = QtWidgets.QListWidgetItem(name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, root)
            tooltip = root
            if entry.get("label_dir"):
                tooltip += f"\n{self.tr('标注目录')}: {entry['label_dir']}"
            if entry.get("last_opened"):
                tooltip += (
                    f"\n{self.tr('上次打开')}: {entry['last_opened']}"
                )
            item.setToolTip(tooltip)
            self.list.addItem(item)
            if root == current:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0:
            self.list.setCurrentRow(0)

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

    def _reveal_settings(self):
        root = self._selected_root()
        settings_dir = osp.join(root or "", project_settings_dirname())
        if not osp.isdir(settings_dir):
            QtWidgets.QMessageBox.information(
                self,
                self.tr("暂无项目设置"),
                self.tr("该项目还没有 .jllabel 设置文件；它会在首次保存时创建。"),
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
