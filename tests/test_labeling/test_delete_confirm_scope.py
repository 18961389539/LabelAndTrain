"""Image deletion always asks; the label-delete skip must not cover it."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from jllabeling.views.labeling.utils import file_lifecycle


class _Widget:
    image_list = ["a.png", "b.png"]
    _config = {}

    def __init__(self):
        self.calls = []

    def status(self, *_args, **_kwargs):
        pass

    def _confirm_destructive_action(self, title, message, allow_skip=True):
        self.calls.append(allow_skip)
        return False


def test_image_deletion_disables_the_session_skip_checkbox():
    widget = _Widget()

    file_lifecycle.delete_image_file(widget)

    assert widget.calls == [False]
