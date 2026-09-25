"""Experiment history: read what each training run recorded.

Every completed run writes ``run_meta.json`` next to its weights. This module
collects those into rows so successive rounds can be compared instead of
remembered, and aligns them with the iteration history stored beside the labels
(the loop records a round per model, but with a name only - joining the two is
what makes "round 3 vs round 4" answerable).
"""

import json
import os
import os.path as osp


def _read_meta(run_dir):
    path = osp.join(run_dir, "run_meta.json")
    if not osp.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _short(digest, width=8):
    if not digest:
        return ""
    return str(digest)[:width]


def collect_run_history(runs_root, task=None):
    """Rows for every run under ``runs_root``, newest finished first.

    Runs that predate ``run_meta.json`` are reported once through the
    ``unrecorded`` count rather than as empty rows, so the table never shows a
    silent blank where a number should be.
    """
    rows = []
    unrecorded = 0
    if not runs_root or not osp.isdir(runs_root):
        return {"rows": rows, "unrecorded": 0}

    task_dirs = _listdir(runs_root)
    if task:
        task_dirs = [name for name in task_dirs if name == task.lower()]
    for task_name in task_dirs:
        task_root = osp.join(runs_root, task_name)
        if not osp.isdir(task_root):
            continue
        for run_name in _listdir(task_root):
            run_dir = osp.join(task_root, run_name)
            if not osp.isdir(run_dir):
                continue
            meta = _read_meta(run_dir)
            if meta is None:
                weights = osp.join(run_dir, "weights", "best.pt")
                if osp.isfile(weights) or osp.isfile(
                    osp.join(run_dir, "results.csv")
                ):
                    unrecorded += 1
                continue
            metrics = meta.get("metrics") or {}
            dataset = meta.get("dataset") or {}
            counts = dataset.get("counts") or {}
            weights = meta.get("weights") or {}
            args = meta.get("train_args") or {}
            rows.append(
                {
                    "task": meta.get("task") or task_name,
                    "name": meta.get("name") or run_name,
                    "project": meta.get("project") or "",
                    "dir": run_dir,
                    "started_at": meta.get("started_at") or "",
                    "finished_at": meta.get("finished_at") or "",
                    "map50": _as_float(metrics.get("map50")),
                    "loss": _as_float(metrics.get("loss")),
                    "epochs": metrics.get("epochs") or args.get("epochs"),
                    "seed": dataset.get("seed"),
                    "train": counts.get("train"),
                    "val": counts.get("val"),
                    "classes": len(dataset.get("classes") or []) or None,
                    "manifest_sha1": _short(dataset.get("manifest_sha1")),
                    "weights_sha1": _short(weights.get("sha1")),
                    "model": args.get("model") or "",
                    "dataset": _dir_name(dataset.get("label_dir")),
                }
            )

    rows.sort(key=lambda row: row.get("finished_at") or "", reverse=True)
    return {"rows": rows, "unrecorded": unrecorded}


def _listdir(path):
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def _dir_name(path):
    """Basename of a recorded path, empty for None (old run_meta files)."""
    if not path:
        return ""
    return osp.basename(osp.normpath(str(path)))


def align_with_iterations(rows, history):
    """Attach the iteration round number to a run by its model name.

    The loop records ``model`` as the run directory name, so the join is exact
    for runs made by 用于自动标注 and simply absent for manual trainings.
    """
    rounds = (history or {}).get("rounds") or []
    by_model = {}
    for index, record in enumerate(rounds, start=1):
        model = record.get("model")
        if model and model not in by_model:
            by_model[model] = {
                "round": record.get("round", index),
                "labeled_images": record.get("labeled_images"),
                "total_shapes": record.get("total_shapes"),
                "new_shapes": record.get("new_shapes"),
            }
    for row in rows:
        match = by_model.get(row.get("name"))
        if match:
            row["iteration"] = match
    return rows


def summarize_history(rows):
    """Headline numbers for the history header."""
    recorded = [row for row in rows if row.get("map50") is not None]
    best = max(recorded, key=lambda row: row["map50"]) if recorded else None
    summary = {
        "runs": len(rows),
        "with_metrics": len(recorded),
        "best_map50": best["map50"] if best else None,
        "best_name": best["name"] if best else "",
        "trend": None,
    }
    if len(recorded) >= 2:
        newer, older = recorded[0], recorded[1]
        if newer.get("map50") is not None and older.get("map50") is not None:
            summary["trend"] = newer["map50"] - older["map50"]
            summary["trend_from"] = older["name"]
            summary["trend_to"] = newer["name"]
    return summary


def format_history_rows(rows):
    """Table rows as plain text, used by the CSV export and tests."""
    header = [
        "任务",
        "运行",
        "轮次",
        "完成时间",
        "mAP50",
        "loss",
        "epochs",
        "train",
        "val",
        "类别数",
        "种子",
        "manifest",
        "权重",
        "基座",
        "数据集",
    ]
    lines = [header]
    for row in rows:
        iteration = row.get("iteration") or {}
        lines.append(
            [
                str(row.get("task") or ""),
                str(row.get("name") or ""),
                str(iteration.get("round") or ""),
                str(row.get("finished_at") or ""),
                _fmt_float(row.get("map50")),
                _fmt_float(row.get("loss")),
                str(
                    row.get("epochs") if row.get("epochs") is not None else ""
                ),
                str(row.get("train") if row.get("train") is not None else ""),
                str(row.get("val") if row.get("val") is not None else ""),
                str(
                    row.get("classes")
                    if row.get("classes") is not None
                    else ""
                ),
                str(row.get("seed") if row.get("seed") is not None else ""),
                str(row.get("manifest_sha1") or ""),
                str(row.get("weights_sha1") or ""),
                str(row.get("model") or ""),
                str(row.get("dataset") or ""),
            ]
        )
    return lines


def _as_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_float(value, digits=4):
    if value is None:
        return ""
    return f"{value:.{digits}f}"
