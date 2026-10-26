"""Output-directory imports must not map two images onto one label file."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from anylabeling.views.labeling.utils import file_lifecycle


def _image(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return str(path)


def test_nested_same_stem_is_detected(tmp_path):
    files = [
        _image(tmp_path / "a" / "photo.png"),
        _image(tmp_path / "b" / "photo.png"),
    ]

    assert file_lifecycle.duplicate_output_stems(files) == ["photo"]


def test_same_stem_with_different_extensions_is_detected(tmp_path):
    files = [
        _image(tmp_path / "photo.png"),
        _image(tmp_path / "photo.jpg"),
    ]

    assert file_lifecycle.duplicate_output_stems(files) == ["photo"]


def test_unique_stems_are_left_alone(tmp_path):
    files = [
        _image(tmp_path / "a" / "one.png"),
        _image(tmp_path / "b" / "two.png"),
    ]

    assert file_lifecycle.duplicate_output_stems(files) == []


def test_import_refuses_and_leaves_the_current_project_alone(tmp_path):
    _image(tmp_path / "a" / "photo.png")
    _image(tmp_path / "b" / "photo.png")
    calls = {}

    class _Widget:
        output_dir = str(tmp_path / "labels")

        def __init__(self):
            self.filename = "current.png"

        def may_continue(self):
            return True

        def error_message(self, title, message):
            calls["title"] = title
            calls["message"] = message

    widget = _Widget()

    file_lifecycle.import_image_folder(widget, str(tmp_path))

    assert "无法导入" in calls["title"]
    assert "photo" in calls["message"]
    assert widget.filename == "current.png"
