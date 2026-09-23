"""Experiment history dialog: compare what each training round produced."""

import csv
import os
import os.path as osp
import webbrowser

from PyQt6 import QtCore, QtWidgets

from anylabeling.services.auto_training.ultralytics.config import (
    get_default_project_dir,
)
from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils.active_learning import load_history
from anylabeling.views.training.run_history import (
    align_with_iterations,
    collect_run_history,
    format_history_rows,
    summarize_history,
)

COLUMNS = 14


class RunHistoryDialog(QtWidgets.QDialog):
    """Table over every run that wrote ``run_meta.json``.

    Runs trained before that field existed are reported as a count rather than
    as blank rows, so an empty cell always means "this run has no such number"
    and never "we did not look".
    """

    def __init__(self, parent, label_dir=None):
        super().__init__(parent)
        self.label_dir = label_dir
        self.setWindowTitle(self.tr("实验历史"))
        self.resize(1080, 560)
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
        export_button = QtWidgets.QPushButton(self.tr("导出 CSV"))
        open_button = QtWidgets.QPushButton(self.tr("打开运行目录"))
        refresh_button = QtWidgets.QPushButton(self.tr("刷新"))
        close_button = QtWidgets.QPushButton(self.tr("关闭"))
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
            self.tr("已记录运行 %1 个").replace("%1", str(summary["runs"]))
        ]
        if data["unrecorded"]:
            parts.append(
                self.tr("另有 %1 个运行早于元数据功能，未列入").replace(
                    "%1", str(data["unrecorded"])
                )
            )
        if summary["best_map50"] is not None:
            parts.append(
                self.tr("最佳 mAP50 %1（%2）")
                .replace("%1", f"{summary['best_map50']:.4f}")
                .replace("%2", summary["best_name"])
            )
        if summary["trend"] is not None:
            arrow = "↑" if summary["trend"] >= 0 else "↓"
            parts.append(
                self.tr("最近两轮 {arrow} {delta}（{from_} → {to}）")
                .replace("{arrow}", arrow)
                .replace("{delta}", f"{abs(summary['trend']):.4f}")
                .replace("{from_}", summary.get("trend_from") or "")
                .replace("{to}", summary.get("trend_to") or "")
            )
        self.summary_label.setText(" · ".join(parts))
        if not self.rows and not data["unrecorded"]:
            self.summary_label.setText(
                self.tr(
                    "没有在 %1 下找到带元数据的训练运行。完成一次训练后，"
                    "运行目录里会生成 run_meta.json 并出现在此表中；"
                    "若训练的 Project 指向了别处，这里看不到那些运行。"
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
                self, self.tr("实验历史"), self.tr("请先选中一行运行。")
            )
            return
        run_dir = self.rows[index].get("dir") or ""
        if run_dir and osp.isdir(run_dir):
            webbrowser.open(
                "file:///" + os.path.abspath(run_dir).replace("\\", "/")
            )
        else:
            QtWidgets.QMessageBox.information(
                self, self.tr("实验历史"), self.tr("该运行目录已不存在。")
            )

    def export_to_csv(self):
        if not self.rows:
            QtWidgets.QMessageBox.information(
                self, self.tr("实验历史"), self.tr("当前没有可导出的运行。")
            )
            return
        directory = self.label_dir or get_default_project_dir()
        suggested = osp.join(
            directory,
            f"run_history_{QtCore.QDateTime.currentDateTime().toString('yyyyMMdd_HHmmss')}.csv",
        )
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, self.tr("导出实验历史"), suggested, "CSV (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                for row in format_history_rows(self.rows):
                    writer.writerow(row)
        except OSError as exc:
            logger.error(f"Failed to export run history: {exc}")
            QtWidgets.QMessageBox.warning(self, self.tr("导出失败"), str(exc))
            return
        QtWidgets.QMessageBox.information(
            self,
            self.tr("导出完成"),
            self.tr("实验历史已导出到：%1").replace("%1", path),
        )
