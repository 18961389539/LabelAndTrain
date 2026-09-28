"""``keep_prev`` copies the previous image's shapes as a *proposal*.

Auto-saving that proposal is how an image that honestly contains nothing (a
negative sample) silently turns into a duplicate of its neighbour: the shapes
are loaded and ``set_dirty()`` used to write them straight to disk, with a
toast that only said "saved". This file pins down the three ways out of the
proposal: edit something, save explicitly, or answer the save prompt.
"""

import json
import os
import tempfile
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtWidgets

    PYQT_AVAILABLE = True
except Exception:  # noqa: BLE001
    PYQT_AVAILABLE = False

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
TEMPLATE_CONFIG = os.path.join(
    REPO_ROOT, "anylabeling", "configs", "jllabeling_config.yaml"
)


def build_labeling_widget(filename=None):
    """Construct the real widget headlessly (same hooks as test_widget_wiring)."""
    from anylabeling import config as app_config
    from anylabeling.views.labeling.label_widget import LabelingWidget

    app_config.current_config_file = TEMPLATE_CONFIG
    LabelingWidget.menu = lambda self, title: QtWidgets.QMenu(title)
    parent = QtWidgets.QWidget()
    return LabelingWidget(parent, filename=filename), parent


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestKeepPrevProposal(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        from PIL import Image

        self.tmp = tempfile.TemporaryDirectory()
        self.image_a = os.path.join(self.tmp.name, "a.png")
        self.image_b = os.path.join(self.tmp.name, "b.png")
        self.label_b = os.path.join(self.tmp.name, "b.json")
        for path in (self.image_a, self.image_b):
            Image.new("RGB", (20, 20), "white").save(path)

        self.widget, self.parent = build_labeling_widget()
        main = QtWidgets.QMainWindow()
        self.widget.parent = SimpleNamespace(parent=main)
        self.main = main
        self.widget.output_dir = self.tmp.name
        self.widget.image_dir = self.tmp.name

        self._saved_config = {
            key: self.widget._config.get(key)
            for key in ("keep_prev", "auto_save")
        }
        self.widget._config["keep_prev"] = True
        self.widget._config["auto_save"] = True

        # Image A carries one box; image B carries nothing at all.
        with open(
            os.path.join(self.tmp.name, "a.json"), "w", encoding="utf-8"
        ) as handle:
            json.dump(
                {
                    "version": "1",
                    "flags": {},
                    "checked": False,
                    "shapes": [
                        {
                            "label": "cat",
                            "shape_type": "rectangle",
                            "points": [[0, 0], [10, 10]],
                            "flags": {},
                            "group_id": None,
                            "description": "",
                            "difficult": False,
                            "attributes": {},
                            "kie_linking": [],
                        }
                    ],
                    "imagePath": "a.png",
                    "imageData": None,
                    "imageHeight": 20,
                    "imageWidth": 20,
                },
                handle,
            )

    def tearDown(self):
        for attr in ("_auto_save_feedback_timer", "_auto_save_timer"):
            timer = getattr(self.widget, attr, None)
            if timer is not None:
                timer.stop()
        for key, value in self._saved_config.items():
            self.widget._config[key] = value
        self.widget.parent = None
        self.tmp.cleanup()

    def _inherit_from_previous_image(self):
        """Open A (one box) then B (nothing) with keep_prev on."""
        self.widget.load_file(self.image_a)
        self.assertEqual(len(self.widget.label_list), 1)
        self.widget.load_file(self.image_b)

    def test_inherited_shapes_reach_the_canvas_but_not_the_disk(self):
        self._inherit_from_previous_image()

        self.assertEqual(
            [shape.label for shape in self.widget.canvas.shapes], ["cat"]
        )
        self.assertTrue(self.widget._pending_inherited_shapes)
        self.assertTrue(self.widget.dirty)
        self.assertFalse(
            os.path.exists(self.label_b),
            "keep_prev wrote a proposal to disk without the annotator asking",
        )

    def test_the_annotator_is_told_the_shapes_are_not_written_yet(self):
        messages = []
        self.widget.status = lambda message, delay=5000: messages.append(
            message
        )
        self._inherit_from_previous_image()

        self.assertEqual(len(messages), 1)
        self.assertIn("1", messages[0])
        self.assertIn("继承", messages[0])

    def test_editing_after_inheriting_saves_normally(self):
        self._inherit_from_previous_image()

        self.widget.set_dirty()
        # The edit re-arms auto-save, which is debounced now: flush the
        # scheduled write the way a real pause (or an image switch) would.
        self.widget.flush_pending_auto_save()

        self.assertFalse(self.widget._pending_inherited_shapes)
        self.assertTrue(os.path.exists(self.label_b))

    def test_explicit_save_ends_the_proposal(self):
        self._inherit_from_previous_image()

        # `save_file()` would open the file chooser: image B has no label
        # file yet, so the annotator picks the path. Write to the same
        # destination that path would resolve to.
        self.widget._save_file(self.label_b)

        self.assertFalse(self.widget._pending_inherited_shapes)
        self.assertFalse(self.widget.dirty)
        self.assertTrue(os.path.exists(self.label_b))

    def test_leaving_asks_instead_of_writing_the_proposal(self):
        from unittest import mock

        self._inherit_from_previous_image()

        with mock.patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Discard,
        ):
            can_leave = self.widget.may_continue(silent=True)

        self.assertTrue(can_leave)
        self.assertFalse(self.widget._pending_inherited_shapes)
        self.assertFalse(
            os.path.exists(self.label_b),
            "a plain 'next image' wrote the inherited proposal silently",
        )

    def test_a_clean_image_still_saves_silently_when_switching(self):
        # The exemption must not leak into the normal flow: once the shapes
        # on screen are the annotator's own, switching images stays silent.
        # The edit re-armed the debounced auto-save; a scheduled write is an
        # edit the annotator already trusted to auto_save, so may_continue
        # flushes it instead of asking.
        self._inherit_from_previous_image()
        self.widget.set_dirty()

        from unittest import mock

        with mock.patch.object(QtWidgets.QMessageBox, "question") as question:
            can_leave = self.widget.may_continue(silent=True)

        self.assertTrue(can_leave)
        question.assert_not_called()
        self.assertTrue(os.path.exists(self.label_b))
