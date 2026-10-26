"""Template-based prelabel propagation and its writer."""

from __future__ import annotations

import json
import os.path as osp
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QPushButton
from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils._io import save_json
from anylabeling.views.labeling.utils.smart_ui import (
    _ResultDialog,
    _append_result_dialog_actions,
    _highlight_button,
    _notify,
    label_dir_for,
)

from .smart_common import _label_entries
from .smart_ui import (
    _SmartTaskThread,
    _make_progress_dialog,
)


def run_template_propagation(parent):
    """Pre-label unlabeled images by copying a visually similar labelled one.

    For each unlabeled image the best-matching labelled template (dhash
    distance) is found and its shapes are scaled into the target. All
    proposals land in a review dialog; 「写入预标注」applies them to the
    label jsons in one click.
    """
    from anylabeling.views.labeling.utils.shape_propagate import (
        plan_template_propagation,
    )

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

    templates = []
    targets = []
    for image_path, data in entries:
        shapes = (data or {}).get("shapes") if data else None
        if shapes:
            templates.append(image_path)
        else:
            targets.append(image_path)
    if not templates:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "至少需要一张已标注图片作为模板。"
            ),
            "warning",
        )
        return
    if not targets:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "没有未标注的图片需要预标注。"
            ),
        )
        return

    def _job(emit_progress):
        return plan_template_propagation(
            directory,
            targets,
            templates,
            progress=lambda done, total: emit_progress(done, total),
        )

    progress = _make_progress_dialog(
        parent,
        QCoreApplication.translate(
            "LabelingWidget", "正在匹配相似模板并生成预标注…"
        ),
        len(targets),
    )
    thread = _SmartTaskThread(_job, total=len(targets))
    thread.progress_updated.connect(
        lambda done, total: progress.setValue(min(total, done))
    )
    thread.error_occurred.connect(
        lambda message: (
            progress.close(),
            logger.error(f"Template propagation failed: {message}"),
            _notify(
                parent,
                QCoreApplication.translate(
                    "LabelingWidget", "匹配失败：%1"
                ).replace("%1", message),
                "warning",
            ),
        )
    )

    def _finish(batch):
        progress.close()
        if not batch:
            _notify(
                parent,
                QCoreApplication.translate(
                    "LabelingWidget",
                    "没有找到与已标注模板足够相似的未标注图片。",
                ),
            )
            return

        dialog = _ResultDialog(
            parent,
            QCoreApplication.translate("LabelingWidget", "智能模板预标注"),
            QCoreApplication.translate(
                "LabelingWidget",
                "每张未标注图片按相似度匹配一张已标注模板生成预标注框，"
                "请先人工抽查再批量写入。",
            ),
        )
        rows = []
        for item in batch:
            rows.append(
                (
                    osp.basename(item["target"]),
                    (
                        f"模板 {osp.basename(item['template'])}"
                        f" · 距离 {item['distance']} · 计划 {len(item['shapes'])} 框"
                    ),
                    item["target"],
                )
            )
        dialog.add_category(
            QCoreApplication.translate("LabelingWidget", "可预标注的图片"),
            rows,
        )
        write_button = QPushButton(
            QCoreApplication.translate("LabelingWidget", "写入预标注")
        )
        write_button.setStyleSheet(_highlight_button())

        def _write():
            written, failed = _write_prelabels(parent, batch)
            dialog.accept()
            if failed:
                _notify(
                    parent,
                    QCoreApplication.translate(
                        "LabelingWidget", "已写入 %1 项，%2 项失败。"
                    )
                    .replace("%1", str(written))
                    .replace("%2", str(failed)),
                    "warning",
                )
            else:
                _notify(
                    parent,
                    QCoreApplication.translate(
                        "LabelingWidget", "已写入 %1 张图片的预标注。"
                    ).replace("%1", str(written)),
                )

        write_button.clicked.connect(_write)
        _append_result_dialog_actions(
            dialog,
            parent,
            directory,
            QCoreApplication.translate("LabelingWidget", "智能模板预标注"),
            extra_buttons=[write_button],
        )
        dialog.exec()

    thread.result_ready.connect(_finish)
    progress.canceled.connect(thread.request_cancel)
    parent._template_propagation_thread = thread
    thread.start()


def _write_prelabels(parent, batch):
    """Write planned shapes into each target label json. Returns ``(n, n_fail)``."""
    from anylabeling.views.labeling.utils.session_snapshot import (
        snapshot_before_label_write,
    )
    from anylabeling.views.labeling.utils.shape_propagate import _image_size

    written = 0
    failed = 0
    for item in batch:
        label_file = item.get("label_file")
        if not label_file:
            continue
        data = {}
        if osp.isfile(label_file):
            try:
                with open(label_file, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                data = {}
        if not isinstance(data, dict):
            data = {}
        size = (0, 0)
        try:
            size = _image_size(item["target"]) or (0, 0)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"Failed to read image size for {item['target']}: {e}"
            )
        data.setdefault("imageWidth", size[0] or data.get("imageWidth", 0))
        data.setdefault("imageHeight", size[1] or data.get("imageHeight", 0))
        shapes = data.setdefault("shapes", [])
        shapes.extend(item["shapes"])
        try:
            snapshot_before_label_write(label_file)
            save_json(data, label_file, indent=2, ensure_ascii=False)
            written += 1
        except OSError as exc:
            logger.warning(
                f"Template propagation: failed to write {label_file}: {exc}"
            )
            failed += 1
    # Reload the image currently open if it received new pre-labels, so the
    # canvas picks them up. We never rebuild the whole file list here: that
    # would reset the user's current file and may raise a save prompt.
    current = getattr(parent, "filename", None)
    if current and any(
        osp.normpath(osp.abspath(item.get("target") or ""))
        == osp.normpath(osp.abspath(current))
        for item in batch
    ):
        loader = getattr(parent, "load_file", None)
        if callable(loader):
            try:
                loader(current)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Template propagation: failed to reload current image"
                )
    return written, failed
