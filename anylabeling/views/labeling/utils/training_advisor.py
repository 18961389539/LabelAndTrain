"""Training intelligence (L4): pre-flight checks and hyperparameter advice.

Given dataset statistics (as produced by ``data_intel.analyze_distribution``)
and an optional iteration-history summary, produce human-readable warnings and
concrete training-config suggestions. Pure logic, no Qt/UI dependencies.
"""

from __future__ import annotations

MIN_SAMPLES_PER_CLASS = 100
UNLABELED_WARN_RATIO = 0.5
IMBALANCE_WARN_RATIO = 10.0
MUCH_DATA_THRESHOLD = 5000
LOW_DATA_THRESHOLD = 50


def preflight_checks(stats):
    """Diagnose a dataset before training.

    Args:
        stats: Dict with keys ``total_images``, ``labeled_images``,
            ``missing_json`` and ``class_counts`` (label -> object count),
            matching ``analyze_distribution`` output.

        Returns:
            List of ``{"level": "err"|"warn"|"ok", "code": str, "message":
            str}``. ``code`` is the stable machine-readable handle; ``message``
            is display text and must not be parsed by callers.
    """
    checks = []
    if not isinstance(stats, dict) or not stats:
        return [
            {
                "level": "err",
                "code": "no_data",
                "message": "没有可分析的数据。",
            }
        ]
    total = int(stats.get("total_images") or 0)
    if total == 0:
        return [
            {
                "level": "err",
                "code": "empty_dataset",
                "message": "数据集为空：请先打开并标注一个图片文件夹。",
            }
        ]

    missing = int(stats.get("missing_json") or 0)
    labeled = int(stats.get("labeled_images") or 0)
    if missing and missing >= total * UNLABELED_WARN_RATIO:
        checks.append(
            {
                "level": "warn",
                "code": "unlabeled_majority",
                "message": f"超过一半图片未标注（{missing}/{total}），训练前建议先补齐标注。",
            }
        )
    elif missing:
        checks.append(
            {
                "level": "ok",
                "code": "unlabeled_minor",
                "message": f"未标注图片 {missing} 张（{missing * 100.0 // max(total, 1)}%），可用自动标注/复核流程补齐。",
            }
        )

    class_counts = stats.get("class_counts") or {}
    if isinstance(class_counts, dict) and class_counts:
        majority = max(class_counts.values())
        for label, count in sorted(
            class_counts.items(), key=lambda item: (item[1], item[0])
        ):
            if count < MIN_SAMPLES_PER_CLASS:
                checks.append(
                    {
                        "level": "warn",
                        "code": "few_samples",
                        "label": label,
                        "count": count,
                        "message": (
                            f"类别「{label}」只有 {count} 个目标"
                            f"（少于建议的 {MIN_SAMPLES_PER_CLASS}），请重点补充。"
                        ),
                    }
                )
            if majority and majority >= max(count, 1) * IMBALANCE_WARN_RATIO:
                detail = (
                    f"{label}（{count}）远少于最多类（{majority}），"
                    "训练时建议启用类别权重或在数据集中补样本。"
                )
                checks.append(
                    {
                        "level": "warn",
                        "code": "imbalance",
                        "label": label,
                        "count": count,
                        "detail": detail,
                        "message": f"类别不平衡：{detail}",
                    }
                )
    elif labeled == 0:
        checks.append(
            {
                "level": "err",
                "code": "no_targets",
                "message": "没有任何已标注目标，无法开始训练。",
            }
        )

    if not checks:
        checks.append(
            {"level": "ok", "code": "healthy", "message": "预检通过，数据分布健康。"}
        )
    return checks


def _round_down_multiple(value, base=32):
    return max(base, int(value // base) * base)


def history_summary(history):
    """Summarize the active-learning history for the advisor.

    ``history`` is what :func:`active_learning.load_history` returns, i.e.
    ``{"rounds": [ ... ]}``. Each round may carry an ``map50`` field. This
    avoids touching ``read_last_map50`` (which parses a results.csv file).

    Returns ``{"iterations": int, "last_map50": float|None}`` or ``None``
    when there are no usable rounds.
    """
    if not isinstance(history, dict):
        return None
    rounds = history.get("rounds")
    if not isinstance(rounds, list) or not rounds:
        return None
    last = rounds[-1]
    map50 = None
    if isinstance(last, dict):
        map50 = last.get("map50")
        if map50 is None:
            for key, value in last.items():
                if "map50" in str(key).lower() and "map50-95" not in str(key).lower():
                    map50 = value
                    break
    try:
        map50 = float(map50) if map50 is not None else None
    except (TypeError, ValueError):
        map50 = None
    return {"iterations": len(rounds), "last_map50": map50}


def recommend_training_config(stats, history=None, max_image_dim=None):
    """Suggest epochs/batch/imgsz plus a Chinese advice paragraph.

    Args:
        stats: Same shape as for :func:`preflight_checks`.
        history: Optional dict with ``{"iterations": int, "last_map50":
            float|None}`` summarizing previous training rounds.
        max_image_dim: Largest side (px) of the training images; when None,
            a 640-based default is assumed.

    Returns:
        Dict with ``epochs``/``batch``/``imgsz`` keys and a ``text`` message.
    """
    checks = preflight_checks(stats)
    errs = [c for c in checks if c["level"] == "err"]
    if errs:
        return {"epochs": 100, "batch": 16, "imgsz": 640, "text": errs[0]["message"]}

    class_counts = stats.get("class_counts") or {}
    labeled = int(stats.get("labeled_images") or 0)

    if 0 < labeled < LOW_DATA_THRESHOLD:
        batch, epochs = 8, 150
    elif labeled >= MUCH_DATA_THRESHOLD:
        batch, epochs = 32, 60
    else:
        batch, epochs = 16, 100

    max_dim = int(max_image_dim or 0)
    if max_dim <= 0:
        imgsz = 640
    elif max_dim <= 5120:
        imgsz = min(1280, max(640, _round_down_multiple(max_dim, 32)))
    else:
        imgsz = 1280

    suggestions = [f"Epochs={epochs}", f"Batch={batch}", f"imgsz={imgsz}"]
    class_counts = stats.get("class_counts") or {}
    if not isinstance(class_counts, dict) or not class_counts:
        return {
            "epochs": epochs,
            "batch": batch,
            "imgsz": imgsz,
            "text": "还没有统计到已标注目标，先完成标注再运行训练建议。",
            "checks": checks,
        }
    lines = []
    lines.append("推荐初值：" + " · ".join(suggestions) + "。")
    if labeled < LOW_DATA_THRESHOLD:
        lines.append("数据量小，适当延长训练并开启数据增强（mosaic/随机裁剪）防过拟合。")
    elif labeled >= MUCH_DATA_THRESHOLD:
        lines.append("数据量充足，可减少轮数并用更大 imgsz 提速收敛。")

    imbalance_warns = [c for c in checks if c["code"] == "imbalance"]
    few_warns = [c for c in checks if c["code"] == "few_samples"]
    if imbalance_warns:
        lines.append("检测到类别不平衡：" + imbalance_warns[0]["detail"])
    elif few_warns:
        lines.append("存在小类样本不足，建议先做主动学习补充硬样例。" + few_warns[0]["message"])

    if any(c["code"] == "unlabeled_majority" for c in checks):
        missing = stats.get("missing_json") or 0
        total = stats.get("total_images") or 0
        lines.append(f"另有 {missing}/{total} 张未标注，训练指标可能偏低。")

    iterations = None
    if isinstance(history, dict):
        iterations = history.get("iterations")
        last_map50 = history.get("last_map50")
        if last_map50 is not None and last_map50 < 0.3:
            lines.append("上一轮 mAP50 偏低，建议先检查标注质量并回看「迭代收益看板」。")
        elif iterations:
            lines.append(f"已是第 {int(iterations)} 轮迭代，建议同步查看「迭代收益看板」判断是否停止。")

    return {
        "epochs": epochs,
        "batch": batch,
        "imgsz": imgsz,
        "text": "\n".join(lines),
        "checks": checks,
    }
