"""Threshold calibration and dataset-intelligence actions."""

from __future__ import annotations

import os.path as osp
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QLabel
from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils.smart_ui import (
    _ResultDialog,
    _append_result_dialog_actions,
    _notify,
    label_dir_for,
)
from anylabeling.views.labeling.utils.active_learning import (
    MIN_CALIBRATION_SAMPLES,
    calibrate_thresholds,
    collect_score_samples,
    load_thresholds,
    save_thresholds,
)
from anylabeling.views.labeling.utils.data_intel import (
    analyze_distribution,
    find_duplicate_groups,
    mine_hard_examples,
    suggest_balancing,
)

from .smart_common import (
    HARD_EXAMPLE_LIMIT,
    _confirmed_lookup,
    _label_entries,
)
from .smart_ui import (
    _SmartTaskThread,
    _make_progress_dialog,
)


def run_threshold_calibration(parent):
    directory = label_dir_for(parent)
    if not directory:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "请先打开一个图片文件夹。"
            ),
            "warning",
        )
        return None

    confirmed = _confirmed_lookup(parent)
    entries = []
    for image_path, data in _label_entries(parent):
        if data is None:
            continue
        is_confirmed = confirmed.get(
            osp.normpath(osp.abspath(image_path)), False
        )
        entries.append((data, is_confirmed))

    if not entries:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "当前文件夹没有可用的标注，无法校准。"
            ),
            "warning",
        )
        return None

    class_scores, confirmed_scores = collect_score_samples(entries)
    if not class_scores:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget",
                "没有带置信度的自动标注框，请先跑一次自动标注。",
            ),
            "warning",
        )
        return None

    thresholds = calibrate_thresholds(class_scores, confirmed_scores)
    if not thresholds:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget",
                "样本不足（至少需要 %1 个带分数的框），暂不校准。",
            ).replace("%1", str(MIN_CALIBRATION_SAMPLES)),
            "warning",
        )
        return None

    save_thresholds(directory, thresholds)

    # Make the new thresholds take effect immediately in the file filter.
    invalidate = getattr(parent, "invalidate_active_thresholds", None)
    if invalidate is not None:
        invalidate()
    refresh = getattr(parent, "_refresh_file_panel", None)
    if refresh is not None:
        refresh()

    dialog = _ResultDialog(
        parent,
        QCoreApplication.translate("LabelingWidget", "阈值校准"),
        QCoreApplication.translate(
            "LabelingWidget",
            "已按各类的置信度分布生成自动接受/建议复核阈值，"
            "结果写入 classes_thresholds.json，并立即用于「待复核」筛选。",
        ),
    )
    rows = []
    for label, entry in sorted(thresholds.items()):
        rows.append(
            (
                label,
                QCoreApplication.translate(
                    "LabelingWidget", "自动接受 ≥ %1 · 建议复核 < %2 · 样本 %3"
                )
                .replace("%1", f"{entry['accept']:.2f}")
                .replace("%2", f"{entry['review']:.2f}")
                .replace("%3", str(entry["samples"])),
                "",
            )
        )
    dialog.add_category(
        QCoreApplication.translate("LabelingWidget", "各类阈值"), rows
    )
    _append_result_dialog_actions(
        dialog,
        parent,
        directory,
        QCoreApplication.translate("LabelingWidget", "阈值校准"),
    )
    dialog.exec()
    return thresholds


def run_smart_analysis(parent):
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

    paths = [path for path, _ in entries]
    thresholds = load_thresholds(directory)

    def _job(emit_progress):
        stats = analyze_distribution(entries)
        emit_progress(len(entries) // 2, len(entries))
        hard = mine_hard_examples(
            [
                (path, (data or {}).get("shapes") if data else None)
                for path, data in entries
            ],
            thresholds=thresholds,
            top_k=HARD_EXAMPLE_LIMIT,
        )
        duplicates = find_duplicate_groups(
            paths,
            progress=lambda done, total: emit_progress(
                len(entries) // 2 + done // 2, len(entries)
            ),
        )
        return stats, hard, duplicates

    progress = _make_progress_dialog(
        parent,
        QCoreApplication.translate("LabelingWidget", "正在分析数据集…"),
        len(entries),
    )
    thread = _SmartTaskThread(_job, total=len(entries))
    thread.progress_updated.connect(
        lambda done, total: progress.setValue(min(total, done))
    )
    thread.error_occurred.connect(
        lambda message: (
            progress.close(),
            logger.error(f"Smart analysis failed: {message}"),
            _notify(
                parent,
                QCoreApplication.translate(
                    "LabelingWidget", "分析失败：%1"
                ).replace("%1", message),
                "warning",
            ),
        )
    )

    def _finish(payload):
        progress.close()
        stats, hard, duplicates = payload

        dialog = _ResultDialog(
            parent,
            QCoreApplication.translate("LabelingWidget", "数据智能分析"),
            QCoreApplication.translate(
                "LabelingWidget", "双击条目可跳转到对应图片。"
            ),
        )

        advice = suggest_balancing(stats)
        dialog.add_category(
            QCoreApplication.translate("LabelingWidget", "配平建议"),
            [(line, "", "") for line in advice],
        )

        dialog.add_category(
            QCoreApplication.translate("LabelingWidget", "难例优先复核"),
            [
                (
                    osp.basename(path),
                    QCoreApplication.translate(
                        "LabelingWidget", "不确定性 %1"
                    ).replace("%1", f"{score:.2f}"),
                    path,
                )
                for path, score in hard
            ]
            or [
                (
                    QCoreApplication.translate(
                        "LabelingWidget", "暂无（所有图片都较确定）"
                    ),
                    "",
                    "",
                )
            ],
        )

        duplicate_rows = []
        for group in duplicates:
            head = group[0]
            duplicate_rows.append(
                (
                    osp.basename(head),
                    QCoreApplication.translate(
                        "LabelingWidget", "与 %1 张图重复"
                    ).replace("%1", str(len(group) - 1)),
                    head,
                )
            )
        dialog.add_category(
            QCoreApplication.translate("LabelingWidget", "疑似重复图片"),
            duplicate_rows
            or [
                (
                    QCoreApplication.translate(
                        "LabelingWidget", "未发现重复图片"
                    ),
                    "",
                    "",
                )
            ],
        )

        summary = (
            QCoreApplication.translate(
                "LabelingWidget",
                "共 %1 张图 · 已标注 %2 · 标注框 %3 个 · 小目标 %4 个",
            )
            .replace("%1", str(stats["total_images"]))
            .replace("%2", str(stats["labeled_images"]))
            .replace("%3", str(stats["total_shapes"]))
            .replace("%4", str(stats["area_buckets"]["small"]))
        )
        title = QLabel(summary)
        title.setStyleSheet("font-size: 13px; font-weight: 500; padding: 2px;")
        dialog.layout().insertWidget(0, title)
        _append_result_dialog_actions(
            dialog,
            parent,
            directory,
            QCoreApplication.translate("LabelingWidget", "数据智能分析"),
        )

        dialog.exec()

    thread.result_ready.connect(_finish)
    progress.canceled.connect(thread.request_cancel)
    parent._smart_analysis_thread = thread
    thread.start()
