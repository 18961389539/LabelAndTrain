"""Run-history CSV export is atomic and keeps the table's rows."""

import csv
import io
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from anylabeling.views.training import run_history_dialog as dialog_module
from anylabeling.views.training.run_history_dialog import write_history_csv


def test_rows_and_bom(tmp_path):
    path = tmp_path / "history.csv"
    path.write_text("old", encoding="utf-8")
    rows = [{"name": "exp", "status": "completed", "map50": 0.5}]

    write_history_csv(str(path), rows)

    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    data = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    assert data[0][1] == "运行"
    assert data[1][1] == "exp"
    assert data[1][2] == "completed"
    assert data[1][5] == "0.5000"
    assert [n for n in os.listdir(tmp_path) if n.endswith(".tmp")] == []


def test_a_failed_export_keeps_the_old_file(tmp_path, monkeypatch):
    path = tmp_path / "history.csv"
    path.write_text("old", encoding="utf-8")

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(dialog_module, "save_text", boom)

    with pytest.raises(OSError):
        write_history_csv(str(path), [{"name": "exp"}])

    assert path.read_text(encoding="utf-8") == "old"
