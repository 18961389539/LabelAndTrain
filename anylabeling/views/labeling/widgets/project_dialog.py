"""Project properties: display name + task kind (new and edit share it).

It asks about the two things that genuinely belong to a project and
nothing else. The class list, the output directory and the split seed
already have homes of their own (``classes.txt``, ``project.json``, the
label folder) — repeating them here would just add a second place that
has to stay in step with the first.
"""

from __future__ import annotations

from PyQt6 import QtWidgets

from anylabeling.views.labeling import project_model
from anylabeling.views.labeling.project import TASK_TYPES


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
