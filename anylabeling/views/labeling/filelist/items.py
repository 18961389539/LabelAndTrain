"""Pure row-item operations for the file list.

Each function takes the labeling widget as its first argument so tests
can drive them with a light stub, the same pattern as
``_shape_editable_state`` in label_widget.
"""

from PyQt6.QtCore import Qt

from ..schema import REVIEW_CONFIRMED, REVIEW_REJECTED, REVIEW_UNCHECKED
from .roles import (
    FILE_ANNOTATION_ROLE,
    FILE_LOW_CONF_ROLE,
    FILE_NEGATIVE_ROLE,
    FILE_REVIEW_ROLE,
    FILE_REVIEWED_AT_ROLE,
)


def is_confirmed(state):
    return state == REVIEW_CONFIRMED


def set_file_item_review_state(widget, item, state, reviewed_at=None):
    changed = (
        item.data(Qt.ItemDataRole.UserRole) is not is_confirmed(state)
        or item.data(FILE_REVIEW_ROLE) != state
    )
    if changed:
        item.setData(Qt.ItemDataRole.UserRole, is_confirmed(state))
        item.setData(FILE_REVIEW_ROLE, state)
    refresh_file_item_status_icon(widget, item)
    if reviewed_at is not None:
        item.setData(FILE_REVIEWED_AT_ROLE, reviewed_at)
    refresh_file_item_tooltip(widget, item)
    return changed


def refresh_file_item_tooltip(widget, item, counts=None):
    """Rebuild a row's hover text from what the row already knows."""
    if item is None:
        return
    file = item.text()
    item.setToolTip(
        widget._file_item_tooltip(
            file,
            widget._label_path_for_image(file),
            item.data(FILE_REVIEW_ROLE) or REVIEW_UNCHECKED,
            item.data(FILE_REVIEWED_AT_ROLE),
            counts=counts,
            negative=bool(item.data(FILE_NEGATIVE_ROLE)),
            low_conf=bool(item.data(FILE_LOW_CONF_ROLE)),
        )
    )


def set_file_item_annotated(widget, item, annotated, negative=False):
    item.setData(FILE_ANNOTATION_ROLE, bool(annotated))
    item.setData(FILE_NEGATIVE_ROLE, bool(annotated) and bool(negative))
    if not annotated:
        item.setData(FILE_LOW_CONF_ROLE, False)
    if widget._config.get("file_list_checkbox_editable", False):
        item.setCheckState(
            Qt.CheckState.Checked if annotated else Qt.CheckState.Unchecked
        )
    refresh_file_item_status_icon(widget, item)


def refresh_file_item_status_icon(widget, item):
    annotated = bool(item.data(FILE_ANNOTATION_ROLE))
    negative = bool(item.data(FILE_NEGATIVE_ROLE))
    state = item.data(FILE_REVIEW_ROLE) or (
        REVIEW_CONFIRMED
        if item.data(Qt.ItemDataRole.UserRole) is True
        else REVIEW_UNCHECKED
    )
    # Only the icon: what it means belongs to the row tooltip, which also
    # carries the path, the review timestamp and the shape counts.
    if state == REVIEW_REJECTED:
        # Sent back for rework: still untrained, but needs eyes on it.
        item.setIcon(widget.file_status_icons["rejected"])
    elif state == REVIEW_CONFIRMED:
        item.setIcon(widget.file_status_icons["checked"])
    elif annotated and negative:
        # Negative sample: confirmed empty (json with zero shapes).
        item.setIcon(widget.file_status_icons["negative"])
    elif annotated:
        item.setIcon(widget.file_status_icons["annotated"])
    else:
        item.setIcon(widget.file_status_icons["unannotated"])


def file_item_annotation_checked(item):
    return item.data(Qt.ItemDataRole.UserRole) is True


def set_file_item_low_conf(widget, item, has_low_conf):
    value = bool(has_low_conf)
    if item.data(FILE_LOW_CONF_ROLE) is value:
        return
    syncing = getattr(widget, "_syncing_file_item", False)
    widget._syncing_file_item = True
    try:
        item.setData(FILE_LOW_CONF_ROLE, value)
    finally:
        widget._syncing_file_item = syncing
