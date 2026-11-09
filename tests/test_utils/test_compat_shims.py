"""The old import paths must keep exporting the names callers already use.

The headless-core extraction moved implementations into ``jllabeling.core``
and left thin re-export modules behind, so no caller had to change.  Those
callers are the contract: a name that quietly disappears from one of these
modules breaks an import in a file nobody edited, and it breaks at import
time -- the whole application, not one feature.

The lists below are frozen on purpose.  Retiring a name means deleting it
here in the same commit, which is the review moment where "who still
imports this?" gets asked.  Every check is a subset check, so *adding* a
name never needs a change to this file.

Two kinds of old path are covered:

* real re-export modules, imported and compared by object identity.  A
  shim that starts carrying its own copy of the logic would drift from the
  core module, and ``test_exported_objects_are_the_implementation`` is what
  notices;
* lazily resolved ``_EXPORTS`` tables, parsed with :mod:`ast` rather than
  imported, because resolving one of those names pulls the whole Qt widget
  graph into the test process and would tax every headless run.
"""

import ast
import importlib
from pathlib import Path
from typing import NamedTuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


class Shim(NamedTuple):
    """A compatibility module, the core modules behind it, and its surface."""

    old: str
    sources: tuple
    names: tuple


SHIMS = (
    Shim(
        old="jllabeling.views.labeling.schema",
        sources=("jllabeling.core.labels.schema", "jllabeling.app_info"),
        names=(
            "__version__",
            "REVIEW_CONFIRMED",
            "REVIEW_NOTE_FIELD",
            "REVIEW_REJECTED",
            "REVIEW_STATES",
            "REVIEW_UNCHECKED",
            "XLABEL_BASIC_FIELDS",
            "create_xlabel_template",
            "is_review_confirmed",
            "review_state_of",
        ),
    ),
    Shim(
        old="jllabeling.views.labeling.project",
        sources=("jllabeling.core.projects.project", "jllabeling.core.io"),
        names=(
            "load_json",
            "save_json",
            "DEFAULT_TASK",
            "PROJECT_DIR_NAME",
            "PROJECT_FILE_NAME",
            "SCHEMA",
            "TASK_TYPES",
            "get_or_create_split_seed",
            "label_dir_for_dataset",
            "load_project",
            "project_path",
            "save_project",
        ),
    ),
    Shim(
        old="jllabeling.views.labeling.provenance",
        sources=("jllabeling.core.labels.provenance",),
        names=(
            "DIGEST_CHARS",
            "MODEL_FIELD",
            "MODEL_VERSION_FIELD",
            "SOURCE_FIELD",
            "SOURCE_HUMAN",
            "SOURCE_MODEL",
            "SOURCE_UNKNOWN",
            "SOURCES",
            "collect_other_model_shapes",
            "describe_shape",
            "get_source",
            "is_deletable_stale_shape",
            "is_from_other_model",
            "model_display_name",
            "model_identity_label",
            "model_of",
            "model_version_of",
            "resolve_model_path",
            "shape_marker",
            "shape_points",
            "stamp_model_shapes",
            "weight_digest",
        ),
    ),
    Shim(
        old="jllabeling.views.labeling.utils._io",
        sources=("jllabeling.core.io",),
        names=(
            "copy_file_atomic",
            "io_open",
            "load_json",
            "safe_replace",
            "save_json",
            "save_text",
        ),
    ),
)


SHIM_IDS = [shim.old for shim in SHIMS]


def test_no_shim_is_listed_twice():
    olds = [shim.old for shim in SHIMS]
    assert len(olds) == len(set(olds)), olds


@pytest.mark.parametrize("shim", SHIMS, ids=SHIM_IDS)
def test_frozen_names_are_still_exported(shim):
    module = importlib.import_module(shim.old)
    missing = [name for name in shim.names if not hasattr(module, name)]
    assert missing == [], f"{shim.old} no longer exports {missing}"


@pytest.mark.parametrize("shim", SHIMS, ids=SHIM_IDS)
def test_exported_objects_are_the_implementation(shim):
    """A re-export must be the same object, not a look-alike.

    Copying the implementation into the shim keeps the imports working and
    the tests green until the two copies disagree, which is the failure this
    check exists to prevent.
    """
    module = importlib.import_module(shim.old)
    drifted = []
    for name in shim.names:
        for source_name in shim.sources:
            source = importlib.import_module(source_name)
            if not hasattr(source, name):
                continue
            if getattr(module, name) is not getattr(source, name):
                drifted.append(f"{name} (declared in {source_name})")
    assert drifted == [], (
        f"{shim.old} defines its own copy of {drifted}; "
        "delete it and re-export from the core module instead"
    )


@pytest.mark.parametrize("shim", SHIMS, ids=SHIM_IDS)
def test_shims_carry_no_logic_of_their_own(shim):
    """The shims are import plumbing only -- nothing may be defined in them."""
    module = importlib.import_module(shim.old)
    local = sorted(
        name
        for name in dir(module)
        if getattr(getattr(module, name), "__module__", None) == shim.old
    )
    assert local == [], (
        f"{shim.old} defines {local} itself; move the implementation to the "
        "core module and import it here"
    )


class LazyTable(NamedTuple):
    """A package whose ``_EXPORTS`` dict is the public surface."""

    module: str
    path: str
    names: tuple


#: ``jllabeling.views.labeling.utils`` -- resolved on first attribute access.
UTILS_EXPORTS = tuple("""
    AsyncExifScanner AsyncLabelChecker ExifProcessingDialog StayOpenMenuFilter
    Struct add_actions check_img_exif distance distance_to_line
    ensure_pillow_heif_registered export_coco_annotation export_voc_annotation
    export_yolo_annotation find_most_similar_label fmt_shortcut get_pil_img_dim
    get_supported_image_extensions gradient_text hex_to_rgb icc_profile_issue
    img_arr_to_b64 img_b64_to_arr img_data_to_arr img_data_to_pil
    img_data_to_png_data img_data_to_qimage img_pil_to_data io_open is_chinese
    label_colormap label_validator load_json masks_to_bboxes new_action
    new_button new_icon on_thumbnail_click open_shape_converter
    polygons_to_mask process_image_exif rectangle_from_diagonal run_all_images
    save_crop save_json save_visualization scan_all_images shape_to_mask
    shapes_to_label upload_coco_annotation upload_image_flags_file
    upload_label_classes_file upload_label_flags_file upload_shape_attrs_file
    upload_voc_annotation upload_yolo_annotation
    """.split())

#: ``jllabeling.views.labeling.widgets`` -- resolved on first attribute access.
WIDGET_EXPORTS = tuple("""
    AutoLabelingWidget BrightnessContrastDialog Canvas CanvasAdjustmentWidget
    CanvasEmptyStateWidget CrosshairSettingsDialog DigitShortcutDialog
    FileDialogPreview FloatingToolPanel GroupIDFilterComboBox
    GroupIDModifyDialog LabelDialog LabelFilterComboBox LabelListWidget
    LabelListWidgetItem LabelModifyDialog LabelQLineEdit NavigatorDialog
    OverviewDialog PolygonSidesDialog Popup SearchBar ShapeModifyDialog ToolBar
    UniqueLabelQListWidget ZoomWidget copy_text_to_system_clipboard
    """.split())

LAZY_TABLES = (
    LazyTable(
        module="jllabeling.views.labeling.utils",
        path="jllabeling/views/labeling/utils/__init__.py",
        names=UTILS_EXPORTS,
    ),
    LazyTable(
        module="jllabeling.views.labeling.widgets",
        path="jllabeling/views/labeling/widgets/__init__.py",
        names=WIDGET_EXPORTS,
    ),
)


TABLE_IDS = [table.module for table in LAZY_TABLES]


def _lazy_exports(relative_path):
    """Read the literal ``_EXPORTS`` dict out of a package, without importing it."""
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign):
            continue
        if any(
            getattr(target, "id", None) == "_EXPORTS"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(
        f"{relative_path} no longer defines a literal _EXPORTS table; this "
        "test reads it statically on purpose, see the module docstring"
    )


@pytest.mark.parametrize("table", LAZY_TABLES, ids=TABLE_IDS)
def test_lazy_tables_still_resolve_every_frozen_name(table):
    declared = _lazy_exports(table.path)
    missing = [name for name in table.names if name not in declared]
    assert missing == [], f"{table.module} no longer resolves {missing}"


@pytest.mark.parametrize("table", LAZY_TABLES, ids=TABLE_IDS)
def test_lazy_tables_point_at_sibling_modules_only(table):
    """A target has to be a module inside the same package, or the lookup
    silently changes meaning (``import_module`` would resolve it elsewhere)."""
    declared = _lazy_exports(table.path)
    outside = sorted(
        f"{name} -> {target}"
        for name, target in declared.items()
        if not target.startswith(".") or target.startswith("..")
    )
    assert outside == [], f"{table.module} maps {outside} outside its package"


@pytest.mark.parametrize("table", LAZY_TABLES, ids=TABLE_IDS)
def test_lazy_tables_point_at_files_that_exist(table):
    """A renamed or deleted helper leaves a table entry that only fails when
    somebody touches that one name -- long after the rename looked safe."""
    declared = _lazy_exports(table.path)
    directory = (REPO_ROOT / table.path).parent
    dangling = sorted(
        f"{name} -> {target}"
        for name, target in declared.items()
        if not (directory / f"{target[1:]}.py").exists()
        and not (directory / target[1:] / "__init__.py").exists()
    )
    assert (
        dangling == []
    ), f"{table.module} maps to missing modules: {dangling}"
