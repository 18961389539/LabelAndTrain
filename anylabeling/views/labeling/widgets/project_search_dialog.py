"""项目内搜索对话框：按标注状态与标签名找图，双击跳转。

匹配逻辑全在 ``utils/project_search.py``（纯函数、另有测试）；这里
只做三件事 —— 收集条件、在后台线程里跑搜索、把结果送回文件。
线程一代一个号，旧代迟到即弃；跳转走 ``load_file``，未保存的改动
照常先问（和方向键导航是同一道闸）。
"""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils import project_search


class _Signals(QtCore.QObject):
    done = QtCore.pyqtSignal(int, list)


class _SearchWorker(QtCore.QRunnable):
    """One generation of the search, off the GUI thread."""

    def __init__(
        self,
        signals,
        generation,
        root,
        output_dir,
        files,
        label_query,
        state_query,
    ):
        super().__init__()
        self._signals = signals
        self._generation = generation
        self._root = root
        self._output_dir = output_dir
        self._files = files
        self._label_query = label_query
        self._state_query = state_query

    def run(self):
        try:
            results = project_search.search_project(
                self._root,
                self._output_dir,
                files=self._files,
                label_query=self._label_query,
                state_query=self._state_query,
            )
        except Exception as e:  # noqa: BLE001 - 搜索不能弄坏对话框
            logger.warning(f"Project search failed: {e}")
            return
        try:
            self._signals.done.emit(self._generation, results)
        except RuntimeError:
            pass  # 对话框已关：没人听的结果让它消失


class ProjectSearchDialog(QtWidgets.QDialog):
    """Search the open project's images; double-click jumps to one."""

    def __init__(self, parent):
        super().__init__(parent)
        self.widget = parent
        self.setWindowTitle(self.tr("项目内搜索"))
        self.resize(560, 480)
        self._generation = 0
        self._signals = _Signals()
        self._signals.done.connect(self._apply_results)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        form = QtWidgets.QFormLayout()
        form.setSpacing(8)
        self.state_combo = QtWidgets.QComboBox(self)
        self.state_combo.addItem(self.tr("全部"), "")
        for state in project_search.SEARCH_STATES:
            self.state_combo.addItem(state, state)
        self.label_edit = QtWidgets.QLineEdit(self)
        self.label_edit.setPlaceholderText(
            self.tr("标签名包含…（留空为不限）")
        )
        form.addRow(self.tr("标注状态"), self.state_combo)
        form.addRow(self.tr("标签名"), self.label_edit)
        layout.addLayout(form)

        self.result_list = QtWidgets.QListWidget(self)
        self.result_list.setAlternatingRowColors(True)
        self.result_list.itemDoubleClicked.connect(
            lambda _item: self._open_selected()
        )
        layout.addWidget(self.result_list, 1)

        self.count_label = QtWidgets.QLabel("", self)
        layout.addWidget(self.count_label)

        buttons = QtWidgets.QHBoxLayout()
        jump_button = QtWidgets.QPushButton(self.tr("跳转"))
        close_button = QtWidgets.QPushButton(self.tr("关闭"))
        buttons.addStretch()
        buttons.addWidget(jump_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        jump_button.clicked.connect(self._open_selected)
        close_button.clicked.connect(self.reject)

        self.state_combo.currentIndexChanged.connect(self._start_search)
        # 打字每敲一个字符就是一轮全量扫描：标签名输入走 300ms 防抖，
        # 最后一次输入才算数；状态下拉是单次点击，即时生效。
        self._search_timer = QtCore.QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._start_search)
        self.label_edit.textChanged.connect(self._search_timer.start)
        self._start_search()

    # --- criteria ----------------------------------------------------------

    def _criteria(self):
        """``(root, output_dir, files, label_query, state_query)``.

        Files come from the session's file list, so the search answers
        for exactly what this open session has; no open project means
        nothing to search and the dialog says so.
        """
        widget = self.widget
        files = []
        file_list = getattr(widget, "file_list_widget", None)
        if file_list is not None:
            files = [
                file_list.item(i).text() for i in range(file_list.count())
            ]
        root = getattr(widget, "_project_dataset_dir", None) or ""
        output_dir = getattr(widget, "output_dir", None) or ""
        label_query = self.label_edit.text()
        state_query = self.state_combo.currentData()
        return root, output_dir, files, label_query, state_query

    # --- search ------------------------------------------------------------

    def _start_search(self):
        self._generation += 1
        generation = self._generation
        root, output_dir, files, label_query, state_query = self._criteria()
        if not files:
            self.result_list.clear()
            self.count_label.setText(self.tr("当前没有打开的图片。"))
            return
        self.count_label.setText(self.tr("搜索中…"))
        worker = _SearchWorker(
            self._signals,
            generation,
            root,
            output_dir,
            files,
            label_query,
            state_query or "",
        )
        QtCore.QThreadPool.globalInstance().start(worker)

    def _apply_results(self, generation, results):
        if generation != self._generation:
            return  # 旧代的迟到结果：条件又变了，丢弃
        self.result_list.clear()
        for row in results:
            name = QtCore.QFileInfo(row["file"]).fileName()
            labels = "、".join(row["labels"][:3]) or "—"
            item = QtWidgets.QListWidgetItem(
                f"{name}    [{row['state']}]    {labels}"
            )
            item.setData(QtCore.Qt.ItemDataRole.UserRole, row["file"])
            self.result_list.addItem(item)
        total = self.result_list.count()
        self.count_label.setText(
            self.tr("共 %d 张。") % total
            if total
            else self.tr("没有匹配的图片。")
        )

    # --- jump ---------------------------------------------------------------

    def _selected_file(self):
        item = self.result_list.currentItem()
        return item.data(QtCore.Qt.ItemDataRole.UserRole) if item else None

    def _open_selected(self):
        """Jump to the selected image through the usual navigation gate.

        Same two checks the arrow-key navigation makes -- drawing in
        progress, unsaved changes -- then the file loads and the dialog
        closes: the search did its job.
        """
        file = self._selected_file()
        if not file:
            return
        if self.widget._paging_blocked_by_drawing():
            return
        if not self.widget.may_continue():
            return
        self.widget.load_file(file)
        self.accept()
