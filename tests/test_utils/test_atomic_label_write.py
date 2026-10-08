"""The YOLO/pose writers must not leave half a label file behind.

``custom_to_yolo`` builds its output line by line: a shape it could not handle
raised part way through and left a truncated ``.txt``, which ultralytics reads
as "this image has fewer objects" — a silently wrong sample rather than a
visible error.  ``label_file.save`` already wrote through a temp file; this
pins the same contract for the converter.
"""

import inspect

import pytest

from anylabeling.views.labeling.label_converter import (
    LabelConverter,
    _atomic_text_writer,
)


class TestAtomicTextWriter:
    def test_the_target_appears_only_after_a_clean_exit(self, tmp_path):
        target = tmp_path / "a.txt"

        with _atomic_text_writer(str(target)) as handle:
            handle.write("complete\n")
            assert not target.exists()

        assert target.read_text(encoding="utf-8") == "complete\n"

    def test_a_failure_inside_the_body_leaves_nothing_behind(self, tmp_path):
        target = tmp_path / "a.txt"

        with pytest.raises(RuntimeError):
            with _atomic_text_writer(str(target)) as handle:
                handle.write("partial")
                raise RuntimeError("boom")

        assert not target.exists()
        # Not even the temp file: nothing half-written should survive.
        assert list(tmp_path.iterdir()) == []

    def test_an_existing_file_is_left_alone_when_the_body_fails(
        self, tmp_path
    ):
        target = tmp_path / "a.txt"
        target.write_text("old\n", encoding="utf-8")

        with pytest.raises(RuntimeError):
            with _atomic_text_writer(str(target)) as handle:
                handle.write("new")
                raise RuntimeError("boom")

        assert target.read_text(encoding="utf-8") == "old\n"


class TestCustomToYoloUsesIt:
    def test_the_writer_goes_through_the_helper(self):
        source = inspect.getsource(LabelConverter.custom_to_yolo)

        assert 'open(output_file, "w"' not in source
        assert "_atomic_text_writer(output_file)" in source
