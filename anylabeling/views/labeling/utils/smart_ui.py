"""Shared smart-tool UI: the result tree dialog, its actions and the
background task helpers.

Every smart action populates the same tree, exports the same CSV shape and
jumps to the same kind of row. Keeping those pieces here means the action
modules no longer grow with each button they add, and the dialog can be
exercised without loading the analysis stack. The task thread and progress
dialog live here too, because four action modules share the same
cancel/progress contract.
"""

from __future__ import annotations

import os
import os.path as osp
import re
import time

from PyQt6.QtCore import (
    QCoreApplication,
    QThread,
    QUrl,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QDesktopServices
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

from anylabeling.views.labeling.utils.qt import new_icon_path
from anylabeling.views.labeling.utils.theme import get_theme
from anylabeling.views.labeling.widgets import Popup

RESULT_PATH_ROLE = Qt.ItemDataRole.UserRole
RESULT_CATEGORY_ROLE = Qt.ItemDataRole.UserRole + 1
RESULT_DETAIL_ROLE = Qt.ItemDataRole.UserRole + 2
# Where a row points at one specific shape: {"index", "label", "marker"}.
RESULT_SHAPE_REF_ROLE = Qt.ItemDataRole.UserRole + 3


def label_dir_for(parent):
    """Folder that actually holds the label json files."""
    directory = getattr(parent, "output_dir", None) or None
    if not directory and getattr(parent, "filename", None):
        directory = osp.dirname(parent.filename)
    return directory


def load_result_image(parent, image_path):
    """Open a result's image, asking first when the current one is dirty.

    Smart-tool jumps used to call ``load_file`` directly, bypassing the
    save prompt that every navigation path runs; with auto-save off (or a
    failed write) that silently discarded the edits on screen.
    """
    may_continue = getattr(parent, "may_continue", None)
    if callable(may_continue) and not may_continue():
        return False
    parent.load_file(image_path)
    return True


def _notify(parent, message, icon="copy-green"):
    popup = Popup(message, parent, icon=new_icon_path(icon, "svg"))
    popup.show_popup(parent, popup_height=65, position="center")
    return popup


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
    dialog = QProgressDialog(
        title,
        QCoreApplication.translate("LabelingWidget", "取消"),
        0,
        max(maximum, 1),
        parent,
    )
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(380)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    dialog.setValue(0)
    dialog.setStyleSheet(f"""
        QProgressDialog {{ background-color: {get_theme()["background"]};
            border-radius: {get_theme()["radius_card"]}; padding: 18px; }}
        QLabel {{ color: {get_theme()["text"]}; font-size: 13px; }}
        """)
    dialog.show()
    return dialog


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
        self.tree.setHeaderLabels(
            [
                QCoreApplication.translate("LabelingWidget", "项目"),
                QCoreApplication.translate("LabelingWidget", "说明"),
            ]
        )
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
            if load_result_image(self._parent, image_path):
                self.accept()

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
            border-radius: {theme["radius_lg"]};
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
            border-radius: {theme["radius_md"]};
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
        _notify(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "当前没有可导出的结果。"
            ),
            "warning",
        )
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
        QCoreApplication.translate("LabelingWidget", "结果已导出：%1").replace(
            "%1", osp.basename(path)
        ),
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
        _notify(
            parent,
            QCoreApplication.translate("LabelingWidget", "没有可打开的目录。"),
            "warning",
        )
        return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(target))


def _jump_to_result(dialog):
    for row in _result_rows(dialog):
        image_path = row.get("image_path")
        if image_path and osp.exists(image_path):
            if load_result_image(dialog._parent, image_path):
                dialog.accept()
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
    export_button = QPushButton(
        QCoreApplication.translate("LabelingWidget", "导出 CSV")
    )
    open_button = QPushButton(
        QCoreApplication.translate("LabelingWidget", "打开所在目录")
    )
    jump_button = QPushButton(
        QCoreApplication.translate("LabelingWidget", "跳到首个结果")
    )
    buttons.addWidget(export_button)
    buttons.addWidget(open_button)
    buttons.addWidget(jump_button)
    buttons.addStretch()
    for button in extra_buttons or []:
        buttons.addWidget(button)
    if include_close:
        close_button = QPushButton(
            QCoreApplication.translate("LabelingWidget", "关闭")
        )
        close_button.clicked.connect(dialog.reject)
        buttons.addWidget(close_button)

    export_button.clicked.connect(
        lambda: _export_dialog_rows(dialog, parent, directory, title)
    )
    open_button.clicked.connect(
        lambda: _open_result_folder(dialog, parent, directory)
    )
    jump_button.clicked.connect(lambda: _jump_to_result(dialog))
    dialog.layout().addLayout(buttons)
