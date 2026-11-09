import copy
import os
import multiprocessing

from jllabeling.config import get_data_dir_name, get_work_directory


def get_trainer_root_dir():
    return os.path.join(
        get_work_directory(), get_data_dir_name(), "trainer", "ultralytics"
    )


def get_data_path():
    return os.path.join(get_trainer_root_dir(), "data.yaml")


def get_dataset_path():
    return os.path.join(get_trainer_root_dir(), "datasets")


def get_settings_config_path():
    return os.path.join(get_trainer_root_dir(), "settings.json")


def get_default_project_dir():
    return os.path.join(get_trainer_root_dir(), "runs")


# UI configuration
DEFAULT_WINDOW_TITLE = "JLTrain Training Platforms 🚀"
DEFAULT_WINDOW_SIZE = (1200, 800)  # (w, h)
ICON_SIZE_NORMAL = (32, 32)
ICON_SIZE_SMALL = (16, 16)

# Task configuration
TASK_TYPES = ["Classify", "Detect", "Segment", "Pose"]
TASK_SHAPE_MAPPINGS = {
    "Classify": ["flags"],
    "Detect": ["rectangle"],
    "Segment": ["polygon"],
    "Pose": ["point"],
}
TASK_LABEL_MAPPINGS = {
    "Classify": "classify",
    "Detect": "hbb",
    "Segment": "seg",
    "Pose": "pose",
}

# Training configuration
#: Small-sample industrial trial runs are legitimate; 4 is the practical
#: floor for a train/val split instead of the old 20-image hard gate.
MIN_LABELED_IMAGES_THRESHOLD = 4
NUM_WORKERS = multiprocessing.cpu_count()
DEFAULT_TRAINING_CONFIG = {
    "epochs": 100,
    "batch": 16,
    "imgsz": 640,
    "workers": 8,
    "classes": "",
    "single_cls": False,
    "time": 0,
    # 100 effectively disables early stopping, which is wrong on GPU too.
    "patience": 20,
    "close_mosaic": 10,
    "optimizer": "auto",
    "cos_lr": False,
    "amp": True,
    "multi_scale": False,
    "lr0": 0.01,
    "lrf": 0.01,
    "momentum": 0.937,
    "weight_decay": 0.0005,
    "warmup_epochs": 3.0,
    "warmup_momentum": 0.8,
    "warmup_bias_lr": 0.1,
    "hsv_h": 0.015,
    "hsv_s": 0.7,
    "hsv_v": 0.4,
    "degrees": 0.0,
    "translate": 0.1,
    "scale": 0.5,
    "shear": 0.0,
    "perspective": 0.0,
    "dropout": 0.0,
    "fraction": 1.0,
    "rect": False,
    "box": 7.5,
    "cls": 0.5,
    "dfl": 1.5,
    "pose": 12.0,
    "kobj": 2.0,
    "save_period": -1,
    "val": True,
    # On by default: the dialog's Training Images panel only reads the
    # artifacts ultralytics writes when plots=True (train_batch*.jpg,
    # *PR_curve.png, results.png). With it off the panel can never show
    # anything, which reads as a broken widget rather than a choice.
    "plots": True,
    "save": True,
    "resume": False,
    "cache": False,
}

#: CPU-safe overrides layered on top of the GPU-oriented defaults above. On
#: Windows a dataloader worker count > 0 needs spawned child processes, so
#: workers stays 0 on CPU; fewer epochs / a shorter patience keep a first
#: CPU pass from running for hours before showing anything useful.
CPU_TRAINING_OVERRIDES = {
    "epochs": 50,
    "batch": 8,
    "imgsz": 416,
    "workers": 0,
    "patience": 10,
}


def get_default_training_config(device=None):
    """Return a fresh deep copy of the default training config for ``device``.

    ``device`` of ``None`` or ``"cpu"`` applies :data:`CPU_TRAINING_OVERRIDES`;
    a GPU device (cuda/mps) keeps the GPU-oriented defaults. The copy is
    independent so callers can adjust values without mutating the shared dict.
    """
    config = copy.deepcopy(DEFAULT_TRAINING_CONFIG)
    if device is None or str(device).lower() == "cpu":
        config.update(CPU_TRAINING_OVERRIDES)
    return config


#: Fields the CPU preset fills when still untouched. Keeping the values here
#: (rather than duplicating them in the dialog) means the settings form and
#: the device hint cannot drift apart.
CPU_PARAM_PRESET = {
    key: CPU_TRAINING_OVERRIDES[key] for key in ("epochs", "batch", "imgsz")
}


#: Pretrained checkpoints offered as presets in the training dialog. Bare
#: names (no path) are downloaded on demand by ``resolve_training_model_path``.
#: Detect leads with yolov8 (the ultralytics default); the other tasks lead
#: with yolo11, which the ModelScope mirror hosts for every variant.
PRETRAINED_MODEL_PRESETS = {
    "Detect": [
        "yolov8n.pt",
        "yolov8s.pt",
        "yolo11n.pt",
        "yolo11s.pt",
        "yolov8m.pt",
        "yolo11m.pt",
    ],
    "Segment": [
        "yolo11n-seg.pt",
        "yolo11s-seg.pt",
        "yolov8n-seg.pt",
        "yolov8s-seg.pt",
    ],
    "Pose": [
        "yolo11n-pose.pt",
        "yolo11s-pose.pt",
        "yolov8n-pose.pt",
        "yolov8s-pose.pt",
    ],
    "Classify": [
        "yolo11n-cls.pt",
        "yolo11s-cls.pt",
        "yolov8n-cls.pt",
        "yolov8s-cls.pt",
    ],
}


def get_preset_models(task_type):
    """Preset checkpoint names for ``task_type`` (empty list when unknown)."""
    return list(PRETRAINED_MODEL_PRESETS.get(task_type, []))


OPTIMIZER_OPTIONS = [
    "auto",
    "SGD",
    "Adam",
    "AdamW",
    "NAdam",
    "RAdam",
    "RMSProp",
]
TRAINING_STATUS_COLORS = {
    "idle": "#6c757d",
    "preparing": "#17a2b8",
    "training": "#6f42c1",
    "completed": "#28a745",
    "error": "#ffc107",
}
TRAINING_STATUS_TEXTS = {
    "idle": "Ready to train",
    "preparing": "Preparing dataset",
    "training": "Training in progress",
    "completed": "Training completed",
    "error": "Training error",
}


# Env Check
def is_torch_available() -> bool:
    try:
        import torch

        return hasattr(torch, "__version__")
    except Exception:
        return False


def is_cuda_available() -> bool:
    try:
        import torch

        return torch.cuda.is_available() if is_torch_available() else False
    except Exception:
        return False


def is_mps_available() -> bool:
    try:
        import torch

        return (
            torch.backends.mps.is_available()
            if is_torch_available()
            else False
        )
    except Exception:
        return False


IS_TORCH_AVAILABLE = is_torch_available()
IS_CUDA_AVAILABLE = is_cuda_available()
IS_MPS_AVAILABLE = is_mps_available()
DEVICE_OPTIONS = (
    (["cuda"] if IS_CUDA_AVAILABLE else [])
    + (["mps"] if IS_MPS_AVAILABLE else [])
    + ["cpu"]
)
