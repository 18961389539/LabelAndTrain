"""Train-side ModelScope-first weight download: offline unit tests."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jllabeling.services.auto_training.ultralytics import trainer

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _clear_hub_env():
    for key in ("JLLABELING_MODEL_HUB",):
        os.environ.pop(key, None)


class TestModelscopeUrlMapping(unittest.TestCase):
    def test_yolov8_det_maps_to_verified_repo(self):
        url = trainer._modelscope_training_url("yolov8s.pt")
        self.assertEqual(
            url,
            "https://www.modelscope.cn/models/AI-ModelScope/YOLOv8/"
            "resolve/master/yolov8s.pt",
        )

    def test_yolo11_seg_variant_maps_to_yolo11_repo(self):
        url = trainer._modelscope_training_url("yolo11s-seg.pt")
        self.assertEqual(
            url,
            "https://www.modelscope.cn/models/AI-ModelScope/YOLO11/"
            "resolve/master/yolo11s-seg.pt",
        )

    def test_unsupported_family_returns_none(self):
        # YOLO26 has no verified ModelScope repo yet -> None -> official src.
        self.assertIsNone(trainer._modelscope_training_url("yolo26s.pt"))
        self.assertIsNone(trainer._modelscope_training_url("yolov5s.pt"))


class TestHubPreference(unittest.TestCase):
    def setUp(self):
        _clear_hub_env()
        self.config_patcher = mock.patch("jllabeling.config.get_config")
        self.mock_get_config = self.config_patcher.start()

    def tearDown(self):
        self.config_patcher.stop()
        _clear_hub_env()

    def test_env_github_wins_over_config_modelscope(self):
        self.mock_get_config.return_value = {"model_hub": "modelscope"}
        with mock.patch.dict(os.environ, {"JLLABELING_MODEL_HUB": "github"}):
            self.assertFalse(trainer._hub_prefers_modelscope())

    def test_env_modelscope_wins(self):
        self.mock_get_config.return_value = {"model_hub": "github"}
        with mock.patch.dict(
            os.environ, {"JLLABELING_MODEL_HUB": "modelscope"}
        ):
            self.assertTrue(trainer._hub_prefers_modelscope())

    def test_config_modelscope_enables(self):
        self.mock_get_config.return_value = {"model_hub": "modelscope"}
        self.assertTrue(trainer._hub_prefers_modelscope())

    def test_config_github_disables(self):
        self.mock_get_config.return_value = {"model_hub": "github"}
        self.assertFalse(trainer._hub_prefers_modelscope())

    def test_unset_hub_defaults_to_modelscope(self):
        # An absent/empty model_hub means ModelScope regardless of the UI
        # language: the download source must never read "language".
        for cfg in ({"language": "zh_CN"}, {"language": "en_US"}, {}):
            self.mock_get_config.return_value = cfg
            self.assertTrue(
                trainer._hub_prefers_modelscope(), f"cfg={cfg}"
            )

    def test_language_cannot_select_the_download_source(self):
        # zh_CN used to flip the source; an explicit github hub now wins.
        self.mock_get_config.return_value = {
            "model_hub": "github",
            "language": "zh_CN",
        }
        self.assertFalse(trainer._hub_prefers_modelscope())


class FakeResponse:
    """Minimal urllib response: context manager + headers + read chunks."""

    def __init__(self, chunks, total=None):
        self._chunks = list(chunks)
        self.headers = {
            "Content-Length": str(
                total
                if total is not None
                else sum(len(c) for c in self._chunks)
            )
        }

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, _size=-1):
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class TestDownloadFile(unittest.TestCase):
    def test_success_writes_zip_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "yolov8s.pt")
            response = FakeResponse([b"PK\x03\x04rest-of-file"])
            with mock.patch("urllib.request.urlopen", return_value=response):
                self.assertTrue(trainer._download_file("http://x/y.pt", dest))
            self.assertTrue(os.path.exists(dest))
            with open(dest, "rb") as f:
                self.assertTrue(f.read().startswith(b"PK"))
            self.assertFalse(os.path.exists(dest + ".part"))

    def test_invalid_payload_cleans_partial_and_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "yolov8s.pt")
            response = FakeResponse([b"not a torch archive"])
            with mock.patch("urllib.request.urlopen", return_value=response):
                self.assertFalse(trainer._download_file("http://x/y.pt", dest))
            self.assertFalse(os.path.exists(dest))
            self.assertFalse(os.path.exists(dest + ".part"))

    def test_network_error_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "yolov8s.pt")
            with mock.patch(
                "urllib.request.urlopen",
                side_effect=OSError("connection refused"),
            ):
                self.assertFalse(trainer._download_file("http://x/y.pt", dest))
            self.assertFalse(os.path.exists(dest))


class TestResolveTrainingModelPath(unittest.TestCase):
    def setUp(self):
        self.weights_patcher = mock.patch.object(
            trainer, "get_training_weights_dir"
        )
        self.mock_weights_dir = self.weights_patcher.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.mock_weights_dir.return_value = self.tmp.name

    def tearDown(self):
        self.weights_patcher.stop()
        self.tmp.cleanup()

    def test_cache_hit_returns_without_download(self):
        cached = Path(self.tmp.name) / "yolov8s.pt"
        cached.write_bytes(b"PK cached")
        with (
            mock.patch.object(trainer, "_try_download_modelscope") as ms,
            mock.patch.object(trainer, "_fallback_official_download") as fb,
        ):
            result = trainer.resolve_training_model_path("yolov8s.pt")
            ms.assert_not_called()
            fb.assert_not_called()
        self.assertEqual(result, str(cached))

    def test_modelscope_tried_first_then_official_fallback(self):
        with (
            mock.patch.object(
                trainer, "_hub_prefers_modelscope", return_value=True
            ),
            mock.patch.object(
                trainer, "_try_download_modelscope", return_value=False
            ) as ms,
            mock.patch.object(
                trainer,
                "_fallback_official_download",
                return_value="/official/yolov8s.pt",
            ) as fb,
        ):
            result = trainer.resolve_training_model_path("yolov8s.pt")
            ms.assert_called_once()
            fb.assert_called_once()
        self.assertEqual(result, "/official/yolov8s.pt")

    def test_github_hub_skips_modelscope(self):
        with (
            mock.patch.object(
                trainer, "_hub_prefers_modelscope", return_value=False
            ),
            mock.patch.object(trainer, "_try_download_modelscope") as ms,
            mock.patch.object(
                trainer,
                "_fallback_official_download",
                return_value="/official/yolov8s.pt",
            ) as fb,
        ):
            result = trainer.resolve_training_model_path("yolov8s.pt")
            ms.assert_not_called()
            fb.assert_called_once()
        self.assertEqual(result, "/official/yolov8s.pt")


class TestNetworkDefaults(unittest.TestCase):
    def test_download_uses_shared_timeout_and_chunk_size(self):
        seen = {}

        class RecordingResponse(FakeResponse):
            def read(self, size=-1):
                seen.setdefault("chunk", size)
                return super().read(size)

        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "yolov8s.pt")
            response = RecordingResponse([b"PK\x03\x04rest"])
            with (
                mock.patch(
                    "urllib.request.urlopen", return_value=response
                ) as urlopen,
                mock.patch.object(
                    trainer.net_defaults, "weights_timeout", return_value=17
                ),
                mock.patch.object(
                    trainer.net_defaults,
                    "weights_chunk_size",
                    return_value=99,
                ),
            ):
                self.assertTrue(
                    trainer._download_file("http://x/y.pt", dest)
                )
            self.assertEqual(urlopen.call_args.kwargs["timeout"], 17)
            self.assertEqual(seen["chunk"], 99)


class TestOfflineMode(unittest.TestCase):
    def test_download_file_skips_the_network_in_offline_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = os.path.join(tmp, "yolov8s.pt")
            with (
                mock.patch.dict(os.environ, {"JLLABELING_OFFLINE": "1"}),
                mock.patch("urllib.request.urlopen") as urlopen,
            ):
                self.assertFalse(
                    trainer._download_file("http://x/y.pt", dest)
                )
                urlopen.assert_not_called()
            self.assertFalse(os.path.exists(dest))

    def test_resolve_fails_fast_with_a_readable_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.dict(os.environ, {"JLLABELING_OFFLINE": "1"}),
                mock.patch.object(
                    trainer, "get_training_weights_dir", return_value=tmp
                ),
                mock.patch.object(
                    trainer, "_fallback_official_download"
                ) as fallback,
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    trainer.resolve_training_model_path("yolov8s.pt")
                self.assertIn("offline mode", str(ctx.exception))
                fallback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
