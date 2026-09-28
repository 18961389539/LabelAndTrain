"""Dock and panel visibility toggles, moved out of LabelingWidget by scripts/extract_method.py."""


def toggle_shapes_visibility(widget, checked):
    widget.shape_dock.setVisible(checked)


def show_attributes_panel(widget):
    if hasattr(widget, "scroll_area"):
        widget.scroll_area.setVisible(True)


def hide_attributes_panel(widget):
    if hasattr(widget, "scroll_area"):
        widget.scroll_area.setVisible(False)
