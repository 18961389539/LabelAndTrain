"""Guard the places where shipped defaults are written twice.

A default is only real if the template, the migration table and the UI agree.
This used to drift silently: ``logger_level`` sat in the rc file but startup
read the CLI value, the conf/iou spinboxes started at 0.00 while their
tooltips said 0.25/0.45, and the same thresholds were written in seven
files. These tests make that class of drift loud.
"""

import importlib.resources as pkg_resources
import io
import os
import xml.etree.ElementTree as ET

import yaml

from jllabeling import configs
from jllabeling.config import _MIGRATIONS, _get_nested_value

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def _template():
    with pkg_resources.open_text(configs, "jllabeling_config.yaml") as handle:
        return yaml.safe_load(handle)


def test_template_version_matches_latest_migration():
    template = _template()
    assert template["config_version"] == max(_MIGRATIONS), (
        "config_version in jllabeling_config.yaml must be bumped whenever a "
        "new _MIGRATIONS generation is added, or existing installs never "
        "receive the new defaults"
    )


def test_latest_migration_targets_match_the_template():
    """For each key, the newest migration's new value IS the shipped default.

    A generation that ends at a value the template no longer ships would
    upgrade existing users *away* from the defaults a fresh install gets.
    Older generations are allowed to disagree (v1 moved 10 -> 100, v3 then
    moved 100 -> 30), so only the last rule per key is compared.
    """
    template = _template()
    latest = {}
    for version in sorted(_MIGRATIONS):
        for key_path, _old, new in _MIGRATIONS[version]:
            latest[key_path] = (version, new)
    mismatches = [
        f"{key}: migration v{version} ends at {new!r}, template has "
        f"{_get_nested_value(template, key)!r}"
        for key, (version, new) in latest.items()
        if _get_nested_value(template, key) != new
    ]
    assert mismatches == [], "\n".join(mismatches)


def test_v3_industrial_defaults_are_present():
    """The defaults that matter for large/offline datasets cannot regress."""
    template = _template()
    expected = {
        "qt_image_allocation_limit": 1024,
        "exif_scan_enabled": False,
        "startup_show_project_manager": False,
        "file_list_checkbox_editable": True,
    }
    for key, value in expected.items():
        assert template[key] == value, f"{key} regressed to {template[key]!r}"
    assert template["training"]["ultralytics"]["project_readonly"] is False
    assert template["canvas"]["num_backups"] == 30
    assert template["canvas"]["brush"]["max_undo_memory_mb"] == 64
    # Kept deliberately: turning exact validation on without a labels file
    # used to abort startup. Privacy-friendly defaults stay off.
    assert template["validate_label"] is None
    assert template["store_data"] is False
    assert template["system_clipboard"] is False


def test_shortcuts_have_no_duplicate_bindings():
    template = _template()
    bound = {}
    duplicates = []
    for key, value in template["shortcuts"].items():
        if not value or key == "zoom_in":
            continue
        normalized = value[0] if isinstance(value, list) else value
        if normalized in bound:
            duplicates.append((bound[normalized], key, normalized))
        bound[normalized] = key
    assert duplicates == [], f"ambiguous shortcuts: {duplicates}"


def test_ui_spinbox_defaults_match_shared_thresholds():
    """The .ui must not drift from thresholds.py a second time."""
    from jllabeling.services.auto_labeling.thresholds import (
        DEFAULT_CONF_THRESHOLD,
        DEFAULT_IOU_THRESHOLD,
    )

    ui_path = os.path.join(
        REPO_ROOT,
        "jllabeling",
        "views",
        "labeling",
        "widgets",
        "auto_labeling",
        "auto_labeling.ui",
    )
    with io.open(ui_path, encoding="utf-8") as handle:
        root = ET.parse(handle).getroot()

    def value_of(name):
        for widget in root.iter("widget"):
            if widget.get("name") != name:
                continue
            for prop in widget.findall("property"):
                if prop.get("name") == "value":
                    return float(prop.find("double").text)
        return None

    assert value_of("edit_conf") == DEFAULT_CONF_THRESHOLD
    assert value_of("edit_iou") == DEFAULT_IOU_THRESHOLD
