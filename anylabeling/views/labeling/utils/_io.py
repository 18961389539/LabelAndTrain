import contextlib
import io
import json
import os
import tempfile
import time


@contextlib.contextmanager
def io_open(name, mode):
    assert mode in ["r", "w"]
    encoding = "utf-8"
    yield io.open(name, mode, encoding=encoding)


def load_json(file_path: str) -> dict:
    """Load a JSON file encoded in UTF-8.

    Args:
        file_path: Path of the JSON file to read.

    Returns:
        The decoded JSON document.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _is_windows_lock_error(exc: BaseException) -> bool:
    """Return True if exc looks like a Windows file lock / access denied."""
    if isinstance(exc, PermissionError):
        return True
    winerror = getattr(exc, "winerror", None)
    if winerror == 5:
        return True
    errno = getattr(exc, "errno", None)
    if errno in (5, 13):
        return True
    return False


def safe_replace(src: str, dst: str, attempts: int = 5, delay: float = 0.15):
    """Atomically replace ``dst`` with ``src``, retrying transient locks.

    On Windows the destination file may be temporarily held by antivirus,
    OneDrive/ShareFile sync, search indexer, or a stale handle from a
    previous app instance. ``os.replace`` then raises
    ``PermissionError`` / ``OSError(WinError 5)`` and the save dialog
    would bubble a raw error to the user. Retry with a short backoff so
    normal transient holds self-heal; only fail after the full budget is
    spent, with an actionable hint.
    """
    last_exc: BaseException | None = None
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except (PermissionError, OSError) as exc:
            if not _is_windows_lock_error(exc):
                raise
            last_exc = exc
            time.sleep(delay * (i + 1))
    raise OSError(
        f"无法替换目标文件 {dst}：连续 {attempts} 次因访问被拒绝失败，"
        f"常见原因：目标文件被其他程序锁定（杀软/OneDrive/ShareFile/搜索"
        f"索引器/残留进程），或目标目录对该用户不可写。请先关闭占用方后"
        f"重试。最后错误: {last_exc}"
    ) from last_exc


def save_json(data: dict, file_path: str):
    """Atomically write ``data`` as JSON.

    The payload is written to a temporary file in the destination
    directory and then moved into place, so a crash mid-write cannot
    leave a truncated configuration file behind.

    Args:
        data: JSON-serializable payload.
        file_path: Destination path. Parent directories are created.
    """
    directory = os.path.dirname(os.path.abspath(file_path))
    os.makedirs(directory, exist_ok=True)
    temporary_file = None
    try:
        fd, temporary_file = tempfile.mkstemp(
            prefix=".xal_", suffix=".tmp", dir=directory
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        safe_replace(temporary_file, file_path)
    finally:
        if temporary_file and os.path.exists(temporary_file):
            try:
                os.remove(temporary_file)
            except OSError:
                pass
