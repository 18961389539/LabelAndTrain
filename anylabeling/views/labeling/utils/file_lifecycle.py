"""File lifecycle: load, delete, import.

Methods and helpers moved out of LabelingWidget by
scripts/extract_method.py; the class keeps thin stubs so wiring and
tests stay put. Every path here touches the annotator's data (loading
replaces the canvas, deleting throws files away), which is exactly why
they live together: the dangerous code shares one address.
"""

import os
from ..widgets import (
    AutoLabelingWidget,
    BrightnessContrastDialog,
    Canvas,
    CanvasAdjustmentWidget,
    CanvasEmptyStateWidget,
    CrosshairSettingsDialog,
    FileDialogPreview,
    FloatingToolPanel,
    ShapeModifyDialog,
    GroupIDFilterComboBox,
    LabelDialog,
    LabelFilterComboBox,
    LabelListWidget,
    LabelListWidgetItem,
    LabelModifyDialog,
    GroupIDModifyDialog,
    OverviewDialog,
    Popup,
    copy_text_to_system_clipboard,
    SearchBar,
    ToolBar,
    UniqueLabelQListWidget,
    ZoomWidget,
    NavigatorDialog,
)
from ..utils.qt import new_icon_path
from . import project_view
from ..utils.session_snapshot import snapshot_before_label_write
from ..filelist.controller import FileReviewController
from anylabeling.services.auto_labeling.types import AutoLabelingMode
from ..filelist.roles import (
    CHECKED_FIELD,
    FILE_ANNOTATION_ROLE,
    FILE_LOW_CONF_ROLE,
    FILE_NEGATIVE_ROLE,
    FILE_REVIEW_ROLE,
    FILE_REVIEWED_AT_ROLE,
    REVIEW_STATE_FIELD,
    REVIEWED_AT_FIELD,
)
from ..utils.file_search import (
    parse_search_pattern,
    matches_filename,
    matches_label_attribute,
)
from .. import project_settings
import re
from PyQt6.QtCore import QCoreApplication, Qt, pyqtSlot
from PyQt6 import QtCore, QtGui, QtWidgets
from ..label_file import LabelFile, LabelFileError
from .. import utils
from ..schema import REVIEW_NOTE_FIELD, REVIEW_REJECTED
import os.path as osp
import shutil
import time

from ..filelist import items as filelist_items
from ..logger import logger
from . import file_list_ops


def _report_inherited_shapes(widget, count):
    """Announce shapes inherited from the previous image (``keep_prev``).

    Those shapes are a proposal, not an edit: they are deliberately left
    unsaved (see ``LabelingWidget.set_dirty``), so the annotator has to be
    told instead of finding out at training time.
    """
    if count <= 0:
        return
    message = QCoreApplication.translate(
        "LabelingWidget",
        "已继承上一张的 {n} 个标注，尚未写入本图"
        "（按 Ctrl+S 保存，或直接编辑后自动保存）",
    ).replace("{n}", str(count))
    logger.info(
        f"keep_prev: inherited {count} shape(s) from the previous image; "
        "they will not be auto-saved until the annotator edits or saves."
    )
    status = getattr(widget, "status", None)
    if callable(status):
        status(message, 8000)


def _announce_rework_reason(widget):
    """Surface the rework reason when a rejected file is opened.

    The reason lives on the file-row tooltip, but the annotator works on
    the canvas -- without this the one piece of feedback they need would
    sit behind a hover on a list they are not looking at.
    """
    if widget._current_review_state() != REVIEW_REJECTED:
        return
    note = widget.other_data.get(REVIEW_NOTE_FIELD)
    if note:
        widget.status(
            QCoreApplication.translate("LabelingWidget", "需返工：%1").replace(
                "%1", str(note)
            ),
            8000,
        )
    else:
        widget.status(
            QCoreApplication.translate("LabelingWidget", "此图已打回，需返工"),
            5000,
        )


def move_file_to_delete_folder(src_path, folder_hint=None):
    """Move a file into a `_delete_` folder next to it (recoverable)."""
    if not src_path or not osp.exists(src_path):
        return None
    base_dir = folder_hint or osp.dirname(src_path)
    delete_dir = osp.join(base_dir, "_delete_")
    os.makedirs(delete_dir, exist_ok=True)
    dest = osp.join(delete_dir, osp.basename(src_path))
    if osp.exists(dest):
        stem, ext = osp.splitext(osp.basename(src_path))
        dest = osp.join(delete_dir, f"{stem}_{int(time.time())}{ext}")
    shutil.move(src_path, dest)
    return dest


def load_file(widget, filename=None):  # noqa: C901
    """Load the specified file, or the last opened file if None."""

    # NOTE(jack): Does we need to save the config here?
    # save_config(widget._config)

    # For auto labeling, clear the previous marks
    # and inform the next files to be annotated
    # NOTE(jack): this is not needed for now
    # widget.clear_auto_labeling_marks()
    # widget.inform_next_files(filename)

    # Changing file_list_widget loads file
    if str(filename) in widget.fn_to_index and (
        widget.file_list_widget.currentRow()
        != widget.fn_to_index[str(filename)]
    ):
        widget.file_list_widget.setCurrentRow(
            widget.fn_to_index[str(filename)]
        )
        current_item = widget.file_list_widget.currentItem()
        if current_item is not None:
            widget.file_list_widget.scrollToItem(
                current_item,
                QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible,
            )
        widget.file_list_widget.update()
        return False

    # A debounced auto-save belongs to the image currently open: land it
    # before any state reset tears its target path down.
    widget.flush_pending_auto_save()
    widget.reset_state()
    widget.canvas.setEnabled(False)

    if filename is None:
        filename = widget.settings.value("filename", "")
    filename = str(filename)
    if not QtCore.QFile.exists(filename):
        widget.error_message(
            QCoreApplication.translate("LabelingWidget", "Error opening file"),
            QCoreApplication.translate(
                "LabelingWidget", "No such file: <b>%s</b>"
            )
            % filename,
        )
        return False

    # assumes same name, but json extension
    label_file = osp.splitext(filename)[0] + ".json"
    image_dir = None
    if widget.output_dir:
        image_dir = osp.dirname(filename)
        label_file_without_path = osp.basename(label_file)
        label_file = widget.output_dir + "/" + label_file_without_path

    if QtCore.QFile.exists(label_file) and LabelFile.is_label_file(label_file):
        try:
            widget.label_file = LabelFile(label_file, image_dir)
        except LabelFileError as e:
            widget.error_message(
                QCoreApplication.translate(
                    "LabelingWidget", "Error opening file"
                ),
                QCoreApplication.translate(
                    "LabelingWidget",
                    "<p><b>%s</b></p>"
                    "<p>Make sure <i>%s</i> is a valid label file.",
                )
                % (e, label_file),
            )
            widget.status(
                QCoreApplication.translate(
                    "LabelingWidget", "Error reading %s"
                )
                % label_file
            )
            return False
        widget.image_data = widget.label_file.image_data
        widget.image_path = osp.join(
            osp.dirname(label_file),
            widget.label_file.image_path,
        )
        widget.other_data = widget.label_file.other_data
        widget.other_data[CHECKED_FIELD] = widget._annotation_checked()
        # Negative-sample badge: an on-disk json with zero shapes is a
        # confirmed background image (YOLO negative sample). Refresh the
        # file list marker whenever such a file is (re)opened.
        try:
            neg_items = widget.file_list_widget.findItems(
                widget.image_path, Qt.MatchFlag.MatchExactly
            )
            if len(neg_items) == 1:
                filelist_items.set_file_item_annotated(
                    widget,
                    neg_items[0],
                    True,
                    negative=len(widget.label_file.shapes) == 0,
                )
                filelist_items.set_file_item_low_conf(
                    widget,
                    neg_items[0],
                    widget.file_quality_controller.shapes_need_review(
                        widget.label_file.shapes
                    ),
                )
        except Exception:  # noqa: BLE001
            pass
    else:
        widget.image_data = LabelFile.load_image_file(filename)
        if widget.image_data:
            widget.image_path = filename
        widget.label_file = None
        widget.other_data = {CHECKED_FIELD: False}

    # TODO(jack): icc profile issue warning
    # - qt.gui.icc: fromIccProfile: failed minimal tag size sanity
    # - qt.gui.icc: fromIccProfile: invalid tag offset alignment
    # Decode large images off the UI thread so opening a big frame never
    # hard-freezes the whole window into a "Not Responding" state.
    image, pil_cache = widget._decode_image_data(widget.image_data, filename)

    if image is None or image.isNull():
        formats = [f"*{ext}" for ext in utils.get_supported_image_extensions()]
        widget.error_message(
            QCoreApplication.translate("LabelingWidget", "Error opening file"),
            QCoreApplication.translate(
                "LabelingWidget",
                "<p>Make sure <i>{0}</i> is a valid image file.<br/>"
                "Supported image formats: {1}</p>",
            ).format(filename, ",".join(formats)),
        )
        widget.status(
            QCoreApplication.translate("LabelingWidget", "Error reading %s")
            % filename
        )
        return False
    widget.image = image
    widget.filename = filename
    # Now that the image is known, point the canvas undo history at it:
    # the previous image's stack is banked instead of dropped.
    widget.canvas.shape_history.enter(filename)

    if (
        hasattr(widget, "navigator_dialog")
        and widget.navigator_dialog.isVisible()
    ):
        widget.navigator_dialog.set_image(QtGui.QPixmap.fromImage(image))
        widget.update_navigator_shapes()
    if (
        hasattr(widget, "_should_restore_navigator")
        and widget._should_restore_navigator
    ):
        widget._should_restore_navigator = False
        if widget.navigator_dialog.isVisible():
            widget.update_navigator_viewport()
    if widget._config["keep_prev"]:
        prev_shapes = widget.canvas.shapes
    widget.canvas.load_pixmap(QtGui.QPixmap.fromImage(image))

    # load label flags
    flags = dict.fromkeys(widget.image_flags or [], False)
    if widget.label_file:
        for shape in widget.label_file.shapes:
            default_flags = {}
            if widget._config["label_flags"]:
                for pattern, keys in widget._config["label_flags"].items():
                    if re.match(pattern, shape.label):
                        for key in keys:
                            default_flags[key] = False
                shape.flags = {
                    **default_flags,
                    **shape.flags,
                }
        widget.load_shapes(widget.label_file.shapes, update_last_label=False)
        if widget.label_file.flags is not None:
            flags.update(widget.label_file.flags)
    widget.load_flags(flags)

    # load shapes
    if widget._config["keep_prev"] and widget.no_shape():
        widget.load_shapes(prev_shapes, replace=False, update_last_label=False)
        widget.set_dirty(from_inherited=True)
        _report_inherited_shapes(widget, len(widget.canvas.shapes))
    else:
        widget.set_clean()
    widget.canvas.setEnabled(True)

    # The stacks are per image now, so the menu entries that reach them have
    # to be re-read after a load: a restored history behind a still-disabled
    # Ctrl+Z is no undo at all.
    actions = getattr(widget, "actions", None)
    if actions is not None:
        actions.undo.setEnabled(widget.canvas.is_shape_restorable)
        actions.redo.setEnabled(widget.canvas.is_shape_redoable)

    # set zoom values
    is_initial_load = widget.view_state.is_empty()
    if widget.filename in widget.view_state.zoom:
        widget.zoom_mode = widget.view_state.zoom[widget.filename][0]
        widget.set_zoom(widget.view_state.zoom[widget.filename][1])
    elif is_initial_load or not widget._config["keep_prev_scale"]:
        widget.adjust_scale(initial=True)
    # set scroll values
    for orientation in widget.view_state.scroll:
        if widget.filename in widget.view_state.scroll[orientation]:
            widget.set_scroll(
                orientation,
                widget.view_state.scroll[orientation][widget.filename],
            )

    # set brightness contrast values
    brightness, contrast = widget.view_state.brightness_contrast.get(
        widget.filename, (None, None)
    )
    if widget._config["keep_prev_brightness"] and widget.recent_files:
        brightness, _ = widget.view_state.brightness_contrast.get(
            widget.recent_files[0], (None, None)
        )
    if widget._config["keep_prev_contrast"] and widget.recent_files:
        _, contrast = widget.view_state.brightness_contrast.get(
            widget.recent_files[0], (None, None)
        )
    widget.view_state.brightness_contrast[widget.filename] = (
        brightness,
        contrast,
    )
    # Always refresh the dialog's source image so the inline adjustment
    # sliders can reuse its brightness/contrast pipeline (which includes
    # 16-bit grayscale handling).  For large images this PIL copy was
    # already produced by the background decoder (pil_cache).
    widget.brightness_contrast_dialog.update_image(
        pil_cache
        if pil_cache is not None
        else utils.img_data_to_pil(widget.image_data)
    )
    widget.brightness_contrast_dialog.set_values(
        brightness if brightness is not None else 50,
        contrast if contrast is not None else 50,
    )
    if brightness is not None or contrast is not None:
        widget.brightness_contrast_dialog.on_new_value()
    # Sync the inline adjustment sliders (50 is the neutral value).
    widget.canvas_adjustment.set_brightness_contrast(
        brightness if brightness is not None else 50,
        contrast if contrast is not None else 50,
    )

    widget.paint_canvas()
    widget.add_recent_file(widget.filename)
    widget.toggle_actions(True)
    widget.canvas.setFocus()
    widget._sync_annotation_checked_state()
    _announce_rework_reason(widget)
    widget.update_thumbnail_display()

    # Reveal the adjustment panel now that an image is loaded.
    widget.canvas_adjustment.show()
    widget._position_canvas_adjustment()
    widget._sync_empty_canvas_state()
    _maybe_focus_low_confidence_shapes(widget)
    # The hint bar describes the state this file just established (how many
    # shapes, drawing/brush modes, "no image" vs open); it used to be rendered
    # once at construction and only refreshed by unrelated triggers such as a
    # scroll-range change, so it kept the boot-time "尚未打开图片" line while an
    # image was open.
    widget.update_labeling_instruction()

    return True


def handle_drag_enter(widget, event):
    """Accept a drag that carries an image file or a folder.

    Folders used to be rejected here -- only image extensions were
    matched -- even though "打开文件夹" is the first line of the empty
    canvas guidance, so the most natural drag (a dataset folder onto the
    window) did nothing at all.
    """
    if not event.mimeData().hasUrls():
        event.ignore()
        return
    extensions = tuple(utils.get_supported_image_extensions())
    for url in event.mimeData().urls():
        path = url.toLocalFile()
        if not path:
            continue
        if path.lower().endswith(extensions) or osp.isdir(path):
            event.accept()
            return
    event.ignore()


def handle_drop(widget, event):
    """Open the first dropped folder, else import the dropped images.

    One folder at a time on purpose: merging two datasets into one list
    is a question this drop cannot answer, and the first folder is what
    the gesture meant.
    """
    items = [url.toLocalFile() for url in event.mimeData().urls()]
    folders = [item for item in items if item and osp.isdir(item)]
    if folders:
        widget.import_image_folder(folders[0])
        return
    if not widget.may_continue():
        event.ignore()
        return
    widget.import_dropped_image_files(items)


def _resume_remembered_file(widget):
    """Open the image this project was last on; ``False`` when unavailable.

    Runs between the row scan and ``open_next_image`` because that call is
    the "nothing remembered" fallback. The remembered path is checked
    against the freshly built image list, so an image deleted since the
    last visit falls through instead of becoming a phantom row.
    """
    target = getattr(widget, "_project_resume_file", None)
    widget._project_resume_file = None
    if not target or target not in widget.image_list:
        return False
    widget.load_file(target)
    return True


def import_image_folder(widget, dirpath, pattern=None, load=True):
    if not widget.may_continue() or not dirpath:
        return

    widget.last_open_dir = dirpath
    _record_recent_dir(widget, dirpath)
    # Per-project settings: flush the previous dataset's state, then
    # restore this one's output dir before the scan below routes label
    # files (an explicit output_dir always wins over the stored one).
    project_settings.begin_project_switch(
        widget, project_settings.dataset_dir_for(filename=dirpath)
    )
    widget.filename = None
    # A fresh project answers nothing to the 1-9 keys until a shape exists --
    # exactly the step those keys are for. Give the declared labels their
    # slots up front; labels already mapped keep theirs.
    widget.digit_shortcut_controller.assign_label_digits(
        widget._config["labels"]
    )
    widget.file_list_widget.clear()
    # Rows are renumbered below, so the old folder's entries must go too:
    # a stale index makes _current_file_item() point at another image.
    widget.fn_to_index.clear()
    image_files = []
    label_files = []

    search_pattern = parse_search_pattern(pattern) if pattern else None

    # Populate the list first (pure fs metadata, cheap), then refresh
    # the per-file review "checked" dots in the background so a large
    # folder does not freeze the UI for seconds.
    widget.async_label_checker.stop()
    widget.file_list_widget.setUpdatesEnabled(False)
    try:
        for file_index, filename in enumerate(
            utils.scan_all_images(dirpath), start=1
        ):
            if search_pattern:
                if search_pattern.mode == "index":
                    if search_pattern.index != file_index:
                        continue
                else:
                    if not matches_filename(filename, search_pattern):
                        continue

                    if search_pattern.mode == "attribute":
                        label_file = osp.splitext(filename)[0] + ".json"
                        if widget.output_dir:
                            label_file_without_path = osp.basename(label_file)
                            label_file = (
                                widget.output_dir
                                + "/"
                                + label_file_without_path
                            )

                        if not matches_label_attribute(
                            filename, label_file, search_pattern
                        ):
                            continue

            image_files.append(filename)
            label_file = osp.splitext(filename)[0] + ".json"
            if widget.output_dir:
                label_file_without_path = osp.basename(label_file)
                label_file = widget.output_dir + "/" + label_file_without_path
            label_files.append(label_file)
            item = widget._create_file_list_item(
                filename, label_file, read_checked=False
            )
            widget.file_list_widget.addItem(item)
            widget.fn_to_index[filename] = widget.file_list_widget.count() - 1
    finally:
        widget.file_list_widget.setUpdatesEnabled(True)

    widget.actions.open_next_image.setEnabled(True)
    widget.actions.open_prev_image.setEnabled(True)
    widget.actions.open_next_unchecked_image.setEnabled(True)
    widget.actions.open_prev_unchecked_image.setEnabled(True)
    widget.toggle_actions(True)
    # A project resumes where it was left, not at the first image. The
    # fallback below is what "nothing remembered" means; load=False (a
    # bulk import that will be painted later) skips both.
    if not (load and _resume_remembered_file(widget)):
        widget.open_next_image(load=load)

    if image_files and widget._config.get("exif_scan_enabled", True):
        widget.async_exif_scanner.start_scan(image_files)
    widget._refresh_file_panel()
    if pattern is None and image_files:
        widget._load_classes_from_folder(dirpath)
        # classes.txt keeps precedence; the project record only fills
        # the panel for folders whose labels were built interactively.
        project_settings.end_project_switch(
            widget, project_settings.dataset_dir_for(filename=dirpath)
        )
        widget._maybe_prompt_missing_labels()
        _maybe_show_smart_tools_guide(widget, dirpath)

    # Background "checked" dot refresh (after rows exist so the batch
    # callback can address them by index).
    if label_files:
        widget.async_label_checker.start(
            label_files,
            on_batch=(lambda s, i: _apply_checked_batch(widget, s, i)),
        )


def delete_file(widget):
    mb = QtWidgets.QMessageBox
    if widget._config.get("keep_prev", False):
        mb.warning(
            widget,
            QCoreApplication.translate("LabelingWidget", "Attention"),
            QCoreApplication.translate(
                "LabelingWidget",
                "Please disable 'Keep Previous Annotation' before deleting the label file.",
            ),
            mb.StandardButton.Ok,
        )
        return

    msg = QCoreApplication.translate(
        "LabelingWidget",
        "当前标签文件将移到图片目录下的 _delete_ 文件夹，可从该目录找回。\n"
        "确定删除吗？",
    )
    if not widget._confirm_destructive_action(
        QCoreApplication.translate("LabelingWidget", "Attention"), msg
    ):
        return

    label_file = widget.get_label_file()
    if osp.exists(label_file):
        image_file = None
        try:
            image_file = widget.get_image_file()
        except Exception:
            image_file = None
        folder_hint = (
            osp.dirname(image_file) if image_file else osp.dirname(label_file)
        )
        dest = move_file_to_delete_folder(label_file, folder_hint)
        logger.info(f"Label file is moved to: {dest}")

        item = widget.file_list_widget.currentItem()
        if item is not None:
            filelist_items.set_file_item_annotated(
                widget, item, False, negative=False
            )
            widget._set_file_item_checked(item, False)

        filename = widget.filename
        widget.reset_state()
        widget.filename = filename
        if widget.filename:
            widget.load_file(widget.filename)


def delete_image_file(widget):
    if len(widget.image_list) < 2:
        widget.status(
            QCoreApplication.translate(
                "LabelingWidget",
                "至少需要两张图片才能删除图片文件："
                "删除后会自动切到相邻图片。",
            ),
            4000,
        )
        return

    mb = QtWidgets.QMessageBox
    if widget._config.get("keep_prev", False):
        mb.warning(
            widget,
            QCoreApplication.translate("LabelingWidget", "Attention"),
            QCoreApplication.translate(
                "LabelingWidget",
                "Please disable 'Keep Previous Annotation' before deleting the image file.",
            ),
            mb.StandardButton.Ok,
        )
        return

    msg = QCoreApplication.translate(
        "LabelingWidget",
        "You are about to permanently delete this image file, "
        "proceed anyway?",
    )
    if not widget._confirm_destructive_action(
        QCoreApplication.translate("LabelingWidget", "Attention"), msg
    ):
        return

    image_file = widget.get_image_file()
    if osp.exists(image_file):
        image_path, image_name = osp.split(image_file)
        save_path = osp.join(image_path, "..", "_delete_")
        os.makedirs(save_path, exist_ok=True)
        save_file = osp.join(save_path, image_name)
        shutil.move(image_file, save_file)
        logger.info(f"Image file is moved to: {osp.realpath(save_file)}")

        label_dir_path = osp.dirname(widget.filename)
        if widget.output_dir:
            label_dir_path = widget.output_dir
        label_name = osp.splitext(image_name)[0] + ".json"
        label_file = osp.join(label_dir_path, label_name)
        if not osp.exists(label_file):
            label_file = osp.join(osp.dirname(image_file), label_name)
        if osp.exists(label_file):
            os.remove(label_file)
            logger.info(f"Label file is removed: {image_file}")

        filename = None
        if widget.filename is None:
            filename = widget.image_list[0]
        else:
            current_index = widget.fn_to_index[str(widget.filename)]
            if current_index + 1 < len(widget.image_list):
                filename = widget.image_list[current_index + 1]
            else:
                filename = widget.image_list[0]

        widget.reset_state()
        if osp.isfile(image_path):
            image_path = osp.dirname(image_path)
        widget.import_image_folder(image_path)

        widget.filename = filename
        if widget.filename:
            widget.load_file(widget.filename)


def save_labels(widget, filename):
    label_file = LabelFile()
    # Get current shapes
    # Excluding auto labeling special shapes
    shapes = [
        item.shape().to_dict()
        for item in widget.label_list
        if item.shape().label
        not in [
            AutoLabelingMode.OBJECT,
            AutoLabelingMode.ADD,
            AutoLabelingMode.REMOVE,
        ]
    ]
    flags = {}
    for i in range(widget.flag_widget.count()):
        item = widget.flag_widget.item(i)
        key = item.text()
        flag = item.checkState() == Qt.CheckState.Checked
        flags[key] = flag
    widget.other_data[CHECKED_FIELD] = widget._annotation_checked()
    try:
        image_path = osp.relpath(widget.image_path, osp.dirname(filename))
        image_data = (
            widget.image_data if widget._config["store_data"] else None
        )
        if osp.dirname(filename) and not osp.exists(osp.dirname(filename)):
            os.makedirs(osp.dirname(filename))

        # One copy of the pre-edit state per (session, file), taken here
        # because this is the only path that writes a label file: the canvas
        # undo stack does not survive a file switch, and the auto-save
        # overwrites the only other copy a few hundred milliseconds after an
        # edit. Failure is logged, never fatal -- refusing to save an
        # annotation would be worse than losing its snapshot.
        snapshot_before_label_write(filename)

        label_file.save(
            filename=filename,
            shapes=shapes,
            image_path=image_path,
            image_data=image_data,
            image_height=widget.image.height(),
            image_width=widget.image.width(),
            other_data=widget.other_data,
            flags=flags,
        )
        write_sidecar = getattr(widget, "_write_yolo_sidecar", None)
        if write_sidecar is not None:
            write_sidecar(filename, shapes)
        widget.label_file = label_file
        items = widget.file_list_widget.findItems(
            widget.image_path, Qt.MatchFlag.MatchExactly
        )
        if len(items) > 0:
            if len(items) != 1:
                raise RuntimeError("There are duplicate files.")
            filelist_items.set_file_item_annotated(
                widget, items[0], True, negative=not shapes
            )
            widget._set_file_item_checked(
                items[0], widget._annotation_checked()
            )
            file_list_ops._note_save_quality(widget, shapes, items[0])
        else:
            file_list_ops._note_save_quality(widget, shapes)
        # disable allows next and previous image to proceed
        # widget.filename = filename
        return True
    except LabelFileError as e:
        widget.error_message(
            QCoreApplication.translate(
                "LabelingWidget", "Error saving label data"
            ),
            QCoreApplication.translate("LabelingWidget", "<b>%s</b>") % e,
        )
        return False


def _apply_checked_batch(widget, start_index, info_list):
    """Delegates to filelist.controller (AsyncLabelChecker callback)."""
    # Built on demand: the controller is stateless, and light test
    # stubs never carry an instance.
    FileReviewController(widget).apply_checked_batch(start_index, info_list)


def _maybe_focus_low_confidence_shapes(widget):
    """Delegates to filelist.quality (called after a file load)."""
    widget.file_quality_controller.maybe_focus_low_confidence_shapes()


def _record_recent_dir(widget, directory):
    """把一个目录记入最近项目列表。

    旧实现只写 QSettings 的 ``recent_dirs``，与项目注册表各存一份，
    于是"打开最近文件夹"和"切换项目"两个入口经常对不上。现在统一
    走 :mod:`project_view`（内部写 registry），老键由读取路径负责迁移。
    """
    if not directory:
        return
    project_view.record_recent(widget, directory)


def _maybe_show_smart_tools_guide(widget, directory):
    if not directory:
        return
    thresholds = widget._load_active_thresholds()
    signature = (
        osp.abspath(directory),
        "calibrated" if thresholds else "default",
    )
    if getattr(widget, "_smart_tools_guide_signature", None) == signature:
        return
    widget._smart_tools_guide_signature = signature
    popup = Popup(
        widget._smart_tools_guide_message(),
        parent=widget,
        msec=4800,
        icon=new_icon_path("copy-green", "svg"),
    )
    popup.show_popup(widget, popup_height=72, position="bottom")
