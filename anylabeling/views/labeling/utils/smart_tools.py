"""Smart tooling UI: threshold calibration, dataset intelligence and the
active-learning iteration dashboard.

The heavy lifting lives in :mod:`active_learning` and :mod:`data_intel`; this
module only wires them to the ``LabelWidget`` (``parent``) so the actions can
be reached from the menu.
"""

from __future__ import annotations

import json
import os
import os.path as osp
import re
import time

from PyQt6.QtCore import Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressDialog,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils.active_learning import (
    DEFAULT_ACCEPT,
    DEFAULT_REVIEW,
    MIN_CALIBRATION_SAMPLES,
    append_iteration,
    calibrate_thresholds,
    collect_score_samples,
    count_annotations,
    format_iteration_summary,
    load_history,
    load_thresholds,
    save_thresholds,
    suggest_next_step,
    update_last_iteration,
)
from anylabeling.views.labeling.utils.data_intel import (
    analyze_distribution,
    find_duplicate_groups,
    find_missing_predictions,
    mine_hard_examples,
    suggest_balancing,
)
from anylabeling.views.labeling.utils.qt import new_icon_path
from anylabeling.views.labeling.utils.theme import get_theme
from anylabeling.views.labeling.widgets import Popup

__all__ = [
    "label_dir_for",
    "run_missing_scan",
    "run_smart_analysis",
    "run_threshold_calibration",
    "show_iteration_dashboard",
    "watch_relabel_result",
]

HARD_EXAMPLE_LIMIT = 50
RESULT_PATH_ROLE = Qt.ItemDataRole.UserRole
RESULT_CATEGORY_ROLE = Qt.ItemDataRole.UserRole + 1
RESULT_DETAIL_ROLE = Qt.ItemDataRole.UserRole + 2


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------
def label_dir_for(parent):
    """Folder that actually holds the label json files."""
    directory = getattr(parent, "output_dir", None) or None
    if not directory and getattr(parent, "filename", None):
        directory = osp.dirname(parent.filename)
    return directory


def _image_list(parent):
    return [path for path in (getattr(parent, "image_list", None) or [])]


def _read_label(label_file):
    if not osp.isfile(label_file):
        return None
    try:
        with open(label_file, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _label_entries(parent):
    """Yield ``(image_path, data_or_None)`` for every open image."""
    directory = label_dir_for(parent)
    for image_path in _image_list(parent):
        label_file = osp.splitext(image_path)[0] + ".json"
        if directory:
            label_file = osp.join(directory, osp.basename(label_file))
        yield image_path, _read_label(label_file)


def _confirmed_lookup(parent):
    """Map of normalised image path -> human-checked flag."""
    mapping = {}
    widget = getattr(parent, "file_list_widget", None)
    checked_getter = getattr(parent, "_file_item_annotation_checked", None)
    if widget is None or checked_getter is None:
        return mapping
    for row in range(widget.count()):
        item = widget.item(row)
        if item is None:
            continue
        try:
            mapping[osp.normpath(osp.abspath(item.text()))] = bool(
                checked_getter(item)
            )
        except Exception:  # noqa: BLE001
            continue
    return mapping


def _notify(parent, message, icon="copy-green"):
    popup = Popup(message, parent, icon=new_icon_path(icon, "svg"))
    popup.show_popup(parent, popup_height=65, position="center")
    return popup


# --------------------------------------------------------------------------
# generic result dialog
# --------------------------------------------------------------------------
class _ResultDialog(QDialog):
    """Tree dialog shared by the smart actions.

    Each top-level node is a category; leaves carry an image path in
    ``UserRole`` so double-clicking jumps to the image.
    """

    def __init__(self, parent, title, hint=None):
        super().__init__(parent)
        self._parent = parent
        self.setWindowTitle(title)
        self.resize(620, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([parent.tr("项目"), parent.tr("说明")])
        self.tree.setColumnWidth(0, 300)
        self.tree.setRootIsDecorated(True)
        self.tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.tree)

        if hint:
            label = QLabel(hint)
            label.setWordWrap(True)
            label.setStyleSheet("color: #86868b; font-size: 12px;")
            layout.addWidget(label)

        self.setStyleSheet(_dialog_style())

    def add_category(self, title, rows):
        """``rows`` is a list of ``(text, detail, image_path_or_None)``."""
        root = QTreeWidgetItem([f"{title}（{len(rows)}）", ""])
        for text, detail, image_path in rows:
            child = QTreeWidgetItem([text, detail or ""])
            child.setData(0, RESULT_PATH_ROLE, image_path or "")
            child.setData(0, RESULT_CATEGORY_ROLE, title)
            child.setData(1, RESULT_DETAIL_ROLE, detail or "")
            root.addChild(child)
        self.tree.addTopLevelItem(root)
        root.setExpanded(True)
        return root

    def _on_double_click(self, item, _column):
        image_path = item.data(0, RESULT_PATH_ROLE)
        if image_path and osp.exists(image_path):
            self.accept()
            self._parent.load_file(image_path)

    def _rows_from_items(self, items):
        rows = []
        for item in items:
            if item.childCount() > 0:
                continue
            rows.append(
                {
                    "category": item.data(0, RESULT_CATEGORY_ROLE) or "",
                    "text": item.text(0),
                    "detail": item.data(1, RESULT_DETAIL_ROLE) or item.text(1),
                    "image_path": item.data(0, RESULT_PATH_ROLE) or "",
                }
            )
        return rows

    def selected_rows(self):
        return self._rows_from_items(self.tree.selectedItems())

    def all_rows(self):
        items = []
        for index in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(index)
            for row in range(root.childCount()):
                items.append(root.child(row))
        return self._rows_from_items(items)


def _dialog_style():
    theme = get_theme()
    return f"""
        QDialog {{ background-color: {theme["background"]}; }}
        QTreeWidget {{
            background-color: {theme["surface"]};
            border: 1px solid {theme["border"]};
            border-radius: 8px;
            color: {theme["text"]};
            font-size: 13px;
            padding: 6px;
        }}
        QTreeWidget::item {{ padding: 3px 2px; }}
        QTreeWidget::item:selected {{ background-color: {theme["primary"]}; }}
        QPushButton {{
            background-color: {theme["surface"]};
            border: 1px solid {theme["border"]};
            border-radius: 6px;
            color: {theme["text"]};
            font-size: 13px;
            height: 32px;
            padding: 0 14px;
        }}
        QPushButton:hover {{ background-color: {theme["background_hover"]}; }}
    """


def _result_rows(dialog):
    selected = dialog.selected_rows()
    return selected or dialog.all_rows()


def _safe_export_name(title):
    safe = re.sub(r"[\\\\/:*?\"<>|\\s]+", "_", title or "results").strip("_")
    return safe or "results"


def _export_dialog_rows(dialog, parent, directory, title):
    rows = _result_rows(dialog)
    if not rows:
        _notify(parent, parent.tr("当前没有可导出的结果。"), "warning")
        return None
    export_dir = directory or label_dir_for(parent) or os.getcwd()
    os.makedirs(export_dir, exist_ok=True)
    path = osp.join(
        export_dir,
        f"{_safe_export_name(title)}_{time.strftime('%Y%m%d_%H%M%S')}.csv",
    )
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write("category,item,detail,image_path\n")
        for row in rows:
            values = [
                str(row.get("category", "")).replace('"', '""'),
                str(row.get("text", "")).replace('"', '""'),
                str(row.get("detail", "")).replace('"', '""'),
                str(row.get("image_path", "")).replace('"', '""'),
            ]
            handle.write(",".join(f'"{value}"' for value in values) + "\n")
    _notify(
        parent,
        parent.tr("结果已导出：%1").replace("%1", osp.basename(path)),
    )
    return path


def _open_result_folder(dialog, parent, directory):
    rows = _result_rows(dialog)
    target = directory or label_dir_for(parent)
    for row in rows:
        image_path = row.get("image_path")
        if image_path and osp.exists(image_path):
            target = osp.dirname(image_path)
            break
    if not target:
        _notify(parent, parent.tr("没有可打开的目录。"), "warning")
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(target))


def _jump_to_result(dialog):
    for row in _result_rows(dialog):
        image_path = row.get("image_path")
        if image_path and osp.exists(image_path):
            dialog.accept()
            dialog._parent.load_file(image_path)
            return True
    return False


def _append_result_dialog_actions(
    dialog,
    parent,
    directory,
    title,
    extra_buttons=None,
    include_close=True,
):
    buttons = QHBoxLayout()
    export_button = QPushButton(parent.tr("导出 CSV"))
    open_button = QPushButton(parent.tr("打开所在目录"))
    jump_button = QPushButton(parent.tr("跳到首个结果"))
    buttons.addWidget(export_button)
    buttons.addWidget(open_button)
    buttons.addWidget(jump_button)
    buttons.addStretch()
    for button in extra_buttons or []:
        buttons.addWidget(button)
    if include_close:
        close_button = QPushButton(parent.tr("关闭"))
        close_button.clicked.connect(dialog.reject)
        buttons.addWidget(close_button)

    export_button.clicked.connect(
        lambda: _export_dialog_rows(dialog, parent, directory, title)
    )
    open_button.clicked.connect(lambda: _open_result_folder(dialog, parent, directory))
    jump_button.clicked.connect(lambda: _jump_to_result(dialog))
    dialog.layout().addLayout(buttons)


# --------------------------------------------------------------------------
# action 1: threshold calibration
# --------------------------------------------------------------------------
def run_threshold_calibration(parent):
    directory = label_dir_for(parent)
    if not directory:
        _notify(parent, parent.tr("请先打开一个图片文件夹。"), "warning")
        return None

    confirmed = _confirmed_lookup(parent)
    entries = []
    for image_path, data in _label_entries(parent):
        if data is None:
            continue
        is_confirmed = confirmed.get(osp.normpath(osp.abspath(image_path)), False)
        entries.append((data, is_confirmed))

    if not entries:
        _notify(parent, parent.tr("当前文件夹没有可用的标注，无法校准。"), "warning")
        return None

    class_scores, confirmed_scores = collect_score_samples(entries)
    if not class_scores:
        _notify(
            parent,
            parent.tr("没有带置信度的自动标注框，请先跑一次自动标注。"),
            "warning",
        )
        return None

    thresholds = calibrate_thresholds(class_scores, confirmed_scores)
    if not thresholds:
        _notify(
            parent,
            parent.tr("样本不足（至少需要 %1 个带分数的框），暂不校准。").replace(
                "%1", str(MIN_CALIBRATION_SAMPLES)
            ),
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
        parent.tr("阈值校准"),
        parent.tr(
            "已按各类的置信度分布生成自动接受/建议复核阈值，"
            "结果写入 classes_thresholds.json，并立即用于「待复核」筛选。"
        ),
    )
    rows = []
    for label, entry in sorted(thresholds.items()):
        rows.append(
            (
                label,
                parent.tr("自动接受 ≥ %1 · 建议复核 < %2 · 样本 %3")
                .replace("%1", f"{entry['accept']:.2f}")
                .replace("%2", f"{entry['review']:.2f}")
                .replace("%3", str(entry["samples"])),
                "",
            )
        )
    dialog.add_category(parent.tr("各类阈值"), rows)
    _append_result_dialog_actions(
        dialog, parent, directory, parent.tr("阈值校准")
    )
    dialog.exec()
    return thresholds


# --------------------------------------------------------------------------
# action 2: dataset intelligence
# --------------------------------------------------------------------------
def run_smart_analysis(parent):
    directory = label_dir_for(parent)
    if not directory:
        _notify(parent, parent.tr("请先打开一个图片文件夹。"), "warning")
        return

    entries = list(_label_entries(parent))
    if not entries:
        _notify(parent, parent.tr("当前没有可分析的图片。"), "warning")
        return

    progress = _make_progress_dialog(
        parent, parent.tr("正在分析数据集…"), len(entries)
    )
    paths = [path for path, _ in entries]

    stats = analyze_distribution(entries)
    progress.setValue(max(1, len(entries) // 2))

    thresholds = load_thresholds(directory)
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
        progress=lambda done, total: progress.setValue(
            min(total, len(entries) // 2 + int(done / max(total, 1) * len(entries) / 2))
        ),
    )
    progress.close()

    dialog = _ResultDialog(
        parent,
        parent.tr("数据智能分析"),
        parent.tr("双击条目可跳转到对应图片。"),
    )

    advice = suggest_balancing(stats)
    dialog.add_category(
        parent.tr("配平建议"),
        [(line, "", "") for line in advice],
    )

    dialog.add_category(
        parent.tr("难例优先复核"),
        [
            (
                osp.basename(path),
                parent.tr("不确定性 %1").replace("%1", f"{score:.2f}"),
                path,
            )
            for path, score in hard
        ]
        or [(parent.tr("暂无（所有图片都较确定）"), "", "")],
    )

    duplicate_rows = []
    for group in duplicates:
        head = group[0]
        duplicate_rows.append(
            (
                osp.basename(head),
                parent.tr("与 %1 张图重复").replace("%1", str(len(group) - 1)),
                head,
            )
        )
    dialog.add_category(
        parent.tr("疑似重复图片"),
        duplicate_rows or [(parent.tr("未发现重复图片"), "", "")],
    )

    summary = (
        parent.tr(
            "共 %1 张图 · 已标注 %2 · 标注框 %3 个 · 小目标 %4 个"
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
        dialog, parent, directory, parent.tr("数据智能分析")
    )

    dialog.exec()


def _make_progress_dialog(parent, title, maximum):
    dialog = QProgressDialog(title, parent.tr("取消"), 0, max(maximum, 1), parent)
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(380)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    dialog.setValue(0)
    dialog.setStyleSheet(
        f"""
        QProgressDialog {{ background-color: {get_theme()["background"]};
            border-radius: 12px; padding: 18px; }}
        QLabel {{ color: {get_theme()["text"]}; font-size: 13px; }}
        """
    )
    dialog.show()
    return dialog


# --------------------------------------------------------------------------
# action 3: missing-annotation scan
# --------------------------------------------------------------------------
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
                    result = (
                        self.app.auto_labeling_widget.model_manager.predict_shapes(
                            self.app.image, image_path, batch=True
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        f"Missing scan: prediction failed for {image_path}: {exc}"
                    )
                    result = None
                predictions = getattr(result, "shapes", None) if result else None
                if predictions:
                    missing = find_missing_predictions(
                        predictions,
                        annotations,
                        iou_threshold=self.iou_threshold,
                        min_score=self.min_score,
                    )
                    if missing:
                        self._results.append((image_path, _shapes_to_payloads(missing)))
                self.progress_updated.emit(
                    index + 1, f"{index + 1}/{total}"
                )
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
            except Exception:  # noqa: BLE001
                pass
        if isinstance(shape, dict):
            payloads.append(dict(shape))
    return payloads


def run_missing_scan(parent, iou_threshold=0.5, min_score=DEFAULT_ACCEPT):
    """Find boxes the model is confident about but nobody labelled."""
    directory = label_dir_for(parent)
    if not directory:
        _notify(parent, parent.tr("请先打开一个图片文件夹。"), "warning")
        return

    manager = getattr(
        getattr(parent, "auto_labeling_widget", None), "model_manager", None
    )
    if manager is None or getattr(manager, "loaded_model_config", None) is None:
        _notify(parent, parent.tr("请先加载一个自动标注模型。"), "warning")
        return

    entries = [
        (path, data)
        for path, data in _label_entries(parent)
        if data is not None
    ]
    if not entries:
        _notify(parent, parent.tr("当前没有已标注的图片可供比对。"), "warning")
        return

    progress = _make_progress_dialog(
        parent, parent.tr("正在扫描疑似漏标…"), len(entries)
    )
    dialog = _ResultDialog(
        parent,
        parent.tr("疑似漏标"),
        parent.tr(
            "模型给出高置信度框但标注中没有对应目标。"
            "确认后可点「写入标注」直接补充。"
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
            rows = [(parent.tr("未发现疑似漏标"), "", "")]
        dialog.add_category(parent.tr("疑似漏标的框"), rows)
        write_button = QPushButton(parent.tr("写入标注"))

        def _write():
            written = _write_missing(parent, results)
            dialog.accept()
            _notify(
                parent,
                parent.tr("已补充 %1 个标注框。").replace("%1", str(written)),
            )

        write_button.clicked.connect(_write)
        _append_result_dialog_actions(
            dialog,
            parent,
            directory,
            parent.tr("疑似漏标"),
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


def _shape_marker(shape):
    """Stable identity for a box so re-runs never duplicate an annotation."""
    if not isinstance(shape, dict):
        return None
    points = shape.get("points") or []
    if not points:
        return None
    rounded = tuple(
        (round(float(point[0]), 2), round(float(point[1]), 2))
        for point in points
        if isinstance(point, (list, tuple)) and len(point) >= 2
    )
    if not rounded:
        return None
    return (str(shape.get("label") or ""), rounded)


def _write_missing(parent, results):
    """Append accepted predictions to their label files."""
    directory = label_dir_for(parent)
    written = 0
    for image_path, payloads in results:
        label_file = osp.splitext(image_path)[0] + ".json"
        if directory:
            label_file = osp.join(directory, osp.basename(label_file))
        data = _read_label(label_file)
        if data is None:
            continue
        shapes = data.setdefault("shapes", [])
        existing = {_shape_marker(shape) for shape in shapes}
        for payload in payloads:
            marker = _shape_marker(payload)
            if marker is not None and marker in existing:
                continue
            if marker is not None:
                existing.add(marker)
            shapes.append(payload)
            written += 1
        try:
            with open(label_file, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.warning(f"Missing scan: failed to write {label_file}: {exc}")
    return written


# --------------------------------------------------------------------------
# action 4: iteration dashboard
# --------------------------------------------------------------------------
def show_iteration_dashboard(parent):
    directory = label_dir_for(parent)
    if not directory:
        _notify(parent, parent.tr("请先打开一个图片文件夹。"), "warning")
        return
    history = load_history(directory)
    lines = format_iteration_summary(history)

    dialog = _ResultDialog(
        parent,
        parent.tr("迭代收益看板"),
        parent.tr("每次训练并回灌标注后会自动追加一轮记录。"),
    )
    dialog.add_category(
        parent.tr("轮次"), [(line, "", "") for line in lines]
    )
    suggestion = suggest_next_step(history)
    dialog.add_category(
        parent.tr("系统建议"),
        [(parent.tr("下一步"), suggestion["reason"], "")],
    )
    _append_result_dialog_actions(
        dialog, parent, directory, parent.tr("迭代收益看板")
    )
    dialog.exec()


def watch_relabel_result(parent, directory, baseline, interval_ms=1500):
    """Once the relabel batch finishes, record what the round produced."""
    if not directory:
        return

    def _check():
        if getattr(parent, "_batch_processing_active", False):
            QTimer.singleShot(interval_ms, _check)
            return
        after = count_annotations(_image_list(parent), directory)
        new_shapes = max(
            0, after["total_shapes"] - (baseline or {}).get("total_shapes", 0)
        )
        update_last_iteration(
            directory,
            labeled_images=after["labeled_images"],
            total_shapes=after["total_shapes"],
            new_shapes=new_shapes,
        )
        logger.info(
            f"Active learning: round updated "
            f"(+{new_shapes} shapes, {after['labeled_images']} images)"
        )

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
