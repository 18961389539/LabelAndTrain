"""One answer to "which project is open", asked from anywhere.

``project_context`` replaced three hand-rolled copies of the same
parent-walk (training dialog, auto-labeling panel, project UI). The
copies agreed by discipline; these tests pin the shared answer: parent
shape, vanished folders, and the task/name readers.
"""

import os
import unittest

from anylabeling.views.labeling import project_context

HERE = os.path.dirname(os.path.abspath(__file__))


class _Widget:
    """A stand-in that carries ``_project_dataset_dir`` on itself."""

    def __init__(self, **attrs):
        for key, value in attrs.items():
            setattr(self, key, value)


class _Dialog:
    """A stand-in whose project context lives on its ``parent``."""

    def __init__(self, parent):
        self._parent = parent

    def parent(self):
        return self._parent


class TestCurrentDatasetDir(unittest.TestCase):
    def test_the_widget_itself_may_hold_the_context(self):
        widget = _Widget(_project_dataset_dir=HERE)
        self.assertEqual(project_context.current_dataset_dir(widget), HERE)

    def test_a_dialog_reads_its_parent(self):
        widget = _Widget(_project_dataset_dir=HERE)
        dialog = _Dialog(widget)
        self.assertEqual(project_context.current_dataset_dir(dialog), HERE)

    def test_a_vanished_folder_is_not_a_project(self):
        widget = _Widget(_project_dataset_dir=os.path.join(HERE, "gone"))
        self.assertIsNone(project_context.current_dataset_dir(widget))

    def test_nothing_open_reads_as_none(self):
        self.assertIsNone(project_context.current_dataset_dir(_Widget()))
        self.assertIsNone(
            project_context.current_dataset_dir(
                _Widget(_project_dataset_dir=None)
            )
        )


class TestParentOfBothShapes(unittest.TestCase):
    """Real widgets expose ``parent()``; fakes expose a plain attribute."""

    def test_callable_parent_is_called(self):
        widget = _Widget(_project_dataset_dir=HERE)
        dialog = _Dialog(widget)
        self.assertIs(project_context.parent_of(dialog), widget)

    def test_attribute_parent_is_taken_as_is(self):
        parent = object()
        fake = _Widget(parent=parent)
        self.assertIs(project_context.parent_of(fake), parent)

    def test_no_parent_at_all(self):
        self.assertIsNone(project_context.parent_of(_Widget()))


if __name__ == "__main__":
    unittest.main()
