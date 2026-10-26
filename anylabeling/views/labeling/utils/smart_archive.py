"""Duplicate-image archive action."""

from __future__ import annotations

import os.path as osp
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QMessageBox
from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils.smart_ui import (
    _notify,
    label_dir_for,
)
from anylabeling.views.labeling.utils.archiver import (
    ARCHIVE_DIRNAME,
    archive_duplicates_plan,
    finalize_moves,
)
from anylabeling.views.labeling.utils.data_intel import find_duplicate_groups

from .smart_common import _image_list
from .smart_ui import _make_progress_dialog


def run_duplicate_archive(parent):
    """Move near-duplicate images (and their sidecars) out of the folder."""
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
    paths = _image_list(parent)
    if not paths:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "当前没有可分析的图片。"
            ),
            "warning",
        )
        return

    progress = _make_progress_dialog(
        parent,
        QCoreApplication.translate("LabelingWidget", "正在查找重复图片…"),
        max(1, len(paths)),
    )
    groups = find_duplicate_groups(
        paths,
        progress=lambda done, total: progress.setValue(
            min(len(paths), 1 + int(done / max(total, 1) * len(paths)))
        ),
    )
    progress.close()

    plan = archive_duplicates_plan(groups, directory)
    if not plan:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "没有发现可归档的重复图片。"
            ),
        )
        return
    images = [src for src, _ in plan if _looks_like_image(src)]
    answer = QMessageBox.question(
        parent,
        QCoreApplication.translate("LabelingWidget", "一键去重归档"),
        QCoreApplication.translate(
            "LabelingWidget",
            "将归档 %1 张重复图片及其标注到「%2」文件夹，是否继续？",
        )
        .replace("%1", str(len(images)))
        .replace("%2", ARCHIVE_DIRNAME),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return
    # Saving before moving matters: a pending auto-save would otherwise land
    # next to an image that has just been archived.
    if not parent.may_continue():
        return

    moved, skipped = finalize_moves(plan)
    # If the file we are looking at got archived, move on.
    reloader = getattr(parent, "import_image_folder", None)
    if callable(reloader) and osp.isdir(directory):
        try:
            reloader(directory, load=False)
        except Exception:  # noqa: BLE001
            logger.warning("Duplicate archive: failed to reload file list")
    report_archive_result(parent, moved, skipped)


def report_archive_result(parent, moved, skipped):
    """Tell the user exactly what the archive move did."""
    if skipped:
        QMessageBox.warning(
            parent,
            QCoreApplication.translate("LabelingWidget", "归档未全部完成"),
            QCoreApplication.translate(
                "LabelingWidget",
                "已移动 %1 项，%2 项未能移动（原位置保持不变）：\n%3",
            )
            .replace("%1", str(len(moved)))
            .replace("%2", str(len(skipped)))
            .replace("%3", "\n".join(skipped[:10])),
        )
        return
    _notify(
        parent,
        QCoreApplication.translate(
            "LabelingWidget", "已归档 %1 项（打开「%2」文件夹可查）"
        )
        .replace("%1", str(len(moved)))
        .replace("%2", ARCHIVE_DIRNAME),
    )


def _looks_like_image(path):
    from anylabeling.views.labeling.utils.image import (
        get_supported_image_extensions,
    )

    return osp.splitext(str(path))[1].lower() in set(
        get_supported_image_extensions()
    )
