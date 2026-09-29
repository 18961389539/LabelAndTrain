"""Digit shortcuts: the tenth slot, and working before the first box exists.

Two gaps met here. Auto-assignment only ever filled 1-9 (`range(1, 10)`),
while `digit_shortcut_0` has always been a real key and `user_guide`
documents "0-9" -- so slot 0 was dead unless mapped by hand. And
assignment only ran when a *shape* was seen, so a brand new project
answered nothing to the keys that exist to remove exactly that step.
"""

import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from anylabeling.views.labeling.shortcuts import digit_controller

from anylabeling.views.labeling.shortcuts.digit_controller import (
    DIGIT_SLOTS,
    DigitShortcutController,
)


def shape(label, shape_type="rectangle"):
    return SimpleNamespace(label=label, shape_type=shape_type)


class DigitAssignmentTestCase(unittest.TestCase):
    def build(self, labels=(), shortcuts=None):
        widget = SimpleNamespace(
            drawing_digit_shortcuts=({} if shortcuts is None else shortcuts),
            _config={"labels": list(labels), "digit_shortcuts": {}},
        )
        self.saved = mock.patch.object(digit_controller, "save_config")
        self.saved_mock = self.saved.start()
        self.addCleanup(self.saved.stop)
        return widget, DigitShortcutController(widget)


class TestColdStart(DigitAssignmentTestCase):
    def test_declared_labels_get_the_keys_in_order(self):
        widget, controller = self.build(["scratch", "dent", "stain"])
        self.assertEqual(
            controller.assign_label_digits(widget._config["labels"]), 3
        )
        self.assertEqual(
            widget.drawing_digit_shortcuts,
            {
                1: {"label": "scratch", "mode": "rectangle"},
                2: {"label": "dent", "mode": "rectangle"},
                3: {"label": "stain", "mode": "rectangle"},
            },
        )
        self.saved_mock.assert_called_once()

    def test_the_tenth_label_takes_the_zero_key(self):
        labels = [f"c{index}" for index in range(10)]
        widget, controller = self.build(labels)
        self.assertEqual(controller.assign_label_digits(labels), 10)
        self.assertIn(0, widget.drawing_digit_shortcuts)
        self.assertEqual(widget.drawing_digit_shortcuts[0]["label"], "c9")

    def test_past_ten_labels_the_slots_run_out(self):
        labels = [f"c{index}" for index in range(14)]
        widget, controller = self.build(labels)
        self.assertEqual(controller.assign_label_digits(labels), 10)
        self.assertEqual(
            sorted(widget.drawing_digit_shortcuts), sorted(DIGIT_SLOTS)
        )

    def test_a_label_already_mapped_keeps_its_key(self):
        widget, controller = self.build(
            ["scratch", "dent"], shortcuts={7: {"label": "dent"}}
        )
        controller.assign_label_digits(widget._config["labels"])
        self.assertEqual(widget.drawing_digit_shortcuts[7]["label"], "dent")
        self.assertEqual(widget.drawing_digit_shortcuts[1]["label"], "scratch")

    def test_a_full_map_is_left_alone(self):
        shortcuts = {digit: {"label": f"c{digit}"} for digit in DIGIT_SLOTS}
        widget, controller = self.build(["new"], shortcuts=shortcuts)
        self.assertEqual(controller.assign_label_digits(["new"]), 0)
        self.saved_mock.assert_not_called()

    def test_disabled_digit_shortcuts_are_respected(self):
        widget, controller = self.build(["scratch"])
        widget.drawing_digit_shortcuts = None
        self.assertEqual(controller.assign_label_digits(["scratch"]), 0)

    def test_no_labels_is_a_no_op(self):
        widget, controller = self.build([])
        self.assertEqual(controller.assign_label_digits([]), 0)
        self.saved_mock.assert_not_called()


class TestShapeDrivenAssignment(DigitAssignmentTestCase):
    def test_the_zero_key_is_the_tenth_slot_not_a_dead_key(self):
        widget, controller = self.build()
        controller.auto_assign_digit_shortcuts(
            [shape(f"c{index}") for index in range(10)]
        )
        self.assertEqual(len(widget.drawing_digit_shortcuts), 10)
        self.assertEqual(widget.drawing_digit_shortcuts[0]["label"], "c9")

    def test_the_shape_type_is_remembered(self):
        widget, controller = self.build()
        controller.auto_assign_digit_shortcuts([shape("poly", "polygon")])
        self.assertEqual(widget.drawing_digit_shortcuts[1]["mode"], "polygon")

    def test_labels_already_mapped_are_not_remapped(self):
        widget, controller = self.build(
            shortcuts={3: {"label": "dent", "mode": "rectangle"}}
        )
        controller.auto_assign_digit_shortcuts(
            [shape("dent"), shape("scratch")]
        )
        self.assertEqual(widget.drawing_digit_shortcuts[3]["label"], "dent")
        self.assertEqual(widget.drawing_digit_shortcuts[1]["label"], "scratch")

    def test_disabled_digit_shortcuts_are_respected(self):
        widget, controller = self.build()
        widget.drawing_digit_shortcuts = None
        controller.auto_assign_digit_shortcuts([shape("scratch")])
        self.saved_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
