"""Per-project settings: lazy creation, stability and damage tolerance."""

import json
import os

import pytest

from anylabeling.views.labeling import project

PROJECT_FILE = os.path.join(project.PROJECT_DIR_NAME, project.PROJECT_FILE_NAME)


def test_reading_creates_nothing(tmp_path):
    assert project.load_project(str(tmp_path)) == {}
    assert not os.path.exists(os.path.join(str(tmp_path), project.PROJECT_DIR_NAME))


def test_split_seed_is_pinned_after_first_use(tmp_path):
    seed, created = project.get_or_create_split_seed(str(tmp_path))
    assert created is True
    assert seed > 0
    assert os.path.isfile(os.path.join(str(tmp_path), PROJECT_FILE))

    again, created_again = project.get_or_create_split_seed(str(tmp_path))
    assert created_again is False
    assert again == seed


def test_save_preserves_unrelated_keys(tmp_path):
    project.save_project(str(tmp_path), {"split_seed": 42, "note": "keep"})
    data = json.loads(
        open(os.path.join(str(tmp_path), PROJECT_FILE), encoding="utf-8").read()
    )
    assert data["note"] == "keep"
    assert data["schema"] == project.SCHEMA


def test_damaged_project_file_falls_back_and_is_repairable(tmp_path):
    project.save_project(str(tmp_path), {"split_seed": 7})
    path = os.path.join(str(tmp_path), PROJECT_FILE)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{ this is not json")

    assert project.load_project(str(tmp_path)) == {}

    seed, created = project.get_or_create_split_seed(str(tmp_path))
    assert created is True
    assert project.load_project(str(tmp_path))["split_seed"] == seed


@pytest.mark.parametrize("payload", ["[]", '"text"', "null", "3"])
def test_non_object_project_json_is_ignored(tmp_path, payload):
    os.makedirs(os.path.join(str(tmp_path), project.PROJECT_DIR_NAME))
    with open(
        os.path.join(str(tmp_path), PROJECT_FILE), "w", encoding="utf-8"
    ) as handle:
        handle.write(payload)
    assert project.load_project(str(tmp_path)) == {}


def test_label_dir_precedence():
    assert (
        project.label_dir_for_dataset("/out", ["/imgs/a.jpg"], "/other/x.jpg")
        == "/out"
    )
    assert (
        project.label_dir_for_dataset(None, ["/imgs/a.jpg"], "/other/x.jpg")
        == "/imgs"
    )
    assert project.label_dir_for_dataset(None, [], "/other/x.jpg") == "/other"
    assert project.label_dir_for_dataset() is None


def test_unwritable_location_reports_failure(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.write_text("i am a file, not a directory", encoding="utf-8")
    assert project.save_project(str(blocked), {"a": 1}) is False
    # A seed is still returned so the run stays reproducible; it is simply
    # not pinned, which the caller sees as created=False.
    seed, created = project.get_or_create_split_seed(str(blocked))
    assert seed > 0
    assert created is False


def test_split_seed_survives_a_save_failure(tmp_path, monkeypatch):
    from anylabeling.views.labeling import project as project_module

    def _fail(_data, _path):
        raise OSError("read-only media")

    monkeypatch.setattr(project_module, "save_json", _fail)
    seed, created = project.get_or_create_split_seed(str(tmp_path))
    # The run still gets a usable seed; it is simply not pinned yet.
    assert seed > 0
    assert created is False
    assert not os.path.exists(
        os.path.join(str(tmp_path), project.PROJECT_DIR_NAME)
    )


class _FakeDialog:
    def __init__(self, output_dir, image_list):
        self.output_dir = output_dir
        self.image_list = image_list

    def bind(self):
        from anylabeling.views.training.ultralytics_dialog import (
            UltralyticsDialog,
        )

        self._project_split_seed = (
            UltralyticsDialog._project_split_seed.__get__(self)
        )
        return self


def test_training_dialog_pins_the_seed_for_the_open_dataset(tmp_path):
    dialog = _FakeDialog(str(tmp_path), []).bind()
    seed, source = dialog._project_split_seed()
    assert source == "project"
    assert isinstance(seed, int) and seed > 0
    assert os.path.isfile(os.path.join(str(tmp_path), PROJECT_FILE))

    again, again_source = dialog._project_split_seed()
    assert again == seed
    assert again_source == "pinned"


def test_training_dataset_without_a_label_dir_falls_back(tmp_path):
    dialog = _FakeDialog(None, []).bind()
    assert dialog._project_split_seed() == (None, "generated")
