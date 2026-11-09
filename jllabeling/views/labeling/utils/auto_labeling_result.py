"""Apply one auto-labeling result to the canvas, guarding overwrites.

The widget delegates here so the replacement policy (what counts as human
ground truth, when to ask) is testable without a QMessageBox in the way.
"""

import os.path as osp

from PyQt6 import QtWidgets
from PyQt6.QtCore import QCoreApplication

from jllabeling.services.auto_labeling.types import AutoLabelingMode
from ..logger import logger
from ..provenance import SOURCE_MODEL, get_source, stamp_model_shapes

#: Auto-labeling placeholder labels are part of the running interaction,
#: not annotations the user would mind losing.
_PLACEHOLDER_LABELS = {
    AutoLabelingMode.OBJECT,
    AutoLabelingMode.ADD,
    AutoLabelingMode.REMOVE,
}


def _tr(text):
    return QCoreApplication.translate("LabelingWidget", text)


def _protected_shapes(shapes):
    """Shapes a replacement would destroy and the user did not delegate.

    Locked shapes were already kept by the caller; model-produced shapes are
    the previous run's own output, so replacing them is the feature working
    as intended. Anything human or unknown (older label files) is protected.
    """
    protected = []
    for shape in shapes:
        if getattr(shape, "locked", False):
            continue
        if getattr(shape, "label", None) in _PLACEHOLDER_LABELS:
            continue
        if get_source(shape) == SOURCE_MODEL:
            continue
        protected.append(shape)
    return protected


def ask_replace(widget, existing_count, new_count):
    """Yes/no for an auto-labeling run that would overwrite annotations."""
    box = QtWidgets.QMessageBox(widget)
    box.setWindowTitle(_tr("替换现有标注？"))
    box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    box.setText(
        _tr(
            "自动标注返回 %1 个目标，将替换当前图片的 %2 个标注。"
            "锁定标注会保留。"
        )
        .replace("%1", str(new_count))
        .replace("%2", str(existing_count))
    )
    keep_btn = box.addButton(
        _tr("保留原标注"), QtWidgets.QMessageBox.ButtonRole.RejectRole
    )
    replace_btn = box.addButton(
        _tr("替换"), QtWidgets.QMessageBox.ButtonRole.DestructiveRole
    )
    box.setDefaultButton(keep_btn)
    box.exec()
    return box.clickedButton() is replace_btn


def apply(widget, auto_labeling_result):
    """Apply an ``AutoLabelingResult`` to the currently open image."""
    if not widget.image or not widget.image_path:
        return

    result_image_path = getattr(auto_labeling_result, "image_path", None)
    if result_image_path and widget.filename:
        current_filename = osp.normpath(osp.abspath(widget.filename))
        result_filename = osp.normpath(osp.abspath(result_image_path))
        if result_filename != current_filename:
            logger.warning(
                "Ignore stale auto labeling result for "
                f"{result_filename}; current file is {current_filename}"
            )
            return

    new_shapes = auto_labeling_result.shapes
    predictions = getattr(auto_labeling_result, "predictions", None)
    if predictions is not None:
        # A classifier returns a whole-image suggestion rather than shapes;
        # handling it here keeps it out of the shape-replacement logic,
        # which would otherwise clear the canvas on an empty shape list.
        widget._apply_model_predictions(predictions)
        return

    # YOLO-consistent guard: a prediction that found *nothing* must not
    # silently erase human ground truth. When the model outputs no
    # shapes (empty/background or missed detection) and the current
    # image already has annotations, we keep them untouched instead of
    # clearing them.
    if (
        auto_labeling_result.replace
        and not new_shapes
        and any(not shape.locked for shape in widget.canvas.shapes)
    ):
        logger.info(
            "Auto labeling found no objects on this image; keeping "
            "existing annotations (empty results never erase "
            "ground truth)."
        )
        widget.status(_tr("本图未检测到目标，已保留原有标注"), 5000)
        return

    protected = []
    if auto_labeling_result.replace and new_shapes:
        protected = _protected_shapes(widget.canvas.shapes)
        if protected and not ask_replace(
            widget, len(protected), len(new_shapes)
        ):
            widget.status(_tr("已保留原有标注（自动标注结果未应用）"), 5000)
            return

    stamp_model_shapes(
        new_shapes,
        widget._current_model_identity(),
        widget._current_model_version(),
    )

    if auto_labeling_result.replace:
        locked_shapes = [
            shape for shape in widget.canvas.shapes if shape.locked
        ]
        widget.label_list.clear()
        widget.load_shapes(locked_shapes + new_shapes, replace=True)
    else:  # Just update existing shapes
        for shape in widget.canvas.shapes:
            if shape.label == AutoLabelingMode.OBJECT:
                item = widget.label_list.find_item_by_shape(shape)
                widget.label_list.remove_item(item)
        widget.load_shapes(new_shapes, replace=False)

    widget.set_dirty()
    # The run used to end in silence either way: zero detections left
    # the canvas unchanged with no word about it (only the log knew),
    # and a hit list never said how much came back.
    if new_shapes:
        widget.status(_tr("自动标注完成：%d 个目标") % len(new_shapes), 5000)
    else:
        widget.status(_tr("本图未检测到目标"), 5000)
