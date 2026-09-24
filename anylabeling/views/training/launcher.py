"""Entry points that open the training dialogs from the labeling widget.

Kept out of LabelingWidget so the widget does not grow training
orchestration on top of everything else it already does. The dialogs
themselves are imported lazily: training is not needed at startup, and
this keeps the training modules out of the app's import graph until the
menu entry is actually used.
"""

from __future__ import annotations


def start_training(widget, mode):
    """Open the training dialog for `mode`, after a dependency check."""
    if mode == "ultralytics":
        from anylabeling.services.auto_training.ultralytics.utils import (
            check_package_installed,
        )

        if not check_package_installed("ultralytics"):
            widget.error_message(
                widget.tr("缺少 Ultralytics"),
                widget.tr(
                    "尚未安装 ultralytics，无法打开训练窗口。<br>"
                    "请先安装：<br>"
                    "<code>pip install ultralytics</code><br>"
                    "或<br>"
                    "<code>uv pip install ultralytics --torch-backend=auto</code>"
                ),
            )
            return
        from anylabeling.views.training.ultralytics_dialog import (
            UltralyticsDialog,
        )

        dialog = UltralyticsDialog(widget)
    else:
        return

    try:
        _ = dialog.exec()
    except Exception as e:
        widget.error_message(
            "Start Error", f"Failed to start training dialog: {str(e)}"
        )


def show_run_history(widget, _value=False):
    """Compare what each recorded training round produced."""
    from anylabeling.views.training.run_history_dialog import (
        RunHistoryDialog,
    )

    dialog = RunHistoryDialog(widget, label_dir=widget._active_label_dir())
    dialog.exec()
