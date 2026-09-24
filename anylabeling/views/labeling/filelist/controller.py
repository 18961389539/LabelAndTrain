"""Review-flow behaviour for the file list.

Owns the "check / reject and keep moving" loop: applying a review verdict
to the open file, stepping to the next unchecked row, and applying the
background checker's batch results to the rows. Row state itself lives in
the item roles (``filelist.roles``); the widget keeps thin delegates so
the menu wiring, the async callbacks and the tests stay untouched.
"""

from PyQt6 import QtCore

from ..logger import logger
from ..schema import REVIEW_CONFIRMED, REVIEW_REJECTED, REVIEW_UNCHECKED
from . import items as filelist_items
from .roles import CHECKED_FIELD, REVIEW_STATE_FIELD, REVIEWED_AT_FIELD


class FileReviewController:
    """Holds the widget's review-flow behaviour; the widget delegates."""

    def __init__(self, widget):
        self._widget = widget

    def set_annotation_checked(self, checked):
        state = REVIEW_CONFIRMED if checked else REVIEW_UNCHECKED
        self.apply_review_state(state)

    def apply_review_state(self, state):
        """Record a review verdict on the current file and save it."""
        widget = self._widget
        if widget.filename is None or widget.image.isNull():
            return
        widget.other_data[REVIEW_STATE_FIELD] = state
        # `checked` stays written for every consumer that has always read it,
        # including the "train on checked files only" dataset filter.
        widget.other_data[CHECKED_FIELD] = state == REVIEW_CONFIRMED
        if state == REVIEW_UNCHECKED:
            widget.other_data.pop(REVIEWED_AT_FIELD, None)
        else:
            widget.other_data[REVIEWED_AT_FIELD] = (
                QtCore.QDateTime.currentDateTime().toString(
                    QtCore.Qt.DateFormat.ISODate
                )
            )
        widget._sync_annotation_checked_state()
        label_file = widget.get_label_file()
        if widget.save_labels(label_file):
            widget.set_clean()
            widget._show_save_feedback(True)
        else:
            widget._show_save_feedback(False)

    def mark_checked_and_next(self, _value=False):
        """Single-step review flow: check the file and keep moving."""
        widget = self._widget
        if widget.filename is None or widget.image.isNull():
            return
        current_filename = str(widget.filename)
        widget.set_annotation_checked(True)
        if widget.filename is None:
            return
        widget.open_next_unchecked_image()
        if str(widget.filename) == current_filename:
            widget.open_next_image()

    def mark_rejected_and_next(self, _value=False):
        """Send the current image back for rework and keep moving."""
        widget = self._widget
        if widget.filename is None or widget.image.isNull():
            return
        current_filename = str(widget.filename)
        widget._apply_review_state(REVIEW_REJECTED)
        if widget.filename is None:
            return
        widget.open_next_unchecked_image()
        if str(widget.filename) == current_filename:
            widget.open_next_image()

    def next_visible_row(self, row, delta):
        """Nearest visible row after ``row`` stepping by ``delta`` (±1).

        ``row`` itself is treated as the origin: when it is visible the
        scan starts one step away, when it is hidden (filter switched while
        the image was open) any visible row is accepted, starting from the
        far end and wrapping so the page always lands somewhere visible.
        Returns ``-1`` when no visible row exists.
        """
        widget = self._widget
        count = widget.file_list_widget.count()
        if count <= 0:
            return -1
        visible = widget._visible_rows()
        if not visible:
            return -1
        if not (0 <= row < count):
            return visible[0]
        if not widget.file_list_widget.item(row).isHidden():
            for _ in range(len(visible)):
                row = (row + delta) % count
                if not widget.file_list_widget.item(row).isHidden():
                    return row
            # No other visible row in this direction (row was the only /
            # last one): keep the origin so navigation stops at the end.
            return -1
        # Current row hidden: scan the whole list for the nearest visible
        # row in the requested direction, falling back to the other side.
        visited = set()
        probe = row
        while len(visited) < count:
            probe = (probe + delta) % count
            if probe in visited:
                break
            visited.add(probe)
            if not widget.file_list_widget.item(probe).isHidden():
                return probe
        # Nothing in direction: pick the first visible anywhere.
        return visible[0]

    def open_prev_unchecked_image(self):
        widget = self._widget
        if widget._paging_blocked_by_drawing():
            return
        if (
            not widget.may_continue(silent=True)
            or widget.file_list_widget.count() <= 0
            or widget.filename is None
        ):
            return

        current_index = widget.fn_to_index[str(widget.filename)]
        for i in range(current_index - 1, -1, -1):
            item = widget.file_list_widget.item(i)
            if item.isHidden():
                continue
            if not filelist_items.file_item_annotation_checked(item):
                filename = item.text()
                if filename:
                    widget.load_file(filename)
                break

    def open_next_unchecked_image(self, _value=False):
        widget = self._widget
        if widget._paging_blocked_by_drawing():
            return
        if (
            not widget.may_continue(silent=True)
            or widget.file_list_widget.count() <= 0
            or widget.filename is None
        ):
            return

        current_index = widget.fn_to_index[str(widget.filename)]
        for i in range(current_index + 1, widget.file_list_widget.count()):
            item = widget.file_list_widget.item(i)
            if item.isHidden():
                continue
            if not filelist_items.file_item_annotation_checked(item):
                filename = item.text()
                if filename:
                    widget.load_file(filename)
                break

    def apply_checked_batch(self, start_index, info_list):
        """Apply a batch of review-state results to file rows by index."""
        widget = self._widget
        try:
            for offset, info in enumerate(info_list):
                row = start_index + offset
                item = widget.file_list_widget.item(row)
                if item is not None:
                    state, reviewed_at = info
                    widget._set_file_item_review_state(
                        item, state, reviewed_at
                    )
            widget._refresh_file_progress()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to apply checked batch: {e}")
