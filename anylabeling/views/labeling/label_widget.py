import functools
import html
import json
import math
import os
import os.path as osp
import re
import shutil
import threading
import time
from typing import Optional

import cv2
import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QLineEdit,
    QCompleter,
)

from anylabeling.services.auto_labeling.types import AutoLabelingMode
from anylabeling.services.auto_labeling import _THUMBNAIL_RENDER_MODELS
from anylabeling.views.training import launcher as training_launcher

from ...app_info import (
    __appname__,
    __version__,
    __preferred_device__,
)
from . import utils
from .utils.async_label_check import (
    _label_file_review_state,
    label_file_review_info,
)
from .utils.theme import get_theme
from .utils.style import (
    get_cancel_btn_style,
    get_checkbox_indicator_style,
    get_dialog_style,
    get_dock_style,
    get_instruction_bar_style,
    get_ok_btn_style,
    get_panel_style,
    get_plain_text_edit_style,
    get_settings_button_style,
    get_toolbar_scroll_area_style,
    keycap_html,
)
from ...config import get_config, save_config
from .label_file import LabelFile, LabelFileError
from .provenance import (
    SOURCE_HUMAN,
    SOURCE_MODEL,
    get_source,
    is_deletable_stale_shape,
    model_display_name,
    model_of,
    model_version_of,
    resolve_model_path,
    stamp_model_shapes,
    weight_digest,
)
from .schema import (
    REVIEW_CONFIRMED,
    REVIEW_REJECTED,
    REVIEW_STATES,
    REVIEW_UNCHECKED,
)
from .logger import logger
from .utils.yolo_detect import (
    CLASSES_FILENAME,
    load_class_names,
    merge_class_names,
    rename_label_across_folder,
    write_yolo_detect_sidecar,
)
from .utils.active_learning import (
    load_thresholds,
    needs_review,
    shape_uncertainty,
    thresholds_for,
)
from .utils.quality import (
    format_save_quality_status,
    inspect_shape_quality,
    shapes_have_low_confidence,
)
from .utils.smart_tools import (
    run_backup_restore,
    run_duplicate_archive,
    run_missing_scan,
    run_review_jump,
    run_smart_analysis,
    run_stale_model_audit,
    run_template_propagation,
    run_threshold_calibration,
    run_training_advice,
    show_iteration_dashboard,
)
from .utils.shortcuts_help import (
    build_shortcut_rows,
    filter_shortcut_rows,
)
from .utils.recent_dirs import push_recent_dir
from .settings import SettingsController, SettingsDialog
from .settings.runtime_applier import SettingsRuntimeApplier
from .shortcuts.digit_controller import DigitShortcutController
from .filelist import items as filelist_items
from .filelist.controller import FileReviewController
# Re-exported: the rest of the widget and the async checkers read the
# row roles and label-JSON field names from this module's namespace.
from .filelist.roles import (  # noqa: F401
    CHECKED_FIELD,
    FILE_ANNOTATION_ROLE,
    FILE_LOW_CONF_ROLE,
    FILE_NEGATIVE_ROLE,
    FILE_REVIEW_ROLE,
    FILE_REVIEWED_AT_ROLE,
    REVIEW_STATE_FIELD,
    REVIEWED_AT_FIELD,
)
from .shape import Shape
from .utils.data_audit import run_data_audit
from .utils.file_search import (
    parse_search_pattern,
    matches_filename,
    matches_label_attribute,
)
from .utils.qt import new_icon_path
from .widgets import (
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
from anylabeling.views.common.toaster import QToaster

LABEL_COLORMAP = utils.label_colormap()
LABEL_OPACITY = 128
# Whole-image class suggestions from a classification model. Deliberately not
# shapes: a suggestion becomes an annotation only when a human confirms it.
PREDICTIONS_FIELD = "predictions"
FILE_CHECKED_COLOR = "#22A06B"
FILE_ANNOTATED_COLOR = "#3B82F6"
FILE_UNCHECKED_COLOR = "#8C98A4"
FILE_NEGATIVE_COLOR = "#F59E0B"
FILE_REJECTED_COLOR = "#D9534F"
FILE_SEARCH_COMPLETIONS = (
    "label::",
    "checked::0",
    "checked::1",
    "gid::",
    "type::rectangle",
    "difficult::1",
    "score::[0,0.5]",
    "score::[0.25,0.45]",
    "description::1",
    "#1",
)


def _measure_text_width(font_metrics, text):
    if hasattr(font_metrics, "horizontalAdvance"):
        return font_metrics.horizontalAdvance(text)
    return font_metrics.width(text)


def _format_label_list_text(label, group_id):
    text = html.escape("" if label is None else str(label))
    if group_id is None:
        return text
    return f"{text} ({group_id})"


def _set_label_list_item_lock(item, locked):
    item.set_locked(locked)


def _shape_editable_state(shape):
    """Fields edited by the label dialog, as one comparable tuple.

    Used to decide whether a label edit actually changed anything. Qt emits
    change signals even when the value is identical, and an unchanged edit
    must not consume an undo slot or invalidate the redo branch.
    """
    return (
        shape.label,
        shape.flags,
        shape.group_id,
        shape.description,
        shape.difficult,
        shape.kie_linking,
    )


def _apply_attribute_change(widget, shape_index, property_name, value):
    """Write one attribute value and record it in the undo history.

    Attribute edits used to be persisted straight to disk with no history
    entry, so a mis-click could not be undone. The value is compared first
    because Qt emits change signals even when nothing changed (the panel is
    repopulated on every selection change), and an unchanged write must not
    consume an undo slot or invalidate the redo branch.

    Returns True when the value actually changed.
    """
    if shape_index >= len(widget.canvas.shapes):
        return False
    shape = widget.canvas.shapes[shape_index]
    if not shape.attributes:
        shape.attributes = {}
    if shape.attributes.get(property_name) == value:
        return False
    shape.attributes[property_name] = value
    # Snapshot after the edit: see Canvas.is_shape_restorable for why.
    widget.canvas.store_shapes()
    widget.canvas.update()
    # Keep the history buttons in sync. set_dirty() is deliberately not used
    # here -- save_attributes() already persists the change, so going through
    # set_dirty() would write the file twice.
    widget.actions.undo.setEnabled(widget.canvas.is_shape_restorable)
    widget.actions.redo.setEnabled(widget.canvas.is_shape_redoable)
    return True


def _find_next_label_loop_shape(shapes, start_index, canvas_shapes):
    canvas_shape_ids = {id(shape) for shape in canvas_shapes}
    for index in range(start_index, len(shapes)):
        shape = shapes[index]
        if id(shape) in canvas_shape_ids:
            return index, shape
    return len(shapes), None


def fill_progress_template(template, annotated, total, checked):
    return (
        template.replace("%1", str(annotated))
        .replace("%2", str(total))
        .replace("%3", str(checked))
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


def _create_file_status_icon(color, filled=True):
    pixmap = QtGui.QPixmap(12, 12)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    if filled:
        painter.setBrush(QtGui.QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
    else:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QtGui.QPen(QtGui.QColor(color), 1.5))
    painter.drawEllipse(2, 2, 8, 8)
    painter.end()
    return QtGui.QIcon(pixmap)


class LabelingWidget(LabelDialog):
    """The main widget for labeling images"""

    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = 0, 1, 2
    next_files_changed = QtCore.pyqtSignal(list)

    def __init__(  # noqa: C901
        self,
        parent=None,
        config=None,
        filename=None,
        output=None,
        output_file=None,
        output_dir=None,
    ):
        self.parent = parent
        if output is not None:
            logger.warning(
                "argument output is deprecated, use output_file instead"
            )
            if output_file is None:
                output_file = output

        self.filename = None
        self.image_path = None
        self.image_data = None
        self.label_file = None
        self.other_data = {}
        self.classes_file = None
        self.attributes = {}
        self.attribute_widget_types = {}
        self.current_category = None
        self.selected_polygon_stack = []
        self.supported_shape = Shape.get_supported_shape()
        self.label_info = {}
        self.image_flags = []
        self.fn_to_index = {}
        self.cache_auto_label = None
        self.cache_auto_label_group_id = None

        # see configs/anylabeling_config.yaml for valid configuration
        if config is None:
            config = get_config()
        self._config = config
        # Debounce for the auto-save "✓ saved" feedback so rapid edits
        # (which each trigger an auto-save) do not spam the status bar.
        self._auto_save_feedback_timer = None
        self.label_flags = self._config["label_flags"]
        self.label_loop_count = -1
        self.label_loop_shapes = None
        self.label_loop_popup = None
        self.select_loop_count = -1
        self.digit_to_label = None
        self.drawing_digit_shortcuts = self._config.get("digit_shortcuts", {})
        self.digit_shortcut_controller = DigitShortcutController(self)
        self._runtime_shape_color_shift = int(
            self._config.get("shift_auto_shape_color", 0)
        )
        self._settings_controller = None
        self._settings_dialog = None
        self._settings_runtime_applier = SettingsRuntimeApplier(self)
        self._auto_switch_signal_connected = False

        # set default shape colors
        Shape.line_color = QtGui.QColor(*self._config["shape"]["line_color"])
        Shape.fill_color = QtGui.QColor(*self._config["shape"]["fill_color"])
        Shape.select_line_color = QtGui.QColor(
            *self._config["shape"]["select_line_color"]
        )
        Shape.select_fill_color = QtGui.QColor(
            *self._config["shape"]["select_fill_color"]
        )
        Shape.vertex_fill_color = QtGui.QColor(
            *self._config["shape"]["vertex_fill_color"]
        )
        Shape.hvertex_fill_color = QtGui.QColor(
            *self._config["shape"]["hvertex_fill_color"]
        )

        # Set point size from config file
        Shape.point_size = self._config["shape"]["point_size"]
        # Set line width from config file
        Shape.line_width = self._config["shape"]["line_width"]

        super(LabelDialog, self).__init__()

        # Whether we need to save or not.
        self.dirty = False

        self._no_selection_slot = False
        self._copied_shapes = None
        self._copied_group_id = None
        self._batch_edit_warning_shown = False
        self._batch_processing_active = False

        self.brightness_contrast_dialog = BrightnessContrastDialog(
            self.on_new_brightness_contrast, parent=self
        )

        # Main widgets and related state.
        self.label_dialog = LabelDialog(
            parent=self,
            labels=self._config["labels"],
            sort_labels=self._config["sort_labels"],
            show_text_field=self._config["show_label_text_field"],
            completion=self._config["label_completion"],
            fit_to_content=self._config["fit_to_content"],
            flags=self.label_flags,
        )

        self.label_list = LabelListWidget()
        self.label_list.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.last_open_dir = None

        self.flag_dock = self.flag_widget = None
        self.flag_dock = QtWidgets.QDockWidget(self.tr("Flags"), self)
        self.flag_dock.setObjectName("Flags")
        self.flag_widget = QtWidgets.QListWidget()
        if config["flags"]:
            self.image_flags = config["flags"]
            self.load_flags({k: False for k in self.image_flags})
        else:
            self.flag_dock.hide()
        self.flag_dock.setWidget(self.flag_widget)
        self.flag_widget.itemChanged.connect(self.set_dirty)
        self.flag_dock.setStyleSheet(get_dock_style())

        self.label_filter_combobox = LabelFilterComboBox(self)
        self.gid_filter_combobox = GroupIDFilterComboBox(self)
        self.label_filter_combobox.hide()
        self.gid_filter_combobox.hide()
        self.select_toggle_action = None

        self.label_list.item_selection_changed.connect(
            self.label_selection_changed
        )
        self.label_list.item_double_clicked.connect(self.edit_label)
        self.label_list.items_lock_requested.connect(
            self.toggle_label_items_lock
        )
        self.label_list.item_changed.connect(self.label_item_changed)
        self.label_list.item_dropped.connect(self.label_order_changed)
        self.shape_dock = QtWidgets.QDockWidget(self.tr("Objects"), self)
        self.shape_dock.setWidget(self.label_list)
        self.shape_dock.setStyleSheet(get_dock_style())

        self.unique_label_list = UniqueLabelQListWidget()
        self.unique_label_list.setToolTip(
            self.tr(
                "单击选择类别后开始画框。双击或右键可重命名。"
                "Esc 取消选择。"
            )
        )
        self.unique_label_list.itemDoubleClicked.connect(
            self.rename_unique_label
        )
        self.unique_label_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.unique_label_list.customContextMenuRequested.connect(
            self._unique_label_context_menu
        )
        self.label_search = SearchBar(
            placeholder_text=self.tr("搜索标签...")
        )
        self.label_search.setToolTip(
            self.tr(
                "按名称过滤下方类别列表；不匹配的类别只是隐藏，"
                "已画的框不受影响"
            )
        )
        self.label_search.setClearButtonEnabled(True)
        self.label_search.textChanged.connect(self._refresh_label_panel)
        self.load_labels(self._config["labels"])
        label_panel = QtWidgets.QWidget()
        label_panel_layout = QVBoxLayout(label_panel)
        label_panel_layout.setContentsMargins(0, 0, 0, 0)
        label_panel_layout.setSpacing(4)
        label_panel_layout.addWidget(self.label_search)
        label_panel_layout.addWidget(self.unique_label_list)
        self.label_dock = QtWidgets.QDockWidget(self.tr("Labels"), self)
        self.label_dock.setObjectName("Labels")
        self.label_dock.setWidget(label_panel)
        self.label_dock.setStyleSheet(get_dock_style())
        self.unique_label_list.setStyleSheet(
            "QListWidget::item { padding: 0; }"
        )

        self.file_search = SearchBar()
        self.file_search.setPlaceholderText(
            self.tr("搜索文件、#序号、label::类别")
        )
        self.file_search.setToolTip(
            self.tr(
                "搜索方式：\n"
                "- 文本：文件名包含即可\n"
                "- 序号：#N（如 #1、#10）\n"
                "- 正则：<pattern>（如 <\\.png$>）\n"
                "- 属性：difficult::1、gid::0、shape::1、label::xxx、type::xxx\n"
                "- 分数：score::[0,0.5]、score::[0.25,0.45]\n"
                "- 描述：description::1\n"
                "- 检查：checked::1、checked::0\n"
                "输入时会提示常用前缀，按 Enter 执行搜索。"
            )
        )
        file_search_completer = QCompleter(FILE_SEARCH_COMPLETIONS, self)
        file_search_completer.setCaseSensitivity(
            Qt.CaseSensitivity.CaseInsensitive
        )
        file_search_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        file_search_completer.setCompletionMode(
            QCompleter.CompletionMode.PopupCompletion
        )
        self.file_search.setCompleter(file_search_completer)
        self.file_search.returnPressed.connect(self.file_search_changed)
        self.file_search.returnPressed.connect(self.file_search.setFocus)
        self.settings_button = QPushButton(self)
        self.settings_button.setFixedSize(32, 32)
        self.settings_button.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
        )
        self.settings_button.setToolTip(self.tr("Settings"))
        self.settings_button.setIcon(utils.new_icon("settings", "svg"))
        self.settings_button.setIconSize(QtCore.QSize(28, 28))
        self.settings_button.setStyleSheet(get_settings_button_style())
        self.settings_button.clicked.connect(self.open_settings_dialog)
        self.file_filter_combo = QComboBox()
        self.file_filter_combo.addItem(self.tr("全部"), "all")
        self.file_filter_combo.addItem(self.tr("未标注"), "unannotated")
        self.file_filter_combo.addItem(self.tr("已标注"), "annotated")
        self.file_filter_combo.addItem(self.tr("已检查"), "checked")
        self.file_filter_combo.addItem(self.tr("需返工"), "rework")
        self.file_filter_combo.addItem(self.tr("待复核"), "low_conf")
        self.file_filter_combo.setItemData(
            self.file_filter_combo.count() - 1,
            self.tr("含有未达自动接受阈值目标的图片；阈值可由「阈值校准」生成"),
            Qt.ItemDataRole.ToolTipRole,
        )
        self.file_filter_combo.currentIndexChanged.connect(
            self._apply_file_filter
        )
        self.file_filter_combo.setStyleSheet(get_plain_text_edit_style())
        self.file_progress_label = QLabel("")
        self.file_progress_label.setWordWrap(True)
        self.file_progress_label.setStyleSheet(
            "color: %s; padding: 2px 4px;" % get_theme()["text_secondary"]
        )
        self.file_list_widget = QtWidgets.QListWidget()
        self.file_list_widget.setObjectName("FileList")
        self.file_list_widget.setIconSize(QtCore.QSize(12, 12))
        self.file_status_icons = {
            "checked": _create_file_status_icon(FILE_CHECKED_COLOR, True),
            "annotated": _create_file_status_icon(FILE_ANNOTATED_COLOR, True),
            "negative": _create_file_status_icon(FILE_NEGATIVE_COLOR, True),
            "rejected": _create_file_status_icon(FILE_REJECTED_COLOR, True),
            "unannotated": _create_file_status_icon(
                FILE_UNCHECKED_COLOR, False
            ),
        }
        self.file_list_widget.itemSelectionChanged.connect(
            self.file_selection_changed
        )
        self.file_list_widget.itemChanged.connect(self._on_file_item_changed)
        self.file_list_widget.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.file_list_widget.customContextMenuRequested.connect(
            self.pop_file_list_menu
        )
        file_list_layout = QtWidgets.QVBoxLayout()
        file_list_layout.setContentsMargins(0, 0, 0, 0)
        file_list_layout.setSpacing(2)
        file_list_layout.addWidget(self.file_filter_combo)
        file_list_layout.addWidget(self.file_progress_label)
        file_list_layout.addWidget(self.file_list_widget)
        self.file_dock = QtWidgets.QDockWidget("", self)
        self.file_dock.setObjectName("Files")
        self.file_dock.setTitleBarWidget(QtWidgets.QWidget(self))
        file_list_widget = QtWidgets.QWidget()
        file_list_widget.setLayout(file_list_layout)
        self.file_dock.setWidget(file_list_widget)
        self.file_dock.setStyleSheet(get_dock_style())

        self.zoom_widget = ZoomWidget()

        self.navigator_dialog = NavigatorDialog(self)
        self.navigator_dialog.navigator.navigation_requested.connect(
            self.on_navigator_request
        )
        self.navigator_dialog.closeEvent = self._navigator_close_event
        self.navigator_dialog.zoom_changed[int].connect(
            lambda zoom: self.on_navigator_zoom_changed(zoom, None)
        )
        self.navigator_dialog.zoom_changed[int, QtCore.QPoint].connect(
            self.on_navigator_zoom_changed
        )
        self.navigator_dialog.viewport_update_requested.connect(
            self.on_navigator_viewport_update_requested
        )
        self.async_exif_scanner = utils.AsyncExifScanner(self)
        self.async_exif_scanner.exif_detected.connect(self.on_exif_detected)
        # Background label-"checked" refresher: opening a large folder used
        # to block the UI for seconds while every row read its label JSON.
        self.async_label_checker = utils.AsyncLabelChecker(self)

        self.setAcceptDrops(True)

        self.canvas = self.label_list.canvas = Canvas(
            parent=self,
            epsilon=self._config["canvas"]["epsilon"],
            double_click=self._config["canvas"]["double_click"],
            num_backups=self._config["canvas"]["num_backups"],
            wheel_rectangle_editing=self._config["canvas"][
                "wheel_rectangle_editing"
            ],
            auto_highlight_shape=self._config.get(
                "auto_highlight_shape", False
            ),
            attributes=self._config["canvas"].get("attributes", {}),
            rotation=self._config["canvas"].get("rotation", {}),
            mask=self._config["canvas"].get("mask", {}),
            brush=self._config["canvas"].get("brush", {}),
            cuboid=self._config["canvas"].get("cuboid", {}),
            double_click_edit_label=self._config["canvas"].get(
                "double_click_edit_label", True
            ),
        )
        self.canvas.zoom_request.connect(self.zoom_request)

        scroll_area = QScrollArea()
        scroll_area.setWidget(self.canvas)
        scroll_area.setWidgetResizable(True)
        self._canvas_scroll_area = scroll_area

        # Adjustment panel docked at the bottom-left of the canvas viewport.
        self.canvas_adjustment = CanvasAdjustmentWidget(scroll_area.viewport())
        self.canvas_adjustment.opacity_changed.connect(
            self._on_shape_opacity_changed
        )
        self.canvas_adjustment.brightness_contrast_changed.connect(
            self._on_inline_brightness_contrast
        )
        self.canvas_adjustment.geometry_changed.connect(
            self._position_canvas_adjustment
        )
        # Hidden until an image is loaded (shown at the end of load_file).
        self.canvas_adjustment.hide()
        self.empty_canvas_state = CanvasEmptyStateWidget(
            scroll_area.viewport()
        )
        self.empty_canvas_state.open_folder_requested.connect(
            self.open_folder_dialog
        )
        self.empty_canvas_state.show()
        self.empty_canvas_state.raise_()
        scroll_area.viewport().installEventFilter(self)

        self.scroll_bars = {
            Qt.Orientation.Vertical: scroll_area.verticalScrollBar(),
            Qt.Orientation.Horizontal: scroll_area.horizontalScrollBar(),
        }
        self.scroll_bars[Qt.Orientation.Vertical].valueChanged.connect(
            lambda: self.update_navigator_viewport()
        )
        self.scroll_bars[Qt.Orientation.Horizontal].valueChanged.connect(
            lambda: self.update_navigator_viewport()
        )
        self.scroll_bars[Qt.Orientation.Vertical].rangeChanged.connect(
            lambda *_: self.update_labeling_instruction()
        )
        self.scroll_bars[Qt.Orientation.Horizontal].rangeChanged.connect(
            lambda *_: self.update_labeling_instruction()
        )
        self.canvas.scroll_request.connect(self.scroll_request)
        self.canvas.new_shape.connect(self.new_shape)
        self.canvas.show_shape.connect(self.show_shape)
        self.canvas.shape_moved.connect(self.set_dirty)
        self.canvas.shape_rotated.connect(self.set_dirty)
        self.canvas.shapes_deleted.connect(self.on_canvas_shapes_deleted)
        # 框数变化时同步刷新状态栏上下文（新建/删除即时生效）
        self.canvas.new_shape.connect(self._refresh_status_context)
        self.canvas.shapes_deleted.connect(self._refresh_status_context)
        self.canvas.selection_changed.connect(self.shape_selection_changed)
        self.canvas.drawing_polygon.connect(self.toggle_drawing_sensitive)
        self.canvas.edit_label_requested.connect(self.edit_label)
        # Keep the brush-edit toggle in sync when the canvas exits brush
        # mode on its own (e.g. via a right-click).
        self.canvas.mode_changed.connect(self.update_labeling_instruction)
        self.canvas.brush_mode_changed.connect(self.on_brush_mode_changed)
        self.canvas.brush_history_changed.connect(
            lambda can_undo: self.actions.undo.setEnabled(can_undo)
        )
        # [Feature] support for automatically switching to editing mode
        # when the cursor moves over an object
        self.canvas.h_shape_is_hovered = self._config.get(
            "auto_highlight_shape", False
        )
        self._settings_runtime_applier.set_auto_switch_to_edit_mode(
            self._config["auto_switch_to_edit_mode"]
        )

        # Crosshair
        self.crosshair_settings = self._config["canvas"]["crosshair"]
        self.canvas.set_cross_line(**self.crosshair_settings)

        self._central_widget = scroll_area

        features = QtWidgets.QDockWidget.DockWidgetFeature(0)
        for dock in [
            "flag_dock",
            "label_dock",
            "shape_dock",
            "file_dock",
        ]:
            if self._config[dock]["closable"]:
                features = (
                    features
                    | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable
                )
            if self._config[dock]["floatable"]:
                features = (
                    features
                    | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable
                )
            if self._config[dock]["movable"]:
                features = (
                    features
                    | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable
                )
            getattr(self, dock).setFeatures(features)
            if self._config[dock]["show"] is False:
                getattr(self, dock).setVisible(False)

        # Actions
        _build_actions(self)

        if output_file is not None and self._config["auto_save"]:
            logger.warning(
                "If `auto_save` argument is True, `output_file` argument "
                "is ignored and output filename is automatically "
                "set as IMAGE_BASENAME.json."
            )
        self.output_file = output_file
        self.output_dir = output_dir

        # Application state.
        self.image = QtGui.QImage()
        self.image_path = None
        self.recent_files = []
        self.max_recent = 7
        self.other_data = {}
        self.zoom_level = 100
        self.fit_window = False
        self.zoom_values = {}  # key=filename, value=(zoom_mode, zoom_value)
        self.brightness_contrast_values = {}
        self.scroll_values = {
            Qt.Orientation.Horizontal: {},
            Qt.Orientation.Vertical: {},
        }  # key=filename, value=scroll_value

        # XXX: Could be completely declarative.
        # Restore application settings. This happens before any folder is
        # imported, because opening a folder records it as a recent directory
        # through self.settings.
        self.settings = QtCore.QSettings("anylabeling", "anylabeling")
        self.recent_files = self.settings.value("recent_files", []) or []
        self.last_open_dir = self.settings.value("last_open_dir", None) or None

        if filename is not None and osp.isdir(filename):
            self.import_image_folder(filename, load=False)
        else:
            self.filename = filename

        if config["file_search"]:
            self.file_search.setText(config["file_search"])
            self.file_search_changed()

        # Populate the File menu dynamically.
        self.update_file_menu()

        # Since loading the file may take some time,
        # make sure it runs in the background.
        if self.filename is not None:
            self.queue_event(functools.partial(self.load_file, self.filename))

        # Callbacks:
        self.zoom_widget.valueChanged.connect(self.paint_canvas)
        self.zoom_widget.valueChanged.connect(self._refresh_status_context)

        self.populate_mode_actions()
        self._settings_controller = SettingsController(
            config=self._config,
            apply_callback=self._settings_runtime_applier.apply_change,
            parent=self,
            defer_runtime_apply=True,
        )
        self._settings_runtime_applier.build_shortcut_action_map()

        QtCore.QTimer.singleShot(100, self.restore_navigator_state)
        QtCore.QTimer.singleShot(250, self._refresh_label_panel)
        QtCore.QTimer.singleShot(0, self._install_save_status_widget)
        QtCore.QTimer.singleShot(0, self._sync_empty_canvas_state)

    def session_resume_path(self):
        """Return the last working directory, or None when unavailable."""
        try:
            directory = self.settings.value("last_open_dir", None)
            if directory and osp.isdir(str(directory)):
                return str(directory)
        except Exception as e:  # noqa
            logger.warning(f"session_resume_path failed: {e}")
        return None

    def continue_last_session(self):
        """Reload the previous folder and jump to the last viewed image."""
        directory = self.session_resume_path()
        if not directory:
            return
        try:
            self.import_image_folder(directory, load=False)
            last_filename = self.settings.value("filename", "") or ""
            if last_filename and osp.isfile(str(last_filename)):
                self.load_file(str(last_filename))
            else:
                self.open_next_image(load=True)
            self._refresh_file_panel()
        except Exception as e:  # noqa
            logger.warning(f"Session resume failed: {e}")
            self.status(self.tr("恢复上次工作现场失败"), 4000)

    def restore_navigator_state(self) -> None:
        try:
            navigator_visible: bool = self.settings.value(
                "navigator/visible", False, type=bool
            )

            if navigator_visible:
                self.navigator_dialog.show()

                if hasattr(self, "image") and not self.image.isNull():
                    self.navigator_dialog.set_image(
                        QtGui.QPixmap.fromImage(self.image)
                    )
                    self.update_navigator_viewport()
                else:
                    self._should_restore_navigator = True

                # Restore geometry information
                geometry = self.settings.value("navigator/geometry")
                if geometry:
                    self.navigator_dialog.restoreGeometry(geometry)
                else:
                    # Fallback: restore position and size separately
                    saved_size = self.settings.value("navigator/size")
                    saved_position = self.settings.value("navigator/position")

                    if saved_size:
                        self.navigator_dialog.resize(saved_size)
                    if saved_position:
                        self.navigator_dialog.move(saved_position)

                if hasattr(self, "actions") and hasattr(
                    self.actions, "show_navigator"
                ):
                    self.actions.show_navigator.setChecked(True)

        except Exception as e:
            print(f"Error restoring navigator state: {e}")

    def _navigator_close_event(self, event: QtGui.QCloseEvent) -> None:
        if hasattr(self, "actions") and hasattr(
            self.actions, "show_navigator"
        ):
            self.actions.show_navigator.setChecked(False)

        self.settings.setValue("navigator/visible", False)

        NavigatorDialog.closeEvent(self.navigator_dialog, event)

    def _on_theme_changed(self, mode: str) -> None:
        """Handle Theme menu selection (System / Light / Dark)."""
        prev_mode = self._config.get("theme", "auto")
        if prev_mode == mode:
            return

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(self.tr("Theme"))
        dialog.setFixedWidth(360)
        dialog.setWindowFlags(
            dialog.windowFlags()
            & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint
        )
        dialog.setStyleSheet(get_dialog_style())

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        label = QLabel(
            self.tr(
                "The new theme will take effect after restarting the application. Apply this setting now?"
            )
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(8)
        cancel_btn = QtWidgets.QPushButton(self.tr("Cancel"))
        cancel_btn.setFixedWidth(100)
        cancel_btn.setStyleSheet(get_cancel_btn_style())
        cancel_btn.clicked.connect(dialog.reject)
        ok_btn = QtWidgets.QPushButton(self.tr("OK"))
        ok_btn.setFixedWidth(100)
        ok_btn.setStyleSheet(get_ok_btn_style())
        ok_btn.clicked.connect(dialog.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._config["theme"] = mode
            save_config(self._config)
            popup = Popup(
                text=self.tr(
                    "Please restart the application to apply changes."
                ),
                parent=self,
            )
            popup.show_popup(self, position="center")
        else:
            # Revert the checkmark to the previously active mode
            prev_act = self._theme_actions.get(prev_mode)
            if prev_act:
                prev_act.setChecked(True)

    def get_labeling_instruction(self):
        shortcuts = self._config.get("shortcuts", {})
        prev_sc = keycap_html(
            self._format_instruction_shortcut(shortcuts.get("open_prev"))
        )
        next_sc = keycap_html(
            self._format_instruction_shortcut(shortcuts.get("open_next"))
        )
        rect_sc = keycap_html(
            self._format_instruction_shortcut(
                shortcuts.get("create_rectangle")
            )
        )
        save_sc = keycap_html(
            self._format_instruction_shortcut(shortcuts.get("save"))
        )
        auto_visible = (
            hasattr(self, "auto_labeling_widget")
            and self.auto_labeling_widget.isVisible()
        )
        if not getattr(self, "filename", None):
            open_dir_sc = keycap_html(
                self._format_instruction_shortcut(shortcuts.get("open_dir"))
            )
            return (
                self.tr("尚未打开图片：%1 打开文件夹，%2/%3 切图，%4 画框。")
                .replace("%1", open_dir_sc)
                .replace("%2", prev_sc)
                .replace("%3", next_sc)
                .replace("%4", rect_sc)
            )
        if auto_visible:
            return self.tr(
                "自动标注：点选或框选提示 → 生成结果 → 人工改框 · "
                "%1/%2 切图"
            ).replace("%1", prev_sc).replace("%2", next_sc)
        if getattr(self.canvas, "is_brush_mode", False):
            return self.tr("画笔编辑：涂抹修改轮廓 · 右键退出")
        if self.canvas.drawing():
            create_mode = self.canvas.create_mode
            in_progress = self.canvas.current is not None
            names = {
                "rectangle": self.tr("矩形"),
                "polygon": self.tr("多边形"),
                "point": self.tr("点"),
                "rotation": self.tr("旋转框"),
                "quadrilateral": self.tr("四边形"),
                "circle": self.tr("圆"),
                "line": self.tr("线"),
                "cuboid": self.tr("立方体"),
            }
            shape_name = names.get(create_mode, create_mode)
            if in_progress:
                if create_mode == "polygon":
                    return self.tr(
                        "单击加点 · Ctrl+Enter 完成保存 · Esc 取消 · 空格拖动画布"
                    )
                if create_mode == "rectangle":
                    return self.tr(
                        "拖拽画框 · Ctrl+Enter 完成保存 · Esc 取消 · 空格拖动画布"
                    )
                return self.tr(
                    "继续绘制%1 · Ctrl+Enter 完成保存 · Esc 取消"
                ).replace("%1", shape_name)
            return self.tr("单击开始画%1 · Esc 返回编辑").replace(
                "%1", shape_name
            )
        return (
            f"{prev_sc}/{next_sc} {self.tr('切图（自动保存）')} · "
            f"{rect_sc} {self.tr('画框')} · "
            f"{save_sc} {self.tr('立即保存')}"
        )

    def _install_save_status_widget(self):
        if getattr(self, "_save_state_label", None) is not None:
            return
        try:
            bar = self.statusBar()
        except Exception:
            return
        if bar is None:
            return
        # 左侧上下文：当前图片的标注框数与缩放比例
        self._status_context_label = QLabel("")
        self._status_context_label.setObjectName("StatusContextLabel")
        self._status_context_label.setStyleSheet("padding: 0 10px;")
        bar.addWidget(self._status_context_label)
        # 右侧保存状态
        self._save_state_label = QLabel(self.tr("就绪"))
        self._save_state_label.setObjectName("SaveStateLabel")
        self._save_state_label.setStyleSheet("padding: 0 10px;")
        bar.addPermanentWidget(self._save_state_label)
        self._update_save_state_label()
        self._refresh_status_context()

    def _refresh_status_context(self):
        """刷新状态栏左侧的上下文信息（框数 + 缩放）。"""
        label = getattr(self, "_status_context_label", None)
        if label is None:
            return
        if not self.filename:
            label.setText("")
            return
        shape_count = (
            len(self.canvas.shapes)
            if hasattr(self.canvas, "shapes")
            else 0
        )
        zoom = self.zoom_widget.value()
        size_text = ""
        image = getattr(self, "image", None)
        if image is not None and not image.isNull():
            size_text = (
                self.tr(" · %1x%2")
                .replace("%1", str(image.width()))
                .replace("%2", str(image.height()))
            )
        label.setText(
            (self.tr("标注 %1 框 · 缩放 %2%") + size_text)
            .replace("%1", str(shape_count))
            .replace("%2", str(zoom))
        )

    def _update_save_state_label(self):
        label = getattr(self, "_save_state_label", None)
        if label is None:
            return
        t = get_theme()
        if not self.filename:
            state, color = self.tr("就绪"), t["text_secondary"]
            hint = self.tr("打开图片文件夹后即可开始标注")
        elif self.dirty:
            state, color = self.tr("未保存"), t["warning"]
            hint = self.tr("当前图片有未写入的改动")
            hint += (
                self.tr("（自动保存已开启，稍候即写入）")
                if self._config.get("auto_save")
                else self.tr("，按 Ctrl+S 保存")
            )
        else:
            state, color = self.tr("已保存"), t["success"]
            hint = self.tr("当前图片的改动已写入标签 JSON")
        label.setText(state)
        label.setToolTip(hint)
        label.setStyleSheet(f"padding: 0 10px; color: {color};")

    def _sync_empty_canvas_state(self):
        overlay = getattr(self, "empty_canvas_state", None)
        if overlay is None:
            return
        pixmap = getattr(self.canvas, "pixmap", None)
        empty = pixmap is None or pixmap.isNull() or pixmap.width() == 0
        overlay.setVisible(empty)
        if empty:
            overlay.raise_()
            self._position_empty_canvas_state()

    def _position_empty_canvas_state(self):
        overlay = getattr(self, "empty_canvas_state", None)
        if overlay is None or not hasattr(self, "_canvas_scroll_area"):
            return
        viewport = self._canvas_scroll_area.viewport()
        overlay.setGeometry(viewport.rect())
        overlay.raise_()

    def _should_show_space_pan_tip(self):
        if not self.canvas.drawing() or self.canvas.current is None:
            return False
        return any(
            scroll_bar.maximum() > 0
            for scroll_bar in self.scroll_bars.values()
        )

    def _space_pan_tip_message(self):
        return self.tr(
            "Tip: Hold Space and drag with the left mouse button to pan the canvas temporarily."
        )

    def update_space_pan_tip(self):
        message = self._space_pan_tip_message()
        status_bar = self.statusBar()
        if self._should_show_space_pan_tip():
            status_bar.showMessage(message)
        elif status_bar.currentMessage() == message:
            status_bar.clearMessage()

    def update_labeling_instruction(self):
        if not hasattr(self, "label_instruction"):
            return
        self.label_instruction.setText(self.get_labeling_instruction())
        self.update_space_pan_tip()

    def _format_instruction_shortcut(self, value):
        text = self._settings_runtime_applier.shortcut_value_to_text(
            value
        ).strip()
        if not text:
            return "<b>-</b>"
        sequences = [
            chunk.strip() for chunk in text.split(",") if chunk.strip()
        ]
        if not sequences:
            return "<b>-</b>"
        formatted = []
        for sequence in sequences:
            keys = [
                part.strip() for part in sequence.split("+") if part.strip()
            ]
            if not keys:
                continue
            formatted.append(
                "+".join(f"<b>{html.escape(key)}</b>" for key in keys)
            )
        if not formatted:
            return "<b>-</b>"
        return ", ".join(formatted)

    @pyqtSlot()
    def on_auto_segmentation_requested(self):
        self.canvas.set_auto_labeling(True)
        self.update_labeling_instruction()

    @pyqtSlot()
    def on_auto_segmentation_disabled(self):
        self.canvas.set_auto_labeling(False)
        self.update_labeling_instruction()

    @pyqtSlot(list)
    def on_exif_detected(self, exif_files):
        if utils.ExifProcessingDialog.show_detection_dialog(
            self, len(exif_files)
        ):
            logger.info("Start processing EXIF orientation")
            utils.ExifProcessingDialog.process_exif_files_with_progress(
                self, exif_files
            )

    @pyqtSlot(list)
    def on_auto_decode_requested(self, marks):
        """Handle auto decode request"""
        self.auto_labeling_widget.model_manager.set_auto_labeling_marks(marks)
        self.auto_labeling_widget.run_prediction()

    def menu(self, title, actions=None):
        menu = self.parent.parent.menuBar().addMenu(title)
        if actions:
            utils.add_actions(menu, actions)
        return menu

    def central_widget(self):
        return self._central_widget

    def toolbar(self, title, actions=None):
        toolbar = ToolBar(title)
        toolbar.setObjectName(f"{title}ToolBar")
        toolbar.setOrientation(Qt.Orientation.Vertical)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        toolbar.setIconSize(QtCore.QSize(15, 15))
        toolbar.setFixedWidth(38)
        toolbar.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.MinimumExpanding,
        )
        if actions:
            utils.add_actions(toolbar, actions)
            toolbar.setMinimumHeight(toolbar.sizeHint().height())
        return toolbar

    def toolbar_scroll_area(self, toolbar):
        scroll_area = QScrollArea()
        scroll_area.setObjectName(f"{toolbar.objectName()}ScrollArea")
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        scroll_area.setStyleSheet(get_toolbar_scroll_area_style())
        scroll_area.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        scroll_area.setFixedWidth(toolbar.maximumWidth() + 4)
        scroll_area.setWidget(toolbar)
        return scroll_area

    def _restore_tools_panel_state(self):
        """Restore the floating toolbar's position/collapsed state.

        Runs once after the layout is ready: first snap to the default
        corner, then apply whatever the user saved in the config so a
        dragged/repositioned panel survives restarts.
        """
        self._sync_tools_panel(reset=True)
        panel = getattr(self, "tools_panel", None)
        if panel is None:
            return
        saved = self._config.get("tools_panel")
        if not isinstance(saved, dict):
            return
        pos = saved.get("position")
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            try:
                panel.set_saved_position(int(pos[0]), int(pos[1]))
            except (TypeError, ValueError):
                logger.debug("Ignoring invalid tools_panel position: %r", pos)
        if saved.get("collapsed"):
            panel.set_collapsed(True)

    def _on_tools_panel_position_committed(self, x, y):
        panel_state = self._config.setdefault("tools_panel", {})
        panel_state["position"] = [int(x), int(y)]
        save_config(self._config)

    def _on_tools_panel_collapse_toggled(self, collapsed):
        panel_state = self._config.setdefault("tools_panel", {})
        panel_state["collapsed"] = bool(collapsed)
        save_config(self._config)

    def _sync_tools_panel(self, reset=False):
        panel = getattr(self, "tools_panel", None)
        scroll_area = getattr(self, "_central_widget", None)
        if panel is None or scroll_area is None:
            return
        viewport = scroll_area.viewport()
        if panel.parentWidget() is not viewport:
            panel.setParent(viewport)
            panel.show()
        if reset:
            panel.reset_position()
        panel.sync_to_parent()

    def statusBar(self):
        return self.parent.parent.statusBar()

    def no_shape(self):
        return len(self.label_list) == 0

    def populate_mode_actions(self):
        tool = self.actions.tool
        menu = self.actions.menu
        self.tools.clear()
        utils.add_actions(self.tools, tool)
        self.tools.setMinimumHeight(self.tools.sizeHint().height())
        self._sync_tools_panel()

        self.canvas.menus[0].clear()
        utils.add_actions(self.canvas.menus[0], menu)
        (
            self.canvas_label_filter_menu_0,
            self.canvas_gid_filter_menu_0,
        ) = self._append_filter_submenus(
            self.canvas.menus[0],
            prepend=True,
            after_filter_actions=(self.actions.toggle_annotation_checked,),
        )
        self.menus.edit.clear()
        actions = (
            self.actions.create_mode,
            self.actions.create_brush_polygon_mode,
            self.actions.create_rectangle_mode,
            self.actions.create_point_mode,
            self.actions.create_rotation_mode,
            self.actions.create_quadrilateral_mode,
            self.actions.create_circle_mode,
            self.actions.create_line_mode,
            self.actions.create_linestrip_mode,
            self.actions.create_cuboid_mode,
            None,
            self.actions.edit_mode,
            self.actions.edit_brush_mode,
        )
        utils.add_actions(self.menus.edit, actions + self.actions.editMenu)

    def set_dirty(self):
        # Even if we autosave the file, we keep the ability to undo
        self.actions.undo.setEnabled(self.canvas.is_shape_restorable)

        if self._config["auto_save"]:
            label_file = osp.splitext(self.image_path)[0] + ".json"
            if self.output_dir:
                label_file_without_path = osp.basename(label_file)
                label_file = self.output_dir + "/" + label_file_without_path
            ok = self.save_labels(label_file)
            if ok:
                # Feedback is debounced: rapid edits each trigger an
                # auto-save, so only surface "✓ saved" once the user pauses.
                self._schedule_auto_save_feedback()
                self._update_save_state_label()
            else:
                # save_labels already popped an error dialog for the cause;
                # also tint the status bar red so the failure is unmissable.
                self._show_save_feedback(False)
            if (
                hasattr(self, "navigator_dialog")
                and self.navigator_dialog.isVisible()
            ):
                self.update_navigator_shapes()
            return
        self.dirty = True
        self.actions.save.setEnabled(True)
        if (
            hasattr(self, "navigator_dialog")
            and self.navigator_dialog.isVisible()
        ):
            self.update_navigator_shapes()
        self.update_progress_title()
        self._update_save_state_label()
        self._refresh_status_context()

    def _schedule_auto_save_feedback(self):
        """Debounce the auto-save success indicator (fires on pause)."""
        if self._auto_save_feedback_timer is None:
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._show_auto_save_feedback)
            self._auto_save_feedback_timer = timer
        self._auto_save_feedback_timer.start(800)

    def _show_auto_save_feedback(self):
        message = self.tr("✓ 已保存（自动）")
        quality = getattr(self, "_last_quality_status", "") or ""
        timeout = 1500
        if quality:
            message = f"{message}  {quality}"
            timeout = 5000
        self.status(message, timeout)

    def _window_title(self):
        title = f"{__appname__} v{__version__}"
        if self.filename is not None:
            current_index, total_count = self.get_image_progress_info()
            basename = osp.basename(str(self.filename))
            dirty_marker = "*" if self.dirty else ""
            image_size = ""
            if hasattr(self, "image") and not self.image.isNull():
                image_size = f" [{self.image.width()}x{self.image.height()}]"
            title = (
                f"{title} - {basename}{dirty_marker}{image_size} "
                f"[{current_index}/{total_count}]"
            )
        return title

    def update_progress_title(self):
        self.parent.parent.setWindowTitle(self._window_title())

    def set_clean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.union_selection.setEnabled(False)
        self._enable_create_mode_actions()

        self.update_progress_title()
        self._update_save_state_label()
        self._refresh_status_context()
        # Both load and save end here, so the open row's hover text stays
        # truthful about shape counts and the review timestamp.
        self._update_current_file_tooltip()

        if self.has_label_file():
            self.actions.delete_file.setEnabled(True)
        else:
            self.actions.delete_file.setEnabled(False)

    def get_image_progress_info(self):
        if self.filename and self.filename in self.fn_to_index:
            current_index = self.fn_to_index[str(self.filename)]
            total_count = self.file_list_widget.count()
            return current_index + 1, total_count
        return 1, 1

    def toggle_actions(self, value=True):
        """Enable/Disable widgets which depend on an opened image."""
        for action in self.actions.zoom_actions:
            action.setEnabled(value)
        for action in self.actions.on_load_active:
            action.setEnabled(value)
        if not value:
            self.actions.edit_brush_mode.setEnabled(False)

        if value and self.file_list_widget.count() > 0:
            self.actions.shape_manager.setEnabled(True)
        else:
            self.actions.shape_manager.setEnabled(False)

    def queue_event(self, function):
        QtCore.QTimer.singleShot(0, function)

    def status(self, message, delay=5000):
        self.statusBar().showMessage(message, delay)

    def reset_state(self):
        self._reset_label_loop()
        self.select_loop_count = -1
        self.label_list.clear()
        self.filename = None
        self.image_path = None
        self.image_data = None
        self.label_file = None
        self.other_data = {}
        self.canvas.reset_state()
        self.brightness_contrast_dialog.clear_image()
        if hasattr(self, "canvas_adjustment"):
            self.canvas_adjustment.hide()
        self._sync_empty_canvas_state()
        self._update_save_state_label()
        self.label_filter_combobox.text_box.clear()
        self.gid_filter_combobox.gid_box.clear()
        self._update_select_toggle_button_tooltip()

    def toggle_select_all(self):
        if self.select_toggle_action is None:
            return
        if self._has_active_shape_filter():
            self._update_select_toggle_button_tooltip()
            return
        if not self.canvas.shapes:
            self._update_select_toggle_button_tooltip()
            return

        all_visible = self._are_all_shapes_visible()
        self._set_all_objects_visibility(not all_visible)
        self._update_select_toggle_button_tooltip()

    def _has_active_shape_filter(self):
        current_label = self.label_filter_combobox.text_box.currentText()
        current_gid = self.gid_filter_combobox.gid_box.currentText()
        return bool(current_label) or current_gid not in ["", "-1"]

    def _update_select_toggle_button_tooltip(self):
        if self.select_toggle_action is None:
            return
        if self._has_active_shape_filter():
            tooltip = self.tr(
                "Toggle shapes visibility is unavailable while a label or group filter is active"
            )
            self.select_toggle_action.setEnabled(False)
            self.select_toggle_action.setToolTip(tooltip)
            self.select_toggle_action.setStatusTip(tooltip)
            return
        self.select_toggle_action.setEnabled(bool(self.canvas.shapes))
        if self._are_all_shapes_visible():
            tooltip = self.tr("Hide all shapes")
            icon = utils.new_icon("eye")
        else:
            tooltip = self.tr("Show all shapes")
            icon = utils.new_icon("hidden")
        self.select_toggle_action.setIcon(icon)
        self.select_toggle_action.setToolTip(tooltip)
        self.select_toggle_action.setStatusTip(tooltip)

    def _are_all_shapes_visible(self):
        if len(self.label_list) == 0:
            return True
        for item in self.label_list:
            if item.checkState() != Qt.CheckState.Checked:
                return False
            shape = item.shape()
            if shape is not None and not shape.visible:
                return False
        return True

    def _set_all_objects_visibility(self, visible):
        """Set all Objects panel checkboxes and shape visibility to visible (True/False)."""
        for item in self.label_list:
            label = item.shape().label
            if label in self.label_info:
                self.label_info[label]["visible"] = visible
        self._sync_label_list_visibility(lambda _item: visible)

    def reset_attribute(self, text, shape):
        # Skip validation for auto-labeling special constants
        if text in [
            AutoLabelingMode.OBJECT,
            AutoLabelingMode.ADD,
            AutoLabelingMode.REMOVE,
        ]:
            return text

        valid_labels = list(self.attributes.keys())
        if text not in valid_labels:
            most_similar_label = utils.find_most_similar_label(
                text, valid_labels
            )
            self.error_message(
                self.tr("Invalid label"),
                self.tr(
                    "Invalid label '{}' with validation type: {}!\n"
                    "Reset the label as {}."
                ).format(text, valid_labels, most_similar_label),
            )
            text = most_similar_label

        new_attributes = {
            attrs_key: (
                attrs_val[0]
                if isinstance(attrs_val, list) and attrs_val
                else attrs_val
            )
            for attrs_key, attrs_val in self.attributes[text].items()
        }
        shape.attributes = new_attributes
        return text

    def current_item(self):
        items = self.label_list.selected_items()
        if items:
            return items[0]
        return None

    def add_recent_file(self, filename):
        if filename in self.recent_files:
            self.recent_files.remove(filename)
        elif len(self.recent_files) >= self.max_recent:
            self.recent_files.pop()
        self.recent_files.insert(0, filename)

    # Callbacks
    def undo_shape_edit(self):
        # In brush-edit mode, undo reverts the last brush stroke instead of
        # the global shape history.
        if getattr(self.canvas, "is_brush_mode", False):
            self.canvas.brush_undo()
            self.actions.undo.setEnabled(self.canvas.brush_can_undo())
            return
        if not self.canvas.is_shape_restorable:
            return
        self.canvas.restore_shape()
        self._reload_shapes_after_history_change()
        self.actions.undo.setEnabled(self.canvas.is_shape_restorable)
        self.actions.redo.setEnabled(self.canvas.is_shape_redoable)
        self.set_dirty()

    def redo_shape_edit(self):
        """Re-apply the last undone shape edit.

        Companion to undo_shape_edit(): restores the state that undo
        discarded, then reloads the list so the UI reflects it.
        """
        if getattr(self.canvas, "is_brush_mode", False):
            # Brush strokes keep their own history; redo is not tracked
            # there yet.
            return
        if not self.canvas.is_shape_redoable:
            return
        self.canvas.redo_shape()
        self._reload_shapes_after_history_change()
        self.actions.undo.setEnabled(self.canvas.is_shape_restorable)
        self.actions.redo.setEnabled(self.canvas.is_shape_redoable)
        self.set_dirty()

    def _reload_shapes_after_history_change(self, keep_redo=True):
        """Rebuild the object list from canvas.shapes after undo/redo.

        ``label_list.clear()`` emits selection/drop signals. Those slots
        must not run mid-rebuild: they would call ``item.shape()`` on
        items Qt is destroying, which crashes the process on Ctrl+Z.

        The rebuild ends in ``canvas.load_shapes()`` which pushes the
        restored state back onto the undo stack and — via
        ``store_shapes()`` — clears the redo stack. Snapshot the redo
        branch and put it back, otherwise Redo is always disabled.
        """
        redo_backups = (
            list(self.canvas.shapes_redo_backups) if keep_redo else None
        )
        self._no_selection_slot = True
        selection_blocker = QtCore.QSignalBlocker(
            self.label_list.selectionModel()
        )
        drop_blocker = QtCore.QSignalBlocker(self.label_list.model())
        try:
            self.label_list.clear()
            self.load_shapes(self.canvas.shapes, update_last_label=False)
        finally:
            del selection_blocker
            del drop_blocker
            self._no_selection_slot = False
        if redo_backups is not None:
            self.canvas.shapes_redo_backups = redo_backups

    def get_label_file_list(self):
        label_file_list = []
        if not self.image_list and self.filename:
            dir_path, filename = osp.split(self.filename)
            label_file = osp.join(
                dir_path, osp.splitext(filename)[0] + ".json"
            )
            if osp.exists(label_file):
                label_file_list = [label_file]
        elif self.image_list and not self.output_dir and self.filename:
            file_list = os.listdir(osp.dirname(self.filename))
            for file_name in file_list:
                if not file_name.endswith(".json"):
                    continue
                label_file_list.append(
                    osp.join(osp.dirname(self.filename), file_name)
                )
        if self.output_dir:
            for file_name in os.listdir(self.output_dir):
                if not file_name.endswith(".json"):
                    continue
                label_file_list.append(osp.join(self.output_dir, file_name))
        return label_file_list

    def copy_shape_coordinates(self):
        item = self.current_item()
        if item is None:
            return
        shape = item.shape()
        if shape is None:
            return

        points = shape.points
        if shape.shape_type == "rectangle":
            if len(points) >= 2:
                x1, y1 = points[0].x(), points[0].y()
                x2, y2 = points[2].x(), points[2].y()
                coordinates = [x1, y1, x2, y2]
                coordinates = list(map(int, coordinates))
            else:
                return
        else:
            coordinates = []
            for point in points:
                coordinates.extend([point.x(), point.y()])

        coordinates_str = str(coordinates)
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(coordinates_str)

    def union_selection(self):
        if any(shape.locked for shape in self.canvas.selected_shapes):
            return
        rectangle_shapes, polygon_shapes = [], []
        for shape in self.canvas.selected_shapes:
            points = shape.points
            if shape.shape_type == "rectangle":
                xmin, ymin = (points[0].x(), points[0].y())
                xmax, ymax = (points[2].x(), points[2].y())
                rectangle_shapes.append([xmin, ymin, xmax, ymax])
            else:
                polygon_shapes.append([(p.x(), p.y()) for p in points])

        union_shape = shape.copy()

        if len(rectangle_shapes) > 0:
            min_x = min([bbox[0] for bbox in rectangle_shapes])
            min_y = min([bbox[1] for bbox in rectangle_shapes])
            max_x = max([bbox[2] for bbox in rectangle_shapes])
            max_y = max([bbox[3] for bbox in rectangle_shapes])

            union_shape.points[0].setX(min_x)
            union_shape.points[0].setY(min_y)
            union_shape.points[1].setX(max_x)
            union_shape.points[1].setY(min_y)
            union_shape.points[2].setX(max_x)
            union_shape.points[2].setY(max_y)
            union_shape.points[3].setX(min_x)
            union_shape.points[3].setY(max_y)
        else:
            # Create a blank mask
            min_x = min([min(p[0] for p in poly) for poly in polygon_shapes])
            min_y = min([min(p[1] for p in poly) for poly in polygon_shapes])
            max_x = max([max(p[0] for p in poly) for poly in polygon_shapes])
            max_y = max([max(p[1] for p in poly) for poly in polygon_shapes])

            width = int(max_x - min_x + 10)
            height = int(max_y - min_y + 10)
            mask = np.zeros((height, width), dtype=np.uint8)

            # Draw all polygons on the mask
            for polygon in polygon_shapes:
                contour = np.array(polygon, dtype=np.int32)
                shifted_contour = contour - np.array(
                    [min_x - 5, min_y - 5], dtype=np.int32
                )
                shifted_contour = shifted_contour.reshape((-1, 1, 2))
                cv2.fillPoly(mask, [shifted_contour], 255)

            # Find contours of the merged shape
            merged_contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            if merged_contours:
                largest_contour = max(merged_contours, key=cv2.contourArea)
                epsilon = 0.001 * cv2.arcLength(largest_contour, True)
                approx_contour = cv2.approxPolyDP(
                    largest_contour, epsilon, True
                )
                approx_contour = approx_contour.reshape(-1, 2) + np.array(
                    [min_x - 5, min_y - 5], dtype=np.int32
                )
                union_shape.points = [
                    QtCore.QPointF(float(x), float(y))
                    for x, y in approx_contour
                ]

        # Append merged shape and remove selected shapes
        self.add_label(union_shape)
        self.remove_labels(self.canvas.delete_selected())
        self.set_dirty()

        # Update UI state
        if self.no_shape():
            for action in self.actions.on_shapes_present:
                action.setEnabled(False)

    # Trainer
    def start_training(self, mode):
        """Delegates to training.launcher (menu wiring stays here)."""
        training_launcher.start_training(self, mode)

    # Tools
    def overview(self):
        if self.filename:
            OverviewDialog(parent=self)

    def digit_shortcut_manager(self):
        """Delegates to shortcuts.digit_controller (menu wiring stays)."""
        self.digit_shortcut_controller.digit_shortcut_manager()

    def label_manager(self):
        modify_label_dialog = LabelModifyDialog(
            parent=self, opacity=LABEL_OPACITY
        )
        result = modify_label_dialog.exec()
        if result == QtWidgets.QDialog.DialogCode.Accepted:
            if self.filename:
                self.load_file(self.filename)

    def gid_manager(self):
        modify_gid_dialog = GroupIDModifyDialog(parent=self)
        result = modify_gid_dialog.exec()
        if result == QtWidgets.QDialog.DialogCode.Accepted:
            self.load_file(self.filename)

    def shape_manager(self):
        modify_shape_dialog = ShapeModifyDialog(parent=self)
        result = modify_shape_dialog.exec()
        if result == QtWidgets.QDialog.DialogCode.Accepted:
            if modify_shape_dialog.need_reload and self.filename:
                self.load_file(self.filename)

    def _reset_label_loop(self):
        self.label_loop_count = -1
        self.label_loop_shapes = None
        if self.label_loop_popup is not None:
            self.label_loop_popup.close()

    def _show_label_loop_popup(self, text):
        if self.label_loop_popup is None:
            self.label_loop_popup = Popup(
                text,
                parent=self,
                msec=1800,
                icon=new_icon_path("copy-green", "svg"),
            )
            self.label_loop_popup.label.setTextFormat(Qt.TextFormat.PlainText)
            self.label_loop_popup.setAttribute(
                Qt.WidgetAttribute.WA_ShowWithoutActivating
            )
            self.label_loop_popup.setWindowFlag(
                Qt.WindowType.WindowDoesNotAcceptFocus, True
            )
            self.label_loop_popup.setWindowFlag(
                Qt.WindowType.WindowTransparentForInput, True
            )
        else:
            self.label_loop_popup.set_text(text)
        self.label_loop_popup.show_popup(
            self.central_widget().viewport(), top_offset=24
        )

    def loop_thru_labels(self):
        is_new_loop = self.label_loop_shapes is None
        if is_new_loop:
            self.label_loop_shapes = list(self.canvas.shapes)

        self.label_loop_count, shape = _find_next_label_loop_shape(
            self.label_loop_shapes,
            self.label_loop_count + 1,
            self.canvas.shapes,
        )
        if shape is None:
            message = (
                self.tr("No objects to review")
                if is_new_loop
                else self.tr("Review complete")
            )
            self._reset_label_loop()
            if not is_new_loop:
                self.canvas.deselect_shape()
                self.set_zoom(int(100 * self.scale_fit_window()))
            self._show_label_loop_popup(message)
            return

        width = self.central_widget().width() - 2.0
        height = self.central_widget().height() - 2.0

        im_width = self.canvas.pixmap.width()
        im_height = self.canvas.pixmap.height()

        zoom_scale = 4

        xs = []
        ys = []
        # loop through all points on this label
        for point in shape.points:
            xs.append(point.x())
            ys.append(point.y())

        # Set minimum label width to 30px this should handle point
        # lables and very tiny labels gracefully
        label_width = max(int(max(xs) - min(xs)), 30)
        x = (max(xs) + min(xs)) / 2
        y = (max(ys) + min(ys)) / 2

        zoom = int(100 * width / (zoom_scale * label_width))
        # Don't go past the max zoom which is 1000
        zoom = min(1000, zoom)

        self.set_zoom(zoom)

        x_range = self.scroll_bars[Qt.Orientation.Horizontal].maximum()
        x_step = self.scroll_bars[Qt.Orientation.Horizontal].pageStep()

        y_range = self.scroll_bars[Qt.Orientation.Vertical].maximum()
        # QT docs says Document length = maximum() - minimum() + pageStep().
        # so there's a weird pageStep thing we gotta add
        y_step = self.scroll_bars[Qt.Orientation.Vertical].pageStep()
        screen_width = width / (zoom / 100)
        # add half a screen to this
        x_scroll = int((x - screen_width / 2) / im_width * (x_range + x_step))
        x_scroll = min(max(0, x_scroll), x_range)

        screen_height = height / (zoom / 100)

        y_scroll = int(
            (y - screen_height / 2) / (im_height) * (y_range + y_step)
        )
        y_scroll = min(max(0, y_scroll), y_range)

        self.set_scroll(Qt.Orientation.Horizontal, x_scroll)
        self.set_scroll(Qt.Orientation.Vertical, y_scroll)
        self.canvas.prev_h_shape = self.canvas.h_shape = shape
        self.canvas.select_shapes([shape])

        progress = self.tr("Reviewing {current} / {total}").format(
            current=self.label_loop_count + 1,
            total=len(self.label_loop_shapes),
        )
        font_metrics = self.fontMetrics()
        label_width = min(
            240,
            max(
                0,
                self.central_widget().viewport().width()
                - _measure_text_width(font_metrics, progress)
                - 56,
            ),
        )
        label = font_metrics.elidedText(
            str(shape.label or ""), Qt.TextElideMode.ElideRight, label_width
        )
        if label:
            progress = f"{progress} - {label}"
        self._show_label_loop_popup(progress)

    def loop_select_labels(self):
        self.select_loop_count += 1
        if len(self.label_list) == 0 or self.select_loop_count >= len(
            self.label_list
        ):
            self.select_loop_count = -1
            self.canvas.deselect_shape()
            return

        item = self.label_list[self.select_loop_count]
        shape = item.shape()
        self.canvas.select_shapes([shape])

    def copy_to_clipboard(self, text):
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(text)
        QMessageBox.information(
            self,
            self.tr("Copied"),
            self.tr("The information has been copied to the clipboard."),
        )

    # General
    def toggle_drawing_sensitive(self, drawing=True):
        """Toggle drawing sensitive.

        In the middle of drawing, toggling between modes should be disabled.
        """
        self.actions.edit_mode.setEnabled(not drawing)
        self.actions.undo_last_point.setEnabled(drawing)
        self.actions.undo.setEnabled(not drawing)
        self.actions.delete.setEnabled(not drawing)
        self.actions.union_selection.setEnabled(not drawing)
        self.update_labeling_instruction()

    def create_digit_mode(self, digit_num):
        """Delegates to shortcuts.digit_controller (digit 0-9 actions)."""
        self.digit_shortcut_controller.create_digit_mode(digit_num)

    def toggle_draw_mode(
        self,
        edit=True,
        create_mode="rectangle",
        disable_auto_labeling=True,
        preserve_brush_mode=False,
    ):
        if not preserve_brush_mode:
            if getattr(self.canvas, "is_brush_mode", False):
                self.canvas.cancel_brush_mode()
            elif self.actions.edit_brush_mode.isChecked():
                self.actions.edit_brush_mode.setChecked(False)
        # Disable auto labeling if needed
        if (
            disable_auto_labeling
            and self.auto_labeling_widget.auto_labeling_mode
            != AutoLabelingMode.NONE
        ):
            self.clear_auto_labeling_marks()
            self.auto_labeling_widget.set_auto_labeling_mode(None)

        self.canvas.set_editing(edit)
        self.canvas.create_mode = create_mode
        self.canvas._brush_drawing = False
        if edit:
            self._enable_create_mode_actions()
        else:
            self.hide_attributes_panel()
            self.actions.union_selection.setEnabled(False)
            create_actions = self._create_mode_actions()
            if create_mode not in create_actions:
                raise ValueError(f"Unsupported create_mode: {create_mode}")
            self._enable_create_mode_actions()
            create_actions[create_mode].setEnabled(False)
        self.actions.edit_mode.setEnabled(not edit)
        self.update_labeling_instruction()

    def _create_mode_actions(self):
        """Map each canvas draw mode to the action that selects it.

        Kept in sync with ``Shape.get_supported_shape()``; a mode missing here
        raises in ``toggle_draw_mode`` instead of silently doing nothing.
        """
        actions = self.actions
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

    def _enable_create_mode_actions(self):
        """Re-arm every drawing mode when leaving or entering one."""
        for mode_action in self._create_mode_actions().values():
            mode_action.setEnabled(True)
        self.actions.create_brush_polygon_mode.setEnabled(True)
        for digit_action in self.actions.digit_shortcut_actions:
            digit_action.setEnabled(True)

    def toggle_brush_polygon_mode(self):
        """Toggle brush drawing mode for polygons."""
        if (
            self.canvas.drawing()
            and self.canvas.create_mode == "polygon"
            and self.canvas._brush_drawing
        ):
            self.toggle_draw_mode(True)
            return
        self.toggle_draw_mode(False, create_mode="polygon")
        self.canvas._brush_drawing = True
        self.actions.create_mode.setEnabled(True)
        self.actions.create_brush_polygon_mode.setEnabled(False)

    def set_edit_mode(self):
        # Disable auto labeling
        self.clear_auto_labeling_marks()
        self.auto_labeling_widget.set_auto_labeling_mode(None)

        self.toggle_draw_mode(True)
        self.update_labeling_instruction()

    def toggle_brush_mode(self, checked: bool) -> None:
        """Enable or disable brush editing for a polygon.

        Enabling requires exactly one selected polygon and switches the
        canvas to edit mode before brush editing starts.

        Args:
            checked: ``True`` when the toolbar toggle is switched on.
        """
        if checked:
            selected_shapes = self.canvas.selected_shapes
            if (
                len(selected_shapes) != 1
                or selected_shapes[0].shape_type != "polygon"
                or selected_shapes[0].locked
            ):
                self.actions.edit_brush_mode.setChecked(False)
                return
            if self.canvas.current is not None:
                self.canvas.current = None
                self.canvas.set_hiding(False)
                self.canvas.drawing_polygon.emit(False)
                self.canvas.update()
            self.toggle_draw_mode(True, preserve_brush_mode=True)
            self.canvas.set_brush_mode(True)
            self.update_labeling_instruction()
            return

        if getattr(self.canvas, "is_brush_mode", False):
            self.canvas.set_brush_mode(False)
        self.update_labeling_instruction()

    def on_brush_mode_changed(self, enabled: bool) -> None:
        """Synchronize brush action and lock the active shape selection."""
        self.actions.edit_brush_mode.setChecked(enabled)
        self.label_list.setEnabled(not enabled)

    def update_file_menu(self):
        current = self.filename

        def exists(filename):
            return osp.exists(str(filename))

        menu = self.menus.recent_files
        menu.clear()
        files = [f for f in self.recent_files if f != current and exists(f)]
        if self.last_open_dir and osp.isdir(self.last_open_dir):
            dir_name = (
                QtCore.QFileInfo(self.last_open_dir).fileName()
                or self.last_open_dir
            )
            action = QtGui.QAction(
                utils.new_icon("folder", "svg"),
                self.tr("Open Last Dir: %s") % dir_name,
                self,
            )
            action.triggered.connect(
                functools.partial(self.load_recent_dir, self.last_open_dir)
            )
            menu.addAction(action)
            if files:
                menu.addSeparator()
        for i, f in enumerate(files):
            icon = utils.new_icon("labels")
            action = QtGui.QAction(
                icon, "&%d %s" % (i + 1, QtCore.QFileInfo(f).fileName()), self
            )
            action.triggered.connect(functools.partial(self.load_recent, f))
            menu.addAction(action)

    def refresh_shape_lock_action(self):
        items = self.label_list.selected_items()
        shapes = [item.shape() for item in items if item.shape() is not None]
        action = self.actions.toggle_shape_lock
        action.setEnabled(bool(shapes))
        with QtCore.QSignalBlocker(action):
            action.setChecked(bool(shapes) and all(s.locked for s in shapes))

    def toggle_label_items_lock(self, items):
        shapes = [item.shape() for item in items if item.shape() is not None]
        if not shapes:
            return
        for shape in shapes:
            shape.locked = not shape.locked
        self._update_shapes_lock(shapes)

    def toggle_selected_shapes_lock(self, locked):
        items = self.label_list.selected_items()
        shapes = [item.shape() for item in items if item.shape() is not None]
        if not shapes:
            shapes = list(self.canvas.selected_shapes)
        if not shapes:
            return
        self._set_shapes_locked(shapes, locked)

    def _set_shapes_locked(self, shapes, locked):
        for shape in shapes:
            shape.locked = locked
        self._update_shapes_lock(shapes)

    def _update_shapes_lock(self, shapes):
        for shape in shapes:
            item = self.label_list.find_item_by_shape(shape)
            if item is not None:
                _set_label_list_item_lock(item, shape.locked)
        self.canvas.store_shapes()
        self.canvas.update()
        if self.canvas.editing():
            self.shape_selection_changed(self.canvas.selected_shapes)
        else:
            self.refresh_shape_lock_action()
        self.set_dirty()

    def pop_file_list_menu(self, point):
        item = self.file_list_widget.itemAt(point)
        if item is None:
            return

        menu = QtWidgets.QMenu(self.file_list_widget)
        copy_name_action = menu.addAction(
            utils.new_icon("copy", "svg"), self.tr("Copy File Name")
        )
        copy_path_action = menu.addAction(
            utils.new_icon("copy", "svg"), self.tr("Copy File Path")
        )
        menu.addSeparator()
        check_and_next_action = menu.addAction(
            self.tr("标记已检查并下一张")
        )
        del_label_action = menu.addAction(
            utils.new_icon("trash", "svg"), self.tr("删除标注文件")
        )
        del_image_action = menu.addAction(
            utils.new_icon("trash", "svg"), self.tr("删除图片文件")
        )
        menu.addSeparator()
        sort_menu = menu.addMenu(self.tr("排序方式"))
        sort_name = sort_menu.addAction(self.tr("按文件名"))
        sort_time = sort_menu.addAction(self.tr("按修改时间"))
        sort_annotation = sort_menu.addAction(self.tr("按标注状态"))
        current_sort = getattr(self, "_file_sort_mode", "name")
        sort_name.setCheckable(True)
        sort_time.setCheckable(True)
        sort_annotation.setCheckable(True)
        sort_name.setChecked(current_sort == "name")
        sort_time.setChecked(current_sort == "time")
        sort_annotation.setChecked(current_sort == "annotation")
        action = menu.exec(self.file_list_widget.mapToGlobal(point))
        if action == copy_name_action:
            self.copy_file_path(osp.basename(item.text()))
        elif action == copy_path_action:
            self.copy_file_path(item.text())
        elif action == check_and_next_action:
            self.file_list_widget.setCurrentItem(item)
            self.load_file(item.text())
            self.mark_checked_and_next()
        elif action == del_label_action:
            self._delete_via_context(item, include_image=False)
        elif action == del_image_action:
            self._delete_via_context(item, include_image=True)
        elif action in (sort_name, sort_time, sort_annotation):
            mode = {
                sort_name: "name",
                sort_time: "time",
                sort_annotation: "annotation",
            }[action]
            self._file_sort_mode = mode
            self._apply_file_sort()

    def _file_sort_key(self, item, mode):
        """Stable sort key for a file-list row under the given mode."""
        text = item.text() or ""
        if mode == "time":
            try:
                return (os.path.getmtime(text), text)
            except OSError:
                return (0.0, text)
        if mode == "annotation":
            checked = item.data(Qt.ItemDataRole.UserRole) is True
            annotated = bool(item.data(FILE_ANNOTATION_ROLE))
            negative = bool(item.data(FILE_NEGATIVE_ROLE))
            low_conf = bool(item.data(FILE_LOW_CONF_ROLE))
            status = (
                0
                if checked
                else 1
                if annotated
                else 2
                if negative
                else 3
                if low_conf
                else 4
            )
            return (status, text.lower())
        return (osp.basename(text).lower(),)

    def _apply_file_sort(self):
        """Re-order the file list rows without losing the current selection."""
        widget = self.file_list_widget
        if widget.count() <= 1:
            return
        mode = getattr(self, "_file_sort_mode", "name")
        current = widget.currentItem()
        current_text = current.text() if current else None
        count = widget.count()
        items = [widget.takeItem(0) for _ in range(count)]
        items.sort(key=lambda item: self._file_sort_key(item, mode))
        for item in items:
            widget.addItem(item)
        # Every row just moved, so the path -> row map has to follow it;
        # a stale map makes _current_file_item() point at another image.
        for row in range(widget.count()):
            self.fn_to_index[widget.item(row).text()] = row
        if current_text is not None:
            for row in range(widget.count()):
                if widget.item(row).text() == current_text:
                    widget.setCurrentRow(row)
                    widget.scrollToItem(widget.item(row))
                    break

    def show_run_history(self, _value=False):
        """Delegates to training.launcher (menu wiring stays here)."""
        training_launcher.show_run_history(self, _value)

    def show_shortcuts_help(self):
        """Dialog listing every configured shortcut with a search box."""
        shortcuts = self._config.get("shortcuts", {})
        rows = build_shortcut_rows(shortcuts)
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(self.tr("快捷键速查"))
        dialog.resize(460, 520)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        search = QtWidgets.QLineEdit()
        search.setPlaceholderText(self.tr("搜索快捷键或功能（如 Ctrl+Z / 撤销）…"))
        layout.addWidget(search)

        tree = QtWidgets.QTreeWidget()
        tree.setHeaderLabels([self.tr("快捷键"), self.tr("功能"), self.tr("分组")])
        tree.setColumnWidth(0, 110)
        tree.setColumnWidth(1, 240)
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        layout.addWidget(tree, 1)

        def render():
            tree.clear()
            for group_title, key_text, description in filter_shortcut_rows(
                rows, search.text()
            ):
                item = QtWidgets.QTreeWidgetItem(
                    [key_text, description, group_title]
                )
                tree.addTopLevelItem(item)

        def on_query(_text):
            render()
            if tree.topLevelItemCount():
                tree.scrollToTop()

        search.textChanged.connect(on_query)
        render()

        close_btn = QtWidgets.QPushButton(self.tr("关闭"))
        close_btn.clicked.connect(dialog.accept)
        close_btn.setFixedWidth(80)
        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)
        dialog.exec()

    def _delete_via_context(self, item, include_image):
        """Right-click delete from the file list.

        Both destructive actions already exist in the File menu but operate
        on the *current* file; from the list we first make the clicked row
        the current file, then reuse that same logic so moving-to-_delete_
        / label removal / list refresh behaviour stays identical.
        """
        if item is None:
            return
        try:
            self.file_list_widget.setCurrentItem(item)
            self.load_file(item.text())
        except Exception:  # noqa: BLE001
            return
        if include_image:
            self.delete_image_file()
        else:
            self.delete_file()

    def copy_file_path(self, file_path):
        # Report what actually happened. The popup used to say "Copy
        # Successful" unconditionally, so a failed clipboard write looked
        # like a success and the user only found out when pasting.
        if copy_text_to_system_clipboard(file_path):
            message = self.tr("Copy Successful")
            icon = new_icon_path("copy-green", "svg")
        else:
            message = self.tr("复制失败：无法访问系统剪贴板")
            icon = new_icon_path("error", "svg")
        popup = Popup(message, parent=self, icon=icon)
        popup.show_popup(self, position="default")

    def _recent_dir_list(self):
        """Recent folders persisted in QSettings, newest first."""
        raw = self.settings.value("recent_dirs", []) or []
        if isinstance(raw, list):
            return [str(item) for item in raw if str(item)]
        return [str(raw)] if raw else []

    def _record_recent_dir(self, directory):
        """Push a folder to the recent list and persist it."""
        if not directory:
            return
        dirs = push_recent_dir(self._recent_dir_list(), directory)
        self.settings.setValue("recent_dirs", dirs)

    def _update_recent_dirs_menu(self):
        menu = self.menus.recent_dirs
        menu.clear()
        dirs = self._recent_dir_list()
        if not dirs:
            empty_action = menu.addAction(self.tr("（暂无最近文件夹）"))
            empty_action.setEnabled(False)
            return
        for path in dirs:
            action = menu.addAction(osp.basename(osp.normpath(path)))
            action.setToolTip(path)
            action.triggered.connect(
                functools.partial(self.load_recent_dir, path)
            )

    def load_recent_dir(self, directory):
        """Reopen a folder picked from the recent-folders menu."""
        if not directory:
            return
        self.import_image_folder(directory, load=True)

    def _review_state_for_label_file(self, label_file):
        if not QtCore.QFile.exists(label_file):
            return REVIEW_UNCHECKED
        return _label_file_review_state(label_file)

    def _review_state_name(self, state):
        """Delegates to filelist.items."""
        return filelist_items.review_state_name(self, state)

    def _file_item_tooltip(
        self, file, label_file, state, reviewed_at=None, counts=None,
        negative=False, low_conf=False,
    ):
        """Delegates to filelist.items."""
        return filelist_items.file_item_tooltip(
            self, file, label_file, state, reviewed_at=reviewed_at,
            counts=counts, negative=negative, low_conf=low_conf,
        )

    def _shape_tooltip(self, shape):
        """Hover text for one object row: everything the label JSON knows.

        The row itself shows only a name, so provenance -- which model drew this
        box, from which weights -- is otherwise invisible until a cleanup pass
        deletes something it should not have.
        """
        source = get_source(shape)
        if source == SOURCE_MODEL:
            origin = self.tr("模型产出：%1").replace(
                "%1", model_of(shape) or self.tr("未记录")
            )
            version = model_version_of(shape)
            if version:
                origin += self.tr(" · 权重 %1").replace("%1", version)
        elif source == SOURCE_HUMAN:
            origin = self.tr("人工绘制")
        else:
            origin = self.tr("来源未记录（早于来源记录功能）")

        lines = [
            self.tr("类别：%1").replace(
                "%1", shape.label or self.tr("（空）")
            )
        ]
        if shape.group_id is not None:
            lines.append(
                self.tr("群组编号：%1").replace("%1", str(shape.group_id))
            )
        lines.append(
            self.tr("形状：%1").replace("%1", shape.shape_type or "")
        )
        lines.append(origin)
        if shape.score is not None:
            lines.append(
                self.tr("置信度：%1").replace("%1", f"{shape.score:.3f}")
            )
        points = shape.points or []
        detail = self.tr("顶点数：%1").replace("%1", str(len(points)))
        if len(points) >= 2:
            xs = [point.x() for point in points]
            ys = [point.y() for point in points]
            detail += self.tr("，外接框 %1x%2").replace(
                "%1", str(int(round(max(xs) - min(xs))))
            ).replace("%2", str(int(round(max(ys) - min(ys)))))
        lines.append(detail)
        for key, value in sorted((shape.attributes or {}).items()):
            lines.append(
                self.tr("属性 %1：%2")
                .replace("%1", str(key))
                .replace("%2", str(value))
            )
        if shape.description:
            lines.append(
                self.tr("描述：%1").replace("%1", shape.description)
            )
        protected = []
        if shape.locked:
            protected.append(self.tr("已锁定"))
        if shape.difficult:
            protected.append(self.tr("困难样本"))
        if not getattr(shape, "visible", True):
            protected.append(self.tr("已隐藏"))
        if protected:
            lines.append(" · ".join(protected))
        lines.append(self.tr("双击行可改标签；删除后可用 Ctrl+Z 撤销"))
        return "\n".join(lines)

    def _update_current_file_tooltip(self):
        """Give the open row the counts that only the canvas knows."""
        item = self._current_file_item()
        if item is None or not self.filename:
            return
        shapes = self.canvas.shapes or []
        counts = {
            "total": len(shapes),
            "model": 0,
            "human": 0,
            "unknown": 0,
        }
        for shape in shapes:
            source = get_source(shape)
            if source == SOURCE_MODEL:
                counts["model"] += 1
            elif source == SOURCE_HUMAN:
                counts["human"] += 1
            else:
                counts["unknown"] += 1
        state = self._current_review_state()
        item.setToolTip(
            self._file_item_tooltip(
                self.filename,
                self._label_path_for_image(self.filename),
                state,
                self.other_data.get("reviewed_at"),
                counts=counts,
            )
        )

    def _label_file_checked(self, label_file):
        state = self._review_state_for_label_file(label_file)
        return state == REVIEW_CONFIRMED

    def _set_file_item_checked(self, item, checked):
        state = REVIEW_CONFIRMED if checked else REVIEW_UNCHECKED
        return self._set_file_item_review_state(item, state)

    def _set_file_item_review_state(self, item, state, reviewed_at=None):
        """Delegates to filelist.items (async checker & tests call this)."""
        return filelist_items.set_file_item_review_state(
            self, item, state, reviewed_at
        )

    def _refresh_file_item_tooltip(self, item, counts=None):
        """Delegates to filelist.items."""
        filelist_items.refresh_file_item_tooltip(self, item, counts)

    @staticmethod
    def _is_confirmed(state):
        return filelist_items.is_confirmed(state)

    def _set_file_item_annotated(self, item, annotated, negative=False):
        """Delegates to filelist.items."""
        filelist_items.set_file_item_annotated(
            self, item, annotated, negative
        )

    def _refresh_file_item_status_icon(self, item):
        """Delegates to filelist.items (tests call this directly)."""
        filelist_items.refresh_file_item_status_icon(self, item)

    def _file_item_annotation_checked(self, item):
        return filelist_items.file_item_annotation_checked(item)

    def _label_path_for_image(self, image_file):
        label_file = osp.splitext(image_file)[0] + ".json"
        if self.output_dir:
            label_file = osp.join(self.output_dir, osp.basename(label_file))
        return label_file

    def _set_file_item_low_conf(self, item, has_low_conf):
        """Delegates to filelist.items."""
        filelist_items.set_file_item_low_conf(self, item, has_low_conf)

    def _active_label_dir(self):
        directory = self.output_dir or None
        if not directory and self.filename:
            directory = osp.dirname(self.filename)
        return directory

    def _prev_labeled_image(self):
        """Walk back from the current image; first labelled one wins.

        Returns ``(image_path, label_file, (w, h))`` or ``None``.
        """
        paths = self.image_list
        if not paths:
            return None
        start = self.file_list_widget.currentRow()
        if start < 0:
            return None
        for index in range(start - 1, -1, -1):
            image_path = paths[index]
            label_file = self._label_path_for_image(image_path)
            if not osp.exists(label_file):
                continue
            try:
                with open(label_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("shapes"):
                    probe = QtGui.QImage(image_path)
                    img_size = (
                        (probe.width(), probe.height())
                        if not probe.isNull()
                        else None
                    )
                    return image_path, label_file, img_size
            except (OSError, ValueError):
                continue
        return None

    def _propagate_previous_labels(self):
        """Copy annotations from the previous image, scaled to this one."""
        from anylabeling.views.labeling.utils.shape_propagate import (
            propagate_labels,
        )

        if not self.filename:
            self.status(self.tr("请先打开一张图片再使用标注传播。"), 3000)
            return
        image = getattr(self, "image", None)
        if image is None or image.isNull():
            image = QtGui.QImage(self.filename)
        dst_w, dst_h = image.width(), image.height()
        if dst_w <= 0 or dst_h <= 0:
            self.status(self.tr("无法读取当前图片尺寸。"), 3000)
            return

        prev = self._prev_labeled_image()
        if prev is None:
            self.status(self.tr("当前图片之前没有可复制的标注。"), 3000)
            return
        _prev_path, prev_file, prev_size = prev

        existing = []
        for shape in self.canvas.shapes:
            existing.append(
                {
                    "label": shape.label,
                    "shape_type": getattr(shape, "shape_type", "rectangle"),
                    "points": [[p.x(), p.y()] for p in shape.points],
                }
            )

        planned = propagate_labels(
            prev_file, prev_size, dst_w, dst_h, existing_shapes=existing
        )
        if not planned:
            self.status(self.tr("没有需要复制的新标注（已存在或来源为空）。"), 3000)
            return

        new_shapes = []
        for payload in planned:
            shape = Shape(
                label=payload.get("label") or "",
                shape_type=payload.get("shape_type") or "rectangle",
            )
            for point in payload.get("points") or []:
                shape.add_point(QtCore.QPointF(float(point[0]), float(point[1])))
            if (
                len(shape.points) > 1
                and shape.shape_type not in ("point", "linestrip")
            ):
                shape.close()
            new_shapes.append(shape)

        self.load_shapes(
            list(self.canvas.shapes) + new_shapes, replace=True
        )
        self.set_dirty()
        self.status(
            self.tr("已从上一张图复制 %1 个标注。").replace(
                "%1", str(len(new_shapes))
            ),
            4000,
        )

    def _load_active_thresholds(self):
        """Per-class accept/review thresholds for the open folder (cached)."""
        directory = self._active_label_dir()
        if not directory:
            return {}
        if getattr(self, "_al_threshold_dir", None) == directory and getattr(
            self, "_al_thresholds", None
        ) is not None:
            return self._al_thresholds
        self._al_threshold_dir = directory
        self._al_thresholds = load_thresholds(directory)
        return self._al_thresholds

    def invalidate_active_thresholds(self):
        """Drop the cached thresholds (called after a calibration run)."""
        self._al_threshold_dir = None
        self._al_thresholds = None

    def _shapes_need_review(self, shapes):
        thresholds = self._load_active_thresholds()
        if thresholds:
            return needs_review(shapes, thresholds=thresholds)
        # No calibration yet: keep the historical fixed band.
        return shapes_have_low_confidence(shapes)

    def _file_item_has_low_conf(self, item):
        cached = item.data(FILE_LOW_CONF_ROLE)
        if cached is not None:
            return bool(cached)
        has_low_conf = False
        label_file = self._label_path_for_image(item.text())
        if QtCore.QFile.exists(label_file):
            try:
                with open(label_file, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                has_low_conf = self._shapes_need_review(
                    data.get("shapes") if isinstance(data, dict) else None
                )
            except Exception:  # noqa: BLE001
                has_low_conf = False
        self._set_file_item_low_conf(item, has_low_conf)
        return has_low_conf

    def _note_save_quality(self, shapes, file_item=None):
        image = getattr(self, "image", None)
        image_width = image.width() if image is not None else 0
        image_height = image.height() if image is not None else 0
        stats = inspect_shape_quality(shapes, image_width, image_height)
        self._last_quality_status = format_save_quality_status(stats)
        if file_item is not None:
            self._set_file_item_low_conf(
                file_item, self._shapes_need_review(shapes)
            )
            combo = getattr(self, "file_filter_combo", None)
            if combo is not None and combo.currentData() == "low_conf":
                file_item.setHidden(not bool(file_item.data(FILE_LOW_CONF_ROLE)))
        return self._last_quality_status

    def _maybe_focus_low_confidence_shapes(self):
        combo = getattr(self, "file_filter_combo", None)
        if combo is None or combo.currentData() != "low_conf":
            return
        thresholds = self._load_active_thresholds()
        selected = []
        for shape in self.canvas.shapes:
            accept, review = thresholds_for(
                getattr(shape, "label", "") or "", thresholds
            )
            if shape_uncertainty(shape, accept, review) > 0:
                selected.append(shape)
        if selected:
            self.canvas.select_shapes(selected)

    def mark_file_item_negative_state(self, image_file, negative):
        """Public helper used by batch auto-label to flag a saved image as a
        negative sample (confirmed empty annotation, zero shapes).

        Mirrors what happens on the single-image save path so batch runs and
        manual saves stay consistent: negative samples show an amber badge in
        the file list and export as empty .txt for YOLO training.
        """
        try:
            target = osp.normpath(osp.abspath(image_file))
            items = self.file_list_widget.findItems(
                target, Qt.MatchFlag.MatchExactly
            )
            if not items:
                for row in range(self.file_list_widget.count()):
                    candidate = self.file_list_widget.item(row)
                    if osp.normpath(osp.abspath(candidate.text())) == target:
                        items = [candidate]
                        break
            if len(items) == 1:
                self._set_file_item_annotated(
                    items[0], True, negative=bool(negative)
                )
        except Exception:  # noqa: BLE001
            pass

    def _create_file_list_item(self, file, label_file, read_checked=True):
        item = QtWidgets.QListWidgetItem(file)
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if self._config.get("file_list_checkbox_editable", False):
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        item.setFlags(flags)
        has_annotation = (
            QtCore.QFile.exists(label_file) and LabelFile.is_label_file(label_file)
        )
        item.setData(FILE_ANNOTATION_ROLE, bool(has_annotation))
        if self._config.get("file_list_checkbox_editable", False):
            if has_annotation:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
        # Reading the JSON is slow on large folders; batch callers pass
        # read_checked=False and let the background checker fill the dot.
        if read_checked:
            state, reviewed_at = label_file_review_info(label_file)
        else:
            state, reviewed_at = REVIEW_UNCHECKED, None
        item.setData(Qt.ItemDataRole.UserRole, state == REVIEW_CONFIRMED)
        item.setData(FILE_REVIEW_ROLE, state)
        item.setData(FILE_REVIEWED_AT_ROLE, reviewed_at)
        self._refresh_file_item_status_icon(item)
        item.setToolTip(
            self._file_item_tooltip(file, label_file, state, reviewed_at)
        )
        return item

    def _current_file_item(self):
        if str(self.filename) not in self.fn_to_index:
            return None
        return self.file_list_widget.item(self.fn_to_index[str(self.filename)])

    def _current_review_state(self):
        state = self.other_data.get(REVIEW_STATE_FIELD)
        if state in REVIEW_STATES:
            return state
        if self.other_data.get(CHECKED_FIELD, False) is True:
            return REVIEW_CONFIRMED
        return REVIEW_UNCHECKED

    def _annotation_checked(self):
        return self._current_review_state() == REVIEW_CONFIRMED

    def _update_annotation_checked_action(self):
        if not hasattr(self, "actions"):
            return
        action = self.actions.toggle_annotation_checked
        quick_action = getattr(self.actions, "mark_checked_and_next", None)
        reject_action = getattr(self.actions, "mark_rejected_and_next", None)
        checked = self._annotation_checked()
        if action.isChecked() != checked:
            action.setChecked(checked)
        if checked:
            action.setText(self.tr("Mark as Unchecked"))
            tip = self.tr("Mark current annotation as unchecked")
        else:
            action.setText(self.tr("Mark as Checked"))
            tip = self.tr("Mark current annotation as checked")
        action.setToolTip(tip)
        action.setStatusTip(tip)
        enabled = self.filename is not None and not self.image.isNull()
        action.setEnabled(enabled)
        if quick_action is not None:
            quick_action.setEnabled(enabled)
        if reject_action is not None:
            reject_action.setEnabled(enabled)

    def _update_current_file_checked_item(self):
        item = self._current_file_item()
        if item is not None:
            self._set_file_item_review_state(item, self._current_review_state())

    def _sync_annotation_checked_state(self):
        self._update_annotation_checked_action()
        self._update_current_file_checked_item()
        self._update_classification_action()

    def set_annotation_checked(self, checked):
        """Delegates to filelist.controller (action wiring stays)."""
        # Built on demand: the controller is stateless, and light test
        # stubs never carry an instance.
        FileReviewController(self).set_annotation_checked(checked)

    def _classification_suggestions(self):
        """``(suggestions, model_name)`` recorded for the open file."""
        data = self.other_data.get(PREDICTIONS_FIELD)
        if isinstance(data, dict):
            return list(data.get("classes") or []), data.get("model")
        if isinstance(data, list):
            return list(data), None
        return [], None

    def _apply_model_predictions(self, predictions):
        """Store classifier suggestions on the open file, still unconfirmed."""
        if self.filename is None or self.image.isNull():
            return
        cleaned = [
            item
            for item in predictions or []
            if isinstance(item, dict) and item.get("label")
        ]
        if cleaned:
            self.other_data[PREDICTIONS_FIELD] = {
                "model": cleaned[0].get("model"),
                "created_at": cleaned[0].get("created_at"),
                "classes": cleaned,
            }
        else:
            self.other_data.pop(PREDICTIONS_FIELD, None)
        self._update_classification_action()
        label_file = self.get_label_file()
        if self.save_labels(label_file):
            self.set_clean()
        if cleaned:
            top = cleaned[0]
            score = float(top.get("score") or 0.0)
            self.status(
                self.tr("分类建议：%1（%2），确认后才写入类别")
                .replace("%1", str(top.get("label")))
                .replace("%2", f"{score:.2f}"),
                5000,
            )
        else:
            self.status(self.tr("分类模型没有达到阈值的建议"), 3000)

    def confirm_classification(self, _value=False):
        """Accept the top suggestion into the image flags.

        The Classify training path reads flags, so this is the point where a
        model suggestion becomes training data - and the only place the label
        JSON can record it without a score.
        """
        if self.filename is None or self.image.isNull():
            return
        suggestions, _model_name = self._classification_suggestions()
        if not suggestions:
            self.status(self.tr("当前图片没有可确认的分类建议"), 3000)
            return
        label = str(suggestions[0].get("label") or "")
        if not label:
            return

        flags = {}
        for row in range(self.flag_widget.count()):
            item = self.flag_widget.item(row)
            flags[item.text()] = item.checkState() == Qt.CheckState.Checked
        flags[label] = True
        self.load_flags(flags)
        self.set_dirty()
        label_file = self.get_label_file()
        saved = self.save_labels(label_file)
        if saved:
            self.set_clean()
        self._show_save_feedback(saved)
        self._update_classification_action()

    def _update_classification_action(self):
        action = getattr(self.actions, "confirm_classification", None)
        if action is None:
            return
        suggestions, _model_name = self._classification_suggestions()
        enabled = bool(suggestions) and self.filename is not None
        action.setEnabled(enabled)
        if suggestions:
            top = suggestions[0]
            text = self.tr("确认分类建议：%1").replace(
                "%1", str(top.get("label"))
            )
            tip = self.tr("把模型建议写入图片类别，之后仍可手工改判")
        else:
            text = self.tr("确认分类建议")
            tip = self.tr("没有待确认的分类建议")
        if action.text() != text:
            action.setText(text)
        action.setToolTip(tip)
        action.setStatusTip(tip)

    def _apply_review_state(self, state):
        """Delegates to filelist.controller (tests call this directly)."""
        # Built on demand: the controller is stateless, and light test
        # stubs never carry an instance.
        FileReviewController(self).apply_review_state(state)

    def mark_checked_and_next(self, _value=False):
        """Delegates to filelist.controller (action wiring stays)."""
        # Built on demand: the controller is stateless, and light test
        # stubs never carry an instance.
        FileReviewController(self).mark_checked_and_next(_value)

    def mark_rejected_and_next(self, _value=False):
        """Delegates to filelist.controller (action wiring stays)."""
        # Built on demand: the controller is stateless, and light test
        # stubs never carry an instance.
        FileReviewController(self).mark_rejected_and_next(_value)

    def _append_filter_submenus(
        self, parent_menu, prepend=False, after_filter_actions=None
    ):
        label_menu = QtWidgets.QMenu(self.tr("Filter by Label"), parent_menu)
        gid_menu = QtWidgets.QMenu(self.tr("Filter by Group ID"), parent_menu)
        if prepend and parent_menu.actions():
            first_action = parent_menu.actions()[0]
            parent_menu.insertMenu(first_action, label_menu)
            parent_menu.insertMenu(first_action, gid_menu)
            parent_menu.insertSeparator(first_action)
            if after_filter_actions:
                for action in after_filter_actions:
                    parent_menu.insertAction(first_action, action)
                parent_menu.insertSeparator(first_action)
        else:
            parent_menu.addSeparator()
            parent_menu.addMenu(label_menu)
            parent_menu.addMenu(gid_menu)
            if after_filter_actions:
                parent_menu.addSeparator()
                utils.add_actions(parent_menu, after_filter_actions)
        return label_menu, gid_menu

    def _populate_label_filter_menu(self, menu):
        menu.clear()
        action_group = QtGui.QActionGroup(menu)
        action_group.setExclusive(True)
        current_label = self.label_filter_combobox.text_box.currentText()
        for label in self.label_filter_combobox.items:
            text = self.tr("All Labels") if label == "" else label
            action = menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(label == current_label)
            action.triggered.connect(
                functools.partial(self.set_label_filter_value, label)
            )
            action_group.addAction(action)

    def _populate_gid_filter_menu(self, menu):
        menu.clear()
        action_group = QtGui.QActionGroup(menu)
        action_group.setExclusive(True)
        current_gid = self.gid_filter_combobox.gid_box.currentText()
        for gid in self.gid_filter_combobox.items:
            text = self.tr("All Group IDs") if gid == "-1" else gid
            action = menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(gid == current_gid)
            action.triggered.connect(
                functools.partial(self.set_gid_filter_value, gid)
            )
            action_group.addAction(action)

    def refresh_filter_menus(self):
        self.update_combo_box(block_signal=True)
        self.update_gid_box(block_signal=True)

        menus = [
            (self.canvas_label_filter_menu_0, self.canvas_gid_filter_menu_0),
            (self.canvas_label_filter_menu_1, self.canvas_gid_filter_menu_1),
        ]
        for label_menu, gid_menu in menus:
            if label_menu is not None:
                self._populate_label_filter_menu(label_menu)
            if gid_menu is not None:
                self._populate_gid_filter_menu(gid_menu)

    def set_label_filter_value(
        self, label, _checked=False, block_signal=False
    ):
        index = self.label_filter_combobox.text_box.findText(str(label))
        if index < 0:
            index = self.label_filter_combobox.text_box.findText("")
        if index >= 0:
            blocker = None
            if block_signal:
                blocker = QtCore.QSignalBlocker(
                    self.label_filter_combobox.text_box
                )
            self.label_filter_combobox.text_box.setCurrentIndex(index)
            del blocker

    def set_gid_filter_value(self, gid, _checked=False, block_signal=False):
        index = self.gid_filter_combobox.gid_box.findText(str(gid))
        if index < 0:
            index = self.gid_filter_combobox.gid_box.findText("-1")
        if index >= 0:
            blocker = None
            if block_signal:
                blocker = QtCore.QSignalBlocker(
                    self.gid_filter_combobox.gid_box
                )
            self.gid_filter_combobox.gid_box.setCurrentIndex(index)
            del blocker

    def validate_label(self, label):
        # no validation
        if self._config["validate_label"] is None:
            return True

        for i in range(self.unique_label_list.count()):
            label_i = self.unique_label_list.item(i).data(
                Qt.ItemDataRole.UserRole
            )
            if self._config["validate_label"] in ["exact"]:
                if label_i == label:
                    return True
        return False

    def batch_edit_labels(self, shapes):
        if not self._batch_edit_warning_shown:
            reply = QtWidgets.QMessageBox.question(
                self,
                self.tr("Batch Edit"),
                self.tr(
                    "You are about to edit multiple shapes in batch mode. "
                    "You can undo this with Ctrl+Z.\n\n"
                    "This warning will only be shown once. Do you want to continue?"
                ),
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )

            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return

            self._batch_edit_warning_shown = True

        first_shape = shapes[0]
        result = self.label_dialog.pop_up(
            text=first_shape.label,
            flags=first_shape.flags,
            group_id=first_shape.group_id,
            description=first_shape.description,
            difficult=first_shape.difficult,
            kie_linking=first_shape.kie_linking,
            move_mode="center",
        )

        if result[0] is None:
            return

        text, flags, group_id, description, difficult, kie_linking = result

        if not self.validate_label(text):
            self.error_message(
                self.tr("Invalid label"),
                self.tr("Invalid label '{}' with validation type '{}'").format(
                    text, self._config["validate_label"]
                ),
            )
            return

        states_before = [_shape_editable_state(shape) for shape in shapes]
        for shape in shapes:
            if self.attributes and text and text != shape.label:
                text = self.reset_attribute(text, shape)

            shape.label = text
            shape.flags = flags
            shape.group_id = group_id
            shape.description = description
            shape.difficult = difficult
            shape.kie_linking = kie_linking

            self._update_shape_color(shape)

            item = self.label_list.find_item_by_shape(shape)
            if item is not None:
                if shape.group_id is None:
                    color = shape.fill_color.getRgb()[:3]
                    item.setText(
                        _format_label_list_text(shape.label, shape.group_id)
                    )
                    item.setBackground(QtGui.QColor(*color, LABEL_OPACITY))
                else:
                    item.setText(
                        _format_label_list_text(shape.label, shape.group_id)
                    )

        self.label_dialog.add_label_history(text)

        if not self.unique_label_list.find_items_by_label(text):
            unique_label_item = self.unique_label_list.create_item_from_label(
                text
            )
            self.unique_label_list.addItem(unique_label_item)
            rgb = self._get_rgb_by_label(text)
            self.unique_label_list.set_item_label(
                unique_label_item, text, rgb, LABEL_OPACITY
            )

        # The confirmation dialog promises "You can undo this with Ctrl+Z";
        # keep that promise by snapshotting the new state (see
        # Canvas.is_shape_restorable for why this happens after the edit).
        if any(
            before != _shape_editable_state(shape)
            for before, shape in zip(states_before, shapes)
        ):
            self.canvas.store_shapes()
        self.set_dirty()
        self._refresh_shape_filters()

    def edit_label(self, item=None):
        if item and not isinstance(item, LabelListWidgetItem):
            raise TypeError("item must be LabelListWidgetItem type")

        if not self.canvas.editing():
            return

        selected_shapes = self.canvas.selected_shapes
        if not selected_shapes:
            return

        if len(selected_shapes) > 1:
            return self.batch_edit_labels(selected_shapes)

        if not item:
            item = self.current_item()
        if item is None:
            return
        shape = item.shape()
        if shape is None:
            return
        (
            text,
            flags,
            group_id,
            description,
            difficult,
            kie_linking,
        ) = self.label_dialog.pop_up(
            text=shape.label,
            flags=shape.flags,
            group_id=shape.group_id,
            description=shape.description,
            difficult=shape.difficult,
            kie_linking=shape.kie_linking,
            move_mode=self._config.get("move_mode", "auto"),
        )
        if text is None:
            return
        if not self.validate_label(text):
            self.error_message(
                self.tr("Invalid label"),
                self.tr("Invalid label '{}' with validation type '{}'").format(
                    text, self._config["validate_label"]
                ),
            )
            return
        if self.attributes and text and text != shape.label:
            text = self.reset_attribute(text, shape)
        state_before = _shape_editable_state(shape)
        shape.label = text
        shape.flags = flags
        shape.group_id = group_id
        shape.description = description
        shape.difficult = difficult
        shape.kie_linking = kie_linking

        # Add to label history
        self.label_dialog.add_label_history(shape.label)

        # Update last group_id
        if group_id is not None:
            self.label_dialog._last_gid = group_id

        # Update unique label list
        if not self.unique_label_list.find_items_by_label(shape.label):
            unique_label_item = self.unique_label_list.create_item_from_label(
                shape.label
            )
            self.unique_label_list.addItem(unique_label_item)
            rgb = self._get_rgb_by_label(shape.label)
            self.unique_label_list.set_item_label(
                unique_label_item, shape.label, rgb, LABEL_OPACITY
            )

        self._update_shape_color(shape)
        if shape.group_id is None:
            color = shape.fill_color.getRgb()[:3]
            item.setText(_format_label_list_text(shape.label, shape.group_id))
            item.setBackground(QtGui.QColor(*color, LABEL_OPACITY))
        else:
            item.setText(_format_label_list_text(shape.label, shape.group_id))
        # The canvas saves the state AFTER each edit (see
        # Canvas.is_shape_restorable), so the snapshot has to happen here --
        # after the new values are in place. Without it a mistaken label was
        # permanent: edit_label only marked the file dirty.
        if state_before != _shape_editable_state(shape):
            self.canvas.store_shapes()
        self.set_dirty()
        self._refresh_shape_filters()

        # update top-right attributes panel
        selected_idx = self.canvas.shapes.index(selected_shapes[0])
        self.update_attributes(selected_idx)

    def _on_file_item_changed(self, item):
        """Keep annotation flag in sync when the checkbox is toggled.

        Note: QListWidgetItem.setData()/setIcon() emit itemChanged()
        unconditionally (even when the value is unchanged), so this slot
        MUST NOT mutate the item without a re-entrancy guard, otherwise a
        programmatic data/icon update during folder load recurses into
        itself until RecursionError crashes the app. Items that are not
        user-checkable have no checkbox to toggle, so we skip them too
        (their FILE_ANNOTATION_ROLE is owned by the loader).
        """
        if getattr(self, "_syncing_file_item", False):
            return
        if not (item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            return
        self._syncing_file_item = True
        try:
            item.setData(
                FILE_ANNOTATION_ROLE,
                item.checkState() == Qt.CheckState.Checked,
            )
            self._refresh_file_item_status_icon(item)
            self._refresh_file_progress()
        finally:
            self._syncing_file_item = False

    def _apply_file_filter(self):
        """Hide/show file rows according to the status combo (all/annotated/unannotated)."""
        mode = self.file_filter_combo.currentData()
        total = 0
        for row in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(row)
            annotated = bool(item.data(FILE_ANNOTATION_ROLE))
            checked = self._file_item_annotation_checked(item)
            if mode == "annotated":
                visible = annotated
            elif mode == "unannotated":
                visible = not annotated
            elif mode == "checked":
                visible = checked
            elif mode == "rework":
                visible = (
                    item.data(FILE_REVIEW_ROLE) == REVIEW_REJECTED
                )
            elif mode == "low_conf":
                visible = self._file_item_has_low_conf(item)
            else:
                visible = True
            item.setHidden(not visible)
            if visible:
                total += 1
        self._refresh_file_progress()

    def _refresh_file_progress(self):
        """Update the annotation progress summary label."""
        total = self.file_list_widget.count()
        annotated = 0
        checked = 0
        review = 0
        rework = 0
        for row in range(total):
            item = self.file_list_widget.item(row)
            if bool(item.data(FILE_ANNOTATION_ROLE)):
                annotated += 1
            if self._file_item_annotation_checked(item):
                checked += 1
            if self._file_item_has_low_conf(item):
                review += 1
            if item.data(FILE_REVIEW_ROLE) == REVIEW_REJECTED:
                rework += 1
        if total <= 0:
            self.file_progress_label.setText("")
            return
        first_line = (
            self.tr("已标 %1/%2 · 已检查 %3 · 待复核 %4 · 需返工 %5")
            .replace("%1", str(annotated))
            .replace("%2", str(total))
            .replace("%3", str(checked))
            .replace("%4", str(review))
            .replace("%5", str(rework))
        )
        threshold_text = (
            self.tr("已校准阈值")
            if self._load_active_thresholds()
            else self.tr("默认阈值")
        )
        filter_text = self.file_filter_combo.currentText()
        second_line = self.tr("筛选：%1 · 阈值来源：%2").replace(
            "%1", filter_text
        ).replace("%2", threshold_text)
        self.file_progress_label.setText(f"{first_line}\n{second_line}")

    def _refresh_file_panel(self):
        self._apply_file_filter()

    def _smart_tools_guide_message(self):
        threshold_text = (
            self.tr("已检测到当前文件夹的校准阈值。")
            if self._load_active_thresholds()
            else self.tr("当前仍在使用默认阈值，建议先跑一次阈值校准。")
        )
        return self.tr(
            "推荐顺序：1 阈值校准 → 2 数据智能分析 → 3 漏标扫描 → 4 迭代收益看板。"
        ) + "\n" + threshold_text

    def _maybe_show_smart_tools_guide(self, directory):
        if not directory:
            return
        thresholds = self._load_active_thresholds()
        signature = (
            osp.abspath(directory),
            "calibrated" if thresholds else "default",
        )
        if getattr(self, "_smart_tools_guide_signature", None) == signature:
            return
        self._smart_tools_guide_signature = signature
        popup = Popup(
            self._smart_tools_guide_message(),
            parent=self,
            msec=4800,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=72, position="bottom")

    def file_search_changed(self):
        search_text = self.file_search.text()
        self.import_image_folder(
            self.last_open_dir,
            pattern=search_text,
            load=False,
        )
        self._refresh_file_panel()

    def file_selection_changed(self):
        items = self.file_list_widget.selectedItems()
        if not items:
            return
        item = items[0]

        if not self.may_continue(silent=True):
            return

        current_index = self.fn_to_index[str(item.text())]
        if current_index < len(self.image_list):
            filename = self.image_list[current_index]
            if filename:
                self.load_file(filename)
                if self.attributes:
                    # Clear the history widgets from the QGridLayout
                    self.grid_layout = QGridLayout()
                    self.grid_layout_container = QWidget()
                    self.grid_layout_container.setLayout(self.grid_layout)
                    self.scroll_area.setWidget(self.grid_layout_container)
                    self.scroll_area.setWidgetResizable(True)
                    # Create a container widget for the grid layout
                    self.grid_layout_container = QWidget()
                    self.grid_layout_container.setLayout(self.grid_layout)
                    self.scroll_area.setWidget(self.grid_layout_container)

    def attribute_selection_changed(self, i, property, combo):
        selected_option = combo.currentText()
        tooltip = combo.currentData(Qt.ItemDataRole.ToolTipRole)
        combo.setToolTip(tooltip or "")
        if _apply_attribute_change(self, i, property, selected_option):
            self.save_attributes(self.canvas.shapes)

    def attribute_radio_changed(self, i, property, option, checked):
        if checked and _apply_attribute_change(self, i, property, option):
            self.save_attributes(self.canvas.shapes)

    def attribute_line_changed(self, i, property, line: QLineEdit):
        if _apply_attribute_change(self, i, property, line.text()):
            self.save_attributes(self.canvas.shapes)

    def update_selected_options(self, selected_options):
        if not isinstance(selected_options, dict):
            return

        row_count = self.grid_layout.rowCount()
        for row in range(row_count):
            category_label = None
            property_widget = None
            if self.grid_layout.itemAtPosition(row, 0):
                category_label = self.grid_layout.itemAtPosition(
                    row, 0
                ).widget()
            if self.grid_layout.itemAtPosition(row, 1):
                property_widget = self.grid_layout.itemAtPosition(
                    row, 1
                ).widget()
            if category_label and property_widget:
                category = category_label.text()
                if category in selected_options:
                    selected_option = selected_options[category]

                    if isinstance(property_widget, QComboBox):
                        index = property_widget.findText(selected_option)
                        if index >= 0:
                            property_widget.setCurrentIndex(index)
                    elif isinstance(property_widget, QWidget):
                        for child in property_widget.findChildren(
                            QRadioButton
                        ):
                            if child.text() == selected_option:
                                child.setChecked(True)
                                break
        return

    def update_attributes(self, shape_index):
        if shape_index >= len(self.canvas.shapes) or shape_index < 0:
            self.hide_attributes_panel()
            return

        update_shape = self.canvas.shapes[shape_index]
        update_category = update_shape.label
        if update_category not in self.attributes:
            self.hide_attributes_panel()
            return

        current_attibute = self.attributes[update_category]
        if not update_shape.attributes:
            update_shape.attributes = {}
        attributes_changed = False

        self.grid_layout = QGridLayout()
        row_counter = 0

        def unknown_value_tooltip(value):
            return self.tr(
                "Value '{}' is not defined in the current attribute "
                "configuration."
            ).format(value)

        def set_current_combo_value(combo, value):
            value = str(value)
            index = combo.findText(value)
            if index < 0:
                combo.addItem(value)
                index = combo.count() - 1
                tooltip = unknown_value_tooltip(value)
                combo.setItemData(index, tooltip, Qt.ItemDataRole.ToolTipRole)
                combo.setToolTip(tooltip)
            combo.setCurrentIndex(index)

        for property, options in current_attibute.items():
            widget_type = self.attribute_widget_types.get(
                update_category, {}
            ).get(property, "combobox")
            has_current_value = property in update_shape.attributes
            current_value = update_shape.attributes.get(property)
            current_value_text = (
                str(current_value) if has_current_value else None
            )
            if hasattr(self, "grid_layout_container"):
                font_metrics = QFontMetrics(self.grid_layout_container.font())
            else:
                font_metrics = QFontMetrics(QLabel().font())
            available_width = self.scroll_area.width() - 30
            property_display = property
            if _measure_text_width(font_metrics, property) > available_width:
                while (
                    _measure_text_width(font_metrics, property_display + "...")
                    > available_width
                    and len(property_display) > 1
                ):
                    property_display = property_display[:-1]
                property_display += "..."

            property_label = QLabel(property_display)
            if property_display != property:
                property_label.setToolTip(property)

            self.grid_layout.addWidget(property_label, row_counter, 0, 1, 2)
            row_counter += 1

            if widget_type == "radiobutton":
                radio_options = list(options)
                unknown_radio_value = None
                if (
                    has_current_value
                    and current_value_text not in radio_options
                ):
                    unknown_radio_value = current_value_text
                    radio_options.append(unknown_radio_value)
                radio_container = QWidget()
                radio_group = QButtonGroup(radio_container)
                main_layout = QVBoxLayout()
                main_layout.setContentsMargins(0, 0, 0, 0)
                main_layout.setSpacing(2)

                def get_truncated_text(text, max_width):
                    if _measure_text_width(font_metrics, text) <= max_width:
                        return text, text
                    truncated = text
                    while (
                        _measure_text_width(font_metrics, truncated + "...")
                        > max_width
                        and len(truncated) > 1
                    ):
                        truncated = truncated[:-1]
                    return truncated + "...", text

                def get_button_width(text):
                    return _measure_text_width(font_metrics, text) + 30

                def create_radio_button_with_handler(
                    display_text, original_text, prop, shape_idx
                ):
                    radio_button = QRadioButton(display_text)
                    if original_text == unknown_radio_value:
                        radio_button.setToolTip(
                            unknown_value_tooltip(original_text)
                        )
                    elif display_text != original_text:
                        radio_button.setToolTip(original_text)
                    radio_group.addButton(radio_button)

                    def handler(checked):
                        if checked:
                            self.attribute_radio_changed(
                                shape_idx, prop, original_text, checked
                            )

                    radio_button.toggled.connect(handler)
                    return radio_button

                buttons_data = []
                for option in radio_options:
                    display_text, original_text = get_truncated_text(
                        option, available_width
                    )
                    button_width = get_button_width(display_text)
                    buttons_data.append(
                        (display_text, original_text, button_width)
                    )

                current_row_buttons = []
                current_row_width = 0

                idx = 0
                while idx < len(buttons_data):
                    display_text, original_text, button_width = buttons_data[
                        idx
                    ]

                    if not current_row_buttons:
                        current_row_buttons.append(
                            (display_text, original_text)
                        )
                        current_row_width = button_width
                        idx += 1
                        continue

                    if current_row_width + button_width <= available_width:
                        current_row_buttons.append(
                            (display_text, original_text)
                        )
                        current_row_width += button_width
                        idx += 1
                    else:
                        if len(current_row_buttons) == 1:
                            (
                                first_display,
                                first_original,
                            ) = current_row_buttons[0]
                            first_truncated, _ = get_truncated_text(
                                first_original, available_width - button_width
                            )
                            first_truncated_width = get_button_width(
                                first_truncated
                            )

                            if (
                                first_truncated_width + button_width
                                <= available_width
                            ):
                                current_row_buttons = [
                                    (first_truncated, first_original),
                                    (display_text, original_text),
                                ]
                                current_row_width = (
                                    first_truncated_width + button_width
                                )
                                idx += 1
                            else:
                                row_layout = QHBoxLayout()
                                row_layout.setContentsMargins(0, 0, 0, 0)
                                row_layout.setSpacing(4)

                                for (
                                    btn_display,
                                    btn_original,
                                ) in current_row_buttons:
                                    radio_button = (
                                        create_radio_button_with_handler(
                                            btn_display,
                                            btn_original,
                                            property,
                                            shape_index,
                                        )
                                    )
                                    row_layout.addWidget(radio_button)
                                    if current_value_text == btn_original or (
                                        not has_current_value
                                        and btn_original == options[0]
                                    ):
                                        blocker = QtCore.QSignalBlocker(
                                            radio_button
                                        )
                                        radio_button.setChecked(True)
                                        del blocker
                                        if not has_current_value:
                                            update_shape.attributes[
                                                property
                                            ] = btn_original
                                            attributes_changed = True

                                row_layout.addStretch()
                                row_widget = QWidget()
                                row_widget.setLayout(row_layout)
                                main_layout.addWidget(row_widget)

                                current_row_buttons = []
                                current_row_width = 0
                                continue
                        else:
                            row_layout = QHBoxLayout()
                            row_layout.setContentsMargins(0, 0, 0, 0)
                            row_layout.setSpacing(4)
                            for (
                                btn_display,
                                btn_original,
                            ) in current_row_buttons:
                                radio_button = (
                                    create_radio_button_with_handler(
                                        btn_display,
                                        btn_original,
                                        property,
                                        shape_index,
                                    )
                                )
                                row_layout.addWidget(radio_button)
                                if current_value_text == btn_original or (
                                    not has_current_value
                                    and btn_original == options[0]
                                ):
                                    blocker = QtCore.QSignalBlocker(
                                        radio_button
                                    )
                                    radio_button.setChecked(True)
                                    del blocker
                                    if not has_current_value:
                                        update_shape.attributes[property] = (
                                            btn_original
                                        )
                                        attributes_changed = True

                            row_layout.addStretch()
                            row_widget = QWidget()
                            row_widget.setLayout(row_layout)
                            main_layout.addWidget(row_widget)

                            current_row_buttons = []
                            current_row_width = 0
                            continue

                if current_row_buttons:
                    row_layout = QHBoxLayout()
                    row_layout.setContentsMargins(0, 0, 0, 0)
                    row_layout.setSpacing(4)
                    for btn_display, btn_original in current_row_buttons:
                        radio_button = create_radio_button_with_handler(
                            btn_display, btn_original, property, shape_index
                        )
                        row_layout.addWidget(radio_button)
                        if current_value_text == btn_original or (
                            not has_current_value
                            and btn_original == options[0]
                        ):
                            blocker = QtCore.QSignalBlocker(radio_button)
                            radio_button.setChecked(True)
                            del blocker
                            if not has_current_value:
                                update_shape.attributes[property] = (
                                    btn_original
                                )
                                attributes_changed = True
                    row_layout.addStretch()
                    row_widget = QWidget()
                    row_widget.setLayout(row_layout)
                    main_layout.addWidget(row_widget)

                radio_container.setLayout(main_layout)
                self.grid_layout.addWidget(
                    radio_container, row_counter, 0, 1, 2
                )
                row_counter += 1
            elif widget_type == "group_id":
                property_combo = QComboBox()
                options = [""] + sorted(
                    {
                        str(obj.group_id)
                        for obj in self.canvas.shapes
                        if obj.group_id is not None
                    }
                )
                property_combo.addItems(options)
                if has_current_value:
                    set_current_combo_value(property_combo, current_value)
                property_combo.currentIndexChanged.connect(
                    lambda _, prop=property, combo=property_combo, shape_idx=shape_index: self.attribute_selection_changed(
                        shape_idx, prop, combo
                    )
                )
                self.grid_layout.addWidget(
                    property_combo, row_counter, 0, 1, 2
                )
                row_counter += 1
            elif widget_type == "lineedit":
                property_line = QLineEdit()
                if has_current_value:
                    property_line.setText(current_value_text)
                property_line.textChanged.connect(
                    lambda _, prop=property, line=property_line, shape_idx=shape_index: self.attribute_line_changed(
                        shape_idx, prop, line
                    )
                )
                self.grid_layout.addWidget(property_line, row_counter, 0, 1, 2)
                row_counter += 1
            else:
                property_combo = QComboBox()
                property_combo.addItems(options)
                if has_current_value:
                    set_current_combo_value(property_combo, current_value)
                else:
                    update_shape.attributes[property] = options[0]
                    attributes_changed = True
                property_combo.currentIndexChanged.connect(
                    lambda _, prop=property, combo=property_combo, shape_idx=shape_index: self.attribute_selection_changed(
                        shape_idx, prop, combo
                    )
                )
                self.grid_layout.addWidget(
                    property_combo, row_counter, 0, 1, 2
                )
                row_counter += 1

        self.grid_layout_container = QWidget()
        self.grid_layout_container.setLayout(self.grid_layout)
        self.scroll_area.setWidget(self.grid_layout_container)
        self.scroll_area.setWidgetResizable(True)
        if shape_index < len(self.canvas.shapes):
            self.canvas.shapes[shape_index] = update_shape
            if attributes_changed:
                self.save_attributes(self.canvas.shapes)
        self.show_attributes_panel()

    def show_attributes_panel(self):
        if hasattr(self, "scroll_area"):
            self.scroll_area.setVisible(True)

    def hide_attributes_panel(self):
        if hasattr(self, "scroll_area"):
            self.scroll_area.setVisible(False)

    def save_attributes(self, _shapes):
        filename = osp.splitext(self.image_path)[0] + ".json"
        if self.output_dir:
            label_file_without_path = osp.basename(filename)
            filename = osp.join(self.output_dir, label_file_without_path)
        label_file = LabelFile()

        # Get current shapes
        # Excluding auto labeling special shapes
        shapes = [
            shape.to_dict()
            for shape in _shapes
            if shape.label
            not in [
                AutoLabelingMode.OBJECT,
                AutoLabelingMode.ADD,
                AutoLabelingMode.REMOVE,
            ]
        ]
        flags = {}
        for i in range(self.flag_widget.count()):
            item = self.flag_widget.item(i)
            key = item.text()
            flag = item.checkState() == Qt.CheckState.Checked
            flags[key] = flag
        self.other_data[CHECKED_FIELD] = self._annotation_checked()
        try:
            image_path = osp.relpath(self.image_path, osp.dirname(filename))
            image_data = (
                self.image_data if self._config["store_data"] else None
            )
            if osp.dirname(filename) and not osp.exists(osp.dirname(filename)):
                os.makedirs(osp.dirname(filename))
            label_file.save(
                filename=filename,
                shapes=shapes,
                image_path=image_path,
                image_data=image_data,
                image_height=self.image.height(),
                image_width=self.image.width(),
                other_data=self.other_data,
                flags=flags,
            )
            write_sidecar = getattr(self, "_write_yolo_sidecar", None)
            if write_sidecar is not None:
                write_sidecar(filename, shapes)
            self.label_file = label_file
            items = self.file_list_widget.findItems(
                self.image_path, Qt.MatchFlag.MatchExactly
            )
            if len(items) > 0:
                if len(items) != 1:
                    raise RuntimeError("There are duplicate files.")
                self._set_file_item_annotated(
                    items[0], True, negative=not shapes
                )
                self._set_file_item_checked(
                    items[0], self._annotation_checked()
                )
                note_quality = getattr(self, "_note_save_quality", None)
                if note_quality is not None:
                    note_quality(shapes, items[0])
            else:
                note_quality = getattr(self, "_note_save_quality", None)
                if note_quality is not None:
                    note_quality(shapes)
            # Defensive refresh: tests may use a lightweight mock widget.
            refresh_progress = getattr(self, "_refresh_file_progress", None)
            if refresh_progress is not None:
                refresh_progress()
            refresh_labels = getattr(self, "_refresh_label_panel", None)
            if refresh_labels is not None:
                refresh_labels()
            # disable allows next and previous image to proceed
            # self.filename = filename
            return True
        except LabelFileError as e:
            self.error_message(
                self.tr("Error saving label data"), self.tr("<b>%s</b>") % e
            )
            return False

    # React to canvas signals.
    def shape_selection_changed(self, selected_shapes):
        if self.canvas.is_brush_mode:
            target = self.canvas._brush_target_shape
            if selected_shapes != [target]:
                self._no_selection_slot = True
                self.label_list.clearSelection()
                item = self.label_list.find_item_by_shape(target)
                if item is not None:
                    self.label_list.select_item(item)
                    self.label_list.scroll_to_item(item)
                self._no_selection_slot = False
                return
        self._no_selection_slot = True
        for shape in self.canvas.selected_shapes:
            shape.selected = False
        self.label_list.clearSelection()
        self.canvas.selected_shapes = selected_shapes
        allow_merge_shape_type = {"rectangle": 0, "polygon": 0}
        for shape in self.canvas.selected_shapes:
            shape.selected = True
            if shape.shape_type in ["rectangle", "polygon"]:
                allow_merge_shape_type[shape.shape_type] += 1
            item = self.label_list.find_item_by_shape(shape)
            # NOTE: Handle the case when the shape is not found
            if item is not None:
                self.label_list.select_item(item)
                self.label_list.scroll_to_item(item)
        self._no_selection_slot = False
        n_selected = len(selected_shapes)
        same_type = (
            len(set(shape.shape_type for shape in selected_shapes)) <= 1
        )
        has_locked = any(shape.locked for shape in selected_shapes)
        has_unlocked = any(not shape.locked for shape in selected_shapes)
        group_shapes = self.canvas._active_group_shapes()
        self.actions.delete.setEnabled(
            has_unlocked and not (group_shapes and has_locked)
        )
        self.actions.duplicate.setEnabled(n_selected)
        self.actions.copy.setEnabled(n_selected)
        self.actions.edit.setEnabled(n_selected >= 1 and same_type)
        self.actions.copy_coordinates.setEnabled(n_selected == 1)
        can_brush_edit = (
            n_selected == 1
            and selected_shapes[0].shape_type == "polygon"
            and not selected_shapes[0].locked
        )
        self.actions.edit_brush_mode.setEnabled(can_brush_edit)
        self.actions.union_selection.setEnabled(
            not has_locked
            and not all(value > 0 for value in allow_merge_shape_type.values())
            and (
                allow_merge_shape_type["rectangle"] > 1
                or allow_merge_shape_type["polygon"] > 1
            )
        )
        self.refresh_shape_lock_action()

        selected_count = len(self.canvas.selected_shapes)
        is_drawing_mode = (
            hasattr(self.canvas, "current") and self.canvas.current is not None
        )
        if self.attributes and selected_count == 1 and not is_drawing_mode:
            for i in range(len(self.canvas.shapes)):
                if self.canvas.shapes[i].selected:
                    self.update_attributes(i)
                    break
        else:
            self.hide_attributes_panel()

    def add_label(self, shape, update_last_label=True, refresh_filters=True):
        if shape.group_id is None:
            text = shape.label
        else:
            text = f"{shape.label} ({shape.group_id})"
        label_list_item = LabelListWidgetItem(text, shape)
        label_list_item.set_tooltip_provider(self._shape_tooltip)
        self.label_list.add_iem(label_list_item)
        if not self.unique_label_list.find_items_by_label(shape.label):
            item = self.unique_label_list.create_item_from_label(shape.label)
            self.unique_label_list.addItem(item)
            rgb = self._get_rgb_by_label(shape.label)
            self.unique_label_list.set_item_label(
                item, shape.label, rgb, LABEL_OPACITY
            )

        if shape.label not in self.label_info:
            rgb = self._get_rgb_by_label(shape.label)
            self.label_info[shape.label] = dict(
                delete=False,
                value=None,
                color=list(rgb),
                opacity=LABEL_OPACITY,
                visible=True,
            )

        # Add label to history if it is not a special label
        if shape.label not in [
            AutoLabelingMode.OBJECT,
            AutoLabelingMode.ADD,
            AutoLabelingMode.REMOVE,
        ]:
            self.label_dialog.add_label_history(
                shape.label, update_last_label=update_last_label
            )
            if update_last_label and shape.group_id is not None:
                self.label_dialog._last_gid = shape.group_id

        for action in self.actions.on_shapes_present:
            action.setEnabled(True)

        self._update_shape_color(shape)
        color = shape.fill_color.getRgb()[:3]
        label_list_item.setText(
            _format_label_list_text(shape.label, shape.group_id)
        )
        _set_label_list_item_lock(label_list_item, shape.locked)
        label_list_item.setBackground(QtGui.QColor(*color, LABEL_OPACITY))
        if refresh_filters:
            self._refresh_shape_filters()

    def load_labels(self, labels, clear_existing=True):
        """
        Load labels to the unique label list widget.

        Args:
            labels (list): List of label names to load
            clear_existing (bool): Whether to clear existing labels before loading new ones
        """
        if not labels:
            return

        if clear_existing:
            self.unique_label_list.clear()

        for label in labels:
            # Check if label already exists to avoid duplicates
            if not self.unique_label_list.find_items_by_label(label):
                item = self.unique_label_list.create_item_from_label(label)
                self.unique_label_list.addItem(item)
                rgb = self._get_rgb_by_label(label)
                self.unique_label_list.set_item_label(
                    item, label, rgb, LABEL_OPACITY
                )

    def _update_shape_color(self, shape):
        r, g, b = self._get_rgb_by_label(shape.label)
        shape.line_color = QtGui.QColor(r, g, b)
        shape.vertex_fill_color = QtGui.QColor(r, g, b)
        shape.hvertex_fill_color = QtGui.QColor(255, 255, 255)
        shape.fill_color = QtGui.QColor(r, g, b, 128)
        shape.select_line_color = QtGui.QColor(255, 255, 255)
        shape.select_fill_color = QtGui.QColor(r, g, b, 155)

    def _get_rgb_by_label(self, label, skip_label_info=False):
        if label == "AUTOLABEL_ADD":
            return (144, 238, 144)
        if label == "AUTOLABEL_REMOVE":
            return (255, 182, 193)
        if label in self.label_info and not skip_label_info:
            return tuple(self.label_info[label]["color"])
        if self._config["shape_color"] == "auto":
            items = self.unique_label_list.find_items_by_label(label)
            if not items:
                item = self.unique_label_list.create_item_from_label(label)
                self.unique_label_list.addItem(item)
                items = [item]
            item = items[0]
            label_id = self.unique_label_list.indexFromItem(item).row() + 1
            label_id += self._runtime_shape_color_shift
            return LABEL_COLORMAP[label_id % len(LABEL_COLORMAP)]
        if (
            self._config["shape_color"] == "manual"
            and self._config["label_colors"]
            and label in self._config["label_colors"]
        ):
            return self._config["label_colors"][label]
        if self._config["default_shape_color"]:
            return self._config["default_shape_color"]
        return (0, 255, 0)

    def remove_labels(self, shapes):
        for shape in shapes:
            item = self.label_list.find_item_by_shape(shape)
            self.label_list.remove_item(item)
        self._refresh_shape_filters()
        self._refresh_label_panel()

    def on_canvas_shapes_deleted(self, shapes):
        self.remove_labels(shapes)
        self.set_dirty()
        if self.no_shape():
            for action in self.actions.on_shapes_present:
                action.setEnabled(False)

    def load_shapes(self, shapes, replace=True, update_last_label=True):
        self._no_selection_slot = True
        self.label_list.setUpdatesEnabled(False)
        try:
            for shape in shapes:
                self.add_label(
                    shape,
                    update_last_label=update_last_label,
                    refresh_filters=False,
                )
            self.label_list.clearSelection()
        finally:
            self.label_list.setUpdatesEnabled(True)
            self._no_selection_slot = False
        self.canvas.load_shapes(shapes, replace=replace)
        self._refresh_shape_filters()
        self._refresh_label_panel()
        self._auto_assign_digit_shortcuts(shapes)

    def _auto_assign_digit_shortcuts(self, shapes):
        """Delegates to shortcuts.digit_controller (load_shapes tail)."""
        self.digit_shortcut_controller.auto_assign_digit_shortcuts(shapes)

    def load_flags(self, flags):
        self.flag_widget.clear()
        for key, flag in flags.items():
            item = QtWidgets.QListWidgetItem(key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if flag else Qt.CheckState.Unchecked
            )
            self.flag_widget.addItem(item)

    def _sync_label_list_visibility(self, get_visible):
        model = self.label_list.model()
        blocker = QtCore.QSignalBlocker(model)
        self.label_list.setUpdatesEnabled(False)
        try:
            for item in self.label_list:
                is_visible = bool(get_visible(item))
                check_state = (
                    Qt.CheckState.Checked
                    if is_visible
                    else Qt.CheckState.Unchecked
                )
                if item.checkState() != check_state:
                    item.setCheckState(check_state)
                shape = item.shape()
                shape.visible = is_visible
                self.canvas.visible[shape] = is_visible
        finally:
            self.label_list.setUpdatesEnabled(True)
            del blocker
        self.canvas.update()
        self._update_select_toggle_button_tooltip()
        if (
            hasattr(self, "navigator_dialog")
            and self.navigator_dialog.isVisible()
        ):
            self.update_navigator_shapes()

    def _refresh_shape_filters(self):
        self.update_combo_box(block_signal=True)
        self.update_gid_box(block_signal=True)
        current_gid = self.gid_filter_combobox.gid_box.currentText()
        if current_gid and current_gid != "-1":
            self.gid_selection_changed(
                self.gid_filter_combobox.gid_box.currentIndex()
            )
            return
        current_label = self.label_filter_combobox.text_box.currentText()
        if current_label:
            self.text_selection_changed(
                self.label_filter_combobox.text_box.currentIndex()
            )
            return
        self.apply_label_visibility()

    def apply_label_visibility(self):
        self._sync_label_list_visibility(
            lambda item: self.label_info.get(item.shape().label, {}).get(
                "visible", True
            )
        )

    def update_combo_box(self, block_signal=False):
        current_label = self.label_filter_combobox.text_box.currentText()

        # Get the unique labels and add them to the Combobox.
        labels_list = []
        for item in self.label_list:
            label = item.shape().label
            labels_list.append(str(label))
        unique_labels_list = list(set(labels_list))

        # Add a null row for showing all the labels
        unique_labels_list.append("")
        unique_labels_list.sort()
        blocker = None
        if block_signal:
            blocker = QtCore.QSignalBlocker(
                self.label_filter_combobox.text_box
            )
        self.label_filter_combobox.update_items(unique_labels_list)
        if current_label in unique_labels_list:
            self.set_label_filter_value(
                current_label, block_signal=block_signal
            )
        else:
            self.set_label_filter_value("", block_signal=block_signal)
        del blocker

    def update_gid_box(self, block_signal=False):
        current_gid = self.gid_filter_combobox.gid_box.currentText()

        # Get the unique group ids and add them to the Combobox.
        gid_list = []
        for item in self.label_list:
            gid = item.shape().group_id
            if gid is not None:
                gid_list.append(str(gid))
        unique_gid_list = list(set(gid_list))

        # Add a null row for showing all the labels
        unique_gid_list.append("-1")
        unique_gid_list.sort()
        blocker = None
        if block_signal:
            blocker = QtCore.QSignalBlocker(self.gid_filter_combobox.gid_box)
        self.gid_filter_combobox.update_items(unique_gid_list)
        if current_gid in unique_gid_list:
            self.set_gid_filter_value(current_gid, block_signal=block_signal)
        else:
            self.set_gid_filter_value("-1", block_signal=block_signal)
        del blocker

    def save_labels(self, filename):
        label_file = LabelFile()
        # Get current shapes
        # Excluding auto labeling special shapes
        shapes = [
            item.shape().to_dict()
            for item in self.label_list
            if item.shape().label
            not in [
                AutoLabelingMode.OBJECT,
                AutoLabelingMode.ADD,
                AutoLabelingMode.REMOVE,
            ]
        ]
        flags = {}
        for i in range(self.flag_widget.count()):
            item = self.flag_widget.item(i)
            key = item.text()
            flag = item.checkState() == Qt.CheckState.Checked
            flags[key] = flag
        self.other_data[CHECKED_FIELD] = self._annotation_checked()
        try:
            image_path = osp.relpath(self.image_path, osp.dirname(filename))
            image_data = (
                self.image_data if self._config["store_data"] else None
            )
            if osp.dirname(filename) and not osp.exists(osp.dirname(filename)):
                os.makedirs(osp.dirname(filename))

            label_file.save(
                filename=filename,
                shapes=shapes,
                image_path=image_path,
                image_data=image_data,
                image_height=self.image.height(),
                image_width=self.image.width(),
                other_data=self.other_data,
                flags=flags,
            )
            write_sidecar = getattr(self, "_write_yolo_sidecar", None)
            if write_sidecar is not None:
                write_sidecar(filename, shapes)
            self.label_file = label_file
            items = self.file_list_widget.findItems(
                self.image_path, Qt.MatchFlag.MatchExactly
            )
            if len(items) > 0:
                if len(items) != 1:
                    raise RuntimeError("There are duplicate files.")
                self._set_file_item_annotated(
                    items[0], True, negative=not shapes
                )
                self._set_file_item_checked(
                    items[0], self._annotation_checked()
                )
                self._note_save_quality(shapes, items[0])
            else:
                self._note_save_quality(shapes)
            # disable allows next and previous image to proceed
            # self.filename = filename
            return True
        except LabelFileError as e:
            self.error_message(
                self.tr("Error saving label data"), self.tr("<b>%s</b>") % e
            )
            return False

    def _yolo_class_names(self):
        """Class names for YOLO ids: Labels dock first, then config."""
        names = []
        unique_list = getattr(self, "unique_label_list", None)
        if unique_list is not None:
            for row in range(unique_list.count()):
                item = unique_list.item(row)
                if item is None:
                    continue
                names.append(item.data(Qt.ItemDataRole.UserRole))
        config = getattr(self, "_config", None) or {}
        return merge_class_names(names, config.get("labels") or [])

    def _write_yolo_sidecar(self, filename, shapes):
        image = getattr(self, "image", None)
        image_width = image.width() if image is not None else 0
        image_height = image.height() if image is not None else 0
        try:
            write_yolo_detect_sidecar(
                filename,
                shapes,
                image_width,
                image_height,
                extra_class_names=self._yolo_class_names(),
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to write YOLO txt for {filename}: {e}")

    def duplicate_selected_shape(self):
        added_shapes = self.canvas.duplicate_selected_shapes()
        self.label_list.clearSelection()
        self.label_list.setUpdatesEnabled(False)
        try:
            for shape in added_shapes:
                self.add_label(shape, refresh_filters=False)
        finally:
            self.label_list.setUpdatesEnabled(True)
        if added_shapes:
            self._refresh_shape_filters()
        self.set_dirty()
        self._refresh_label_panel()

    def paste_selected_shape(self):
        if self._config["system_clipboard"]:
            clipboard = QtWidgets.QApplication.clipboard()
            json_str = clipboard.text()
            shapes = []
            try:
                shapeDicts = json.loads(json_str)
                for shapeDict in shapeDicts:
                    shapes.append(Shape().load_from_dict(shapeDict))
            except json.JSONDecodeError as e:
                self.error_message(
                    self.tr("Error pasting shapes"),
                    self.tr("Error decoding shapes: %s") % str(e),
                )
                return
        else:
            shapes = self._copied_shapes
        shapes = self.canvas.prepare_pasted_shapes(
            shapes, self._copied_group_id
        )
        self.load_shapes(shapes, replace=False)
        self.set_dirty()

    def toggle_system_clipboard(self, system_clipboard):
        self._config["system_clipboard"] = system_clipboard
        self.actions.paste.setEnabled(
            bool(system_clipboard or self._copied_shapes)
        )

    def copy_selected_shape(self):
        group_shapes = self.canvas._active_group_shapes()
        self._copied_group_id = (
            self.canvas._selected_group_id if group_shapes else None
        )
        if self._config["system_clipboard"]:
            clipboard = QtWidgets.QApplication.clipboard()
            clipboard.setText(
                json.dumps([s.to_dict() for s in self.canvas.selected_shapes])
            )
        else:
            self._copied_shapes = [
                s.copy() for s in self.canvas.selected_shapes
            ]
            self.actions.paste.setEnabled(len(self._copied_shapes) > 0)

    def text_selection_changed(self, index):
        label = self.label_filter_combobox.text_box.itemText(index)
        self._sync_label_list_visibility(
            lambda item: label in ["", item.shape().label]
            and self.label_info.get(item.shape().label, {}).get(
                "visible", True
            )
        )

    def gid_selection_changed(self, index):
        gid = self.gid_filter_combobox.gid_box.itemText(index)
        self._sync_label_list_visibility(
            lambda item: str(gid)
            in (
                ["-1", str(item.shape().group_id)]
                if item.shape().group_id is not None
                else ["-1"]
            )
        )

    def label_selection_changed(self):
        if self._no_selection_slot:
            return
        if self.canvas.is_brush_mode:
            return
        if self.canvas.editing():
            selected_shapes = []
            for item in self.label_list.selected_items():
                if item is None:
                    continue
                shape = item.shape()
                if shape is not None:
                    selected_shapes.append(shape)
            if selected_shapes:
                self.canvas.select_shapes(selected_shapes)
            else:
                self.canvas.deselect_shape()

    def label_item_changed(self, item):
        shape = item.shape()
        shape.visible = item.checkState() == Qt.CheckState.Checked
        self.canvas.set_shape_visible(
            shape, item.checkState() == Qt.CheckState.Checked
        )
        self._update_select_toggle_button_tooltip()
        if (
            hasattr(self, "navigator_dialog")
            and self.navigator_dialog.isVisible()
        ):
            self.update_navigator_shapes()

    def label_order_changed(self):
        shapes = []
        for item in self.label_list:
            if item is None:
                continue
            shape = item.shape()
            if shape is not None:
                shapes.append(shape)
        self.canvas.load_shapes(shapes)
        self.set_dirty()

    # Callback functions:
    def new_shape(self):
        """Pop-up and give focus to the label editor.

        position MUST be in global coordinates.
        """
        items = self.unique_label_list.selectedItems()
        text = None
        if items:
            text = items[0].data(Qt.ItemDataRole.UserRole)
        flags = {}
        group_id = None
        description = ""
        difficult = False
        kie_linking = []

        if self.canvas.shapes[-1].label in [
            AutoLabelingMode.ADD,
            AutoLabelingMode.REMOVE,
        ]:
            text = self.canvas.shapes[-1].label
        elif (
            self._config["display_label_popup"]
            or not text
            or self.canvas.shapes[-1].label == AutoLabelingMode.OBJECT
        ):
            last_label = self.find_last_label()
            last_gid = (
                self.find_last_gid()
                if self._config["auto_use_last_gid"]
                else None
            )
            if self.digit_to_label is not None:
                text = self.digit_to_label
                self.digit_to_label = None
                if last_gid is not None:
                    group_id = last_gid
            elif self._config["auto_use_last_label"] and last_label:
                text = last_label
                if last_gid is not None:
                    group_id = last_gid
            else:
                previous_text = self.label_dialog.edit.text()
                (
                    text,
                    flags,
                    group_id,
                    description,
                    difficult,
                    kie_linking,
                ) = self.label_dialog.pop_up(
                    text,
                    group_id=last_gid,
                    move_mode=self._config.get("move_mode", "auto"),
                )
                if not text:
                    self.label_dialog.edit.setText(previous_text)

        if text and not self.validate_label(text):
            self.error_message(
                self.tr("Invalid label"),
                self.tr("Invalid label '{}' with validation type '{}'").format(
                    text, self._config["validate_label"]
                ),
            )
            text = ""
            return

        if self.attributes and text:
            text = self.reset_attribute(text, self.canvas.shapes[-1])

        if text:
            self.label_list.clearSelection()
            shape = self.canvas.set_last_label(text, flags, group_id)
            shape.group_id = group_id
            shape.description = description
            if text not in [AutoLabelingMode.ADD, AutoLabelingMode.REMOVE]:
                shape.label = text
            shape.difficult = difficult
            shape.kie_linking = kie_linking
            self.add_label(shape)
            self.actions.edit_mode.setEnabled(True)
            self.actions.undo_last_point.setEnabled(False)
            self.actions.undo.setEnabled(True)
            self.set_dirty()
            if (
                self.canvas.drawing()
                and self.canvas.create_mode == "polygon"
                and not self.actions.create_brush_polygon_mode.isEnabled()
            ):
                self.canvas._brush_drawing = True

            if self.attributes and text in self.attributes:
                shape.selected = True
                self.shape_attributes.show()
                self.scroll_area.show()
                for i, canvas_shape in enumerate(self.canvas.shapes):
                    if canvas_shape is shape:
                        self.update_attributes(i)
                        break
        else:
            self.canvas.undo_last_line()
            self.canvas.shapes_backups.pop()

    def show_shape(self, shape_height, shape_width, pos):
        """Display annotation width and height while hovering inside.

        Parameters:
        - shape_height (float): The height of the shape.
        - shape_width (float): The width of the shape.
        - pos (QPointF): The current mouse coordinates inside the shape.
        """
        num_images = len(self.image_list)
        if shape_height > 0 and shape_width > 0:
            if num_images and self.filename in self.image_list:
                self.status(
                    str(self.tr("X: %d, Y: %d | H: %d, W: %d"))
                    % (
                        int(pos.x()),
                        int(pos.y()),
                        shape_height,
                        shape_width,
                    )
                )
            else:
                self.status(
                    str(self.tr("X: %d, Y: %d | H: %d, W: %d"))
                    % (int(pos.x()), int(pos.y()), shape_height, shape_width)
                )
        elif self.image_path:
            if num_images and self.filename in self.image_list:
                self.status(
                    str(self.tr("X: %d, Y: %d"))
                    % (
                        int(pos.x()),
                        int(pos.y()),
                    )
                )
            else:
                self.status(
                    str(self.tr("X: %d, Y: %d")) % (int(pos.x()), int(pos.y()))
                )

    def on_navigator_request(self, x_ratio, y_ratio):
        """Handle navigation request from navigator widget."""
        if not hasattr(self, "image") or self.image.isNull():
            return

        scroll_area = self._central_widget
        canvas_size = self.canvas.size()
        scroll_area_size = scroll_area.viewport().size()

        target_x = x_ratio * canvas_size.width() - scroll_area_size.width() / 2
        target_y = (
            y_ratio * canvas_size.height() - scroll_area_size.height() / 2
        )

        self.set_scroll(Qt.Orientation.Horizontal, target_x)
        self.set_scroll(Qt.Orientation.Vertical, target_y)

    def update_navigator_viewport(self):
        """Update the viewport rectangle in the navigator."""
        if not hasattr(self, "navigator_dialog") or not hasattr(self, "image"):
            return

        if not self.navigator_dialog.isVisible():
            return

        if self.image.isNull():
            return

        scroll_area = self._central_widget
        canvas_size = self.canvas.size()
        scroll_area_size = scroll_area.viewport().size()
        if canvas_size.width() <= 0 or canvas_size.height() <= 0:
            return

        h_scroll = self.scroll_bars[Qt.Orientation.Horizontal].value()
        v_scroll = self.scroll_bars[Qt.Orientation.Vertical].value()
        x_ratio = max(0.0, h_scroll / canvas_size.width())
        y_ratio = max(0.0, v_scroll / canvas_size.height())
        width_ratio = min(1.0, scroll_area_size.width() / canvas_size.width())
        height_ratio = min(
            1.0, scroll_area_size.height() / canvas_size.height()
        )

        self.navigator_dialog.set_viewport(
            x_ratio, y_ratio, width_ratio, height_ratio
        )
        self.update_navigator_shapes()

    def update_navigator_shapes(self):
        """Update shapes overlay in navigator."""
        if (
            not hasattr(self, "navigator_dialog")
            or not self.navigator_dialog.isVisible()
        ):
            return

        shapes = getattr(self.canvas, "shapes", [])
        canvas_visible = getattr(self.canvas, "visible", {})
        h_shape = getattr(self.canvas, "h_shape", None)
        for shape in shapes:
            shape._is_highlighted = shape == h_shape
        self.navigator_dialog.set_shapes(shapes, canvas_visible)

    def on_navigator_zoom_changed(
        self, zoom_percentage: int, mouse_pos: Optional[QtCore.QPoint] = None
    ) -> None:
        """Handle zoom change from navigator controls."""

        if not hasattr(self, "image") or self.image.isNull():
            return

        if mouse_pos is not None:
            canvas_pos = self._convert_navigator_pos_to_canvas(mouse_pos)
            if canvas_pos:
                canvas_width_old = self.canvas.width()

                self.zoom_widget.setValue(zoom_percentage)
                self.zoom_mode = self.MANUAL_ZOOM
                self.zoom_values[self.filename] = (
                    self.zoom_mode,
                    zoom_percentage,
                )
                self.paint_canvas()

                canvas_width_new = self.canvas.width()
                if canvas_width_old != canvas_width_new:
                    canvas_scale_factor = canvas_width_new / canvas_width_old
                    x_shift = round(
                        canvas_pos.x() * canvas_scale_factor - canvas_pos.x()
                    )
                    y_shift = round(
                        canvas_pos.y() * canvas_scale_factor - canvas_pos.y()
                    )
                    self.set_scroll(
                        QtCore.Qt.Orientation.Horizontal,
                        self.scroll_bars[
                            QtCore.Qt.Orientation.Horizontal
                        ].value()
                        + x_shift,
                    )
                    self.set_scroll(
                        QtCore.Qt.Orientation.Vertical,
                        self.scroll_bars[
                            QtCore.Qt.Orientation.Vertical
                        ].value()
                        + y_shift,
                    )

                return

        # Handle direct zoom changes
        if (
            hasattr(self, "canvas")
            and hasattr(self.canvas, "width")
            and hasattr(self.canvas, "height")
        ):
            if hasattr(self.navigator_dialog, "navigator"):
                nav_widget = self.navigator_dialog.navigator
                if (
                    hasattr(nav_widget, "viewport_rect")
                    and not nav_widget.viewport_rect.isEmpty()
                ):
                    nav_rect_center_x = nav_widget.viewport_rect.center().x()
                    nav_rect_center_y = nav_widget.viewport_rect.center().y()
                    canvas_pos = self._convert_navigator_pos_to_canvas(
                        QtCore.QPoint(
                            int(nav_rect_center_x), int(nav_rect_center_y)
                        )
                    )

                    if canvas_pos:
                        canvas_width_old = self.canvas.width()

                        self.zoom_widget.setValue(zoom_percentage)
                        self.zoom_mode = self.MANUAL_ZOOM
                        self.zoom_values[self.filename] = (
                            self.zoom_mode,
                            zoom_percentage,
                        )
                        self.paint_canvas()

                        canvas_width_new = self.canvas.width()
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
                            self.set_scroll(
                                QtCore.Qt.Orientation.Horizontal,
                                self.scroll_bars[
                                    QtCore.Qt.Orientation.Horizontal
                                ].value()
                                + x_shift,
                            )
                            self.set_scroll(
                                QtCore.Qt.Orientation.Vertical,
                                self.scroll_bars[
                                    QtCore.Qt.Orientation.Vertical
                                ].value()
                                + y_shift,
                            )
                        return

            self.zoom_widget.setValue(zoom_percentage)
            self.zoom_mode = self.MANUAL_ZOOM
            self.zoom_values[self.filename] = (self.zoom_mode, zoom_percentage)
            self.paint_canvas()
        else:
            self.zoom_widget.setValue(zoom_percentage)
            self.zoom_mode = self.MANUAL_ZOOM
            self.zoom_values[self.filename] = (self.zoom_mode, zoom_percentage)
            self.paint_canvas()

    def _convert_navigator_pos_to_canvas(
        self, navigator_pos: QtCore.QPoint
    ) -> Optional[QtCore.QPoint]:
        """Convert navigator mouse position to canvas coordinates."""
        if (
            not hasattr(self, "navigator_dialog")
            or not self.navigator_dialog.isVisible()
        ):
            return None

        navigator_widget = self.navigator_dialog.navigator
        if (
            not navigator_widget.image_rect
            or navigator_widget.image_rect.isEmpty()
        ):
            return None

        relative_x = navigator_pos.x() - navigator_widget.image_rect.x()
        relative_y = navigator_pos.y() - navigator_widget.image_rect.y()
        if (
            relative_x < 0
            or relative_x > navigator_widget.image_rect.width()
            or relative_y < 0
            or relative_y > navigator_widget.image_rect.height()
        ):
            return None

        # Convert to ratio (0.0 to 1.0)
        x_ratio = relative_x / navigator_widget.image_rect.width()
        y_ratio = relative_y / navigator_widget.image_rect.height()

        # Convert to canvas coordinates
        canvas_x = int(x_ratio * self.canvas.width())
        canvas_y = int(y_ratio * self.canvas.height())

        return QtCore.QPoint(canvas_x, canvas_y)

    def on_navigator_viewport_update_requested(self):
        """Handle viewport update request from navigator resize"""
        QtCore.QTimer.singleShot(50, self.update_navigator_viewport)

    def toggle_navigator(self):
        """Toggle the navigator window visibility"""
        if self.navigator_dialog.isVisible():
            self.navigator_dialog.hide()
            if hasattr(self, "actions") and hasattr(
                self.actions, "show_navigator"
            ):
                self.actions.show_navigator.setChecked(False)
        else:
            self.navigator_dialog.show()
            if hasattr(self, "image") and not self.image.isNull():
                self.navigator_dialog.set_image(
                    QtGui.QPixmap.fromImage(self.image)
                )
                self.update_navigator_viewport()
            if hasattr(self, "actions") and hasattr(
                self.actions, "show_navigator"
            ):
                self.actions.show_navigator.setChecked(True)

    def scroll_request(self, delta, orientation, mode):
        scroll_bar = self.scroll_bars[orientation]
        units = -delta * (0.1 if mode == 0 else 1)
        step = scroll_bar.singleStep() if mode == 0 else scroll_bar.maximum()
        value = scroll_bar.value() + step * units
        self.set_scroll(orientation, value)

    def set_scroll(self, orientation, value):
        self.scroll_bars[orientation].setValue(round(value))
        self.scroll_values[orientation][self.filename] = value
        self.update_navigator_viewport()

    def set_zoom(self, value):
        self.actions.fit_width.setChecked(False)
        self.actions.fit_window.setChecked(False)
        self.zoom_mode = self.MANUAL_ZOOM
        self.zoom_widget.setValue(value)
        self.zoom_values[self.filename] = (self.zoom_mode, value)
        if hasattr(self, "navigator_dialog"):
            self.navigator_dialog.set_zoom_value(value)

    def add_zoom(self, increment=1.1):
        zoom_value = self.zoom_widget.value() * increment
        if increment > 1:
            zoom_value = math.ceil(zoom_value)
        else:
            zoom_value = math.floor(zoom_value)
        self.set_zoom(zoom_value)

    def zoom_request(self, delta, pos):
        canvas_width_old = self.canvas.width()
        units = 1.1
        if delta < 0:
            units = 0.9
        self.add_zoom(units)

        canvas_width_new = self.canvas.width()
        if canvas_width_old != canvas_width_new:
            canvas_scale_factor = canvas_width_new / canvas_width_old

            x_shift = round(pos.x() * canvas_scale_factor - pos.x())
            y_shift = round(pos.y() * canvas_scale_factor - pos.y())

            self.set_scroll(
                Qt.Orientation.Horizontal,
                self.scroll_bars[Qt.Orientation.Horizontal].value() + x_shift,
            )
            self.set_scroll(
                Qt.Orientation.Vertical,
                self.scroll_bars[Qt.Orientation.Vertical].value() + y_shift,
            )

    def set_fit_window(self, value=True):
        if value:
            self.actions.fit_width.setChecked(False)
        self.zoom_mode = self.FIT_WINDOW if value else self.MANUAL_ZOOM
        self.adjust_scale()

    def set_fit_width(self, value=True):
        if value:
            self.actions.fit_window.setChecked(False)
        self.zoom_mode = self.FIT_WIDTH if value else self.MANUAL_ZOOM
        self.adjust_scale()

    def set_cross_line(self):
        crosshair_dialog = CrosshairSettingsDialog(**self.crosshair_settings)
        if crosshair_dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            crosshair_settings = crosshair_dialog.get_settings()
            show = crosshair_settings["show"]
            width = crosshair_settings["width"]
            color = crosshair_settings["color"]
            opacity = crosshair_settings["opacity"]
            self.canvas.set_cross_line(show, width, color, opacity)
            self._config["canvas"]["crosshair"] = crosshair_settings

    def set_canvas_params(self, key, value):
        self._config[key] = value
        assert hasattr(self.canvas, key), f"Canvas has no attribute {key}"
        setattr(self.canvas, key, value)
        self.canvas.update()
        if key in ("show_masks", "show_attributes"):
            # Give immediate, unambiguous feedback for Ctrl+M / Ctrl+Shift+L so
            # toggling the overlay is obvious: the change is hard to spot when
            # the affected shapes also draw outlines or carry no attributes.
            labels = {
                "show_masks": self.tr("掩膜显示"),
                "show_attributes": self.tr("属性显示"),
            }
            try:
                self.status(
                    "%s：%s"
                    % (
                        labels[key],
                        self.tr("开") if value else self.tr("关"),
                    )
                )
            except Exception:  # noqa: BLE001
                pass

    def open_settings_dialog(self):
        if self._settings_controller is None:
            return
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(
                self, self._settings_controller
            )
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def add_point_to_edge(self):
        shape = self.canvas.prev_h_shape
        edge_index = self.canvas.prev_h_edge
        point = self.canvas.prev_move_point
        if shape is None or edge_index is None or point is None:
            return
        self.canvas.add_point_to_edge()
        self.canvas.update()
        self.set_dirty()

    def on_new_brightness_contrast(self, qimage):
        self.canvas.load_pixmap(
            QtGui.QPixmap.fromImage(qimage), clear_shapes=False
        )

    def _on_shape_opacity_changed(self, value):
        """Update label/shape opacity from the slider value (0-100)."""
        self.canvas.shape_opacity = value / 100.0
        self.canvas.update()

    def _on_inline_brightness_contrast(self, brightness, contrast):
        """Apply brightness/contrast from the inline adjustment sliders.

        Reuses ``brightness_contrast_dialog`` so 16-bit grayscale handling is
        shared with the menu-driven dialog. ``dialog.img`` is refreshed on
        every image load (see ``load_file``).
        """
        if self.image_data is None or self.filename is None:
            return
        dialog = self.brightness_contrast_dialog
        dialog.set_values(brightness, contrast)
        dialog.on_new_value()
        self.brightness_contrast_values[self.filename] = (brightness, contrast)

    def _position_canvas_adjustment(self):
        """Keep the adjustment panel anchored to the viewport's bottom-left."""
        if not hasattr(self, "canvas_adjustment"):
            return
        viewport = self._canvas_scroll_area.viewport()
        self.canvas_adjustment.adjustSize()
        margin = 10
        height = self.canvas_adjustment.height()
        self.canvas_adjustment.move(
            margin, max(0, viewport.height() - height - margin)
        )
        self.canvas_adjustment.raise_()

    def eventFilter(self, obj, event):
        if (
            hasattr(self, "_canvas_scroll_area")
            and obj is self._canvas_scroll_area.viewport()
            and event.type() == QtCore.QEvent.Type.Resize
        ):
            self._position_canvas_adjustment()
            self._position_empty_canvas_state()
            self._sync_tools_panel()
        return super().eventFilter(obj, event)

    def brightness_contrast(self, _):
        self.brightness_contrast_dialog.update_image(
            utils.img_data_to_pil(self.image_data)
        )

        brightness, contrast = self.brightness_contrast_values.get(
            self.filename, (None, None)
        )
        self.brightness_contrast_dialog.set_values(
            brightness if brightness is not None else 50,
            contrast if contrast is not None else 50,
        )

        self.brightness_contrast_dialog.exec()

        brightness = self.brightness_contrast_dialog.slider_brightness.value()
        contrast = self.brightness_contrast_dialog.slider_contrast.value()
        self.brightness_contrast_values[self.filename] = (brightness, contrast)
        # Keep the inline adjustment sliders in sync with the dialog.
        self.canvas_adjustment.set_brightness_contrast(brightness, contrast)

    def hide_selected_polygons(self):
        shapes_to_hide = []
        for item in self.label_list:
            if item.shape().selected:
                item.setCheckState(Qt.CheckState.Unchecked)
                item.shape().visible = False
                shapes_to_hide.append(item.shape())

        self.selected_polygon_stack.extend(shapes_to_hide)
        self.canvas.update()
        if (
            hasattr(self, "navigator_dialog")
            and self.navigator_dialog.isVisible()
        ):
            self.update_navigator_shapes()

    def show_hidden_polygons(self):
        if self.selected_polygon_stack:
            shape_to_show = self.selected_polygon_stack.pop()
            item = self.label_list.find_item_by_shape(shape_to_show)
            if item:
                item.setCheckState(Qt.CheckState.Checked)
                shape_to_show.visible = True
                self.canvas.update()
                if (
                    hasattr(self, "navigator_dialog")
                    and self.navigator_dialog.isVisible()
                ):
                    self.update_navigator_shapes()
            else:
                logger.warning(
                    f"Shape associated with the hidden item was not found in label list, could not show."
                )

    def get_next_files(self, filename, num_files):
        """Get the next files in the list."""
        if not self.image_list:
            return []
        filenames = []
        current_index = 0
        if filename is not None:
            try:
                current_index = self.fn_to_index[str(filename)]
            except ValueError:
                return []
            filenames.append(filename)
        for _ in range(num_files):
            if current_index + 1 < len(self.image_list):
                filenames.append(self.image_list[current_index + 1])
                current_index += 1
            else:
                filenames.append(self.image_list[-1])
                break
        return filenames

    def inform_next_files(self, filename):
        """Inform the next files to be annotated.
        This list can be used by the user to preload the next files
        or running a background process to process them
        """
        next_files = self.get_next_files(filename, 5)
        if next_files:
            self.next_files_changed.emit(next_files)

    def _decode_image_data(self, image_data, filename=None):
        """Decode image bytes into a QImage (and a loaded PIL copy for the
        adjustment dialog).

        Small files are decoded inline exactly as before.  Large files are
        decoded on a background thread while the main thread keeps pumping
        non-input events, so opening a big frame shows a live loading
        overlay instead of freezing the whole window into "Not Responding".
        User input events are excluded during the wait, which prevents a
        re-entrant ``load_file`` while decoding is in progress.
        """
        LARGE_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB raw bytes threshold

        if image_data is None or len(image_data) <= LARGE_IMAGE_BYTES:
            # Keep the historical fast path bit-for-bit identical.
            return utils.img_data_to_qimage(image_data, filename), None

        result = {}
        self.canvas.set_loading(
            True, self.tr("Loading large image... Please wait.")
        )
        QtWidgets.QApplication.setOverrideCursor(
            QtCore.Qt.CursorShape.WaitCursor
        )

        def _decode():
            try:
                qimage = utils.img_data_to_qimage(image_data, filename)
                result["image"] = qimage
            except Exception:  # noqa: BLE001
                result["image"] = None
            try:
                pil = utils.img_data_to_pil(image_data)
                pil.load()  # force pixel decode off the UI thread
                result["pil"] = pil
            except Exception:  # noqa: BLE001
                result["pil"] = None

        worker = threading.Thread(target=_decode, daemon=True)
        worker.start()
        while worker.is_alive():
            QtWidgets.QApplication.processEvents(
                QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
            )
            time.sleep(0.01)
        QtWidgets.QApplication.restoreOverrideCursor()
        self.canvas.set_loading(False)
        return result.get("image"), result.get("pil")

    def load_file(self, filename=None):  # noqa: C901
        """Load the specified file, or the last opened file if None."""

        # NOTE(jack): Does we need to save the config here?
        # save_config(self._config)

        # For auto labeling, clear the previous marks
        # and inform the next files to be annotated
        # NOTE(jack): this is not needed for now
        # self.clear_auto_labeling_marks()
        # self.inform_next_files(filename)

        # Changing file_list_widget loads file
        if str(filename) in self.fn_to_index and (
            self.file_list_widget.currentRow()
            != self.fn_to_index[str(filename)]
        ):
            self.file_list_widget.setCurrentRow(
                self.fn_to_index[str(filename)]
            )
            current_item = self.file_list_widget.currentItem()
            if current_item is not None:
                self.file_list_widget.scrollToItem(
                    current_item,
                    QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible,
                )
            self.file_list_widget.update()
            return False

        self.reset_state()
        self.canvas.setEnabled(False)

        if filename is None:
            filename = self.settings.value("filename", "")
        filename = str(filename)
        if not QtCore.QFile.exists(filename):
            self.error_message(
                self.tr("Error opening file"),
                self.tr("No such file: <b>%s</b>") % filename,
            )
            return False

        # assumes same name, but json extension
        label_file = osp.splitext(filename)[0] + ".json"
        image_dir = None
        if self.output_dir:
            image_dir = osp.dirname(filename)
            label_file_without_path = osp.basename(label_file)
            label_file = self.output_dir + "/" + label_file_without_path

        if QtCore.QFile.exists(label_file) and LabelFile.is_label_file(
            label_file
        ):
            try:
                self.label_file = LabelFile(label_file, image_dir)
            except LabelFileError as e:
                self.error_message(
                    self.tr("Error opening file"),
                    self.tr(
                        "<p><b>%s</b></p>"
                        "<p>Make sure <i>%s</i> is a valid label file."
                    )
                    % (e, label_file),
                )
                self.status(self.tr("Error reading %s") % label_file)
                return False
            self.image_data = self.label_file.image_data
            self.image_path = osp.join(
                osp.dirname(label_file),
                self.label_file.image_path,
            )
            self.other_data = self.label_file.other_data
            self.other_data[CHECKED_FIELD] = self._annotation_checked()
            # Negative-sample badge: an on-disk json with zero shapes is a
            # confirmed background image (YOLO negative sample). Refresh the
            # file list marker whenever such a file is (re)opened.
            try:
                neg_items = self.file_list_widget.findItems(
                    self.image_path, Qt.MatchFlag.MatchExactly
                )
                if len(neg_items) == 1:
                    self._set_file_item_annotated(
                        neg_items[0],
                        True,
                        negative=len(self.label_file.shapes) == 0,
                    )
                    self._set_file_item_low_conf(
                        neg_items[0],
                        self._shapes_need_review(self.label_file.shapes),
                    )
            except Exception:  # noqa: BLE001
                pass
        else:
            self.image_data = LabelFile.load_image_file(filename)
            if self.image_data:
                self.image_path = filename
            self.label_file = None
            self.other_data = {CHECKED_FIELD: False}

        # TODO(jack): icc profile issue warning
        # - qt.gui.icc: fromIccProfile: failed minimal tag size sanity
        # - qt.gui.icc: fromIccProfile: invalid tag offset alignment
        # Decode large images off the UI thread so opening a big frame never
        # hard-freezes the whole window into a "Not Responding" state.
        image, pil_cache = self._decode_image_data(self.image_data, filename)

        if image is None or image.isNull():
            formats = [
                f"*{ext}" for ext in utils.get_supported_image_extensions()
            ]
            self.error_message(
                self.tr("Error opening file"),
                self.tr(
                    "<p>Make sure <i>{0}</i> is a valid image file.<br/>"
                    "Supported image formats: {1}</p>"
                ).format(filename, ",".join(formats)),
            )
            self.status(self.tr("Error reading %s") % filename)
            return False
        self.image = image
        self.filename = filename

        if (
            hasattr(self, "navigator_dialog")
            and self.navigator_dialog.isVisible()
        ):
            self.navigator_dialog.set_image(QtGui.QPixmap.fromImage(image))
            self.update_navigator_shapes()
        if (
            hasattr(self, "_should_restore_navigator")
            and self._should_restore_navigator
        ):
            self._should_restore_navigator = False
            if self.navigator_dialog.isVisible():
                self.update_navigator_viewport()
        if self._config["keep_prev"]:
            prev_shapes = self.canvas.shapes
        self.canvas.load_pixmap(QtGui.QPixmap.fromImage(image))

        # load label flags
        flags = {k: False for k in self.image_flags or []}
        if self.label_file:
            for shape in self.label_file.shapes:
                default_flags = {}
                if self._config["label_flags"]:
                    for pattern, keys in self._config["label_flags"].items():
                        if re.match(pattern, shape.label):
                            for key in keys:
                                default_flags[key] = False
                    shape.flags = {
                        **default_flags,
                        **shape.flags,
                    }
            self.load_shapes(self.label_file.shapes, update_last_label=False)
            if self.label_file.flags is not None:
                flags.update(self.label_file.flags)
        self.load_flags(flags)

        # load shapes
        if self._config["keep_prev"] and self.no_shape():
            self.load_shapes(
                prev_shapes, replace=False, update_last_label=False
            )
            self.set_dirty()
        else:
            self.set_clean()
        self.canvas.setEnabled(True)

        # set zoom values
        is_initial_load = not self.zoom_values
        if self.filename in self.zoom_values:
            self.zoom_mode = self.zoom_values[self.filename][0]
            self.set_zoom(self.zoom_values[self.filename][1])
        elif is_initial_load or not self._config["keep_prev_scale"]:
            self.adjust_scale(initial=True)
        # set scroll values
        for orientation in self.scroll_values:
            if self.filename in self.scroll_values[orientation]:
                self.set_scroll(
                    orientation, self.scroll_values[orientation][self.filename]
                )

        # set brightness contrast values
        brightness, contrast = self.brightness_contrast_values.get(
            self.filename, (None, None)
        )
        if self._config["keep_prev_brightness"] and self.recent_files:
            brightness, _ = self.brightness_contrast_values.get(
                self.recent_files[0], (None, None)
            )
        if self._config["keep_prev_contrast"] and self.recent_files:
            _, contrast = self.brightness_contrast_values.get(
                self.recent_files[0], (None, None)
            )
        self.brightness_contrast_values[self.filename] = (brightness, contrast)
        # Always refresh the dialog's source image so the inline adjustment
        # sliders can reuse its brightness/contrast pipeline (which includes
        # 16-bit grayscale handling).  For large images this PIL copy was
        # already produced by the background decoder (pil_cache).
        self.brightness_contrast_dialog.update_image(
            pil_cache
            if pil_cache is not None
            else utils.img_data_to_pil(self.image_data)
        )
        self.brightness_contrast_dialog.set_values(
            brightness if brightness is not None else 50,
            contrast if contrast is not None else 50,
        )
        if brightness is not None or contrast is not None:
            self.brightness_contrast_dialog.on_new_value()
        # Sync the inline adjustment sliders (50 is the neutral value).
        self.canvas_adjustment.set_brightness_contrast(
            brightness if brightness is not None else 50,
            contrast if contrast is not None else 50,
        )

        self.paint_canvas()
        self.add_recent_file(self.filename)
        self.toggle_actions(True)
        self.canvas.setFocus()
        self._sync_annotation_checked_state()
        self.update_thumbnail_display()

        # Reveal the adjustment panel now that an image is loaded.
        self.canvas_adjustment.show()
        self._position_canvas_adjustment()
        self._sync_empty_canvas_state()
        self._maybe_focus_low_confidence_shapes()

        return True

    # QT Overload
    def keyPressEvent(self, event):
        # 输入控件有焦点时不拦截按键（避免输入 A/D 触发翻页）
        focus = self.focusWidget()
        if focus is not None and isinstance(
            focus,
            (
                QtWidgets.QLineEdit,
                QtWidgets.QPlainTextEdit,
                QtWidgets.QTextEdit,
                QtWidgets.QComboBox,
                QtWidgets.QSpinBox,
                QtWidgets.QDoubleSpinBox,
                QtWidgets.QTextBrowser,
            ),
        ):
            super(LabelingWidget, self).keyPressEvent(event)
            return
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key.Key_D and modifiers == Qt.KeyboardModifier.NoModifier:
            self.open_next_image()
            event.accept()
            return
        if key == Qt.Key.Key_A and modifiers == Qt.KeyboardModifier.NoModifier:
            self.open_prev_image()
            event.accept()
            return
        if key == Qt.Key.Key_Return and modifiers & Qt.KeyboardModifier.ControlModifier:
            self._finish_shape_and_save()
            event.accept()
            return
        if key == Qt.Key.Key_Escape:
            if getattr(self.canvas, "is_brush_mode", False):
                self.canvas.cancel_brush_mode()
            elif self.actions.edit_brush_mode.isChecked():
                self.actions.edit_brush_mode.setChecked(False)
            event.accept()
            return
        super(LabelingWidget, self).keyPressEvent(event)

    def _finish_shape_and_save(self):
        """Ctrl+Enter: finish the current drawing shape (if any) and save."""
        try:
            if getattr(self.canvas, "current", None) is not None and (
                self.canvas.drawing() if hasattr(self.canvas, "drawing") else True
            ):
                self.canvas.finalise()
        except Exception as e:  # noqa
            logger.warning(f"Finish shape failed: {e}")
        if self.dirty:
            self.save_file()

    def resizeEvent(self, _):
        if (
            self.canvas
            and not self.image.isNull()
            and self.zoom_mode != self.MANUAL_ZOOM
        ):
            self.adjust_scale()
        self.update_thumbnail_pixmap()
        self._position_canvas_adjustment()
        self._sync_tools_panel()

    def paint_canvas(self):
        if self.image.isNull():
            return
        self.canvas.scale = 0.01 * self.zoom_widget.value()
        self.canvas.adjustSize()
        self.canvas.update()
        self.update_navigator_viewport()

    def adjust_scale(self, initial=False):
        value = self.scalers[self.FIT_WINDOW if initial else self.zoom_mode]()
        value = int(100 * value)
        self.zoom_widget.setValue(value)
        self.zoom_values[self.filename] = (self.zoom_mode, value)
        if hasattr(self, "navigator_dialog"):
            self.navigator_dialog.set_zoom_value(value)

    def scale_fit_window(self):
        """Figure out the size of the pixmap to fit the main widget."""
        e = 2.0  # So that no scrollbars are generated.
        w1 = self.central_widget().width() - e
        h1 = self.central_widget().height() - e
        # Calculate a new scale value based on the pixmap's aspect ratio.
        w2 = self.canvas.pixmap.width() - 0.0
        h2 = self.canvas.pixmap.height() - 0.0
        if h1 <= 0 or w2 <= 0 or h2 <= 0:
            return 1.0
        wh_ratio1 = w1 / h1
        wh_ratio2 = w2 / h2
        return w1 / w2 if wh_ratio2 >= wh_ratio1 else h1 / h2

    def scale_fit_width(self):
        # The epsilon does not seem to work too well here.
        w = self.central_widget().width() - 2.0
        pw = self.canvas.pixmap.width()
        return w / pw if pw > 0 else 1.0

    # QT Overload
    def closeEvent(self, event):
        if not self.may_continue():
            event.ignore()
        self.settings.setValue(
            "filename", self.filename if self.filename else ""
        )
        self.settings.setValue("recent_files", self.recent_files)
        if self.last_open_dir:
            self.settings.setValue("last_open_dir", self.last_open_dir)

        if hasattr(self, "navigator_dialog"):
            navigator_visible = self.navigator_dialog.isVisible()
            self.settings.setValue("navigator/visible", navigator_visible)
            if navigator_visible:
                self.settings.setValue(
                    "navigator/geometry", self.navigator_dialog.saveGeometry()
                )
                self.settings.setValue(
                    "navigator/size", self.navigator_dialog.size()
                )
                self.settings.setValue(
                    "navigator/position", self.navigator_dialog.pos()
                )

        if self._settings_controller is not None:
            self._settings_controller.close_session()

        save_config(self._config)

        if hasattr(self, "async_exif_scanner") and self.async_exif_scanner:
            try:
                self.async_exif_scanner.stop_scan()
            except (RuntimeError, AttributeError):
                pass
        if hasattr(self, "async_label_checker") and self.async_label_checker:
            try:
                self.async_label_checker.stop()
            except (RuntimeError, AttributeError):
                pass

        # ask the use for where to save the labels
        # self.settings.setValue('window/geometry', self.saveGeometry())

    # QT Overload
    def dragEnterEvent(self, event):
        extensions = utils.get_supported_image_extensions()
        if event.mimeData().hasUrls():
            items = [i.toLocalFile() for i in event.mimeData().urls()]
            if any(i.lower().endswith(tuple(extensions)) for i in items):
                event.accept()
        else:
            event.ignore()

    # QT Overload
    def dropEvent(self, event):
        if not self.may_continue():
            event.ignore()
            return
        items = [i.toLocalFile() for i in event.mimeData().urls()]
        self.import_dropped_image_files(items)

    def load_recent(self, filename):
        if self.may_continue():
            self.load_file(filename)

    def load_recent_dir(self, dirpath):
        self.import_image_folder(dirpath)

    def _paging_blocked_by_drawing(self):
        """Block prev/next paging while a shape is being drawn so the
        half-finished shape is not silently discarded (A/D accident)."""
        if not hasattr(self, "canvas") or self.canvas is None:
            return False
        if not self.canvas.drawing():
            return False
        if getattr(self.canvas, "current", None) is None:
            return False
        self.status(
            self.tr(
                "Finish or cancel the current shape "
                "(Enter / Esc) before changing images."
            )
        )
        return True

    def _visible_rows(self):
        """Row indices currently not hidden by the filter combo."""
        count = self.file_list_widget.count()
        return [
            i
            for i in range(count)
            if not self.file_list_widget.item(i).isHidden()
        ]

    def _first_visible_row(self):
        rows = self._visible_rows()
        return rows[0] if rows else -1

    def _next_visible_row(self, row, delta):
        """Delegates to filelist.controller (paging actions call this)."""
        return FileReviewController(self).next_visible_row(row, delta)

    def open_prev_unchecked_image(self):
        """Delegates to filelist.controller (action wiring stays)."""
        # Built on demand: the controller is stateless, and light test
        # stubs never carry an instance.
        FileReviewController(self).open_prev_unchecked_image()

    def open_next_unchecked_image(self, _value=False):
        """Delegates to filelist.controller (action wiring stays)."""
        # Built on demand: the controller is stateless, and light test
        # stubs never carry an instance.
        FileReviewController(self).open_next_unchecked_image(_value)

    def open_prev_image(self, _value=False):
        if self._paging_blocked_by_drawing():
            return
        if not self.may_continue(silent=True):
            return
        if self.file_list_widget.count() <= 0:
            return
        if self.filename is None:
            return
        current_index = self.fn_to_index[str(self.filename)]
        target_index = self._next_visible_row(current_index, -1)
        if target_index < 0 or target_index == current_index:
            return
        filename = self.file_list_widget.item(target_index).text()
        if filename:
            self.load_file(filename)

    def open_next_image(self, _value=False, load=True):
        if self._paging_blocked_by_drawing():
            return
        if not self.may_continue(silent=True):
            return
        count = self.file_list_widget.count()
        if count <= 0:
            return
        filename = None
        if self.filename is None:
            first_row = self._first_visible_row()
            if first_row < 0:
                return
            filename = self.file_list_widget.item(first_row).text()
        else:
            current_index = self.fn_to_index[str(self.filename)]
            target_index = self._next_visible_row(current_index, 1)
            if target_index < 0 or target_index == current_index:
                return
            filename = self.file_list_widget.item(target_index).text()
        self.filename = filename
        if self.filename and load:
            self.load_file(self.filename)

    # File
    def open_file(self, _value=False):
        if not self.may_continue():
            return
        path = osp.dirname(str(self.filename)) if self.filename else "."
        formats = [f"*{ext}" for ext in utils.get_supported_image_extensions()]
        filters = self.tr("Image & Label files (%s)") % " ".join(
            formats + [f"*{LabelFile.suffix}"]
        )
        file_dialog = FileDialogPreview(self)
        file_dialog.setFileMode(QtWidgets.QFileDialog.FileMode.ExistingFile)
        file_dialog.setNameFilter(filters)
        file_dialog.setWindowTitle(
            self.tr("%s - Choose Image or Label file") % __appname__,
        )
        file_dialog.setWindowFilePath(path)
        file_dialog.setViewMode(QtWidgets.QFileDialog.ViewMode.Detail)
        if file_dialog.exec():
            filename = file_dialog.selectedFiles()[0]
            if filename:
                self.file_list_widget.clear()
                self.fn_to_index.clear()
                self.load_file(filename)

    def _current_label_counts(self):
        """Count shapes per label for the currently loaded image."""
        counts = {}
        if not hasattr(self, "canvas") or self.canvas is None:
            return counts
        for shape in self.canvas.shapes:
            label = getattr(shape, "label", None)
            if not label:
                continue
            counts[label] = counts.get(label, 0) + 1
        return counts

    def _refresh_label_panel(self, *_, **__):
        """Refresh label counts and apply the label search filter.

        The unique label list keeps its selection/order; hidden rows are
        restored when the search box is cleared.
        """
        try:
            counts = self._current_label_counts()
            query = self.label_search.text().strip().lower()
            for row in range(self.unique_label_list.count()):
                item = self.unique_label_list.item(row)
                label = item.data(Qt.ItemDataRole.UserRole) or ""
                count = counts.get(label)
                self.unique_label_list.set_label_count(label, count)
                if count is not None:
                    item.setToolTip(
                        self.tr("%1（当前图片 %2 个）")
                        .replace("%1", str(label))
                        .replace("%2", str(count))
                    )
                matched = (
                    not query or query in str(label).lower()
                )
                item.setHidden(not matched)
        except Exception as e:  # noqa
            logger.warning(f"Label panel refresh failed: {e}")

    def _unique_label_context_menu(self, pos):
        item = self.unique_label_list.itemAt(pos)
        if item is None:
            return
        menu = QtWidgets.QMenu(self)
        rename_action = menu.addAction(self.tr("重命名标签"))
        chosen = menu.exec(self.unique_label_list.mapToGlobal(pos))
        if chosen == rename_action:
            self.rename_unique_label(item)

    def rename_unique_label(self, item=None):
        """Rename a class in the Labels dock (e.g. class_0 → 真实类别名)."""
        if item is None or not isinstance(item, QtWidgets.QListWidgetItem):
            items = self.unique_label_list.selectedItems()
            if not items:
                return
            item = items[0]
        old_label = item.data(Qt.ItemDataRole.UserRole)
        if not old_label:
            return
        new_label, ok = QInputDialog.getText(
            self,
            self.tr("重命名标签"),
            self.tr("将「%1」修改为：").replace("%1", str(old_label)),
            QLineEdit.EchoMode.Normal,
            str(old_label),
        )
        if not ok:
            return
        new_label = str(new_label).strip()
        if not new_label or new_label == old_label:
            return
        if not self.validate_label(new_label):
            self.error_message(
                self.tr("Invalid label"),
                self.tr("Invalid label '{}' with validation type '{}'").format(
                    new_label, self._config["validate_label"]
                ),
            )
            return
        self._apply_unique_label_rename(old_label, new_label)

    def _apply_unique_label_rename(self, old_label, new_label):
        if self.canvas.shapes:
            self.canvas.store_shapes()

        old_items = self.unique_label_list.find_items_by_label(old_label)
        new_items = self.unique_label_list.find_items_by_label(new_label)
        if new_items:
            for old_item in old_items:
                row = self.unique_label_list.row(old_item)
                if row >= 0:
                    self.unique_label_list.takeItem(row)
        else:
            for old_item in old_items:
                old_item.setData(Qt.ItemDataRole.UserRole, new_label)
                rgb = self._get_rgb_by_label(new_label)
                self.unique_label_list.set_item_label(
                    old_item, new_label, rgb, LABEL_OPACITY
                )

        if old_label in self.label_info:
            info = self.label_info.pop(old_label)
            if new_label not in self.label_info:
                info["value"] = None
                self.label_info[new_label] = info

        renamed = 0
        for shape in self.canvas.shapes:
            if shape.label != old_label:
                continue
            shape.label = new_label
            self._update_shape_color(shape)
            renamed += 1
            list_item = self.label_list.find_item_by_shape(shape)
            if list_item is not None:
                list_item.setText(
                    _format_label_list_text(shape.label, shape.group_id)
                )
                color = shape.fill_color.getRgb()[:3]
                list_item.setBackground(QtGui.QColor(*color, LABEL_OPACITY))

        self.label_dialog.remove_label_history(old_label)
        self.label_dialog.add_label_history(new_label)

        labels = list(self._config.get("labels") or [])
        if old_label in labels:
            labels = [new_label if name == old_label else name for name in labels]
        elif new_label not in labels:
            labels.append(new_label)
        seen = set()
        unique_labels = []
        for name in labels:
            if name in seen:
                continue
            seen.add(name)
            unique_labels.append(name)
        self._config["labels"] = unique_labels
        save_config(self._config)

        folder_changed = 0
        label_dir = self.output_dir
        if not label_dir and self.filename:
            label_dir = osp.dirname(self.filename)
        if label_dir:
            paths = list(self.image_list or [])
            if self.filename and self.filename not in paths:
                paths = [self.filename, *paths]
            folder_changed = rename_label_across_folder(
                paths,
                label_dir,
                old_label,
                new_label,
                extra_class_names=self._yolo_class_names(),
            )

        self.canvas.update()
        self._refresh_shape_filters()
        self._refresh_label_panel()
        self.set_dirty()
        status = self.tr("已将 %1 改为 %2").replace("%1", old_label).replace(
            "%2", new_label
        )
        if renamed:
            status += f" ({renamed})"
        if folder_changed:
            status += self.tr(" · 文件夹 %1 个文件").replace(
                "%1", str(folder_changed)
            )
        self.status(status)

    def change_output_dir_dialog(self, _value=False):
        default_output_dir = self.output_dir
        if default_output_dir is None and self.filename:
            default_output_dir = osp.dirname(self.filename)
        if default_output_dir is None:
            default_output_dir = self.current_path()

        output_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("%s - Save/Load Annotations in Directory") % __appname__,
            default_output_dir,
            QtWidgets.QFileDialog.Option.ShowDirsOnly
            | QtWidgets.QFileDialog.Option.DontResolveSymlinks,
        )
        output_dir = str(output_dir)

        if not output_dir:
            return

        self.output_dir = output_dir

        self.statusBar().showMessage(
            self.tr("%s . Annotations will be saved/loaded in %s")
            % ("Change Annotations Dir", self.output_dir)
        )
        self.statusBar().show()

        current_filename = self.filename
        self.import_image_folder(self.last_open_dir, load=False)

        if current_filename in self.image_list:
            # retain currently selected file
            self.file_list_widget.setCurrentRow(
                self.fn_to_index[str(current_filename)]
            )
            self.file_list_widget.repaint()

    def save_file(self, _value=False):
        assert not self.image.isNull(), "cannot save empty image"
        if self.label_file:
            # DL20180323 - overwrite when in directory
            self._save_file(self.label_file.filename)
        elif self.output_file:
            self._save_file(self.output_file)
            self.close()
        else:
            self._save_file(self.save_file_dialog())

    def save_file_as(self, _value=False):
        assert not self.image.isNull(), "cannot save empty image"
        self._save_file(self.save_file_dialog())

    def save_file_dialog(self):
        caption = self.tr("%s - Choose File") % __appname__
        filters = self.tr("Label files (*%s)") % LabelFile.suffix
        if self.output_dir:
            file_dialog = QtWidgets.QFileDialog(
                self, caption, self.output_dir, filters
            )
        else:
            file_dialog = QtWidgets.QFileDialog(
                self, caption, self.current_path(), filters
            )
        file_dialog.setDefaultSuffix(LabelFile.suffix[1:])
        file_dialog.setAcceptMode(QtWidgets.QFileDialog.AcceptMode.AcceptSave)
        file_dialog.setOption(
            QtWidgets.QFileDialog.Option.DontConfirmOverwrite, False
        )
        file_dialog.setOption(
            QtWidgets.QFileDialog.Option.DontUseNativeDialog, False
        )
        basename = osp.basename(osp.splitext(self.filename)[0])
        if self.output_dir:
            default_labelfile_name = osp.join(
                self.output_dir, basename + LabelFile.suffix
            )
        else:
            default_labelfile_name = osp.join(
                self.current_path(), basename + LabelFile.suffix
            )
        filename = file_dialog.getSaveFileName(
            self,
            self.tr("Choose File"),
            default_labelfile_name,
            self.tr("Label files (*%s)") % LabelFile.suffix,
        )
        if isinstance(filename, tuple):
            filename, _ = filename
        return filename

    def _save_file(self, filename):
        if filename and self.save_labels(filename):
            self.add_recent_file(filename)
            self.set_clean()
            self._show_save_feedback(True)
        else:
            self._show_save_feedback(False)

    def _show_save_feedback(self, ok):
        """Show a short, non-modal feedback about the last save operation.

        Success is shown briefly in the status bar; failures are surfaced
        through the corner toaster (red) so they do not stomp on other
        status-bar messages while the user keeps annotating.
        """
        try:
            name = osp.basename(str(self.filename)) if self.filename else ""
            if ok:
                message = self.tr("✓ 已保存：%s") % name
                quality = getattr(self, "_last_quality_status", "") or ""
                if quality:
                    message = f"{message}  {quality}"
                self.status(message, 5000 if quality else 2500)
            else:
                try:
                    t = get_theme()
                    error_color = t.get("error", "#E5484D")
                except Exception:  # noqa: BLE001
                    error_color = "#E5484D"
                QToaster.show_message(
                    self,
                    self.tr("✗ 保存失败：%s") % name,
                    timeout=5000,
                    color=error_color,
                )
                self.statusBar().showMessage(
                    self.tr("✗ 保存失败：%s") % name,
                    5000,
                )
        except Exception as e:  # noqa
            logger.warning(f"Save feedback failed: {e}")
        self._update_save_state_label()

    def close_file(self, _value=False):
        if not self.may_continue():
            return
        self.reset_state()
        self.set_clean()
        self.toggle_actions(False)
        self.canvas.setEnabled(False)
        self.actions.save_as.setEnabled(False)

    def get_label_file(self):
        if self.label_file:
            return self.label_file.filename
        base = self.image_path if self.image_path else self.filename
        if base.lower().endswith(".json"):
            return base
        lf = osp.splitext(base)[0] + ".json"
        if self.output_dir:
            lf = osp.join(self.output_dir, osp.basename(lf))
        return lf

    def get_image_file(self):
        if not self.filename.lower().endswith(".json"):
            image_file = self.filename
        else:
            image_file = self.image_path

        return image_file

    def _confirm_destructive_action(self, title, message):
        """破坏性操作的确认，默认焦点在"取消"，回车不会误删。

        勾选"本次会话不再询问"后，本次会话内后续删除将直接执行
        （仅存内存、不落盘，重启后恢复询问），在批量复核时既安全
        又不至于每次都被弹窗打断。
        """
        if getattr(self, "_skip_delete_confirm", False):
            return True
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(message)
        delete_btn = box.addButton(
            self.tr("Delete"), QMessageBox.ButtonRole.DestructiveRole
        )
        cancel_btn = box.addButton(
            self.tr("Cancel"), QMessageBox.ButtonRole.RejectRole
        )
        box.setDefaultButton(cancel_btn)
        checkbox = QCheckBox(self.tr("本次会话不再询问"))
        box.setCheckBox(checkbox)
        box.exec()
        if box.clickedButton() != delete_btn:
            return False
        if checkbox.isChecked():
            self._skip_delete_confirm = True
        return True

    def delete_file(self):
        mb = QtWidgets.QMessageBox
        if self._config.get("keep_prev", False):
            mb.warning(
                self,
                self.tr("Attention"),
                self.tr(
                    "Please disable 'Keep Previous Annotation' before deleting the label file."
                ),
                mb.StandardButton.Ok,
            )
            return

        msg = self.tr(
            "当前标签文件将移到图片目录下的 _delete_ 文件夹，可从该目录找回。\n"
            "确定删除吗？"
        )
        if not self._confirm_destructive_action(self.tr("Attention"), msg):
            return

        label_file = self.get_label_file()
        if osp.exists(label_file):
            image_file = None
            try:
                image_file = self.get_image_file()
            except Exception:
                image_file = None
            folder_hint = (
                osp.dirname(image_file) if image_file else osp.dirname(label_file)
            )
            dest = move_file_to_delete_folder(label_file, folder_hint)
            logger.info(f"Label file is moved to: {dest}")

            item = self.file_list_widget.currentItem()
            if item is not None:
                self._set_file_item_annotated(item, False, negative=False)
                self._set_file_item_checked(item, False)

            filename = self.filename
            self.reset_state()
            self.filename = filename
            if self.filename:
                self.load_file(self.filename)

    def delete_image_file(self):
        if len(self.image_list) < 2:
            self.status(
                self.tr(
                    "至少需要两张图片才能删除图片文件："
                    "删除后会自动切到相邻图片。"
                ),
                4000,
            )
            return

        mb = QtWidgets.QMessageBox
        if self._config.get("keep_prev", False):
            mb.warning(
                self,
                self.tr("Attention"),
                self.tr(
                    "Please disable 'Keep Previous Annotation' before deleting the image file."
                ),
                mb.StandardButton.Ok,
            )
            return

        msg = self.tr(
            "You are about to permanently delete this image file, "
            "proceed anyway?"
        )
        if not self._confirm_destructive_action(self.tr("Attention"), msg):
            return

        image_file = self.get_image_file()
        if osp.exists(image_file):
            image_path, image_name = osp.split(image_file)
            save_path = osp.join(image_path, "..", "_delete_")
            os.makedirs(save_path, exist_ok=True)
            save_file = osp.join(save_path, image_name)
            shutil.move(image_file, save_file)
            logger.info(f"Image file is moved to: {osp.realpath(save_file)}")

            label_dir_path = osp.dirname(self.filename)
            if self.output_dir:
                label_dir_path = self.output_dir
            label_name = osp.splitext(image_name)[0] + ".json"
            label_file = osp.join(label_dir_path, label_name)
            if not osp.exists(label_file):
                label_file = osp.join(osp.dirname(image_file), label_name)
            if osp.exists(label_file):
                os.remove(label_file)
                logger.info(f"Label file is removed: {image_file}")

            filename = None
            if self.filename is None:
                filename = self.image_list[0]
            else:
                current_index = self.fn_to_index[str(self.filename)]
                if current_index + 1 < len(self.image_list):
                    filename = self.image_list[current_index + 1]
                else:
                    filename = self.image_list[0]

            self.reset_state()
            if osp.isfile(image_path):
                image_path = osp.dirname(image_path)
            self.import_image_folder(image_path)

            self.filename = filename
            if self.filename:
                self.load_file(self.filename)

    # Message Dialogs. #
    def has_labels(self):
        if self.no_shape():
            self.error_message(
                "No objects labeled",
                "You must label at least one object to save the file.",
            )
            return False
        return True

    def has_label_file(self):
        if self.filename is None:
            return False

        label_file = self.get_label_file()
        return osp.exists(label_file)

    def may_continue(self, silent=False):
        if not self.dirty:
            return True
        # When auto_save is on, switching between images should not break
        # the annotation flow with a dialog on every single image: save
        # silently instead. Closing/loading a different file still asks,
        # so a mis-click on close can never throw work away.
        # Only the plain folder mode opts in — the `--output` mode keeps
        # its own semantics.
        if silent and self._config.get("auto_save") and not self.output_file:
            self.save_file()
            return not self.dirty
        mb = QtWidgets.QMessageBox
        msg = self.tr(
            f'Save annotations to "{self.filename!r}" before closing?'
        )
        answer = mb.question(
            self,
            self.tr("Save annotations?"),
            msg,
            mb.StandardButton.Save
            | mb.StandardButton.Discard
            | mb.StandardButton.Cancel,
            mb.StandardButton.Save,
        )
        if answer == mb.StandardButton.Discard:
            return True
        if answer == mb.StandardButton.Save:
            self.save_file()
            return True
        # answer == mb.Cancel
        return False

    def error_message(self, title, message):
        return QtWidgets.QMessageBox.critical(
            self, title, f"<p><b>{title}</b></p>{message}"
        )

    def current_path(self):
        return osp.dirname(str(self.filename)) if self.filename else "."

    def toggle_visibility_shapes(self, value):
        for index, item in enumerate(self.label_list):
            item.setCheckState(
                Qt.CheckState.Checked if value else Qt.CheckState.Unchecked
            )
            self.label_list[index].shape().visible = True if value else False
        self._config["show_shapes"] = value
        self._update_select_toggle_button_tooltip()
        if (
            hasattr(self, "navigator_dialog")
            and self.navigator_dialog.isVisible()
        ):
            self.update_navigator_shapes()

    def remove_selected_point(self):
        self.canvas.remove_selected_point()
        self.canvas.update()
        if self.canvas.h_shape is not None and not self.canvas.h_shape.points:
            self.canvas.delete_shape(self.canvas.h_shape)
            self.remove_labels([self.canvas.h_shape])
            self.set_dirty()
            if self.no_shape():
                for action in self.actions.on_shapes_present:
                    action.setEnabled(False)

    def delete_selected_shape(self):
        group_shapes = self.canvas._active_group_shapes()
        deleted = None
        if group_shapes:
            answer = QtWidgets.QMessageBox.warning(
                self,
                self.tr("Delete Group"),
                self.tr(
                    "Deleting this group will remove %d shapes. "
                    "You can undo this with Ctrl+Z. Do you want to continue?"
                )
                % len(group_shapes),
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            deleted = self.canvas.delete_selected()
        else:
            # Guard against deleting many objects at once (e.g. an
            # accidental multi-selection followed by Delete).
            deletable = [
                shape
                for shape in self.canvas.selected_shapes
                if not shape.locked and shape in self.canvas.shapes
            ]
            if len(deletable) > 1:
                answer = QtWidgets.QMessageBox.warning(
                    self,
                    self.tr("Delete Shapes"),
                    self.tr(
                        "Delete %d selected shapes? "
                        "You can undo this with Ctrl+Z."
                    )
                    % len(deletable),
                    QtWidgets.QMessageBox.StandardButton.Yes
                    | QtWidgets.QMessageBox.StandardButton.No,
                    QtWidgets.QMessageBox.StandardButton.No,
                )
                if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                    return
            deleted = self.canvas.delete_selected()
            if deleted and len(deleted) == 1:
                self.status(
                    self.tr("Deleted 1 object. Undo with Ctrl+Z.")
                )
        self.remove_labels(deleted)
        self.shape_selection_changed(self.canvas.selected_shapes)
        self.set_dirty()
        if self.no_shape():
            for action in self.actions.on_shapes_present:
                action.setEnabled(False)

    def copy_shape(self):
        self.canvas.end_move(copy=True)
        self.label_list.setUpdatesEnabled(False)
        try:
            for shape in self.canvas.selected_shapes:
                self.add_label(shape, refresh_filters=False)
        finally:
            self.label_list.setUpdatesEnabled(True)
        if self.canvas.selected_shapes:
            self._refresh_shape_filters()
        self.label_list.clearSelection()
        self.set_dirty()

    def move_shape(self):
        self.canvas.end_move(copy=False)
        self.set_dirty()

    def open_folder_dialog(self, _value=False, dirpath=None):
        if not self.may_continue():
            return

        default_open_dir_path = dirpath if dirpath else "."
        if self.last_open_dir and osp.exists(self.last_open_dir):
            default_open_dir_path = self.last_open_dir
        else:
            default_open_dir_path = (
                osp.dirname(self.filename) if self.filename else "."
            )

        target_dir_path = str(
            QtWidgets.QFileDialog.getExistingDirectory(
                self,
                self.tr("%s - Open Directory") % __appname__,
                default_open_dir_path,
                QtWidgets.QFileDialog.Option.ShowDirsOnly
                | QtWidgets.QFileDialog.Option.DontResolveSymlinks,
            )
        )
        self.import_image_folder(target_dir_path)

    @property
    def image_list(self):
        lst = []
        for i in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(i)
            lst.append(item.text())
        return lst

    def import_dropped_image_files(self, image_files):
        extensions = utils.get_supported_image_extensions()

        self.filename = None
        valid_files = []
        for file in image_files:
            if file in self.fn_to_index or not file.lower().endswith(
                tuple(extensions)
            ):
                continue
            valid_files.append(file)
            label_file = osp.splitext(file)[0] + ".json"
            if self.output_dir:
                label_file_without_path = osp.basename(label_file)
                label_file = self.output_dir + "/" + label_file_without_path
            item = self._create_file_list_item(file, label_file)
            self.file_list_widget.addItem(item)
            self.fn_to_index[file] = self.file_list_widget.count() - 1

        if self.file_list_widget.count() > 1:
            self.actions.open_next_image.setEnabled(True)
            self.actions.open_prev_image.setEnabled(True)
            self.actions.open_next_unchecked_image.setEnabled(True)
            self.actions.open_prev_unchecked_image.setEnabled(True)

        self.toggle_actions(True)
        self.open_next_image()

        if valid_files and self._config.get("exif_scan_enabled", True):
            self.async_exif_scanner.start_scan(valid_files)

    def import_image_folder(self, dirpath, pattern=None, load=True):
        if not self.may_continue() or not dirpath:
            return

        self.last_open_dir = dirpath
        self._record_recent_dir(dirpath)
        self.filename = None
        self.file_list_widget.clear()
        # Rows are renumbered below, so the old folder's entries must go too:
        # a stale index makes _current_file_item() point at another image.
        self.fn_to_index.clear()
        image_files = []
        label_files = []

        search_pattern = parse_search_pattern(pattern) if pattern else None

        # Populate the list first (pure fs metadata, cheap), then refresh
        # the per-file review "checked" dots in the background so a large
        # folder does not freeze the UI for seconds.
        self.async_label_checker.stop()
        self.file_list_widget.setUpdatesEnabled(False)
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
                            if self.output_dir:
                                label_file_without_path = osp.basename(
                                    label_file
                                )
                                label_file = (
                                    self.output_dir
                                    + "/"
                                    + label_file_without_path
                                )

                            if not matches_label_attribute(
                                filename, label_file, search_pattern
                            ):
                                continue

                image_files.append(filename)
                label_file = osp.splitext(filename)[0] + ".json"
                if self.output_dir:
                    label_file_without_path = osp.basename(label_file)
                    label_file = self.output_dir + "/" + label_file_without_path
                label_files.append(label_file)
                item = self._create_file_list_item(
                    filename, label_file, read_checked=False
                )
                self.file_list_widget.addItem(item)
                self.fn_to_index[filename] = self.file_list_widget.count() - 1
        finally:
            self.file_list_widget.setUpdatesEnabled(True)

        self.actions.open_next_image.setEnabled(True)
        self.actions.open_prev_image.setEnabled(True)
        self.actions.open_next_unchecked_image.setEnabled(True)
        self.actions.open_prev_unchecked_image.setEnabled(True)
        self.toggle_actions(True)
        self.open_next_image(load=load)

        if image_files and self._config.get("exif_scan_enabled", True):
            self.async_exif_scanner.start_scan(image_files)
        self._refresh_file_panel()
        if pattern is None and image_files:
            self._load_classes_from_folder(dirpath)
            self._maybe_prompt_missing_labels()
            self._maybe_show_smart_tools_guide(dirpath)

        # Background "checked" dot refresh (after rows exist so the batch
        # callback can address them by index).
        if label_files:
            self.async_label_checker.start(
                label_files, on_batch=self._apply_checked_batch
            )

    def _apply_checked_batch(self, start_index, info_list):
        """Delegates to filelist.controller (AsyncLabelChecker callback)."""
        # Built on demand: the controller is stateless, and light test
        # stubs never carry an instance.
        FileReviewController(self).apply_checked_batch(start_index, info_list)

    def _load_classes_from_folder(self, image_dir):
        """Make the label panel follow ``classes.txt`` of the opened folder.

        Two problems are fixed here:

        * opening a folder used to ignore ``classes.txt`` entirely, so the
          "还没有类别" prompt appeared even when the folder declared classes;
        * the panel survived folder switches, so labels from a previously
          opened folder stayed in the list and looked like classes that were
          never in the file.

        A folder that ships ``classes.txt`` is now authoritative and replaces
        the panel. Folders without one are left alone, so labels from the
        config keep working as before.
        """
        if not image_dir:
            return []

        names = []
        for candidate_dir in (self.output_dir, image_dir):
            if not candidate_dir:
                continue
            names = load_class_names(
                osp.join(candidate_dir, CLASSES_FILENAME)
            )
            if names:
                break
        if not names:
            return []

        if self._panel_label_names() == names:
            return names

        self.unique_label_list.clear()
        self.load_labels(names, clear_existing=False)
        self._reset_label_dialog_labels(names)
        logger.info(
            f"Loaded {len(names)} classes from {CLASSES_FILENAME}: "
            f"{', '.join(names)}"
        )
        return names

    def _panel_label_names(self):
        """Labels currently shown in the panel, in display order."""
        names = []
        for row in range(self.unique_label_list.count()):
            item = self.unique_label_list.item(row)
            if item is None:
                continue
            label = item.data(Qt.ItemDataRole.UserRole)
            if label:
                names.append(str(label))
        return names

    def _reset_label_dialog_labels(self, labels):
        """Replace the label dialog's suggestion list with ``labels``."""
        dialog = getattr(self, "label_dialog", None)
        if dialog is None or not labels:
            return
        label_list = getattr(dialog, "label_list", None)
        if label_list is None:
            return
        label_list.clear()
        label_list.addItems(labels)
        if getattr(dialog, "_sort_labels", False):
            try:
                dialog.sort_labels()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Failed to sort label dialog list: {e}")

    def _maybe_prompt_missing_labels(self):
        if self.unique_label_list.count() > 0:
            self._pending_missing_labels_prompt = False
            return
        if not self.isVisible():
            if not getattr(self, "_pending_missing_labels_prompt", False):
                self._pending_missing_labels_prompt = True
                QtCore.QTimer.singleShot(800, self._maybe_prompt_missing_labels)
            return
        self._pending_missing_labels_prompt = False
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(self.tr("还没有类别"))
        box.setIcon(QtWidgets.QMessageBox.Icon.Information)
        box.setText(
            self.tr(
                "当前没有预定义类别。导入 classes.txt 或打开标签管理器后再画框，"
                "可以减少每张图重复输入。"
            )
        )
        import_btn = box.addButton(
            self.tr("导入 classes.txt"),
            QtWidgets.QMessageBox.ButtonRole.AcceptRole,
        )
        manage_btn = box.addButton(
            self.tr("打开标签管理器"),
            QtWidgets.QMessageBox.ButtonRole.ActionRole,
        )
        box.addButton(
            self.tr("稍后再说"), QtWidgets.QMessageBox.ButtonRole.RejectRole
        )
        box.exec()
        clicked = box.clickedButton()
        if clicked == import_btn:
            utils.upload_label_classes_file(self)
        elif clicked == manage_btn:
            self.label_manager()

    def toggle_auto_labeling_widget(self):
        """Toggle auto labeling widget visibility."""
        if self.auto_labeling_widget.isVisible():
            self.auto_labeling_widget.hide()
            self.actions.run_all_images.setEnabled(False)
        else:
            self.auto_labeling_widget.show()
            self.actions.run_all_images.setEnabled(True)
        self.update_thumbnail_display()
        self.update_labeling_instruction()

    @pyqtSlot()
    def _current_model_identity(self):
        """Name of the loaded auto-labeling model, used for shape provenance."""
        manager = getattr(self.auto_labeling_widget, "model_manager", None)
        return model_display_name(getattr(manager, "loaded_model_config", None))

    def _current_model_version(self):
        """Digest of the loaded model's weights file, or None if unidentified.

        The name alone cannot tell a retrained model from the one it replaced at
        the same path, which is the common case for the loop's ``best.onnx``.
        Memoised on (path, size, mtime) so rewriting the file yields a new
        digest instead of a cached one.
        """
        manager = getattr(self.auto_labeling_widget, "model_manager", None)
        config = getattr(manager, "loaded_model_config", None)
        path = resolve_model_path(config)
        if not path:
            return None
        try:
            stat = os.stat(path)
            token = (path, stat.st_size, stat.st_mtime_ns)
        except OSError:
            return None
        cached = getattr(self, "_model_version_cache", None)
        if cached and cached[0] == token:
            return cached[1]
        digest = weight_digest(path)
        self._model_version_cache = (token, digest)
        if digest:
            logger.info(
                f"Model weights digest for {osp.basename(path)}: {digest}"
            )
        return digest

    def delete_reported_shapes(self, indices):
        """Mirror a bulk cleanup on the image that is currently open.

        The deletion is applied to the canvas rather than by reloading the file,
        because ``load_file`` resets the shape history: this way one Ctrl+Z
        brings the whole batch back. Only shapes that are still unlocked and
        still attributable to another model are removed, so a box the user
        claimed in between stays.
        """
        current_model = self._current_model_identity()
        current_version = self._current_model_version()
        shapes = self.canvas.shapes
        doomed = []
        for index in sorted(set(indices or [])):
            if not 0 <= index < len(shapes):
                continue
            shape = shapes[index]
            if shape in doomed or not is_deletable_stale_shape(
                shape, current_model, current_version
            ):
                continue
            doomed.append(shape)
        if not doomed:
            return 0

        # Pre-state first: undo restores the newest-but-one snapshot, so the
        # batch has to be in the stack before it disappears from the canvas.
        self.canvas.store_shapes()
        remaining = [shape for shape in shapes if shape not in doomed]
        # Dropping the list items re-syncs the canvas through
        # label_order_changed(), which pushes the resulting snapshot itself.
        # Only correct the canvas here when that did not happen: a second
        # identical snapshot would cost the user two presses of Ctrl+Z.
        self.remove_labels(doomed)
        if self.canvas.shapes != remaining:
            self.canvas.load_shapes(remaining)
        self.canvas.selected_shapes = [
            shape
            for shape in self.canvas.selected_shapes
            if shape not in doomed
        ]
        self.canvas.update()
        self.shape_selection_changed(self.canvas.selected_shapes)
        self.set_dirty()
        self.actions.undo.setEnabled(self.canvas.is_shape_restorable)
        self.actions.redo.setEnabled(self.canvas.is_shape_redoable)
        if self.no_shape():
            for action in self.actions.on_shapes_present:
                action.setEnabled(False)
        return len(doomed)

    def new_shapes_from_auto_labeling(self, auto_labeling_result):
        """Apply auto labeling results to the current image."""
        if not self.image or not self.image_path:
            return

        result_image_path = getattr(auto_labeling_result, "image_path", None)
        if result_image_path and self.filename:
            current_filename = osp.normpath(osp.abspath(self.filename))
            result_filename = osp.normpath(osp.abspath(result_image_path))
            if result_filename != current_filename:
                logger.warning(
                    "Ignore stale auto labeling result for "
                    f"{result_filename}; current file is {current_filename}"
                )
                return

        new_shapes = auto_labeling_result.shapes
        predictions = getattr(auto_labeling_result, "predictions", None)
        if predictions is not None:
            # A classifier returns a whole-image suggestion rather than shapes;
            # handling it here keeps it out of the shape-replacement logic,
            # which would otherwise clear the canvas on an empty shape list.
            self._apply_model_predictions(predictions)
            return
        stamp_model_shapes(
            new_shapes,
            self._current_model_identity(),
            self._current_model_version(),
        )
        # YOLO-consistent guard: a prediction that found *nothing* must not
        # silently erase human ground truth. When the model outputs no
        # shapes (empty/background or missed detection) and the current
        # image already has annotations, we keep them untouched instead of
        # clearing them (locked shapes were already preserved, now the
        # default replace path is safe for the empty-result case too).
        if (
            auto_labeling_result.replace
            and not new_shapes
            and any(
                not shape.locked for shape in self.canvas.shapes
            )
        ):
            logger.info(
                "Auto labeling found no objects on this image; keeping "
                "existing annotations (empty results never erase "
                "ground truth)."
            )
            return

        # Clear existing shapes
        if auto_labeling_result.replace:
            locked_shapes = [
                shape for shape in self.canvas.shapes if shape.locked
            ]
            self.label_list.clear()
            self.load_shapes(
                locked_shapes + new_shapes, replace=True
            )
        else:  # Just update existing shapes
            # Remove shapes with label AutoLabelingMode.OBJECT
            for shape in self.canvas.shapes:
                if shape.label == AutoLabelingMode.OBJECT:
                    item = self.label_list.find_item_by_shape(shape)
                    self.label_list.remove_item(item)
            self.load_shapes(new_shapes, replace=False)

        self.set_dirty()

    def clear_auto_labeling_marks(self):
        """Clear auto labeling marks from the current image."""
        # Clean up label list
        for shape in self.canvas.shapes:
            if shape.label in [
                AutoLabelingMode.OBJECT,
                AutoLabelingMode.ADD,
                AutoLabelingMode.REMOVE,
            ]:
                try:
                    item = self.label_list.find_item_by_shape(shape)
                    self.label_list.remove_item(item)
                except ValueError:
                    pass

        # Clean up unique label list
        for shape_label in [
            AutoLabelingMode.OBJECT,
            AutoLabelingMode.ADD,
            AutoLabelingMode.REMOVE,
        ]:
            for item in self.unique_label_list.find_items_by_label(
                shape_label
            ):
                self.unique_label_list.takeItem(
                    self.unique_label_list.row(item)
                )

        # Remove shapes from the canvas
        self.canvas.shapes = [
            shape
            for shape in self.canvas.shapes
            if shape.label
            not in [
                AutoLabelingMode.OBJECT,
                AutoLabelingMode.ADD,
                AutoLabelingMode.REMOVE,
            ]
        ]
        self.canvas.update()

    def find_last_label(self):
        """
        Find the last label in the label list.
        Exclude labels for auto labeling.
        """

        # Get from dialog history
        last_label = self.label_dialog.get_last_label()
        if last_label:
            return last_label

        # Get selected label from the label list
        items = self.label_list.selected_items()
        if items:
            shape = items[0].data(Qt.ItemDataRole.UserRole)
            return shape.label

        # Get the last label from the label list
        for item in reversed(self.label_list):
            shape = item.data(Qt.ItemDataRole.UserRole)
            if shape.label not in [
                AutoLabelingMode.OBJECT,
                AutoLabelingMode.ADD,
                AutoLabelingMode.REMOVE,
            ]:
                return shape.label

        # No label is found
        return ""

    def find_last_gid(self):
        last_gid = self.label_dialog.get_last_gid()
        if last_gid is not None:
            return last_gid

        for item in reversed(self.label_list):
            shape = item.data(Qt.ItemDataRole.UserRole)
            if (
                shape.label
                not in [
                    AutoLabelingMode.OBJECT,
                    AutoLabelingMode.ADD,
                    AutoLabelingMode.REMOVE,
                ]
                and shape.group_id is not None
            ):
                return shape.group_id
        return None

    def set_cache_auto_label(self):
        self.auto_labeling_widget.on_cache_auto_label_changed(
            self.cache_auto_label, self.cache_auto_label_group_id
        )

    def finish_auto_labeling_object(self):
        """Finish auto labeling object."""
        has_object, cache_label = False, None
        for shape in self.canvas.shapes:
            if shape.label == AutoLabelingMode.OBJECT:
                cache_label = shape.cache_label
                cache_description = shape.cache_description
                has_object = True
                break

        # If there is no object, do nothing
        if not has_object:
            return

        # Ask a label for the object
        text, flags, group_id, description, difficult, kie_linking = (
            "",
            {},
            None,
            None,
            False,
            [],
        )
        last_label = self.find_last_label()
        last_gid = (
            self.find_last_gid() if self._config["auto_use_last_gid"] else None
        )
        if self._config["auto_use_last_label"] and last_label:
            text = last_label
            if last_gid is not None:
                group_id = last_gid
        elif cache_label is not None:
            text = cache_label
            description = cache_description
        else:
            previous_text = self.label_dialog.edit.text()
            (
                text,
                flags,
                group_id,
                description,
                difficult,
                kie_linking,
            ) = self.label_dialog.pop_up(
                text=self.find_last_label(),
                flags={},
                group_id=last_gid,
                description=None,
                difficult=False,
                kie_linking=[],
                move_mode=self._config.get("move_mode", "auto"),
            )
            if not text:
                self.label_dialog.edit.setText(previous_text)
                return

        self.cache_auto_label = text
        self.cache_auto_label_group_id = group_id
        if not self.validate_label(text):
            self.error_message(
                self.tr("Invalid label"),
                self.tr("Invalid label '{}' with validation type '{}'").format(
                    text, self._config["validate_label"]
                ),
            )
            return

        if self.attributes and text:
            text = self.reset_attribute(text, shape)

        # Add to label history
        self.label_dialog.add_label_history(text)

        # Update label for the object
        updated_shapes = False
        for shape in self.canvas.shapes:
            if shape.label == AutoLabelingMode.OBJECT:
                updated_shapes = True
                shape.label = text
                shape.flags = flags
                shape.group_id = group_id
                shape.description = description
                shape.difficult = difficult
                shape.kie_linking = kie_linking
                # Update unique label list
                if not self.unique_label_list.find_items_by_label(shape.label):
                    unique_label_item = (
                        self.unique_label_list.create_item_from_label(
                            shape.label
                        )
                    )
                    self.unique_label_list.addItem(unique_label_item)
                    rgb = self._get_rgb_by_label(shape.label)
                    self.unique_label_list.set_item_label(
                        unique_label_item, shape.label, rgb, LABEL_OPACITY
                    )

                # Update label list
                self._update_shape_color(shape)
                item = self.label_list.find_item_by_shape(shape)
                if shape.group_id is None:
                    color = shape.fill_color.getRgb()[:3]
                    item.setText(
                        '{} <font color="#{:02x}{:02x}{:02x}">●</font>'.format(
                            html.escape(shape.label), *color
                        )
                    )
                else:
                    item.setText(
                        _format_label_list_text(shape.label, shape.group_id)
                    )

        # Clean up auto labeling objects
        self.clear_auto_labeling_marks()

        # Update shape colors
        for shape in self.canvas.shapes:
            self._update_shape_color(shape)
            color = shape.fill_color.getRgb()[:3]
            item = self.label_list.find_item_by_shape(shape)
            item.setText(_format_label_list_text(shape.label, shape.group_id))
            item.setBackground(QtGui.QColor(*color, LABEL_OPACITY))
            self.unique_label_list.update_item_color(
                shape.label, color, LABEL_OPACITY
            )

        if updated_shapes:
            self.set_dirty()

    def group_selected_shapes(self):
        self.canvas.group_selected_shapes()
        self.set_dirty()
        self.load_file(self.filename)

    def ungroup_selected_shapes(self):
        self.canvas.ungroup_selected_shapes()
        self.set_dirty()
        self.load_file(self.filename)

    def update_thumbnail_pixmap(self):
        if self.thumbnail_pixmap and not self.thumbnail_pixmap.isNull():
            width = self.thumbnail_image_label.width()
            if width > 0:
                self.thumbnail_image_label.setPixmap(
                    self.thumbnail_pixmap.scaledToWidth(
                        width,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    )
                )

    def update_thumbnail_display(self):
        self.thumbnail_pixmap = None
        self.thumbnail_image_label.clear()
        self.thumbnail_container.hide()

        model_config = (
            self.auto_labeling_widget.model_manager.loaded_model_config
        )
        supported_model_list = list(_THUMBNAIL_RENDER_MODELS.keys())
        if not (
            model_config
            and model_config.get("type") in supported_model_list
            and self.image_list
        ):
            return

        try:
            image_dir = osp.dirname(self.filename)
            parent_dir = osp.dirname(image_dir)
            base_name = osp.splitext(osp.basename(self.filename))[0]
            save_dir, _thumbnail_file_ext = _THUMBNAIL_RENDER_MODELS[
                model_config["type"]
            ]
            thumbnail_dir = osp.join(parent_dir, save_dir)
            thumbnail_path = osp.join(
                thumbnail_dir, base_name + _thumbnail_file_ext
            )
            if not osp.exists(thumbnail_path):
                return

            self.thumbnail_pixmap = QtGui.QPixmap(thumbnail_path)
            if not self.thumbnail_pixmap.isNull():
                self.thumbnail_container.show()
                self.update_thumbnail_pixmap()

        except Exception as e:
            logger.error(f"Failed to load thumbnail image: {str(e)}")

    def toggle_labels_visibility(self, checked):
        self.label_dock.setVisible(checked)

    def toggle_shapes_visibility(self, checked):
        self.shape_dock.setVisible(checked)


def _build_actions(widget):
    """Create every QAction and register them on widget.actions.

    Moved out of LabelingWidget.__init__ (split batch 4): pure
    assembly, everything is reached through the widget argument.
    """
    # Actions
    action = functools.partial(utils.new_action, widget)
    shortcuts = widget._config["shortcuts"]

    open_ = action(
        widget.tr("Open File"),
        widget.open_file,
        shortcuts["open"],
        "file",
        widget.tr("Open image or label file"),
    )
    opendir = action(
        widget.tr("Open Dir"),
        widget.open_folder_dialog,
        shortcuts["open_dir"],
        "open",
        widget.tr("Open Dir"),
    )
    open_next_image = action(
        widget.tr("Next Image"),
        widget.open_next_image,
        shortcuts["open_next"],
        "next",
        widget.tr("Open next image"),
        enabled=False,
    )
    open_prev_image = action(
        widget.tr("Prev Image"),
        widget.open_prev_image,
        shortcuts["open_prev"],
        "prev",
        widget.tr("Open prev image"),
        enabled=False,
    )
    open_next_unchecked_image = action(
        widget.tr("Next Unchecked Image"),
        widget.open_next_unchecked_image,
        shortcuts["open_next_unchecked"],
        "next",
        widget.tr("Open next unchecked image"),
        enabled=False,
    )
    open_prev_unchecked_image = action(
        widget.tr("Prev Unchecked Image"),
        widget.open_prev_unchecked_image,
        shortcuts["open_prev_unchecked"],
        "prev",
        widget.tr("Open previous unchecked image"),
        enabled=False,
    )
    save = action(
        widget.tr("Save"),
        widget.save_file,
        shortcuts["save"],
        "save",
        widget.tr("Save labels to file"),
        enabled=False,
    )
    save_as = action(
        widget.tr("Save As"),
        widget.save_file_as,
        shortcuts["save_as"],
        "save-as",
        widget.tr("Save labels to a different file"),
        enabled=False,
    )
    run_all_images = action(
        widget.tr("Auto Run"),
        lambda: utils.run_all_images(widget),
        shortcuts["auto_run"],
        "auto-run",
        widget.tr("Auto run all images at once"),
        enabled=False,
    )
    delete_file = action(
        widget.tr("Delete File"),
        widget.delete_file,
        shortcuts["delete_file"],
        "delete",
        widget.tr("Delete current label file"),
        enabled=False,
    )
    delete_image_file = action(
        widget.tr("Delete Image File"),
        widget.delete_image_file,
        shortcuts["delete_image_file"],
        "delete",
        widget.tr("Delete current image file"),
        enabled=True,
    )
    data_audit = action(
        widget.tr("数据体检"),
        lambda: run_data_audit(widget),
        None,
        "icon",
        widget.tr(
            "Scan the folder for unlabeled images, empty/corrupted "
            "labels and orphan label files"
        ),
        enabled=True,
    )
    smart_calibrate = action(
        widget.tr("1. 阈值校准"),
        lambda: run_threshold_calibration(widget),
        None,
        "settings",
        widget.tr("推荐先做：按各类置信度分布生成自动接受 / 建议复核阈值"),
        enabled=True,
    )
    smart_analysis = action(
        widget.tr("2. 数据智能分析"),
        lambda: run_smart_analysis(widget),
        None,
        "overview",
        widget.tr("阈值校准后再做：难例排序、重复图片检测与配平建议"),
        enabled=True,
    )
    smart_missing_scan = action(
        widget.tr("3. 漏标扫描"),
        lambda: run_missing_scan(widget),
        None,
        "search",
        widget.tr("智能分析后再做：用当前模型找出置信度高但没有标注的目标"),
        enabled=True,
    )
    smart_iteration = action(
        widget.tr("4. 迭代收益看板"),
        lambda: show_iteration_dashboard(widget),
        None,
        "loop",
        widget.tr("最后查看：每轮训练→回灌的边际收益与下一步建议"),
        enabled=True,
    )
    smart_review = action(
        widget.tr("5. 智能复核（下一张待复核）"),
        lambda: run_review_jump(widget),
        None,
        "check",
        widget.tr("按不确定性优先级跳到下一张待复核的图片（再次点击可继续跳）"),
        enabled=True,
    )
    smart_propagate = action(
        widget.tr("6. 标注传播（上一张→当前图）"),
        widget._propagate_previous_labels,
        None,
        "copy",
        widget.tr("把上一张已标注图片的框按比例复制到当前图片，自动跳过重复框"),
        enabled=True,
    )
    smart_archive = action(
        widget.tr("7. 一键去重归档"),
        lambda: run_duplicate_archive(widget),
        None,
        "trash",
        widget.tr("把近重复图片及其标注移动到「._duplicates_archive」文件夹"),
        enabled=True,
    )
    smart_advice = action(
        widget.tr("8. 训练建议"),
        lambda: run_training_advice(widget),
        None,
        "brain",
        widget.tr("训练前预检 + 基于当前数据与历史轮次推荐 epochs/batch/imgsz 初值"),
        enabled=True,
    )
    smart_template = action(
        widget.tr("9. 智能模板预标注（批量）"),
        lambda: run_template_propagation(widget),
        None,
        "labels",
        widget.tr("为未标注图片按相似度匹配已标注模板，批量生成预标注后再人工确认"),
        enabled=True,
    )
    smart_stale_audit = action(
        widget.tr("10. 旧轮模型框盘点"),
        lambda: run_stale_model_audit(widget),
        None,
        "layers",
        widget.tr("列出由其它模型留下、可考虑清理的框（只报告，不删除）"),
        enabled=True,
    )
    smart_restore_backup = action(
        widget.tr("11. 从备份恢复标注（撤销批量删除）"),
        lambda: run_backup_restore(widget),
        None,
        "undo",
        widget.tr(
            "把 .label_backups 里的某一次快照写回标注目录；"
            "被覆盖的文件会先生成一个新快照"
        ),
        enabled=True,
    )
    toggle_annotation_checked = action(
        widget.tr("Mark as Checked"),
        widget.set_annotation_checked,
        shortcuts.get("toggle_annotation_checked"),
        None,
        widget.tr("Mark current annotation as checked"),
        checkable=True,
        enabled=False,
    )
    mark_checked_and_next = action(
        widget.tr("检查完成并下一张"),
        widget.mark_checked_and_next,
        shortcuts["mark_checked_and_next"],
        None,
        widget.tr("将当前图片标为已检查，并跳到下一张未检查图片"),
        enabled=False,
    )
    mark_rejected_and_next = action(
        widget.tr("打回并下一张"),
        widget.mark_rejected_and_next,
        shortcuts.get("mark_rejected_and_next"),
        None,
        widget.tr("将当前图片标为需返工，并跳到下一张未检查图片"),
        enabled=False,
    )
    # Menu-only on purpose: no shortcut key is invented here, so there is no
    # config entry that could drift from a real binding.
    confirm_classification = action(
        widget.tr("确认分类建议"),
        widget.confirm_classification,
        None,
        None,
        widget.tr("把分类模型的整图建议写入图片类别（flags）"),
        enabled=False,
    )

    change_output_dir = action(
        widget.tr("Change Output Dir"),
        slot=widget.change_output_dir_dialog,
        shortcut=shortcuts["save_to"],
        icon="open",
        tip=widget.tr("Change where annotations are loaded/saved"),
    )

    save_auto = action(
        text=widget.tr("Save Automatically"),
        slot=lambda x: widget._config.update({"auto_save": x}),
        icon=None,
        tip=widget.tr("Save automatically"),
        checkable=True,
        enabled=True,
        checked=widget._config["auto_save"],
    )

    save_with_image_data = action(
        text=widget.tr("Save With Image Data"),
        slot=lambda x: widget._config.update({"store_data": x}),
        icon=None,
        tip=widget.tr("Save image data in label file"),
        checkable=True,
        checked=widget._config["store_data"],
    )

    close = action(
        widget.tr("Close"),
        widget.close_file,
        shortcuts["close"],
        "cancel",
        widget.tr("Close current file"),
    )

    keep_prev_mode = action(
        widget.tr("Keep Previous Annotation"),
        lambda x: widget._config.update({"keep_prev": x}),
        shortcuts["toggle_keep_prev_mode"],
        None,
        widget.tr('Toggle "Keep Previous Annotation" mode'),
        checkable=True,
        checked=widget._config["keep_prev"],
    )

    auto_use_last_label_mode = action(
        widget.tr("Auto Use Last Label"),
        lambda x: widget._config.update({"auto_use_last_label": x}),
        shortcuts["toggle_auto_use_last_label"],
        None,
        widget.tr('Toggle "Auto Use Last Label" mode'),
        checkable=True,
        checked=widget._config["auto_use_last_label"],
    )

    auto_use_last_gid_mode = action(
        widget.tr("Auto Use Last Group ID"),
        lambda x: widget._config.update({"auto_use_last_gid": x}),
        shortcuts["toggle_auto_use_last_gid"],
        None,
        widget.tr('Toggle "Auto Use Last Group ID" mode'),
        checkable=True,
        checked=widget._config["auto_use_last_gid"],
    )

    use_system_clipboard = action(
        widget.tr("Use System Clipboard"),
        widget.toggle_system_clipboard,
        tip=widget.tr("Use system clipboard for copy and paste"),
        checkable=True,
        checked=widget._config["system_clipboard"],
        enabled=True,
    )

    visibility_shapes_mode = action(
        widget.tr("Visibility Shapes"),
        widget.toggle_visibility_shapes,
        shortcuts["toggle_visibility_shapes"],
        None,
        widget.tr('Toggle "Visibility Shapes" mode'),
        checkable=True,
        checked=widget._config["show_shapes"],
    )

    create_mode = action(
        widget.tr("Create Polygons"),
        lambda: widget.toggle_draw_mode(False, create_mode="polygon"),
        shortcuts["create_polygon"],
        "polygon",
        widget.tr("Start drawing polygons"),
        enabled=False,
    )
    create_brush_polygon_mode = action(
        widget.tr("Create Brush Polygons"),
        widget.toggle_brush_polygon_mode,
        shortcuts["create_brush_polygon"],
        "brush_polygon",
        widget.tr("Toggle brush mode for drawing polygons"),
        enabled=False,
    )
    create_rectangle_mode = action(
        widget.tr("Create Rectangle"),
        lambda: widget.toggle_draw_mode(False, create_mode="rectangle"),
        shortcuts["create_rectangle"],
        "rectangle",
        widget.tr("Start drawing rectangles"),
        enabled=False,
    )
    create_point_mode = action(
        widget.tr("Create Point"),
        lambda: widget.toggle_draw_mode(False, create_mode="point"),
        shortcuts["create_point"],
        "point",
        widget.tr("Start drawing points"),
        enabled=False,
    )
    # These six existed only as config keys: the shortcuts-help dialog
    # advertised them, but no QAction ever bound them, so the shapes were
    # reachable through the digit-shortcut manager alone.
    create_cuboid_mode = action(
        widget.tr("创建立方体"),
        lambda: widget.toggle_draw_mode(False, create_mode="cuboid"),
        shortcuts["create_cuboid"],
        None,
        widget.tr("开始画立方体"),
        enabled=False,
    )
    create_rotation_mode = action(
        widget.tr("创建旋转框"),
        lambda: widget.toggle_draw_mode(False, create_mode="rotation"),
        shortcuts["create_rotation"],
        None,
        widget.tr("开始画旋转框"),
        enabled=False,
    )
    create_quadrilateral_mode = action(
        widget.tr("创建四边形"),
        lambda: widget.toggle_draw_mode(False, create_mode="quadrilateral"),
        shortcuts["create_quadrilateral"],
        None,
        widget.tr("开始画四边形"),
        enabled=False,
    )
    create_circle_mode = action(
        widget.tr("创建圆"),
        lambda: widget.toggle_draw_mode(False, create_mode="circle"),
        shortcuts["create_circle"],
        None,
        widget.tr("开始画圆"),
        enabled=False,
    )
    create_line_mode = action(
        widget.tr("创建线段"),
        lambda: widget.toggle_draw_mode(False, create_mode="line"),
        shortcuts["create_line"],
        None,
        widget.tr("开始画线段"),
        enabled=False,
    )
    create_linestrip_mode = action(
        widget.tr("创建折线"),
        lambda: widget.toggle_draw_mode(False, create_mode="linestrip"),
        shortcuts["create_linestrip"],
        None,
        widget.tr("开始画折线"),
        enabled=False,
    )
    digit_shortcut_0 = action(
        widget.tr("Digit Shortcut 0"),
        lambda: widget.create_digit_mode(0),
        "0",
        "digit0",
        enabled=False,
    )
    digit_shortcut_1 = action(
        widget.tr("Digit Shortcut 1"),
        lambda: widget.create_digit_mode(1),
        "1",
        "digit1",
        enabled=False,
    )
    digit_shortcut_2 = action(
        widget.tr("Digit Shortcut 2"),
        lambda: widget.create_digit_mode(2),
        "2",
        "digit2",
        enabled=False,
    )
    digit_shortcut_3 = action(
        widget.tr("Digit Shortcut 3"),
        lambda: widget.create_digit_mode(3),
        "3",
        "digit3",
        enabled=False,
    )
    digit_shortcut_4 = action(
        widget.tr("Digit Shortcut 4"),
        lambda: widget.create_digit_mode(4),
        "4",
        "digit4",
        enabled=False,
    )
    digit_shortcut_5 = action(
        widget.tr("Digit Shortcut 5"),
        lambda: widget.create_digit_mode(5),
        "5",
        "digit5",
        enabled=False,
    )
    digit_shortcut_6 = action(
        widget.tr("Digit Shortcut 6"),
        lambda: widget.create_digit_mode(6),
        "6",
        "digit6",
        enabled=False,
    )
    digit_shortcut_7 = action(
        widget.tr("Digit Shortcut 7"),
        lambda: widget.create_digit_mode(7),
        "7",
        "digit7",
        enabled=False,
    )
    digit_shortcut_8 = action(
        widget.tr("Digit Shortcut 8"),
        lambda: widget.create_digit_mode(8),
        "8",
        "digit8",
        enabled=False,
    )
    digit_shortcut_9 = action(
        widget.tr("Digit Shortcut 9"),
        lambda: widget.create_digit_mode(9),
        "9",
        "digit9",
        enabled=False,
    )
    edit_mode = action(
        widget.tr("Edit Object"),
        widget.set_edit_mode,
        shortcuts["edit_polygon"],
        "edit",
        widget.tr("Move and edit the selected polygons"),
        enabled=False,
    )
    edit_brush_mode = action(
        widget.tr("Edit Brush"),
        lambda checked: widget.toggle_brush_mode(checked),
        shortcuts.get("edit_brush_mode", "Shift+B"),
        "brush",
        widget.tr(
            "Select one polygon, then paint to add, hold Ctrl to erase, "
            "and scroll to resize the brush"
        ),
        enabled=False,
        checkable=True,
        checked=False,
    )
    group_selected_shapes = action(
        widget.tr("Group Selected Shapes"),
        widget.group_selected_shapes,
        shortcuts["group_selected_shapes"],
        None,
        widget.tr("Group shapes by assigning a same group_id"),
        enabled=True,
    )
    ungroup_selected_shapes = action(
        widget.tr("Ungroup Selected Shapes"),
        widget.ungroup_selected_shapes,
        shortcuts["ungroup_selected_shapes"],
        None,
        widget.tr("Ungroup shapes"),
        enabled=True,
    )

    delete = action(
        widget.tr("Delete"),
        widget.delete_selected_shape,
        shortcuts["delete_polygon"],
        "cancel",
        widget.tr("Delete the selected polygons"),
        enabled=False,
    )
    duplicate = action(
        widget.tr("Duplicate Polygons"),
        widget.duplicate_selected_shape,
        shortcuts["duplicate_polygon"],
        "copy",
        widget.tr("Create a duplicate of the selected polygons"),
        enabled=False,
    )
    copy = action(
        widget.tr("Copy Object"),
        widget.copy_selected_shape,
        shortcuts["copy_polygon"],
        "copy",
        widget.tr("Copy selected polygons to clipboard"),
        enabled=False,
    )
    paste = action(
        widget.tr("Paste Object"),
        widget.paste_selected_shape,
        shortcuts["paste_polygon"],
        "paste",
        widget.tr("Paste copied polygons"),
        enabled=widget._config["system_clipboard"],
    )
    undo_last_point = action(
        widget.tr("Undo last point"),
        widget.canvas.undo_last_point,
        shortcuts["undo_last_point"],
        "undo",
        widget.tr("Undo last drawn point"),
        enabled=False,
    )
    remove_point = action(
        text=widget.tr("Remove Selected Point"),
        slot=widget.remove_selected_point,
        shortcut=shortcuts["remove_selected_point"],
        icon="edit",
        tip=widget.tr("Remove selected point from polygon"),
        enabled=False,
    )

    undo = action(
        widget.tr("Undo"),
        widget.undo_shape_edit,
        shortcuts["undo"],
        "undo",
        widget.tr("Undo last add and edit of shape"),
        enabled=False,
    )
    redo = action(
        widget.tr("Redo"),
        widget.redo_shape_edit,
        shortcuts.get("redo", "Ctrl+Shift+Z"),
        "redo",
        widget.tr("Redo the last undone edit of shape"),
        enabled=False,
    )
    hide_selected_polygons = action(
        widget.tr("Hide Selected Polygons"),
        widget.hide_selected_polygons,
        shortcuts["hide_selected_polygons"],
        None,
        widget.tr("Hide selected polygons"),
        enabled=True,
    )
    show_hidden_polygons = action(
        widget.tr("Show Hidden Polygons"),
        widget.show_hidden_polygons,
        shortcuts["show_hidden_polygons"],
        None,
        widget.tr("Show hidden polygons"),
        enabled=True,
    )

    overview = action(
        widget.tr("Overview"),
        widget.overview,
        shortcuts["show_overview"],
        icon="overview",
        tip=widget.tr("Show annotations statistics"),
    )
    save_crop = action(
        widget.tr("Save Cropped Image"),
        lambda: utils.save_crop(widget),
        icon="crop",
        tip=widget.tr(
            "Save cropped image. (Support rectangle/rotation/polygon shape_type)"
        ),
    )
    save_visualization_image = action(
        widget.tr("Save Visualization Image"),
        lambda: utils.save_visualization(widget),
        icon="file",
        tip=widget.tr("Save visualization image"),
    )
    digit_shortcut_manager = action(
        widget.tr("Digit Shortcut Manager"),
        widget.digit_shortcut_manager,
        shortcuts["edit_digit_shortcut"],
        icon="edit",
        tip=widget.tr(
            "Manage Digit Shortcuts: Assign Drawing Modes and Labels to Number Keys"
        ),
    )
    label_manager = action(
        widget.tr("Label Manager"),
        widget.label_manager,
        shortcuts["edit_labels"],
        icon="edit",
        tip=widget.tr(
            "Manage Labels: Rename, Delete, Hide/Show, Adjust Color"
        ),
    )
    shortcuts_help = action(
        widget.tr("快捷键速查"),
        widget.show_shortcuts_help,
        shortcuts["show_shortcuts_help"],
        icon="search",
        tip=widget.tr("查看所有可用快捷键，可按快捷键或功能搜索"),
    )
    gid_manager = action(
        widget.tr("Group ID Manager"),
        widget.gid_manager,
        shortcuts["edit_group_id"],
        icon="edit",
        tip=widget.tr("Manage Group ID"),
    )
    shape_manager = action(
        widget.tr("Shape Manager"),
        widget.shape_manager,
        shortcuts["edit_shapes"],
        icon="edit",
        tip=widget.tr("Manage Shapes: Add, Delete, Remove"),
        enabled=False,
    )
    copy_coordinates = action(
        widget.tr("Copy Coordinates"),
        widget.copy_shape_coordinates,
        icon="copy",
        tip=widget.tr("Copy shape coordinates to clipboard"),
        enabled=False,
    )
    union_selection = action(
        widget.tr("Union Selection"),
        widget.union_selection,
        shortcuts["union_selected_shapes"],
        icon="union",
        tip=widget.tr("Union multiple selected rectangle shapes"),
        enabled=False,
    )
    toggle_shape_lock = action(
        widget.tr("Lock Shape"),
        widget.toggle_selected_shapes_lock,
        tip=widget.tr("Prevent changes to the selected shapes' coordinates"),
        checkable=True,
        enabled=False,
    )
    shape_converter = action(
        widget.tr("Shape Converter"),
        lambda: utils.open_shape_converter(widget),
        icon="convert",
        tip=widget.tr("Open shape converter"),
    )

    loop_thru_labels = action(
        widget.tr("Loop Through Labels"),
        widget.loop_thru_labels,
        shortcut=shortcuts["loop_thru_labels"],
        icon="loop",
        tip=widget.tr("Loop through labels"),
        enabled=False,
    )
    loop_select_labels = action(
        widget.tr("Loop Select Labels"),
        widget.loop_select_labels,
        shortcut=shortcuts["loop_select_labels"],
        icon="circle-selection",
        tip=widget.tr("Loop select labels"),
        enabled=False,
    )
    select_toggle_shapes = action(
        widget.tr("Toggle Shapes Visibility"),
        widget.toggle_select_all,
        icon="eye",
        tip=widget.tr("Hide all shapes"),
        enabled=False,
    )
    widget.select_toggle_action = select_toggle_shapes

    ultralytics_train = action(
        "Ultralytics",
        lambda: widget.start_training("ultralytics"),
        icon="ultralytics",
    )
    run_history = action(
        widget.tr("实验历史"),
        widget.show_run_history,
    )

    zoom = QtWidgets.QWidgetAction(widget)
    zoom.setDefaultWidget(widget.zoom_widget)
    widget.zoom_widget.setWhatsThis(
        str(
            widget.tr(
                "Zoom in or out of the image. Also accessible with "
                "{} and {} from the canvas."
            )
        ).format(
            utils.fmt_shortcut(
                f"{shortcuts['zoom_in']},{shortcuts['zoom_out']}"
            ),
            utils.fmt_shortcut(widget.tr("Ctrl+Wheel")),
        )
    )
    widget.zoom_widget.setEnabled(False)

    zoom_in = action(
        widget.tr("Zoom In"),
        functools.partial(widget.add_zoom, 1.1),
        shortcuts["zoom_in"],
        "zoom-in",
        widget.tr("Increase zoom level"),
        enabled=False,
    )
    zoom_out = action(
        widget.tr("Zoom Out"),
        functools.partial(widget.add_zoom, 0.9),
        shortcuts["zoom_out"],
        "zoom-out",
        widget.tr("Decrease zoom level"),
        enabled=False,
    )
    zoom_org = action(
        widget.tr("Original Size"),
        functools.partial(widget.set_zoom, 100),
        shortcuts["zoom_to_original"],
        "zoom",
        widget.tr("Zoom to original size"),
        enabled=False,
    )
    keep_prev_scale = action(
        widget.tr("Keep Previous Scale"),
        lambda x: widget._config.update({"keep_prev_scale": x}),
        tip=widget.tr("Keep previous zoom scale"),
        checkable=True,
        checked=widget._config["keep_prev_scale"],
        enabled=True,
    )
    keep_prev_brightness = action(
        widget.tr("Keep Previous Brightness"),
        lambda x: widget._config.update({"keep_prev_brightness": x}),
        tip=widget.tr("Keep previous brightness"),
        checkable=True,
        checked=widget._config["keep_prev_brightness"],
        enabled=True,
    )
    keep_prev_contrast = action(
        widget.tr("Keep Previous Contrast"),
        lambda x: widget._config.update({"keep_prev_contrast": x}),
        tip=widget.tr("Keep previous contrast"),
        checkable=True,
        checked=widget._config["keep_prev_contrast"],
        enabled=True,
    )
    fit_window = action(
        widget.tr("Fit Window"),
        widget.set_fit_window,
        shortcuts["fit_window"],
        "fit-window",
        widget.tr("Zoom follows window size"),
        checkable=True,
        enabled=False,
    )
    fit_width = action(
        widget.tr("Fit Width"),
        widget.set_fit_width,
        shortcuts["fit_width"],
        "fit-width",
        widget.tr("Zoom follows window width"),
        checkable=True,
        enabled=False,
    )
    brightness_contrast = action(
        widget.tr("Set Brightness Contrast"),
        widget.brightness_contrast,
        None,
        "color",
        "Adjust brightness and contrast",
        enabled=False,
    )
    set_cross_line = action(
        widget.tr("Set Cross Line"),
        widget.set_cross_line,
        tip=widget.tr("Adjust cross line for mouse position"),
        icon="cartesian",
    )
    show_groups = action(
        widget.tr("Show Groups"),
        lambda x: widget.set_canvas_params("show_groups", x),
        tip=widget.tr("Show shape groups"),
        icon=None,
        checkable=True,
        checked=widget._config["show_groups"],
        enabled=True,
        auto_trigger=True,
    )
    show_masks = action(
        widget.tr("Show Masks"),
        lambda x: widget.set_canvas_params("show_masks", x),
        shortcut=shortcuts["show_masks"],
        tip=widget.tr("Show semi-transparent masks for shapes"),
        icon=None,
        checkable=True,
        checked=widget._config["show_masks"],
        enabled=True,
        auto_trigger=True,
    )
    # Fire the shortcut even when a child widget (e.g. the text-prompt
    # QLineEdit) has focus, so Ctrl+M reliably toggles the mask overlay.
    show_masks.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    show_texts = action(
        widget.tr("Show Texts"),
        lambda x: widget.set_canvas_params("show_texts", x),
        shortcut=shortcuts["show_texts"],
        tip=widget.tr("Show text above shapes"),
        icon=None,
        checkable=True,
        checked=widget._config["show_texts"],
        enabled=True,
        auto_trigger=True,
    )
    show_labels = action(
        widget.tr("Show Labels"),
        lambda x: widget.set_canvas_params("show_labels", x),
        shortcut=shortcuts["show_labels"],
        tip=widget.tr("Show label inside shapes"),
        icon=None,
        checkable=True,
        checked=widget._config["show_labels"],
        enabled=True,
        auto_trigger=True,
    )
    # Toggle the attribute text painted on the canvas. The canvas has
    # supported ``show_attributes`` all along, but it was never exposed as
    # an action, which left Ctrl+Shift+L advertised in the F1 cheat sheet
    # while doing nothing.
    show_attributes = action(
        widget.tr("Show Attributes"),
        lambda x: widget.set_canvas_params("show_attributes", x),
        shortcut=shortcuts["show_attributes"],
        tip=widget.tr("Show attributes below shapes"),
        icon=None,
        checkable=True,
        checked=widget._config["show_attributes"],
        enabled=True,
        auto_trigger=True,
    )
    # Same reasoning as show_masks: the shortcut must win over a focused
    # child widget (e.g. the text-prompt QLineEdit).
    show_attributes.setShortcutContext(
        Qt.ShortcutContext.ApplicationShortcut
    )
    show_scores = action(
        widget.tr("Show Scores"),
        lambda x: widget.set_canvas_params("show_scores", x),
        tip=widget.tr("Show score inside shapes"),
        icon=None,
        checkable=True,
        checked=widget._config["show_scores"],
        enabled=True,
        auto_trigger=True,
    )
    show_degrees = action(
        widget.tr("Show Degress"),
        lambda x: widget.set_canvas_params("show_degrees", x),
        tip=widget.tr("Show degrees above rotated shapes"),
        icon=None,
        checkable=True,
        checked=widget._config["show_degrees"],
        enabled=True,
        auto_trigger=True,
    )

    # Theme menu options (System / Light / Dark)
    theme_mode_actions = []
    theme_group = QtGui.QActionGroup(widget)
    theme_group.setExclusive(True)
    widget._theme_actions = {}
    current_appearance = widget._config.get("theme", "auto")
    for _mode, _label in (
        ("auto", widget.tr("System")),
        ("light", widget.tr("Light")),
        ("dark", widget.tr("Dark")),
    ):
        _act = QtGui.QAction(_label, theme_group)
        _act.setCheckable(True)
        _act.setChecked(current_appearance == _mode)
        _act.setData(_mode)
        _act.triggered.connect(
            functools.partial(widget._on_theme_changed, _mode)
        )
        theme_mode_actions.append(_act)
        widget._theme_actions[_mode] = _act

    # Upload
    upload_export_icon = "label"
    upload_image_flags_file = action(
        widget.tr("Image Flags"),
        lambda: utils.upload_image_flags_file(widget),
        None,
        icon=upload_export_icon,
        tip=widget.tr("Upload Custom Image Flags File"),
    )
    upload_label_flags_file = action(
        widget.tr("Label Flags"),
        lambda: utils.upload_label_flags_file(widget, LABEL_OPACITY),
        None,
        icon=upload_export_icon,
        tip=widget.tr("Upload Custom Label Flags File"),
    )
    upload_label_classes_file = action(
        widget.tr("Label Classes"),
        lambda: utils.upload_label_classes_file(widget),
        None,
        icon=upload_export_icon,
        tip=widget.tr("Upload Custom Label Classes File"),
    )
    upload_yolo_hbb_annotation = action(
        widget.tr("YOLO HBB"),
        lambda: utils.upload_yolo_annotation(widget, "hbb", LABEL_OPACITY),
        None,
        icon=upload_export_icon,
        tip=widget.tr(
            "Upload Custom YOLO Horizontal Bounding Boxes Annotations"
        ),
    )
    upload_yolo_seg_annotation = action(
        widget.tr("YOLO Seg"),
        lambda: utils.upload_yolo_annotation(widget, "seg", LABEL_OPACITY),
        None,
        icon=upload_export_icon,
        tip=widget.tr("Upload Custom YOLO Segmentation Annotations"),
    )
    upload_yolo_pose_annotation = action(
        widget.tr("YOLO Pose"),
        lambda: utils.upload_yolo_annotation(widget, "pose", LABEL_OPACITY),
        None,
        icon=upload_export_icon,
        tip=widget.tr("Upload Custom YOLO Pose Annotations"),
    )

    # Export
    export_yolo_hbb_annotation = action(
        widget.tr("YOLO HBB"),
        lambda: utils.export_yolo_annotation(widget, "hbb"),
        None,
        icon=upload_export_icon,
        tip=widget.tr(
            "Export Custom YOLO Horizontal Bounding Boxes Annotations"
        ),
    )
    export_yolo_seg_annotation = action(
        widget.tr("YOLO Seg"),
        lambda: utils.export_yolo_annotation(widget, "seg"),
        None,
        icon=upload_export_icon,
        tip=widget.tr("Export Custom YOLO Segmentation Annotations"),
    )
    export_yolo_pose_annotation = action(
        widget.tr("YOLO Pose"),
        lambda: utils.export_yolo_annotation(widget, "pose"),
        None,
        icon=upload_export_icon,
        tip=widget.tr("Export Custom YOLO Pose Annotations"),
    )

    # Group zoom controls into a list for easier toggling.
    zoom_actions = (
        widget.zoom_widget,
        zoom_in,
        zoom_out,
        zoom_org,
        fit_window,
        fit_width,
    )
    widget.zoom_mode = widget.FIT_WINDOW
    fit_window.setChecked(True)
    widget.scalers = {
        widget.FIT_WINDOW: widget.scale_fit_window,
        widget.FIT_WIDTH: widget.scale_fit_width,
        # Set to one to scale to 100% when loading files.
        widget.MANUAL_ZOOM: lambda: 1,
    }

    edit = action(
        widget.tr("Edit Label"),
        widget.edit_label,
        shortcuts["edit_label"],
        "edit",
        widget.tr("Modify the label of the selected polygon"),
        enabled=False,
    )

    fill_drawing = action(
        widget.tr("Fill Drawing Polygon"),
        widget.canvas.set_fill_drawing,
        None,
        "color",
        widget.tr("Fill polygon while drawing"),
        checkable=True,
        enabled=True,
    )
    fill_drawing.trigger()

    show_navigator = action(
        widget.tr("Navigator"),
        widget.toggle_navigator,
        shortcuts["show_navigator"],
        "navigator",
        widget.tr("Show/hide the navigator window"),
        checkable=True,
        enabled=True,
    )

    # AI Actions
    toggle_auto_labeling_widget = action(
        widget.tr("Auto Labeling"),
        widget.toggle_auto_labeling_widget,
        shortcuts["auto_label"],
        "brain",
        widget.tr("Auto Labeling"),
    )

    widget.label_list.setContextMenuPolicy(
        Qt.ContextMenuPolicy.NoContextMenu
    )

    # Store actions for further handling.
    widget.actions = utils.Struct(
        save_auto=save_auto,
        save_with_image_data=save_with_image_data,
        change_output_dir=change_output_dir,
        save=save,
        save_as=save_as,
        open=open_,
        open_dir=opendir,
        close=close,
        delete_file=delete_file,
        delete_image_file=delete_image_file,
        toggle_annotation_checked=toggle_annotation_checked,
        mark_checked_and_next=mark_checked_and_next,
        mark_rejected_and_next=mark_rejected_and_next,
        confirm_classification=confirm_classification,
        keep_prev_mode=keep_prev_mode,
        auto_use_last_label_mode=auto_use_last_label_mode,
        auto_use_last_gid_mode=auto_use_last_gid_mode,
        use_system_clipboard=use_system_clipboard,
        visibility_shapes_mode=visibility_shapes_mode,
        run_all_images=run_all_images,
        union_selection=union_selection,
        delete=delete,
        edit=edit,
        duplicate=duplicate,
        copy=copy,
        copy_coordinates=copy_coordinates,
        paste=paste,
        toggle_shape_lock=toggle_shape_lock,
        overview=overview,
        save_visualization_image=save_visualization_image,
        undo_last_point=undo_last_point,
        undo=undo,
        redo=redo,
        remove_point=remove_point,
        create_mode=create_mode,
        create_brush_polygon_mode=create_brush_polygon_mode,
        edit_mode=edit_mode,
        edit_brush_mode=edit_brush_mode,
        create_rectangle_mode=create_rectangle_mode,
        create_point_mode=create_point_mode,
        create_cuboid_mode=create_cuboid_mode,
        create_rotation_mode=create_rotation_mode,
        create_quadrilateral_mode=create_quadrilateral_mode,
        create_circle_mode=create_circle_mode,
        create_line_mode=create_line_mode,
        create_linestrip_mode=create_linestrip_mode,
        digit_shortcut_0=digit_shortcut_0,
        digit_shortcut_1=digit_shortcut_1,
        digit_shortcut_2=digit_shortcut_2,
        digit_shortcut_3=digit_shortcut_3,
        digit_shortcut_4=digit_shortcut_4,
        digit_shortcut_5=digit_shortcut_5,
        digit_shortcut_6=digit_shortcut_6,
        digit_shortcut_7=digit_shortcut_7,
        digit_shortcut_8=digit_shortcut_8,
        digit_shortcut_9=digit_shortcut_9,
        digit_shortcut_actions=(
            digit_shortcut_0,
            digit_shortcut_1,
            digit_shortcut_2,
            digit_shortcut_3,
            digit_shortcut_4,
            digit_shortcut_5,
            digit_shortcut_6,
            digit_shortcut_7,
            digit_shortcut_8,
            digit_shortcut_9,
        ),
        upload_image_flags_file=upload_image_flags_file,
        upload_label_flags_file=upload_label_flags_file,
        upload_label_classes_file=upload_label_classes_file,
        upload_yolo_hbb_annotation=upload_yolo_hbb_annotation,
        upload_yolo_seg_annotation=upload_yolo_seg_annotation,
        upload_yolo_pose_annotation=upload_yolo_pose_annotation,
        export_yolo_hbb_annotation=export_yolo_hbb_annotation,
        export_yolo_seg_annotation=export_yolo_seg_annotation,
        export_yolo_pose_annotation=export_yolo_pose_annotation,
        zoom=zoom,
        zoom_in=zoom_in,
        zoom_out=zoom_out,
        zoom_org=zoom_org,
        keep_prev_scale=keep_prev_scale,
        keep_prev_brightness=keep_prev_brightness,
        keep_prev_contrast=keep_prev_contrast,
        fit_window=fit_window,
        fit_width=fit_width,
        brightness_contrast=brightness_contrast,
        set_cross_line=set_cross_line,
        show_groups=show_groups,
        show_masks=show_masks,
        show_texts=show_texts,
        show_labels=show_labels,
        show_attributes=show_attributes,
        show_scores=show_scores,
        show_degrees=show_degrees,
        show_navigator=show_navigator,
        zoom_actions=zoom_actions,
        open_next_image=open_next_image,
        open_prev_image=open_prev_image,
        open_next_unchecked_image=open_next_unchecked_image,
        open_prev_unchecked_image=open_prev_unchecked_image,
        toggle_auto_labeling_widget=toggle_auto_labeling_widget,
        digit_shortcut_manager=digit_shortcut_manager,
        label_manager=label_manager,
        gid_manager=gid_manager,
        shape_manager=shape_manager,
        loop_thru_labels=loop_thru_labels,
        loop_select_labels=loop_select_labels,
        select_toggle_shapes=select_toggle_shapes,
        file_menu_actions=(
            open_,
            opendir,
            save,
            save_as,
            close,
        ),
        tool=(),
        # XXX: need to add some actions here to activate the shortcut
        editMenu=(
            edit,
            duplicate,
            delete,
            copy,
            paste,
            None,
            undo,
            undo_last_point,
            redo,
            None,
            copy_coordinates,
            remove_point,
            union_selection,
            None,
            keep_prev_mode,
            auto_use_last_label_mode,
            auto_use_last_gid_mode,
            use_system_clipboard,
            visibility_shapes_mode,
        ),
        # menu shown at right click
        menu=(
            create_mode,
            create_brush_polygon_mode,
            create_rectangle_mode,
            create_point_mode,
            create_rotation_mode,
            create_quadrilateral_mode,
            create_circle_mode,
            create_line_mode,
            create_linestrip_mode,
            create_cuboid_mode,
            None,
            edit_mode,
            edit_brush_mode,
            edit,
            toggle_shape_lock,
            None,
            copy_coordinates,
            union_selection,
            duplicate,
            copy,
            paste,
            None,
            delete,
            undo,
            undo_last_point,
            redo,
            remove_point,
        ),
        on_load_active=(
            close,
            create_mode,
            create_brush_polygon_mode,
            create_rectangle_mode,
            create_point_mode,
            create_cuboid_mode,
            create_rotation_mode,
            create_quadrilateral_mode,
            create_circle_mode,
            create_line_mode,
            create_linestrip_mode,
            digit_shortcut_0,
            digit_shortcut_1,
            digit_shortcut_2,
            digit_shortcut_3,
            digit_shortcut_4,
            digit_shortcut_5,
            digit_shortcut_6,
            digit_shortcut_7,
            digit_shortcut_8,
            digit_shortcut_9,
            edit_mode,
            brightness_contrast,
            toggle_annotation_checked,
            mark_checked_and_next,
            mark_rejected_and_next,
            shape_manager,
            loop_thru_labels,
            loop_select_labels,
            select_toggle_shapes,
        ),
        on_shapes_present=(save_as, delete),
        hide_selected_polygons=hide_selected_polygons,
        show_hidden_polygons=show_hidden_polygons,
        group_selected_shapes=group_selected_shapes,
        ungroup_selected_shapes=ungroup_selected_shapes,
    )

    for digit_action in (
        widget.actions.digit_shortcut_0,
        widget.actions.digit_shortcut_1,
        widget.actions.digit_shortcut_2,
        widget.actions.digit_shortcut_3,
        widget.actions.digit_shortcut_4,
        widget.actions.digit_shortcut_5,
        widget.actions.digit_shortcut_6,
        widget.actions.digit_shortcut_7,
        widget.actions.digit_shortcut_8,
        widget.actions.digit_shortcut_9,
    ):
        widget.addAction(digit_action)
    widget.addAction(widget.actions.toggle_annotation_checked)
    widget.addAction(widget.actions.mark_checked_and_next)
    widget.addAction(widget.actions.mark_rejected_and_next)

    widget.canvas.vertex_selected.connect(
        widget.actions.remove_point.setEnabled
    )

    widget.menus = utils.Struct(
        file=widget.menu(widget.tr("File")),
        edit=widget.menu(widget.tr("Edit")),
        view=widget.menu(widget.tr("View")),
        theme=widget.menu(widget.tr("Theme")),
        upload=widget.menu(widget.tr("Upload")),
        export=widget.menu(widget.tr("Export")),
        tool=widget.menu(widget.tr("Tool")),
        train=widget.menu(widget.tr("Train")),
        smart_tools=widget.menu(widget.tr("智能工具")),
        recent_files=QtWidgets.QMenu(widget.tr("Open Recent")),
        recent_dirs=QtWidgets.QMenu(widget.tr("打开最近文件夹")),
    )
    widget.menus.recent_files.aboutToShow.connect(widget.update_file_menu)
    widget.menus.recent_dirs.aboutToShow.connect(
        widget._update_recent_dirs_menu
    )
    widget.canvas_label_filter_menu_0 = None
    widget.canvas_gid_filter_menu_0 = None
    widget.canvas_label_filter_menu_1 = None
    widget.canvas_gid_filter_menu_1 = None

    utils.add_actions(
        widget.menus.file,
        (
            open_,
            open_next_image,
            open_prev_image,
            open_next_unchecked_image,
            open_prev_unchecked_image,
            opendir,
            widget.menus.recent_dirs,
            widget.menus.recent_files,
            save,
            save_as,
            save_auto,
            change_output_dir,
            save_with_image_data,
            close,
            delete_file,
            delete_image_file,
            None,
            mark_checked_and_next,
            mark_rejected_and_next,
            confirm_classification,
            None,
        ),
    )
    utils.add_actions(
        widget.menus.smart_tools,
        (
            data_audit,
            smart_calibrate,
            smart_analysis,
            smart_missing_scan,
            smart_iteration,
            smart_review,
            smart_propagate,
            smart_archive,
            smart_advice,
            smart_template,
            smart_stale_audit,
            smart_restore_backup,
        ),
    )
    utils.add_actions(
        widget.menus.train, (ultralytics_train, run_history)
    )
    utils.add_actions(
        widget.menus.tool,
        (
            overview,
            None,
            save_crop,
            save_visualization_image,
            None,
            digit_shortcut_manager,
            label_manager,
            gid_manager,
            shape_manager,
            None,
            shape_converter,
            None,
            shortcuts_help,
        ),
    )
    utils.add_actions(widget.menus.theme, theme_mode_actions)
    utils.add_actions(
        widget.menus.upload,
        (
            upload_image_flags_file,
            upload_label_flags_file,
            upload_label_classes_file,
            None,
            upload_yolo_hbb_annotation,
            upload_yolo_seg_annotation,
            upload_yolo_pose_annotation,
            None,
            None,
            None,
            None,
        ),
    )
    utils.add_actions(
        widget.menus.export,
        (
            export_yolo_hbb_annotation,
            export_yolo_seg_annotation,
            export_yolo_pose_annotation,
            None,
            None,
            None,
            None,
            None,
        ),
    )
    utils.add_actions(
        widget.menus.view,
        (
            show_navigator,
            fill_drawing,
            loop_thru_labels,
            loop_select_labels,
            None,
            zoom_in,
            zoom_out,
            zoom_org,
            None,
            keep_prev_scale,
            keep_prev_brightness,
            keep_prev_contrast,
            None,
            fit_window,
            fit_width,
            None,
            brightness_contrast,
            set_cross_line,
            None,
            show_masks,
            show_texts,
            show_labels,
            show_attributes,
            show_scores,
            show_degrees,
            show_groups,
            hide_selected_polygons,
            show_hidden_polygons,
            group_selected_shapes,
            ungroup_selected_shapes,
        ),
    )

    widget._view_menu_filter = utils.StayOpenMenuFilter(widget.menus.view)
    widget.menus.view.installEventFilter(widget._view_menu_filter)

    widget.menus.file.aboutToShow.connect(widget.update_file_menu)

    # Custom context menu for the canvas widget:
    utils.add_actions(widget.canvas.menus[0], widget.actions.menu)
    utils.add_actions(
        widget.canvas.menus[1],
        (
            action("&Copy here", widget.copy_shape),
            action("&Move here", widget.move_shape),
        ),
    )
    (
        widget.canvas_label_filter_menu_0,
        widget.canvas_gid_filter_menu_0,
    ) = widget._append_filter_submenus(
        widget.canvas.menus[0],
        prepend=True,
        after_filter_actions=(widget.actions.toggle_annotation_checked,),
    )
    widget.canvas.menus[0].aboutToShow.connect(widget.refresh_filter_menus)
    widget.canvas.menus[0].aboutToShow.connect(
        widget.refresh_shape_lock_action
    )

    widget.tools = widget.toolbar("Tools")
    # Menu buttons on Left
    widget.actions.tool = (
        opendir,
        open_prev_image,
        open_next_image,
        save,
        delete_file,
        None,
        create_mode,
        widget.actions.create_rectangle_mode,
        widget.actions.create_point_mode,
        widget.actions.create_brush_polygon_mode,
        None,
        edit_mode,
        edit_brush_mode,
        delete,
        undo,
        redo,
        None,
        loop_thru_labels,
        loop_select_labels,
        select_toggle_shapes,
        None,
        run_all_images,
        toggle_auto_labeling_widget,
        None,
        fit_width,
        zoom,
    )

    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)

    widget.tools_scroll_area = widget.toolbar_scroll_area(widget.tools)
    widget.tools_panel = FloatingToolPanel(
        widget._canvas_scroll_area.viewport()
    )
    widget.tools_panel.setObjectName("ToolsFloatingPanel")
    widget.tools_panel.set_content_widget(widget.tools_scroll_area)
    widget.tools_panel.positionCommitted.connect(
        widget._on_tools_panel_position_committed
    )
    widget.tools_panel.collapseToggled.connect(
        widget._on_tools_panel_collapse_toggled
    )

    central_layout = QVBoxLayout()
    central_layout.setContentsMargins(0, 0, 0, 0)
    central_layout.setSpacing(2)
    widget.label_instruction = QLabel(widget.get_labeling_instruction())
    widget.label_instruction.setObjectName("LabelInstructionBar")
    widget.label_instruction.setContentsMargins(0, 0, 0, 0)
    widget.label_instruction.setStyleSheet(get_instruction_bar_style())
    widget.label_instruction.setWordWrap(True)
    widget.label_instruction.setTextFormat(Qt.TextFormat.RichText)
    widget.auto_labeling_widget = AutoLabelingWidget(widget)
    widget.auto_labeling_widget.auto_segmentation_requested.connect(
        widget.on_auto_segmentation_requested
    )
    widget.auto_labeling_widget.auto_segmentation_disabled.connect(
        widget.on_auto_segmentation_disabled
    )
    widget.canvas.auto_labeling_marks_updated.connect(
        widget.auto_labeling_widget.on_new_marks
    )
    widget.auto_labeling_widget.auto_labeling_mode_changed.connect(
        widget.canvas.set_auto_labeling_mode
    )
    widget.auto_labeling_widget.auto_decode_mode_changed.connect(
        widget.canvas.set_auto_decode_mode
    )
    widget.auto_labeling_widget.cropping_mode_changed.connect(
        widget.auto_labeling_widget.model_manager.set_cropping_mode
    )
    widget.auto_labeling_widget.clear_auto_decode_requested.connect(
        widget.canvas.reset_auto_decode_state
    )
    widget.canvas.auto_decode_requested.connect(
        widget.on_auto_decode_requested
    )
    widget.canvas.auto_decode_finish_requested.connect(
        widget.auto_labeling_widget.on_finish_clicked
    )
    widget.canvas.shape_hover_changed.connect(
        lambda: (
            widget.update_navigator_shapes()
            if (
                hasattr(widget, "navigator_dialog")
                and widget.navigator_dialog.isVisible()
            )
            else None
        )
    )
    widget.auto_labeling_widget.clear_auto_labeling_action_requested.connect(
        widget.clear_auto_labeling_marks
    )
    widget.auto_labeling_widget.finish_auto_labeling_object_action_requested.connect(
        widget.finish_auto_labeling_object
    )
    widget.auto_labeling_widget.cache_auto_label_changed.connect(
        widget.set_cache_auto_label
    )
    widget.auto_labeling_widget.model_manager.prediction_started.connect(
        lambda: widget.canvas.set_loading(True, widget.tr("Please wait..."))
    )
    widget.auto_labeling_widget.model_manager.prediction_finished.connect(
        lambda: widget.canvas.set_loading(False)
    )
    widget.auto_labeling_widget.model_manager.prediction_finished.connect(
        widget.update_thumbnail_display
    )
    widget.auto_labeling_widget.model_manager.model_loaded.connect(
        widget.update_thumbnail_display
    )
    widget.next_files_changed.connect(
        widget.auto_labeling_widget.model_manager.on_next_files_changed
    )
    # NOTE(jack): this is not needed for now
    # widget.auto_labeling_widget.model_manager.request_next_files_requested.connect(
    #     lambda: widget.inform_next_files(widget.filename)
    # )
    widget.auto_labeling_widget.hide()  # Hide by default
    central_layout.addWidget(widget.label_instruction)
    central_layout.addWidget(widget.auto_labeling_widget)
    central_layout.addWidget(widget._canvas_scroll_area)
    layout.addLayout(central_layout)

    # Save central area for resize
    widget._central_widget = widget._canvas_scroll_area

    # Stretch central area (image view)
    layout.setStretch(0, 1)

    right_sidebar_layout = QVBoxLayout()
    right_sidebar_layout.setContentsMargins(0, 0, 0, 0)
    right_sidebar_layout.setSpacing(4)

    # Thumbnail image display
    widget.thumbnail_pixmap = None
    widget.thumbnail_container = QWidget()
    thumbnail_image_layout = QVBoxLayout()
    thumbnail_image_layout.setContentsMargins(2, 2, 2, 2)
    widget.thumbnail_image_label = QLabel()
    widget.thumbnail_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    widget.thumbnail_image_label.mousePressEvent = utils.on_thumbnail_click(
        widget
    )
    thumbnail_image_layout.addWidget(widget.thumbnail_image_label)
    widget.thumbnail_container.setLayout(thumbnail_image_layout)
    widget.thumbnail_container.hide()
    right_sidebar_layout.addWidget(widget.thumbnail_container)

    # Shape attributes
    widget.shape_attributes = QLabel(widget.tr("Attributes"))
    widget.grid_layout = QGridLayout()
    widget.scroll_area = QScrollArea()
    # Show vertical scrollbar as needed
    widget.scroll_area.setVerticalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )
    # Disable horizontal scrollbar
    widget.scroll_area.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    widget.scroll_area.setWidgetResizable(True)
    # Create a container widget for the grid layout
    widget.grid_layout_container = QWidget()
    widget.grid_layout_container.setLayout(widget.grid_layout)
    widget.scroll_area.setWidget(widget.grid_layout_container)
    if not widget.attributes:
        widget.shape_attributes.hide()
        widget.scroll_area.hide()
    right_sidebar_layout.addWidget(
        widget.shape_attributes, 0, Qt.AlignmentFlag.AlignCenter
    )
    right_sidebar_layout.addWidget(widget.scroll_area)

    right_sidebar_layout.addWidget(widget.flag_dock)

    # Labels with checkbox
    widget.labels_checkbox = QCheckBox()
    widget.labels_checkbox.setChecked(True)
    widget.labels_checkbox.setStyleSheet(get_checkbox_indicator_style())
    widget.labels_checkbox.toggled.connect(widget.toggle_labels_visibility)

    labels_header_layout = QHBoxLayout()
    labels_header_layout.setContentsMargins(0, 2, 0, 2)
    labels_header_layout.addStretch()
    labels_title = QLabel(widget.tr("Labels"))
    labels_header_layout.addWidget(labels_title)
    labels_header_layout.addStretch()
    labels_header_layout.addWidget(widget.labels_checkbox)
    labels_header_widget = QWidget()
    labels_header_widget.setLayout(labels_header_layout)

    # Hide the original dock title bar
    empty_widget = QWidget()
    empty_widget.setFixedHeight(0)
    widget.label_dock.setTitleBarWidget(empty_widget)

    labels_panel = QFrame()
    labels_panel.setObjectName("sidebarPanel")
    labels_panel.setStyleSheet(get_panel_style())
    labels_panel_layout = QVBoxLayout(labels_panel)
    labels_panel_layout.setContentsMargins(0, 0, 0, 0)
    labels_panel_layout.setSpacing(0)
    labels_panel_layout.addWidget(labels_header_widget)
    labels_panel_layout.addWidget(widget.label_dock)
    right_sidebar_layout.addWidget(labels_panel)

    widget.shapes_checkbox = QCheckBox()
    widget.shapes_checkbox.setChecked(True)
    widget.shapes_checkbox.setStyleSheet(get_checkbox_indicator_style())
    widget.shapes_checkbox.toggled.connect(widget.toggle_shapes_visibility)

    shapes_header_layout = QHBoxLayout()
    shapes_header_layout.setContentsMargins(0, 2, 0, 2)
    shapes_header_layout.addStretch()
    shapes_title = QLabel(widget.tr("Shapes"))
    shapes_header_layout.addWidget(shapes_title)
    shapes_header_layout.addStretch()
    shapes_header_layout.addWidget(widget.shapes_checkbox)
    shapes_header_widget = QWidget()
    shapes_header_widget.setLayout(shapes_header_layout)

    shape_empty_widget = QWidget()
    shape_empty_widget.setFixedHeight(0)
    widget.shape_dock.setTitleBarWidget(shape_empty_widget)

    objects_panel = QFrame()
    objects_panel.setObjectName("sidebarPanel")
    objects_panel.setStyleSheet(get_panel_style())
    objects_panel_layout = QVBoxLayout(objects_panel)
    objects_panel_layout.setContentsMargins(0, 0, 0, 0)
    objects_panel_layout.setSpacing(0)
    objects_panel_layout.addWidget(shapes_header_widget)
    objects_panel_layout.addWidget(widget.shape_dock)
    right_sidebar_layout.addWidget(objects_panel)

    file_search_row_layout = QHBoxLayout()
    file_search_row_layout.setContentsMargins(0, 0, 0, 0)
    file_search_row_layout.setSpacing(6)
    file_search_row_layout.addWidget(widget.file_search, 1)
    file_search_row_layout.addWidget(widget.settings_button, 0)
    right_sidebar_layout.addLayout(file_search_row_layout)

    files_panel = QFrame()
    files_panel.setObjectName("sidebarPanel")
    files_panel.setStyleSheet(get_panel_style())
    files_panel_layout = QVBoxLayout(files_panel)
    files_panel_layout.setContentsMargins(0, 0, 0, 0)
    files_panel_layout.setSpacing(0)
    files_panel_layout.addWidget(widget.file_dock)
    right_sidebar_layout.addWidget(files_panel)
    widget.file_dock.setFeatures(
        QDockWidget.DockWidgetFeature.DockWidgetFloatable
    )
    dock_features = (
        ~QDockWidget.DockWidgetFeature.DockWidgetMovable
        | ~QDockWidget.DockWidgetFeature.DockWidgetFloatable
        | ~QDockWidget.DockWidgetFeature.DockWidgetClosable
    )
    rev_dock_features = ~dock_features
    widget.label_dock.setFeatures(
        widget.label_dock.features() & rev_dock_features
    )
    widget.file_dock.setFeatures(
        widget.file_dock.features() & rev_dock_features
    )
    widget.flag_dock.setFeatures(
        widget.flag_dock.features() & rev_dock_features
    )
    widget.shape_dock.setFeatures(
        widget.shape_dock.features() & rev_dock_features
    )

    layout.addLayout(right_sidebar_layout)
    widget.setLayout(layout)
    QtCore.QTimer.singleShot(0, widget._restore_tools_panel_state)
