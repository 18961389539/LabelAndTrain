"""Per-project settings for the opened dataset, anchored at the image folder.

``project.py`` keeps the generic storage (lazy ``.jllabel/project.json`` next
to the data); this module owns the policy for which settings follow a dataset
between sessions:

* ``labels`` - the label-panel suggestion list, so folder B no longer inherits
  folder A's classes when neither ships a ``classes.txt``;
* ``output_dir`` - the annotation output directory override, so reopening a
  dataset restores where its label JSONs go.

Anchor: the image folder, i.e. the folder the user opens. That is the
project's identity and it always exists; ``output_dir`` can be repointed or
moved, so settings derived from it must not live there. The one exception is
``split_seed``, which stays anchored at the label dir (``project.py``) because
training reads it from where the label JSONs live - that contract predates
this module and its tests pin it.

Everything here is best-effort: a damaged or unwritable project file must
never block annotating, and every widget access is ``getattr``-guarded so
light test stubs survive.
"""

import os.path as osp

from anylabeling.views.labeling import project as project_store
from anylabeling.views.labeling.project import label_dir_for_dataset

#: Keys this module owns inside ``project.json`` (beside ``split_seed``).
UI_KEYS = ("labels", "output_dir")


def dataset_dir_for(output_dir=None, image_list=None, filename=None):
    """The image folder that identifies the open project.

    Deliberately ignores ``output_dir`` (unlike
    :func:`project.label_dir_for_dataset`): the dataset folder is the
    identity, the output dir is one of its settings.
    """
    if image_list:
        return osp.dirname(image_list[0])
    if filename:
        return osp.dirname(filename)
    return None


def load_settings(dataset_dir):
    """Full project record, or ``{}`` (same tolerance as the storage)."""
    if not dataset_dir:
        return {}
    return project_store.load_project(dataset_dir)


def get_value(dataset_dir, key, default=None):
    data = load_settings(dataset_dir)
    value = data.get(key, default)
    return value if value is not None else default


def update_values(dataset_dir, **changes):
    """Merge ``changes`` into the project file; a ``None`` value removes.

    Returns True when the file was written. Creating the file for a dataset
    the user merely browsed is avoided by callers (they only call this when
    there is something to record).
    """
    if not dataset_dir:
        return False
    data = load_settings(dataset_dir)
    dirty = False
    for key, value in changes.items():
        if value is None:
            if key in data:
                data.pop(key, None)
                dirty = True
        elif data.get(key) != value:
            data[key] = value
            dirty = True
    if not dirty:
        return True
    return project_store.save_project(dataset_dir, data)


def reset_ui_settings(dataset_dir):
    """Drop this module's keys, keep ``split_seed`` (split comparability)."""
    if not dataset_dir:
        return False
    return update_values(dataset_dir, **{key: None for key in UI_KEYS})


def _panel_label_names(widget):
    names = getattr(widget, "_panel_label_names", None)
    if not callable(names):
        return []
    try:
        return list(names())
    except Exception:  # noqa: BLE001 - stubs may fake the panel
        return []


def save_current_labels(widget, dataset_dir):
    """Persist the label panel's current names for ``dataset_dir``."""
    if not dataset_dir:
        return False
    names = _panel_label_names(widget)
    if not names:
        return False
    return update_values(dataset_dir, labels=names)


def _previous_dataset_dir(widget):
    return getattr(widget, "_project_dataset_dir", None) or None


def flush_open_project(widget):
    """Write back per-project state of the dataset currently open."""
    previous = _previous_dataset_dir(widget)
    if previous:
        save_current_labels(widget, previous)


def _restore_output_dir(widget, dataset_dir):
    """Re-apply the recorded output dir unless one was set explicitly.

    An explicit ``output_dir`` (CLI argument, or just picked in the change
    dialog) always wins; a recorded dir that no longer exists is ignored and
    left in the file - the user may plug the drive back in.
    """
    if getattr(widget, "output_dir", None):
        return
    stored = get_value(dataset_dir, "output_dir")
    if not stored or not osp.isdir(stored):
        return
    try:
        widget.output_dir = stored
    except Exception:  # noqa: BLE001 - read-only stub
        pass


def _restore_labels(widget, dataset_dir):
    """Seed the label panel from the project record as a fallback.

    Runs after ``_load_classes_from_folder``, so a ``classes.txt`` shipped
    with the folder still wins; the record only fills the gap for folders
    whose classes were built interactively.
    """
    names = get_value(dataset_dir, "labels") or []
    if not names:
        return
    panel_is_empty = not _panel_label_names(widget)
    if not panel_is_empty:
        return
    load_labels = getattr(widget, "load_labels", None)
    if not callable(load_labels):
        return
    try:
        load_labels(names, clear_existing=False)
        reset_dialog = getattr(widget, "_reset_label_dialog_labels", None)
        if callable(reset_dialog):
            reset_dialog(names)
        _logger().info(
            f"Restored {len(names)} labels from project settings: "
            f"{', '.join(names)}"
        )
    except Exception:  # noqa: BLE001 - stubs may fake the panel
        pass


def _logger():
    from anylabeling.views.labeling.logger import logger

    return logger


def begin_project_switch(widget, dataset_dir):
    """First half of a dataset switch: flush the old, restore the early.

    Must run before the image scan of ``import_image_folder`` so a restored
    ``output_dir`` routes the label-file paths correctly. Records the old
    dataset's label panel first, so edits made without saving are not lost.
    """
    if not dataset_dir:
        return
    flush_open_project(widget)
    widget._project_dataset_dir = dataset_dir
    _restore_output_dir(widget, dataset_dir)


def end_project_switch(widget, dataset_dir):
    """Second half: label-panel fallback plus registry bookkeeping."""
    if not dataset_dir:
        return
    _restore_labels(widget, dataset_dir)
    try:
        from anylabeling.views.labeling.project_registry import (
            record_project,
        )

        record_project(
            dataset_dir,
            label_dir=label_dir_for_dataset(
                getattr(widget, "output_dir", None),
                getattr(widget, "image_list", None),
            ),
        )
    except Exception as e:  # noqa: BLE001 - registry is never critical
        _logger().warning(f"Failed to record project: {e}")


def record_output_dir_change(widget, output_dir):
    """Persist an output-dir change made through the change dialog."""
    if not output_dir:
        return
    dataset_dir = dataset_dir_for(
        filename=getattr(widget, "filename", None)
    ) or _previous_dataset_dir(widget)
    if not dataset_dir:
        return
    update_values(dataset_dir, output_dir=output_dir)
