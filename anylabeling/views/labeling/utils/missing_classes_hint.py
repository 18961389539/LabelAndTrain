"""The 还没有类别 hint: once per project, never on every folder open.

``load_dir`` closes with a hint when the open folder has no predefined
classes. It used to fire on *every* folder open, so re-opening the project
that was just closed, or switching projects, stacked a modal dialog each
time -- the 2026-10-10 machine check counted eleven of them inside nine
steps, one of them where the check expected none.

Two rules make it advice instead of nagging: a project is asked at most once
per process, and 不再提示 writes the choice into the project record, so the
folder stays quiet across restarts until 重置本项目设置 (which clears
``project_settings.UI_KEYS``) re-arms it. The asked table is module state, not
widget state: the 10-10 run's 「关闭项目后重开」 step is exactly the case where
counting on one widget object to survive would be a guess.
"""

import os.path as osp

from PyQt6 import QtCore, QtWidgets, sip

from anylabeling.views.labeling import project_context, project_settings

#: Value written under ``project_settings.HINT_KEY`` while the hint is off.
MUTED = "muted"

#: A folder open lands before the widget is shown; retry once, later.
RETRY_MS = 800

#: Projects the hint has already been shown for this process. Kept here
#: rather than on the widget so that nothing which rebuilds the labeling
#: view can restart the counting -- the same reason ``project_settings``
#: keeps ``_WRITE_WARNED`` at module level.
_ASKED = set()


def asked_roots():
    """The projects already asked about, for tests and diagnostics."""
    return _ASKED


def _root_key(root):
    return osp.normcase(osp.abspath(str(root)))


def _schedule(widget, dataset_dir):
    """Retry the hint shortly, once the widget has had time to show.

    Module-level so a test can replace it: what matters is that a folder
    opened before the window is visible still gets its hint, and that the
    retry cannot stack into a timer per switch.
    """
    QtCore.QTimer.singleShot(
        RETRY_MS, lambda: maybe_prompt(widget, dataset_dir)
    )


def is_muted(dataset_dir):
    """True when this project asked not to be told about missing classes."""
    if not dataset_dir:
        return False
    return (
        project_settings.get_value(dataset_dir, project_settings.HINT_KEY)
        == MUTED
    )


def _deleted(obj):
    """True when `obj` is a Qt object whose C++ side is already gone.

    ``TypeError`` is the plain test doubles this package is fed in tests, and
    those are always live.
    """
    try:
        return sip.isdeleted(obj)
    except TypeError:
        return False


def _is_gone(widget):
    """True once the labeling view has been destroyed.

    ``_schedule`` keeps a Python reference to the widget, so the retry still
    fires after 关闭项目 or a project switch tears that view down. Touching a
    deleted wrapper raises inside the Qt event loop, where no dialog can show
    the failure and the frames that caused it are already gone.
    """
    return _deleted(widget) or _deleted(widget.unique_label_list)


def maybe_prompt(widget, dataset_dir=None):
    """Offer to define classes for the open project, at most once per project.

    ``dataset_dir`` is the folder just opened; it is passed by ``load_dir``
    because the widget's own idea of the current project is not settled until
    the open finishes.
    """
    if _is_gone(widget):
        return
    if widget.unique_label_list.count() > 0:
        widget._missing_classes_hint_pending = False
        return
    if not widget.isVisible():
        if getattr(widget, "_missing_classes_hint_pending", False):
            return
        widget._missing_classes_hint_pending = True
        _schedule(widget, dataset_dir)
        return
    widget._missing_classes_hint_pending = False

    root = dataset_dir or project_context.current_dataset_dir(widget)
    if not root or not osp.isdir(str(root)):
        return
    if is_muted(root):
        return
    key = _root_key(root)
    if key in _ASKED:
        return
    _ASKED.add(key)
    _ask(widget, root)


def _ask(widget, root):
    """The hint itself: name the way out, and offer both doors.

    The strings go through ``QCoreApplication.translate`` under the widget's
    own context rather than ``widget.tr()``: the extractor can only place a
    ``tr()`` call it can see the receiver of, and a bare ``widget.tr()`` in a
    module-level function is dropped from the catalog without a warning.
    """
    translate = QtCore.QCoreApplication.translate
    box = QtWidgets.QMessageBox(widget)
    box.setWindowTitle(translate("LabelingWidget", "还没有类别"))
    box.setIcon(QtWidgets.QMessageBox.Icon.Information)
    box.setText(
        translate(
            "LabelingWidget",
            "当前没有预定义类别。导入 classes.txt 或打开标签管理器后再画框，"
            "可以减少每张图重复输入。",
        )
    )
    import_btn = box.addButton(
        translate("LabelingWidget", "导入 classes.txt"),
        QtWidgets.QMessageBox.ButtonRole.AcceptRole,
    )
    manage_btn = box.addButton(
        translate("LabelingWidget", "打开标签管理器"),
        QtWidgets.QMessageBox.ButtonRole.ActionRole,
    )
    mute_btn = box.addButton(
        translate("LabelingWidget", "不再提示"),
        QtWidgets.QMessageBox.ButtonRole.DestructiveRole,
    )
    box.addButton(
        translate("LabelingWidget", "稍后再说"),
        QtWidgets.QMessageBox.ButtonRole.RejectRole,
    )
    box.exec()
    clicked = box.clickedButton()
    if clicked is import_btn:
        from anylabeling.views.labeling.utils.upload import (
            upload_label_classes_file,
        )

        upload_label_classes_file(widget)
    elif clicked is manage_btn:
        widget.label_manager()
    elif clicked is mute_btn:
        if not project_settings.update_values(
            root, **{project_settings.HINT_KEY: MUTED}
        ):
            project_settings.report_write_failure(
                widget, root, action="missing-classes hint"
            )
