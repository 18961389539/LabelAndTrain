"""项目包：整个项目打成 zip，或从 zip 还原成项目。

"项目跟着数据走"的第一原则（``.jllabel/project.json`` 就在数据旁边）
让打包变得几乎免费：把数据集目录原样进包，项目就迁移完成了。本模块
只做三件事——

* :func:`export_bundle` 整目录进包（顶层是项目文件夹名，相对路径存档）；
* :func:`inspect_bundle` 不解包先看一眼：顶层是什么、清单里记了什么；
* :func:`import_bundle` 解包到指定父目录，**逐条目防 zip-slip**——
  归档名解析出的路径必须落在目标目录内，越界即整体拒绝（不是跳过：
  一半恶意条目被跳过、另一半落盘，比整体失败更糟）。

进度用回调而不是线程：打包/解包是文件级操作，回调驱动 ``QProgressDialog``
就够用；纯逻辑不依赖 Qt，测试直接驱动回调。
"""

from __future__ import annotations

import json
import os
import os.path as osp
import zipfile

from anylabeling.views.labeling.project import PROJECT_DIR_NAME

#: 包内清单的固定位置（顶层目录名在运行时才知道）。
_RECORD_ARC_TAIL = (PROJECT_DIR_NAME, "project.json")


def _iter_files(root):
    """Every regular file under ``root``, as ``(abs_path, rel_path)``."""
    root = osp.normpath(str(root))
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            abs_path = osp.join(dirpath, name)
            if not osp.isfile(abs_path):
                continue
            rel = osp.relpath(abs_path, root)
            yield abs_path, rel


def export_bundle(root, zip_path, progress=None, cancel=None):
    """Pack the whole project folder into ``zip_path``.

    Arcnames are ``<folder name>/<relative path>`` so extraction lands in
    one directory no matter where it is unpacked. Entries are stored
    (``ZIP_STORED``): the payload is images, which deflate cannot shrink,
    so compression would only burn minutes on a many-GB folder.

    ``progress(done, total, name)`` and ``cancel()`` are optional; a
    cancelled export removes the half-written archive — a partial zip
    that pretends to be a project is worse than no zip. Returns the
    counts ``{"files", "bytes", "skipped"}`` (``skipped`` lists paths
    that vanished mid-walk or refused to be read); raises ``OSError``
    when the archive itself cannot be written.
    """
    root = osp.normpath(str(root))
    zip_path = osp.normpath(str(zip_path))
    if not osp.isdir(root):
        raise OSError(f"not a directory: {root}")
    top = osp.basename(root)

    members = [
        (abs_path, rel)
        for abs_path, rel in _iter_files(root)
        if osp.normpath(abs_path) != osp.normpath(zip_path)
    ]
    total = len(members)
    done = 0
    files = 0
    bytes_written = 0
    skipped = []
    with zipfile.ZipFile(zip_path, "w", allowZip64=True) as bundle:
        for abs_path, rel in members:
            if cancel is not None and cancel():
                bundle.close()
                try:
                    os.remove(zip_path)
                except OSError:
                    pass
                return {
                    "files": 0,
                    "bytes": 0,
                    "skipped": [],
                    "cancelled": True,
                }
            arcname = "/".join((top,) + tuple(osp.normpath(rel).split(os.sep)))
            try:
                bundle.write(abs_path, arcname)
            except OSError:
                skipped.append(abs_path)
                continue
            files += 1
            bytes_written += osp.getsize(abs_path)
            done += 1
            if progress is not None:
                progress(done, total, rel)
    return {"files": files, "bytes": bytes_written, "skipped": skipped}


def _top_entries(names):
    """Distinct first path components of the archive's entries."""
    tops = set()
    for name in names:
        parts = name.replace("\\", "/").split("/", 1)
        if len(parts) == 2 and parts[1]:
            tops.add(parts[0])
    return tops


def _record_from_bundle(bundle, top):
    """The project record stored in the bundle, or ``{}``."""
    arcname = "/".join((top,) + _RECORD_ARC_TAIL)
    try:
        with bundle.open(arcname) as handle:
            data = json.loads(handle.read().decode("utf-8"))
    except (KeyError, OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def inspect_bundle(zip_path):
    """Peek inside without unpacking: ``{"top", "record", "entries"}``.

    ``top`` is ``None`` for anything that is not a single-folder archive
    (a flat zip, a multi-project zip), which callers must refuse. A
    bundle whose record is missing or damaged still comes back — with an
    empty ``record`` — so a zipped folder that was merely opened can be
    identified as "no project record" rather than rejected as garbage.
    """
    zip_path = str(zip_path)
    if not osp.isfile(zip_path):
        return None
    try:
        with zipfile.ZipFile(zip_path) as bundle:
            names = bundle.namelist()
            tops = _top_entries(names)
            if len(tops) != 1:
                return {"top": None, "record": {}, "entries": len(names)}
            top = tops.pop()
            record = _record_from_bundle(bundle, top)
            return {
                "top": top,
                "record": record,
                "entries": len(names),
            }
    except (OSError, zipfile.BadZipFile):
        return None


def _safe_target(target_dir, arcname):
    """Where ``arcname`` lands, refusing anything outside ``target_dir``.

    The zip-slip guard, decided on the *components* rather than on the
    joined path: ``normpath`` would quietly digest ``plates/../x`` into
    ``x``, letting an entry hop out of the project folder while staying
    inside the extraction root. Any ``..`` component, absolute path or
    Windows drive anchor therefore ends the whole import — an archive is
    untrusted input, and one skipped-then-escaped file is worse than a
    clean failure.
    """
    parts = str(arcname).replace("\\", "/").split("/")
    if not parts or parts[0] == "" or osp.isabs(str(arcname)):
        raise ValueError(f"unsafe entry in project bundle: {arcname}")
    for part in parts:
        if part in ("..", "") or (len(part) > 1 and part[1] == ":"):
            raise ValueError(f"unsafe entry in project bundle: {arcname}")
    target = osp.normpath(osp.join(str(target_dir), *parts))
    base = osp.normpath(str(target_dir))
    if target != base and not target.startswith(base + os.sep):
        raise ValueError(f"unsafe entry in project bundle: {arcname}")
    return target


def import_bundle(zip_path, parent_dir, progress=None, cancel=None):
    """Unpack a project bundle under ``parent_dir``; returns the project root.

    Refuses anything that is not a single-folder bundle (see
    :func:`inspect_bundle`), a target that already exists, and any entry
    that escapes the target. Progress and cancellation mirror
    :func:`export_bundle`; a cancelled import removes what it wrote.
    """
    info = inspect_bundle(zip_path)
    if not info or not info["top"]:
        raise ValueError("not a single-folder project bundle")
    top = info["top"]
    target = osp.normpath(osp.join(str(parent_dir), top))
    if osp.exists(target):
        raise ValueError(f"target already exists: {target}")

    with zipfile.ZipFile(str(zip_path)) as bundle:
        entries = [
            name for name in bundle.namelist() if not name.endswith("/")
        ]
        # 先全量校验、后写一个字节：整体拒绝必须真的是整体 —— 一半条目
        # 已落盘才发现越界，"拒绝"就只剩一个空壳目录。
        rels = {}
        for name in entries:
            # 条目自带顶层目录前缀（导出时加的）；target 已经是
            # parent/<top>，所以按**去掉前缀后的相对路径**落位 ——
            # 不剥掉这一层，整个项目就会翻倍嵌进 plates/plates/。
            rel = name[len(top) + 1 :] if name.startswith(top + "/") else name
            rels[name] = rel
            _safe_target(target, rel)
        total = len(entries)
        done = 0
        written = 0
        for name in entries:
            if cancel is not None and cancel():
                try:
                    import shutil

                    shutil.rmtree(target, ignore_errors=True)
                except OSError:
                    pass
                return {"root": target, "files": 0, "cancelled": True}
            arc_target = _safe_target(target, rels[name])
            os.makedirs(osp.dirname(arc_target), exist_ok=True)
            with bundle.open(name) as source, open(arc_target, "wb") as dest:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    dest.write(chunk)
            written += 1
            done += 1
            if progress is not None:
                progress(done, total, name)
    return {"root": target, "files": written}
