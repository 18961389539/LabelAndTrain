"""Shared pytest fixtures.

Every test runs with the config work directory pointed at a per-test temp
folder and the global ``current_config_file`` reset, so no test can ever
read or write the real ``~/.xanylabelingrc``. Tests that want a specific
work directory can still call ``config.set_work_directory`` on their own;
the fixture restores both globals afterwards.
"""

import pytest

from anylabeling import config


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Redirect all config I/O away from the user's home directory."""
    monkeypatch.setattr(config, "_work_directory", str(tmp_path))
    monkeypatch.setattr(config, "current_config_file", None)
    yield
