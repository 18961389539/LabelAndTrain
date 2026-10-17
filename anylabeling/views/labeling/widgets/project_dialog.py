"""Project properties: display name + task kind (new and edit share it).

It asks about the two things that genuinely belong to a project and
nothing else. The class list, the output directory and the split seed
already have homes of their own (``classes.txt``, ``project.json``, the
label folder) — repeating them here would just add a second place that
has to stay in step with the first.

An *existing* project additionally gets a read-only overview (annotation
progress, training rounds) when the caller hands one in: the numbers all
exist elsewhere already, and the dialog only renders what
``project_dashboard`` counted — it owns no numbers of its own, so it
cannot drift away from the file list or the history dialog.
"""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from anylabeling.views.labeling import project_model
from anylabeling.views.labeling.project import TASK_TYPES
from anylabeling.views.labeling.utils.style import get_dialog_style


def _fmt_map50(value):
    """``0.734`` as ``73.4%``; ``None`` and junk stay ``None``."""
    try:
        return "{:.1f}%".format(float(value) * 100)
    except (TypeError, ValueError):
        return None


def format_labels_line(labels, limit=6):
    """``标签 3 个：划痕、凹坑、气泡``; long lists stop at ``limit``.

    Returns ``""`` for an empty list -- a project with no labels has
    nothing to show, and an empty "标签 0 个" line would just be noise.
    """
    names = [str(label) for label in labels if str(label or "").strip()]
    if not names:
        return ""
    shown = "、".join(names[:limit])
    if len(names) > limit:
        # 字符串内联（不用 _tr 助手）：lupdate 只提取调用点上的字面量，
        # 本项目现有 _tr 包装的串全部没进翻译目录（已知缺陷，另批处理）。
        shown += "、" + QtCore.QCoreApplication.translate(
            "LabelingWidget", "…共 %d 个"
        ) % len(names)
    return QtCore.QCoreApplication.translate(
        "LabelingWidget", "标签 %d 个：%s"
    ) % (len(names), shown)


def format_last_export_line(snapshot):
    """``上次导出：G:/out（yolo，2026-10-14 09:20:11）``, or ``""``."""
    save_path = str((snapshot or {}).get("save_path") or "").strip()
    if not save_path:
        return ""
    mode = str((snapshot or {}).get("mode") or "").strip()
    at = str((snapshot or {}).get("at") or "").strip()
    detail = "，".join(part for part in (mode, at) if part)
    if detail:
        return QtCore.QCoreApplication.translate(
            "LabelingWidget", "上次导出：%s（%s）"
        ) % (save_path, detail)
    return (
        QtCore.QCoreApplication.translate("LabelingWidget", "上次导出：%s")
        % save_path
    )


def build_overview_group(overview):
    """The read-only 概览 block, or ``None`` when there is nothing to say.

    A separate constructor function rather than inline building: tests
    can drive it without instantiating the whole dialog, and the dialog
    keeps asking about name and task only.
    """
    progress = overview.get("progress") or {}
    training = overview.get("training") or {}
    images = progress.get("images") or 0

    lines = []
    if images:
        lines.append(
            QtWidgets.QLabel(
                QtCore.QCoreApplication.translate(
                    "LabelingWidget",
                    "已标 {annotated}/{images} · 已确认 {confirmed} · 需返工 {rework}",
                ).format(**progress)
            )
        )
    runs = training.get("runs") or 0
    if runs:
        best = _fmt_map50(training.get("best_map50"))
        if best:
            lines.append(
                QtWidgets.QLabel(
                    QtCore.QCoreApplication.translate(
                        "LabelingWidget", "训练 %d 轮 · 最好 mAP50 %s（%s）"
                    )
                    % (runs, best, training.get("best_name") or "-")
                )
            )
        else:
            lines.append(
                QtWidgets.QLabel(
                    QtCore.QCoreApplication.translate(
                        "LabelingWidget", "训练 %d 轮 · 无评分记录"
                    )
                    % runs
                )
            )
        last = training.get("last_finished") or ""
        if last:
            lines.append(
                QtWidgets.QLabel(
                    QtCore.QCoreApplication.translate(
                        "LabelingWidget", "最近一轮：%s（%s）"
                    )
                    % (training.get("last_run") or "-", last)
                )
            )
    elif images:
        lines.append(
            QtWidgets.QLabel(
                QtCore.QCoreApplication.translate("LabelingWidget", "尚未训练")
            )
        )

    # 标签列表与上次导出：项目的两个"我该去哪看"的问题，答案都在清单里。
    labels_line = format_labels_line(overview.get("labels") or [])
    if labels_line:
        lines.append(QtWidgets.QLabel(labels_line))
    export_line = format_last_export_line(overview.get("last_export") or {})
    if export_line:
        lines.append(QtWidgets.QLabel(export_line))

    if not lines:
        return None
    group = QtWidgets.QGroupBox(
        QtCore.QCoreApplication.translate("LabelingWidget", "项目概览")
    )
    box = QtWidgets.QVBoxLayout(group)
    box.setContentsMargins(8, 4, 8, 4)
    for line in lines:
        line.setWordWrap(True)
        box.addWidget(line)
    return group


class ProjectPropertiesDialog(QtWidgets.QDialog):
    """Edit a project's name and task kind; collapses to one page."""

    def __init__(
        self,
        parent,
        name="",
        task=None,
        root="",
        title="",
        note=None,
        overview=None,
        templates=None,
    ):
        super().__init__(parent)
        self.root = root
        self.setWindowTitle(title or self.tr("项目属性"))
        self.resize(460, 320)
        self.setStyleSheet(get_dialog_style())

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        if root:
            folder = QtWidgets.QLabel(self.tr("文件夹：%s") % root)
            folder.setWordWrap(True)
            folder.setStyleSheet("color: palette(mid);")
            layout.addWidget(folder)

        overview_group = build_overview_group(overview) if overview else None
        if overview_group is not None:
            layout.addWidget(overview_group)

        layout.addWidget(QtWidgets.QLabel(self.tr("项目名")))
        self.name_edit = QtWidgets.QLineEdit(
            project_model.normalize_name(name, root)
        )
        self.name_edit.setMaxLength(project_model.NAME_MAX_LENGTH)
        self.name_edit.setPlaceholderText(
            project_model.default_name(root) or self.tr("例如：螺丝划痕")
        )
        self.name_edit.selectAll()
        layout.addWidget(self.name_edit)

        layout.addWidget(QtWidgets.QLabel(self.tr("任务类型")))
        self.task_group = QtWidgets.QButtonGroup(self)
        current = project_model.normalize_task(task)
        for kind in TASK_TYPES:
            radio = QtWidgets.QRadioButton(
                "%s — %s"
                % (
                    project_model.task_label(kind),
                    project_model.task_hint(kind),
                )
            )
            radio.setChecked(kind == current)
            radio.setProperty("task_kind", kind)
            self.task_group.addButton(radio)
            layout.addWidget(radio)

        # 新建向导独有：从既有项目复制标签集与训练超参。选中的那一刻
        # 就把任务类型带过来 —— 这是模板里唯一能立即在界面上反映的
        # 部分，也让"模板的任务"和"单选的任务"从选中起就是一致的。
        self.template_combo = None
        self._templates = list(templates or [])
        if self._templates:
            layout.addWidget(QtWidgets.QLabel(self.tr("设置模板")))
            self.template_combo = QtWidgets.QComboBox(self)
            self.template_combo.addItem(self.tr("不使用模板"), None)
            for choice in self._templates:
                label = choice.get("name") or choice.get("root") or ""
                count = len(choice.get("labels") or [])
                if count:
                    label = self.tr("%s（%d 个标签）") % (label, count)
                self.template_combo.addItem(label, choice.get("root"))
                index = self.template_combo.count() - 1
                self.template_combo.setItemData(
                    index,
                    choice.get("task"),
                    QtCore.Qt.ItemDataRole.ToolTipRole,
                )
            self.template_combo.currentIndexChanged.connect(
                self._on_template_changed
            )
            layout.addWidget(self.template_combo)

        if note:
            hint = QtWidgets.QLabel(note)
            hint.setWordWrap(True)
            hint.setStyleSheet("color: palette(mid);")
            layout.addWidget(hint)

        layout.addStretch(1)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Save).setText(
            self.tr("保存")
        )
        buttons.button(
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        ).setText(self.tr("取消"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_template_changed(self, index):
        """Carry the template's task kind over to the radio buttons.

        Fires only when a template is actually picked; going back to
        不使用模板 leaves the radios where the user has them, because a
        cleared template is not a statement about the task.
        """
        if self.template_combo is None:
            return
        source = self.template_combo.itemData(index)
        if not source:
            return
        try:
            template = project_model.template_record(source)
        except Exception:  # noqa: BLE001 - 坏模板只是不预选
            return
        kind = project_model.normalize_task(template.get("task"))
        for button in self.task_group.buttons():
            if button.property("task_kind") == kind:
                button.setChecked(True)
                return

    def values(self):
        """``{"name", "task", "template_root"}``, name and task normalized.

        The name falls back to the folder name when the box is empty, so
        a project can never end up nameless — "unnamed" in a list of
        twelve is less useful than the folder it came from.
        ``template_root`` is ``None`` unless a template is picked; the
        caller reads the template's settings from that project itself,
        so the dialog does not have to keep a copy of them in step.
        """
        kind = None
        for button in self.task_group.buttons():
            if button.isChecked():
                kind = button.property("task_kind")
                break
        return {
            "name": project_model.normalize_name(
                self.name_edit.text(), self.root
            ),
            "task": project_model.normalize_task(kind),
            "template_root": (
                self.template_combo.currentData()
                if self.template_combo is not None
                else None
            ),
        }
