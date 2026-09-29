"""Undo history that survives leaving the image.

``canvas.reset_state()`` used to empty both stacks on every file switch, so
a wrong edit noticed after moving on was unrecoverable from the keyboard.
These tests pin the two halves of the fix: the store banks each image's
history and restores it, and the canvas reaches that store through the same
attribute names it always exposed.
"""

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from anylabeling.views.labeling.widgets import shape_history

from anylabeling.views.labeling.widgets.shape_history import (
    ShapeHistoryStore,
)

try:
    from PyQt6 import QtWidgets

    from anylabeling.views.labeling.shape import Shape
    from anylabeling.views.labeling.widgets.canvas import Canvas

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


def state(*labels):
    return [Shape(label=label, shape_type="rectangle") for label in labels]


class TestStore(unittest.TestCase):
    def test_undo_needs_a_current_and_a_previous_state(self):
        store = ShapeHistoryStore()
        self.assertFalse(store.can_undo())
        store.push(state("car"), limit=10)
        self.assertFalse(store.can_undo())
        store.push(state("car", "bus"), limit=10)
        self.assertTrue(store.can_undo())

    def test_the_oldest_states_fall_off_past_the_limit(self):
        store = ShapeHistoryStore()
        for index in range(20):
            store.push(state(str(index)), limit=3)
        self.assertLessEqual(len(store.undo_stack), 5)

    def test_a_new_edit_kills_the_redo_branch(self):
        store = ShapeHistoryStore()
        store.push(state("one"), limit=10)
        store.push(state("one", "two"), limit=10)
        store.undo()
        self.assertTrue(store.can_redo())
        store.push(state("one", "three"), limit=10)
        self.assertFalse(store.can_redo())

    def test_undo_returns_the_state_below_the_top(self):
        store = ShapeHistoryStore()
        store.push(state("one"), limit=10)
        store.push(state("one", "two"), limit=10)
        restored = store.undo()
        self.assertEqual([shape.label for shape in restored], ["one"])
        self.assertFalse(store.can_undo())

    def test_redo_returns_what_undo_discarded(self):
        store = ShapeHistoryStore()
        store.push(state("one"), limit=10)
        store.push(state("one", "two"), limit=10)
        store.undo()
        reapplied = store.redo()
        self.assertEqual([shape.label for shape in reapplied], ["one", "two"])


class TestHistoryAcrossImages(unittest.TestCase):
    def test_a_banked_stack_comes_back_without_its_top(self):
        store = ShapeHistoryStore()
        store.enter("a.json")
        store.push(["a1"], limit=10)
        store.push(["a1", "a2"], limit=10)
        store.leave()

        store.enter("b.json")
        self.assertEqual(store.undo_stack, [])

        store.enter("a.json")
        # The file on disk holds the newest state, and load_shapes() is about
        # to push exactly that; keeping it would make the first Ctrl+Z a
        # no-op.
        self.assertEqual(store.undo_stack, [["a1"]])

    def test_entering_the_same_image_again_keeps_the_stacks(self):
        store = ShapeHistoryStore()
        store.enter("a.json")
        store.push(["a1"], limit=10)
        store.enter("a.json")
        self.assertEqual(store.undo_stack, [["a1"]])

    def test_entering_another_image_banks_the_first(self):
        store = ShapeHistoryStore()
        store.enter("a.json")
        store.push(["a1"], limit=10)
        store.enter("b.json")
        store.push(["b1"], limit=10)
        store.enter("a.json")
        self.assertEqual(store.undo_stack, [])
        store.enter("b.json")
        self.assertEqual(store.undo_stack, [])

    def test_leaving_twice_is_harmless(self):
        store = ShapeHistoryStore()
        store.enter("a.json")
        store.push(["a1"], limit=10)
        store.leave()
        store.leave()
        store.enter("a.json")
        self.assertEqual(store.undo_stack, [])

    def test_only_the_most_recent_images_keep_a_history(self):
        with mock.patch.object(shape_history, "MAX_BUCKETS", 2):
            store = ShapeHistoryStore()
            for name in ("a.json", "b.json", "c.json"):
                store.enter(name)
                store.push([name], limit=10)
                store.leave()
            self.assertEqual(sorted(store._buckets), ["b.json", "c.json"])


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required for canvas tests")
class TestCanvasWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])

    def test_the_old_attribute_names_still_work(self):
        canvas = Canvas(parent=None)
        canvas.shapes_backups.append("snapshot")
        self.assertEqual(canvas.shape_history.undo_stack, ["snapshot"])
        canvas.shapes_redo_backups = ["branch"]
        self.assertEqual(canvas.shape_history.redo_stack, ["branch"])
        # The label editor pops the live list rather than calling a method.
        canvas.shapes_backups.pop()
        self.assertEqual(canvas.shape_history.undo_stack, [])

    def test_undo_works_again_after_a_detour_through_another_image(self):
        canvas = Canvas(parent=None)

        canvas.shape_history.enter("a.json")
        canvas.load_shapes(state("car"))
        canvas.load_shapes(state("car", "bus"))
        self.assertTrue(canvas.is_shape_restorable)
        on_disk = [shape.copy() for shape in canvas.shapes]

        # The annotator moves on to another image ...
        canvas.reset_state()
        canvas.shape_history.enter("b.json")
        canvas.load_shapes(state("boat"))
        self.assertFalse(canvas.is_shape_restorable)

        # ... and comes back to the first one. Its history is still there.
        canvas.reset_state()
        canvas.shape_history.enter("a.json")
        canvas.load_shapes(on_disk)
        self.assertTrue(canvas.is_shape_restorable)
        canvas.restore_shape()
        self.assertEqual([shape.label for shape in canvas.shapes], ["car"])

    def test_redo_is_reachable_after_coming_back(self):
        canvas = Canvas(parent=None)
        canvas.shape_history.enter("a.json")
        canvas.load_shapes(state("car"))
        canvas.load_shapes(state("car", "bus"))
        on_disk = [shape.copy() for shape in canvas.shapes]
        canvas.reset_state()
        canvas.shape_history.enter("b.json")
        canvas.shape_history.enter("a.json")
        canvas.load_shapes(on_disk)
        canvas.restore_shape()
        self.assertTrue(canvas.is_shape_redoable)


if __name__ == "__main__":
    unittest.main()
