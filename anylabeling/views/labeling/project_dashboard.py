"""项目概览：把散在各处的数字聚成一份只读快照。

标注进度住在文件列表的行数据里（打开项目才看得到），训练轮次住在
实验历史对话框里（按 runs 目录翻）——"这个项目现在什么状态"这两个
问题从来没法在一个地方回答。本模块把两边都从**盘上**重新数一遍，
返回纯数据，不做任何展示：渲染是 ``ProjectPropertiesDialog`` 的事。

它不持有状态、不写盘，慢一点也无所谓（打开属性对话框才调用一次）；
任何一路读不了（runs 目录不存在、清单损坏）都按"没有"处理，概览
永远不能成为打不开项目属性的理由。
"""

from __future__ import annotations

import os.path as osp

#: 训练 runs 目录的默认位置（与 trainer 侧一致）。经训练包取值是
#: 刻意惰性的：标注侧不该为读一个数字背上 ultralytics 的导入。
_RUNS_SUBPATH = ("xanylabeling_data", "trainer", "ultralytics", "runs")


def default_runs_root():
    """The trainer's runs directory, or ``""`` when it cannot be known."""
    try:
        from anylabeling.services.auto_training.ultralytics.config import (
            get_default_project_dir,
        )

        return get_default_project_dir()
    except Exception:  # noqa: BLE001 - 概览不能因导入失败而崩
        return ""


def label_path_for_image(image_file, output_dir=None):
    """Where an image's label JSON lives; the widget's own rule.

    Mirrors ``LabelingWidget._label_path_for_image``: beside the image,
    or in the project's output directory when one is set. One copy here
    is cheaper than reaching into the widget from a dialog that must
    also work with no widget behind it.
    """
    label_file = osp.splitext(str(image_file))[0] + ".json"
    if output_dir:
        return osp.join(str(output_dir), osp.basename(label_file))
    return label_file


def collect_progress(root, output_dir=None):
    """Annotation progress counted from disk: ``{images, annotated,
    confirmed, rework}``.

    The review state is the same scan the file list uses (first bytes of
    the label JSON), so the overview and the list cannot disagree about
    what 已确认 means. A label file that cannot be read counts as
    unreviewed - the same judgement the list makes - and never as an
    error.
    """
    from anylabeling.views.labeling.schema import (
        REVIEW_CONFIRMED,
        REVIEW_REJECTED,
    )
    from anylabeling.views.labeling.utils.async_label_check import (
        label_file_review_info,
    )
    from anylabeling.views.labeling.utils.qt import scan_all_images

    images = (
        scan_all_images(str(root)) if root and osp.isdir(str(root)) else []
    )
    annotated = confirmed = rework = 0
    for image_file in images:
        label_file = label_path_for_image(image_file, output_dir)
        if not osp.isfile(label_file):
            continue
        annotated += 1
        try:
            state = label_file_review_info(label_file)[0]
        except Exception:  # noqa: BLE001 - 坏文件按未复核算
            continue
        if state == REVIEW_CONFIRMED:
            confirmed += 1
        elif state == REVIEW_REJECTED:
            rework += 1
    return {
        "images": len(images),
        "annotated": annotated,
        "confirmed": confirmed,
        "rework": rework,
    }


def collect_training(root, output_dir=None, runs_root=None):
    """Training history attributed to this project, or all-``None``.

    ``runs_root`` defaults to the trainer's own location; a missing or
    unreadable runs directory means "never trained", not an error.
    Returns ``{runs, best_map50, best_name, last_run, last_finished}``.
    """
    from anylabeling.views.training import run_history

    runs_root = runs_root or default_runs_root()
    rows = run_history.project_run_rows(
        str(root or ""), str(output_dir or ""), runs_root
    )
    if not rows:
        return {
            "runs": 0,
            "best_map50": None,
            "best_name": "",
            "last_run": "",
            "last_finished": "",
        }
    scored = [row for row in rows if row.get("map50") is not None]
    best = max(scored, key=lambda row: row["map50"]) if scored else None
    return {
        "runs": len(rows),
        "best_map50": best["map50"] if best else None,
        "best_name": str(best["name"]) if best else "",
        "last_run": str(rows[0].get("name") or ""),
        "last_finished": str(rows[0].get("finished_at") or ""),
    }


def collect(root, output_dir=None, runs_root=None):
    """Everything the overview shows, in one call."""
    progress = collect_progress(root, output_dir)
    training = collect_training(root, output_dir, runs_root)
    return {"progress": progress, "training": training}
