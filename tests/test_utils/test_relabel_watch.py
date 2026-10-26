"""A delayed relabel update must not write into the previous project."""

import os
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from anylabeling.views.labeling.utils import smart_review


def _parent(directory):
    return SimpleNamespace(output_dir=directory, filename=None)


def test_a_switched_project_is_not_written(tmp_path):
    old = tmp_path / "old"
    old.mkdir()
    new = tmp_path / "new"
    new.mkdir()

    with (
        mock.patch.object(smart_review, "count_annotations") as count,
        mock.patch.object(smart_review, "update_last_iteration") as write,
    ):
        result = smart_review._record_relabel_result(
            _parent(str(new)), str(old), {}
        )

    assert result is None
    count.assert_not_called()
    write.assert_not_called()


def test_a_deleted_project_is_not_written(tmp_path):
    missing = tmp_path / "gone"

    with (
        mock.patch.object(smart_review, "count_annotations") as count,
        mock.patch.object(smart_review, "update_last_iteration") as write,
    ):
        result = smart_review._record_relabel_result(
            _parent(str(missing)), str(missing), {}
        )

    assert result is None
    count.assert_not_called()
    write.assert_not_called()


def test_the_same_project_records_the_gain(tmp_path):
    calls = {}

    def fake_update(directory, **fields):
        calls["args"] = (directory, fields)
        return {"ok": True}

    with (
        mock.patch.object(
            smart_review,
            "count_annotations",
            return_value={"total_shapes": 5, "labeled_images": 2},
        ),
        mock.patch.object(
            smart_review, "update_last_iteration", side_effect=fake_update
        ),
    ):
        result = smart_review._record_relabel_result(
            _parent(str(tmp_path)), str(tmp_path), {"total_shapes": 2}
        )

    assert result == {"ok": True}
    assert calls["args"][0] == str(tmp_path)
    assert calls["args"][1]["new_shapes"] == 3
    assert calls["args"][1]["labeled_images"] == 2
