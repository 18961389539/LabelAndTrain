"""设备管理：决定自动标注跑在哪块硬件上，并把"为什么"说清楚。

现有约定：自动标注的推理后端是 ONNX Runtime，设备串是 ``"CPU"`` /
``"GPU"``。本模块在此之上补三件事：

1. **多卡**：``"GPU:1"``（别名 ``cuda:1`` / ``gpu:1``）指定第 N 张卡；
   越界不报错，回退第 0 张并记警告 —— 设备名写错不该让标注打不开。
2. **诊断**：机器装了 NVIDIA 卡但 onnxruntime 不是 GPU 版时，原本是
   *静默降级到 CPU*（用户只感到"慢"，看不出原因）。现在会明确记一条
   含处理办法的警告，``describe_devices()`` 也给出一行可读摘要。
3. **可刷新**：``refresh_devices()`` 清掉探测缓存 —— 装完
   onnxruntime-gpu 不必重启就能重新探测（给未来的设备面板用）。

优先级不变：手动选择 → 环境变量 ``X_ANYLABELING_DEVICE`` → 配置
``device`` → 自动探测。
"""

import os
import logging
from typing import Literal, Optional

logger = logging.getLogger(__name__)

DeviceType = Literal["CPU", "GPU", "AUTO"]

#: 环境变量与配置里能写的前缀，统一归一到 ``GPU`` / ``GPU:N``。
_GPU_ALIASES = ("gpu", "cuda")


def parse_device_spec(value) -> Optional[str]:
    """Normalize a user-supplied device string, or ``None`` if unknown.

    ``"cpu"`` → ``"CPU"``; ``"gpu"`` / ``"cuda"`` / ``"cuda:0"`` →
    ``"GPU"``; ``"gpu:1"`` → ``"GPU:1"``. Index aliases are folded so the
    rest of the app only ever sees one spelling.
    """
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text == "cpu":
        return "CPU"
    head, _, tail = text.partition(":")
    if head in _GPU_ALIASES:
        if not tail:
            return "GPU"
        if not tail.isdigit():
            return None
        index = int(tail)
        return "GPU" if index == 0 else f"GPU:{index}"
    return None


class DeviceManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._preferred_device = None
        self._available_providers = None
        self._torch_cuda_devices = None

    # --- public API --------------------------------------------------------

    def get_device(self) -> str:
        if self._preferred_device:
            return self._preferred_device

        env_spec = parse_device_spec(os.getenv("X_ANYLABELING_DEVICE", ""))
        if env_spec:
            logger.info(f"Using device from environment: {env_spec}")
            return self._validate_and_set(env_spec)

        config_device = self._load_from_config()
        if config_device:
            logger.info(f"Using device from config: {config_device}")
            return self._validate_and_set(config_device)

        return self._auto_detect()

    def set_device(self, device: str) -> str:
        """Pin the device; returns what actually took effect.

        ``"GPU:3"`` on a one-GPU machine does not raise -- it falls back
        to the first GPU (or CPU) with a warning, the same gate the
        environment and config paths go through. The return value is the
        normalized, validated string so callers can show the truth.
        """
        spec = parse_device_spec(device)
        if spec is None:
            raise ValueError(f"Invalid device: {device}")

        self._validate_and_set(spec)
        logger.info(f"Device manually set to: {self._preferred_device}")
        return self._preferred_device

    def reset_device_preference(self):
        self._preferred_device = None
        logger.info("Device preference reset to auto")

    def get_available_devices(self) -> list:
        """Selectable device strings, first GPU first.

        Each GPU is its own entry (``"GPU"``, ``"GPU:1"`` …) so a
        multi-card machine can be told which one to use.
        """
        devices = ["CPU"]
        count = self.gpu_count()
        if count > 0:
            devices.append("GPU")
            devices.extend(f"GPU:{i}" for i in range(1, count))
        return devices

    def gpu_count(self) -> int:
        """How many GPUs ONNX Runtime can actually use (0 = CPU only).

        ONNX Runtime does not report a count, so a usable CUDA provider
        means "at least one card"; when torch can see them too, its count
        is the better answer (and names the card for the description).
        """
        if not self._is_gpu_available():
            return 0
        return len(self._probe_torch_cuda()) or 1

    def describe_devices(self) -> str:
        """One human-readable line about what this machine offers.

        Written for a log line and a future device panel: it says which
        backend can use a GPU *and*, when the hardware is there but the
        backend is not, what to install.
        """
        parts = [f"CPU ({os.cpu_count() or '?'} 核)"]
        torch_cards = self._torch_cuda_devices or []
        if self._is_gpu_available():
            count = self.gpu_count()
            gpu = f"{count} 张 CUDA GPU（onnxruntime）"
            if torch_cards:
                gpu += f"：{torch_cards[0]}"
            parts.append(gpu)
        elif torch_cards:
            parts.append(
                f"检测到 {len(torch_cards)} 张 NVIDIA GPU（{torch_cards[0]}），"
                "但 onnxruntime 未启用 CUDAExecutionProvider —— "
                "自动标注将使用 CPU；安装 onnxruntime-gpu 后可用 GPU 加速"
            )
        else:
            parts.append("未检测到可用的 CUDA GPU")
        return "；".join(parts)

    def gpu_advice(self) -> Optional[str]:
        """What to tell a user whose model just failed on this machine.

        Returns a sentence only in the actionable case -- NVIDIA hardware
        present but onnxruntime without CUDA -- because that user's next
        step is a concrete install. ``None`` otherwise: a CPU-only machine
        gets no homework it cannot do.
        """
        if self._is_gpu_available():
            return None
        cards = self._probe_torch_cuda()
        if not cards:
            return None
        return (
            f"本机有 NVIDIA GPU（{cards[0]}），但当前 onnxruntime 未启用 CUDA，"
            "自动标注只能跑 CPU。安装与 torch 的 CUDA 版本对应的 "
            "onnxruntime-gpu 后，重新启动即可用 GPU 加速。"
        )

    def refresh_devices(self):
        """Forget every probe result, so the next call re-detects.

        Invalidates the pinned device too: the pin was validated against
        the old detection, and a GPU that has gone away must not stay
        selected.
        """
        self._available_providers = None
        self._torch_cuda_devices = None
        self._preferred_device = None
        logger.info("Device probing cache cleared")

    # --- validation --------------------------------------------------------

    def _validate_and_set(self, device: str) -> str:
        spec = parse_device_spec(device) or "CPU"

        if spec.startswith("GPU"):
            spec = self._clamp_gpu_index(spec)

        self._preferred_device = spec
        return spec

    def _clamp_gpu_index(self, spec: str) -> str:
        """Gate a GPU request against what is really usable.

        No usable GPU at all → CPU. An index past the end of the list →
        the first GPU, with a warning that says both numbers, because
        "I asked for card 2" silently becoming card 0 is exactly the kind
        of quiet wrong answer this module exists to avoid.
        """
        if not self._is_gpu_available():
            logger.warning(
                "GPU requested but not available. Falling back to CPU."
            )
            return "CPU"

        if ":" not in spec:
            # 没写卡号就不必数卡 —— 数卡要 import torch，启动路径不做这件事。
            return "GPU"

        index = self._gpu_index_of(spec)
        count = self.gpu_count()
        if index >= count:
            logger.warning(
                f"GPU:{index} requested but only {count} GPU(s) are "
                "available. Falling back to GPU:0."
            )
            index = 0
        return "GPU" if index == 0 else f"GPU:{index}"

    @staticmethod
    def _gpu_index_of(spec: str) -> int:
        _, _, tail = spec.partition(":")
        return int(tail) if tail.isdigit() else 0

    # --- detection ---------------------------------------------------------

    def _auto_detect(self) -> str:
        if self._is_gpu_available():
            logger.info("GPU detected and available, using GPU")
            self._preferred_device = "GPU"
            return "GPU"

        logger.info("GPU not available, using CPU")
        self._preferred_device = "CPU"
        return "CPU"

    def _is_gpu_available(self) -> bool:
        """Whether auto labeling can use a GPU (onnxruntime's own answer)."""
        if self._available_providers is None:
            try:
                import onnxruntime as ort

                self._available_providers = ort.get_available_providers()
            except Exception as e:
                logger.debug(f"Failed to get ONNX providers: {e}")
                self._available_providers = []

        return "CUDAExecutionProvider" in self._available_providers

    def _probe_torch_cuda(self) -> list:
        """NVIDIA card names torch can see; ``[]`` when torch is absent.

        Diagnosis only -- never a reason to hand ONNX Runtime a GPU it
        cannot use. Torch is imported lazily because it is heavy and the
        rest of the app does not need it at startup.
        """
        if self._torch_cuda_devices is None:
            devices = []
            try:
                import torch

                if torch.cuda.is_available():
                    devices = [
                        torch.cuda.get_device_name(i)
                        for i in range(torch.cuda.device_count())
                    ]
            except Exception as e:
                logger.debug(f"Could not probe torch for GPUs: {e}")
            self._torch_cuda_devices = devices
        return self._torch_cuda_devices

    def _load_from_config(self) -> Optional[str]:
        """The device pinned in the app config, if any.

        Goes through ``get_config`` so a ``--config`` path and the template's
        merge rules both apply — reading ``.xanylabelingrc`` directly ignored
        both, which is how this could disagree with the settings dialog about
        what the config says.
        """
        try:
            from anylabeling.config import get_config

            device = get_config().get("device")
        except Exception as e:
            logger.debug(f"Failed to load device from config: {e}")
            return None

        return parse_device_spec(device)


device_manager = DeviceManager()


def get_preferred_device() -> str:
    return device_manager.get_device()
