"""Regression guards for the auto-labeling service layer.

Three defects fixed 2026-10-08, all of them silent:

* ``YOLOv8Cls`` handed a ``QImage`` straight to ``cv2.cvtColor`` — every
  classification attempt raised and surfaced as a generic "model error".
* ``GenericWorker.run`` emitted ``finished`` only on a clean return, so a
  single raising payload left the model switcher locked for the session.
* ``YOLOv8SegmentAnything2.unload`` called ``quit`` without parentheses and
  never released ``self.model``.

The stubs follow the repository convention: plain ``SimpleNamespace`` for
anything that only touches attributes, real objects only where a Qt signal
is involved.
"""

from types import SimpleNamespace

import numpy as np
import pytest

from anylabeling.services.auto_labeling import yolov8_cls as cls_module
from anylabeling.services.auto_labeling import yolov8_sam2 as sam2_module
from anylabeling.services.auto_labeling.worker import GenericWorker


class TestGenericWorkerAlwaysFinishes:
    """``finished`` drives the "a model operation is running" flag."""

    def test_finished_is_emitted_when_the_payload_raises(self):
        worker = GenericWorker(lambda: 1 / 0)
        received = []
        worker.finished.connect(lambda: received.append(True))

        worker.run()

        assert received == [True]

    def test_finished_is_emitted_on_success(self):
        calls = []
        worker = GenericWorker(calls.append, "ok")
        received = []
        worker.finished.connect(lambda: received.append(True))

        worker.run()

        assert calls == ["ok"]
        assert received == [True]

    def test_arguments_reach_the_payload(self):
        seen = {}
        worker = GenericWorker(lambda a, b=None: seen.update(a=a, b=b), 1, b=2)

        worker.run()

        assert seen == {"a": 1, "b": 2}


def _classifier(**overrides):
    """The subset of ``YOLOv8Cls`` state that ``preprocess`` touches."""
    state = {"input_width": 4, "input_height": 4, "rescale": False}
    state.update(overrides)
    return SimpleNamespace(**state)


class TestYOLOv8ClsChannelOrder:
    """``preprocess`` takes RGB already: predict_shapes converts."""

    def test_preprocess_does_not_convert_colour_again(self):
        image = np.zeros((8, 8, 3), dtype=np.uint8)
        image[..., 0] = 200  # red, in RGB order
        image[..., 2] = 50

        blob = cls_module.YOLOv8Cls.preprocess(_classifier(), image)

        assert blob.shape == (1, 3, 4, 4)
        # A stray BGR2RGB would move the red channel to index 2.
        assert blob[0, 0].max() == pytest.approx(200.0)
        assert blob[0, 2].max() == pytest.approx(50.0)

    def test_rescale_is_still_opt_in(self):
        image = np.full((4, 4, 3), 255, dtype=np.uint8)

        assert cls_module.YOLOv8Cls.preprocess(
            _classifier(), image
        ).max() == pytest.approx(255.0)
        assert cls_module.YOLOv8Cls.preprocess(
            _classifier(rescale=True), image
        ).max() == pytest.approx(1.0)

    def test_predict_shapes_normalises_the_qimage_first(self, monkeypatch):
        seen = []

        def _convert(image, image_path=None):
            seen.append((image, image_path))
            return np.zeros((4, 4, 3), dtype=np.uint8)

        monkeypatch.setattr(cls_module, "qt_img_to_rgb_cv_img", _convert)

        class _Boom(Exception):
            """Stops predict_shapes right after preprocessing."""

        stub = SimpleNamespace()
        stub.preprocess = lambda image: np.zeros((1, 3, 4, 4), np.float32)
        stub.net = SimpleNamespace(
            get_ort_inference=lambda blob: (_ for _ in ()).throw(_Boom())
        )

        with pytest.raises(_Boom):
            cls_module.YOLOv8Cls.predict_shapes(
                stub, "SENTINEL-IMAGE", "C:/tmp/x.png"
            )

        assert seen == [("SENTINEL-IMAGE", "C:/tmp/x.png")]

    def test_predict_shapes_reports_an_unreadable_image(self, monkeypatch):
        def _explode(image, image_path=None):
            raise ValueError("cannot decode")

        monkeypatch.setattr(cls_module, "qt_img_to_rgb_cv_img", _explode)

        stub = SimpleNamespace()
        stub.preprocess = lambda image: pytest.fail(
            "preprocess must not run when the image cannot be read"
        )

        assert cls_module.YOLOv8Cls.predict_shapes(stub, object(), None)

    def test_predict_shapes_passes_none_through(self):
        stub = SimpleNamespace()
        stub.preprocess = lambda image: pytest.fail("no image, no work")

        assert cls_module.YOLOv8Cls.predict_shapes(stub, None, None)


class _RecordingThread:
    def __init__(self):
        self.quit_calls = 0

    def quit(self):
        self.quit_calls += 1


class TestYOLOv8Sam2Unload:
    def test_unload_quits_the_thread_and_releases_the_model(self):
        thread = _RecordingThread()
        stub = SimpleNamespace(
            net=object(),
            stop_inference=False,
            pre_inference_thread=thread,
            pre_inference_worker=object(),
            model=object(),
        )

        sam2_module.YOLOv8SegmentAnything2.unload(stub)

        assert thread.quit_calls == 1
        assert stub.stop_inference is True
        assert stub.model is None
        assert stub.pre_inference_worker is None

    def test_unload_tolerates_a_never_started_thread(self):
        stub = SimpleNamespace(
            net=object(),
            stop_inference=False,
            pre_inference_thread=None,
            pre_inference_worker=None,
            model=object(),
        )

        sam2_module.YOLOv8SegmentAnything2.unload(stub)

        assert stub.model is None
