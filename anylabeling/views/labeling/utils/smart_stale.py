"""Stale-shape audit, cleanup report and deletion."""

from __future__ import annotations

import os.path as osp
import time
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import (
    QMessageBox,
    QPushButton,
)
from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.provenance import (
    SOURCE_HUMAN,
    SOURCE_MODEL,
    SOURCE_UNKNOWN,
    collect_other_model_shapes,
    describe_shape,
    get_source,
    is_deletable_stale_shape,
    is_from_other_model,
    model_identity_label,
    model_of,
    model_version_of,
    shape_marker,
)
from anylabeling.views.labeling.utils._io import save_json
from anylabeling.views.labeling.utils.label_backup import backup_label_files
from anylabeling.views.labeling.utils.smart_ui import (
    _ResultDialog,
    _append_result_dialog_actions,
    _notify,
    label_dir_for,
)

from .smart_common import (
    _label_entries,
    _label_file_for_image,
    _read_label,
)


def apply_stale_deletions(
    targets,
    current_model,
    skip_files=None,
    label_dir=None,
    current_version=None,
):
    """Delete the stale model boxes a reviewed report pointed at.

    ``targets`` maps a label file to the shape references the report showed.
    A reference is honoured only while the shape at that index is still the
    same box and still attributable to another model, so anything the user
    moved, relabelled or locked between reporting and deleting is skipped
    rather than removed. ``current_version`` is the loaded model's weight
    digest: without it a retrained model looks identical to the one whose boxes
    are being cleaned up, because both carry the same name.

    When ``label_dir`` is given the files that are about to change are copied
    into ``<label_dir>/.label_backups/<stamp>/`` first, and the whole batch is
    abandoned if that backup cannot be completed. Files other than the one open
    in the canvas have no undo history to fall back on, so that snapshot is the
    only way back.
    """
    skipped_files = set(skip_files or ())
    counts = {
        "deleted": 0,
        "files": 0,
        "skipped_locked": 0,
        "skipped_changed": 0,
        "skipped_unavailable": 0,
        "backup_dir": None,
        "backup_failed": False,
        # Which shape indexes were actually removed from each file, so the
        # caller can mirror the same decision on the canvas instead of
        # re-deriving it and possibly disagreeing.
        "deleted_refs": {},
    }
    pending = {}
    for label_file, refs in (targets or {}).items():
        if not refs:
            continue
        data = _read_label(label_file)
        if not isinstance(data, dict):
            counts["skipped_unavailable"] += len(refs)
            continue
        shapes = data.get("shapes") or []
        doomed = set()
        for ref in refs:
            index = ref.get("index")
            if not isinstance(index, int) or not 0 <= index < len(shapes):
                counts["skipped_unavailable"] += 1
                continue
            shape = shapes[index]
            if shape_marker(shape) != ref.get("marker"):
                counts["skipped_changed"] += 1
                continue
            if shape.get("locked"):
                counts["skipped_locked"] += 1
                continue
            if not is_deletable_stale_shape(
                shape, current_model, current_version
            ):
                counts["skipped_changed"] += 1
                continue
            doomed.add(index)
        if label_file in skipped_files:
            counts["skipped_changed"] += len(doomed)
            continue
        if not doomed:
            continue
        pending[label_file] = (data, shapes, doomed)

    if not pending:
        return counts

    if label_dir:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        counts["backup_dir"] = backup_label_files(pending, label_dir, stamp)
        if counts["backup_dir"] is None:
            counts["backup_failed"] = True
            counts["skipped_unavailable"] += sum(
                len(doomed) for _, _, doomed in pending.values()
            )
            return counts
    else:
        # No folder was handed over, but every label file knows where it
        # lives: snapshot through the editor's helper. Deleting model boxes
        # with nothing to restore is the one outcome this tool must not
        # produce, whatever its caller remembered to pass.
        from anylabeling.views.labeling.utils.session_snapshot import (
            snapshot_before_label_write,
        )

        runs = {
            label_file: snapshot_before_label_write(label_file)
            for label_file in pending
        }
        if any(run is None for run in runs.values()):
            counts["backup_failed"] = True
            counts["skipped_unavailable"] += sum(
                len(doomed) for _, _, doomed in pending.values()
            )
            return counts
        counts["backup_dir"] = sorted(set(runs.values()))[0]

    for label_file, (data, shapes, doomed) in pending.items():
        data["shapes"] = [
            shape for i, shape in enumerate(shapes) if i not in doomed
        ]
        try:
            save_json(data, label_file)
        except OSError as exc:
            logger.warning(
                f"Stale cleanup: failed to write {label_file}: {exc}"
            )
            counts["skipped_unavailable"] += len(doomed)
            continue
        counts["deleted"] += len(doomed)
        counts["files"] += 1
        counts["deleted_refs"][label_file] = sorted(doomed)
    return counts


def run_stale_model_audit(parent):
    """List boxes produced by a model other than the one currently loaded.

    Deliberately report-only: a box may have been corrected by hand after the
    old model drew it, so deleting requires looking at the list first.
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

    current_model = parent._current_model_identity()
    current_version = parent._current_model_version()
    by_producer = {}
    counts = {SOURCE_HUMAN: 0, SOURCE_UNKNOWN: 0}
    current_model_boxes = 0
    for image_path, data in entries:
        if not data:
            continue
        for index, shape in collect_other_model_shapes(
            data, current_model, current_version
        ):
            if shape.get("locked"):
                continue
            producer = model_identity_label(
                model_of(shape), model_version_of(shape)
            ) or QCoreApplication.translate("LabelingWidget", "未记录来源")
            label_name, detail = describe_shape(shape)
            ref = {
                "index": index,
                "marker": shape_marker(shape),
                "label_file": _label_file_for_image(image_path, directory),
            }
            by_producer.setdefault(producer, []).append(
                (
                    osp.basename(image_path),
                    f"{label_name} · {detail}".strip(" ·"),
                    image_path,
                    ref,
                )
            )
        for shape in data.get("shapes") or []:
            source = get_source(shape)
            if source in counts:
                counts[source] += 1
            elif source == SOURCE_MODEL and not is_from_other_model(
                shape, current_model, current_version
            ):
                current_model_boxes += 1

    stale_total = sum(len(rows) for rows in by_producer.values())
    dialog = _ResultDialog(
        parent,
        QCoreApplication.translate("LabelingWidget", "旧轮模型框盘点"),
        QCoreApplication.translate(
            "LabelingWidget",
            "双击条目可跳转到对应图片；勾选条目后可删除。被锁定的框、"
            "来源不明的框以及期间被改动过的框都不会被删除。",
        ),
    )
    dialog.add_category(
        QCoreApplication.translate("LabelingWidget", "概览"),
        [
            (
                QCoreApplication.translate(
                    "LabelingWidget", "当前模型：%1"
                ).replace(
                    "%1",
                    model_identity_label(current_model, current_version)
                    or QCoreApplication.translate("LabelingWidget", "未加载"),
                ),
                "",
                "",
            ),
            (
                QCoreApplication.translate(
                    "LabelingWidget", "可清理的旧轮模型框 %1 个"
                ).replace("%1", str(stale_total)),
                QCoreApplication.translate(
                    "LabelingWidget", "由其它模型产生，未被本轮结果覆盖"
                ),
                "",
            ),
            (
                QCoreApplication.translate(
                    "LabelingWidget", "本轮模型框 %1 个"
                ).replace("%1", str(current_model_boxes)),
                "",
                "",
            ),
            (
                QCoreApplication.translate(
                    "LabelingWidget", "人工框 %1 个"
                ).replace("%1", str(counts[SOURCE_HUMAN])),
                "",
                "",
            ),
            (
                QCoreApplication.translate(
                    "LabelingWidget", "来源不明 %1 个"
                ).replace("%1", str(counts[SOURCE_UNKNOWN])),
                QCoreApplication.translate(
                    "LabelingWidget", "早于来源记录功能，不参与清理"
                ),
                "",
            ),
        ],
    )
    for producer in sorted(by_producer):
        dialog.add_category(
            QCoreApplication.translate("LabelingWidget", "来自 %1（%2 个）")
            .replace("%1", producer)
            .replace("%2", str(len(by_producer[producer]))),
            by_producer[producer],
        )
    if not by_producer:
        dialog.add_category(
            QCoreApplication.translate("LabelingWidget", "可清理项"),
            [
                (
                    QCoreApplication.translate(
                        "LabelingWidget", "没有其它模型留下的框"
                    ),
                    "",
                    "",
                )
            ],
        )
    delete_button = QPushButton(
        QCoreApplication.translate("LabelingWidget", "删除所选")
    )
    delete_button.clicked.connect(
        lambda: _delete_reported_stale(parent, dialog)
    )
    _append_result_dialog_actions(
        dialog,
        parent,
        directory,
        QCoreApplication.translate("LabelingWidget", "旧轮模型框盘点"),
        extra_buttons=[delete_button],
    )
    dialog.exec()


def stale_cleanup_result(counts, open_deleted):
    """User-facing summary of a stale cleanup: (message, icon, skipped)."""
    skipped = (
        counts["skipped_locked"]
        + counts["skipped_changed"]
        + counts["skipped_unavailable"]
    )
    if counts["deleted"]:
        message = (
            QCoreApplication.translate(
                "LabelingWidget", "已删除 %1 个框（涉及 %2 个文件），备份在 %3"
            )
            .replace("%1", str(counts["deleted"]))
            .replace("%2", str(counts["files"]))
            .replace(
                "%3",
                osp.basename(counts["backup_dir"] or "")
                or QCoreApplication.translate("LabelingWidget", "未备份"),
            )
        )
        if open_deleted:
            message += QCoreApplication.translate(
                "LabelingWidget", "；当前图片可直接 Ctrl+Z 撤销"
            )
        if skipped:
            message += QCoreApplication.translate(
                "LabelingWidget",
                "；另有 %1 个框被跳过（锁定、已改动或文件不可用）",
            ).replace("%1", str(skipped))
        return message, "copy-green", skipped
    if skipped:
        return (
            QCoreApplication.translate(
                "LabelingWidget",
                "没有框被删除；%1 个框被跳过（锁定、已改动或文件不可用）。",
            ).replace("%1", str(skipped)),
            "warning",
            skipped,
        )
    return (
        QCoreApplication.translate("LabelingWidget", "没有框被删除。"),
        "warning",
        0,
    )


def _delete_reported_stale(parent, dialog):
    """Delete exactly the stale boxes the reviewed report has selected."""
    rows = [row for row in dialog.selected_rows() if row.get("shape_ref")]
    if not rows:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "请先在列表中选择要删除的框。"
            ),
            "warning",
        )
        return

    targets = {}
    for row in rows:
        ref = dict(row["shape_ref"])
        label_file = ref.pop("label_file", None)
        if not label_file:
            continue
        targets.setdefault(label_file, []).append(ref)
    if not targets:
        return

    total = sum(len(refs) for refs in targets.values())
    answer = QMessageBox.question(
        parent,
        QCoreApplication.translate("LabelingWidget", "删除旧轮模型框"),
        QCoreApplication.translate(
            "LabelingWidget",
            "将从 %1 个文件中删除选中的 %2 个框。\n"
            "锁定、来源不明以及报告之后被改动过的框会自动跳过。\n"
            "当前打开的图片删除后可用 Ctrl+Z 撤销；其余文件删除前会先备份到 "
            ".label_backups，之后可用「从备份恢复标注」取回。",
        )
        .replace("%1", str(len(targets)))
        .replace("%2", str(total)),
    )
    if answer != QMessageBox.StandardButton.Yes:
        return

    current_model = parent._current_model_identity()
    open_label = None
    filename = getattr(parent, "filename", None)
    if filename:
        open_label = _label_file_for_image(filename, label_dir_for(parent))
    # The open file lives in the canvas too: editing it on disk while unsaved
    # human work is pending would lose that work, so leave it alone.
    skip = set()
    if open_label in targets and getattr(parent, "dirty", False):
        skip.add(open_label)

    counts = apply_stale_deletions(
        targets,
        current_model,
        skip_files=skip,
        label_dir=label_dir_for(parent),
        current_version=parent._current_model_version(),
    )

    open_deleted = (counts.get("deleted_refs") or {}).get(open_label) or []
    if open_deleted:
        mirror = getattr(parent, "delete_reported_shapes", None)
        applied = mirror(open_deleted) if callable(mirror) else 0
        if applied != len(open_deleted):
            # Canvas and file disagree about which boxes were live. Reloading
            # loses the undo step, but showing a canvas that no longer matches
            # the file on disk is worse.
            logger.warning(
                "Stale cleanup: canvas mirror applied %d of %d, "
                "reloading %s" % (applied, len(open_deleted), open_label)
            )
            parent.load_file(filename)
    refresh = getattr(parent, "_refresh_file_panel", None)
    if callable(refresh):
        refresh()

    if counts["backup_failed"]:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "备份失败，已放弃删除，标注文件未作修改。"
            ),
            "warning",
        )
        return
    message, icon, skipped = stale_cleanup_result(counts, open_deleted)
    _notify(parent, message, icon)
    if skipped:
        logger.info(
            "Stale cleanup skipped %d boxes (locked=%d, changed=%d, "
            "unavailable=%d)"
            % (
                skipped,
                counts["skipped_locked"],
                counts["skipped_changed"],
                counts["skipped_unavailable"],
            )
        )
    dialog.reject()
