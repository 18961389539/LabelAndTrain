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


def _tr(text):
    """Module-level strings go through an explicit context.

    ``self.tr`` inside a module-level function is invisible to
    ``pylupdate6`` (it can only infer the context from a receiver
    expression inside a class body), so the overview's labels are
    translated the way ``utils/output_dir.py`` does it.
    """
    return QtCore.QCoreApplication.translate("LabelingWidget", text)


def _fmt_map50(value):
    """``0.734`` as ``73.4%``; ``None`` and junk stay ``None``."""
    try:
        return "{:.1f}%".format(float(value) * 100)
    except (TypeError, ValueError):
        return None


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
                _tr(
                    "已标 {annotated}/{images} · 已确认 {confirmed} · 需返工 {rework}"
                ).format(**progress)
            )
        )
    runs = training.get("runs") or 0
    if runs:
        best = _fmt_map50(training.get("best_map50"))
        if best:
            lines.append(
                QtWidgets.QLabel(
                    _tr("训练 %d 轮 · 最好 mAP50 %s（%s）")
                    % (runs, best, training.get("best_name") or "-")
                )
            )
        else:
            lines.append(
                QtWidgets.QLabel(_tr("训练 %d 轮 · 无评分记录") % runs)
            )
        last = training.get("last_finished") or ""
        if last:
            lines.append(
                QtWidgets.QLabel(
                    _tr("最近一轮：%s（%s）")
                    % (training.get("last_run") or "-", last)
                )
            )
    elif images:
        lines.append(QtWidgets.QLabel(_tr("尚未训练")))

    if not lines:
        return None
    group = QtWidgets.QGroupBox(_tr("项目概览"))
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
    ):
        super().__init__(parent)
        self.root = root
        self.setWindowTitle(title or self.tr("项目属性"))
        self.resize(460, 320)

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

    def values(self):
        """``{"name", "task"}`` with both already normalized.

        The name falls back to the folder name when the box is empty, so
        a project can never end up nameless — "unnamed" in a list of
        twelve is less useful than the folder it came from.
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
        }
