"""Which project is open right now - one answer, asked from anywhere.

Three modules used to carry a private copy of the same question: the
training dialog, the auto-labeling panel and the project UI each walked
``parent -> _project_dataset_dir -> guess from the image list`` by hand.
The copies agreed only by discipline; this module owns the question so
they agree by construction.

It is deliberately a *read-only snapshot*, never a state holder: the
project's real state lives in ``_project_dataset_dir`` (maintained by
``project_settings.begin_project_switch`` / ``project_view.close_project``)
and in ``project.json`` beside the data. A second writable copy is how
the two recent-project lists drifted apart once already.

Identity stays the folder path (see ``project_model``): the answer here
is a directory, not an id, and there is deliberately no id.
"""

from __future__ import annotations

import os.path as osp

_MISSING = object()


def parent_of(source):
    """The parent object of ``source``, whatever shape it arrives in.

    Real Qt widgets expose ``parent()`` as a method; the test stand-ins
    (and light fakes) expose ``parent`` as a plain attribute. Both are
    accepted here, which is what lets the module-level helpers keep
    taking stand-ins instead of demanding a whole widget. A parent that
    refuses to be called (deleted C++ object) reads as "no parent".
    """
    parent = getattr(source, "parent", None)
    if parent is None:
        return None
    if callable(parent):
        try:
            return parent()
        except (TypeError, RuntimeError):
            return None
    return parent


def _holders(source):
    """The objects that may carry ``_project_dataset_dir``, nearest first.

    A labeling widget holds it on itself; a dialog or a panel holds it
    on its parent (the widget). Both shapes end up here, so callers do
    not each re-derive the parent dance.
    """
    yield source
    holder = parent_of(source)
    if holder is not None:
        yield holder


def current_dataset_dir(source):
    """The open project's dataset folder, or ``None`` when nothing is.

    ``source`` may be the labeling widget, a dialog whose parent is that
    widget, or an embedded panel - the attribute is looked up on the
    object itself and then its parent, whichever carries it first. A
    directory that no longer exists reads as "nothing open": a vanished
    dataset must not be mistaken for the current project (same rule as
    ``project_view.current_root``).
    """
    for holder in _holders(source):
        opened = getattr(holder, "_project_dataset_dir", _MISSING)
        if opened is _MISSING or not opened:
            continue
        if osp.isdir(str(opened)):
            return str(opened)
    return None


def current_task(source):
    """The open project's task kind, or ``None`` when nothing is open.

    Reads the record live (``project_model`` owns the meaning) instead of
    caching it: the wizard, the switcher and the title bar must not each
    keep their own idea of the task - that is exactly what
    ``project_model.describe`` exists to prevent.
    """
    root = current_dataset_dir(source)
    if not root:
        return None
    from anylabeling.views.labeling import project_model

    return project_model.describe(root)["task"]


def current_name(source):
    """The open project's display name, or ``""`` when nothing is open."""
    root = current_dataset_dir(source)
    if not root:
        return ""
    from anylabeling.views.labeling import project_model

    return project_model.describe(root)["name"]
