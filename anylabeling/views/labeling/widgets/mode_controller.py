"""Draw / brush / edit mode switching for the labeling widget.

Owns the "which drawing mode is the canvas in" state machine: switching
between the create modes (polygon, rectangle, point, ...), the brush
polygon mode, brush editing of a selected polygon, and plain edit mode.
It also arms/disarms the toolbar actions that select those modes so the
UI always reflects the canvas state.

The widget keeps thin delegates with the same names so canvas signals,
the digit-shortcut controller, the settings runtime applier and the tests
keep calling the widget as before.
"""

from anylabeling.services.auto_labeling.types import AutoLabelingMode


class ModeController:
    """Holds the widget's draw/brush/edit mode behaviour; widget delegates."""

    def __init__(self, widget):
        self._widget = widget

    def toggle_drawing_sensitive(self, drawing=True):
        """Toggle drawing sensitive.

        In the middle of drawing, toggling between modes should be disabled.
        """
        widget = self._widget
        widget.actions.edit_mode.setEnabled(not drawing)
        widget.actions.undo_last_point.setEnabled(drawing)
        widget.actions.undo.setEnabled(not drawing)
        widget.actions.delete.setEnabled(not drawing)
        widget.actions.union_selection.setEnabled(not drawing)
        widget.update_labeling_instruction()

    def toggle_draw_mode(
        self,
        edit=True,
        create_mode="rectangle",
        disable_auto_labeling=True,
        preserve_brush_mode=False,
    ):
        widget = self._widget
        if not preserve_brush_mode:
            if getattr(widget.canvas, "is_brush_mode", False):
                widget.canvas.cancel_brush_mode()
            elif widget.actions.edit_brush_mode.isChecked():
                widget.actions.edit_brush_mode.setChecked(False)
        # Disable auto labeling if needed
        if (
            disable_auto_labeling
            and widget.auto_labeling_widget.auto_labeling_mode
            != AutoLabelingMode.NONE
        ):
            widget.clear_auto_labeling_marks()
            widget.auto_labeling_widget.set_auto_labeling_mode(None)

        widget.canvas.set_editing(edit)
        widget.canvas.create_mode = create_mode
        widget.canvas._brush_drawing = False
        if edit:
            self.enable_create_mode_actions()
        else:
            widget.hide_attributes_panel()
            widget.actions.union_selection.setEnabled(False)
            create_actions = self.create_mode_actions()
            if create_mode not in create_actions:
                raise ValueError(f"Unsupported create_mode: {create_mode}")
            self.enable_create_mode_actions()
            create_actions[create_mode].setEnabled(False)
        widget.actions.edit_mode.setEnabled(not edit)
        widget.update_labeling_instruction()

    def create_mode_actions(self):
        """Map each canvas draw mode to the action that selects it.

        Kept in sync with ``Shape.get_supported_shape()``; a mode missing here
        raises in ``toggle_draw_mode`` instead of silently doing nothing.
        """
        actions = self._widget.actions
        return {
            "polygon": actions.create_mode,
            "rectangle": actions.create_rectangle_mode,
            "point": actions.create_point_mode,
            "cuboid": actions.create_cuboid_mode,
            "rotation": actions.create_rotation_mode,
            "quadrilateral": actions.create_quadrilateral_mode,
            "circle": actions.create_circle_mode,
            "line": actions.create_line_mode,
            "linestrip": actions.create_linestrip_mode,
        }

    def enable_create_mode_actions(self):
        """Re-arm every drawing mode when leaving or entering one."""
        widget = self._widget
        for mode_action in self.create_mode_actions().values():
            mode_action.setEnabled(True)
        widget.actions.create_brush_polygon_mode.setEnabled(True)
        for digit_action in widget.actions.digit_shortcut_actions:
            digit_action.setEnabled(True)

    def toggle_brush_polygon_mode(self):
        """Toggle brush drawing mode for polygons."""
        widget = self._widget
        if (
            widget.canvas.drawing()
            and widget.canvas.create_mode == "polygon"
            and widget.canvas._brush_drawing
        ):
            self.toggle_draw_mode(True)
            return
        self.toggle_draw_mode(False, create_mode="polygon")
        widget.canvas._brush_drawing = True
        widget.actions.create_mode.setEnabled(True)
        widget.actions.create_brush_polygon_mode.setEnabled(False)

    def set_edit_mode(self):
        widget = self._widget
        # Disable auto labeling
        widget.clear_auto_labeling_marks()
        widget.auto_labeling_widget.set_auto_labeling_mode(None)

        self.toggle_draw_mode(True)
        widget.update_labeling_instruction()

    def toggle_brush_mode(self, checked: bool) -> None:
        """Enable or disable brush editing for a polygon.

        Enabling requires exactly one selected polygon and switches the
        canvas to edit mode before brush editing starts.

        Args:
            checked: ``True`` when the toolbar toggle is switched on.
        """
        widget = self._widget
        if checked:
            selected_shapes = widget.canvas.selected_shapes
            if (
                len(selected_shapes) != 1
                or selected_shapes[0].shape_type != "polygon"
                or selected_shapes[0].locked
            ):
                widget.actions.edit_brush_mode.setChecked(False)
                return
            if widget.canvas.current is not None:
                widget.canvas.current = None
                widget.canvas.set_hiding(False)
                widget.canvas.drawing_polygon.emit(False)
                widget.canvas.update()
            self.toggle_draw_mode(True, preserve_brush_mode=True)
            widget.canvas.set_brush_mode(True)
            widget.update_labeling_instruction()
            return

        if getattr(widget.canvas, "is_brush_mode", False):
            widget.canvas.set_brush_mode(False)
        widget.update_labeling_instruction()

    def on_brush_mode_changed(self, enabled: bool) -> None:
        """Synchronize brush action and lock the active shape selection."""
        widget = self._widget
        widget.actions.edit_brush_mode.setChecked(enabled)
        widget.label_list.setEnabled(not enabled)
