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
import os.path as osp
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


def _shell_success(code, aborted, abspath):
    """Whether the operation really moved ``abspath`` out of the way.

    ``code == 0`` is the normal success. But the shell has been
    observed returning ``DE_INVALIDFILES`` (2) **after a successful
    recycle** on one machine's system drive -- the entries land in the
    bin and the code still says 2. The only truth that matters here is
    the one the caller cares about: did the path leave the disk? An
    operation that moved it counts as success; one that left it in
    place (with any nonzero code) is a refusal.
    """
    if aborted:
        return False
    return code == 0 or not osp.exists(abspath)


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

    def drive_type_of(abspath):
        return ctypes.windll.kernel32.GetDriveTypeW(
            ctypes.c_wchar_p(osp.splitdrive(abspath)[0] + "\\")
        )

    def operation(abspath, _drive_type_of=drive_type_of):
        # FOF_ALLOWUNDO 只在**有回收站的卷**上进回收站；网络盘、RAM 盘
        # 这些没有回收站的卷上，同一个调用会**直接永久删除** —— 恰好是
        # 本模块承诺过绝不发生的事。这类卷一律拒绝，让调用方走"手动
        # 处理"的提示，而不是换一条不可恢复的路把同一件事做掉。
        # DRIVE_FIXED(3) 与 DRIVE_REMOVABLE(2) 有回收站；其余不算。
        if _drive_type_of(abspath) not in (2, 3):
            return False
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
        return _shell_success(code, op.fAnyOperationsAborted, abspath)

    return operation
