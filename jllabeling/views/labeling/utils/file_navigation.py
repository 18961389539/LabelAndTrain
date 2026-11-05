"""Image navigation: prev/next, the unchecked-queue jumps, and the next-files signal. Moved out of LabelingWidget by scripts/extract_method.py."""

from ..filelist.controller import FileReviewController
from typing import Optional
from PyQt6.QtCore import QCoreApplication
import os.path as osp
from PyQt6 import QtCore, QtGui, QtWidgets
from ....app_info import __appname__, __version__, __preferred_device__


def open_prev_unchecked_image(widget):
    """Delegates to filelist.controller (action wiring stays)."""
    # Built on demand: the controller is stateless, and light test
    # stubs never carry an instance.
    FileReviewController(widget).open_prev_unchecked_image()


def open_next_unchecked_image(widget, _value=False):
    """Delegates to filelist.controller (action wiring stays)."""
    # Built on demand: the controller is stateless, and light test
    # stubs never carry an instance.
    FileReviewController(widget).open_next_unchecked_image(_value)


def open_prev_image(widget, _value=False):
    if widget._paging_blocked_by_drawing():
        return
    if not widget.may_continue(silent=True):
        return
    if widget.file_list_widget.count() <= 0:
        return
    if widget.filename is None:
        return
    current_index = widget.fn_to_index[str(widget.filename)]
    target_index = widget._next_visible_row(current_index, -1)
    if target_index < 0 or target_index == current_index:
        return
    filename = widget.file_list_widget.item(target_index).text()
    if filename:
        widget.load_file(filename)


def open_next_image(widget, _value=False, load=True):
    if widget._paging_blocked_by_drawing():
        return
    if not widget.may_continue(silent=True):
        return
    count = widget.file_list_widget.count()
    if count <= 0:
        return
    filename = None
    if widget.filename is None:
        first_row = widget._first_visible_row()
        if first_row < 0:
            return
        filename = widget.file_list_widget.item(first_row).text()
    else:
        current_index = widget.fn_to_index[str(widget.filename)]
        target_index = widget._next_visible_row(current_index, 1)
        if target_index < 0 or target_index == current_index:
            return
        filename = widget.file_list_widget.item(target_index).text()
    widget.filename = filename
    if widget.filename and load:
        widget.load_file(widget.filename)


def inform_next_files(widget, filename):
    """Inform the next files to be annotated.
    This list can be used by the user to preload the next files
    or running a background process to process them
    """
    next_files = widget.get_next_files(filename, 5)
    if next_files:
        widget.next_files_changed.emit(next_files)


def open_folder_dialog(widget, _value=False, dirpath=None):
    if not widget.may_continue():
        return

    default_open_dir_path = dirpath if dirpath else "."
    if widget.last_open_dir and osp.exists(widget.last_open_dir):
        default_open_dir_path = widget.last_open_dir
    else:
        default_open_dir_path = (
            osp.dirname(widget.filename) if widget.filename else "."
        )

    target_dir_path = str(
        QtWidgets.QFileDialog.getExistingDirectory(
            widget,
            QCoreApplication.translate("LabelingWidget", "%s - Open Directory")
            % __appname__,
            default_open_dir_path,
            QtWidgets.QFileDialog.Option.ShowDirsOnly
            | QtWidgets.QFileDialog.Option.DontResolveSymlinks,
        )
    )
    widget.import_image_folder(target_dir_path)


def on_navigator_zoom_changed(
    widget, zoom_percentage: int, mouse_pos: Optional[QtCore.QPoint] = None
) -> None:
    """Handle zoom change from navigator controls."""

    if not hasattr(widget, "image") or widget.image.isNull():
        return

    if mouse_pos is not None:
        canvas_pos = widget._convert_navigator_pos_to_canvas(mouse_pos)
        if canvas_pos:
            canvas_width_old = widget.canvas.width()

            widget.zoom_widget.setValue(zoom_percentage)
            widget.zoom_mode = widget.MANUAL_ZOOM
            widget.view_state.zoom[widget.filename] = (
                widget.zoom_mode,
                zoom_percentage,
            )
            widget.paint_canvas()

            canvas_width_new = widget.canvas.width()
            if canvas_width_old != canvas_width_new:
                canvas_scale_factor = canvas_width_new / canvas_width_old
                x_shift = round(
                    canvas_pos.x() * canvas_scale_factor - canvas_pos.x()
                )
                y_shift = round(
                    canvas_pos.y() * canvas_scale_factor - canvas_pos.y()
                )
                widget.set_scroll(
                    QtCore.Qt.Orientation.Horizontal,
                    widget.scroll_bars[
                        QtCore.Qt.Orientation.Horizontal
                    ].value()
                    + x_shift,
                )
                widget.set_scroll(
                    QtCore.Qt.Orientation.Vertical,
                    widget.scroll_bars[QtCore.Qt.Orientation.Vertical].value()
                    + y_shift,
                )

            return

    # Handle direct zoom changes
    if (
        hasattr(widget, "canvas")
        and hasattr(widget.canvas, "width")
        and hasattr(widget.canvas, "height")
    ):
        if hasattr(widget.navigator_dialog, "navigator"):
            nav_widget = widget.navigator_dialog.navigator
            if (
                hasattr(nav_widget, "viewport_rect")
                and not nav_widget.viewport_rect.isEmpty()
            ):
                nav_rect_center_x = nav_widget.viewport_rect.center().x()
                nav_rect_center_y = nav_widget.viewport_rect.center().y()
                canvas_pos = widget._convert_navigator_pos_to_canvas(
                    QtCore.QPoint(
                        int(nav_rect_center_x), int(nav_rect_center_y)
                    )
                )

                if canvas_pos:
                    canvas_width_old = widget.canvas.width()

                    widget.zoom_widget.setValue(zoom_percentage)
                    widget.zoom_mode = widget.MANUAL_ZOOM
                    widget.view_state.zoom[widget.filename] = (
                        widget.zoom_mode,
                        zoom_percentage,
                    )
                    widget.paint_canvas()

                    canvas_width_new = widget.canvas.width()
                    if canvas_width_old != canvas_width_new:
                        canvas_scale_factor = (
                            canvas_width_new / canvas_width_old
                        )
                        x_shift = round(
                            canvas_pos.x() * canvas_scale_factor
                            - canvas_pos.x()
                        )
                        y_shift = round(
                            canvas_pos.y() * canvas_scale_factor
                            - canvas_pos.y()
                        )
                        widget.set_scroll(
                            QtCore.Qt.Orientation.Horizontal,
                            widget.scroll_bars[
                                QtCore.Qt.Orientation.Horizontal
                            ].value()
                            + x_shift,
                        )
                        widget.set_scroll(
                            QtCore.Qt.Orientation.Vertical,
                            widget.scroll_bars[
                                QtCore.Qt.Orientation.Vertical
                            ].value()
                            + y_shift,
                        )
                    return

        widget.zoom_widget.setValue(zoom_percentage)
        widget.zoom_mode = widget.MANUAL_ZOOM
        widget.view_state.zoom[widget.filename] = (
            widget.zoom_mode,
            zoom_percentage,
        )
        widget.paint_canvas()
    else:
        widget.zoom_widget.setValue(zoom_percentage)
        widget.zoom_mode = widget.MANUAL_ZOOM
        widget.view_state.zoom[widget.filename] = (
            widget.zoom_mode,
            zoom_percentage,
        )
        widget.paint_canvas()
