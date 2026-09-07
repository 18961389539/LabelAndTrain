import json
import logging
import os
import queue
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import threading
import traceback
from io import StringIO
from pathlib import Path
from typing import Dict, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

from anylabeling.config import get_work_directory

from .config import get_settings_config_path, get_trainer_root_dir

TRAINING_WORKER_EVENT_PREFIX = "__XANYLABELING_TRAIN_EVENT__="


class TrainingEventRedirector(QObject):
    """Thread-safe training event redirector"""

    training_event_signal = pyqtSignal(str, dict)

    def __init__(self):
        super().__init__()

    def emit_training_event(self, event_type, data):
        """Safely emit training events from child thread to main thread"""
        self.training_event_signal.emit(event_type, data)


class TrainingLogRedirector(QObject):
    """Thread-safe training log redirector"""

    log_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.log_stream = StringIO()

    def write(self, text):
        """Write text to log stream and emit signal if not empty"""
        if text.strip():
            self.log_signal.emit(text)

    def flush(self):
        """Flush the log stream"""
        pass


class TrainingManager:
    def __init__(self):
        self.training_process = None
        self.is_training = False
        self.callbacks = []
        self.total_epochs = 100
        self.stop_event = threading.Event()

    def notify_callbacks(self, event_type: str, data: dict):
        for callback in self.callbacks:
            try:
                callback(event_type, data)
            except Exception:
                pass

    def start_training(self, train_args: Dict) -> Tuple[bool, str]:
        if self.is_training:
            return False, "Training is already in progress"

        try:
            self.total_epochs = train_args.get("epochs", 100)
            self.stop_event.clear()
            self.is_training = True
            payload_path = create_training_payload(train_args)

            def run_training():
                try:
                    self.notify_callbacks(
                        "training_started", {"total_epochs": self.total_epochs}
                    )
                    creationflags = 0
                    if os.name == "nt" and hasattr(
                        subprocess, "CREATE_NEW_PROCESS_GROUP"
                    ):
                        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

                    self.training_process = subprocess.Popen(
                        build_training_worker_command(payload_path),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        bufsize=1,
                        env=build_training_worker_env(),
                        preexec_fn=os.setsid if os.name != "nt" else None,
                        creationflags=creationflags,
                    )
                    terminal_event_seen = False

                    # Read child output on a dedicated thread so that the
                    # stop check below never blocks on readline() while the
                    # worker is silent (e.g. during long validation phases).
                    output_queue: queue.Queue = queue.Queue()

                    def read_output(process=self.training_process):
                        try:
                            for line in process.stdout:
                                output_queue.put(line)
                        finally:
                            output_queue.put(None)

                    reader_thread = threading.Thread(
                        target=read_output, daemon=True
                    )
                    reader_thread.start()

                    while True:
                        if self.stop_event.is_set():
                            self.training_process.terminate()
                            try:
                                self.training_process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                kill_training_process_tree(
                                    self.training_process
                                )
                            self.is_training = False
                            self.notify_callbacks("training_stopped", {})
                            return

                        try:
                            output = output_queue.get(timeout=0.2)
                        except queue.Empty:
                            continue
                        if output is None:
                            break

                        if handle_training_worker_output(
                            output,
                            self.notify_callbacks,
                        ):
                            terminal_event_seen = True

                    return_code = self.training_process.poll()
                    self.is_training = False

                    if terminal_event_seen:
                        return

                    if return_code == 0:
                        self.notify_callbacks(
                            "training_completed",
                            {"results": "Training completed successfully"},
                        )
                    else:
                        self.notify_callbacks(
                            "training_error",
                            {
                                "error": f"Training process exited with code {return_code}"
                            },
                        )

                except Exception as e:
                    self.is_training = False
                    self.notify_callbacks("training_error", {"error": str(e)})
                finally:
                    try:
                        os.remove(payload_path)
                    except OSError:
                        pass

            def save_settings_config():
                save_path = os.path.join(
                    train_args["project"], train_args["name"]
                )
                save_file = os.path.join(save_path, "settings.json")

                while (
                    self.is_training
                    and not self.stop_event.is_set()
                    and not os.path.exists(save_path)
                ):
                    time.sleep(1)

                if os.path.exists(save_path):
                    shutil.copy2(get_settings_config_path(), save_file)

            training_thread = threading.Thread(target=run_training)
            training_thread.daemon = True
            training_thread.start()

            config_thread = threading.Thread(target=save_settings_config)
            config_thread.daemon = True
            config_thread.start()

            return True, "Training started successfully"

        except Exception as e:
            return False, f"Failed to start training: {str(e)}"

    def start_training_mp(self, train_args: Dict) -> Tuple[bool, str]:
        return self.start_training(train_args)

    def stop_training(self) -> bool:
        if not self.is_training:
            return False

        try:
            self.stop_event.set()
            return True
        except Exception:
            return False


class TrainingWorkerLogStream:
    def __init__(self, output_stream):
        self._buffer = ""
        self._output_stream = output_stream

    def write(self, text):
        if not text:
            return

        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if line:
                emit_training_worker_event(
                    "training_log",
                    message=line,
                    output_stream=self._output_stream,
                )

    def flush(self):
        line = self._buffer.strip()
        if line:
            emit_training_worker_event(
                "training_log",
                message=line,
                output_stream=self._output_stream,
            )
        self._buffer = ""


def build_training_worker_env():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def build_training_worker_command(payload_path: str):
    command = [sys.executable]
    if getattr(sys, "frozen", False):
        command.extend(
            [
                "--work-dir",
                get_work_directory(),
                "train-worker",
                "--payload",
                payload_path,
            ]
        )
        return command

    command.extend(
        [
            "-m",
            "anylabeling.app",
            "--work-dir",
            get_work_directory(),
            "train-worker",
            "--payload",
            payload_path,
        ]
    )
    return command


def create_training_payload(train_args: Dict) -> str:
    payload_train_args = dict(train_args)
    payload_train_args["model"] = resolve_training_model_path(
        payload_train_args["model"]
    )
    fd, payload_path = tempfile.mkstemp(
        prefix="xanylabeling-train-", suffix=".json"
    )
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload_train_args, f, ensure_ascii=False)
    return payload_path


def emit_training_worker_event(event_type: str, output_stream=None, **data):
    payload = {"event": event_type}
    payload.update(data)
    stream = output_stream or sys.__stdout__ or sys.stdout
    stream.write(
        f"{TRAINING_WORKER_EVENT_PREFIX}"
        f"{json.dumps(payload, ensure_ascii=False)}\n"
    )
    stream.flush()


def handle_training_worker_output(output: str, notify_callbacks) -> bool:
    cleaned_output = output.strip()
    if not cleaned_output:
        return False

    if not cleaned_output.startswith(TRAINING_WORKER_EVENT_PREFIX):
        notify_callbacks("training_log", {"message": cleaned_output})
        return False

    payload_text = cleaned_output[len(TRAINING_WORKER_EVENT_PREFIX) :]
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        notify_callbacks("training_log", {"message": cleaned_output})
        return False

    event_type = payload.pop("event", "")
    if not event_type:
        return False

    notify_callbacks(event_type, payload)
    return event_type in {"training_completed", "training_error"}


def kill_training_process_tree(training_process):
    if training_process is None:
        return

    try:
        if os.name == "nt":
            subprocess.run(
                [
                    "taskkill",
                    "/F",
                    "/T",
                    "/PID",
                    str(training_process.pid),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return

        os.killpg(os.getpgid(training_process.pid), signal.SIGKILL)
    except OSError:
        pass


def get_training_weights_dir() -> str:
    return os.path.join(get_trainer_root_dir(), "weights")


# ---------------------------------------------------------------------------
# ModelScope-first pretrained weight download (train-side)
#
# Auto-labeling model downloads already default to ModelScope
# (services/auto_labeling/model.py). This block gives the *training* weights
# (ultralytics .pt pulled via attempt_download_asset, which defaults to
# github.com/ultralytics/assets) the same ModelScope-first behaviour.
#
# Verified on 2026-09-02 via the ModelScope file API (repos below mirror the
# official weights at repo root):
#   - AI-ModelScope/YOLOv8  -> yolov8{n,s,m,l,x}.pt (det only)
#   - AI-ModelScope/YOLO11  -> yolo11{n,s,m,l,x}.pt + -seg/-pose/-obb/-cls
#   - AI-ModelScope/YOLO26  -> does NOT exist yet; yolo26* falls back to the
#                              official ultralytics source.
# ---------------------------------------------------------------------------
MODELSCOPE_TRAINING_REPOS = {
    "yolov8": "AI-ModelScope/YOLOv8",
    "yolo11": "AI-ModelScope/YOLO11",
}

_MODELSCOPE_URL_TEMPLATE = (
    "https://www.modelscope.cn/models/{repo}/resolve/master/{file_name}"
)


def _hub_prefers_modelscope() -> bool:
    """Mirror the auto-labeling downloader decision (model_hub config/env)."""
    env_model_hub = os.getenv("XANYLABELING_MODEL_HUB")
    if env_model_hub == "modelscope":
        return True
    if env_model_hub == "github":
        return False

    from anylabeling.config import get_config

    cfg = get_config()
    hub = cfg.get("model_hub")
    if hub == "modelscope":
        return True
    if hub in (None, ""):
        return cfg.get("language") == "zh_CN"
    return False


def _modelscope_training_url(model_name: str):
    """Return the ModelScope download URL for ``model_name`` or None."""
    file_name = os.path.basename(model_name)
    lower_name = file_name.lower()
    for prefix, repo in MODELSCOPE_TRAINING_REPOS.items():
        if lower_name.startswith(prefix):
            return _MODELSCOPE_URL_TEMPLATE.format(
                repo=repo, file_name=file_name
            )
    return None


def _download_file(url: str, dest: str) -> bool:
    """Download ``url`` into ``dest`` (atomic via temp + replace).

    Returns True on success. Never raises for network errors; on failure a
    partial file is cleaned up so the caller can fall back to another source.
    """
    import urllib.request

    tmp_dest = f"{dest}.part"
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (X-AnyLabeling)"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or 0)
            with open(tmp_dest, "wb") as out:
                downloaded = 0
                last_reported = 0
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    if (
                        total > 0
                        and downloaded - last_reported >= 4 * 1024 * 1024
                    ):
                        last_reported = downloaded
                        logging.getLogger(__name__).info(
                            "Downloading from ModelScope: "
                            f"{downloaded * 100 // total}% ({url})"
                        )
        # Sanity: ultralytics .pt weights are zip archives starting with PK.
        with open(tmp_dest, "rb") as check:
            if check.read(2) != b"PK":
                raise OSError("downloaded weight is not a valid torch archive")
        os.replace(tmp_dest, dest)
        return True
    except Exception as e:  # noqa: BLE001
        logging.getLogger(__name__).warning(
            f"ModelScope download failed for {url}: {e}. "
            "Falling back to the official source."
        )
        try:
            if os.path.exists(tmp_dest):
                os.remove(tmp_dest)
        except OSError:
            pass
        return False


def _try_download_modelscope(cached_model_path: Path) -> bool:
    """Try ModelScope for the weight at ``cached_model_path``."""
    url = _modelscope_training_url(cached_model_path.name)
    if not url:
        return False
    logging.getLogger(__name__).info(
        f"Downloading pretrained weight from ModelScope: {url}"
    )
    return _download_file(url, str(cached_model_path))


def _fallback_official_download(cached_model_path: Path) -> str:
    """Download through ultralytics official assets (github)."""
    from ultralytics.utils.downloads import attempt_download_asset

    return attempt_download_asset(str(cached_model_path))


def resolve_training_model_path(model):
    if not isinstance(model, str):
        return model

    model_path = Path(model)
    if (
        model.startswith(("http://", "https://"))
        or model_path.is_absolute()
        or model_path.parent != Path(".")
        or model_path.suffix.lower() != ".pt"
    ):
        return model

    weights_dir = Path(get_training_weights_dir())
    weights_dir.mkdir(parents=True, exist_ok=True)
    cached_model_path = weights_dir / model_path.name
    if cached_model_path.exists():
        return str(cached_model_path)

    # ModelScope first (when enabled); ultralytics official as fallback.
    if _hub_prefers_modelscope() and _try_download_modelscope(
        cached_model_path
    ):
        return str(cached_model_path)

    return _fallback_official_download(cached_model_path)


def run_training_worker_command(args):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    with open(args.payload, "r", encoding="utf-8") as f:
        train_args = json.load(f)

    old_stdout = sys.stdout
    old_stderr = sys.stderr
    log_stream = TrainingWorkerLogStream(old_stdout)

    try:
        sys.stdout = log_stream
        sys.stderr = log_stream

        import matplotlib

        matplotlib.use("Agg")

        from ultralytics import YOLO

        model = YOLO(train_args.pop("model"))
        train_args["verbose"] = False
        train_args["show"] = False
        model.train(**train_args)
    except Exception as e:
        log_stream.flush()
        emit_training_worker_event(
            "training_error",
            error=str(e),
            traceback=traceback.format_exc(),
            output_stream=old_stdout,
        )
        raise SystemExit(1) from e
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    emit_training_worker_event(
        "training_completed",
        results="Training completed successfully",
        output_stream=old_stdout,
    )


_training_manager = TrainingManager()


def get_training_manager() -> TrainingManager:
    return _training_manager
