"""Copy annotations from the previous labelled image onto the current one.

Owns the widget-side glue of the propagation flow: walking the file list
backwards for the closest labelled predecessor, then handing off to
``utils.shape_propagate.propagate_labels`` for the scaling/overlap math and
feeding the resulting shapes back through the widget's normal edit path.
The widget keeps thin delegates so the menu wiring and the tests stay
untouched.
"""

import json
import os.path as osp

from PyQt6 import QtCore, QtGui

from ..shape import Shape


class LabelPropagateController:
    """Holds the widget's label-propagation flow; the widget delegates."""

    def __init__(self, widget):
        self._widget = widget

    def prev_labeled_image(self):
        """Walk back from the current image; first labelled one wins.

        Returns ``(image_path, label_file, (w, h))`` or ``None``.
        """
        widget = self._widget
        paths = widget.image_list
        if not paths:
            return None
        start = widget.file_list_widget.currentRow()
        if start < 0:
            return None
        for index in range(start - 1, -1, -1):
            image_path = paths[index]
            label_file = widget._label_path_for_image(image_path)
            if not osp.exists(label_file):
                continue
            try:
                with open(label_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("shapes"):
                    probe = QtGui.QImage(image_path)
                    img_size = (
                        (probe.width(), probe.height())
                        if not probe.isNull()
                        else None
                    )
                    return image_path, label_file, img_size
            except (OSError, ValueError):
                continue
        return None

    def propagate_previous_labels(self):
        """Copy annotations from the previous image, scaled to this one."""
        from ..utils.shape_propagate import propagate_labels

        widget = self._widget
        if not widget.filename:
            widget.status(widget.tr("请先打开一张图片再使用标注传播。"), 3000)
            return
        image = getattr(widget, "image", None)
        if image is None or image.isNull():
            image = QtGui.QImage(widget.filename)
        dst_w, dst_h = image.width(), image.height()
        if dst_w <= 0 or dst_h <= 0:
            widget.status(widget.tr("无法读取当前图片尺寸。"), 3000)
            return

        prev = self.prev_labeled_image()
        if prev is None:
            widget.status(widget.tr("当前图片之前没有可复制的标注。"), 3000)
            return
        _prev_path, prev_file, prev_size = prev

        existing = []
        for shape in widget.canvas.shapes:
            existing.append(
                {
                    "label": shape.label,
                    "shape_type": getattr(shape, "shape_type", "rectangle"),
                    "points": [[p.x(), p.y()] for p in shape.points],
                }
            )

        planned = propagate_labels(
            prev_file, prev_size, dst_w, dst_h, existing_shapes=existing
        )
        if not planned:
            widget.status(
                widget.tr("没有需要复制的新标注（已存在或来源为空）。"), 3000
            )
            return

        new_shapes = []
        for payload in planned:
            shape = Shape(
                label=payload.get("label") or "",
                shape_type=payload.get("shape_type") or "rectangle",
            )
            for point in payload.get("points") or []:
                shape.add_point(QtCore.QPointF(float(point[0]), float(point[1])))
            if (
                len(shape.points) > 1
                and shape.shape_type not in ("point", "linestrip")
            ):
                shape.close()
            new_shapes.append(shape)

        widget.load_shapes(
            list(widget.canvas.shapes) + new_shapes, replace=True
        )
        widget.set_dirty()
        widget.status(
            widget.tr("已从上一张图复制 %1 个标注。").replace(
                "%1", str(len(new_shapes))
            ),
            4000,
        )
