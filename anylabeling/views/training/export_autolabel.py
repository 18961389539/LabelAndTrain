"""Export and auto-label hand-off for the training dialog.

A finished or stopped run becomes usable in the labeling loop through this
module: export ``weights/best.pt`` to ONNX, then write the custom-model YAML
and load it into the auto-labeling panel together with the run's class names.
The dialog keeps the button wiring and its stubs; artifact freshness, the
dependency-consent prompt and the feedback prompt after loading live here.
"""

from __future__ import annotations

import os

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QDialog, QMessageBox

from anylabeling.config import save_config as save_labeling_config
from anylabeling.services.auto_training.ultralytics._io import (
    load_yaml_config,
)
from anylabeling.services.auto_training.ultralytics.exporter import (
    get_export_validator,
)
from anylabeling.services.auto_training.ultralytics.utils import (
    autolabel_type_for_task,
    collect_class_names,
    sanitize_custom_model_name,
    write_autolabel_model_yaml,
)
from anylabeling.services.auto_training.ultralytics.validators import (
    validate_data_file,
)
from anylabeling.views.labeling.logger import logger
from anylabeling.views.training.widgets.ultralytics_widgets import (
    ExportFormatDialog,
)


def is_fresh_export(exported_path: str, weights_path: str) -> bool:
    """True when an already-exported artifact is not older than its weights.

    "用于自动标注" reuses ``weights/best.onnx`` when it exists, without
    comparing dates, so resuming a run and then reloading the model handed
    back the ONNX from before the resume — a run that looks finished with a
    model that is not the one on screen. An unreadable timestamp counts as
    stale, so the artifact is rebuilt rather than trusted.
    """
    if not exported_path or not weights_path:
        return False
    try:
        if not os.path.exists(exported_path):
            return False
        return os.path.getmtime(exported_path) >= os.path.getmtime(
            weights_path
        )
    except OSError:
        return False


def on_export_event(widget, event_type, data):
    if event_type == "export_started":
        widget.append_training_log(
            QCoreApplication.translate(
                "UltralyticsDialog", "Export started..."
            )
        )
        widget.export_button.setEnabled(False)
        if hasattr(widget, "use_autolabel_button"):
            widget.use_autolabel_button.setEnabled(False)
    elif event_type == "export_completed":
        exported_path = data.get("exported_path", "")
        export_format = data.get("format", "onnx")
        widget.append_training_log(
            QCoreApplication.translate(
                "UltralyticsDialog",
                f"Export completed successfully! File saved to: {exported_path}",
            )
        )
        widget.export_button.setEnabled(True)
        if hasattr(widget, "use_autolabel_button"):
            widget.use_autolabel_button.setEnabled(True)
        if widget._pending_autolabel_after_export:
            widget._pending_autolabel_after_export = False
            if exported_path:
                widget._load_exported_weights_for_autolabel(exported_path)
            return
        QMessageBox.information(
            widget,
            QCoreApplication.translate(
                "UltralyticsDialog", "Export Successful"
            ),
            QCoreApplication.translate(
                "UltralyticsDialog",
                f"Model successfully exported to {export_format.upper()} format:\n{exported_path}",
            ),
        )
    elif event_type == "export_error":
        error_msg = data.get("error", "Unknown error occurred")
        widget.append_training_log(f"ERROR: {error_msg}")
        widget.export_button.setEnabled(True)
        if hasattr(widget, "use_autolabel_button"):
            widget.use_autolabel_button.setEnabled(True)
        if widget._pending_autolabel_after_export:
            widget._pending_autolabel_after_export = False
            QMessageBox.warning(
                widget,
                QCoreApplication.translate(
                    "UltralyticsDialog", "Export Error"
                ),
                QCoreApplication.translate(
                    "UltralyticsDialog",
                    "Failed to export ONNX; not loaded into auto-labeling.\n%1",
                ).replace("%1", error_msg),
            )
            return
        QMessageBox.warning(
            widget,
            QCoreApplication.translate("UltralyticsDialog", "Export Error"),
            error_msg,
        )
    elif event_type == "export_log":
        log_message = data.get("message", "")
        if log_message:
            widget.append_training_log(log_message)


def start_export(widget):
    if not widget.current_project_path:
        QMessageBox.warning(
            widget,
            QCoreApplication.translate("UltralyticsDialog", "Error"),
            QCoreApplication.translate(
                "UltralyticsDialog", "No training project available for export"
            ),
        )
        return

    weights_path = os.path.join(
        widget.current_project_path, "weights", "best.pt"
    )
    if not os.path.exists(weights_path):
        QMessageBox.warning(
            widget,
            QCoreApplication.translate("UltralyticsDialog", "Model Not Found"),
            QCoreApplication.translate(
                "UltralyticsDialog",
                f"Model weights not found at: {weights_path}",
            ),
        )
        return

    export_dialog = ExportFormatDialog(widget)
    if export_dialog.exec() != QDialog.DialogCode.Accepted:
        return
    export_format = export_dialog.get_selected_format()
    if not widget._confirm_export_dependencies(export_format):
        return
    success, message = widget.export_manager.start_export(
        widget.current_project_path, export_format, allow_install=True
    )
    if not success:
        QMessageBox.critical(
            widget,
            QCoreApplication.translate("UltralyticsDialog", "Export Error"),
            message,
        )
        widget.append_training_log(f"Failed to start export: {message}")


def _resolve_class_names(widget):
    if widget.names:
        return list(widget.names)
    if getattr(widget, "_config_tab_initialized", False):
        data_widget = widget.config_widgets.get("data")
        if data_widget is not None:
            path = data_widget.text().strip().strip('"')
            if path and os.path.isfile(path):
                is_valid, result = validate_data_file(path)
                if is_valid and isinstance(result, list):
                    return result
    return collect_class_names(widget.image_list, widget.output_dir)


def use_weights_for_autolabel(widget):
    model_type = autolabel_type_for_task(widget.selected_task_type)
    if not model_type:
        QMessageBox.information(
            widget,
            QCoreApplication.translate(
                "UltralyticsDialog", "Not supported yet"
            ),
            QCoreApplication.translate(
                "UltralyticsDialog",
                "No auto-labeling type for this task yet; export the weights and load the model manually. Supported: detect / segment / pose / classify (ONNX).",
            ),
        )
        return
    if not widget.current_project_path:
        QMessageBox.warning(
            widget,
            QCoreApplication.translate("UltralyticsDialog", "Error"),
            QCoreApplication.translate(
                "UltralyticsDialog", "No training project available for export"
            ),
        )
        return
    weights_path = os.path.join(
        widget.current_project_path, "weights", "best.pt"
    )
    if not os.path.exists(weights_path):
        QMessageBox.warning(
            widget,
            QCoreApplication.translate("UltralyticsDialog", "Model Not Found"),
            QCoreApplication.translate(
                "UltralyticsDialog", "Model weights not found at: %1"
            ).replace("%1", weights_path),
        )
        return
    onnx_path = os.path.join(
        widget.current_project_path, "weights", "best.onnx"
    )
    if os.path.exists(onnx_path) and not is_fresh_export(
        onnx_path, weights_path
    ):
        # Reusing a stale artifact silently pairs the run on screen with
        # the model from before the last resume, so it is rebuilt instead.
        widget.append_training_log(
            QCoreApplication.translate(
                "UltralyticsDialog",
                "The existing ONNX export is older than best.pt; exporting again.",
            )
        )
    elif os.path.exists(onnx_path):
        widget._load_exported_weights_for_autolabel(onnx_path)
        return
    if not widget._confirm_export_dependencies("onnx"):
        widget.append_training_log(
            QCoreApplication.translate(
                "UltralyticsDialog",
                "Auto-labeling export cancelled: dependencies missing.",
            )
        )
        return
    widget._pending_autolabel_after_export = True
    widget.use_autolabel_button.setEnabled(False)
    widget.append_training_log(
        QCoreApplication.translate(
            "UltralyticsDialog", "Exporting ONNX for auto-labeling..."
        )
    )
    success, message = widget.export_manager.start_export(
        widget.current_project_path, "onnx", allow_install=True
    )
    if not success:
        widget._pending_autolabel_after_export = False
        widget.use_autolabel_button.setEnabled(True)
        QMessageBox.critical(
            widget,
            QCoreApplication.translate("UltralyticsDialog", "Export Error"),
            message,
        )
        widget.append_training_log(f"Failed to start export: {message}")


def _confirm_export_dependencies(widget, export_format):
    """Ask before pip touches the environment; True means "carry on".

    The worker used to install missing packages by itself, unprompted, with
    a 30s timeout that no real wheel download fits in — so the automatic
    path could only fail slowly. Consent is asked here, on the UI thread
    (a worker thread cannot show a modal dialog), and the prompt carries
    the exact command, which is the only route a packaged build has.
    """
    missing = get_export_validator(export_format)()
    if not missing:
        return True

    missing_text = ", ".join(missing)
    manual = f"pip install {missing_text}"
    reply = QMessageBox.question(
        widget,
        QCoreApplication.translate(
            "UltralyticsDialog", "Missing Export Dependencies"
        ),
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Exporting to %1 needs these packages:\n%2\n\n"
            "Install them now with pip?\n%3\n\n"
            "Choosing No cancels the export. Nothing is installed without asking.",
        )
        .replace("%1", export_format)
        .replace("%2", missing_text)
        .replace("%3", manual),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if reply == QMessageBox.StandardButton.Yes:
        widget.append_training_log(
            f"Installing export dependencies: {missing_text}"
        )
        return True
    widget.append_training_log(f"Export cancelled; install manually: {manual}")
    return False


def _record_active_learning_round(widget, parent):
    """Log one train -> relabel round for the marginal-gain dashboard."""
    try:
        from anylabeling.views.labeling.utils.active_learning import (
            read_last_map50,
        )
        from anylabeling.views.labeling.utils.smart_review import (
            record_training_round,
        )

        map50 = None
        if widget.current_project_path:
            map50 = read_last_map50(
                os.path.join(widget.current_project_path, "results.csv")
            )
        record_training_round(
            parent,
            widget.current_project_path,
            model_name=os.path.basename(
                os.path.normpath(widget.current_project_path or "")
            ),
            map50=map50,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to record active learning round: {exc}")


def _resolve_pose_classes(widget):
    """``({class: [keypoint names]}, has_visible)`` from the pose config.

    The pose adapter reads ``classes`` as a mapping and derives
    ``kpt_shape`` from it when the exported ONNX carries no metadata, so
    the names must come from the same pose config training used.
    """
    path = ""
    pose_widget = widget.config_widgets.get("pose_config")
    if pose_widget is not None:
        path = pose_widget.text().strip().strip('"')
    if not path or not os.path.isfile(path):
        return None, True
    try:
        data = load_yaml_config(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Failed to read pose config {path}: {exc}")
        return None, True
    classes = (data or {}).get("classes")
    if not isinstance(classes, dict) or not classes:
        return None, True
    mapping = {}
    for class_name, key_points in classes.items():
        if not isinstance(key_points, (list, tuple)) or not key_points:
            return None, True
        mapping[str(class_name)] = [str(name) for name in key_points]
    return mapping, bool((data or {}).get("has_visible", True))


def _load_exported_weights_for_autolabel(widget, onnx_path):
    has_visible = True
    if widget.selected_task_type == "Pose":
        classes, has_visible = widget._resolve_pose_classes()
        if not classes:
            QMessageBox.warning(
                widget,
                QCoreApplication.translate(
                    "UltralyticsDialog", "Missing pose config"
                ),
                QCoreApplication.translate(
                    "UltralyticsDialog",
                    "Pose feedback needs the same pose config used for training (classes: class name -> keypoint name list). Fill in Pose Config on the Data tab and retry.",
                ),
            )
            return
    else:
        classes = widget._resolve_class_names()
    if not classes:
        QMessageBox.warning(
            widget,
            QCoreApplication.translate("UltralyticsDialog", "Missing classes"),
            QCoreApplication.translate(
                "UltralyticsDialog",
                "Could not read class names from the labels; check the data config and retry.",
            ),
        )
        return
    model_type = autolabel_type_for_task(widget.selected_task_type)
    if not model_type:
        return
    project_name = os.path.basename(
        os.path.normpath(widget.current_project_path)
    )
    name = sanitize_custom_model_name(f"{project_name}_best")
    display_name = QCoreApplication.translate(
        "UltralyticsDialog", "Training weights · %1"
    ).replace("%1", project_name)
    yaml_path = os.path.join(
        widget.current_project_path, "weights", f"{name}.yaml"
    )
    write_autolabel_model_yaml(
        yaml_path,
        model_type=model_type,
        name=name,
        display_name=display_name,
        model_path=onnx_path,
        classes=classes,
        has_visible=has_visible,
        # A classifier ranks its top-k; a 0.25 floor would silently drop
        # every suggestion once the classes are many.
        conf_threshold=(
            0.0 if widget.selected_task_type == "Classify" else 0.25
        ),
    )
    parent = widget.parent()
    widget.accept()
    autolabel_widget = (
        getattr(parent, "auto_labeling_widget", None) if parent else None
    )
    if autolabel_widget is None:
        return
    autolabel_widget._last_model_selection = ("Custom", name, yaml_path)
    autolabel_widget.show()
    widget._sync_training_classes_to_label_dock(parent, classes)

    def _on_exported_model_loaded(model_config):
        try:
            autolabel_widget.model_manager.model_loaded.disconnect(
                _on_exported_model_loaded
            )
        except TypeError:
            pass
        if not model_config or not model_config.get("model"):
            return
        if parent is None:
            return
        from anylabeling.views.labeling.utils.active_learning import (
            load_history,
            suggest_next_step,
        )
        from anylabeling.views.labeling.utils.smart_ui import (
            label_dir_for,
        )

        label_dir = label_dir_for(parent)
        suggestion = suggest_next_step(load_history(label_dir))
        suggestion_text = QCoreApplication.translate(
            "UltralyticsDialog", "Current iteration suggestion: %1"
        ).replace("%1", suggestion["reason"])
        reply = QMessageBox.question(
            parent,
            QCoreApplication.translate("LabelingWidget", "Feed Back Now"),
            QCoreApplication.translate(
                "LabelingWidget",
                "Training weights loaded. Re-run auto-labeling on unlabeled and pending-review images; the Iteration Gains Board updates automatically when done.\nConfirmed empty labels (negatives) are skipped.\n\n%1\n\nStart now?",
            ).replace("%1", suggestion_text),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            if hasattr(parent, "status"):
                parent.status(
                    QCoreApplication.translate(
                        "LabelingWidget",
                        "Check the next-step suggestions in the Iteration Gains Board later.",
                    ),
                    4000,
                )
            return
        from anylabeling.views.labeling.utils.active_learning import (
            count_annotations,
        )
        from anylabeling.views.labeling.utils.batch import run_all_images
        from anylabeling.views.labeling.utils.quality import (
            file_needs_re_autolabel,
        )
        from anylabeling.views.labeling.utils.smart_review import (
            watch_relabel_result,
        )

        output_dir = getattr(parent, "output_dir", None)
        baseline = count_annotations(
            list(getattr(parent, "image_list", None) or []), label_dir
        )
        widget._record_active_learning_round(parent)
        run_all_images(
            parent,
            prompt=False,
            from_start=True,
            skip_existing=False,
            skip_if=lambda image_file, directory=output_dir: (
                not file_needs_re_autolabel(image_file, directory)
            ),
        )
        watch_relabel_result(parent, label_dir, baseline)

    autolabel_widget.model_manager.model_loaded.connect(
        _on_exported_model_loaded
    )
    # Pin it: the iteration history now references this model, so the
    # custom-model cap must never evict it behind the user's back.
    autolabel_widget.model_manager.load_custom_model(yaml_path, pin=True)


def _sync_training_classes_to_label_dock(widget, parent, classes):
    if parent is None or not classes:
        return
    from anylabeling.views.labeling.utils.yolo_detect import (
        merge_class_names,
    )

    dock_names = []
    unique_list = getattr(parent, "unique_label_list", None)
    if unique_list is not None:
        for row in range(unique_list.count()):
            item = unique_list.item(row)
            if item is None:
                continue
            dock_names.append(item.data(Qt.ItemDataRole.UserRole))
    merged = merge_class_names(classes, dock_names)
    load_labels = getattr(parent, "load_labels", None)
    if callable(load_labels):
        load_labels(merged, clear_existing=True)
    config = getattr(parent, "_config", None)
    if isinstance(config, dict):
        config["labels"] = merged
        save_labeling_config(config)
