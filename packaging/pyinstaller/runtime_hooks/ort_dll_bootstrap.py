import os
import sys

# torch ships its own libiomp5md.dll; when the frozen GUI later imports torch
# (training checks at dialog import time) alongside PySide6's OpenMP runtime,
# duplicate copies crash the process unless this flag is set early.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

_HANDLES = []


def configure_ort_dll_search_path():
    if sys.platform != "win32" or not hasattr(sys, "_MEIPASS"):
        return

    base_dir = sys._MEIPASS
    search_dirs = [os.path.join(base_dir, "onnxruntime", "capi"), base_dir]
    valid_dirs = [
        directory for directory in search_dirs if os.path.isdir(directory)
    ]

    if hasattr(os, "add_dll_directory"):
        for directory in valid_dirs:
            _HANDLES.append(os.add_dll_directory(directory))

    path_value = os.environ.get("PATH", "")
    path_parts = [part for part in path_value.split(os.pathsep) if part]
    existing = {os.path.normcase(os.path.abspath(part)) for part in path_parts}
    extra_dirs = [
        directory
        for directory in valid_dirs
        if os.path.normcase(os.path.abspath(directory)) not in existing
    ]
    if not extra_dirs:
        return
    os.environ["PATH"] = os.pathsep.join(extra_dirs + path_parts)


configure_ort_dll_search_path()
