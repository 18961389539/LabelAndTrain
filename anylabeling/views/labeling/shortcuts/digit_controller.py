"""Digit-shortcut behaviour for the labeling widget.

Owns the digit -> label flow: the manager dialog (Alt+D), the create
dispatch behind the 0-9 keys, and the auto-assignment of free digits to
labels -- both the ones seen for the first time on a shape, and the ones a
project declares up front.

The shortcut map itself stays on the widget (``drawing_digit_shortcuts`` /
``digit_to_label``) so the canvas callbacks and the settings runtime keep
reading it from one place.
"""

from PyQt6 import QtWidgets

from ....config import save_config
from ..logger import logger
from ..shape import Shape
from ..widgets.label_dialog import DigitShortcutDialog

#: The keys ``digit_shortcut_0..9`` cover, in the order they get filled.
#: 1-9 come first because those are the ones a hand reaches for; 0 is the
#: tenth slot rather than a dead key (the dialog has always offered it, and
#: ``user_guide`` documents "0-9" while auto-assignment used to stop at 9).
DIGIT_SLOTS = tuple(range(1, 10)) + (0,)

#: Shape type used when a slot is filled without a shape to copy from.
DEFAULT_DIGIT_MODE = "rectangle"


class DigitShortcutController:
    """Holds the widget's digit-shortcut behaviour; the widget delegates."""

    def __init__(self, widget):
        self._widget = widget

    def digit_shortcut_manager(self):
        widget = self._widget
        digit_shortcut_dialog = DigitShortcutDialog(parent=widget)
        result = digit_shortcut_dialog.exec()
        if result == QtWidgets.QDialog.DialogCode.Accepted:
            widget._config["digit_shortcuts"] = widget.drawing_digit_shortcuts
            save_config(widget._config)

    def create_digit_mode(self, digit_num):
        widget = self._widget
        if widget.drawing_digit_shortcuts is None:
            return

        data = widget.drawing_digit_shortcuts.get(digit_num, None)
        if not data:
            return

        label = data.get("label", "object")
        create_mode = data.get("mode", None)

        if create_mode not in Shape.get_supported_shape():
            return

        widget.digit_to_label = label
        widget.toggle_draw_mode(edit=False, create_mode=create_mode)

    def auto_assign_digit_shortcuts(self, shapes):
        """Assign free digit shortcuts to labels seen for the first time.

        Keeps multi-class annotation from needing manual setup via Alt+D.
        The shortcut creates the label with the shape type it was first seen
        as; users can still re-map via the digit shortcut manager. ``None``
        digit_shortcuts (feature disabled) is respected.
        """
        widget = self._widget
        shortcuts = getattr(widget, "drawing_digit_shortcuts", None)
        if shortcuts is None:
            return
        assigned = False
        for shape in shapes:
            label = getattr(shape, "label", None)
            if not label:
                continue
            if _digit_for_label(shortcuts, label) is not None:
                continue
            digit = _free_slot(shortcuts)
            if digit is None:
                break
            shape_type = shape.shape_type or DEFAULT_DIGIT_MODE
            shortcuts[digit] = {"label": label, "mode": shape_type}
            assigned = True
            logger.info(
                f"Digit shortcut {digit} auto-assigned to "
                f"'{label}' ({shape.shape_type})"
            )
        if assigned:
            _persist_digits(widget)

    def assign_label_digits(self, labels):
        """Give a project's declared labels the free digit keys, in order.

        Auto-assignment otherwise waits for a shape to exist, so a brand new
        project answers nothing when the very first box is drawn with the
        digit keys -- the exact step those keys exist to remove. Labels
        already mapped keep their key, and a full set of slots is left alone.
        Returns how many were assigned.
        """
        widget = self._widget
        shortcuts = getattr(widget, "drawing_digit_shortcuts", None)
        if shortcuts is None:
            return 0
        assigned = 0
        for label in labels or ():
            if not label or _digit_for_label(shortcuts, label) is not None:
                continue
            digit = _free_slot(shortcuts)
            if digit is None:
                break
            shortcuts[digit] = {"label": label, "mode": DEFAULT_DIGIT_MODE}
            assigned += 1
        if assigned:
            logger.info(
                f"Digit shortcuts pre-assigned to {assigned} project "
                f"label(s)"
            )
            _persist_digits(widget)
        return assigned


def _assigned_digits(shortcuts):
    return {int(key) for key in shortcuts if str(key).lstrip("-").isdigit()}


def _digit_for_label(shortcuts, label):
    for digit, data in shortcuts.items():
        if data.get("label") == label:
            return digit
    return None


def _free_slot(shortcuts):
    used = _assigned_digits(shortcuts)
    for digit in DIGIT_SLOTS:
        if digit not in used:
            return digit
    return None


def _persist_digits(widget):
    config = getattr(widget, "_config", None)
    if config is None:
        return
    config["digit_shortcuts"] = widget.drawing_digit_shortcuts
    save_config(config)
