"""Iteration dashboard, review jumps, relabel watch and training advice."""

from __future__ import annotations

import os.path as osp
from PyQt6.QtCore import (
    QCoreApplication,
    QTimer,
)
from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils.smart_ui import (
    _ResultDialog,
    _append_result_dialog_actions,
    _notify,
    label_dir_for,
    load_result_image,
)
from anylabeling.views.labeling.utils.active_learning import (
    DEFAULT_ACCEPT,
    DEFAULT_REVIEW,
    append_iteration,
    count_annotations,
    format_iteration_summary,
    load_history,
    load_thresholds,
    suggest_next_step,
    update_last_iteration,
)
from anylabeling.views.labeling.utils.data_audit import audit_dataset
from anylabeling.views.labeling.utils.data_intel import analyze_distribution
from anylabeling.views.labeling.utils.review_queue import next_review_target
from anylabeling.views.labeling.utils.training_advisor import (
    history_summary,
    preflight_checks,
    recommend_training_config,
)

from .smart_common import (
    _image_list,
    _label_entries,
)


def show_iteration_dashboard(parent):
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
    history = load_history(directory)
    lines = format_iteration_summary(history)

    dialog = _ResultDialog(
        parent,
        QCoreApplication.translate("LabelingWidget", "迭代收益看板"),
        QCoreApplication.translate(
            "LabelingWidget", "每次训练并回灌标注后会自动追加一轮记录。"
        ),
    )
    dialog.add_category(
        QCoreApplication.translate("LabelingWidget", "轮次"),
        [(line, "", "") for line in lines],
    )
    suggestion = suggest_next_step(history)
    dialog.add_category(
        QCoreApplication.translate("LabelingWidget", "系统建议"),
        [
            (
                QCoreApplication.translate("LabelingWidget", "下一步"),
                suggestion["reason"],
                "",
            )
        ],
    )
    _append_result_dialog_actions(
        dialog,
        parent,
        directory,
        QCoreApplication.translate("LabelingWidget", "迭代收益看板"),
    )
    dialog.exec()


def _record_relabel_result(parent, directory, baseline):
    """Record the finished round only while its project is still open."""
    if not directory or not osp.isdir(directory):
        return None
    if label_dir_for(parent) != directory:
        # The delayed check can fire after a project switch; the image list
        # would then describe another dataset while ``directory`` points at
        # the old one.
        logger.info(
            "Active learning: relabel round not recorded (project changed)"
        )
        return None
    after = count_annotations(_image_list(parent), directory)
    new_shapes = max(
        0, after["total_shapes"] - (baseline or {}).get("total_shapes", 0)
    )
    result = update_last_iteration(
        directory,
        labeled_images=after["labeled_images"],
        total_shapes=after["total_shapes"],
        new_shapes=new_shapes,
    )
    logger.info(
        f"Active learning: round updated "
        f"(+{new_shapes} shapes, {after['labeled_images']} images)"
    )
    return result


def watch_relabel_result(parent, directory, baseline, interval_ms=1500):
    """Once the relabel batch finishes, record what the round produced."""
    if not directory:
        return

    def _check():
        if label_dir_for(parent) != directory or not osp.isdir(directory):
            return
        if getattr(parent, "_batch_processing_active", False):
            QTimer.singleShot(interval_ms, _check)
            return
        _record_relabel_result(parent, directory, baseline)

    QTimer.singleShot(interval_ms, _check)


def record_training_round(parent, project_path, model_name=None, map50=None):
    """Append a round when a training run is used for auto labeling."""
    directory = label_dir_for(parent)
    if not directory:
        return None
    counts = count_annotations(_image_list(parent), directory)
    return append_iteration(
        directory,
        model=model_name or osp.basename(osp.normpath(project_path or "")),
        map50=map50,
        labeled_images=counts["labeled_images"],
        total_shapes=counts["total_shapes"],
    )


def current_thresholds(parent):
    """``(thresholds, accept, review)`` for the currently open folder."""
    thresholds = load_thresholds(label_dir_for(parent))
    return thresholds, DEFAULT_ACCEPT, DEFAULT_REVIEW


def run_review_jump(parent, forward=True):
    """Open the next/previous image that still needs human review."""
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
    entries = list(_label_entries(parent))
    if not entries:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "当前没有可分析的图片。"
            ),
            "warning",
        )
        return

    results = audit_dataset([path for path, _ in entries], directory)
    queue = [
        osp.normpath(osp.abspath(p)) for p in (results.get("review") or [])
    ]
    if not queue:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "太棒了，暂无待复核图片。"
            ),
        )
        return

    current = None
    if parent.filename:
        current = osp.normpath(osp.abspath(parent.filename))
    target, index = next_review_target(queue, current, forward=forward)
    if target is None:
        _notify(
            parent,
            QCoreApplication.translate("LabelingWidget", "已到复核队列末尾。"),
            "info",
        )
        return
    if not load_result_image(parent, target):
        return
    status = getattr(parent, "status", None)
    if callable(status):
        status(
            QCoreApplication.translate("LabelingWidget", "待复核队列 %1/%2")
            .replace("%1", str(index + 1))
            .replace("%2", str(len(queue)))
        )


def run_training_advice(parent):
    """Pre-flight checks plus suggested hyperparameters for the next round."""
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
    entries = list(_label_entries(parent))
    if not entries:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "当前没有可分析的图片。"
            ),
            "warning",
        )
        return

    stats = analyze_distribution(entries)
    history = load_history(directory)
    hist_info = history_summary(history)

    max_dim = None
    image = getattr(parent, "image", None)
    if image is not None and not image.isNull():
        max_dim = max(image.width(), image.height())

    checks = preflight_checks(stats)
    advice = recommend_training_config(
        stats, history=hist_info, max_image_dim=max_dim
    )

    dialog = _ResultDialog(
        parent,
        QCoreApplication.translate("LabelingWidget", "训练建议"),
        QCoreApplication.translate(
            "LabelingWidget",
            "训练前预检与下一轮超参初值，可按推荐手动填入训练面板。",
        ),
    )
    dialog.add_category(
        QCoreApplication.translate("LabelingWidget", "预检"),
        [(check["message"], "", "") for check in checks],
    )
    dialog.add_category(
        QCoreApplication.translate("LabelingWidget", "推荐初值"),
        [
            (
                f"Epochs={advice['epochs']} · Batch={advice['batch']} · imgsz={advice['imgsz']}",
                advice["text"],
                "",
            )
        ],
    )
    _append_result_dialog_actions(
        dialog,
        parent,
        directory,
        QCoreApplication.translate("LabelingWidget", "训练建议"),
    )
    dialog.exec()
