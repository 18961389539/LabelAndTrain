"""项目内搜索：按标注状态与标签名找图，结果可跳转。

匹配是**纯函数**：从盘上读、在内存里判，返回纯数据 —— 对话框只做
呈现与跳转，测试不用立任何控件。判定与文件列表/概览同源（复核状态
用同一个 head 读法），三处永远说同一个词。

搜索在对话框里走后台线程；一代结果一个代数号，迟到的旧代直接丢弃。
"""

from __future__ import annotations

import json
import os.path as osp

from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.schema import (
    REVIEW_CONFIRMED,
    REVIEW_REJECTED,
    REVIEW_UNCHECKED,
)

#: 展示层的状态词。搜索、文件列表、概览说同一套话。
STATE_UNLABELED = "未标注"
STATE_UNCHECKED = "未复检"
STATE_CONFIRMED = "已确认"
STATE_REWORK = "待复检"
SEARCH_STATES = (
    STATE_UNLABELED,
    STATE_UNCHECKED,
    STATE_CONFIRMED,
    STATE_REWORK,
)

_REVIEW_TO_STATE = {
    REVIEW_CONFIRMED: STATE_CONFIRMED,
    REVIEW_REJECTED: STATE_REWORK,
    REVIEW_UNCHECKED: STATE_UNCHECKED,
}


def _state_and_labels(label_file):
    """``(state, labels)`` from one label file, tolerant of damage.

    没有 label 文件、或 shapes 为空，都算 未标注 —— 和文件列表的
    行为一致。读不了的文件按 未标注/无标签 处理：搜索不能因为一个
    坏文件变成报错现场。
    """
    if not osp.isfile(label_file):
        return STATE_UNLABELED, []
    try:
        with open(label_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        labels = [
            str(shape.get("label") or "") for shape in data.get("shapes") or []
        ]
    except Exception as e:  # noqa: BLE001 - 坏文件是数据，不是异常
        logger.warning(
            f"Could not read the label file for search: {label_file} ({e})"
        )
        return STATE_UNLABELED, []
    if not labels:
        return STATE_UNLABELED, []
    from anylabeling.views.labeling.utils.async_label_check import (
        label_file_review_info,
    )

    try:
        review, _at, _note = label_file_review_info(label_file)
    except Exception:  # noqa: BLE001 - 坏头按未复核算
        review = REVIEW_UNCHECKED
    return _REVIEW_TO_STATE.get(review, STATE_UNCHECKED), labels


def search_project(
    root, output_dir=None, files=None, label_query="", state_query=""
):
    """Match images by review state and label name; pure disk read.

    ``files`` comes from the caller's file list when given (so the
    search answers for exactly what the session has), falling back to a
    recursive scan of the project folder. Returns a list of
    ``{"file", "state", "labels"}`` in the given order. An empty
    ``state_query`` (or 全部) matches every state; ``label_query`` is a
    case-insensitive substring match against the shapes' labels, and an
    image with no matching label is excluded even when its state fits.
    """
    if files is None:
        from anylabeling.views.labeling.utils.qt import scan_all_images

        files = (
            scan_all_images(str(root)) if root and osp.isdir(str(root)) else []
        )
    label_query = (label_query or "").strip().lower()
    state_query = (state_query or "").strip()
    matches = []
    for image_file in files:
        from anylabeling.views.labeling.project_dashboard import (
            label_path_for_image,
        )

        state, labels = _state_and_labels(
            label_path_for_image(image_file, output_dir)
        )
        if (
            state_query
            and state_query not in ("全部",)
            and state != state_query
        ):
            continue
        if label_query and not any(label_query in lb.lower() for lb in labels):
            continue
        matches.append({"file": image_file, "state": state, "labels": labels})
    return matches
