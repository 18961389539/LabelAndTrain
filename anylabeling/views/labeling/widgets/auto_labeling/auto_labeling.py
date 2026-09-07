import os
import re
import yaml
import collections
from pathlib import Path

from anylabeling.config import get_config, get_work_directory

from PyQt6 import uic
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QWidget,
)

from anylabeling.services.auto_labeling.model_manager import ModelManager
from anylabeling.services.auto_labeling.types import AutoLabelingMode
from anylabeling.services.auto_labeling import (
    _AUTO_LABELING_IOU_MODELS,
    _AUTO_LABELING_CONF_MODELS,
    _SKIP_DET_MODELS,
    _SKIP_PREDICTION_ON_NEW_MARKS_MODELS,
)
from anylabeling.views.labeling.ai.style import SliderStyle
from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.utils._io import load_json, save_json
from anylabeling.views.labeling.utils.model_task_groups import (
    classify_model_load_error,
    mark_recommended_models,
)
from anylabeling.views.labeling.utils.theme import get_theme
from anylabeling.views.labeling.utils.style import (
    get_lineedit_style,
    get_double_spinbox_style,
    get_normal_button_style,
    get_highlight_button_style,
    get_ready_button_style,
    get_settings_combo_style,
    get_model_selection_scroll_area_style,
    get_toggle_button_style,
    get_download_progress_bar_style,
    get_cancel_download_button_style,
)
from anylabeling.views.labeling.widgets.classes_filter_dialog import (
    ClassesFilterDialog,
)
from anylabeling.views.labeling.widgets.searchable_model_dropdown import (
    _get_models_config_path,
    SearchableModelDropdownPopup,
)


def update_model_selection_scroll_area_height(scroll_area):
    content_widget = scroll_area.widget()
    if content_widget is None:
        return
    scroll_bar = scroll_area.horizontalScrollBar()
    scroll_bar_height = (
        scroll_bar.sizeHint().height()
        if scroll_bar.maximum() > scroll_bar.minimum()
        else 0
    )
    scroll_area.setFixedHeight(
        content_widget.sizeHint().height() + scroll_bar_height
    )
    content_layout = content_widget.layout()
    if content_layout is not None:
        content_layout.invalidate()
        content_layout.activate()
        content_layout.setGeometry(content_widget.rect())


# Custom-model weights are ONNX-only by design: every supported backend
# (onnxruntime / OpenCV DNN / TensorRT) consumes an ``.onnx`` graph.
CUSTOM_MODEL_WEIGHT_EXTS = {".onnx"}

# Filename hints → _CUSTOM_MODELS type. Conservative defaults: we only
# auto-classify when the filename makes the task unambiguous, otherwise we
# fall back to yolov8 (the most common detection case).
def _infer_custom_model_type(stem: str) -> str:
    s = stem.lower()
    if "pose" in s:
        return "yolo26_pose"
    # SAM hints must be checked BEFORE the generic "seg"/"segment" rule,
    # otherwise files like "segment_anything_2" are mis-classified as
    # yolov8_seg.
    if "sam2" in s or "sam_" in s or "segment_anything" in s:
        return "segment_anything_2"
    if "seg" in s:
        return "yolov8_seg"
    return "yolov8"


def _safe_custom_model_name(stem: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", stem or "")
    text = text.strip("._-") or "custom_model"
    return text[:80]


def _classify_yolo_onnx(weights_path: str):
    """Classify an ``.onnx`` file into a concrete supported model type.

    The YOLO runtime dispatch in this app depends on the yaml ``type``:

    - ``yolov8`` family  → ``non_max_suppression_v8`` (anchor-grid decode +
      NMS in the app). Export outputs carry a large grid axis (e.g. 8400).
    - ``yolo26`` family  → ``non_max_suppression_end2end`` (NMS is already
      baked into the export). Outputs are flat end-to-end boxes/scores.

    So "which YOLO is it" is NOT cosmetic: the wrong family decodes
    garbage. This helper inspects the graph's outputs/metadata (no
    inference) and returns the exact type to put in the yaml, or ``None``
    when it cannot be determined (caller then keeps the filename hint):

    - ``kpt_shape`` metadata            → pose. Only the end-to-end pose
      (``yolo26_pose``) is supported here, so a *classic* (grid) pose
      export cannot be mapped → ``None``.
    - a 4-D output (proto/mask head)    → seg: classic grid → ``yolov8_seg``,
      end-to-end → ``yolo26_seg``.
    - a large grid axis (>= 1000)       → classic detection → ``yolov8``.
    - otherwise flat outputs            → end-to-end detection → ``yolo26``.
    """
    try:
        import onnxruntime as ort

        sess_options = ort.SessionOptions()
        sess_options.log_severity_level = 3
        sess_options.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        )
        session = ort.InferenceSession(
            weights_path,
            sess_options,
            providers=["CPUExecutionProvider"],
        )
        meta = session.get_modelmeta().custom_metadata_map or {}
        has_kpt = any("kpt_shape" in key.lower() for key in meta)

        def _dims(shape):
            return [d for d in shape if isinstance(d, int) and d > 0]

        shapes = [_dims(o.shape) for o in session.get_outputs()]
        has_grid = any(
            dims and max(dims) >= 1000 for dims in shapes
        )  # e.g. anchor-axis 8400 / 25200
        has_4d = any(len(dims) == 4 for dims in shapes)  # proto/mask head

        if has_kpt:
            # Only end-to-end pose decode (yolo26_pose) is whitelisted.
            return "yolo26_pose" if not has_grid else None
        if has_4d:
            return "yolov8_seg" if has_grid else "yolo26_seg"
        if has_grid:
            return "yolov8"
        return "yolo26"
    except Exception:  # noqa: BLE001
        return None


def _parse_ultralytics_names(raw):
    """Parse the ``names`` field Ultralytics writes into ONNX metadata.

    The value is usually a Python dict repr like ``"{'person': 0, 'cat': 1}"``
    (single quotes, single-line), but it can also be JSON, or already be a
    list. Returns a list of names ordered by their integer index, or
    ``None`` if the format cannot be recognised.
    """
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)) and all(isinstance(s, str) for s in raw):
        return list(raw)
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    # Normalise common single-quoted Python repr to JSON-friendly.
    if text.startswith("{") and text.endswith("}"):
        try:
            import ast
            obj = ast.literal_eval(text)
            if isinstance(obj, dict):
                names = [None] * len(obj)
                for name, index in obj.items():
                    try:
                        names[int(index)] = str(name)
                    except (ValueError, IndexError):
                        return None
                if any(n is None for n in names):
                    return None
                return names
        except (ValueError, SyntaxError):
            pass
        try:
            import json
            obj = json.loads(text)
            if isinstance(obj, dict):
                names = [None] * len(obj)
                for name, index in obj.items():
                    try:
                        names[int(index)] = str(name)
                    except (ValueError, IndexError):
                        return None
                if any(n is None for n in names):
                    return None
                return names
        except json.JSONDecodeError:
            return None
    if text.startswith("["):
        try:
            import ast
            obj = ast.literal_eval(text)
            if isinstance(obj, list):
                return [str(n) for n in obj]
        except (ValueError, SyntaxError):
            pass
        try:
            import json
            obj = json.loads(text)
            if isinstance(obj, list):
                return [str(n) for n in obj]
        except json.JSONDecodeError:
            return None
    return None


def _derive_nc_from_outputs(model_type, shapes, has_grid):
    """Guess ``nc`` (class count) from ONNX output shapes.

    Returns ``nc`` as a positive int, or ``None`` if it cannot be
    determined. Handles classic v8 / classic seg / E2E variants and the
    yolo26 family.
    """
    # Most outputs: 3D (classic) [1, 4+nc+nm, N] or 2D (e2e) [1, 300, 4+nc+nm]
    for dims in shapes:
        if not dims:
            continue
        n = len(dims)
        if n == 3 and has_grid:
            # classic det/seg/pose output axis
            c = dims[1]
            if c <= 4:
                continue  # not enough channels to be a useful output
            if model_type in ("yolov8_seg", "yolo26_seg"):
                nm = 32  # default Ultralytics seg mask-coeff count
                nc = c - 4 - nm
                if nc > 0:
                    return nc
            else:  # det / pose classic
                nc = c - 4
                if nc > 0:
                    return nc
        elif n == 2:
            # E2E: [1, 300, 4+nc] (or 4+nc+nm for seg)
            c = dims[2] if len(dims) >= 3 else None
            if c is not None and c > 4:
                if model_type in ("yolov8_seg", "yolo26_seg"):
                    nm = 32
                    nc = c - 4 - nm
                else:
                    nc = c - 4
                if nc > 0:
                    return nc
    return None


def _extract_class_names_from_onnx(weights_path, model_type):
    """Return a list of class names for a custom model, sourced from the
    ONNX metadata when available, otherwise derived from output shapes.

    Returns a 3-tuple ``(names, source, nc)`` where ``source`` is one of
    ``"metadata"`` / ``"shape"`` / ``"none"``. The list is always sized
    to match the actual class count (or empty if nothing could be
    determined).
    """
    try:
        import onnx
    except Exception:  # noqa: BLE001
        return [], "none", None

    try:
        model = onnx.load(weights_path)
    except Exception:  # noqa: BLE001
        return [], "none", None

    # 1) Ultralytics writes "names" into custom metadata props.
    for prop in model.metadata_props:
        if prop.key == "names":
            parsed = _parse_ultralytics_names(prop.value)
            if parsed is not None:
                return parsed, "metadata", len(parsed)

    # 2) Fall back to reading the output shapes to derive nc.
    shapes = []
    for o in model.graph.output:
        if o.type.tensor_type.shape:
            shapes.append([
                d.dim_value
                for d in o.type.tensor_type.shape.dim
                if isinstance(d.dim_value, int) and d.dim_value > 0
            ])
    has_grid = any(s and max(s) >= 1000 for s in shapes)
    nc = _derive_nc_from_outputs(model_type, shapes, has_grid)
    if nc and nc > 0:
        return [f"class_{i}" for i in range(nc)], "shape", nc

    return [], "none", None


def _build_custom_model_yaml_from_weights(weights_path: str) -> str:
    """Create a custom-model yaml pointing at ``weights_path``.

    The user is allowed to pick an ``.onnx`` weights file directly from the
    file dialog (custom models are ONNX-only); this helper materialises the yaml that ``ModelManager.load_custom_model`` requires
    and writes it under ``<work_dir>/custom_models/`` so it survives
    restart and participates in the existing custom-models list/eviction
    logic.

    The yaml ``type`` starts from the filename hint and is then refined
    against the real ONNX graph when the file is ``.onnx`` and the hint is
    not SAM2: ``_classify_yolo_onnx`` returns the exact supported type
    (family + task), so both "yolov8 vs yolo26" and "det vs seg vs pose"
    are decided by the model itself, not by the filename.
    """
    weights_abs = os.path.abspath(weights_path)
    weights = Path(weights_abs)
    if not weights.is_file():
        raise FileNotFoundError(f"Model file not found: {weights_abs}")

    try:
        work_dir = get_work_directory()
    except Exception:
        work_dir = os.path.dirname(weights_abs) or "."

    custom_dir = os.path.join(work_dir, "custom_models")
    os.makedirs(custom_dir, exist_ok=True)

    name = _safe_custom_model_name(weights.stem)

    type_hint = _infer_custom_model_type(weights.stem)
    model_type = type_hint
    if weights.suffix.lower() == ".onnx" and type_hint != "segment_anything_2":
        # Prefer ground truth from the graph over filename guessing.
        classified = _classify_yolo_onnx(weights_abs)
        if classified:
            model_type = classified
            if model_type != type_hint:
                logger.info(
                    f"Custom-model type refined for {weights.name}: "
                    f"{type_hint} → {model_type} (from ONNX graph analysis)"
                )

    # Read or derive class names. Seg models reject empty classes (nc=0)
    # at decode time, so an auto-generated yaml must include a non-empty
    # ``classes`` list whenever we can.
    classes, classes_source, _ = _extract_class_names_from_onnx(
        weights_abs, model_type
    )
    if classes:
        logger.info(
            f"Custom-model classes for {weights.name}: "
            f"{len(classes)} entries (from {classes_source})"
        )

    yaml_path = os.path.join(custom_dir, f"{name}.yaml")
    # Avoid clobbering an existing user-authored yaml with the same name.
    n = 2
    while os.path.exists(yaml_path):
        yaml_path = os.path.join(custom_dir, f"{name}_{n}.yaml")
        n += 1

    payload = {
        "type": model_type,
        "name": name,
        "display_name": f"Custom \u00b7 {weights.stem}",
        "model_path": weights_abs,
        "engine": "ort",
        "conf_threshold": 0.25,
        "iou_threshold": 0.45,
        "classes": classes,
    }

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)
    logger.info(
        f"Auto-generated custom-model yaml for {weights.name} → {yaml_path}"
    )
    return yaml_path


class AutoLabelingWidget(QWidget):
    new_model_selected = pyqtSignal(str)
    new_custom_model_selected = pyqtSignal(str)
    auto_segmentation_requested = pyqtSignal()
    auto_segmentation_disabled = pyqtSignal()
    auto_labeling_mode_changed = pyqtSignal(AutoLabelingMode)
    clear_auto_labeling_action_requested = pyqtSignal()
    finish_auto_labeling_object_action_requested = pyqtSignal()
    cache_auto_label_changed = pyqtSignal()
    auto_decode_mode_changed = pyqtSignal(bool)
    cropping_mode_changed = pyqtSignal(bool)
    clear_auto_decode_requested = pyqtSignal()
    mask_fineness_changed = pyqtSignal(float)


    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        current_dir = os.path.dirname(__file__)
        uic.loadUi(os.path.join(current_dir, "auto_labeling.ui"), self)
        self.model_selection_scroll_area.setStyleSheet(
            get_model_selection_scroll_area_style()
        )
        scroll_bar = self.model_selection_scroll_area.horizontalScrollBar()
        scroll_bar.rangeChanged.connect(
            self._update_model_selection_scroll_area_height
        )
        self._update_model_selection_scroll_area_height()

        self.skip_auto_prediction = False
        self._last_model_selection = None
        self.model_manager = ModelManager()
        self.model_manager.new_model_status.connect(self.on_new_model_status)
        self.new_model_selected.connect(self.model_manager.load_model)
        self.new_custom_model_selected.connect(
            self.model_manager.load_custom_model
        )
        self.model_manager.model_loaded.connect(self.update_visible_widgets)
        self.model_manager.model_loaded.connect(self.on_new_model_loaded)
        self.model_manager.new_auto_labeling_result.connect(
            lambda auto_labeling_result: self.parent.new_shapes_from_auto_labeling(
                auto_labeling_result
            )
        )
        self.model_manager.auto_segmentation_model_selected.connect(
            self.auto_segmentation_requested
        )
        self.model_manager.auto_segmentation_model_unselected.connect(
            self.auto_segmentation_disabled
        )
        self.model_manager.output_modes_changed.connect(
            self.on_output_modes_changed
        )
        self.output_select_combobox.currentIndexChanged.connect(
            lambda: self.model_manager.set_output_mode(
                self.output_select_combobox.currentData()
            )
        )

        # Download progress bar
        self._setup_download_progress_ui()
        self._setup_prediction_cancel_ui()
        self._setup_status_dot_ui()
        self._setup_more_panel()
        self.model_manager.download_progress.connect(
            self._on_download_progress
        )
        self.model_manager.download_finished.connect(
            self._on_download_finished
        )
        # Download *phases* (verifying / connecting / retrying) must stay
        # visible even while byte progress drives the same row, so they get
        # their own signal instead of riding on new_model_status (which the
        # view freezes via _downloading).
        self.model_manager.download_stage.connect(self._on_download_stage)
        self.model_manager.model_load_failed.connect(self._on_model_load_failed)

        # Disable tools when inference is running
        def set_enable_tools(enable):
            self.model_selection_button.setEnabled(enable)
            self.output_select_combobox.setEnabled(enable)
            self.button_add_point.setEnabled(enable)
            self.button_remove_point.setEnabled(enable)
            self.button_add_rect.setEnabled(enable)
            self.add_pos_rect.setEnabled(enable)
            self.add_neg_rect.setEnabled(enable)
            self.button_run_rect.setEnabled(enable)
            self.button_clear.setEnabled(enable)
            self.button_finish_object.setEnabled(enable)
            self.button_auto_decode.setEnabled(enable)
            self.button_cropping.setEnabled(enable)
            self.button_segment_everything.setEnabled(enable)
            self.button_skip_detection.setEnabled(enable)
            # The cancel affordance is *always* clickable while inference
            # runs, so the user is never trapped waiting for a long AMG
            # prediction with no way out.
            self._cancel_prediction_button.setEnabled(True)
            if enable:
                self._cancel_prediction_button.hide()
            else:
                self._cancel_prediction_button.show()

        self.model_manager.prediction_started.connect(
            lambda: set_enable_tools(False)
        )
        self.model_manager.prediction_finished.connect(
            lambda: set_enable_tools(True)
        )

        # Init value
        self.initial_conf_value = 0
        self.initial_iou_value = 0
        self.initial_preserve_annotations_state = False
        self.skip_detection = False
        self._amg_warning_confirmed = False

        # ===================================
        #  Auto labeling buttons
        # ===================================

        # --- Configuration for: model_selection_button ---
        model_data = self.init_model_data()
        self.model_dropdown = SearchableModelDropdownPopup(model_data)
        self.model_dropdown.hide()
        self.model_dropdown.modelSelected.connect(self.on_model_selected)
        self.model_dropdown.modelRemoveRequested.connect(
            self.on_model_remove_requested
        )
        self.model_selection_button.setAutoDefault(False)
        self.model_selection_button.setDefault(False)
        self.model_selection_button.setStyleSheet(get_normal_button_style())
        self.model_selection_button.setToolTip(
            "Select an AI model to use for auto labeling"
        )
        self.model_selection_button.clicked.connect(self.show_model_dropdown)
        combo_style = get_settings_combo_style()
        for combo in (
            self.output_select_combobox,
        ):
            combo.setStyleSheet(combo_style)

        # --- Configuration for: output_label ---
        self.output_label.setText(self.tr("Output"))

        # --- Configuration for: button_run ---
        self.button_run.setStyleSheet(get_highlight_button_style())
        self.button_run.setText(self.tr("Run (i)"))
        self.button_run.clicked.connect(self.run_prediction)

        # --- Configuration for: button_classes_filter ---
        self.button_classes_filter.setStyleSheet(get_normal_button_style())
        self.button_classes_filter.setText(self.tr("Classes"))
        self.button_classes_filter.setToolTip(
            "Filter which classes are detected / segmented"
        )
        self.button_classes_filter.clicked.connect(
            self.on_classes_filter_clicked
        )

        # --- Configuration for: input_box_thres ---
        self.input_box_thres.setText(self.tr("Box threshold"))

        # --- Configuration for: button_send ---
        self.button_send.setStyleSheet(get_highlight_button_style())
        self.button_send.setText(self.tr("Send"))
        self.button_send.clicked.connect(self.run_vl_prediction)

        # --- Configuration for: input_conf ---
        # Direct Chinese text (not tr) so the visible caption stays Chinese
        # regardless of the embedded translation table.
        self.input_conf.setText("置信度阈值")
        self.input_conf.setToolTip(
            "Confidence Threshold / 置信度阈值\n"
            "\n"
            "保留一个检测框所需的最低置信度（0~1）。\n"
            "得分低于该阈值的框会被视为背景并丢弃。\n"
            "\n"
            "· 调低（如 0.15）：更易检出目标，但误检（把背景当产品）可能增多\n"
            "· 调高（如 0.50）：更保守，只保留高置信结果，可能漏检\n"
            "\n"
            "默认 0.25，对应模型 yaml 中的 conf_threshold。"
        )
        self.input_conf.setAccessibleName(self.tr("Confidence threshold"))

        # --- Configuration for: edit_conf ---
        self.edit_conf.setStyleSheet(get_double_spinbox_style())
        self.edit_conf.setToolTip(
            "Confidence Threshold / 置信度阈值\n"
            "\n"
            "保留一个检测框所需的最低置信度（0~1）。\n"
            "得分低于该阈值的框会被视为背景并丢弃。\n"
            "\n"
            "· 调低（如 0.15）：更易检出目标，但误检（把背景当产品）可能增多\n"
            "· 调高（如 0.50）：更保守，只保留高置信结果，可能漏检\n"
            "\n"
            "默认 0.25，对应模型 yaml 中的 conf_threshold。"
        )
        self.edit_conf.valueChanged.connect(self.on_conf_value_changed)

        # --- Configuration for: input_iou ---
        self.input_iou.setText("交并比阈值")
        self.input_iou.setToolTip(
            "IoU Threshold / 交并比阈值（NMS 去重）\n"
            "\n"
            "非极大值抑制（NMS）去重阈值（0~1），\n"
            "用于决定两个重叠框是否合并成一个。\n"
            "\n"
            "· 调低：去重更激进，同一物体基本只剩一个框\n"
            "· 调高：允许更多重叠框共存，可能对同一目标输出多个框\n"
            "\n"
            "默认 0.45，对应模型 yaml 中的 iou_threshold。"
        )
        self.input_iou.setAccessibleName(self.tr("IoU threshold"))

        # --- Configuration for: edit_iou ---
        self.edit_iou.setStyleSheet(get_double_spinbox_style())
        self.edit_iou.setToolTip(
            "IoU Threshold / 交并比阈值（NMS 去重）\n"
            "\n"
            "非极大值抑制（NMS）去重阈值（0~1），\n"
            "用于决定两个重叠框是否合并成一个。\n"
            "\n"
            "· 调低：去重更激进，同一物体基本只剩一个框\n"
            "· 调高：允许更多重叠框共存，可能对同一目标输出多个框\n"
            "\n"
            "默认 0.45，对应模型 yaml 中的 iou_threshold。"
        )
        self.edit_iou.valueChanged.connect(self.on_iou_value_changed)

        # Runtime layout fix: guarantee the conf/iou *labels* (置信度阈值,
        # 交并比阈值) sit *before* their spinboxes. The .ui already orders
        # them that way, but a stray .ui re-ordering or theme quirk could
        # otherwise show 标签在输入框后面, which the user reported even on
        # the latest build. We re-parent the two labels to the immediate
        # left of their spinbox in the toolbar's QHBoxLayout.
        container = self.model_selection
        layout = container.layout() if hasattr(container, "layout") else None
        if layout is not None:
            for label_name, spinbox_name in (
                ("input_conf", "edit_conf"),
                ("input_iou", "edit_iou"),
            ):
                lbl = container.findChild(QLabel, label_name)
                spn = container.findChild(QDoubleSpinBox, spinbox_name)
                if lbl is None or spn is None:
                    continue
                lbl_idx = layout.indexOf(lbl)
                spn_idx = layout.indexOf(spn)
                if lbl_idx < 0 or spn_idx < 0 or lbl_idx >= spn_idx:
                    # Remove the label and re-insert it directly before
                    # the spinbox so the visual order becomes
                    # `置信度阈值  [0.25]`.
                    layout.removeWidget(lbl)
                    layout.insertWidget(spn_idx, lbl)

        # --- Configuration for: edit_text ---
        self.edit_text.setStyleSheet(get_lineedit_style())
        self.edit_text.setToolTip(
            "Enter text prompt here. Use dots (.) to separate multiple classes.\n"
            "Example: person.car.bicycle"
        )

        # --- Configuration for: button_add_point ---
        self.button_add_point.setToolTip(
            "Add a foreground point (left click on object, shortcut: q)"
        )
        self.button_add_point.clicked.connect(
            lambda: self.set_auto_labeling_mode(
                AutoLabelingMode.ADD, AutoLabelingMode.POINT
            )
        )

        # --- Configuration for: button_remove_point ---
        self.button_remove_point.setToolTip(
            "Remove a background point (left click, shortcut: e)"
        )
        self.button_remove_point.clicked.connect(
            lambda: self.set_auto_labeling_mode(
                AutoLabelingMode.REMOVE, AutoLabelingMode.POINT
            )
        )

        # --- Configuration for: button_add_rect ---
        self.button_add_rect.setText(self.tr("+Rect"))
        self.button_add_rect.setToolTip(
            "Add a box around the object to segment"
        )
        self.button_add_rect.clicked.connect(self.on_button_add_rect_clicked)

        # --- Configuration for: add_pos_rect ---
        self.add_pos_rect.setText(self.tr("+Rect"))
        self.add_pos_rect.setToolTip("Add positive region inside the box")
        self.add_pos_rect.clicked.connect(self.on_add_pos_rect_clicked)

        # --- Configuration for: add_neg_rect ---
        self.add_neg_rect.setText(self.tr("-Rect"))
        self.add_neg_rect.setToolTip("Add negative region inside the box")
        self.add_neg_rect.clicked.connect(self.on_add_neg_rect_clicked)

        # --- Configuration for: button_run_rect ---
        self.button_run_rect.setStyleSheet(get_highlight_button_style())
        self.button_run_rect.setText(self.tr("Run Rect"))
        self.button_run_rect.setToolTip(
            "Run inference with the current box prompts"
        )
        self.button_run_rect.clicked.connect(self.run_prediction)

        # --- Configuration for: button_clear ---
        self.button_clear.setText(self.tr("Clear (b)"))
        self.button_clear.setToolTip("Clear all prompts (shortcut: b)")
        self.button_clear.clicked.connect(self.on_clear_clicked)

        # --- Configuration for: button_finish_object ---
        self.button_finish_object.setText(self.tr("Finish (f)"))
        self.button_finish_object.setToolTip(
            "Finish the current object (shortcut: f)"
        )
        self.button_finish_object.clicked.connect(self.on_finish_clicked)

        # --- Configuration for: button_auto_decode ---
        self.button_auto_decode.setStyleSheet(get_normal_button_style())
        self.button_auto_decode.clicked.connect(self.on_auto_decode_toggled)
        self.button_auto_decode.setToolTip(
            self.tr(
                "Enable auto mask decode mode for continuous point tracking"
            )
        )

        # --- Configuration for: button_cropping ---
        self.button_cropping.setStyleSheet(get_normal_button_style())
        self.button_cropping.clicked.connect(self.on_cropping_toggled)
        self.button_cropping.setToolTip(
            self.tr(
                "Enable local cropping for rectangle prompts to improve accuracy "
                "for small objects in high-resolution images"
            )
        )

        # --- Configuration for: toggle_preserve_existing_annotations ---
        self.toggle_preserve_existing_annotations.setChecked(False)
        self.toggle_preserve_existing_annotations.setCheckable(True)
        self.toggle_preserve_existing_annotations.setStyleSheet(
            get_normal_button_style()
        )
        self.toggle_preserve_existing_annotations_tooltip_on = self.tr(
            "Existing shapes will be preserved during updates. Click to switch to overwriting."
        )
        self.toggle_preserve_existing_annotations_tooltip_off = self.tr(
            "Existing shapes will be overwritten by new shapes during updates. Click to switch to preserving."
        )
        self.toggle_preserve_existing_annotations.setToolTip(
            self.toggle_preserve_existing_annotations_tooltip_off
        )
        self.toggle_preserve_existing_annotations.setText(
            self.tr("Replace (On)")
        )
        self.toggle_preserve_existing_annotations.toggled.connect(
            self._on_toggle_preserve_existing_annotations_toggled
        )

        # --- Configuration for: button_skip_detection ---
        self.button_skip_detection.setStyleSheet(get_normal_button_style())
        self.button_skip_detection.setCheckable(True)
        self.button_skip_detection.setChecked(False)
        self.button_skip_detection.setToolTip(
            self.tr(
                "Skip detection model and use existing annotations as detection boxes"
            )
        )
        self.button_skip_detection.clicked.connect(
            self.on_skip_detection_toggled
        )

        # --- Configuration for: mask_fineness_slider ---
        self.mask_fineness_slider.setMinimumWidth(120)
        self.mask_fineness_slider.setStyleSheet(
            SliderStyle.get_slider_style()
        )
        self.mask_fineness_slider.valueChanged.connect(
            self.on_mask_fineness_changed
        )
        self.mask_fineness_slider.setToolTip(
            self.tr(
                "Adjust mask fineness: lower=finer, higher=coarser [Default: 0.001]"
            )
        )
        self.mask_fineness_value_label.setStyleSheet(f"""
            QLabel {{
                color: {get_theme()["text_secondary"]};
                font-size: 10px;
                font-weight: 500;
                background: transparent;
                border: none;
                padding: 0px;
            }}
        """)
        self.on_mask_fineness_changed(self.mask_fineness_slider.value())

        # --- Configuration for: button_segment_everything ---
        self.button_segment_everything.setText(self.tr("AMG"))
        self.button_segment_everything.setStyleSheet(get_normal_button_style())
        self.button_segment_everything.clicked.connect(
            self.on_segment_everything_clicked
        )
        self.button_segment_everything.setToolTip(
            self.tr("Automatically segment the whole image (no prompts)")
        )

        # ===================================
        #  End of Auto labeling buttons
        # ===================================

        # Hide labeling widgets by default
        self.hide_labeling_widgets()

        # Handle close button
        self.button_close.clicked.connect(self.unload_and_hide)

        self.auto_labeling_mode_changed.connect(self.update_button_colors)
        self.auto_labeling_mode = AutoLabelingMode.NONE
        self.auto_labeling_mode_changed.emit(self.auto_labeling_mode)

        # Populate select combobox with modes
        self.update_shortcut_button_texts()
        self._queue_model_selection_scroll_area_height_update()

    def _split_label_and_shortcut(self, text):
        normalized = str(text).strip()
        if "(" in normalized and normalized.endswith(")"):
            prefix, suffix = normalized.rsplit("(", 1)
            base = prefix.strip()
            shortcut = suffix[:-1].strip()
            if base:
                return base, shortcut
        return normalized, ""

    def _shortcut_value_to_text(self, value):
        if isinstance(value, (list, tuple)):
            return ",".join(str(v).strip() for v in value if str(v).strip())
        if value in (None, ""):
            return ""
        return str(value).strip()

    def _format_button_with_shortcut(
        self, current_text, value, default_shortcut=""
    ):
        base, existing_shortcut = self._split_label_and_shortcut(current_text)
        shortcut = self._shortcut_value_to_text(value)
        if not shortcut:
            shortcut = existing_shortcut or str(default_shortcut).strip()
        if shortcut:
            return f"{base} ({shortcut})"
        return base

    def update_shortcut_button_texts(self, shortcuts=None):
        if shortcuts is None:
            shortcuts = self.parent._config.get("shortcuts", {})
        self.button_add_point.setText(
            self._format_button_with_shortcut(
                self.button_add_point.text(),
                shortcuts.get("auto_labeling_add_point"),
                "q",
            )
        )
        self.button_remove_point.setText(
            self._format_button_with_shortcut(
                self.button_remove_point.text(),
                shortcuts.get("auto_labeling_remove_point"),
                "e",
            )
        )
        self.button_clear.setText(
            self._format_button_with_shortcut(
                self.button_clear.text(),
                shortcuts.get("auto_labeling_clear"),
                "b",
            )
        )
        self.button_finish_object.setText(
            self._format_button_with_shortcut(
                self.button_finish_object.text(),
                shortcuts.get("auto_labeling_finish_object"),
                "f",
            )
        )

    def init_model_data(self):
        """Get models data"""
        model_data = {
            "Custom": {
                "load_custom_model": {
                    "selected": False,
                    "favorite": False,
                    "display_name": "...Load Custom Model",
                }
            }
        }
        self.model_info = {
            "load_custom_model": {
                "display_name": "...Load Custom Model",
                "config_path": None,
            }
        }

        try:
            local_model_data = load_json(_get_models_config_path())[
                "models_data"
            ]
            for model_name, model_dict in local_model_data["Custom"].items():
                if model_name == "load_custom_model":
                    continue
                elif not os.path.exists(model_dict["config_path"]):
                    continue

                if not model_name.startswith("_custom_"):
                    model_name = f"_custom_{model_name}"

                model_data["Custom"][model_name] = {
                    "selected": False,
                    "favorite": model_dict["favorite"],
                    "display_name": model_dict["display_name"],
                    "config_path": model_dict["config_path"],
                }

                self.model_info[model_name] = {
                    "display_name": model_dict["display_name"],
                    "config_path": model_dict["config_path"],
                }

        except Exception as _:
            local_model_data = {}

        model_list = self.model_manager.get_model_configs()
        for model_dict in model_list:
            model_name = model_dict["name"]
            if model_dict.get("is_custom_model", False):
                provider_name = "Custom"
            else:
                provider_name = model_dict.get("provider", "Others")

            if provider_name not in model_data:
                model_data[provider_name] = {}

            if (
                provider_name in local_model_data
                and model_name in local_model_data[provider_name]
            ):
                local_model_data[provider_name][model_name][
                    "selected"
                ] = False
                # NOTE: only copy the matching model_name from the cache,
                # NOT the entire provider dict. Using dict.update() here
                # would leak stale entries (e.g. models that have since
                # been removed from the built-in presets) into the
                # dropdown and bloat it indefinitely as users keep a
                # long-lived xanylabeling_data/models.json.
                cached_entry = local_model_data[provider_name][model_name]
                model_data[provider_name][model_name] = {
                    "selected": False,
                    "favorite": cached_entry.get("favorite", False),
                    "display_name": cached_entry.get(
                        "display_name", model_dict["display_name"]
                    ),
                    "type": model_dict.get("type", ""),
                }
            else:
                model_data[provider_name][model_name] = {
                    "selected": False,
                    "favorite": False,
                    "display_name": model_dict["display_name"],
                    "type": model_dict.get("type", ""),
                }

            self.model_info[model_name] = {
                "display_name": model_dict["display_name"],
                "config_path": (
                    None
                    if model_name == "load_custom_model"
                    else model_dict["config_file"]
                ),
                "type": model_dict.get("type", ""),
            }

        mark_recommended_models(model_data)

        # Sort the collected model_data
        sorted_model_data = self._sort_model_data(model_data)

        return sorted_model_data

    def _sort_model_data(self, model_data: dict) -> collections.OrderedDict:
        """Sorts the model data dictionary"""

        def top_level_sort_key(key: str):
            if key == "Custom":
                return (0,)
            if key == "CVHub":
                return (0.5,)
            if key == "Others":
                return (2,)
            return (1, key)

        def inner_sort_key(item: tuple[str, dict]):
            _, model_details = item
            display_name = model_details.get("display_name", "")
            if display_name == "...Load Custom Model":
                return (0,)
            return (1, display_name)

        sorted_top_keys = sorted(model_data.keys(), key=top_level_sort_key)
        sorted_data = collections.OrderedDict()
        for key in sorted_top_keys:
            inner_dict = model_data[key]
            sorted_inner_items = sorted(inner_dict.items(), key=inner_sort_key)
            sorted_data[key] = collections.OrderedDict(sorted_inner_items)
        return sorted_data

    def show_model_dropdown(self):
        """Show the model dropdown"""
        button_pos = self.model_selection_button.mapToGlobal(QPoint(0, 0))
        self.model_dropdown.move(int(button_pos.x()), int(button_pos.y()))
        self.model_dropdown.adjustSize()
        self.model_dropdown.show()

    def on_model_remove_requested(self, provider, model_name):
        """Remove a user-added custom model after confirmation.

        Only the registry entry is removed (models.json + the app config).
        The weight files on disk are intentionally left in place, and the
        dialog tells the user where they are, so nothing is lost
        irreversibly.
        """
        if model_name == "load_custom_model":
            return
        if model_name not in self.model_info:
            return

        display_name = self.model_info[model_name].get("display_name", model_name)
        config_path = self.model_info[model_name].get("config_path", "")
        reply = QMessageBox.question(
            self,
            self.tr("Remove Custom Model"),
            self.tr(
                "Remove '%s' from the model list?\n\n"
                "Only the registry entry is removed. The config/weight "
                "files on disk are kept:\n%s"
            )
            % (display_name, config_path or self.tr("(unknown)")),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if config_path:
            try:
                self.model_manager.remove_custom_model(config_path)
            except Exception as e:  # noqa: BLE001
                logger.error(f"Failed to remove custom model: {e}")

        # Drop the entry from the persisted models.json + refresh the list.
        try:
            models_data = self.init_model_data()
            removed_any = False
            for prov in list(models_data.keys()):
                if model_name in models_data[prov]:
                    del models_data[prov][model_name]
                    removed_any = True
                if prov != "Custom" and not models_data[prov]:
                    del models_data[prov]
            if removed_any:
                save_json(
                    {"models_data": models_data}, _get_models_config_path()
                )
                self.model_dropdown.update_models_data(models_data)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to persist model removal: {e}")

        if model_name in self.model_info:
            del self.model_info[model_name]

        # If the removed model was the active one, reset the toolbar state.
        try:
            current_text = self.model_selection_button.text()
            if current_text and current_text.lstrip("● ").strip() == display_name:
                self.model_selection_button.setText(self.tr("选择 AI 模型"))
                self.model_selection_button.setEnabled(True)
                self.model_selection_button.setStyleSheet(
                    get_normal_button_style()
                )
        except Exception:  # noqa: BLE001
            pass
        self._set_status_label(
            self.tr("Model removed: %s") % display_name
        )

    def on_model_selected(self, provider, model_name):
        """Handle the model selected event"""

        if model_name == "load_custom_model":
            # Unload current model first
            self.model_manager.unload_model()

            # Open file dialog to select an .onnx weights file. Custom
            # models are ONNX-only: we auto-generate a matching yaml
            # under <work_dir>/custom_models/ and feed that to the
            # existing custom-model loader (so persistence and eviction
            # continue to work). No yaml or "All files" option is shown
            # because selecting anything but an .onnx would only produce
            # a confusing error at the next step.
            file_dialog = QFileDialog(self)
            file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
            file_dialog.setNameFilter("ONNX model (*.onnx)")

            if file_dialog.exec():
                self.hide_labeling_widgets()
                selected_path = file_dialog.selectedFiles()[0]
                try:
                    if (
                        Path(selected_path).suffix.lower()
                        in CUSTOM_MODEL_WEIGHT_EXTS
                    ):
                        config_file = (
                            _build_custom_model_yaml_from_weights(
                                selected_path
                            )
                        )
                    else:
                        config_file = selected_path
                    flag = self.model_manager.load_custom_model(config_file)
                except Exception as e:  # noqa: BLE001
                    logger.exception(
                        f"Failed to load custom model: {selected_path}: {e}"
                    )
                    self.model_manager.new_model_status.emit(
                        self.tr("Error in loading custom model: {error}").format(
                            error=str(e)
                        )
                    )
                    self.model_selection_button.setText(self.tr("选择 AI 模型"))
                    self.model_selection_button.setEnabled(True)
                    return
                if not flag:
                    self.model_selection_button.setText(self.tr("选择 AI 模型"))
                    self.model_selection_button.setEnabled(True)
                    return

                try:
                    # update model_info
                    with open(config_file, "r", encoding="utf-8") as f:
                        config_info = yaml.safe_load(f)

                    name = config_info.get("name")
                    display_name = config_info.get("display_name")
                    if not name or not display_name:
                        raise ValueError(
                            "Custom model config is missing required "
                            "fields 'name' or 'display_name'."
                        )

                    if not name.startswith("_custom_"):
                        name = f"_custom_{name}"

                    self.model_info[name] = {
                        "display_name": display_name,
                        "config_path": config_file,
                    }

                    # update model_data
                    models_data = self.init_model_data()
                    models_data["Custom"]["load_custom_model"]["selected"] = False
                    models_data["Custom"][name] = {
                        "selected": True,
                        "favorite": False,
                        "display_name": display_name,
                        "config_path": config_file,
                    }
                    save_json(
                        {"models_data": models_data}, _get_models_config_path()
                    )
                    self.model_dropdown.update_models_data(models_data)
                except Exception as e:  # noqa: BLE001
                    logger.exception(
                        f"Failed to register custom model {config_file}: {e}"
                    )
                    self.model_manager.new_model_status.emit(
                        self.tr(
                            "Error in registering custom model: {error}"
                        ).format(error=str(e))
                    )
                    self.model_selection_button.setText(self.tr("选择 AI 模型"))
                    self.model_selection_button.setEnabled(True)
                    return

                self.clear_auto_labeling_action_requested.emit()
                self.model_selection_button.setText(
                    config_info["display_name"]
                )
                self.model_selection_button.setEnabled(False)

            return

        # Validate model status
        if model_name not in self.model_info:
            logger.warning(
                f"Model '{model_name}' is not defined or no longer available. "
                "Removing from configuration."
            )
            # Update config to remove invalid model
            try:
                models_data = self.init_model_data()
                if (
                    provider in models_data
                    and model_name in models_data[provider]
                ):
                    del models_data[provider][model_name]
                    save_json(
                        {"models_data": models_data},
                        _get_models_config_path(),
                    )
                    self.model_dropdown.update_models_data(models_data)
            except Exception as e:
                logger.warning(f"Failed to update config: {e}")

            self.model_selection_button.setText(self.tr("选择 AI 模型"))
            self.model_selection_button.setEnabled(True)

            return

        self.clear_auto_labeling_action_requested.emit()
        self.model_selection_button.setText(
            self.model_info[model_name]["display_name"]
        )

        self.model_selection_button.setEnabled(False)
        self.hide_labeling_widgets()

        config_path = self.model_info[model_name]["config_path"]
        self._last_model_selection = (provider, model_name, config_path)

        if provider == "Custom":
            self.model_manager.load_custom_model(config_path)
        else:
            self.new_model_selected.emit(config_path)

    def update_button_colors(self):
        """Update button colors"""
        for button in [
            self.button_add_point,
            self.button_remove_point,
            self.button_add_rect,
            self.add_pos_rect,
            self.add_neg_rect,
            self.button_clear,
            self.button_finish_object,
        ]:
            button.setStyleSheet(get_normal_button_style())
        if self.auto_labeling_mode == AutoLabelingMode.NONE:
            return
        if self.auto_labeling_mode.edit_mode == AutoLabelingMode.ADD:
            if self.auto_labeling_mode.shape_type == AutoLabelingMode.POINT:
                self.button_add_point.setStyleSheet(
                    get_toggle_button_style(button_color="#90EE90")
                )
            elif (
                self.auto_labeling_mode.shape_type
                == AutoLabelingMode.RECTANGLE
            ):
                self.button_add_rect.setStyleSheet(
                    get_toggle_button_style(button_color="#90EE90")
                )
                self.add_pos_rect.setStyleSheet(
                    get_toggle_button_style(button_color="#90EE90")
                )
        elif self.auto_labeling_mode.edit_mode == AutoLabelingMode.REMOVE:
            if self.auto_labeling_mode.shape_type == AutoLabelingMode.POINT:
                self.button_remove_point.setStyleSheet(
                    get_toggle_button_style(button_color="#FFB6C1")
                )
            elif (
                self.auto_labeling_mode.shape_type
                == AutoLabelingMode.RECTANGLE
            ):
                self.add_neg_rect.setStyleSheet(
                    get_toggle_button_style(button_color="#FFB6C1")
                )

    def set_auto_labeling_mode(self, edit_mode, shape_type=None):
        """Set auto labeling mode"""
        if edit_mode is None:
            self.auto_labeling_mode = AutoLabelingMode.NONE
        else:
            self.auto_labeling_mode = AutoLabelingMode(edit_mode, shape_type)
        self.auto_labeling_mode_changed.emit(self.auto_labeling_mode)

    def run_prediction(self):
        """Run prediction"""
        if self.parent.filename is not None:
            if (
                self.button_skip_detection.isChecked()
                and self.parent.canvas.shapes
                and self.model_manager.loaded_model_config
                and self.model_manager.loaded_model_config["type"]
                in _SKIP_DET_MODELS
            ):
                existing_shapes = self._extract_shapes_for_recognition()
                if existing_shapes is not None:
                    self.model_manager.predict_shapes_threading(
                        self.parent.image,
                        self.parent.filename,
                        existing_shapes=existing_shapes,
                    )
                    return

            self.model_manager.predict_shapes_threading(
                self.parent.image, self.parent.filename
            )

    def on_segment_everything_clicked(self):
        """Trigger prompt-free full-image segmentation."""
        if not self._amg_warning_confirmed:
            reply = QMessageBox.warning(
                self,
                self.tr("AMG"),
                self.tr(
                    "AMG may take a long time to process the current image. "
                    "Do you want to continue?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._amg_warning_confirmed = True

        self.model_manager.set_auto_labeling_marks([{"type": "auto_grid"}])
        self.run_prediction()

    def run_vl_prediction(self):
        """Run visual-language prediction"""
        if self.parent.filename is not None and self.edit_text:
            self.model_manager.set_auto_labeling_marks([])
            self.model_manager.predict_shapes_threading(
                self.parent.image,
                self.parent.filename,
                text_prompt=self.edit_text.text(),
            )

    def _setup_download_progress_ui(self):
        """Build the download-progress row (hidden by default)."""
        self._download_widget = QWidget()
        layout = QHBoxLayout(self._download_widget)
        layout.setContentsMargins(0, 0, 0, 2)
        layout.setSpacing(8)

        self._download_progress_bar = QProgressBar()
        self._download_progress_bar.setRange(0, 100)
        self._download_progress_bar.setValue(0)
        self._download_progress_bar.setStyleSheet(
            get_download_progress_bar_style()
        )
        self._download_progress_bar.setFixedHeight(6)

        self._download_info_label = QLabel("")
        self._download_info_label.setStyleSheet(
            f"color: {get_theme()['text_secondary']}; "
            f"font-size: 11px; background: transparent; border: none;"
        )

        self._cancel_download_button = QPushButton(self.tr("Cancel"))
        self._cancel_download_button.setStyleSheet(
            get_cancel_download_button_style()
        )
        self._cancel_download_button.setFixedHeight(20)
        self._cancel_download_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self._cancel_download_button.clicked.connect(self._on_cancel_download)

        layout.addWidget(self._download_progress_bar, 1)
        layout.addWidget(self._download_info_label)
        layout.addWidget(self._cancel_download_button)

        main_layout = self.layout()
        main_layout.insertWidget(
            main_layout.indexOf(self.model_status_label), self._download_widget
        )
        self._download_widget.hide()
        self._downloading = False
        self._download_stage_text = ""

    def _setup_prediction_cancel_ui(self):
        """Build the "Cancel inference" affordance (hidden by default).

        Long AMG / segment-everything runs can take minutes; without this
        button the user is stuck with all tools disabled and no way to bail
        out.  Clicking it asks the manager to cancel: cooperative models
        (SAM2) abort their loops quickly, and the manager drops any result
        produced after the request so stale shapes never reach the canvas.
        """
        self._cancel_prediction_button = QPushButton(
            self.tr("Cancel Inference")
        )
        self._cancel_prediction_button.setStyleSheet(
            get_cancel_download_button_style()
        )
        self._cancel_prediction_button.setFixedHeight(20)
        self._cancel_prediction_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self._cancel_prediction_button.clicked.connect(
            self._on_cancel_prediction_clicked
        )
        main_layout = self.layout()
        main_layout.insertWidget(
            main_layout.indexOf(self.model_status_label) + 1,
            self._cancel_prediction_button,
        )
        self._cancel_prediction_button.hide()

    def _on_cancel_prediction_clicked(self):
        """Ask the manager to cancel the running inference and report it."""
        self.model_manager.cancel_prediction()
        self._set_status_label(self.tr("Cancelling inference..."))

    def _setup_status_dot_ui(self):
        """Tint the status label by state (success/error/busy/idle).

        A bare text row gives no at-a-glance signal whether the last model
        action succeeded, failed or is still running. Prefixing the text
        with a colored "●" and tinting the whole label fixes that without
        re-parenting the label (which would disturb the existing layout
        expectations of downstream geometry checks).
        """
        self._set_status_label(self.model_status_label.text())

    @staticmethod
    def _classify_status_color(text):
        """Map a status string to a color (success/error/busy/idle)."""
        t = get_theme()
        if not text:
            return t["text_secondary"]
        low = text.lower()
        success_keys = (
            "ready for labeling",
            "model loaded",
            "verified",
            "completed",
            "finished inferencing",
            "下载完成",
            "校验通过",
            "初始化完成",
            "已加载",
            "成功",
        )
        if any(k in low for k in success_keys):
            return t["success"]
        error_keys = (
            "error",
            "failed",
            "失败",
            "错误",
            "损坏",
            "corrupted",
            "timed out",
            "超时",
            "refused",
            "拒绝",
            "not found",
            "无法解析",
            "timeout",
        )
        if any(k in low for k in error_keys):
            return t["error"]
        busy_keys = (
            "loading",
            "downloading",
            "verifying",
            "connecting",
            "retrying",
            "initializing",
            "wait",
            "cancelling",
            "inferencing",
            "preparing",
            "正在",
            "下载",
            "校验",
            "连接",
            "重试",
            "准备",
            "加载",
            "初始化",
            "请",
        )
        if any(k in low for k in busy_keys):
            return t["warning"]
        return t["text_secondary"]

    def _set_status_label(self, status):
        """Render the status line with a colored '●' prefix by state."""
        color = self._classify_status_color(status)
        text = f"● {status}" if status else status
        self.model_status_label.setText(text)
        # Keep the original margins from auto_labeling.ui.
        self.model_status_label.setStyleSheet(
            f"color: {color}; margin-top: 0; margin-bottom: 2px;"
        )

    def _set_status_dot(self, text):
        # Retained for compatibility with callers; color handling is now
        # entirely inside _set_status_label.
        self._set_status_label(text)

    def _setup_more_panel(self):
        """Fold secondary controls behind a collapsible "More" panel.

        The toolbar is one scrolling row of 25+ controls. Low-frequency
        options (AMD/TinyObj/AMG/Skip Det/Replace/thresholds/IoU/classes/
        mask fineness) move into a wrapper that is hidden by default, so
        the primary row no longer overflows on typical window widths.

        Widgets keep their object names and parents inside ``_more_panel``,
        so the existing per-widget show/hide logic (``update_visible_widgets``
        / ``hide_labeling_widgets``) keeps working unchanged — collapsing
        only toggles the wrapper container's visibility.
        """
        self._MORE_PANEL_WIDGETS = {
            "button_run_rect",
            "input_box_thres",
            "input_conf",
            "edit_conf",
            "input_iou",
            "edit_iou",
            "button_auto_decode",
            "button_cropping",
            "button_segment_everything",
            "button_skip_detection",
            "toggle_preserve_existing_annotations",
            "button_classes_filter",
            "mask_fineness_value_label",
            "mask_fineness_slider",
        }
        main_layout = self.findChild(QHBoxLayout, "model_selection")
        if main_layout is None:
            logger.warning(
                "model_selection layout not found; More panel skipped"
            )
            return

        self._more_panel = QWidget()
        self._more_panel.setObjectName("more_panel")
        panel_layout = QHBoxLayout(self._more_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(6)

        # Direct children of the main row.
        direct_names = sorted(
            self._MORE_PANEL_WIDGETS
            - {"mask_fineness_value_label", "mask_fineness_slider"}
        )
        for name in direct_names:
            widget = getattr(self, name)
            main_layout.removeWidget(widget)
            widget.setParent(self._more_panel)
            panel_layout.addWidget(widget)

        # mask_fineness_value_label / mask_fineness_slider live in the
        # nested mask_fineness_layout inside the main row.
        mf_layout = self.findChild(QHBoxLayout, "mask_fineness_layout")
        for name in ("mask_fineness_value_label", "mask_fineness_slider"):
            widget = getattr(self, name)
            if mf_layout is not None:
                mf_layout.removeWidget(widget)
            widget.setParent(self._more_panel)
            panel_layout.addWidget(widget)

        self._more_button = QPushButton("更多 ▾")
        self._more_button.setCheckable(True)
        self._more_button.setStyleSheet(get_normal_button_style())
        self._more_button.setToolTip("Show/hide more AI labeling options")
        self._more_button.clicked.connect(self._on_toggle_more_panel)

        close_index = main_layout.indexOf(self.button_close)
        main_layout.insertWidget(close_index, self._more_button)
        main_layout.insertWidget(close_index + 1, self._more_panel)
        self._more_panel.hide()
        self._update_model_selection_scroll_area_height()

    def _on_toggle_more_panel(self, checked):
        self._more_panel.setVisible(checked)
        self._more_button.setText("更多 ▴" if checked else "更多 ▾")
        self._update_model_selection_scroll_area_height()

    @staticmethod
    def _format_bytes(n):
        for unit in ("B", "KB", "MB", "GB"):
            if abs(n) < 1024:
                return f"{n:.1f}{unit}"
            n /= 1024
        return f"{n:.1f}TB"

    @pyqtSlot(str)
    def _on_download_stage(self, stage):
        """Show a download phase.

        Phases are emitted *before* any byte progress exists — during the
        local integrity check, DNS resolution and the TLS handshake — which
        is exactly the window where the UI used to sit frozen on
        "Downloading model from registry..." with no further feedback.
        """
        if not stage:
            return
        self._download_stage_text = stage
        if self._downloading:
            # Already streaming bytes: the byte readout is more precise, so
            # keep it and stash the phase in the tooltip.
            self._download_info_label.setToolTip(stage)
            return
        # No bytes yet -> swap in the progress row and run an indeterminate
        # bar so the user can tell something is actually happening.
        self._download_widget.show()
        self.model_status_label.hide()
        self._download_progress_bar.setRange(0, 0)
        self._download_info_label.setText(stage)

    @pyqtSlot(int, int)
    def _on_download_progress(self, downloaded, total):
        if not self._downloading:
            self._downloading = True
            self._download_widget.show()
            self.model_status_label.hide()
        if total > 0:
            percent = int(downloaded * 100 / total)
            self._download_progress_bar.setRange(0, 100)
            self._download_progress_bar.setValue(percent)
            self._download_info_label.setText(
                f"{self._format_bytes(downloaded)} / "
                f"{self._format_bytes(total)}  ({percent}%)"
            )
        else:
            self._download_progress_bar.setRange(0, 0)
            self._download_info_label.setText(
                f"{self._format_bytes(downloaded)}"
            )

    @pyqtSlot()
    def _on_download_finished(self):
        self._downloading = False
        self._download_stage_text = ""
        self._download_widget.hide()
        self.model_status_label.show()
        # Restore a determinate range; phase reporting may have left the bar
        # in indeterminate (marquee) mode.
        self._download_progress_bar.setRange(0, 100)
        self._download_progress_bar.setValue(0)
        self._download_info_label.setText("")
        self._download_info_label.setToolTip("")

    @pyqtSlot(str)
    def _on_model_load_failed(self, error_text):
        """Surface a failed model load / download so the user sees why.

        ``new_model_status`` is frozen while byte progress is streaming
        (``_downloading``), so load failures used to vanish silently: the
        download row was hidden and the toolbar fell back to "Select AI
        model" with a stale "Loading..." text left behind.  This dedicated
        channel always lands on the status label (tinted red) and clears
        the download row.
        """
        self._downloading = False
        self._download_stage_text = ""
        self._download_widget.hide()
        self._download_progress_bar.setRange(0, 100)
        self._download_progress_bar.setValue(0)
        self._download_info_label.setText("")
        self._download_info_label.setToolTip("")
        self.model_status_label.show()
        friendly, offer_cpu = classify_model_load_error(error_text)
        self._set_status_label(self.tr("Model load failed: %s") % friendly)
        self._show_model_load_failed_dialog(friendly, offer_cpu)

    def _show_model_load_failed_dialog(self, friendly, offer_cpu):
        box = QMessageBox(self)
        box.setWindowTitle(self.tr("模型加载失败"))
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(friendly)
        cpu_btn = None
        if offer_cpu:
            cpu_btn = box.addButton(
                self.tr("改用 CPU 并重试"),
                QMessageBox.ButtonRole.AcceptRole,
            )
        change_btn = box.addButton(
            self.tr("重新选择模型"), QMessageBox.ButtonRole.ActionRole
        )
        box.addButton(self.tr("关闭"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if offer_cpu and clicked == cpu_btn:
            self._retry_last_model_on_cpu()
        elif clicked == change_btn:
            self.show_model_dropdown()

    def _retry_last_model_on_cpu(self):
        from anylabeling.config import save_config
        from anylabeling.views.common.device_manager import device_manager

        config = get_config()
        config["device"] = "CPU"
        save_config(config)
        device_manager.set_device("CPU")
        selection = self._last_model_selection
        if not selection:
            self.show_model_dropdown()
            return
        provider, _name, config_path = selection
        if not config_path:
            self.show_model_dropdown()
            return
        self.model_selection_button.setEnabled(False)
        if provider == "Custom":
            self.model_manager.load_custom_model(config_path)
        else:
            self.new_model_selected.emit(config_path)

    def _on_cancel_download(self):
        self.model_manager.cancel_download()
        self._downloading = False
        self._download_stage_text = ""
        self._download_widget.hide()
        self.model_status_label.show()
        self.model_status_label.setText(self.tr("Cancelling..."))
        self._download_progress_bar.setRange(0, 100)
        self._download_progress_bar.setValue(0)
        self._download_info_label.setText("")
        self._download_info_label.setToolTip("")

    def unload_and_hide(self):
        """Unload model and hide widget"""
        self.hide()

    def on_new_model_status(self, status):
        if not self._downloading:
            self._set_status_label(status)

    def _apply_model_button_state(self, model_config):
        """Reflect the load result on the model-selection button.

        A successful load gets a green-tinted outline plus a "● " prefix;
        a failed / empty load (``model_config`` without display_name)
        reverts to the default idle look so the toolbar never claims a
        model is ready when it is not.
        """
        display_name = model_config.get("display_name")
        if display_name:
            self.model_selection_button.setText(f"● {display_name}")
            self.model_selection_button.setStyleSheet(
                get_ready_button_style()
            )
        else:
            self.model_selection_button.setText(self.tr("选择 AI 模型"))
            self.model_selection_button.setStyleSheet(
                get_normal_button_style()
            )

    def on_new_model_loaded(self, model_config):
        """Enable model select combobox"""
        self.model_selection_button.setEnabled(True)
        self._apply_model_button_state(model_config)

        # Reset controls to initial values when the model changes
        try:
            if (
                self.model_manager.loaded_model_config["type"]
                in _AUTO_LABELING_IOU_MODELS
            ):
                if "iou_threshold" in self.model_manager.loaded_model_config:
                    initial_iou_value = self.model_manager.loaded_model_config[
                        "iou_threshold"
                    ]
                elif "nms_threshold" in self.model_manager.loaded_model_config:
                    initial_iou_value = self.model_manager.loaded_model_config[
                        "nms_threshold"
                    ]
                self.edit_iou.setValue(initial_iou_value)
            else:
                initial_iou_value = 0.0
                self.edit_iou.setValue(initial_iou_value)
        except Exception as _:
            initial_iou_value = 0.0
            self.edit_iou.setValue(initial_iou_value)

        try:
            if (
                self.model_manager.loaded_model_config["type"]
                in _AUTO_LABELING_CONF_MODELS
            ):
                if "conf_threshold" in self.model_manager.loaded_model_config:
                    initial_conf_value = (
                        self.model_manager.loaded_model_config[
                            "conf_threshold"
                        ]
                    )
                elif "box_threshold" in self.model_manager.loaded_model_config:
                    initial_conf_value = (
                        self.model_manager.loaded_model_config["box_threshold"]
                    )
                elif (
                    "confidence_threshold"
                    in self.model_manager.loaded_model_config
                ):
                    initial_conf_value = (
                        self.model_manager.loaded_model_config[
                            "confidence_threshold"
                        ]
                    )
                self.edit_conf.setValue(initial_conf_value)
            else:
                initial_conf_value = 0.0
                self.edit_conf.setValue(initial_conf_value)
        except Exception as _:
            initial_conf_value = 0.0
            self.edit_conf.setValue(initial_conf_value)

        self.on_iou_value_changed(initial_iou_value)
        self.on_conf_value_changed(initial_conf_value)
        self.on_preserve_existing_annotations_state_changed(
            self.initial_preserve_annotations_state
        )

        # Update specific mode in UI if specific model is loaded

    def on_output_modes_changed(self, output_modes, default_output_mode):
        """Handle output modes changed"""
        # Disconnect onIndexChanged signal to prevent triggering
        # on model select combobox change
        self.output_select_combobox.currentIndexChanged.disconnect()

        self.output_select_combobox.clear()
        for output_mode, display_name in output_modes.items():
            self.output_select_combobox.addItem(
                display_name, userData=output_mode
            )
        self.output_select_combobox.setCurrentIndex(
            self.output_select_combobox.findData(default_output_mode)
        )

        # Reconnect onIndexChanged signal
        self.output_select_combobox.currentIndexChanged.connect(
            lambda: self.model_manager.set_output_mode(
                self.output_select_combobox.currentData()
            )
        )

    def update_visible_widgets(self, model_config):
        """Update widget status"""
        if not model_config or "model" not in model_config:
            return
        widgets = model_config["model"].get_required_widgets()
        for widget_name in widgets:
            if hasattr(self, widget_name):
                getattr(self, widget_name).show()
            else:
                logger.warning(
                    f"Warning: Widget '{widget_name}' not found in AutoLabelingWidget."
                )
        # If this model needs widgets parked inside the collapsed "More"
        # panel, expand it so the tools are actually visible.
        if hasattr(self, "_more_panel") and self._more_panel is not None:
            panel_names = getattr(self, "_MORE_PANEL_WIDGETS", set())
            if panel_names.intersection(widgets) and not self._more_panel.isVisible():
                self._more_button.setChecked(True)
                self._more_panel.show()
        self._update_model_selection_scroll_area_height()

    def hide_labeling_widgets(self):
        """Hide labeling widgets by default"""
        widgets = [
            "button_run",
            "button_add_point",
            "button_remove_point",
            "button_add_rect",
            "add_pos_rect",
            "add_neg_rect",
            "button_run_rect",
            "button_clear",
            "button_finish_object",
            "button_send",
            "edit_text",
            "edit_conf",
            "edit_iou",
            "input_box_thres",
            "input_conf",
            "input_iou",
            "output_label",
            "output_select_combobox",
            "toggle_preserve_existing_annotations",
            "button_classes_filter",
            "button_auto_decode",
            "button_cropping",
            "button_skip_detection",
            "mask_fineness_slider",
            "mask_fineness_value_label",
            "button_segment_everything",
        ]
        for widget in widgets:
            getattr(self, widget).hide()
        self._update_model_selection_scroll_area_height()

    def showEvent(self, event):
        super().showEvent(event)
        self._queue_model_selection_scroll_area_height_update()

    def _queue_model_selection_scroll_area_height_update(self):
        QTimer.singleShot(0, self._update_model_selection_scroll_area_height)

    def _update_model_selection_scroll_area_height(self, *_):
        update_model_selection_scroll_area_height(
            self.model_selection_scroll_area
        )

    def on_new_marks(self, marks):
        """Handle new marks"""
        self.model_manager.set_auto_labeling_marks(marks)
        if self.skip_auto_prediction:
            return
        if not self.model_manager.loaded_model_config:
            return
        current_model_name = self.model_manager.loaded_model_config["type"]
        if current_model_name not in _SKIP_PREDICTION_ON_NEW_MARKS_MODELS:
            self.run_prediction()

    def on_open(self):
        pass

    def on_close(self):
        return True

    def on_conf_value_changed(self, value):
        """Handle conf value changed"""
        self.model_manager.set_auto_labeling_conf(value)

    def on_iou_value_changed(self, value):
        """Handle iou value changed"""
        self.model_manager.set_auto_labeling_iou(value)

    def _on_toggle_preserve_existing_annotations_toggled(self, checked):
        """Handle toggle button state change - update UI and notify backend"""
        if checked:
            self.toggle_preserve_existing_annotations.setText(
                self.tr("Replace (Off)")
            )
            self.toggle_preserve_existing_annotations.setToolTip(
                self.toggle_preserve_existing_annotations_tooltip_on
            )
        else:
            self.toggle_preserve_existing_annotations.setText(
                self.tr("Replace (On)")
            )
            self.toggle_preserve_existing_annotations.setToolTip(
                self.toggle_preserve_existing_annotations_tooltip_off
            )

        # Notify backend
        self.on_preserve_existing_annotations_state_changed(checked)

    def on_preserve_existing_annotations_state_changed(self, state):
        """Handle preserve existing annotations state changed"""
        self.initial_preserve_annotations_state = state
        self.model_manager.set_auto_labeling_preserve_existing_annotations_state(
            state
        )

    def on_classes_filter_clicked(self):
        """Open the classes filter dialog and apply the selection."""
        if self.model_manager.loaded_model_config is None:
            return
        model = self.model_manager.loaded_model_config.get("model")
        classes_attr = getattr(model, "classes", [])
        if not classes_attr:
            return
        if isinstance(classes_attr, dict):
            class_names = [
                classes_attr[k] for k in sorted(classes_attr.keys())
            ]
        else:
            class_names = list(classes_attr)

        raw_filter = getattr(model, "filter_classes", None)
        filter_names = None
        if isinstance(raw_filter, list):
            if (
                raw_filter
                and isinstance(raw_filter[0], int)
                and not isinstance(classes_attr, dict)
            ):
                filter_names = [
                    class_names[i]
                    for i in raw_filter
                    if 0 <= int(i) < len(class_names)
                ]
            else:
                filter_names = raw_filter
        dialog = ClassesFilterDialog(class_names, filter_names, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.model_manager.set_auto_labeling_filter_classes(
                dialog.get_selected_classes()
            )

    def on_cache_auto_label_changed(self, text, gid):
        self.model_manager.set_cache_auto_label(text, gid)

    def on_auto_decode_toggled(self):
        """Handle AMD button toggle"""
        is_checked = self.button_auto_decode.isChecked()

        if is_checked:
            self.button_auto_decode.setStyleSheet(
                get_toggle_button_style(button_color="#87CEEB")
            )
        else:
            self.button_auto_decode.setStyleSheet(get_normal_button_style())

        self.auto_decode_mode_changed.emit(is_checked)

    def on_cropping_toggled(self):
        """Handle TinyObj button toggle"""
        is_checked = self.button_cropping.isChecked()

        if is_checked:
            self.button_cropping.setStyleSheet(
                get_toggle_button_style(button_color="#F8E003")
            )
        else:
            self.button_cropping.setStyleSheet(get_normal_button_style())

        self.cropping_mode_changed.emit(is_checked)

    def on_button_add_rect_clicked(self):
        """Handle button_add_rect click"""
        self.skip_auto_prediction = False
        self.set_auto_labeling_mode(
            AutoLabelingMode.ADD, AutoLabelingMode.RECTANGLE
        )

    def on_add_pos_rect_clicked(self):
        """Handle add_pos_rect click"""
        if (
            self.auto_labeling_mode.edit_mode == AutoLabelingMode.ADD
            and self.auto_labeling_mode.shape_type
            == AutoLabelingMode.RECTANGLE
        ):
            self.skip_auto_prediction = False
            self.set_auto_labeling_mode(None, None)
        else:
            self.skip_auto_prediction = True
            self.set_auto_labeling_mode(
                AutoLabelingMode.ADD, AutoLabelingMode.RECTANGLE
            )

    def on_add_neg_rect_clicked(self):
        """Handle add_neg_rect click"""
        if (
            self.auto_labeling_mode.edit_mode == AutoLabelingMode.REMOVE
            and self.auto_labeling_mode.shape_type
            == AutoLabelingMode.RECTANGLE
        ):
            self.skip_auto_prediction = False
            self.set_auto_labeling_mode(None, None)
        else:
            self.skip_auto_prediction = True
            self.set_auto_labeling_mode(
                AutoLabelingMode.REMOVE, AutoLabelingMode.RECTANGLE
            )

    def on_clear_clicked(self):
        """Handle clear button click"""
        self.model_manager.set_auto_labeling_marks([])
        self.clear_auto_decode_requested.emit()
        self.clear_auto_labeling_action_requested.emit()

        # Adaptation for Segment Anything 3 Video Integration

    def on_finish_clicked(self):
        """Handle finish button click"""
        self.clear_auto_decode_requested.emit()
        self.finish_auto_labeling_object_action_requested.emit()
        self.cache_auto_label_changed.emit()

    def on_skip_detection_toggled(self):
        """Handle skip detection button toggle"""
        is_checked = self.button_skip_detection.isChecked()

        if is_checked:
            self.button_skip_detection.setStyleSheet(
                get_toggle_button_style(button_color="#90EE90")
            )
        else:
            self.button_skip_detection.setStyleSheet(get_normal_button_style())

        self.skip_detection = is_checked

    def _extract_shapes_for_recognition(self):
        """Extract shapes for text recognition"""
        shapes_for_recognition = []
        for shape in self.parent.canvas.shapes:
            if shape.shape_type in ["rectangle", "rotation", "polygon"]:
                shapes_for_recognition.append(shape)
            else:
                error_text = self.tr(
                    "Existing unsupported shape type. Only rectangle, rotation and polygon shapes are supported for detection boxes."
                )
                self.model_manager.new_model_status.emit(error_text)
                raise ValueError(error_text)

        return shapes_for_recognition

    def on_mask_fineness_changed(self, value):
        """Handle mask fineness slider change"""
        # Map slider value (1-100) to epsilon range (0.0001-0.01)
        epsilon = 0.0001 + (value - 1) * (0.01 - 0.0001) / 99

        self.mask_fineness_value_label.setText(f"{epsilon:.4f}")
        self.model_manager.set_mask_fineness(epsilon)
        self.mask_fineness_changed.emit(epsilon)
