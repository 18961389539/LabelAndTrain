"""Entry points that open the training dialogs from the labeling widget.

Kept out of LabelingWidget so the widget does not grow training
orchestration on top of everything else it already does. The dialogs
themselves are imported lazily: training is not needed at startup, and
this keeps the training modules out of the app's import graph until the
menu entry is actually used.
"""

from __future__ import annotations

from PyQt6 import QtWidgets
from PyQt6.QtCore import QCoreApplication

TRAINING_INSTALL_COMMAND = 'pip install -e ".[cpu-train]"'


def _show_missing_training_dialog(widget):
    """Explain the missing extra and let the user copy the command."""
    box = QtWidgets.QMessageBox(widget)
    box.setWindowTitle(
        QCoreApplication.translate("LabelingWidget", "缺少训练组件")
    )
    box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    box.setText(
        QCoreApplication.translate(
            "LabelingWidget",
            "未安装 ultralytics，无法打开训练面板。\n"
            "请在当前项目环境中安装训练组件后重试：",
        )
    )
    box.setInformativeText(TRAINING_INSTALL_COMMAND)
    copy_btn = box.addButton(
        QCoreApplication.translate("LabelingWidget", "复制安装命令"),
        QtWidgets.QMessageBox.ButtonRole.ActionRole,
    )
    close_btn = box.addButton(
        QCoreApplication.translate("LabelingWidget", "关闭"),
        QtWidgets.QMessageBox.ButtonRole.RejectRole,
    )
    box.setDefaultButton(close_btn)
    box.exec()
    if box.clickedButton() is copy_btn:
        QtWidgets.QApplication.clipboard().setText(TRAINING_INSTALL_COMMAND)
        widget.status(
            QCoreApplication.translate("LabelingWidget", "安装命令已复制"),
            4000,
        )


def start_training(widget, mode):
    """Open the training dialog for `mode`, after a dependency check."""
    if mode == "ultralytics":
        from jllabeling.services.auto_training.ultralytics.utils import (
            check_package_installed,
        )

        if not check_package_installed("ultralytics"):
            _show_missing_training_dialog(widget)
            return
        from jllabeling.views.training.ultralytics_dialog import (
            UltralyticsDialog,
        )

        dialog = UltralyticsDialog(widget)
    else:
        return

    try:
        _ = dialog.exec()
    except Exception as e:
        widget.error_message(
            QCoreApplication.translate("LabelingWidget", "无法启动训练面板"),
            str(e),
        )


def show_run_history(widget, _value=False):
    """Compare what each recorded training round produced."""
    from jllabeling.views.training.run_history_dialog import (
        RunHistoryDialog,
    )

    dialog = RunHistoryDialog(widget, label_dir=widget._active_label_dir())
    dialog.exec()
