"""The persistent label metadata cache: hit, miss and invalidation."""

import json
import os
import os.path as osp
import tempfile

from jllabeling.views.labeling.utils.label_index import LabelIndex


def _write(path, payload=None):
    if payload is None:
        payload = {"shapes": [], "review_state": "unchecked"}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)


def _stat(path):
    return os.stat(path)


def test_round_trip_reuses_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        label = osp.join(tmp, "a.json")
        _write(label)
        cache = osp.join(tmp, "index.json")

        index = LabelIndex(tmp, cache_path=cache)
        stat = _stat(label)
        index.update_review(
            label, stat, ("confirmed", "2026-01-01 00:00:00", None)
        )
        index.update_low_conf(label, stat, True, 2, ["bolt", "nut"])
        assert index.save() is True

        reloaded = LabelIndex(tmp, cache_path=cache)
        entry = reloaded.lookup(label, _stat(label))
        assert entry is not None
        assert entry.review == (
            "confirmed",
            "2026-01-01 00:00:00",
            None,
        )
        assert entry.low_conf is True
        assert entry.shape_count == 2
        assert entry.labels == ("bolt", "nut")


def test_changed_file_misses_the_cache():
    with tempfile.TemporaryDirectory() as tmp:
        label = osp.join(tmp, "a.json")
        _write(label)
        cache = osp.join(tmp, "index.json")

        index = LabelIndex(tmp, cache_path=cache)
        stat = _stat(label)
        index.update_review(label, stat, ("confirmed", None, None))
        index.update_low_conf(label, stat, True, 1, ["bolt"])
        index.save()

        with open(label, "a", encoding="utf-8") as handle:
            handle.write(" ")

        reloaded = LabelIndex(tmp, cache_path=cache)
        assert reloaded.lookup(label, _stat(label)) is None


def test_threshold_change_invalidates_only_low_conf():
    with tempfile.TemporaryDirectory() as tmp:
        label = osp.join(tmp, "a.json")
        _write(label)
        cache = osp.join(tmp, "index.json")

        index = LabelIndex(tmp, cache_path=cache)
        stat = _stat(label)
        index.update_review(label, stat, ("confirmed", None, None))
        index.update_low_conf(label, stat, True, 1, ["bolt"])
        index.save()

        calibrated = LabelIndex(
            tmp,
            thresholds={"defect": {"accept": 0.8, "review": 0.3}},
            cache_path=cache,
        )
        entry = calibrated.lookup(label, _stat(label))
        assert entry is not None
        assert entry.review[0] == "confirmed"
        assert entry.low_conf is None


def test_missing_label_is_removed():
    with tempfile.TemporaryDirectory() as tmp:
        label = osp.join(tmp, "a.json")
        _write(label)
        cache = osp.join(tmp, "index.json")

        index = LabelIndex(tmp, cache_path=cache)
        index.update_review(label, _stat(label), ("confirmed", None, None))
        index.save()

        os.remove(label)
        reloaded = LabelIndex(tmp, cache_path=cache)
        reloaded.remove(label)
        assert reloaded.save() is True

        assert LabelIndex(tmp, cache_path=cache).entries == {}


def test_corrupt_cache_is_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        label = osp.join(tmp, "a.json")
        _write(label)
        cache = osp.join(tmp, "index.json")
        with open(cache, "w", encoding="utf-8") as handle:
            handle.write("{not json")

        index = LabelIndex(tmp, cache_path=cache)
        assert index.lookup(label, _stat(label)) is None

        index.update_review(label, _stat(label), ("rejected", None, "fix"))
        assert index.save() is True
        reloaded = LabelIndex(tmp, cache_path=cache)
        assert reloaded.lookup(label, _stat(label)).review[0] == "rejected"
