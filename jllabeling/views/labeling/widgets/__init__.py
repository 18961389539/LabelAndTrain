# flake8: noqa
"""Widget exports for the labeling views, resolved lazily.

Importing this package used to import every widget.  Several of those
widgets import ``label_file`` or ``shape``, so a helper such as
``utils.shape`` would pull the whole GUI graph back into itself.  Resolving
names on first access keeps the old import surface while letting callers
load only the widget they actually use.
"""

from importlib import import_module

_EXPORTS = {
    "AutoLabelingWidget": ".auto_labeling",
    "BrightnessContrastDialog": ".brightness_contrast_dialog",
    "Canvas": ".canvas",
    "CanvasAdjustmentWidget": ".canvas_adjustment",
    "CanvasEmptyStateWidget": ".canvas_empty_state",
    "CrosshairSettingsDialog": ".crosshair_settings_dialog",
    "FileDialogPreview": ".file_dialog_preview",
    "GroupIDFilterComboBox": ".filter_label_widget",
    "LabelFilterComboBox": ".filter_label_widget",
    "ShapeModifyDialog": ".shape_dialog",
    "DigitShortcutDialog": ".label_dialog",
    "GroupIDModifyDialog": ".label_dialog",
    "LabelDialog": ".label_dialog",
    "LabelModifyDialog": ".label_dialog",
    "LabelQLineEdit": ".label_dialog",
    "LabelListWidget": ".label_list_widget",
    "LabelListWidgetItem": ".label_list_widget",
    "SearchBar": ".searchable_model_dropdown",
    "NavigatorDialog": ".navigator_widget",
    "OverviewDialog": ".overview_dialog",
    "PolygonSidesDialog": ".polygon_sides_dialog",
    "Popup": ".popup",
    "copy_text_to_system_clipboard": ".popup",
    "FloatingToolPanel": ".toolbar",
    "ToolBar": ".toolbar",
    "UniqueLabelQListWidget": ".unique_label_qlist_widget",
    "ZoomWidget": ".zoom_widget",
}


def __getattr__(name):
    module_name = _EXPORTS.get(name)
    if module_name is not None:
        value = getattr(import_module(module_name, __name__), name)
        globals()[name] = value
        return value
    if name.startswith("_"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    qualified = f"{__name__}.{name}"
    try:
        module = import_module(qualified)
    except ModuleNotFoundError as error:
        if error.name != qualified:
            raise
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from error
    globals()[name] = module
    return module


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))
