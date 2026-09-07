"""Classify auto-labeling models into task groups for the dropdown."""

from __future__ import annotations

TASK_TYPE_GROUPS = {
    "detect": {
        "yolov8",
        "yolo26",
        "yolov5",
        "yolov6",
        "yolov7",
        "yolov9",
        "yolov10",
        "yolov8_obb",
        "gold_yolo",
        "rfdetr",
        "grounding_dino",
        "deim",
        "dfine",
    },
    "segment": {
        "yolov8_seg",
        "yolo26_seg",
        "segment_anything_2",
        "yolov8_sam2",
        "sam",
        "sam2",
    },
    "pose": {
        "yolo26_pose",
        "yolov8_pose",
        "dwpose",
        "rtmo",
    },
}

TASK_GROUP_LABELS = {
    "all": "全部",
    "detect": "检测",
    "segment": "分割",
    "pose": "姿态",
    "other": "其他",
}

TASK_FILTER_ORDER = ("all", "detect", "segment", "pose", "other")


def group_for_model_type(model_type: str) -> str:
    token = (model_type or "").strip().lower()
    if not token:
        return "other"
    for group, types in TASK_TYPE_GROUPS.items():
        if token in types:
            return group
    matches = []
    for group, types in TASK_TYPE_GROUPS.items():
        for candidate in types:
            if token.startswith(candidate):
                matches.append((len(candidate), group))
    if matches:
        matches.sort(reverse=True)
        return matches[0][1]
    return "other"


def _recommend_score(name: str, display_name: str) -> int:
    blob = f"{name} {display_name}".lower()
    if "tiny" in blob or "nano" in blob:
        return 0
    if "_n" in blob or "-n" in blob or blob.endswith(" n"):
        return 1
    if "small" in blob or "_s" in blob or "-s" in blob:
        return 2
    return 3


def mark_recommended_models(model_data: dict) -> None:
    """Mark one lightweight model per task group as recommended."""
    by_group: dict[str, list] = {}
    for _provider, models in model_data.items():
        for name, data in models.items():
            if name == "load_custom_model":
                continue
            data["recommended"] = False
            group = group_for_model_type(data.get("type", ""))
            if group == "other":
                continue
            by_group.setdefault(group, []).append((name, data))

    for items in by_group.values():
        items.sort(
            key=lambda item: _recommend_score(
                item[0], item[1].get("display_name", "")
            )
        )
        items[0][1]["recommended"] = True


def classify_model_load_error(error_text: str) -> tuple[str, bool]:
    """Return (friendly_zh_message, offer_cpu_fallback)."""
    text = (error_text or "").lower()
    raw = error_text or ""
    cuda_tokens = (
        "cuda",
        "gpu",
        "cublas",
        "cudnn",
        "nvidia",
        "execution provider",
    )
    if any(token in text for token in cuda_tokens):
        return (
            "当前环境无法使用 GPU（缺少 CUDA / 驱动 / 显存不足）。"
            "可以改用 CPU 后重新加载，或换一个更小的模型。",
            True,
        )
    if any(
        token in text
        for token in (
            "could not download",
            "file not found",
            "no such file",
            "initialize",
            "not found",
        )
    ):
        return (
            "权重文件缺失或下载失败。请检查网络和磁盘空间后重试，或换一个模型。",
            False,
        )
    if "onnx" in text:
        return (
            "ONNX 运行失败。可改用 CPU 后重试，或检查模型文件是否完整。",
            True,
        )
    if "mismatch" in text or "shape" in text:
        return (
            "模型任务类型可能与当前标注不匹配。请换一个对应检测/分割任务的模型。",
            False,
        )
    return (f"模型加载失败：{raw}", False)
