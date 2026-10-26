"""Image-flag import keeps the list and does not reload it away."""

import os
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from anylabeling.views.labeling.utils import upload as upload_module
from anylabeling.views.labeling.utils.upload import upload_image_flags_file


def _run(tmp_path, content, monkeypatch):
    path = tmp_path / "flags.txt"
    path.write_text(content, encoding="utf-8")
    calls = {}
    widget = SimpleNamespace(
        image_flags=[],
        _config={"flags": None},
        flag_dock=SimpleNamespace(show=lambda: calls.setdefault("dock", True)),
        load_flags=lambda flags: calls.setdefault("loaded", flags),
        set_dirty=lambda: calls.setdefault("dirty", True),
        load_file=lambda name: calls.setdefault("reloaded", name),
    )
    monkeypatch.setattr(
        upload_module.QtWidgets.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(path), ""),
    )
    monkeypatch.setattr(
        upload_module,
        "save_config",
        lambda cfg: calls.setdefault("saved", list(cfg["flags"])) or True,
    )
    monkeypatch.setattr(upload_module, "Popup", mock.MagicMock())

    upload_image_flags_file(widget)
    return widget, calls


def test_import_keeps_and_persists_flags(tmp_path, monkeypatch):
    widget, calls = _run(
        tmp_path, "occluded\n\n lost \noccluded\n", monkeypatch
    )

    assert widget.image_flags == ["occluded", "lost"]
    assert calls["loaded"] == {"occluded": False, "lost": False}
    assert calls["saved"] == ["occluded", "lost"]
    assert widget._config["flags"] == ["occluded", "lost"]
    assert calls.get("dirty") is True
    # Loading the file again would read the old flags back from disk.
    assert "reloaded" not in calls
    assert calls.get("dock") is True


def test_empty_file_is_rejected(tmp_path, monkeypatch):
    widget, calls = _run(tmp_path, "\n  \n", monkeypatch)

    assert widget.image_flags == []
    assert "loaded" not in calls
    assert "saved" not in calls
    assert "dirty" not in calls
