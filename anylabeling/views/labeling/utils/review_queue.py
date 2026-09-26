"""Smart review queue navigation (L1 review-flow enhancement).

The folder audit already ranks images by uncertainty; this module turns that
priority list into an easy "jump to the next image that needs review" flow.
Pure logic, no Qt dependencies.
"""

from __future__ import annotations


def queue_position(ordered, current_path=None):
    """Index of ``current_path`` inside ``ordered`` (or None when absent)."""
    if not ordered or current_path is None:
        return None
    try:
        return ordered.index(current_path)
    except ValueError:
        return None


def next_review_target(ordered, current_path=None, forward=True, wrap=True):
    """Pick the next image to visit in a priority-ordered review queue.

    Args:
        ordered: Image paths sorted by review priority (highest first).
        current_path: Image currently open (may not be part of the queue).
        forward: ``True`` walks down the queue, ``False`` walks back up.
        wrap: Allow cycling past either end of the queue.

    Returns:
        ``(path, index)`` of the image to open, or ``(None, None)`` when the
        queue is empty.
    """
    if not ordered:
        return None, None
    idx = queue_position(ordered, current_path)
    if idx is None:
        # Because the current image isn't in the queue, forward goes to the
        # highest priority; backward to the lowest.
        return (ordered[0], 0) if forward else (ordered[-1], len(ordered) - 1)
    step = 1 if forward else -1
    target = idx + step
    if 0 <= target < len(ordered):
        return ordered[target], target
    if wrap:
        wrapped = 0 if forward else len(ordered) - 1
        return ordered[wrapped], wrapped
    return None, None
