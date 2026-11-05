"""Cooperative shutdown of background work when the labeling window closes.

A batch auto-labeling worker is a ``QThread`` that holds the widget and
writes label files between images. Destroying the widget while that thread
is running is not safe, so the close path asks it to stop and refuses to
close until the current image has finished. Model download and interactive
inference are cooperative too; they are cancelled once the close is really
going ahead, after the save prompt has been answered.
"""

from __future__ import annotations


def batch_allows_close(widget):
    """Request the batch stop; True when it is safe to destroy the widget.

    The cancel flag is set even when the answer is False: the worker checks
    it between images and the next close can then proceed. While a batch is
    running the save prompt must not be shown -- the worker is still writing
    labels for other images.
    """
    if not getattr(widget, "_batch_processing_active", False):
        return True
    widget.cancel_processing = True
    thread = getattr(widget, "_batch_thread", None)
    if thread is None:
        return True
    try:
        return not thread.isRunning()
    except RuntimeError:
        # The QThread wrapper was already deleted; nothing can outlive us.
        return True


def cancel_model_work(widget):
    """Ask a model download/inference to stop before the widget goes away."""
    auto_labeling = getattr(widget, "auto_labeling_widget", None)
    manager = getattr(auto_labeling, "model_manager", None)
    if manager is None:
        return
    manager.cancel_download()
    manager.cancel_prediction()
