"""Dropping a folder opens it; dropping images imports them.

Folder drops used to be refused at dragEnter -- only image extensions
were matched -- so dragging the dataset folder onto the window, the very
gesture the empty-canvas guidance teaches, did nothing at all.
"""

import os
import tempfile
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from anylabeling.views.labeling import utils
    from anylabeling.views.labeling.utils import file_lifecycle

    AVAILABLE = True
except Exception:
    AVAILABLE = False


class _Url:
    def __init__(self, path):
        self._path = path

    def toLocalFile(self):
        return self._path


class _MimeData:
    def __init__(self, paths):
        self._paths = paths

    def hasUrls(self):
        return bool(self._paths)

    def urls(self):
        return [_Url(path) for path in self._paths]


class _Event:
    def __init__(self, paths):
        self._mime = _MimeData(paths)
        self.accepted = None

    def mimeData(self):
        return self._mime

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.accepted = False


def _widget(allow_continue=True):
    calls = SimpleNamespace(folder=None, dropped=None)
    widget = SimpleNamespace(
        import_image_folder=lambda dirpath: setattr(calls, "folder", dirpath),
        import_dropped_image_files=lambda items: setattr(
            calls, "dropped", list(items)
        ),
        may_continue=lambda: allow_continue,
    )
    return widget, calls


@unittest.skipUnless(AVAILABLE, "PyQt6 is required")
class TestDropTargets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        extension = utils.get_supported_image_extensions()[0]
        self.image = os.path.join(self.tmp.name, "photo" + extension)
        with open(self.image, "wb") as handle:
            handle.write(b"not really an image")

    def test_a_folder_is_accepted_and_opened(self):
        widget, calls = _widget()
        enter = _Event([self.tmp.name])
        file_lifecycle.handle_drag_enter(widget, enter)
        self.assertTrue(enter.accepted)
        file_lifecycle.handle_drop(widget, _Event([self.tmp.name]))
        self.assertEqual(calls.folder, self.tmp.name)
        self.assertIsNone(calls.dropped)

    def test_an_image_is_still_accepted_and_imported(self):
        widget, calls = _widget()
        enter = _Event([self.image])
        file_lifecycle.handle_drag_enter(widget, enter)
        self.assertTrue(enter.accepted)
        file_lifecycle.handle_drop(widget, _Event([self.image]))
        self.assertEqual(calls.dropped, [self.image])
        self.assertIsNone(calls.folder)

    def test_a_folder_wins_when_both_are_dropped(self):
        widget, calls = _widget()
        event = _Event([self.image, self.tmp.name])
        file_lifecycle.handle_drop(widget, event)
        self.assertEqual(calls.folder, self.tmp.name)
        self.assertIsNone(calls.dropped)

    def test_only_the_first_folder_is_opened(self):
        inner = os.path.join(self.tmp.name, "inner")
        os.makedirs(inner)
        widget, calls = _widget()
        file_lifecycle.handle_drop(widget, _Event([inner, self.tmp.name]))
        self.assertEqual(calls.folder, inner)

    def test_other_files_are_refused(self):
        note = os.path.join(self.tmp.name, "notes.txt")
        with open(note, "w", encoding="utf-8") as handle:
            handle.write("x")
        widget, _calls = _widget()
        enter = _Event([note])
        file_lifecycle.handle_drag_enter(widget, enter)
        self.assertFalse(enter.accepted)

    def test_an_empty_drag_is_refused(self):
        widget, _calls = _widget()
        enter = _Event([])
        file_lifecycle.handle_drag_enter(widget, enter)
        self.assertFalse(enter.accepted)

    def test_a_blocked_switch_ignores_image_drops(self):
        widget, calls = _widget(allow_continue=False)
        drop = _Event([self.image])
        file_lifecycle.handle_drop(widget, drop)
        self.assertIsNone(calls.dropped)
        self.assertFalse(drop.accepted)


if __name__ == "__main__":
    unittest.main()
