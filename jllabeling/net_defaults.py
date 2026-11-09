"""One place for the network defaults used by model and weight downloads.

The same "how long do we wait for the network" decision used to be made in
four files with four different answers: a 240s global socket timeout and a
30s per-attempt download timeout in ``auto_labeling/model.py``, a 60s weight
download in ``auto_training/ultralytics/trainer.py``, and a 300s pip install
in ``validators.py``. On a restricted or offline machine that meant minutes
of hanging with no explanation.

Everything now reads from here. Each value can be overridden with an
environment variable, and ``JLLABELING_OFFLINE=1`` turns any download into an
immediate, explicit error instead of a long timeout.
"""

import os

#: Global socket default. Only affects sockets created after it is set.
DEFAULT_SOCKET_TIMEOUT = 240
#: Per-attempt connect/read timeout for a model download.
DOWNLOAD_TIMEOUT = 30
DOWNLOAD_MAX_RETRIES = 2
DOWNLOAD_RETRY_DELAY = 3  # seconds, multiplied by the attempt number
DOWNLOAD_CHUNK_SIZE = 64 * 1024
#: Pretrained weight download (larger files, single attempt).
WEIGHTS_DOWNLOAD_TIMEOUT = 60
WEIGHTS_CHUNK_SIZE = 256 * 1024
#: Installing optional export dependencies.
INSTALL_TIMEOUT = 300
#: Subprocess sanity check on a .pt/.pth weight file.
MODEL_CHECK_TIMEOUT = 30
#: Waiting for a worker process / thread to stop.
PROCESS_WAIT_TIMEOUT = 5

_TRUE_VALUES = {"1", "true", "yes", "on"}


class OfflineMode(RuntimeError):
    """Raised when a download is requested while offline mode is on."""


def _env_int(name, default, minimum=1, maximum=3600):
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def socket_timeout():
    return _env_int("JLLABELING_SOCKET_TIMEOUT", DEFAULT_SOCKET_TIMEOUT)


def download_timeout():
    return _env_int("JLLABELING_DOWNLOAD_TIMEOUT", DOWNLOAD_TIMEOUT)


def max_retries():
    return _env_int("JLLABELING_DOWNLOAD_RETRIES", DOWNLOAD_MAX_RETRIES)


def retry_delay():
    return _env_int("JLLABELING_DOWNLOAD_RETRY_DELAY", DOWNLOAD_RETRY_DELAY)


def chunk_size():
    return _env_int("JLLABELING_DOWNLOAD_CHUNK_SIZE", DOWNLOAD_CHUNK_SIZE)


def weights_timeout():
    return _env_int("JLLABELING_WEIGHTS_TIMEOUT", WEIGHTS_DOWNLOAD_TIMEOUT)


def weights_chunk_size():
    return _env_int("JLLABELING_WEIGHTS_CHUNK_SIZE", WEIGHTS_CHUNK_SIZE)


def install_timeout():
    return _env_int("JLLABELING_INSTALL_TIMEOUT", INSTALL_TIMEOUT)


def model_check_timeout():
    return _env_int("JLLABELING_MODEL_CHECK_TIMEOUT", MODEL_CHECK_TIMEOUT)


def process_wait_timeout():
    return _env_int("JLLABELING_PROCESS_WAIT_TIMEOUT", PROCESS_WAIT_TIMEOUT)


def is_offline():
    return os.getenv("JLLABELING_OFFLINE", "").strip().lower() in _TRUE_VALUES


def ensure_online(operation):
    """Fail fast with a readable message instead of waiting for a timeout.

    Call this at the very start of a download. The message tells the user
    both why nothing happened and how to bring the file in by hand.
    """
    if is_offline():
        raise OfflineMode(
            f"{operation} needs a network download, but offline mode is on "
            "(JLLABELING_OFFLINE=1). Place the weight/model file in the "
            "application data directory, or unset the variable and retry."
        )
