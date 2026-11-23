"""Shared pytest fixtures.

Every test runs with the config work directory pointed at a per-test temp
folder and the global ``current_config_file`` reset, so no test can ever
read or write the real ``~/.jllabelingrc``. Tests that want a specific
work directory can still call ``config.set_work_directory`` on their own;
the fixture restores both globals afterwards.
"""

import os

import pytest

from jllabeling import config

# pytest-qt picks PySide6 first when both bindings are installed (the local
# translation toolchain brings in PySide6-Essentials).  Loading PySide6 and
# PyQt6 in one process breaks Qt6Network.dll on Windows.  The app itself ships
# with PyQt6, so pin pytest-qt to the same binding.  pytest-qt reads this in
# its pytest_configure hook, which runs after conftest import.
os.environ.setdefault("PYTEST_QT_API", "pyqt6")


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Redirect all config I/O away from the user's home directory."""
    monkeypatch.setattr(config, "_work_directory", str(tmp_path))
    monkeypatch.setattr(config, "current_config_file", None)
    monkeypatch.setattr(config, "_config_load_warning", None)
    yield
