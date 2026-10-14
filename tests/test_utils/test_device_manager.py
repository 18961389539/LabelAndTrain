"""设备管理：设备串归一、多卡、越界回退与"为什么用 CPU"的诊断。

探测结果一律注入（monkeypatch 实例方法），测试不依赖机器上有没有卡。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from anylabeling.views.common import device_manager as dm_module


@pytest.fixture()
def dm():
    """A clean singleton: no pinned device, no cached probes."""
    manager = dm_module.DeviceManager()
    manager.refresh_devices()
    yield manager
    manager.refresh_devices()


def _fake_gpu(dm, count, names=None):
    """Pretend onnxruntime has CUDA and ``count`` cards are installed."""
    dm._available_providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    dm._torch_cuda_devices = (
        names or [f"GPU Card {i}" for i in range(count)]
    )[:count]


def _no_gpu(dm, torch_names=None):
    dm._available_providers = ["CPUExecutionProvider"]
    dm._torch_cuda_devices = list(torch_names or [])


# --- 设备串归一 -------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("cpu", "CPU"),
        ("CPU", "CPU"),
        (" cpu ", "CPU"),
        ("gpu", "GPU"),
        ("GPU", "GPU"),
        ("cuda", "GPU"),
        ("cuda:0", "GPU"),
        ("gpu:0", "GPU"),
        ("gpu:1", "GPU:1"),
        ("CUDA:2", "GPU:2"),
    ],
)
def test_parse_device_spec_normalizes(raw, expected):
    assert dm_module.parse_device_spec(raw) == expected


@pytest.mark.parametrize(
    "raw", [None, "", "  ", "tpu:1", "gpu:x", "GPU:-1", 42]
)
def test_parse_device_spec_rejects_junk(raw):
    assert dm_module.parse_device_spec(raw) is None


# --- 多卡 -------------------------------------------------------------------


def test_single_gpu_machine_offers_cpu_and_gpu(dm):
    _fake_gpu(dm, 1)
    assert dm.get_available_devices() == ["CPU", "GPU"]


def test_multi_gpu_machine_offers_each_card(dm):
    _fake_gpu(dm, 3, ["RTX 4090", "RTX 3080", "RTX 3060"])
    assert dm.get_available_devices() == ["CPU", "GPU", "GPU:1", "GPU:2"]
    assert dm.gpu_count() == 3


def test_second_card_can_be_selected(dm):
    _fake_gpu(dm, 2)
    assert dm.set_device("cuda:1") == "GPU:1"
    assert dm.get_device() == "GPU:1"


def test_an_index_past_the_end_falls_back_to_the_first_card(dm):
    _fake_gpu(dm, 1)
    assert dm.set_device("gpu:5") == "GPU"
    assert dm.get_device() == "GPU"


def test_gpu_request_without_cuda_falls_back_to_cpu(dm):
    _no_gpu(dm)
    assert dm.set_device("gpu:1") == "CPU"
    assert dm.get_device() == "CPU"


def test_a_junk_device_string_raises(dm):
    with pytest.raises(ValueError):
        dm.set_device("tpu")


# --- 来源优先级 -------------------------------------------------------------


def test_environment_wins_and_accepts_an_index(dm, monkeypatch):
    _fake_gpu(dm, 2)
    monkeypatch.setenv("X_ANYLABELING_DEVICE", "gpu:1")
    assert dm.get_device() == "GPU:1"


def test_config_is_read_through_get_config(dm, monkeypatch):
    _fake_gpu(dm, 2)
    monkeypatch.delenv("X_ANYLABELING_DEVICE", raising=False)
    import anylabeling.config as app_config

    monkeypatch.setattr(
        app_config, "get_config", lambda *a, **k: {"device": "cuda:1"}
    )
    assert dm.get_device() == "GPU:1"


def test_manual_choice_beats_everything(dm, monkeypatch):
    _fake_gpu(dm, 2)
    monkeypatch.setenv("X_ANYLABELING_DEVICE", "cpu")
    dm.set_device("gpu:1")
    assert dm.get_device() == "GPU:1"


# --- 诊断 -------------------------------------------------------------------


def test_description_says_cpu_only_when_there_is_no_hardware(dm):
    _no_gpu(dm)
    text = dm.describe_devices()
    assert "未检测到可用的 CUDA GPU" in text
    assert "CPU" in text


def test_description_names_the_unusable_card_and_the_fix(dm):
    """卡在、onnxruntime 不是 GPU 版 —— 这正是"标注怎么这么慢"的答案。"""
    _no_gpu(dm, torch_names=["NVIDIA GeForce RTX 4090"])
    text = dm.describe_devices()
    assert "RTX 4090" in text
    assert "onnxruntime-gpu" in text  # 给出处理办法


def test_description_names_the_card_when_gpu_is_usable(dm):
    _fake_gpu(dm, 1, ["NVIDIA RTX A4000"])
    text = dm.describe_devices()
    assert "1 张 CUDA GPU" in text
    assert "RTX A4000" in text


def test_probing_is_cached_until_refreshed(dm):
    _fake_gpu(dm, 1)
    assert dm.gpu_count() == 1
    dm._torch_cuda_devices = []  # 卡被拔了
    assert dm.gpu_count() == 1  # 缓存还在
    dm.refresh_devices()
    dm._available_providers = ["CPUExecutionProvider"]
    assert dm.gpu_count() == 0


def test_refresh_also_drops_the_pin(dm):
    _fake_gpu(dm, 1)
    dm.set_device("gpu")
    assert dm.get_device() == "GPU"
    dm.refresh_devices()
    _no_gpu(dm)
    assert dm.get_device() == "CPU"


# --- 给失败用户的建议（模型加载失败对话框用） --------------------------------


def test_advice_names_the_card_and_the_install(dm):
    _no_gpu(dm, torch_names=["NVIDIA RTX 4090"])
    advice = dm.gpu_advice()
    assert advice and "RTX 4090" in advice and "onnxruntime-gpu" in advice


def test_advice_is_silent_when_a_gpu_is_usable(dm):
    _fake_gpu(dm, 1)
    assert dm.gpu_advice() is None


def test_advice_is_silent_on_a_cpu_only_machine(dm):
    """没有卡的机器不该收到做不到的作业。"""
    _no_gpu(dm)
    assert dm.gpu_advice() is None
