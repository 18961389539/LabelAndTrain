"""Shortcut wiring guards.

Three relationships used to be able to drift here without anything going
red:

* an ``action(...)`` with no shortcut at all — the feature existed, no key
  reached it, and because the key was missing from the yaml table too, the
  settings dialog could not even offer a rebind;
* a yaml shortcut key that no code consumes: a ghost key the user can edit
  with no effect;
* a settings-dialog description for a shortcut that no longer exists.

The three-layer count check (yaml / runtime map / F1 sheet) cannot see any
of them, because all three layers stay mutually consistent while being
wrong together. This module locks the relationships that actually matter:
action -> yaml, yaml -> consumer, description -> yaml.
"""

import ast
import pathlib
import re
import unittest

try:
    from anylabeling.views.labeling.settings.schema import (
        load_template_config,
    )
    from anylabeling.views.labeling.utils.shortcuts_help import (
        NO_KEY_TEXT,
        UNBOUND_ACTIONS,
        UNBOUND_GROUP_TITLE,
        build_shortcut_rows,
    )

    SCHEMA_AVAILABLE = True
except Exception:  # pragma: no cover - import guard, mirrors test_schema
    SCHEMA_AVAILABLE = False


ROOT = pathlib.Path(__file__).resolve().parents[2]
LABEL_WIDGET = ROOT / "anylabeling/views/labeling/label_widget.py"
DIALOG = ROOT / "anylabeling/views/labeling/settings/dialog.py"
APPLIER = ROOT / "anylabeling/views/labeling/settings/runtime_applier.py"
PACKAGE = ROOT / "anylabeling"

#: Actions that deliberately carry no keyboard entry.
#:
#: Every entry is a one-off menu item — a file dialog, a batch export, a
#: training launcher — none of which belongs to the per-image annotation
#: loop, so a key would only add noise to the F1 sheet. The list is written
#: out on purpose: an action added without deciding "does this need a key?"
#: fails ``test_keyless_actions_are_declared_by_design`` instead of quietly
#: shipping as mouse-only. Entries must be removed as soon as they gain a
#: key (the assertion is bidirectional).
NO_SHORTCUT_BY_DESIGN = frozenset(
    {
        "confirm_classification",
        "copy_coordinates",
        "export_yolo_hbb_annotation",
        "export_yolo_obb_annotation",
        "export_yolo_pose_annotation",
        "export_yolo_seg_annotation",
        "run_history",
        "save_auto",
        "save_crop",
        "save_visualization_image",
        "save_with_image_data",
        "set_cross_line",
        "toggle_shape_lock",
        "ultralytics_train",
        "upload_image_flags_file",
        "upload_label_classes_file",
        "upload_label_flags_file",
        "upload_yolo_hbb_annotation",
        "upload_yolo_obb_annotation",
        "upload_yolo_pose_annotation",
        "upload_yolo_seg_annotation",
        "use_system_clipboard",
    }
)


def _classify(call):
    """Return ``(kind, value)`` for one ``action(...)`` call.

    ``kind`` is ``"config"`` (value is the yaml shortcut key), ``"literal"``
    (a hard-coded key sequence, e.g. the digit shortcuts) or ``"none"``.
    """
    candidates = []
    if len(call.args) >= 3:
        candidates.append(call.args[2])
    for keyword in call.keywords:
        if keyword.arg == "shortcut":
            candidates.append(keyword.value)
    for candidate in candidates:
        if isinstance(candidate, ast.Subscript):
            return ("config", ast.unparse(candidate.slice).strip("'\""))
        if (
            isinstance(candidate, ast.Call)
            and getattr(candidate.func, "attr", "") == "get"
        ):
            return ("config", ast.unparse(candidate.args[0]).strip("'\""))
        if isinstance(candidate, ast.Constant) and isinstance(
            candidate.value, str
        ):
            return ("literal", candidate.value)
    return ("none", None)


def _action_shortcuts():
    """Map every ``action()`` variable name to its shortcut classification."""
    tree = ast.parse(LABEL_WIDGET.read_text(encoding="utf-8"))
    found = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        call = node.value
        if not isinstance(target, ast.Name) or not isinstance(call, ast.Call):
            continue
        if not isinstance(call.func, ast.Name) or call.func.id != "action":
            continue
        found[target.id] = _classify(call)
    return found


def _config_keys_in(path):
    """Shortcut config keys referenced anywhere in ``path``."""
    text = path.read_text(encoding="utf-8", errors="replace")
    keys = set(
        re.findall(
            r'shortcuts(?:\.get\(\s*|\[\s*)["\']([a-z_0-9]+)["\']', text
        )
    )
    keys |= set(re.findall(r'"shortcuts\.([a-z_0-9]+)"', text))
    return keys


def _applier_generically_binds_unbound_actions():
    """The declared-but-unbound keys are read only by one loop."""
    text = APPLIER.read_text(encoding="utf-8")
    return "for config_key, _description in UNBOUND_ACTIONS" in text


def _shortcut_consumers():
    """Every shortcut config key referenced anywhere in the package."""
    keys = set()
    for path in PACKAGE.rglob("*.py"):
        if "__pycache__" in str(path):
            continue
        keys |= _config_keys_in(path)
    if _applier_generically_binds_unbound_actions():
        keys |= {key for key, _ in UNBOUND_ACTIONS}
    return keys


@unittest.skipUnless(
    SCHEMA_AVAILABLE, "Settings schema dependencies are unavailable"
)
class TestShortcutBindings(unittest.TestCase):
    def setUp(self):
        self.shortcuts = load_template_config()["shortcuts"]

    def test_every_wired_shortcut_exists_in_the_template(self):
        wired = {
            key
            for kind, key in _action_shortcuts().values()
            if kind == "config"
        }
        self.assertTrue(wired, "no action() wired any shortcut at all")
        missing = sorted(wired - set(self.shortcuts))
        self.assertEqual(
            missing,
            [],
            "these actions bind a shortcut key that the template yaml does "
            "not define, so the key can never be rebound or shown in F1",
        )

    def test_keyless_actions_are_declared_by_design(self):
        keyless = {
            name
            for name, (kind, _) in _action_shortcuts().items()
            if kind == "none"
        }
        self.assertEqual(
            sorted(keyless - NO_SHORTCUT_BY_DESIGN),
            [],
            "these actions have no keyboard entry and are not declared in "
            "NO_SHORTCUT_BY_DESIGN — either wire a shortcut or declare it",
        )
        self.assertEqual(
            sorted(NO_SHORTCUT_BY_DESIGN - keyless),
            [],
            "these entries gained a shortcut and must leave "
            "NO_SHORTCUT_BY_DESIGN so the list keeps shrinking honestly",
        )

    def test_no_ghost_shortcut_keys(self):
        consumers = _shortcut_consumers()
        ghosts = sorted(set(self.shortcuts) - consumers)
        self.assertEqual(
            ghosts,
            [],
            "these keys are editable in the settings dialog but no code "
            "reads them, so changing them does nothing",
        )

    def test_the_unbound_actions_are_declared_in_the_template(self):
        """An entry the settings dialog never sees is not rebindable."""
        declared = [key for key, _ in UNBOUND_ACTIONS]
        self.assertEqual(
            sorted(set(declared) - set(self.shortcuts)),
            [],
            "these actions are advertised as rebindable but have no key in "
            "the template, so the settings dialog has no row for them",
        )
        self.assertEqual(
            sorted(set(declared) - _shortcut_consumers()),
            [],
            "the template defines these keys but nothing applies them -- the "
            "loop in runtime_applier that puts them in the shortcut map is "
            "what makes the binding real",
        )

    def test_the_unbound_section_empties_out_as_keys_get_bound(self):
        rows = build_shortcut_rows(self.shortcuts)
        unbound = [row for row in rows if row[0] == UNBOUND_GROUP_TITLE]
        self.assertEqual(len(unbound), len(UNBOUND_ACTIONS))
        self.assertTrue(
            all(row[1] == NO_KEY_TEXT for row in unbound),
            "an unbound row must not claim a key",
        )
        # Bind one: its row moves into the group it belongs to.
        sample = UNBOUND_ACTIONS[0][0]
        bound = dict(self.shortcuts)
        bound[sample] = "Ctrl+Alt+Shift+F9"
        groups = {
            row[0]
            for row in build_shortcut_rows(bound)
            if row[2] == dict(UNBOUND_ACTIONS)[sample]
        }
        self.assertNotIn(UNBOUND_GROUP_TITLE, groups)

    def test_settings_descriptions_reference_real_shortcuts(self):
        described = _config_keys_in(DIALOG)
        self.assertTrue(
            described, "the shortcut description map was not found"
        )
        stale = sorted(described - set(self.shortcuts))
        self.assertEqual(
            stale,
            [],
            "the settings dialog describes shortcuts that no longer exist",
        )
