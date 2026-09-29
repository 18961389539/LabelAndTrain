"""The "output directory already exists" policy, shared by four call sites.

These tests exist because the four copies used to disagree: the YOLO export
had been hardened while the crop export still offered a single click that
ran ``shutil.rmtree`` on whatever directory the annotator had typed. The
last test here is the ratchet that keeps a fifth copy from appearing.
"""

import ast
import os
import pathlib
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from anylabeling.views.labeling.utils import output_dir

ROOT = pathlib.Path(__file__).resolve().parents[2]
UTILS = ROOT / "anylabeling/views/labeling/utils"


class _FakeButton:
    __slots__ = ("text", "role")

    def __init__(self, text, role=None):
        self.text = text
        self.role = role


class _FakeMessageBox:
    """Stands in for QMessageBox: records buttons, clicks what the test says.

    The click script is consumed one entry per created dialog, so the
    two-step Clear flow can be driven as ``("Clear", "删除并重建")``.
    """

    scripts = []
    instances = []

    class Icon:
        Warning = "warning"
        Critical = "critical"

    class ButtonRole:
        AcceptRole = "accept"
        DestructiveRole = "destructive"
        RejectRole = "reject"
        YesRole = "yes"
        NoRole = "no"

    def __init__(self, parent=None):
        self.parent = parent
        self.buttons = []
        self.default_button = None
        self.informative_text = ""
        self.clicked = None
        _FakeMessageBox.instances.append(self)

    def setIcon(self, icon):
        self.icon = icon

    def setWindowTitle(self, title):
        self.title = title

    def setText(self, text):
        self.text = text

    def setInformativeText(self, text):
        self.informative_text = text

    def setDefaultButton(self, button):
        self.default_button = button

    def setStyleSheet(self, style):
        pass

    def addButton(self, text, role=None):
        button = _FakeButton(text, role)
        self.buttons.append(button)
        return button

    def exec(self):
        wanted = (
            _FakeMessageBox.scripts.pop(0) if _FakeMessageBox.scripts else None
        )
        for button in self.buttons:
            if button.text == wanted:
                self.clicked = button
                break

    def clickedButton(self):
        return self.clicked

    def button_texts(self):
        return [button.text for button in self.buttons]


class OutputDirTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="outdir-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.output = os.path.join(self.root, "out")
        self.images = os.path.join(self.root, "images")
        os.makedirs(self.images)
        with open(os.path.join(self.images, "a.jpg"), "w") as handle:
            handle.write("image")

    def make_output_with_content(self):
        os.makedirs(self.output, exist_ok=True)
        marker = os.path.join(self.output, "keep.txt")
        with open(marker, "w") as handle:
            handle.write("previous run")
        return marker

    def use_fake_dialogs(self, *clicks):
        _FakeMessageBox.scripts = list(clicks)
        _FakeMessageBox.instances = []
        patcher = mock.patch.object(
            output_dir,
            "QtWidgets",
            SimpleNamespace(QMessageBox=_FakeMessageBox),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(setattr, _FakeMessageBox, "scripts", [])
        patcher2 = mock.patch.object(
            output_dir, "get_msg_box_style", lambda *a, **k: ""
        )
        patcher2.start()
        self.addCleanup(patcher2.stop)
        return _FakeMessageBox.instances


class TestResolveExistingOutputDir(OutputDirTestCase):
    def test_a_missing_directory_is_created(self):
        action = output_dir.resolve_existing_output_dir(
            None, self.output, ask=self._never_asked
        )
        self.assertEqual(action, output_dir.MERGE)
        self.assertTrue(os.path.isdir(self.output))

    def _never_asked(self, *args, **kwargs):
        raise AssertionError("no dialog for a directory that does not exist")

    def test_merge_keeps_what_was_there(self):
        marker = self.make_output_with_content()
        action = output_dir.resolve_existing_output_dir(
            None, self.output, ask=lambda *a, **k: output_dir.MERGE
        )
        self.assertEqual(action, output_dir.MERGE)
        self.assertTrue(os.path.exists(marker))

    def test_clear_empties_and_rebuilds(self):
        marker = self.make_output_with_content()
        action = output_dir.resolve_existing_output_dir(
            None, self.output, ask=lambda *a, **k: output_dir.CLEAR
        )
        self.assertEqual(action, output_dir.CLEAR)
        self.assertTrue(os.path.isdir(self.output))
        self.assertFalse(os.path.exists(marker))

    def test_cancel_touches_nothing(self):
        marker = self.make_output_with_content()
        action = output_dir.resolve_existing_output_dir(
            None, self.output, ask=lambda *a, **k: output_dir.CANCEL
        )
        self.assertEqual(action, output_dir.CANCEL)
        self.assertTrue(os.path.exists(marker))

    def test_the_annotated_folder_is_never_offered_for_clearing(self):
        self.make_output_with_content()
        seen = {}

        def ask(widget, path, allow_clear=True):
            seen["allow_clear"] = allow_clear
            return output_dir.MERGE

        output_dir.resolve_existing_output_dir(
            None, self.output, protected_paths=(self.images,), ask=ask
        )
        self.assertTrue(seen["allow_clear"])

        # Now aim the output at the folder that holds the images: clearing
        # it would delete the work itself.
        output_dir.resolve_existing_output_dir(
            None, self.root, protected_paths=(self.images,), ask=ask
        )
        self.assertFalse(seen["allow_clear"])

    def test_a_protected_target_cannot_be_cleared_even_if_asked_for(self):
        marker = self.make_output_with_content()
        action = output_dir.resolve_existing_output_dir(
            None,
            self.output,
            protected_paths=(self.output,),
            ask=lambda *a, **k: output_dir.CLEAR,
        )
        self.assertEqual(action, output_dir.CANCEL)
        self.assertTrue(os.path.exists(marker))

    def test_protected_hit_only_matches_the_target_or_its_ancestors(self):
        images = self.images
        self.assertIsNotNone(output_dir.protected_hit(self.root, [images]))
        self.assertIsNotNone(output_dir.protected_hit(images, [images]))
        self.assertIsNone(output_dir.protected_hit(self.output, [images]))
        self.assertIsNone(output_dir.protected_hit(images, [""]))


class TestSharedDialog(OutputDirTestCase):
    def test_merge_is_the_default_button(self):
        self.make_output_with_content()
        dialogs = self.use_fake_dialogs("Merge")
        action = output_dir.resolve_existing_output_dir(None, self.output)
        self.assertEqual(action, output_dir.MERGE)
        self.assertEqual(dialogs[0].default_button.text, "Merge")
        self.assertEqual(
            dialogs[0].button_texts(), ["Merge", "Clear", "Cancel"]
        )

    def test_clear_asks_a_second_time_with_the_path(self):
        marker = self.make_output_with_content()
        dialogs = self.use_fake_dialogs("Clear", "删除并重建")
        action = output_dir.resolve_existing_output_dir(None, self.output)
        self.assertEqual(action, output_dir.CLEAR)
        self.assertFalse(os.path.exists(marker))
        self.assertEqual(len(dialogs), 2)
        self.assertEqual(
            dialogs[1].informative_text, os.path.realpath(self.output)
        )
        self.assertEqual(dialogs[1].default_button.text, "Cancel")

    def test_backing_out_of_the_second_question_changes_nothing(self):
        marker = self.make_output_with_content()
        self.use_fake_dialogs("Clear", "Cancel")
        action = output_dir.resolve_existing_output_dir(None, self.output)
        self.assertEqual(action, output_dir.CANCEL)
        self.assertTrue(os.path.exists(marker))

    def test_closing_the_dialog_is_a_cancel(self):
        marker = self.make_output_with_content()
        self.use_fake_dialogs(None)
        action = output_dir.resolve_existing_output_dir(None, self.output)
        self.assertEqual(action, output_dir.CANCEL)
        self.assertTrue(os.path.exists(marker))

    def test_a_protected_target_has_no_clear_button(self):
        marker = self.make_output_with_content()
        dialogs = self.use_fake_dialogs("Merge")
        output_dir.resolve_existing_output_dir(
            None, self.output, protected_paths=(self.output,)
        )
        self.assertEqual(dialogs[0].button_texts(), ["Merge", "Cancel"])
        self.assertIn("Clearing is not offered", dialogs[0].informative_text)
        self.assertTrue(os.path.exists(marker))


class TestDeleteRatchet(unittest.TestCase):
    """A fifth copy of this dialog is the bug; fail when one appears."""

    def test_only_the_shared_helper_deletes_an_output_directory(self):
        offenders = []
        for path in sorted(UTILS.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            if "rmtree(save_path)" in text and path.name != "output_dir.py":
                offenders.append(path.name)
        self.assertEqual(
            offenders,
            [],
            "an output directory may only be deleted through "
            "utils/output_dir.resolve_existing_output_dir",
        )

    def test_the_shared_dialog_is_reachable_from_every_writer(self):
        for name in ("export.py", "crop.py"):
            tree = ast.parse((UTILS / name).read_text(encoding="utf-8"))
            calls = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and getattr(node.func, "id", "")
                == "resolve_existing_output_dir"
            ]
            self.assertTrue(calls, f"{name} does not use the shared dialog")
            for call in calls:
                keywords = {keyword.arg for keyword in call.keywords}
                self.assertIn(
                    "protected_paths",
                    keywords,
                    f"{name}: the call must declare what must survive",
                )


if __name__ == "__main__":
    unittest.main()
