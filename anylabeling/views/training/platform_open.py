"""Opening a file or folder in the system's own tool, once for this module.

The training dialog and the image preview both need this, and the WSL2 path
translation is fiddly enough that one copy is the right number: a second copy
is how the two drift apart.
"""

import os
import platform
import subprocess

from anylabeling.views.labeling.logger import logger


def _is_wsl2():
    try:
        return (
            hasattr(os, "uname") and "microsoft" in os.uname().release.lower()
        )
    except (AttributeError, OSError):
        return False


def open_path(path):
    """Hand ``path`` to the desktop's default application.

    Returns True when the command was dispatched; failures are logged rather
    than raised, since "nothing happened" is the worst outcome to debug.
    """
    try:
        if _is_wsl2():
            windows_path = (
                subprocess.check_output(["wslpath", "-w", path])
                .decode()
                .strip()
            )
            subprocess.run(
                ["powershell.exe", "-c", f"Start-Process {windows_path!r}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif os.name == "nt":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Failed to open {path}: {e}")
        return False
