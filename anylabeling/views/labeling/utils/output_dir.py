"""One implementation of the "output directory already exists" question.

Four call sites used to carry their own copy of this dialog, and the copies
disagreed. The YOLO export was hardened (Merge / Clear / Cancel, with Clear
behind a second confirmation that names the path) while the VOC export, the
COCO export and the crop export kept the older Overwrite / Cancel shape: one
click away from ``shutil.rmtree`` on whatever directory the annotator had
typed, no path in the dialog, and no listing of what was about to go.
``shutil.rmtree`` does not use the recycle bin, so that click was
irreversible. Reading any single file could not have shown this -- only
comparing the four could.

Two rules live here so that no caller can contradict them:

* Merge is the default button, and the destructive choice always asks again
  with the absolute path spelled out.
* A target that holds (or is) the directory being annotated can never be
  cleared. The images are the work; an output path that swallows them is a
  typo, not an instruction.
"""

import os
import os.path as osp
import shutil

from PyQt6 import QtWidgets
from PyQt6.QtCore import QCoreApplication

from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils.style import get_msg_box_style

#: Write into whatever is already there (default).
MERGE = "merge"
#: The directory was emptied and rebuilt.
CLEAR = "clear"
#: The caller must stop; nothing was touched.
CANCEL = "cancel"


def _translate(text):
    """Translate with an explicit context.

    ``widget.tr(...)`` inside a module-level function is invisible to
    ``pylupdate6`` (it can only infer the context from a receiver
    expression inside a class body), so a moved ``self.tr`` string is
    silently dropped from the catalogue. The context spelled out here is
    the same one the surrounding widget methods resolve to.
    """
    return QCoreApplication.translate("LabelingWidget", text)


def protected_hit(save_path, protected_paths):
    """Return the protected directory ``save_path`` would take down, if any.

    A hit means ``save_path`` *is* that directory or an ancestor of it, so
    clearing ``save_path`` would delete it.
    """
    target = osp.normcase(osp.realpath(str(save_path)))
    for raw in protected_paths:
        if not raw:
            continue
        candidate = osp.normcase(osp.realpath(str(raw)))
        if candidate == target or candidate.startswith(target + osp.sep):
            return candidate
    return None


def resolve_existing_output_dir(
    widget, save_path, *, protected_paths=(), ask=None
):
    """Make ``save_path`` ready to be written into.

    Returns ``MERGE`` (write into what is already there), ``CLEAR`` (the
    directory was emptied and rebuilt) or ``CANCEL`` (the caller must stop).
    ``save_path`` exists whenever the result is not ``CANCEL``.

    ``protected_paths`` are directories that must survive; ``ask`` is
    injectable so the policy can be tested without a dialog.
    """
    save_path = str(save_path)
    if not osp.exists(save_path):
        os.makedirs(save_path, exist_ok=True)
        return MERGE

    blocked = protected_hit(save_path, protected_paths)
    if blocked is not None:
        logger.warning(
            "Refusing to clear an output directory that holds the folder "
            f"being annotated: {save_path} (protected: {blocked})"
        )

    ask = ask or ask_about_existing_dir
    choice = ask(widget, save_path, allow_clear=blocked is None)
    if choice == CLEAR and blocked is None:
        logger.warning(f"Output directory cleared and rebuilt: {save_path}")
        shutil.rmtree(save_path)
        os.makedirs(save_path)
        return CLEAR
    if choice == MERGE:
        return MERGE
    return CANCEL


def ask_about_existing_dir(widget, save_path, *, allow_clear=True):
    """The shared dialog. Returns ``MERGE`` / ``CLEAR`` / ``CANCEL``."""
    msg_box = QtWidgets.QMessageBox(widget)
    msg_box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    msg_box.setWindowTitle(_translate("Output Directory Exists!"))
    msg_box.setText(_translate("Directory already exists. Choose an action:"))
    if allow_clear:
        msg_box.setInformativeText(
            _translate(
                "• Merge  - Keep what is already there and overwrite the "
                "files this run writes\n"
                "• Clear  - Delete this whole directory and rebuild it "
                "(asks again first)\n"
                "• Cancel - Abort"
            )
        )
    else:
        msg_box.setInformativeText(
            _translate(
                "• Merge  - Keep what is already there and overwrite the "
                "files this run writes\n"
                "• Cancel - Abort\n"
                "\n"
                "Clearing is not offered: this directory holds the images "
                "being annotated."
            )
        )

    merge_button = msg_box.addButton(
        _translate("Merge"), QtWidgets.QMessageBox.ButtonRole.AcceptRole
    )
    clear_button = None
    if allow_clear:
        clear_button = msg_box.addButton(
            _translate("Clear"),
            QtWidgets.QMessageBox.ButtonRole.DestructiveRole,
        )
    cancel_button = msg_box.addButton(
        _translate("Cancel"), QtWidgets.QMessageBox.ButtonRole.RejectRole
    )
    msg_box.setDefaultButton(merge_button)
    msg_box.setStyleSheet(get_msg_box_style())
    msg_box.exec()

    clicked = msg_box.clickedButton()
    if clear_button is not None and clicked == clear_button:
        if not _confirm_clear(widget, save_path):
            return CANCEL
        return CLEAR
    if clicked is None or clicked == cancel_button:
        return CANCEL
    return MERGE


def _confirm_clear(widget, save_path):
    """Second question for the destructive branch, with the path on screen."""
    confirm = QtWidgets.QMessageBox(widget)
    confirm.setIcon(QtWidgets.QMessageBox.Icon.Critical)
    confirm.setWindowTitle(_translate("Delete the whole directory?"))
    confirm.setText(
        _translate("即将删除并重建该目录，里面的内容不会进回收站：")
    )
    confirm.setInformativeText(save_path)
    yes_button = confirm.addButton(
        _translate("删除并重建"),
        QtWidgets.QMessageBox.ButtonRole.DestructiveRole,
    )
    cancel_button = confirm.addButton(
        _translate("Cancel"), QtWidgets.QMessageBox.ButtonRole.RejectRole
    )
    confirm.setDefaultButton(cancel_button)
    confirm.setStyleSheet(get_msg_box_style())
    confirm.exec()
    return confirm.clickedButton() is yes_button
