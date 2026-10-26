"""Merge the selected shapes into one without dropping any of them.

The union used to keep only the largest exterior contour, so merging two
disjoint polygons deleted the smaller one, and a selected point or
rotation was folded into the polygon mask and then removed with the
originals. Both were silent. This module refuses a selection it cannot
represent as a single shape and says why; a mergeable selection is
replaced by a result that covers all of it.
"""

import cv2
import numpy as np

from PyQt6 import QtWidgets
from PyQt6.QtCore import QCoreApplication, QPointF

MERGEABLE_SHAPE_TYPES = ("rectangle", "polygon")

# The polygon mask gets a margin so contours never touch its edge.
_MASK_MARGIN = 5


def _refuse(widget, message):
    widget.status(message, 5000)


def _confirm_mixed_labels(widget, selected):
    """Ask before collapsing shapes of different classes into the last.

    Kept enabled rather than disabled: merging duplicate boxes that a
    model labelled differently is a real cleanup, but which class survives
    must not be a silent side effect of selection order.
    """
    labels = []
    for shape in selected:
        if shape.label not in labels:
            labels.append(shape.label)
    if len(labels) <= 1:
        return True

    kept = selected[-1].label
    answer = QtWidgets.QMessageBox.question(
        widget,
        QCoreApplication.translate("LabelingWidget", "合并选中标注"),
        QCoreApplication.translate(
            "LabelingWidget",
            "选中的对象类别不同（%1）。合并后的对象沿用最后选中的「%2」的类别与属性，其余对象的类别与属性会丢失。是否继续？",
        )
        .replace("%1", "、".join(str(label) for label in labels))
        .replace("%2", str(kept)),
        QtWidgets.QMessageBox.StandardButton.Yes
        | QtWidgets.QMessageBox.StandardButton.No,
        QtWidgets.QMessageBox.StandardButton.No,
    )
    return answer == QtWidgets.QMessageBox.StandardButton.Yes


def _rectangle_union(selected):
    xs = [point.x() for shape in selected for point in shape.points]
    ys = [point.y() for shape in selected for point in shape.points]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    return [
        QPointF(xmin, ymin),
        QPointF(xmax, ymin),
        QPointF(xmax, ymax),
        QPointF(xmin, ymax),
    ]


def _polygon_union(widget, selected):
    polygons = [
        [(float(p.x()), float(p.y())) for p in shape.points]
        for shape in selected
    ]
    if any(len(polygon) < 3 for polygon in polygons):
        _refuse(
            widget,
            QCoreApplication.translate(
                "LabelingWidget",
                "合并失败：每个多边形至少要有 3 个顶点。",
            ),
        )
        return None

    xs = [x for polygon in polygons for x, _ in polygon]
    ys = [y for polygon in polygons for _, y in polygon]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    width = int(xmax - xmin + 2 * _MASK_MARGIN)
    height = int(ymax - ymin + 2 * _MASK_MARGIN)
    mask = np.zeros((height, width), dtype=np.uint8)
    offset = np.array([xmin - _MASK_MARGIN, ymin - _MASK_MARGIN])
    for polygon in polygons:
        contour = np.round(np.array(polygon) - offset).astype(np.int32)
        cv2.fillPoly(mask, [contour], 255)

    contours, hierarchy = cv2.findContours(
        mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
    )
    if hierarchy is None:
        _refuse(
            widget,
            QCoreApplication.translate(
                "LabelingWidget",
                "合并失败：选中的多边形没有可用的轮廓。",
            ),
        )
        return None
    hierarchy = hierarchy[0]
    exterior = [
        contour
        for index, contour in enumerate(contours)
        if hierarchy[index][3] == -1
    ]
    has_hole = any(node[3] != -1 for node in hierarchy)
    if len(exterior) != 1 or has_hole:
        _refuse(
            widget,
            QCoreApplication.translate(
                "LabelingWidget",
                "合并失败：选中的多边形没有连成一个整体（彼此分离或围出了孔洞），无法用一个多边形表示；请分开合并。",
            ),
        )
        return None

    largest = max(exterior, key=cv2.contourArea)
    epsilon = 0.001 * cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, epsilon, True).reshape(-1, 2)
    if len(approx) < 3:
        _refuse(
            widget,
            QCoreApplication.translate(
                "LabelingWidget", "合并失败：合并后的多边形为空。"
            ),
        )
        return None
    approx = approx + offset
    return [QPointF(float(x), float(y)) for x, y in approx]


def union_selection(widget):
    selected = list(widget.canvas.selected_shapes)
    if len(selected) < 2 or any(shape.locked for shape in selected):
        return

    kinds = {shape.shape_type for shape in selected}
    kind = next(iter(kinds))
    if len(kinds) != 1 or kind not in MERGEABLE_SHAPE_TYPES:
        _refuse(
            widget,
            QCoreApplication.translate(
                "LabelingWidget",
                "合并失败：只支持同为矩形或同为多边形的对象；请取消选择其它类型的对象后再试。",
            ),
        )
        return

    if not _confirm_mixed_labels(widget, selected):
        return

    if kind == "rectangle":
        points = _rectangle_union(selected)
    else:
        points = _polygon_union(widget, selected)
        if points is None:
            return

    merged = selected[-1].copy()
    merged.points = points
    merged.selected = False

    remaining = [
        shape for shape in widget.canvas.shapes if shape not in selected
    ]
    # Remove the old rows with the drop signal suppressed, then add the
    # merged row and replace the canvas shapes in one call. Going through
    # remove_labels()/delete_selected() would let each row removal rebuild
    # canvas.shapes, pushing intermediate states onto the undo stack -- the
    # first Ctrl+Z would bring back one original, the next would empty the
    # image.
    model = widget.label_list.model()
    suppressed = getattr(model, "_suppress_drop_signal", False)
    model._suppress_drop_signal = True
    widget._no_selection_slot = True
    try:
        for shape in selected:
            item = widget.label_list.find_item_by_shape(shape)
            if item is not None:
                widget.label_list.remove_item(item)
        widget.add_label(merged, refresh_filters=False)
    finally:
        widget._no_selection_slot = False
        model._suppress_drop_signal = suppressed

    widget.canvas.selected_shapes = []
    widget.canvas.load_shapes(remaining + [merged])
    widget._refresh_shape_filters()
    widget._refresh_label_panel()
    widget.set_dirty()

    if widget.no_shape():
        for action in widget.actions.on_shapes_present:
            action.setEnabled(False)
