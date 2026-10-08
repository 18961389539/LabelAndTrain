"""What the Config tab does for the user beyond displaying fields.

CPU is not a GPU with a slower chip, so the form adapts to it:

* AMP is switched off and disabled on CPU — ultralytics ignores it there, so
  a ticked box claimed a setting that did nothing — and the user's choice is
  restored when the device goes back to a GPU.
* Untouched epochs/batch/imgsz are filled from a CPU preset; anything the
  user (or a saved per-dataset prefs file) already changed is left alone.
* The adaptation runs *after* the config load, not mid-load: ``device`` and
  ``amp`` are written in separate passes, and adapting in between would let
  the later pass re-enable what the earlier one switched off.

The same tab also carries the one-click tuning tiers and the field tooltips
that explain the parameters, and both are pinned here.

The tests drive the real dialog offscreen, since the logic lives in the
signal wiring (``on_device_changed``) rather than in a pure function.
"""

import json
import os
import re
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTranslator  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QCheckBox,
    QGroupBox,
    QLabel,
    QPushButton,
    QWidget,
)

import anylabeling.resources.resources  # noqa: E402,F401 - registers the :/ resources
from anylabeling.services.auto_training.ultralytics.config import (  # noqa: E402
    DEFAULT_TRAINING_CONFIG,
)
from anylabeling.views.training import (
    ultralytics_dialog as dialog_module,
)  # noqa: E402
from anylabeling.views.training.ultralytics_dialog import (  # noqa: E402
    CPU_PARAM_PRESET,
    TRAIN_PARAM_PRESETS,
    UltralyticsDialog,
)

CJK = re.compile(r"[\u4e00-\u9fff]")
#: Values, not labels: the dataset-ratio readout and similar.
NOT_A_LABEL = re.compile(r"^[\d\s.,%:/\-]*$")


def _labeled_images(folder, count=20):
    """``count`` images with one rectangle each — clears the Data gate."""
    images = []
    for index in range(count):
        image = os.path.join(folder, f"img{index}.jpg")
        open(image, "wb").close()
        with open(
            os.path.join(folder, f"img{index}.json"), "w", encoding="utf-8"
        ) as handle:
            json.dump(
                {
                    "shapes": [
                        {
                            "label": "cat",
                            "shape_type": "rectangle",
                            "points": [[1, 1], [5, 5]],
                        }
                    ],
                    "flags": {},
                },
                handle,
            )
        images.append(image)
    return images


class TestConfigFormHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "trainer")
        self._patchers = {
            "get_trainer_root_dir": dialog_module.get_trainer_root_dir,
            "load_config": dialog_module.load_config,
            "get_config": dialog_module.get_config,
            "DEVICE_OPTIONS": dialog_module.DEVICE_OPTIONS,
        }
        dialog_module.get_trainer_root_dir = lambda: self.root
        dialog_module.load_config = lambda: {}
        dialog_module.get_config = lambda: {"training": {}}
        # Deterministic device list: a CPU-only machine ships just ["cpu"],
        # which would skip the very transition these tests drive. Both
        # entries make the combo start on "cuda" like a GPU box would.
        dialog_module.DEVICE_OPTIONS = ["cuda", "cpu"]

        self.label_dir = os.path.join(self.tmp.name, "labels")
        os.makedirs(self.label_dir)
        self.image_list = _labeled_images(self.label_dir)

        self.dialog = self._build_dialog()

    def _build_dialog(self):
        parent = QWidget()
        parent.image_list = self.image_list
        parent.output_dir = self.label_dir
        parent.supported_shape = ["rectangle", "polygon", "point"]
        # Held on the test: a QObject parent that goes out of scope takes the
        # dialog (and every widget in it) down with it.
        self.parent = parent

        dialog = UltralyticsDialog(parent)
        dialog.on_task_type_selected("Detect")
        dialog.proceed_to_config()
        return dialog

    def tearDown(self):
        for name, original in self._patchers.items():
            setattr(dialog_module, name, original)
        self.tmp.cleanup()

    def _widget(self, key):
        return self.dialog.config_widgets[key]

    def _switch_device_to(self, text):
        """Select a device through the real signal path."""
        self._widget("device").setCurrentText(text)

    # -- AMP ---------------------------------------------------------------
    def test_cpu_switches_amp_off_and_disables_it(self):
        amp = self._widget("amp")
        amp.setChecked(True)

        self._switch_device_to("cpu")

        self.assertFalse(amp.isChecked(), "CPU training cannot use AMP")
        self.assertFalse(amp.isEnabled())
        self.assertIn("CPU", amp.toolTip())

    def test_leaving_cpu_restores_the_previous_amp_choice(self):
        amp = self._widget("amp")
        amp.setChecked(True)
        self._switch_device_to("cpu")

        self.dialog._apply_amp_for_device(False)  # any non-CPU device

        self.assertTrue(amp.isChecked(), "the user's choice came back")
        self.assertTrue(amp.isEnabled())

    def test_amp_that_was_off_stays_off_after_cpu(self):
        amp = self._widget("amp")
        amp.setChecked(False)
        self._switch_device_to("cpu")

        self.dialog._apply_amp_for_device(False)

        self.assertFalse(amp.isChecked())

    def test_loading_a_cpu_config_cannot_re_enable_amp(self):
        # device and amp arrive in separate passes; the final sync wins.
        self.dialog.load_config_to_ui(
            {"basic": {"device": "cpu"}, "strategy": {"amp": True}}
        )

        amp = self._widget("amp")
        self.assertFalse(amp.isChecked())
        self.assertFalse(amp.isEnabled())

    # -- preset ------------------------------------------------------------
    def test_untouched_parameters_get_the_cpu_preset(self):
        self._switch_device_to("cpu")

        self.assertEqual(
            self._widget("epochs").value(), CPU_PARAM_PRESET["epochs"]
        )
        self.assertEqual(
            self._widget("batch").value(), CPU_PARAM_PRESET["batch"]
        )
        self.assertEqual(
            self._widget("imgsz").value(), CPU_PARAM_PRESET["imgsz"]
        )

    def test_parameters_the_user_changed_are_never_overwritten(self):
        self._widget("epochs").setValue(77)
        self._widget("batch").setValue(32)
        self._switch_device_to("cpu")

        self.assertEqual(self._widget("epochs").value(), 77)
        self.assertEqual(self._widget("batch").value(), 32)
        # ...while the field still at its default is filled.
        self.assertEqual(
            self._widget("imgsz").value(), CPU_PARAM_PRESET["imgsz"]
        )

    # -- hint --------------------------------------------------------------
    def test_hint_names_what_was_replaced_and_only_shows_on_cpu(self):
        hint = self.dialog.device_hint
        self._switch_device_to("cuda")
        self.assertTrue(hint.isHidden())

        self._switch_device_to("cpu")
        self.assertFalse(hint.isHidden())
        self.assertIn("epochs=50", hint.text())
        self.assertIn("slower", hint.text())

    def test_hint_drops_the_preset_note_when_nothing_was_filled(self):
        self._widget("epochs").setValue(77)
        self._widget("batch").setValue(32)
        self._widget("imgsz").setValue(512)

        self._switch_device_to("cpu")

        self.assertNotIn("preset", self.dialog.device_hint.text())

    # -- tooltips ----------------------------------------------------------
    def test_batch_tooltip_documents_minus_one_and_the_cpu_fallback(self):
        tooltip = self._widget("batch").toolTip()

        self.assertIn("-1", tooltip)
        self.assertIn("CPU", tooltip)

    def test_pace_related_fields_explain_themselves(self):
        self.assertIn("CPU", self._widget("epochs").toolTip())
        self.assertIn("640", self._widget("imgsz").toolTip())
        self.assertTrue(self._widget("workers").toolTip())
        self.assertIn("CPU", self._widget("multi_scale").toolTip())

    def test_every_advanced_field_explains_itself(self):
        """The advanced half is a wall of English jargon without these."""
        explained = (
            "time",
            "patience",
            "close_mosaic",
            "optimizer",
            "cos_lr",
            "lr0",
            "lrf",
            "momentum",
            "weight_decay",
            "warmup_epochs",
            "warmup_momentum",
            "warmup_bias_lr",
            "hsv_h",
            "hsv_s",
            "hsv_v",
            "degrees",
            "translate",
            "scale",
            "shear",
            "perspective",
            "dropout",
            "fraction",
            "rect",
            "box",
            "cls",
            "dfl",
            "pose",
            "kobj",
            "save_period",
            "val",
            "plots",
            "save",
            "resume",
            "cache",
            "skip_empty_files",
            "only_checked_files",
        )
        missing = [
            key for key in explained if not self._widget(key).toolTip().strip()
        ]

        self.assertEqual(missing, [], "fields with no explanation")

    # -- tuning tiers ------------------------------------------------------
    def test_a_tier_applies_every_value_it_names(self):
        self.dialog.apply_param_preset("quick")

        for key, value in TRAIN_PARAM_PRESETS["quick"].items():
            widget = self._widget(key)
            actual = (
                widget.isChecked()
                if value is False or value is True
                else widget.value()
            )
            self.assertEqual(actual, value, f"{key} after the quick tier")

    def test_the_standard_tier_resets_the_pace(self):
        self.dialog.apply_param_preset("high")
        self.assertEqual(self._widget("epochs").value(), 300)
        self.assertTrue(self._widget("cos_lr").isChecked())

        self.dialog.apply_param_preset("standard")

        self.assertEqual(
            self._widget("epochs").value(),
            DEFAULT_TRAINING_CONFIG["epochs"],
        )
        self.assertEqual(
            self._widget("imgsz").value(), DEFAULT_TRAINING_CONFIG["imgsz"]
        )
        self.assertFalse(self._widget("cos_lr").isChecked())

    def test_a_tier_replaces_values_the_cpu_preset_would_leave_alone(self):
        """Tiers are explicit clicks, so they overwrite what is there."""
        self._switch_device_to("cpu")
        self.assertEqual(
            self._widget("epochs").value(), CPU_PARAM_PRESET["epochs"]
        )

        self.dialog.apply_param_preset("high")

        self.assertEqual(self._widget("epochs").value(), 300)

    def test_an_unknown_tier_changes_nothing(self):
        before = self._widget("epochs").value()

        self.dialog.apply_param_preset("no-such-tier")

        self.assertEqual(self._widget("epochs").value(), before)

    # -- the panel reads as one language -----------------------------------
    def test_every_visible_label_is_translated(self):
        """The panel used to be half Chinese, half bare English field names.

        The dialog is built with the shipped catalog installed, so this checks
        what a Chinese user actually sees: every label must come out Chinese.
        Values (the dataset-ratio readout) are not labels and are skipped --
        what fails is an English string that survived the round trip, which
        means the label skipped ``tr()`` or the catalog is missing it.
        """
        translator = QTranslator()
        self.assertTrue(
            translator.load(":/languages/translations/zh_CN.qm"),
            "the compiled catalog did not load",
        )
        self.app.installTranslator(translator)
        try:
            dialog = self._build_dialog()
            untranslated = []
            for widget in dialog.config_tab.findChildren(QWidget):
                if not isinstance(
                    widget, (QLabel, QGroupBox, QCheckBox, QPushButton)
                ):
                    continue
                # QGroupBox keeps its caption in title(), everything else in
                # text().
                raw = (
                    widget.title()
                    if isinstance(widget, QGroupBox)
                    else widget.text()
                )
                text = raw.strip()
                if not text or NOT_A_LABEL.match(text) or CJK.search(text):
                    continue
                untranslated.append(text)
        finally:
            self.app.removeTranslator(translator)

        self.assertEqual(
            sorted(set(untranslated)),
            [],
            "labels a Chinese user would see in English",
        )


if __name__ == "__main__":
    unittest.main()
