"""Persistent per-label metadata cache for large dataset folders.

Opening a folder reads every label JSON twice: once for the review header and
once for the low-confidence scan.  The files themselves rarely change, so the
results are cached under the work directory and keyed by ``(mtime_ns, size)``.
A cache miss only means the file is read, exactly as before.

This is a cache, never a source of truth: deleting it, or a damaged copy,
falls back to reading every label.  Keys are absolute normalized label paths,
so an external output directory is cached too.
"""

import hashlib
import json
import os.path as osp
import time
from typing import NamedTuple, Optional, Tuple

from jllabeling.core.io import load_json, save_json
from jllabeling.views.labeling.logger import logger
from jllabeling.views.labeling.schema import REVIEW_UNCHECKED

#: Bump when the review or low-confidence meaning changes; old caches are
#: then ignored and rebuilt on the next folder open.
INDEX_SCHEMA = 2
DEFAULT_THRESHOLDS = "default"


class IndexEntry(NamedTuple):
    review: Tuple[str, Optional[str], Optional[str]]
    low_conf: Optional[bool]
    shape_count: Optional[int]
    labels: Optional[Tuple[str, ...]]


def _normalize_path(path):
    return osp.normcase(osp.abspath(str(path)))


def _thresholds_signature(thresholds):
    if not thresholds:
        return DEFAULT_THRESHOLDS
    raw = json.dumps(
        thresholds,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def default_cache_path(root):
    from jllabeling.config import get_work_directory

    digest = hashlib.sha1(_normalize_path(root).encode("utf-8")).hexdigest()
    return osp.join(
        get_work_directory(),
        "jllabeling_data",
        "cache",
        "label_index",
        digest + ".json",
    )


class LabelIndex:
    """Metadata for the labels under one dataset root."""

    def __init__(self, root, thresholds=None, cache_path=None):
        self.root = _normalize_path(root)
        self.signature = _thresholds_signature(thresholds)
        self.cache_path = cache_path or default_cache_path(self.root)
        self.entries = {}
        self.low_conf_valid = False
        self._dirty = False
        self._load()

    def _load(self):
        if not osp.isfile(self.cache_path):
            return
        try:
            data = load_json(self.cache_path)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        if data.get("schema") != INDEX_SCHEMA:
            return
        if data.get("root") != self.root:
            return
        entries = data.get("labels")
        if not isinstance(entries, dict):
            return
        self.entries = {
            str(key): value
            for key, value in entries.items()
            if isinstance(value, dict)
        }
        self.low_conf_valid = data.get("thresholds") == self.signature

    def lookup(self, label_file, stat):
        """Cached metadata for ``stat``, or ``None`` when it is stale."""
        entry = self.entries.get(_normalize_path(label_file))
        if entry is None:
            return None
        if (
            entry.get("mtime_ns") != stat.st_mtime_ns
            or entry.get("size") != stat.st_size
        ):
            return None
        review = (
            entry.get("review_state") or REVIEW_UNCHECKED,
            entry.get("reviewed_at"),
            entry.get("review_note"),
        )
        low_conf = entry.get("low_conf") if self.low_conf_valid else None
        raw_labels = entry.get("labels")
        labels = (
            tuple(str(label) for label in raw_labels)
            if isinstance(raw_labels, list)
            else None
        )
        return IndexEntry(
            review,
            low_conf,
            entry.get("shape_count"),
            labels,
        )

    def update_review(self, label_file, stat, review):
        key = _normalize_path(label_file)
        entry = self.entries.get(key)
        if (
            entry is None
            or entry.get("mtime_ns") != stat.st_mtime_ns
            or entry.get("size") != stat.st_size
        ):
            # A changed file invalidates the shape half too: the new
            # content may have different boxes.
            entry = {
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
            }
            self.entries[key] = entry
        entry["review_state"] = review[0]
        entry["reviewed_at"] = review[1]
        entry["review_note"] = review[2]
        self._dirty = True

    def update_low_conf(
        self, label_file, stat, low_conf, shape_count, labels=()
    ):
        key = _normalize_path(label_file)
        entry = self.entries.get(key)
        if (
            entry is None
            or entry.get("mtime_ns") != stat.st_mtime_ns
            or entry.get("size") != stat.st_size
        ):
            return
        entry["low_conf"] = bool(low_conf)
        entry["shape_count"] = shape_count
        entry["labels"] = [str(label) for label in (labels or ())]
        self._dirty = True

    def remove(self, label_file):
        key = _normalize_path(label_file)
        if self.entries.pop(key, None) is not None:
            self._dirty = True

    def save(self):
        if not self._dirty:
            return False
        payload = {
            "schema": INDEX_SCHEMA,
            "root": self.root,
            "thresholds": self.signature,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "labels": self.entries,
        }
        try:
            save_json(
                payload,
                self.cache_path,
                indent=None,
                ensure_ascii=False,
            )
        except OSError as error:
            logger.warning(
                "Could not write label index %s: %s",
                self.cache_path,
                error,
            )
            return False
        self._dirty = False
        return True
