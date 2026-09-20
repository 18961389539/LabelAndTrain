"""Dataset housekeeping plans (L3 data-management enhancement).

Turn duplicate groups into a safe, reviewable list of file moves (archive the
extras, keep one representative per group), and execute the moves. Pure logic
kept separate from the UI so it can be unit-tested.
"""

from __future__ import annotations

import os
import os.path as osp
import shutil

ARCHIVE_DIRNAME = "._duplicates_archive"

SIDECAR_EXTS = ("json", "txt")


def archive_duplicates_plan(duplicate_groups, base_dir):
    """Plan archive moves for near-duplicate images.

    Args:
        duplicate_groups: Iterable of lists of image paths that are
            near-duplicates (a group may hold a single image).
        base_dir: Folder to create ``._duplicates_archive`` under.

    Returns:
        List of ``(src, dst)`` tuples. One image per group is kept in place;
        the rest (plus their ``json``/``txt`` sidecars when present) move
        under ``base_dir/._duplicates_archive``. Only files that exist on
        disk are included.
    """
    if not base_dir or base_dir == ARCHIVE_DIRNAME:
        return []
    archive_dir = osp.join(base_dir, ARCHIVE_DIRNAME)

    planned_dst = set()
    plan = []
    for group in duplicate_groups or []:
        members = [p for p in group if p and osp.exists(p)]
        if len(members) < 2:
            continue
        for path in members[1:]:
            base = osp.splitext(osp.basename(path))[0]
            candidates = [path] + [
                osp.join(osp.dirname(path), base + "." + ext)
                for ext in SIDECAR_EXTS
            ]
            for src in candidates:
                if not osp.exists(src):
                    continue
                dst = osp.join(archive_dir, osp.basename(src))
                if dst in planned_dst:
                    continue
                planned_dst.add(dst)
                plan.append((src, dst))
    return plan


def finalize_moves(plan, dry_run=False):
    """Execute an archive plan and report what happened.

    Returns:
        ``(moved, skipped)`` where ``moved`` is a list of ``(src, dst)``
        actually moved and ``skipped`` lists sources that could not be moved
        (missing source, I/O error). ``dry_run=True`` marks everything as
        moved without touching the filesystem.
    """
    moved = []
    skipped = []
    for src, dst in plan:
        if not osp.exists(src):
            skipped.append(src)
            continue
        target = dst
        if osp.exists(target):
            base, ext = osp.splitext(dst)
            counter = 1
            while osp.exists(target):
                target = f"{base}.{counter}{ext}"
                counter += 1
        if not dry_run:
            try:
                os.makedirs(osp.dirname(target), exist_ok=True)
                shutil.move(src, target)
            except OSError:
                skipped.append(src)
                continue
        moved.append((src, target))
    return moved, skipped