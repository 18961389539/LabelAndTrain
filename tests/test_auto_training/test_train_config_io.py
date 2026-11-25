"""The Train tab config bridge, tested without a dialog.

``read_config_from_widgets`` / ``write_config_into_widgets`` used to be
methods on ``UltralyticsDialog``. They only touch the widget map, the ratio
caption and the device hook, so the doubles below use the class names the
bridge dispatches on and need no Qt at all.
"""

import unittest

from jllabeling.views.training.train_config_io import (
    read_config_from_widgets,
    write_config_into_widgets,
)


class CustomLineEdit:
    def __init__(self):
        self._text = ""

    def text(self):
        return self._text

    def setText(self, value):
        self._text = str(value)


class CustomSpinBox:
    def __init__(self):
        self._value = 0

    def value(self):
        return self._value

    def setValue(self, value):
        self._value = value


class CustomSlider(CustomSpinBox):
    pass


class CustomComboBox:
    def __init__(self, items):
        self._items = list(items)
        self._index = 0

    def findText(self, text):
        return self._items.index(text) if text in self._items else -1

    def setCurrentIndex(self, index):
        self._index = index

    def currentText(self):
        return self._items[self._index]


class CustomCheckBox:
    def __init__(self):
        self._checked = False

    def isChecked(self):
        return self._checked

    def setChecked(self, value):
        self._checked = bool(value)


class _RatioLabel:
    def __init__(self):
        self.text = ""

    def setText(self, value):
        self.text = str(value)


def _widgets():
    return {
        "project": CustomLineEdit(),
        "name": CustomLineEdit(),
        "model": CustomLineEdit(),
        "data": CustomLineEdit(),
        "device": CustomComboBox(["cpu", "cuda"]),
        "dataset_ratio": CustomSlider(),
        "classes": CustomLineEdit(),
        "epochs": CustomSpinBox(),
        "cache": CustomCheckBox(),
    }


class TestTrainConfigBridge(unittest.TestCase):
    def test_a_saved_config_lands_on_the_widgets(self):
        widgets = _widgets()
        label = _RatioLabel()
        devices = []
        write_config_into_widgets(
            {
                "basic": {
                    "project": "/runs",
                    "name": "exp_1",
                    "model": "yolov8n.pt",
                    "data": "/labels",
                    "device": "cuda",
                    "dataset_ratio": 0.8,
                },
                "train": {"epochs": 50},
                "checkpoint": {"cache": True},
            },
            widgets,
            label,
            devices.append,
        )

        self.assertEqual(widgets["project"].text(), "/runs")
        self.assertEqual(widgets["model"].text(), "yolov8n.pt")
        self.assertEqual(widgets["device"].currentText(), "cuda")
        self.assertEqual(widgets["epochs"].value(), 50)
        self.assertTrue(widgets["cache"].isChecked())
        self.assertEqual(widgets["dataset_ratio"].value(), 80)
        self.assertEqual(label.text, "0.8")
        self.assertEqual(devices, ["cuda"])

    def test_reading_returns_the_nested_shape_the_trainer_expects(self):
        widgets = _widgets()
        widgets["project"].setText("/runs")
        widgets["name"].setText("exp_1")
        widgets["model"].setText('"yolov8n.pt"')
        widgets["data"].setText("/labels")
        widgets["dataset_ratio"].setValue(80)
        widgets["epochs"].setValue(30)

        config = read_config_from_widgets(widgets)

        self.assertEqual(config["basic"]["project"], "/runs")
        self.assertEqual(config["basic"]["name"], "exp_1")
        self.assertEqual(config["basic"]["model"], "yolov8n.pt")
        self.assertEqual(config["basic"]["dataset_ratio"], 0.8)
        self.assertEqual(config["train"]["epochs"], 30)
        self.assertIsNone(config["train"]["batch"])

    def test_a_missing_widget_yields_an_empty_path_not_a_crash(self):
        config = read_config_from_widgets({})

        self.assertEqual(config["basic"]["model"], "")
        self.assertEqual(config["basic"]["data"], "")
        self.assertEqual(config["basic"]["dataset_ratio"], 0.8)
