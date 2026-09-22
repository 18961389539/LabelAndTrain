"""Classification loop-back: adapter, predictions payload and persistence."""

import json
import os

import numpy as np
import pytest

from anylabeling.services.auto_labeling.types import AutoLabelingResult

onnx = pytest.importorskip("onnx")
ort = pytest.importorskip("onnxruntime")

from onnx import TensorProto, helper, numpy_helper  # noqa: E402

from anylabeling.services.auto_labeling.yolov8_cls import (  # noqa: E402
    YOLOv8Cls,
    softmax,
)

SIZE = 32
CLASSES = ["cat", "dog", "bird"]

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
TEMPLATE_CONFIG = os.path.join(
    REPO_ROOT, "anylabeling", "configs", "xanylabeling_config.yaml"
)


@pytest.fixture(autouse=True)
def app_config_file():
    """Model.__init__ reads the app config; it resolves to None otherwise."""
    from anylabeling import config as app_config

    previous = app_config.current_config_file
    app_config.current_config_file = TEMPLATE_CONFIG
    yield
    app_config.current_config_file = previous


def _build_fake_classifier(path):
    """A model whose logits are the per-channel means of the input.

    Feeding a solid colour therefore makes the winning class a direct read of
    the channel order and scaling the adapter applies - the two things that are
    easy to get wrong and impossible to see in a unit test otherwise.
    """
    x = helper.make_tensor_value_info(
        "input", TensorProto.FLOAT, [1, 3, SIZE, SIZE]
    )
    y = helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 3])
    pool = helper.make_node("GlobalAveragePool", ["input"], ["pooled"])
    reshape = helper.make_node(
        "Reshape",
        ["pooled", "shape"],
        ["output"],
        name="flatten_to_logits",
    )
    shape = numpy_helper.from_array(
        np.array([1, 3], dtype=np.int64), name="shape"
    )
    graph = helper.make_graph(
        [pool, reshape], "fake_cls", [x], [y], initializer=[shape]
    )
    model = helper.make_model(
        graph, opset_imports=[helper.make_opsetid("", 13)]
    )
    model.ir_version = 10
    onnx.save(model, path)


@pytest.fixture
def model_dir(tmp_path):
    onnx_path = tmp_path / "best.onnx"
    _build_fake_classifier(str(onnx_path))
    return tmp_path, str(onnx_path)


def _adapter(onnx_path, **overrides):
    config = {
        "type": "yolov8_cls",
        "name": "run_07_best",
        "display_name": "训练权重 · run_07",
        "model_path": onnx_path,
        "classes": CLASSES,
        "conf_threshold": 0.0,
        "topk": 3,
    }
    config.update(overrides)
    return YOLOv8Cls(config, on_message=lambda _text: None)


def _solid_image(value_per_channel):
    """BGR image where each channel is a flat intensity."""
    blue, green, red = value_per_channel
    array = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
    array[:, :, 0] = blue
    array[:, :, 1] = green
    array[:, :, 2] = red
    return array


def test_softmax_is_a_distribution():
    probs = softmax(np.array([2.0, 1.0, 0.0], dtype=np.float32))
    assert probs.sum() == pytest.approx(1.0)
    assert probs[0] > probs[1] > probs[2]


def test_adapter_reports_shapes_free_predictions(model_dir):
    _tmp, onnx_path = model_dir
    adapter = _adapter(onnx_path)
    result = adapter.predict_shapes(_solid_image((10, 10, 200)))

    assert isinstance(result, AutoLabelingResult)
    # A suggestion must never masquerade as an annotation.
    assert result.shapes == []
    assert result.replace is False
    labels = [item["label"] for item in result.predictions]
    assert labels[0] == "cat"  # index 0 is the red channel, strongest here
    assert len(labels) == len(CLASSES)
    for item in result.predictions:
        assert item["model"] == "run_07_best"
        assert item["created_at"]
        assert 0.0 <= item["score"] <= 1.0
    total = sum(item["score"] for item in result.predictions)
    assert total == pytest.approx(1.0, abs=1e-4)


def test_channel_order_decides_the_winner(model_dir):
    _tmp, onnx_path = model_dir
    adapter = _adapter(onnx_path)
    # Green-dominant input must rank index 1 ("dog") first.
    result = adapter.predict_shapes(_solid_image((10, 220, 10)))
    assert result.predictions[0]["label"] == "dog"


def test_topk_and_confidence_floor_are_honoured(model_dir):
    _tmp, onnx_path = model_dir
    top_only = _adapter(onnx_path, topk=1)
    assert len(top_only.predict_shapes(_solid_image((5, 5, 9))).predictions) == 1

    floored = _adapter(onnx_path, conf_threshold=0.999)
    assert floored.predict_shapes(_solid_image((50, 50, 50))).predictions == []


def test_missing_class_names_fall_back_to_indexes(model_dir):
    _tmp, onnx_path = model_dir
    adapter = _adapter(onnx_path, classes=[])
    predictions = adapter.predict_shapes(_solid_image((1, 2, 200))).predictions
    # The blob is channel-first RGB, so the red channel is logit 0.
    assert predictions[0]["label"] == "0"


def test_blob_is_channel_first_and_expected_size(model_dir):
    _tmp, onnx_path = model_dir
    adapter = _adapter(onnx_path)
    blob = adapter.preprocess(_solid_image((1, 2, 3)))
    assert blob.shape == (1, 3, SIZE, SIZE)
    assert blob.dtype == np.float32
    # Default feeds raw 0-255 because Ultralytics folds /255 into the graph.
    assert blob.max() > 1.0
    rescaled = _adapter(onnx_path, rescale=True).preprocess(
        _solid_image((1, 2, 3))
    )
    assert rescaled.max() == pytest.approx(3.0 / 255.0)


def test_batch_writer_stores_predictions_without_touching_shapes(tmp_path):
    from anylabeling.views.labeling.utils.batch import (
        save_classification_predictions,
    )

    label_path = tmp_path / "a.json"
    existing_shape = {"label": "cat", "points": [[0, 0], [4, 4]]}
    label_path.write_text(
        json.dumps(
            {
                "shapes": [existing_shape],
                "checked": True,
                "review_state": "confirmed",
                "imageWidth": 10,
                "imageHeight": 10,
            }
        ),
        encoding="utf-8",
    )

    class Owner:
        output_dir = None
        _config = {"store_data": False}

    saved = save_classification_predictions(
        Owner(),
        str(label_path),
        [{"label": "dog", "score": 0.7, "model": "run_07_best"}],
    )
    assert saved is True
    data = json.loads(label_path.read_text(encoding="utf-8"))
    assert data["shapes"] == [existing_shape]
    assert data["review_state"] == "confirmed"
    assert data["predictions"]["classes"][0]["label"] == "dog"
    assert data["predictions"]["model"] == "run_07_best"


def test_batch_writer_creates_a_label_file_for_new_images(tmp_path):
    from anylabeling.views.labeling.utils.batch import (
        save_classification_predictions,
    )

    image_path = tmp_path / "new.jpg"
    import cv2

    cv2.imwrite(str(image_path), np.zeros((6, 4, 3), dtype=np.uint8))

    class Owner:
        output_dir = str(tmp_path)
        _config = {"store_data": False}

    assert (
        save_classification_predictions(
            Owner(), str(image_path), [{"label": "cat", "score": 0.6}]
        )
        is True
    )
    data = json.loads((tmp_path / "new.json").read_text(encoding="utf-8"))
    assert data["shapes"] == []
    assert data["imageWidth"] == 4
    assert data["imageHeight"] == 6
    assert data["predictions"]["classes"][0]["label"] == "cat"


def test_predictions_survive_a_label_file_round_trip(tmp_path):
    from anylabeling.views.labeling import label_file

    path = tmp_path / "a.json"
    # LabelFile.load validates dimensions, so the image must really exist.
    import cv2

    cv2.imwrite(str(tmp_path / "a.jpg"), np.zeros((6, 4, 3), dtype=np.uint8))
    payload = {
        "shapes": [],
        "checked": False,
        "imagePath": "a.jpg",
        "imageData": None,
        "predictions": {
            "model": "run_07_best",
            "created_at": "2026-09-22 10:00:00",
            "classes": [{"label": "cat", "score": 0.8}],
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    label = label_file.LabelFile()
    label.image_dir = str(tmp_path)
    label.load(str(path))
    stored = label.other_data["predictions"]
    assert stored["model"] == "run_07_best"
    assert stored["classes"][0]["label"] == "cat"

    label.save(
        filename=str(path),
        shapes=[],
        image_path="a.jpg",
        image_height=6,
        image_width=4,
        image_data=None,
        other_data=label.other_data,
    )
    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["predictions"]["classes"][0]["label"] == "cat"
    assert after["predictions"]["model"] == "run_07_best"


def test_reader_accepts_both_recorded_shapes():
    from anylabeling.views.labeling.label_widget import LabelingWidget

    def widget_with(other_data):
        fake = type("W", (), {"other_data": other_data})()
        fake._classification_suggestions = (
            LabelingWidget._classification_suggestions.__get__(fake)
        )
        return fake

    suggestions, model = widget_with(
        {
            "predictions": {
                "model": "m1",
                "classes": [{"label": "cat", "score": 0.9}],
            }
        }
    )._classification_suggestions()
    assert model == "m1"
    assert suggestions[0]["label"] == "cat"

    # Older records stored the bare list.
    suggestions, model = widget_with(
        {"predictions": [{"label": "dog", "score": 0.5}]}
    )._classification_suggestions()
    assert suggestions[0]["label"] == "dog"
    assert model is None

    assert widget_with({})._classification_suggestions() == ([], None)
    assert widget_with({"predictions": None})._classification_suggestions() == (
        [],
        None,
    )
