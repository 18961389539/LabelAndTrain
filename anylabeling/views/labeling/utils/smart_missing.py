"""Missing-annotation scan: the background predictor and the writer."""

from __future__ import annotations

import os.path as osp
from PyQt6.QtCore import (
    QCoreApplication,
    QThread,
    pyqtSignal,
)
from PyQt6.QtWidgets import QPushButton
from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.provenance import (
    shape_marker,
    stamp_model_shapes,
)
from anylabeling.views.labeling.utils._io import save_json
from anylabeling.views.labeling.utils.smart_ui import (
    _ResultDialog,
    _append_result_dialog_actions,
    _highlight_button,
    _notify,
    label_dir_for,
)
from anylabeling.views.labeling.utils.active_learning import DEFAULT_ACCEPT
from anylabeling.views.labeling.utils.data_intel import (
    find_missing_predictions,
)

from .smart_common import (
    _label_entries,
    _read_label,
)
from .smart_ui import _make_progress_dialog


class _MissingScanThread(QThread):
    progress_updated = pyqtSignal(int, str)
    results_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self, app, entries, iou_threshold, min_score):
        super().__init__()
        self.app = app
        self.entries = entries
        self.iou_threshold = iou_threshold
        self.min_score = min_score
        self._results = []
        self._cancelled = False

    def request_cancel(self):
        self._cancelled = True

    def run(self):
        total = len(self.entries)
        try:
            for index, (image_path, data) in enumerate(self.entries):
                if self._cancelled:
                    break
                annotations = (data or {}).get("shapes") or []
                try:
                    result = self.app.auto_labeling_widget.model_manager.predict_shapes(
                        self.app.image, image_path, batch=True
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        f"Missing scan: prediction failed for {image_path}: {exc}"
                    )
                    result = None
                predictions = (
                    getattr(result, "shapes", None) if result else None
                )
                if predictions:
                    missing = find_missing_predictions(
                        predictions,
                        annotations,
                        iou_threshold=self.iou_threshold,
                        min_score=self.min_score,
                    )
                    if missing:
                        self._results.append(
                            (image_path, _shapes_to_payloads(missing))
                        )
                self.progress_updated.emit(index + 1, f"{index + 1}/{total}")
            self.results_ready.emit(self._results)
        except Exception as exc:  # noqa: BLE001
            self.error_occurred.emit(str(exc))


def _shapes_to_payloads(shapes):
    payloads = []
    for shape in shapes:
        if hasattr(shape, "to_dict"):
            try:
                payloads.append(shape.to_dict())
                continue
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Dropping a shape that failed to serialize "
                    f"(label={getattr(shape, 'label', '?')}): {e}"
                )
        if isinstance(shape, dict):
            payloads.append(dict(shape))
    return payloads


def run_missing_scan(parent, iou_threshold=0.5, min_score=DEFAULT_ACCEPT):
    """Find boxes the model is confident about but nobody labelled."""
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

    manager = getattr(
        getattr(parent, "auto_labeling_widget", None), "model_manager", None
    )
    if (
        manager is None
        or getattr(manager, "loaded_model_config", None) is None
    ):
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "请先加载一个自动标注模型。"
            ),
            "warning",
        )
        return

    entries = [
        (path, data)
        for path, data in _label_entries(parent)
        if data is not None
    ]
    if not entries:
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "当前没有已标注的图片可供比对。"
            ),
            "warning",
        )
        return

    progress = _make_progress_dialog(
        parent,
        QCoreApplication.translate("LabelingWidget", "正在扫描疑似漏标…"),
        len(entries),
    )
    dialog = _ResultDialog(
        parent,
        QCoreApplication.translate("LabelingWidget", "疑似漏标"),
        QCoreApplication.translate(
            "LabelingWidget",
            "模型给出高置信度框但标注中没有对应目标。"
            "确认后可点「写入标注」直接补充。",
        ),
    )

    results = []

    def _on_progress(value, label):
        progress.setValue(value)
        progress.setLabelText(label)

    def _on_results(found):
        results.extend(found)

    def _on_error(message):
        logger.error(f"Missing scan failed: {message}")
        progress.close()

    def _finish():
        progress.close()
        rows = []
        for image_path, payloads in results:
            for payload in payloads:
                score = payload.get("score")
                rows.append(
                    (
                        osp.basename(image_path),
                        f"{payload.get('label', '?')}"
                        + (
                            f" · {float(score):.2f}"
                            if isinstance(score, (int, float))
                            else ""
                        ),
                        image_path,
                    )
                )
        if not rows:
            rows = [
                (
                    QCoreApplication.translate(
                        "LabelingWidget", "未发现疑似漏标"
                    ),
                    "",
                    "",
                )
            ]
        dialog.add_category(
            QCoreApplication.translate("LabelingWidget", "疑似漏标的框"), rows
        )
        write_button = QPushButton(
            QCoreApplication.translate("LabelingWidget", "写入标注")
        )
        write_button.setStyleSheet(_highlight_button())

        def _write():
            written, failed = _write_missing(parent, results)
            dialog.accept()
            if failed:
                _notify(
                    parent,
                    QCoreApplication.translate(
                        "LabelingWidget",
                        "已补充 %1 个标注框，%2 个文件写入失败。",
                    )
                    .replace("%1", str(written))
                    .replace("%2", str(failed)),
                    "warning",
                )
                return
            _notify(
                parent,
                QCoreApplication.translate(
                    "LabelingWidget", "已补充 %1 个标注框。"
                ).replace("%1", str(written)),
            )

        write_button.clicked.connect(_write)
        _append_result_dialog_actions(
            dialog,
            parent,
            directory,
            QCoreApplication.translate("LabelingWidget", "疑似漏标"),
            extra_buttons=[write_button],
        )
        dialog.exec()

    thread = _MissingScanThread(parent, entries, iou_threshold, min_score)
    thread.progress_updated.connect(_on_progress)
    thread.results_ready.connect(_on_results)
    thread.error_occurred.connect(_on_error)
    thread.finished.connect(_finish)
    progress.canceled.connect(thread.request_cancel)
    parent._missing_scan_thread = thread
    thread.start()


def _write_missing(parent, results):
    """Append accepted predictions to their label files."""
    from anylabeling.views.labeling.utils.session_snapshot import (
        snapshot_before_label_write,
    )

    directory = label_dir_for(parent)
    written = 0
    failed = 0
    for image_path, payloads in results:
        label_file = osp.splitext(image_path)[0] + ".json"
        if directory:
            label_file = osp.join(directory, osp.basename(label_file))
        data = _read_label(label_file)
        if data is None:
            logger.warning(
                f"Missing scan: no readable label file for {image_path}"
            )
            failed += 1
            continue
        stamp_model_shapes(
            payloads,
            parent._current_model_identity(),
            parent._current_model_version(),
        )
        shapes = data.setdefault("shapes", [])
        existing = {shape_marker(shape) for shape in shapes}
        added = 0
        for payload in payloads:
            marker = shape_marker(payload)
            if marker is not None and marker in existing:
                continue
            if marker is not None:
                existing.add(marker)
            shapes.append(payload)
            added += 1
        if not added:
            continue
        try:
            snapshot_before_label_write(label_file)
            save_json(data, label_file, indent=2, ensure_ascii=False)
        except OSError as exc:
            logger.warning(
                f"Missing scan: failed to write {label_file}: {exc}"
            )
            failed += 1
            continue
        written += added
    return written, failed
