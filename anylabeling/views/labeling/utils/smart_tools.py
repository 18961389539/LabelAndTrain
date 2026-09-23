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
import shutil
import time

from PyQt6.QtCore import Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
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
    stamp_model_shapes,
)
from anylabeling.views.labeling.utils._io import save_json
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
from anylabeling.views.labeling.utils.archiver import (
    ARCHIVE_DIRNAME,
    archive_duplicates_plan,
    finalize_moves,
)
from anylabeling.views.labeling.utils.data_audit import audit_dataset
from anylabeling.views.labeling.utils.data_intel import (
    analyze_distribution,
    find_duplicate_groups,
    find_missing_predictions,
    mine_hard_examples,
    suggest_balancing,
)
from anylabeling.views.labeling.utils.review_queue import next_review_target
from anylabeling.views.labeling.utils.training_advisor import (
    history_summary,
    preflight_checks,
    recommend_training_config,
)
from anylabeling.views.labeling.utils.qt import new_icon_path
from anylabeling.views.labeling.utils.theme import get_theme
from anylabeling.views.labeling.widgets import Popup

__all__ = [
    "label_dir_for",
    "run_backup_restore",
    "run_duplicate_archive",
    "run_missing_scan",
    "run_review_jump",
    "run_smart_analysis",
    "run_stale_model_audit",
    "run_template_propagation",
    "run_threshold_calibration",
    "run_training_advice",
    "show_iteration_dashboard",
    "watch_relabel_result",
]

HARD_EXAMPLE_LIMIT = 50
RESULT_PATH_ROLE = Qt.ItemDataRole.UserRole
RESULT_CATEGORY_ROLE = Qt.ItemDataRole.UserRole + 1
RESULT_DETAIL_ROLE = Qt.ItemDataRole.UserRole + 2
# Where a row points at one specific shape: {"index", "label", "marker"}.
RESULT_SHAPE_REF_ROLE = Qt.ItemDataRole.UserRole + 3


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------
def _label_file_for_image(image_path, directory):
    """Label json path for an image, honouring a separate output dir."""
    label_file = osp.splitext(image_path)[0] + ".json"
    if directory:
        label_file = osp.join(directory, osp.basename(label_file))
    return label_file


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
            label.setStyleSheet(
                f"color: {get_theme()['text_secondary']}; font-size: 12px;"
            )
            layout.addWidget(label)

        self.setStyleSheet(_dialog_style())

    def add_category(self, title, rows):
        """``rows`` is ``(text, detail, image_path_or_None)`` per entry.

        A fourth element is accepted and stored as the shape reference, so a
        row can point at one shape instead of one image.
        """
        from PyQt6.QtGui import QFont

        root = QTreeWidgetItem([f"{title}（{len(rows)}）", ""])
        font = QFont()
        font.setBold(True)
        root.setFont(0, font)
        root.setForeground(0, QColor(get_theme()["highlight_text"]))
        for row in rows:
            text, detail, image_path = row[0], row[1], row[2]
            shape_ref = row[3] if len(row) > 3 else None
            child = QTreeWidgetItem([text, detail or ""])
            child.setData(0, RESULT_PATH_ROLE, image_path or "")
            child.setData(0, RESULT_CATEGORY_ROLE, title)
            child.setData(1, RESULT_DETAIL_ROLE, detail or "")
            if shape_ref is not None:
                child.setData(0, RESULT_SHAPE_REF_ROLE, shape_ref)
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
                    "shape_ref": item.data(0, RESULT_SHAPE_REF_ROLE),
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
        QTreeWidget::item:hover {{ background-color: {theme["background_hover"]}; }}
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
        QPushButton:pressed {{ background-color: {theme["surface_pressed"]}; }}
    """


def _highlight_button():
    """Accent style for the primary action in smart-tool dialogs."""
    from anylabeling.views.labeling.utils.style import (
        get_highlight_button_style,
    )

    return get_highlight_button_style(compact=True)


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
        parent, parent.tr("正在分析数据集…"), len(entries)
    )
    thread = _SmartTaskThread(_job, total=len(entries))
    thread.progress_updated.connect(
        lambda done, total: progress.setValue(min(total, done))
    )
    thread.error_occurred.connect(
        lambda message: (
            progress.close(),
            logger.error(f"Smart analysis failed: {message}"),
            _notify(parent, parent.tr("分析失败：%1").replace("%1", message), "warning"),
        )
    )

    def _finish(payload):
        progress.close()
        stats, hard, duplicates = payload

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
        title.setStyleSheet(
            "font-size: 13px; font-weight: 500; padding: 2px;"
        )
        dialog.layout().insertWidget(0, title)
        _append_result_dialog_actions(
            dialog, parent, directory, parent.tr("数据智能分析")
        )

        dialog.exec()

    thread.result_ready.connect(_finish)
    progress.canceled.connect(thread.request_cancel)
    parent._smart_analysis_thread = thread
    thread.start()


# --------------------------------------------------------------------------
# background task thread
# --------------------------------------------------------------------------
class _SmartTaskThread(QThread):
    """Run a pure compute job off the UI thread.

    The job receives an ``emit_progress(done, total)`` callable and returns
    a single payload; errors are routed to :attr:`error_occurred`. Keeps
    hash-heavy scans (duplicates, template matching) from freezing the UI.
    """

    progress_updated = pyqtSignal(int, int)
    result_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, fn, total=1):
        super().__init__()
        self._fn = fn
        self._total = max(1, total)
        self._cancel_requested = False

    def run(self):
        try:
            result = self._fn(self._emit_progress)
        except Exception as exc:  # noqa: BLE001
            self.error_occurred.emit(str(exc))
            return
        self.result_ready.emit(result)

    def _emit_progress(self, done, total=0):
        if self._cancel_requested:
            return
        self.progress_updated.emit(int(done), int(total) or self._total)

    def request_cancel(self):
        self._cancel_requested = True


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
        write_button.setStyleSheet(_highlight_button())

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
        stamp_model_shapes(
            payloads,
            parent._current_model_identity(),
            parent._current_model_version(),
        )
        shapes = data.setdefault("shapes", [])
        existing = {shape_marker(shape) for shape in shapes}
        for payload in payloads:
            marker = shape_marker(payload)
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
# stale model-box cleanup (used by action 10)
# --------------------------------------------------------------------------
BACKUP_ROOT_NAME = ".label_backups"
# ``20260923_101112``, with a ``_1`` suffix when two snapshots land in the same
# second -- both stay prunable, and neither merges into the other.
BACKUP_STAMP_PATTERN = re.compile(r"\d{8}_\d{6}(_\d+)?$")
# Files outside the canvas undo stack can only come back from these snapshots.
BACKUP_KEEP_RUNS = 20


def _prune_backup_runs(backup_root):
    """Drop our own oldest timestamped backup runs beyond the retention."""
    try:
        names = [
            name
            for name in os.listdir(backup_root)
            if BACKUP_STAMP_PATTERN.fullmatch(name)
            and osp.isdir(osp.join(backup_root, name))
        ]
    except OSError:
        return
    for name in sorted(names, reverse=True)[BACKUP_KEEP_RUNS:]:
        try:
            shutil.rmtree(osp.join(backup_root, name))
        except OSError as exc:
            logger.warning(f"Could not prune label backup run {name}: {exc}")


def _new_backup_dir(backup_root, stamp):
    """Reserve an empty run directory, so same-second runs do not overwrite."""
    candidate = stamp
    suffix = 1
    while osp.isdir(osp.join(backup_root, candidate)):
        candidate = f"{stamp}_{suffix}"
        suffix += 1
    return osp.join(backup_root, candidate)


def backup_label_files(label_files, label_dir, stamp):
    """Copy the label files that are about to change into a backup run.

    Returns ``None`` when the backup could not be completed, which the caller
    must treat as "do not change anything".
    """
    backup_root = osp.join(label_dir, BACKUP_ROOT_NAME)
    try:
        os.makedirs(backup_root, exist_ok=True)
        destination = _new_backup_dir(backup_root, stamp)
        os.makedirs(destination)
        for label_file in label_files:
            shutil.copy2(
                label_file, osp.join(destination, osp.basename(label_file))
            )
    except OSError as exc:
        logger.warning(f"Label backup failed: {exc}")
        return None
    _prune_backup_runs(backup_root)
    return destination


def list_label_backups(label_dir):
    """Snapshot runs under ``.label_backups``, newest first.

    Entries are ``(name, path, file_count)``: the picker needs to say what a
    run would put back before the user commits to overwriting labels.
    """
    backup_root = osp.join(label_dir or "", BACKUP_ROOT_NAME)
    try:
        names = os.listdir(backup_root)
    except OSError:
        return []
    runs = []
    for name in names:
        path = osp.join(backup_root, name)
        if not BACKUP_STAMP_PATTERN.fullmatch(name) or not osp.isdir(path):
            continue
        try:
            count = len([f for f in os.listdir(path) if f.endswith(".json")])
        except OSError:
            continue
        runs.append((name, path, count))
    runs.sort(key=lambda run: run[0], reverse=True)
    return runs


def plan_backup_restore(backup_dir, label_dir, skip_files=None):
    """Map a snapshot's jsons onto the label files they came from."""
    skipped = {
        osp.normpath(osp.abspath(path)) for path in (skip_files or ())
    }
    plan = {}
    try:
        names = sorted(os.listdir(backup_dir))
    except OSError:
        return plan
    for name in names:
        if not name.endswith(".json"):
            continue
        target = osp.join(label_dir, name)
        if osp.normpath(osp.abspath(target)) in skipped:
            continue
        plan[target] = osp.join(backup_dir, name)
    return plan


def restore_label_backup(backup_dir, label_dir, skip_files=None):
    """Copy a bulk-deletion snapshot back over the labels it came from.

    What gets overwritten is snapshotted first, so choosing the wrong run is
    itself reversible: the newer run in the same list is the pre-restore state.
    """
    result = {
        "restored": 0,
        "skipped": 0,
        "undo_dir": None,
        "backup_failed": False,
    }
    plan = plan_backup_restore(backup_dir, label_dir, skip_files)
    result["skipped"] += len(skip_files or ())
    if not plan:
        return result
    present = [target for target in plan if osp.isfile(target)]
    result["undo_dir"] = backup_label_files(
        present, label_dir, time.strftime("%Y%m%d_%H%M%S")
    )
    if result["undo_dir"] is None:
        result["backup_failed"] = True
        result["skipped"] += len(plan)
        return result
    for target, source in plan.items():
        try:
            shutil.copy2(source, target)
        except OSError as exc:
            logger.warning(f"Label restore failed for {target}: {exc}")
            result["skipped"] += 1
            continue
        result["restored"] += 1
    return result


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


# --------------------------------------------------------------------------
# action 5: smart review queue navigation
# --------------------------------------------------------------------------
def run_review_jump(parent, forward=True):
    """Open the next/previous image that still needs human review."""
    directory = label_dir_for(parent)
    if not directory:
        _notify(parent, parent.tr("请先打开一个图片文件夹。"), "warning")
        return
    entries = list(_label_entries(parent))
    if not entries:
        _notify(parent, parent.tr("当前没有可分析的图片。"), "warning")
        return

    results = audit_dataset([path for path, _ in entries], directory)
    queue = [osp.normpath(osp.abspath(p)) for p in (results.get("review") or [])]
    if not queue:
        _notify(parent, parent.tr("太棒了，暂无待复核图片。"))
        return

    current = None
    if parent.filename:
        current = osp.normpath(osp.abspath(parent.filename))
    target, index = next_review_target(queue, current, forward=forward)
    if target is None:
        _notify(parent, parent.tr("已到复核队列末尾。"), "info")
        return
    parent.load_file(target)
    status = getattr(parent, "status", None)
    if callable(status):
        status(parent.tr("待复核队列 %1/%2").replace("%1", str(index + 1)).replace("%2", str(len(queue))))


# --------------------------------------------------------------------------
# action 6: one-click duplicate archive
# --------------------------------------------------------------------------
def run_duplicate_archive(parent):
    """Move near-duplicate images (and their sidecars) out of the folder."""
    directory = label_dir_for(parent)
    if not directory:
        _notify(parent, parent.tr("请先打开一个图片文件夹。"), "warning")
        return
    paths = _image_list(parent)
    if not paths:
        _notify(parent, parent.tr("当前没有可分析的图片。"), "warning")
        return

    progress = _make_progress_dialog(
        parent, parent.tr("正在查找重复图片…"), max(1, len(paths))
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
        _notify(parent, parent.tr("没有发现可归档的重复图片。"))
        return
    images = [src for src, _ in plan if _looks_like_image(src)]
    answer = QMessageBox.question(
        parent,
        parent.tr("一键去重归档"),
        parent.tr(
            "将归档 %1 张重复图片及其标注到「%2」文件夹，是否继续？"
        ).replace("%1", str(len(images))).replace("%2", ARCHIVE_DIRNAME),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer != QMessageBox.StandardButton.Yes:
        return

    moved, _skipped = finalize_moves(plan)
    # If the file we are looking at got archived, move on.
    reloader = getattr(parent, "import_image_folder", None)
    if callable(reloader) and osp.isdir(directory):
        try:
            reloader(directory, load=False)
        except Exception:  # noqa: BLE001
            logger.warning("Duplicate archive: failed to reload file list")
    _notify(
        parent,
        parent.tr("已归档 %1 项（打开「%2」文件夹可查）").replace("%1", str(len(moved))).replace("%2", ARCHIVE_DIRNAME),
    )


def _looks_like_image(path):
    from anylabeling.views.labeling.utils.image import (
        get_supported_image_extensions,
    )

    return osp.splitext(str(path))[1].lower() in set(
        get_supported_image_extensions()
    )


# --------------------------------------------------------------------------
# action 7: training advice
# --------------------------------------------------------------------------
def run_training_advice(parent):
    """Pre-flight checks plus suggested hyperparameters for the next round."""
    directory = label_dir_for(parent)
    if not directory:
        _notify(parent, parent.tr("请先打开一个图片文件夹。"), "warning")
        return
    entries = list(_label_entries(parent))
    if not entries:
        _notify(parent, parent.tr("当前没有可分析的图片。"), "warning")
        return

    stats = analyze_distribution(entries)
    history = load_history(directory)
    hist_info = history_summary(history)

    max_dim = None
    image = getattr(parent, "image", None)
    if image is not None and not image.isNull():
        max_dim = max(image.width(), image.height())

    checks = preflight_checks(stats)
    advice = recommend_training_config(stats, history=hist_info, max_image_dim=max_dim)

    dialog = _ResultDialog(
        parent,
        parent.tr("训练建议"),
        parent.tr("训练前预检与下一轮超参初值，可按推荐手动填入训练面板。"),
    )
    dialog.add_category(
        parent.tr("预检"),
        [(check["message"], "", "") for check in checks],
    )
    dialog.add_category(
        parent.tr("推荐初值"),
        [
            (
                f"Epochs={advice['epochs']} · Batch={advice['batch']} · imgsz={advice['imgsz']}",
                advice["text"],
                "",
            )
        ],
    )
    _append_result_dialog_actions(
        dialog, parent, directory, parent.tr("训练建议")
    )
    dialog.exec()


# --------------------------------------------------------------------------
# action 10: stale model-box audit (report only; cleanup stays manual)
# --------------------------------------------------------------------------


def run_stale_model_audit(parent):
    """List boxes produced by a model other than the one currently loaded.

    Deliberately report-only: a box may have been corrected by hand after the
    old model drew it, so deleting requires looking at the list first.
    """
    directory = label_dir_for(parent)
    if not directory:
        _notify(parent, parent.tr("请先打开一个图片文件夹。"), "warning")
        return
    entries = list(_label_entries(parent))
    if not entries:
        _notify(parent, parent.tr("当前没有可分析的图片。"), "warning")
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
            ) or parent.tr("未记录来源")
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
        parent.tr("旧轮模型框盘点"),
        parent.tr(
            "双击条目可跳转到对应图片；勾选条目后可删除。被锁定的框、"
            "来源不明的框以及期间被改动过的框都不会被删除。"
        ),
    )
    dialog.add_category(
        parent.tr("概览"),
        [
            (
                parent.tr("当前模型：%1").replace(
                    "%1",
                    model_identity_label(current_model, current_version)
                    or parent.tr("未加载"),
                ),
                "",
                "",
            ),
            (
                parent.tr("可清理的旧轮模型框 %1 个").replace(
                    "%1", str(stale_total)
                ),
                parent.tr("由其它模型产生，未被本轮结果覆盖"),
                "",
            ),
            (
                parent.tr("本轮模型框 %1 个").replace(
                    "%1", str(current_model_boxes)
                ),
                "",
                "",
            ),
            (
                parent.tr("人工框 %1 个").replace(
                    "%1", str(counts[SOURCE_HUMAN])
                ),
                "",
                "",
            ),
            (
                parent.tr("来源不明 %1 个").replace(
                    "%1", str(counts[SOURCE_UNKNOWN])
                ),
                parent.tr("早于来源记录功能，不参与清理"),
                "",
            ),
        ],
    )
    for producer in sorted(by_producer):
        dialog.add_category(
            parent.tr("来自 %1（%2 个）").replace("%1", producer).replace(
                "%2", str(len(by_producer[producer]))
            ),
            by_producer[producer],
        )
    if not by_producer:
        dialog.add_category(
            parent.tr("可清理项"),
            [(parent.tr("没有其它模型留下的框"), "", "")],
        )
    delete_button = QPushButton(parent.tr("删除所选"))
    delete_button.clicked.connect(
        lambda: _delete_reported_stale(parent, dialog)
    )
    _append_result_dialog_actions(
        dialog,
        parent,
        directory,
        parent.tr("旧轮模型框盘点"),
        extra_buttons=[delete_button],
    )
    dialog.exec()


def _delete_reported_stale(parent, dialog):
    """Delete exactly the stale boxes the reviewed report has selected."""
    rows = [row for row in dialog.selected_rows() if row.get("shape_ref")]
    if not rows:
        _notify(parent, parent.tr("请先在列表中选择要删除的框。"), "warning")
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
        parent.tr("删除旧轮模型框"),
        parent.tr(
            "将从 %1 个文件中删除选中的 %2 个框。\n"
            "锁定、来源不明以及报告之后被改动过的框会自动跳过。\n"
            "当前打开的图片删除后可用 Ctrl+Z 撤销；其余文件删除前会先备份到 "
            ".label_backups，之后可用「从备份恢复标注」取回。"
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
        open_label = _label_file_for_image(
            filename, label_dir_for(parent)
        )
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
            parent.tr("备份失败，已放弃删除，标注文件未作修改。"),
            "warning",
        )
        return
    if counts["deleted"]:
        message = (
            parent.tr("已删除 %1 个框（涉及 %2 个文件），备份在 %3")
            .replace("%1", str(counts["deleted"]))
            .replace("%2", str(counts["files"]))
            .replace(
                "%3",
                osp.basename(counts["backup_dir"] or "")
                or parent.tr("未备份"),
            )
        )
        if open_deleted:
            message += parent.tr("；当前图片可直接 Ctrl+Z 撤销")
        _notify(parent, message, "copy-green")
    else:
        _notify(parent, parent.tr("没有框被删除。"), "warning")
    skipped = (
        counts["skipped_locked"]
        + counts["skipped_changed"]
        + counts["skipped_unavailable"]
    )
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


def run_backup_restore(parent):
    """Put back the label files a bulk deletion overwrote.

    Only the image open in the canvas has a real undo; every other file a
    deletion touched comes back from its snapshot, which is what this lists.
    """
    directory = label_dir_for(parent)
    if not directory:
        _notify(parent, parent.tr("请先打开一个图片文件夹。"), "warning")
        return
    runs = list_label_backups(directory)
    if not runs:
        _notify(
            parent,
            parent.tr("没有找到标注备份（%1 下没有快照）。").replace(
                "%1", BACKUP_ROOT_NAME
            ),
            "warning",
        )
        return
    entries = [
        parent.tr("%1（%2 个文件）")
        .replace("%1", name)
        .replace("%2", str(count))
        for name, _path, count in runs
    ]
    choice, ok = QInputDialog.getItem(
        parent,
        parent.tr("从备份恢复标注"),
        parent.tr("选择要恢复的备份（最新在前）："),
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
        parent.tr("从备份恢复标注"),
        parent.tr(
            "将用备份 %1 中的 %2 个文件覆盖当前标注。\n"
            "被覆盖的文件会先写入一个新的备份；选错了就在列表里再选更新的那一项。\n"
            "当前打开且有未保存改动的图片不会被覆盖。"
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
            parent.tr("备份当前标注失败，已放弃恢复，文件未作修改。"),
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
            parent.tr("已恢复 %1 个标注文件，被覆盖的版本备份在 %2")
            .replace("%1", str(result["restored"]))
            .replace("%2", osp.basename(result["undo_dir"] or "") or "?"),
            "copy-green",
        )
    else:
        _notify(parent, parent.tr("没有文件被恢复。"), "warning")


# --------------------------------------------------------------------------
# action 9: smart template pre-labeling (batch)
# --------------------------------------------------------------------------
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
        _notify(parent, parent.tr("请先打开一个图片文件夹。"), "warning")
        return
    entries = list(_label_entries(parent))
    if not entries:
        _notify(parent, parent.tr("当前没有可分析的图片。"), "warning")
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
        _notify(parent, parent.tr("至少需要一张已标注图片作为模板。"), "warning")
        return
    if not targets:
        _notify(parent, parent.tr("没有未标注的图片需要预标注。"))
        return

    def _job(emit_progress):
        return plan_template_propagation(
            directory,
            targets,
            templates,
            progress=lambda done, total: emit_progress(done, total),
        )

    progress = _make_progress_dialog(
        parent, parent.tr("正在匹配相似模板并生成预标注…"), len(targets)
    )
    thread = _SmartTaskThread(_job, total=len(targets))
    thread.progress_updated.connect(
        lambda done, total: progress.setValue(min(total, done))
    )
    thread.error_occurred.connect(
        lambda message: (
            progress.close(),
            logger.error(f"Template propagation failed: {message}"),
            _notify(parent, parent.tr("匹配失败：%1").replace("%1", message), "warning"),
        )
    )

    def _finish(batch):
        progress.close()
        if not batch:
            _notify(parent, parent.tr("没有找到与已标注模板足够相似的未标注图片。"))
            return

        dialog = _ResultDialog(
            parent,
            parent.tr("智能模板预标注"),
            parent.tr(
                "每张未标注图片按相似度匹配一张已标注模板生成预标注框，"
                "请先人工抽查再批量写入。"
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
        dialog.add_category(parent.tr("可预标注的图片"), rows)
        write_button = QPushButton(parent.tr("写入预标注"))
        write_button.setStyleSheet(_highlight_button())

        def _write():
            written, failed = _write_prelabels(parent, batch)
            dialog.accept()
            if failed:
                _notify(
                    parent,
                    parent.tr("已写入 %1 项，%2 项失败。").replace("%1", str(written)).replace("%2", str(failed)),
                    "warning",
                )
            else:
                _notify(
                    parent,
                    parent.tr("已写入 %1 张图片的预标注。").replace("%1", str(written)),
                )

        write_button.clicked.connect(_write)
        _append_result_dialog_actions(
            dialog,
            parent,
            directory,
            parent.tr("智能模板预标注"),
            extra_buttons=[write_button],
        )
        dialog.exec()

    thread.result_ready.connect(_finish)
    progress.canceled.connect(thread.request_cancel)
    parent._template_propagation_thread = thread
    thread.start()


def _write_prelabels(parent, batch):
    """Write planned shapes into each target label json. Returns ``(n, n_fail)``."""
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
            with open(label_file, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            written += 1
        except OSError as exc:
            logger.warning(f"Template propagation: failed to write {label_file}: {exc}")
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
