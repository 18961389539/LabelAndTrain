"""Experiment history dialog: compare what each training round produced."""

import csv
import io
import os
import os.path as osp

from PyQt6 import QtCore, QtWidgets

from anylabeling.services.auto_training.ultralytics.config import (
    get_default_project_dir,
)
from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils.active_learning import load_history
from anylabeling.views.labeling.utils._io import save_text
from anylabeling.views.labeling.utils.style import (
    get_dialog_style,
    get_ok_btn_style,
)
from anylabeling.views.training import platform_open
from anylabeling.views.training.run_history import (
    align_with_iterations,
    collect_run_history,
    format_history_rows,
    summarize_history,
)

#: Must match ``len(format_history_rows([])[0])`` - the header comes from the
#: row formatter, while the table is built with a fixed column count, so a new
#: field silently loses its column otherwise (pinned by
#: ``test_run_history.test_table_width_matches_the_row_layout``).
COLUMNS = 16


def write_history_csv(path, rows):
    """Write the history table atomically, with a BOM for spreadsheets."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    for row in format_history_rows(rows):
        writer.writerow(row)
    save_text(buffer.getvalue(), path, encoding="utf-8-sig", newline="")


class RunHistoryDialog(QtWidgets.QDialog):
    """Table over every run that wrote ``run_meta.json``.

    Runs trained before that field existed are reported as a count rather than
    as blank rows, so an empty cell always means "this run has no such number"
    and never "we did not look".
    """

    def __init__(self, parent, label_dir=None):
        super().__init__(parent)
        self.label_dir = label_dir
        self.setWindowTitle(self.tr("Run History"))
        self.resize(1080, 560)
        self.setStyleSheet(get_dialog_style())
        self.rows = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.summary_label = QtWidgets.QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.table = QtWidgets.QTableWidget(0, COLUMNS, self)
        self.table.setHorizontalHeaderLabels(
            [self.tr(h) for h in format_history_rows([])[0]]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table, 1)

        buttons = QtWidgets.QHBoxLayout()
        export_button = QtWidgets.QPushButton(self.tr("Export CSV"))
        # 四个按钮此前同权，谁该点看不出来；导出是这张表唯一的产出动作。
        export_button.setStyleSheet(get_ok_btn_style())
        open_button = QtWidgets.QPushButton(self.tr("Open Run Directory"))
        refresh_button = QtWidgets.QPushButton(self.tr("Refresh"))
        close_button = QtWidgets.QPushButton(self.tr("Close"))
        for button in (export_button, open_button, refresh_button):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        export_button.clicked.connect(self.export_to_csv)
        open_button.clicked.connect(self.open_selected_run)
        refresh_button.clicked.connect(lambda: self.load())
        close_button.clicked.connect(self.reject)

        self.load()

    def load(self):
        runs_root = get_default_project_dir()
        data = collect_run_history(runs_root)
        self.rows = data["rows"]
        if self.label_dir:
            align_with_iterations(self.rows, load_history(self.label_dir))

        table_rows = format_history_rows(self.rows)
        self.table.setRowCount(max(0, len(table_rows) - 1))
        for row_index, row in enumerate(table_rows[1:]):
            for col_index, value in enumerate(row):
                self.table.setItem(
                    row_index,
                    col_index,
                    QtWidgets.QTableWidgetItem(value),
                )

        summary = summarize_history(self.rows)
        parts = [
            self.tr("%1 recorded runs").replace("%1", str(summary["runs"]))
        ]
        if data["unrecorded"]:
            parts.append(
                self.tr(
                    "%1 more runs predate the metadata feature and are not listed"
                ).replace("%1", str(data["unrecorded"]))
            )
        if summary["best_map50"] is not None:
            parts.append(
                self.tr("Best mAP50 %1 (%2)")
                .replace("%1", f"{summary['best_map50']:.4f}")
                .replace("%2", summary["best_name"])
            )
        if summary["trend"] is not None:
            arrow = "↑" if summary["trend"] >= 0 else "↓"
            parts.append(
                self.tr("Last two runs {arrow} {delta} ({from_} → {to})")
                .replace("{arrow}", arrow)
                .replace("{delta}", f"{abs(summary['trend']):.4f}")
                .replace("{from_}", summary.get("trend_from") or "")
                .replace("{to}", summary.get("trend_to") or "")
            )
        self.summary_label.setText(" · ".join(parts))
        if not self.rows and not data["unrecorded"]:
            self.summary_label.setText(
                self.tr(
                    "No training runs with metadata found under %1. After a training run finishes, run_meta.json appears in the run directory and shows up in this table; runs whose Project points elsewhere are not visible here."
                ).replace("%1", runs_root or "")
            )

    def selected_row_index(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        return row

    def open_selected_run(self):
        index = self.selected_row_index()
        if index is None or index >= len(self.rows):
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Run History"),
                self.tr("Select a run row first."),
            )
            return
        run_dir = self.rows[index].get("dir") or ""
        if run_dir and osp.isdir(run_dir):
            # The same WSL-aware opener the rest of the training window uses;
            # the hand-rolled file:// URL here was a third copy of that logic.
            platform_open.open_path(run_dir)
        else:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Run History"),
                self.tr("That run directory no longer exists."),
            )

    def export_to_csv(self):
        if not self.rows:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Run History"),
                self.tr("There are no runs to export."),
            )
            return
        directory = self.label_dir or get_default_project_dir()
        suggested = osp.join(
            directory,
            f"run_history_{QtCore.QDateTime.currentDateTime().toString('yyyyMMdd_HHmmss')}.csv",
        )
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, self.tr("Export Run History"), suggested, "CSV (*.csv)"
        )
        if not path:
            return
        try:
            write_history_csv(path, self.rows)
        except OSError as exc:
            logger.error(f"Failed to export run history: {exc}")
            QtWidgets.QMessageBox.warning(
                self, self.tr("Export Failed"), str(exc)
            )
            return
        QtWidgets.QMessageBox.information(
            self,
            self.tr("Export Complete"),
            self.tr("Run history exported to: %1").replace("%1", path),
        )
