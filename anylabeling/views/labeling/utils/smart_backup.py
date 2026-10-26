"""Restore labels from a previous backup run."""

from __future__ import annotations

import os.path as osp
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import (
    QInputDialog,
    QMessageBox,
)
from anylabeling.views.labeling.utils.label_backup import (
    BACKUP_ROOT_NAME,
    is_session_snapshot,
    list_label_backups,
    restore_label_backup,
)
from anylabeling.views.labeling.utils.smart_ui import (
    _notify,
    label_dir_for,
)

from .smart_common import _label_file_for_image


def run_backup_restore(parent):
    """Put back the label files a bulk deletion -- or an edit -- overwrote.

    Only the image open in the canvas has a real undo, and that undo does not
    survive a file switch, so every other file comes back from a snapshot.
    Two kinds end up in this list: the pre-deletion runs the batch tools
    write, and the runs the editor writes itself before it first overwrites
    each label file in a session (marked 自动快照), which is what answers
    "I broke this an hour and ten images ago".
    """
    directory = label_dir_for(parent)
    if not directory:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "请先打开一个图片文件夹。"
            ),
            "warning",
        )
        return
    runs = list_label_backups(directory)
    if not runs:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "没有找到标注备份（%1 下没有快照）。"
            ).replace("%1", BACKUP_ROOT_NAME),
            "warning",
        )
        return
    entries = [
        QCoreApplication.translate("LabelingWidget", "%1（%2 个文件）")
        .replace("%1", name)
        .replace("%2", str(count))
        + (
            QCoreApplication.translate("LabelingWidget", " · 自动快照")
            if is_session_snapshot(_path)
            else ""
        )
        for name, _path, count in runs
    ]
    choice, ok = QInputDialog.getItem(
        parent,
        QCoreApplication.translate("LabelingWidget", "从备份恢复标注"),
        QCoreApplication.translate(
            "LabelingWidget", "选择要恢复的备份（最新在前）："
        ),
        entries,
        0,
        False,
    )
    if not ok or choice not in entries:
        return
    name, path, count = runs[entries.index(choice)]

    open_label = None
    filename = getattr(parent, "filename", None)
    if filename:
        open_label = _label_file_for_image(filename, directory)
    # Copying over a file the canvas still holds unsaved work for would
    # flatten that work, so the open image is left alone when it is dirty.
    skip = {open_label} if getattr(parent, "dirty", False) else set()

    answer = QMessageBox.question(
        parent,
        QCoreApplication.translate("LabelingWidget", "从备份恢复标注"),
        QCoreApplication.translate(
            "LabelingWidget",
            "将用备份 %1 中的 %2 个文件覆盖当前标注。\n"
            "被覆盖的文件会先写入一个新的备份；选错了就在列表里再选更新的那一项。\n"
            "当前打开且有未保存改动的图片不会被覆盖。",
        )
        .replace("%1", name)
        .replace("%2", str(count)),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return

    result = restore_label_backup(path, directory, skip_files=skip)
    if result["backup_failed"]:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget",
                "备份当前标注失败，已放弃恢复，文件未作修改。",
            ),
            "warning",
        )
        return
    if open_label and open_label not in skip and osp.isfile(open_label):
        parent.load_file(filename)
    refresh = getattr(parent, "_refresh_file_panel", None)
    if callable(refresh):
        refresh()
    if result["restored"]:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "已恢复 %1 个标注文件，被覆盖的版本备份在 %2"
            )
            .replace("%1", str(result["restored"]))
            .replace("%2", osp.basename(result["undo_dir"] or "") or "?"),
            "copy-green",
        )
    else:
        _notify(
            parent,
            QCoreApplication.translate("LabelingWidget", "没有文件被恢复。"),
            "warning",
        )
