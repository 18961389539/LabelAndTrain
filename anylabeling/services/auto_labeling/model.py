import os
import pathlib
import yaml
import urllib.request
import time
import multiprocessing
import socket
from urllib.parse import urlparse
from urllib.error import URLError, HTTPError

socket.setdefaulttimeout(240)  # Prevent timeout when downloading models

from abc import abstractmethod

from PyQt6.QtCore import QCoreApplication, QFile
from .types import AutoLabelingResult, DownloadCancelledError
from anylabeling.config import get_config, get_work_directory
from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.label_file import LabelFile, LabelFileError
from anylabeling.views.labeling import utils


def _check_model_worker(model_path):
    """Worker function to validate model in subprocess.

    Only reached for ``.pth`` / ``.pt`` weights (see ``safe_check_model``):
    ``torch.load`` on a corrupt archive can hard-crash the process, so it
    is isolated in a child process.
    """
    try:
        file_extension = os.path.splitext(model_path)[1].lower()
        if file_extension == ".onnx":
            import onnx

            onnx.checker.check_model(model_path)
        elif file_extension in [".pth", ".pt"]:
            import torch

            torch.load(model_path, map_location="cpu")
        else:
            raise ValueError(f"Unsupported model format: {file_extension}")
    except Exception as e:
        import sys

        print(f"Model check failed: {e}", file=sys.stderr)
        sys.exit(1)


def safe_check_model(model_path, timeout=30, on_stage=None):
    """Check model integrity without crashing the application.

    The check is deliberately *lightweight*:
    - ``.onnx`` files are only sanity-checked on the file level (non-empty)
      — the deep protobuf parse (``onnx.checker``) is NOT run here because
      importing the ``onnx`` C++ extensions inside a PyInstaller onefile exe
      is unreliable (some ``onnx_cpp2py_export`` submodules are not
      collected) and crashes the process. Real validation happens later in
      the onnxruntime ``InferenceSession`` constructor, which raises a
      catchable Python exception for corrupt files.
    - ``.pth`` / ``.pt`` weights keep the spawn-subprocess isolation,
      because a corrupt ``torch.load`` can hard-crash the process.

    Args:
        model_path: Absolute path to the model file.
        timeout: Subprocess timeout (only used for .pth/.pt weights).
        on_stage: Optional callable receiving human-readable progress.

    Returns:
        True if the file passed validation, False otherwise.
    """
    file_extension = os.path.splitext(model_path)[1].lower()

    # --- .onnx: lightweight file-level check (safe in any packaging) -------
    if file_extension == ".onnx":
        if on_stage is not None:
            on_stage(
                QCoreApplication.translate(
                    "Model", "Verifying model file integrity..."
                )
            )
        try:
            if os.path.getsize(model_path) > 0:
                if on_stage is not None:
                    on_stage(
                        QCoreApplication.translate(
                            "Model", "Model file verified."
                        )
                    )
                return True
        except OSError:
            pass
        logger.warning(f"Model file is empty or unreadable: {model_path}")
        if on_stage is not None:
            on_stage(
                QCoreApplication.translate(
                    "Model", "Model file is corrupted. Redownloading..."
                )
            )
        return False

    # --- .pth / .pt: subprocess isolation against torch.load segfaults ---
    if on_stage is not None:
        on_stage(
            QCoreApplication.translate(
                "Model", "Verifying model file integrity..."
            )
        )
    ctx = multiprocessing.get_context("spawn")
    p = ctx.Process(target=_check_model_worker, args=(model_path,))
    p.start()
    p.join(timeout)

    if p.exitcode == 0:
        if on_stage is not None:
            on_stage(
                QCoreApplication.translate(
                    "Model", "Model file verified."
                )
            )
        return True
    elif p.exitcode is None:
        logger.warning(
            f"Model check timeout after {timeout}s for {model_path}"
        )
        if on_stage is not None:
            on_stage(
                QCoreApplication.translate(
                    "Model", "Verification timed out. Redownloading..."
                )
            )
        p.terminate()
        p.join(1)
        if p.is_alive():
            p.kill()
            p.join()
        return False
    else:
        logger.warning(
            f"Model check failed with exit code {p.exitcode} for {model_path}"
        )
        if on_stage is not None:
            on_stage(
                QCoreApplication.translate(
                    "Model", "Model file is corrupted. Redownloading..."
                )
            )
        return False


def _set_response_socket_timeout(response, timeout):
    """Set a per-read timeout on the HTTPResponse's underlying socket.

    ``socket.setdefaulttimeout`` only affects sockets that are created
    *after* it is called; the socket opened by ``urlopen`` is already
    alive, so a subsequent default-timeout change does NOT bound its
    blocking ``read()`` calls. Apply the timeout explicitly here so a
    stalled stream eventually raises ``socket.timeout`` and is caught by
    the retry loop in :meth:`Model.download_with_retry`.
    """
    seen = set()
    current = response
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        try:
            current.settimeout(timeout)
            return
        except (OSError, AttributeError, ValueError):
            pass
        # http.client.HTTPResponse exposes the underlying socket as
        # ``sock``; the buffered file object exposes it as ``_sock`` or
        # through ``fp.raw`` — try each reachable object.
        next_obj = None
        if hasattr(current, "sock"):
            next_obj = getattr(current, "sock")
        elif hasattr(current, "fp"):
            fp = current.fp
            if fp is not None and id(fp) not in seen:
                next_obj = fp
            elif fp is not None and hasattr(fp, "raw"):
                raw = fp.raw
                if raw is not None and id(raw) not in seen:
                    next_obj = raw
                elif raw is not None and hasattr(raw, "_sock"):
                    inner = raw._sock
                    if inner is not None and id(inner) not in seen:
                        next_obj = inner
        current = next_obj


class ModelMeta(type):
    """Plain metaclass.

    ``Model`` no longer inherits from ``QObject``: shiboken6's QObject
    metaclass forwards positional ``__init__`` arguments to the C++
    ``QObject.__init__`` constructor, whose first parameter is the
    ``parent`` QObject. Subclasses such as ``SegmentAnything2`` accept a
    config dict and an ``on_message`` callback positionally, so the
    shiboken forwarding raised
    "QObject(parent: ...): argument 1 has unexpected type 'dict'". Since
    the model classes don't define Qt signals themselves (they raise
    status updates via the ``on_message`` callback wired by the model
    manager), dropping ``QObject`` from the base is safe and removes the
    metaclass conflict.
    """


class Model(metaclass=ModelMeta):
    BASE_DOWNLOAD_URL = (
        "https://github.com/CVHub520/X-AnyLabeling/releases/tag"
    )

    MAX_RETRIES = 2
    RETRY_DELAY = 3  # seconds
    DOWNLOAD_CHUNK_SIZE = 64 * 1024  # 64KB
    DOWNLOAD_TIMEOUT = 30  # seconds per connection/read

    class Meta:
        required_config_names = []
        widgets = ["button_run"]
        output_modes = {
            "rectangle": QCoreApplication.translate("Model", "Rectangle"),
        }
        default_output_mode = "rectangle"

    def __init__(self, model_config, on_message) -> None:
        self.on_message = on_message
        if isinstance(model_config, str):
            if not os.path.isfile(model_config):
                raise FileNotFoundError(
                    QCoreApplication.translate(
                        "Model", "Config file not found: {model_config}"
                    ).format(model_config=model_config)
                )
            with open(model_config, "r") as f:
                self.config = yaml.safe_load(f)
        elif isinstance(model_config, dict):
            self.config = model_config
        else:
            raise ValueError(
                QCoreApplication.translate(
                    "Model", "Unknown config type: {type}"
                ).format(type=type(model_config))
            )
        self._cancel_event = self.config.pop("_cancel_event", None)
        self._cancel_prediction_event = self.config.pop(
            "_cancel_prediction_event", None
        )
        self._on_progress = self.config.pop("_on_progress", None)
        self._on_stage = self.config.pop("_on_stage", None)
        self.check_missing_config(
            config_names=self.Meta.required_config_names,
            config=self.config,
        )
        self.output_mode = self.Meta.default_output_mode
        self._config = get_config()

    def _prediction_cancelled(self):
        """Whether the user asked to cancel the running inference.

        Subclasses with long loops (e.g. SAM2 grid segmentation) poll this
        between iterations so a cancel takes effect quickly instead of
        waiting for the whole inference to finish.
        """
        # getattr guards unit tests that construct models via __new__ and
        # never run Model.__init__ (which would set this attribute).
        event = getattr(self, "_cancel_prediction_event", None)
        return event is not None and event.is_set()

    def _emit_stage(self, text):
        """Broadcast a download *phase* to every interested listener.

        ``on_message`` only reaches the status label, and that label is
        frozen by the view as soon as byte-progress starts arriving. The
        stage channel is separate so phases like "Verifying..." or
        "Connecting..." stay visible even while the byte progress bar is
        driving the same row.
        """
        self.on_message(text)
        if self._on_stage is not None:
            try:
                self._on_stage(text)
            except RuntimeError:
                # Underlying QObject was destroyed mid-download.
                self._on_stage = None

    def get_required_widgets(self):
        """
        Get required widgets for showing in UI
        """
        return self.Meta.widgets

    @staticmethod
    def allow_migrate_data():
        """Check if the current env have write permissions"""
        work_dir = get_work_directory()
        old_model_path = os.path.join(work_dir, "anylabeling_data")
        new_model_path = os.path.join(work_dir, "xanylabeling_data")

        if os.path.exists(new_model_path) or not os.path.exists(
            old_model_path
        ):
            return True

        if not os.access(work_dir, os.W_OK):
            return False

        try:
            os.rename(old_model_path, new_model_path)
            return True
        except Exception as e:
            logger.error(f"An error occurred during data migration: {str(e)}")
            return False

    def _check_cancelled(self):
        if self._cancel_event and self._cancel_event.is_set():
            raise DownloadCancelledError("Download cancelled by user")

    @staticmethod
    def _ensure_path_within_directory(path, directory):
        directory = pathlib.Path(directory).resolve()
        path = pathlib.Path(path).resolve()
        if path == directory or directory not in path.parents:
            raise ValueError(
                f"Model path must be within the model directory: {path}"
            )
        return str(path)

    @classmethod
    def _ensure_download_paths(cls, dest_path, directory):
        if directory is None:
            return dest_path, dest_path + ".part"
        dest_path = cls._ensure_path_within_directory(dest_path, directory)
        part_path = cls._ensure_path_within_directory(
            dest_path + ".part", directory
        )
        return dest_path, part_path

    @staticmethod
    def _describe_network_error(exc):
        """Turn a low-level download exception into something readable.

        Raw ``URLError`` text ("<urlopen error [Errno 11001] getaddrinfo
        failed>") tells the user nothing actionable, so map the common
        cases onto a short plain-language reason instead.
        """
        if isinstance(exc, HTTPError):
            code = getattr(exc, "code", None)
            if code == 403:
                return QCoreApplication.translate(
                    "Model", "access denied (HTTP 403)"
                )
            if code == 404:
                return QCoreApplication.translate(
                    "Model", "file not found on server (HTTP 404)"
                )
            if code is not None:
                return QCoreApplication.translate(
                    "Model", "server error (HTTP {code})"
                ).format(code=code)
        if isinstance(exc, socket.timeout):
            return QCoreApplication.translate("Model", "connection timed out")
        if isinstance(exc, URLError):
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, socket.timeout):
                return QCoreApplication.translate(
                    "Model", "connection timed out"
                )
            text = str(reason)
            lowered = text.lower()
            if "getaddrinfo" in lowered or "name or service" in lowered:
                return QCoreApplication.translate(
                    "Model", "could not resolve server address"
                )
            if "timed out" in lowered:
                return QCoreApplication.translate(
                    "Model", "connection timed out"
                )
            if "refused" in lowered:
                return QCoreApplication.translate(
                    "Model", "connection refused"
                )
            if "ssl" in lowered or "certificate" in lowered:
                return QCoreApplication.translate(
                    "Model", "SSL certificate error"
                )
            return QCoreApplication.translate(
                "Model", "network error: {detail}"
            ).format(detail=text[:80])
        if isinstance(exc, OSError):
            return QCoreApplication.translate(
                "Model", "network error: {detail}"
            ).format(detail=str(exc)[:80])
        return QCoreApplication.translate("Model", "unknown error")

    def download_with_retry(
        self, url, dest_path, progress_callback, model_directory=None
    ):
        """Download file with retry mechanism and cancellation support.

        Uses chunk-based downloading so the cancel flag can be checked
        between chunks, giving the user near-instant cancellation. A
        per-read socket timeout also bounds how long
        ``response.read()`` may block when the remote stays connected but
        stops sending bytes.
        """
        dest_path, part_path = self._ensure_download_paths(
            dest_path, model_directory
        )

        # Enforce a default socket timeout for the duration of the
        # download so a stalled stream cannot block indefinitely. We
        # restore the previous value when leaving this method.
        prev_socket_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self.DOWNLOAD_TIMEOUT)
        try:
            for attempt in range(self.MAX_RETRIES):
                try:
                    if attempt > 0:
                        logger.warning(
                            f"Retry attempt {attempt + 1}/{self.MAX_RETRIES}"
                        )
                    self._check_cancelled()

                    try:
                        host = urlparse(url).netloc
                    except Exception:  # noqa
                        host = ""
                    if attempt > 0:
                        self._emit_stage(
                            QCoreApplication.translate(
                                "Model",
                                "Retrying connection to {host} "
                                "(attempt {attempt}/{total})...",
                            ).format(
                                host=host or "server",
                                attempt=attempt + 1,
                                total=self.MAX_RETRIES,
                            )
                        )
                    else:
                        self._emit_stage(
                            QCoreApplication.translate(
                                "Model",
                                "Connecting to {host}...",
                            ).format(host=host or "server")
                        )

                    req = urllib.request.Request(url)
                    response = urllib.request.urlopen(
                        req, timeout=self.DOWNLOAD_TIMEOUT
                    )
                    # Apply per-read timeout to the now-open socket so a
                    # stalled stream is bounded (default-timeout only
                    # affects sockets created afterwards).
                    _set_response_socket_timeout(
                        response, self.DOWNLOAD_TIMEOUT
                    )
                    total_size = int(response.headers.get("Content-Length", 0))
                    downloaded = 0
                    if total_size > 0:
                        self._emit_stage(
                            QCoreApplication.translate(
                                "Model",
                                "Downloading {file_name} ({size_mb:.1f} MB)...",
                            ).format(
                                file_name=os.path.basename(dest_path),
                                size_mb=total_size / (1024 * 1024),
                            )
                        )
                    else:
                        self._emit_stage(
                            QCoreApplication.translate(
                                "Model",
                                "Downloading {file_name} "
                                "(size unknown)...",
                            ).format(file_name=os.path.basename(dest_path))
                        )

                    dest_path, part_path = self._ensure_download_paths(
                        dest_path, model_directory
                    )
                    with open(part_path, "wb") as f:
                        while True:
                            self._check_cancelled()
                            chunk = response.read(self.DOWNLOAD_CHUNK_SIZE)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback:
                                progress_callback(downloaded, total_size)

                    dest_path, part_path = self._ensure_download_paths(
                        dest_path, model_directory
                    )
                    os.replace(part_path, dest_path)
                    self._emit_stage(
                        QCoreApplication.translate(
                            "Model",
                            "Download completed: {file_name} ({size_mb:.1f} MB)",
                        ).format(
                            file_name=os.path.basename(dest_path),
                            size_mb=os.path.getsize(dest_path)
                            / (1024 * 1024),
                        )
                    )
                    return True

                except DownloadCancelledError:
                    if os.path.exists(part_path):
                        _, part_path = self._ensure_download_paths(
                            dest_path, model_directory
                        )
                        os.remove(part_path)
                    raise

                except (URLError, socket.timeout, OSError) as e:
                    if os.path.exists(part_path):
                        _, part_path = self._ensure_download_paths(
                            dest_path, model_directory
                        )
                        os.remove(part_path)
                    reason = self._describe_network_error(e)
                    delay = self.RETRY_DELAY * (attempt + 1)
                    if attempt < self.MAX_RETRIES - 1:
                        logger.warning(
                            f"Connection failed ({reason}), "
                            f"retrying in {delay}s... "
                            f"(Attempt {attempt + 1}/{self.MAX_RETRIES} failed)"
                        )
                        for remaining in range(delay, 0, -1):
                            self._emit_stage(
                                QCoreApplication.translate(
                                    "Model",
                                    "{reason}. Retrying in "
                                    "{remaining}s... "
                                    "(attempt {attempt}/{total})",
                                ).format(
                                    reason=reason,
                                    remaining=remaining,
                                    attempt=attempt + 1,
                                    total=self.MAX_RETRIES,
                                )
                            )
                            self._check_cancelled()
                            time.sleep(1)
                    else:
                        logger.warning(
                            f"All download attempts failed "
                            f"({self.MAX_RETRIES} tries)"
                        )
                        self._emit_stage(
                            QCoreApplication.translate(
                                "Model",
                                "Download failed: {reason}",
                            ).format(reason=reason)
                        )
                        raise e
        finally:
            socket.setdefaulttimeout(prev_socket_timeout)

    def get_model_abs_path(self, model_config, model_path_field_name):
        # Try getting model path from config folder
        model_path = model_config[model_path_field_name]

        # Model path is a local path
        if not model_path.startswith(("http://", "https://")):
            # Relative path to executable or absolute path?
            model_abs_path = os.path.abspath(model_path)
            if os.path.exists(model_abs_path):
                return model_abs_path

            # Relative path to config file?
            config_file_path = model_config["config_file"]
            config_folder = os.path.dirname(config_file_path)
            model_abs_path = os.path.abspath(
                os.path.join(config_folder, model_path)
            )
            if os.path.exists(model_abs_path):
                return model_abs_path

            raise QCoreApplication.translate(
                "Model", "Model path not found: {model_path}"
            ).format(model_path=model_path)

        # Build download url
        def get_filename_from_url(url):
            a = urlparse(url)
            return os.path.basename(a.path)

        filename = get_filename_from_url(model_path)
        download_url = model_path

        self._emit_stage(
            QCoreApplication.translate(
                "Model",
                "Preparing to download {file_name} from registry...",
            ).format(file_name=filename or "model")
        )

        # Continue with the rest of your function logic
        migrate_flag = self.allow_migrate_data()
        work_dir = get_work_directory()
        data_dir = "xanylabeling_data" if migrate_flag else "anylabeling_data"

        # Create model folder
        model_path = os.path.abspath(os.path.join(work_dir, data_dir))
        model_directory = os.path.join(model_path, "models")
        model_abs_path = self._ensure_path_within_directory(
            os.path.join(
                model_directory,
                model_config["name"],
                filename,
            ),
            model_directory,
        )
        if os.path.exists(model_abs_path):
            file_extension = os.path.splitext(model_abs_path)[1].lower()
            is_known_type = file_extension in (".onnx", ".pth", ".pt")
            is_valid = False

            if is_known_type:
                logger.info(f"Validating model integrity: {filename}")
                # Subprocess timeout must scale with file size: the checker
                # parses the whole file, and a fixed 30s timeout would kill
                # legitimate validation of large encoders (SAM2 Large is
                # ~1.2GB), misclassifying them as corrupted and triggering
                # an endless delete-redownload loop.
                size_mb = os.path.getsize(model_abs_path) / (1024 * 1024)
                check_timeout = max(30, min(300, int(size_mb)))
                is_valid = safe_check_model(
                    model_abs_path,
                    timeout=check_timeout,
                    on_stage=self._emit_stage,
                )
            elif os.path.getsize(model_abs_path) > 0:
                logger.info(
                    f"Model file exists and is not empty: {model_abs_path}"
                )
                is_valid = True

            if is_valid:
                logger.info(f"Model file is valid: {model_abs_path}")
                return model_abs_path
            else:
                logger.warning(
                    f"Model validation failed or file is empty: {model_abs_path}. Deleting and redownloading..."
                )
                try:
                    model_abs_path = self._ensure_path_within_directory(
                        model_abs_path, model_directory
                    )
                    os.remove(model_abs_path)
                    logger.info(
                        f"Model file {model_abs_path} deleted successfully"
                    )
                except Exception as e2:  # noqa
                    logger.error(f"Could not delete corrupted file: {str(e2)}")
        model_abs_path = self._ensure_path_within_directory(
            model_abs_path, model_directory
        )
        pathlib.Path(model_abs_path).parent.mkdir(parents=True, exist_ok=True)

        # Download url
        use_modelscope = False
        env_model_hub = os.getenv("XANYLABELING_MODEL_HUB")
        if env_model_hub == "modelscope":
            use_modelscope = True
        elif (
            env_model_hub is None or env_model_hub == ""
        ):  # Only check config if env var is not set or empty
            if self._config.get("model_hub") == "modelscope":
                use_modelscope = True
            # Fallback to language check only if model_hub is not 'modelscope'
            elif (
                self._config.get("model_hub") is None
                or self._config.get("model_hub") == ""
            ):
                if self._config.get("language") == "zh_CN":
                    use_modelscope = True

        if use_modelscope:
            model_type = model_config["name"].split("-")[0]
            model_name = os.path.basename(download_url)
            download_url = f"https://www.modelscope.cn/models/CVHub520/{model_type}/resolve/master/{model_name}"
            self._emit_stage(
                QCoreApplication.translate(
                    "Model", "Using mirror: ModelScope (China)"
                )
            )
        else:
            self._emit_stage(
                QCoreApplication.translate(
                    "Model", "Using source: GitHub releases"
                )
            )

        ellipsis_download_url = download_url
        if len(download_url) > 40:
            ellipsis_download_url = (
                download_url[:20] + "..." + download_url[-20:]
            )

        logger.info(f"Downloading {download_url} to {model_abs_path}")
        try:

            def _progress(downloaded, total_size):
                # Throttle UI updates, but never let the UI look frozen:
                # emit when either ~1s has elapsed OR ~1MB has arrived, and
                # always emit on the very first chunk so the user sees the
                # download actually started (previously a slow first megabyte
                # left the status stuck on "Downloading model from registry").
                now = time.monotonic()
                if not hasattr(_progress, "_last_bytes"):
                    _progress._last_bytes = 0
                    _progress._last_time = 0.0
                if _progress._last_time:
                    enough_bytes = (
                        downloaded - _progress._last_bytes >= 1024 * 1024
                    )
                    enough_time = now - _progress._last_time >= 1.0
                    if not (enough_bytes or enough_time):
                        return
                _progress._last_bytes = downloaded
                _progress._last_time = now

                # Always drive the progress bar, even when the server gave
                # no Content-Length (total_size <= 0 -> marquee mode).
                if self._on_progress:
                    self._on_progress(downloaded, total_size)

                if total_size <= 0:
                    # No percentage available; still tell the user bytes are
                    # flowing so the label is not frozen.
                    self._emit_stage(
                        QCoreApplication.translate(
                            "Model",
                            "Downloading {download_url}: "
                            "{downloaded_mb:.1f} MB received...",
                        ).format(
                            download_url=ellipsis_download_url,
                            downloaded_mb=downloaded / (1024 * 1024),
                        )
                    )
                    return

                percent = int(downloaded * 100 / total_size)
                downloaded_mb = downloaded / (1024 * 1024)
                total_mb = total_size / (1024 * 1024)
                self._emit_stage(
                    QCoreApplication.translate(
                        "Model",
                        "Downloading {download_url}: {percent}% "
                        "({downloaded_mb:.1f}/{total_mb:.1f} MB)",
                    ).format(
                        download_url=ellipsis_download_url,
                        percent=percent,
                        downloaded_mb=downloaded_mb,
                        total_mb=total_mb,
                    )
                )

            model_abs_path = self._ensure_path_within_directory(
                model_abs_path, model_directory
            )
            self.download_with_retry(
                download_url,
                model_abs_path,
                _progress,
                model_directory=model_directory,
            )

        except DownloadCancelledError:
            raise

        except Exception as e:  # noqa
            logger.error(
                f"Could not download {download_url}: {e}, "
                "you can try to download it manually."
            )
            reason = self._describe_network_error(e)
            self._emit_stage(
                QCoreApplication.translate(
                    "Model",
                    "Download failed: {reason}. "
                    "You can download it manually from: {url}",
                ).format(reason=reason, url=ellipsis_download_url)
            )
            time.sleep(1)
            raise Exception(
                QCoreApplication.translate(
                    "Model",
                    "Could not download model: {url}. Reason: {reason}",
                ).format(url=ellipsis_download_url, reason=reason)
            ) from e

        return model_abs_path

    def check_missing_config(self, config_names, config):
        """
        Check if config has all required config names
        """
        for name in config_names:
            if name not in config:
                raise Exception(f"Missing config: {name}")

    @abstractmethod
    def predict_shapes(self, image, filename=None) -> AutoLabelingResult:
        """
        Predict image and return AnyLabeling shapes
        """
        raise NotImplementedError

    @abstractmethod
    def unload(self):
        """
        Unload memory
        """
        raise NotImplementedError

    @staticmethod
    def load_image_from_filename(filename):
        """Load image from labeling file and return image data and image path."""
        label_file = os.path.splitext(filename)[0] + ".json"
        if QFile.exists(label_file) and LabelFile.is_label_file(label_file):
            try:
                label_file = LabelFile(label_file)
            except LabelFileError as e:
                logger.error("Error reading {}: {}".format(label_file, e))
                return None, None
            image_data = label_file.image_data
        else:
            image_data = LabelFile.load_image_file(filename)
        image = utils.img_data_to_qimage(image_data, filename)
        if image.isNull():
            logger.error("Error reading {}".format(filename))
        return image

    def on_next_files_changed(self, next_files):
        """
        Handle next files changed. This function can preload next files
        and run inference to save time later.
        """
        pass

    def set_output_mode(self, mode):
        """
        Set output mode
        """
        self.output_mode = mode