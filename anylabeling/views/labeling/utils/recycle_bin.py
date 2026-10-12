"""把文件或目录送进系统回收站 —— 本应用里删除数据的唯一通道。

``shutil.rmtree`` 不进回收站，而"删除项目"按错一次就是几个小时的标注。
回收站让这一步**可恢复**：这是防静默数据丢失在删除路径上的落点，不是
锦上添花。

Windows 用 shell 的 ``SHFileOperationW``（``FOF_ALLOWUNDO``，零依赖）；
其他平台返回失败而**绝不退化成 rmtree** —— 调用方收到 False 后应该
提示手动处理，而不是换一条不可恢复的路把同一件事做掉。
"""

from __future__ import annotations

import ctypes
import os
import sys

#: FOF_ALLOWUNDO（进回收站）| FOF_NOCONFIRMATION（确认由应用自己做）
#: | FOF_SILENT | FOF_NOERRORUI（失败走应用的提示，不走系统弹窗）。
_FOF_FLAGS = 0x40 | 0x10 | 0x4 | 0x400
_FO_DELETE = 3


def send_to_recycle_bin(path, _operation=None):
    """Send ``path`` (a file or a directory) to the recycle bin.

    Returns True when the shell reported success, False when it failed,
    was aborted, the path does not exist, or the platform offers no
    recycle-bin channel. False always means "nothing was deleted through
    this call" — the caller must treat it as a refusal, not a fallback
    trigger.
    """
    if not path or not os.path.exists(str(path)):
        return False
    operation = _operation or _windows_recycle_operation()
    if operation is None:
        return False
    return bool(operation(os.path.abspath(str(path))))


def _windows_recycle_operation():
    """The shell operation for Windows, or ``None`` elsewhere."""
    if sys.platform != "win32":
        return None

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", ctypes.c_int),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    def operation(abspath):
        # SHFileOperationW 的 pFrom 是双 NUL 结尾的路径列表；
        # c_wchar_p 只带一个，追加一个显式的。
        buffer = ctypes.create_unicode_buffer(abspath + "\0")
        op = SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = _FO_DELETE
        op.pFrom = ctypes.cast(buffer, ctypes.c_wchar_p)
        op.pTo = None
        op.fFlags = _FOF_FLAGS
        code = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        return code == 0 and not op.fAnyOperationsAborted

    return operation
