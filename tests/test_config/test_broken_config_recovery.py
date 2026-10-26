"""A broken rc must not stop the app from opening.

The app passed the rc path to ``get_config`` with no guard: an empty or
hand-edited file aborted startup before the window existed. These tests
hold the recovery path down: defaults are used, the broken file is kept
for inspection, and the next save cannot truncate a good file.
"""

import os

import pytest
import yaml

from anylabeling import config


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_invalid_yaml_is_backed_up_and_defaults_are_used(tmp_path):
    rc = tmp_path / ".xanylabelingrc"
    _write(rc, "labels: [cat, dog\n")

    cfg = config.get_config(str(rc))

    warning = config.take_config_load_warning()
    assert warning is not None
    assert warning["path"] == str(rc)
    assert warning["backup"] and os.path.isfile(warning["backup"])
    with open(warning["backup"], encoding="utf-8") as f:
        assert f.read() == "labels: [cat, dog\n"
    assert not rc.exists()
    assert cfg["labels"] is None
    assert config.take_config_load_warning() is None


def test_empty_file_uses_defaults_without_renaming(tmp_path):
    rc = tmp_path / ".xanylabelingrc"
    _write(rc, "")

    cfg = config.get_config(str(rc))

    assert config.take_config_load_warning() is None
    assert rc.exists()
    assert cfg["labels"] is None


@pytest.mark.parametrize("text", ["- cat\n- dog\n", "just a scalar\n", "42\n"])
def test_non_mapping_config_is_preserved(tmp_path, text):
    rc = tmp_path / ".xanylabelingrc"
    _write(rc, text)

    config.get_config(str(rc))

    warning = config.take_config_load_warning()
    assert warning is not None
    with open(warning["backup"], encoding="utf-8") as f:
        assert f.read() == text


def test_a_custom_config_is_not_overwritten_by_rc_creation(
    tmp_path, monkeypatch
):
    custom = tmp_path / "custom.yaml"
    _write(custom, "labels:\n  - cat\n")
    monkeypatch.setattr(config, "current_config_file", str(custom))
    assert not (tmp_path / ".xanylabelingrc").exists()

    cfg = config.get_config(str(custom))

    assert cfg["labels"] == ["cat"]
    assert custom.read_text(encoding="utf-8") == "labels:\n  - cat\n"
    assert (tmp_path / ".xanylabelingrc").exists()


def test_current_config_file_is_cleared_after_recovery(tmp_path, monkeypatch):
    rc = tmp_path / "custom.yaml"
    _write(rc, "labels: [unclosed\n")
    monkeypatch.setattr(config, "current_config_file", str(rc))

    config.get_config(str(rc))

    assert config.current_config_file is None


def test_save_config_keeps_the_old_file_when_the_write_fails(
    tmp_path, monkeypatch
):
    rc = tmp_path / ".xanylabelingrc"
    _write(rc, "labels: [cat]\n")
    monkeypatch.setattr(config, "current_config_file", str(rc))

    def broken_dump(data, stream, **kwargs):
        stream.write("labels: [dog, ")
        raise OSError("disk full")

    monkeypatch.setattr(config.yaml, "safe_dump", broken_dump)
    assert config.save_config({"labels": ["dog"]}) is False
    assert rc.read_text(encoding="utf-8") == "labels: [cat]\n"
    assert not list(tmp_path.glob(".xanylabelingrc_*.tmp"))


def test_the_shipped_template_is_never_a_save_target(tmp_path, monkeypatch):
    from importlib import resources

    from anylabeling import configs as anylabeling_configs

    template = str(
        resources.files(anylabeling_configs) / "jllabeling_config.yaml"
    )
    with open(template, encoding="utf-8") as f:
        before = f.read()
    monkeypatch.setattr(config, "current_config_file", template)

    assert config.save_config({"labels": ["cat"]}) is True

    with open(template, encoding="utf-8") as f:
        assert f.read() == before
    with open(tmp_path / ".xanylabelingrc", encoding="utf-8") as f:
        assert yaml.safe_load(f)["labels"] == ["cat"]


def test_save_config_replaces_the_file_atomically(tmp_path, monkeypatch):
    rc = tmp_path / ".xanylabelingrc"
    monkeypatch.setattr(config, "current_config_file", str(rc))
    cfg = {"labels": ["cat", "dog"], "canvas": {"num_backups": 7}}

    assert config.save_config(cfg) is True

    with open(rc, encoding="utf-8") as f:
        assert yaml.safe_load(f) == cfg
    assert not list(tmp_path.glob(".xanylabelingrc_*.tmp"))
