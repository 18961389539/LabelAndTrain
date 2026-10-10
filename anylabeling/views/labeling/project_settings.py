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

from PyQt6 import QtCore, QtWidgets

from anylabeling.views.labeling import project as project_store
from anylabeling.views.labeling.project import label_dir_for_dataset

#: Keys this module owns inside ``project.json`` (beside ``split_seed``).
UI_KEYS = ("labels", "output_dir")

#: Datasets whose settings already failed to save this session. One
#: warning per dataset: a run of folder switches would otherwise stack
#: dialogs the annotator can do nothing about.
_WRITE_WARNED = set()


def _show_write_warning(widget, dataset_dir):
    """The one visible surface for a failed project-settings write.

    A module-level function so a test can replace it: what matters is
    that the failure is surfaced at all, not how it is rendered.
    """
    box = QtWidgets.QMessageBox(widget)
    box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    box.setWindowTitle(
        QtCore.QCoreApplication.translate("LabelingWidget", "项目设置无法保存")
    )
    box.setText(
        QtCore.QCoreApplication.translate(
            "LabelingWidget",
            "无法把项目设置写入下面的目录（只读盘或没有写入权限）：\n%s\n\n"
            "本次会话中这个项目的标签列表与标注输出目录不会被记住。",
        )
        % dataset_dir
    )
    box.exec()


def report_write_failure(widget, dataset_dir, action=""):
    """Tell the user once per dataset that its settings did not stick.

    Until this existed, a failed write was silent: on a read-only or
    network drive the annotator watched the label panel accept a new
    list and found it gone after a restart. Project settings are the
    promise a project makes, so the failure is surfaced — once per
    dataset per session, with the detail logged every time.
    """
    if not dataset_dir:
        return
    _logger().warning(
        "Could not save project settings "
        f"({action or 'write'}): {dataset_dir}"
    )
    key = osp.normcase(osp.normpath(str(dataset_dir)))
    if key in _WRITE_WARNED:
        return
    _WRITE_WARNED.add(key)
    try:
        _show_write_warning(widget, dataset_dir)
    except Exception as e:  # noqa: BLE001 - never break a save path
        _logger().warning(f"Could not show the write-failure warning: {e}")


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
    ok = update_values(dataset_dir, labels=names)
    if not ok:
        report_write_failure(widget, dataset_dir, "labels")
    return ok


def _previous_dataset_dir(widget):
    return getattr(widget, "_project_dataset_dir", None) or None


def _relative_to_project(dataset_dir, filename):
    """``filename`` as a project-relative path, or absolute if outside.

    Relative where possible: copying or moving a whole dataset folder is
    a normal thing to do, and a resume point that stops matching after
    the next ``mv`` is not worth writing down.
    """
    try:
        relative = osp.relpath(filename, dataset_dir)
    except ValueError:
        # Different drives on Windows: no relative form exists.
        return filename
    if relative.startswith(".."):
        return filename
    return relative


def remembered_file(dataset_dir):
    """The image this project was last looking at, or ``None``.

    Both stored forms are accepted: relative (the normal case) and
    absolute (the image sits outside the project, e.g. an output
    directory browsed on its own). A path that no longer exists reads as
    "nothing remembered" rather than an error — the folder is allowed to
    change under us.
    """
    stored = get_value(dataset_dir, "last_file")
    if not stored:
        return None
    stored = str(stored)
    if osp.isabs(stored):
        return stored if osp.isfile(stored) else None
    candidate = osp.join(str(dataset_dir), stored)
    return candidate if osp.isfile(candidate) else None


def save_last_file(widget, dataset_dir):
    """Record which image the project is on; skips the write if unchanged.

    Called from the leaving paths (switch away, close, quit) rather than
    on every image: one small write per visit to a project is affordable,
    one per image is not — and the record only matters when leaving.
    """
    filename = getattr(widget, "filename", None)
    if not filename or not dataset_dir:
        return False
    if not osp.isfile(str(filename)):
        return False
    stored = _relative_to_project(str(dataset_dir), str(filename))
    if get_value(dataset_dir, "last_file") == stored:
        return False
    return update_values(dataset_dir, last_file=stored)


def flush_open_project(widget):
    """Write back per-project state of the dataset currently open."""
    previous = _previous_dataset_dir(widget)
    if not previous:
        return
    save_current_labels(widget, previous)
    save_last_file(widget, previous)


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


def restore_configured_classes(widget):
    """Reset the label panel to the configured classes.

    Runs when the folder being opened ships no ``classes.txt``.  The panel
    would otherwise keep the *previous* folder's list, and
    ``_yolo_class_names`` reads it to build the YOLO id map — an unrelated
    list silently remaps every exported label.  Falling back to
    ``config.labels`` keeps the documented behaviour ("labels from the config
    keep working") without the leak.

    Returns True when the panel actually changed.
    """
    panel = getattr(widget, "unique_label_list", None)
    if panel is None:
        return False
    config = getattr(widget, "_config", None) or {}
    names = [str(name) for name in (config.get("labels") or [])]
    if _panel_label_names(widget) == names:
        return False
    panel.clear()
    if names:
        load_labels = getattr(widget, "load_labels", None)
        if callable(load_labels):
            load_labels(names, clear_existing=False)
        reset_dialog = getattr(widget, "_reset_label_dialog_labels", None)
        if callable(reset_dialog):
            reset_dialog(names)
    else:
        dialog = getattr(widget, "label_dialog", None)
        label_list = getattr(dialog, "label_list", None) if dialog else None
        if label_list is not None:
            label_list.clear()
    _logger().info("Reset the class panel to the configured labels")
    return True


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
    ``output_dir`` routes the label-file paths correctly, and so the
    remembered image can be opened by that scan's tail. Records the old
    dataset's label panel and position first, so leaving loses nothing.
    """
    if not dataset_dir:
        return
    flush_open_project(widget)
    widget._project_dataset_dir = dataset_dir
    # Read now, consumed later by ``_resume_remembered_file``: the scan
    # in between is what fills ``image_list``, and the target has to be
    # known before the "open the first image" fallback runs.
    widget._project_resume_file = remembered_file(dataset_dir)
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
    if not update_values(dataset_dir, output_dir=output_dir):
        report_write_failure(widget, dataset_dir, "output_dir")
