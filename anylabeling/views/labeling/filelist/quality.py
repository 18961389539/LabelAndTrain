"""Low-confidence / quality gating for the file list.

Owns the per-folder accept/review threshold cache and everything that
consumes it: deciding whether saved shapes need review, stamping the
low-confidence badge on rows, hiding rows in the "low_conf" filter, and
focusing uncertain shapes after a load. Row state itself lives in
``filelist.roles``/``filelist.items``; the widget keeps thin delegates so
the async checkers, the training launcher and the tests keep calling the
same widget methods as before.
"""

import json
import os.path as osp

from PyQt6 import QtCore

from ..utils.active_learning import (
    load_thresholds,
    needs_review,
    shape_uncertainty,
    thresholds_for,
)
from ..utils.quality import (
    format_save_quality_status,
    inspect_shape_quality,
    shapes_have_low_confidence,
)
from . import items as filelist_items
from .roles import FILE_LOW_CONF_ROLE


class FileQualityController:
    """Holds the widget's low-confidence/quality behaviour; widget delegates."""

    def __init__(self, widget):
        self._widget = widget
        # Per-folder threshold cache. Keyed by the active label directory so
        # switching datasets (or output dirs) re-reads its calibration file.
        self._threshold_dir = None
        self._thresholds = None

    # -- thresholds ---------------------------------------------------------

    def active_label_dir(self):
        widget = self._widget
        directory = widget.output_dir or None
        if not directory and widget.filename:
            directory = osp.dirname(widget.filename)
        return directory

    def load_active_thresholds(self):
        """Per-class accept/review thresholds for the open folder (cached)."""
        directory = self.active_label_dir()
        if not directory:
            return {}
        if self._threshold_dir == directory and self._thresholds is not None:
            return self._thresholds
        self._threshold_dir = directory
        self._thresholds = load_thresholds(directory)
        return self._thresholds

    def invalidate_active_thresholds(self):
        """Drop the cached thresholds (called after a calibration run)."""
        self._threshold_dir = None
        self._thresholds = None

    # -- review gating ------------------------------------------------------

    def shapes_need_review(self, shapes):
        thresholds = self.load_active_thresholds()
        if thresholds:
            return needs_review(shapes, thresholds=thresholds)
        # No calibration yet: keep the historical fixed band.
        return shapes_have_low_confidence(shapes)

    def file_item_has_low_conf(self, item):
        cached = item.data(FILE_LOW_CONF_ROLE)
        if cached is not None:
            return bool(cached)
        has_low_conf = False
        label_file = self._widget._label_path_for_image(item.text())
        if QtCore.QFile.exists(label_file):
            try:
                with open(label_file, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                has_low_conf = self.shapes_need_review(
                    data.get("shapes") if isinstance(data, dict) else None
                )
            except Exception:  # noqa: BLE001
                has_low_conf = False
        filelist_items.set_file_item_low_conf(self._widget, item, has_low_conf)
        return has_low_conf

    def note_save_quality(self, shapes, file_item=None):
        widget = self._widget
        image = getattr(widget, "image", None)
        image_width = image.width() if image is not None else 0
        image_height = image.height() if image is not None else 0
        stats = inspect_shape_quality(shapes, image_width, image_height)
        widget._last_quality_status = format_save_quality_status(stats)
        if file_item is not None:
            filelist_items.set_file_item_low_conf(
                widget, file_item, self.shapes_need_review(shapes)
            )
            combo = getattr(widget, "file_filter_combo", None)
            if combo is not None and combo.currentData() == "low_conf":
                file_item.setHidden(
                    not bool(file_item.data(FILE_LOW_CONF_ROLE))
                )
        return widget._last_quality_status

    def maybe_focus_low_confidence_shapes(self):
        widget = self._widget
        combo = getattr(widget, "file_filter_combo", None)
        if combo is None or combo.currentData() != "low_conf":
            return
        thresholds = self.load_active_thresholds()
        selected = []
        for shape in widget.canvas.shapes:
            accept, review = thresholds_for(
                getattr(shape, "label", "") or "", thresholds
            )
            if shape_uncertainty(shape, accept, review) > 0:
                selected.append(shape)
        if selected:
            widget.canvas.select_shapes(selected)

    # -- batch helpers ------------------------------------------------------

    def mark_file_item_negative_state(self, image_file, negative):
        """Flag a saved image as a negative sample in the file list.

        Mirrors what happens on the single-image save path so batch runs and
        manual saves stay consistent: negative samples show an amber badge in
        the file list and export as empty .txt for YOLO training.
        """
        widget = self._widget
        try:
            target = osp.normpath(osp.abspath(image_file))
            items = widget.file_list_widget.findItems(
                target, QtCore.Qt.MatchFlag.MatchExactly
            )
            if not items:
                for row in range(widget.file_list_widget.count()):
                    candidate = widget.file_list_widget.item(row)
                    if osp.normpath(osp.abspath(candidate.text())) == target:
                        items = [candidate]
                        break
            if len(items) == 1:
                filelist_items.set_file_item_annotated(
                    widget, items[0], True, negative=bool(negative)
                )
        except Exception:  # noqa: BLE001
            pass
