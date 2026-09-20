"""Recent-folder history used by the "Open Recent Folder" menu.

Pure list handling (dedupe / trim / presence), kept free of Qt and QSettings
so it can be unit-tested; the widget layer just persists the resulting list.
"""

from __future__ import annotations

import os.path as osp

DEFAULT_MAX_ITEMS = 7


def _norm_key(path):
    """Normalized absolute path lowercased for case-insensitive comparison."""
    return osp.normpath(osp.abspath(path)).lower()


def push_recent_dir(dirs, directory, max_items=DEFAULT_MAX_ITEMS):
    """Return a new recent-dirs list with ``directory`` moved to the front.

    - Newest first.
    - Existing entries are de-duplicated (case-insensitive compare on the
      normalized absolute path).
    - Empty/non-existent paths are dropped.
    - The list is trimmed to ``max_items``.
    """
    if not directory:
        return list(dirs or [])
    normalized = osp.normpath(osp.abspath(directory))
    key = _norm_key(directory)
    items = [
        entry
        for entry in (dirs or [])
        if entry and _norm_key(entry) != key and osp.isdir(entry)
    ]
    items.insert(0, normalized)
    return items[:max_items]


def drop_recent_dir(dirs, directory):
    """Remove ``directory`` (if present) and return the updated list."""
    if not directory:
        return list(dirs or [])
    key = _norm_key(directory)
    return [
        entry
        for entry in (dirs or [])
        if entry and _norm_key(entry) != key
    ]
