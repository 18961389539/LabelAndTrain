# flake8: noqa
"""Utility exports for the labeling views, resolved lazily.

These modules depend on each other through the Qt widget layer.  Eager
re-exports meant that importing one helper (for example
``utils.shape.rectangle_from_diagonal``) also imported ``batch``, every
widget, and eventually ``label_file`` again -- a circular import that only
worked because ``jllabeling/__init__`` happened to load the GUI first.

Names are now resolved on first access.  The public surface is unchanged:
``from ...utils import get_pil_img_dim`` and ``utils.image`` both still work.
"""

from importlib import import_module

_EXPORTS = {
    "AsyncExifScanner": ".async_exif",
    "ExifProcessingDialog": ".async_exif",
    "AsyncLabelChecker": ".async_label_check",
    "run_all_images": ".batch",
    "label_colormap": ".colormap",
    "save_crop": ".crop",
    "export_yolo_annotation": ".export",
    "export_voc_annotation": ".export",
    "export_coco_annotation": ".export",
    "gradient_text": ".general",
    "hex_to_rgb": ".general",
    "is_chinese": ".general",
    "find_most_similar_label": ".general",
    "check_img_exif": ".image",
    "ensure_pillow_heif_registered": ".image",
    "get_pil_img_dim": ".image",
    "img_arr_to_b64": ".image",
    "img_b64_to_arr": ".image",
    "img_data_to_arr": ".image",
    "img_data_to_pil": ".image",
    "img_data_to_png_data": ".image",
    "img_data_to_qimage": ".image",
    "img_pil_to_data": ".image",
    "get_supported_image_extensions": ".image",
    "icc_profile_issue": ".image",
    "process_image_exif": ".image",
    "io_open": "._io",
    "load_json": "._io",
    "save_json": "._io",
    "Struct": ".qt",
    "StayOpenMenuFilter": ".qt",
    "add_actions": ".qt",
    "scan_all_images": ".qt",
    "distance": ".qt",
    "distance_to_line": ".qt",
    "fmt_shortcut": ".qt",
    "label_validator": ".qt",
    "new_action": ".qt",
    "new_button": ".qt",
    "new_icon": ".qt",
    "on_thumbnail_click": ".qt",
    "masks_to_bboxes": ".shape",
    "polygons_to_mask": ".shape",
    "shape_to_mask": ".shape",
    "shapes_to_label": ".shape",
    "rectangle_from_diagonal": ".shape",
    "open_shape_converter": ".shape",
    "upload_image_flags_file": ".upload",
    "upload_label_flags_file": ".upload",
    "upload_shape_attrs_file": ".upload",
    "upload_label_classes_file": ".upload",
    "upload_yolo_annotation": ".upload",
    "upload_voc_annotation": ".upload",
    "upload_coco_annotation": ".upload",
    "save_visualization": ".visualization",
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
