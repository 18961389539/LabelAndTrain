"""Digit-shortcut behaviour for the labeling widget.

Owns the digit -> label flow: the manager dialog (Alt+D), the create
dispatch behind the 0-9 keys, and the auto-assignment of free digits to
labels seen for the first time. The shortcut map itself stays on the
widget (``drawing_digit_shortcuts`` / ``digit_to_label``) so the canvas
callbacks and the settings runtime keep reading it from one place.
"""

from PyQt6 import QtWidgets

from ....config import save_config
from ..logger import logger
from ..shape import Shape
from ..widgets.label_dialog import DigitShortcutDialog


class DigitShortcutController:
    """Holds the widget's digit-shortcut behaviour; the widget delegates."""

    def __init__(self, widget):
        self._widget = widget

    def digit_shortcut_manager(self):
        widget = self._widget
        digit_shortcut_dialog = DigitShortcutDialog(parent=widget)
        result = digit_shortcut_dialog.exec()
        if result == QtWidgets.QDialog.DialogCode.Accepted:
            widget._config["digit_shortcuts"] = (
                widget.drawing_digit_shortcuts
            )
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
        """Assign free digit shortcuts (1-9) to labels seen for the first
        time, so multi-class annotation does not require manual setup via
        Alt+D. The shortcut creates the label with the shape type it was
        first seen as; users can still re-map via the digit shortcut
        manager. ``None`` digit_shortcuts (feature disabled) is respected.
        """
        widget = self._widget
        if widget.drawing_digit_shortcuts is None:
            return
        assigned = False
        used = {
            int(k) for k in widget.drawing_digit_shortcuts if str(k).isdigit()
        }
        for shape in shapes:
            label = getattr(shape, "label", None)
            if not label:
                continue
            if any(
                v.get("label") == label
                for v in widget.drawing_digit_shortcuts.values()
            ):
                continue
            for digit in range(1, 10):
                if digit in used:
                    continue
                widget.drawing_digit_shortcuts[digit] = {
                    "label": label,
                    "mode": shape.shape_type or "rectangle",
                }
                used.add(digit)
                assigned = True
                logger.info(
                    f"Digit shortcut {digit} auto-assigned to "
                    f"'{label}' ({shape.shape_type})"
                )
                break
            if len(used) >= 9:
                break
        if assigned:
            widget._config["digit_shortcuts"] = widget.drawing_digit_shortcuts
            save_config(widget._config)
