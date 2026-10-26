"""Shared helpers for the smart-tool action modules."""

from __future__ import annotations

import json
import os.path as osp
from anylabeling.views.labeling.utils.smart_ui import label_dir_for

HARD_EXAMPLE_LIMIT = 50


def _label_file_for_image(image_path, directory):
    """Label json path for an image, honouring a separate output dir."""
    label_file = osp.splitext(image_path)[0] + ".json"
    if directory:
        label_file = osp.join(directory, osp.basename(label_file))
    return label_file


def _image_list(parent):
    return list(getattr(parent, "image_list", None) or [])


def _read_label(label_file):
    if not osp.isfile(label_file):
        return None
    try:
        with open(label_file, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _label_entries(parent):
    """Yield ``(image_path, data_or_None)`` for every open image."""
    directory = label_dir_for(parent)
    for image_path in _image_list(parent):
        label_file = osp.splitext(image_path)[0] + ".json"
        if directory:
            label_file = osp.join(directory, osp.basename(label_file))
        yield image_path, _read_label(label_file)


def _confirmed_lookup(parent):
    """Map of normalised image path -> human-checked flag."""
    mapping = {}
    widget = getattr(parent, "file_list_widget", None)
    checked_getter = getattr(parent, "_file_item_annotation_checked", None)
    if widget is None or checked_getter is None:
        return mapping
    for row in range(widget.count()):
        item = widget.item(row)
        if item is None:
            continue
        try:
            mapping[osp.normpath(osp.abspath(item.text()))] = bool(
                checked_getter(item)
            )
        except Exception:  # noqa: BLE001
            continue
    return mapping
