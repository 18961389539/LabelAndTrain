import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from anylabeling.services.auto_labeling.types import AutoLabelingMode
    from anylabeling.views.labeling.widgets.auto_labeling.auto_labeling import (
        _UNNAMED_CLASS,
        _classes_need_name_fallback,
        _first_user_label,
        _labels_from_parent,
        _resolve_custom_model_classes,
    )

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


class _FakeItem:
    def __init__(self, label):
        self._label = label

    def data(self, _role):
        return self._label


class _FakeList:
    def __init__(self, labels):
        self._labels = labels

    def count(self):
        return len(self._labels)

    def item(self, row):
        return _FakeItem(self._labels[row])


class _FakeParent:
    def __init__(self, labels, config_labels=None):
        self.unique_label_list = _FakeList(labels)
        self._config = {"labels": config_labels or []}


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestCustomClassNameFallback(unittest.TestCase):
    def test_keeps_onnx_metadata_names(self):
        names, source = _resolve_custom_model_classes(
            ["person", "car"], "metadata", 2, "产品"
        )
        self.assertEqual(names, ["person", "car"])
        self.assertEqual(source, "metadata")

    def test_uses_first_label_when_metadata_missing(self):
        names, source = _resolve_custom_model_classes(
            ["class_0", "class_1"], "shape", 2, "产品"
        )
        self.assertEqual(names, ["产品", "产品"])
        self.assertEqual(source, "label_list")

    def test_uses_unname_when_label_list_empty(self):
        names, source = _resolve_custom_model_classes(
            ["class_0"], "shape", 1, None
        )
        self.assertEqual(names, [_UNNAMED_CLASS])
        self.assertEqual(source, "unname")

    def test_skips_autolabel_placeholder_rows(self):
        self.assertEqual(
            _first_user_label(
                [AutoLabelingMode.OBJECT, "  ", "缺陷", "其它"]
            ),
            "缺陷",
        )

    def test_labels_from_parent_prefer_dock_then_config(self):
        parent = _FakeParent(
            [AutoLabelingMode.ADD, "产品"],
            config_labels=["配置类"],
        )
        self.assertEqual(
            _first_user_label(_labels_from_parent(parent)), "产品"
        )
        empty_dock = _FakeParent([], config_labels=["配置类"])
        self.assertEqual(
            _first_user_label(_labels_from_parent(empty_dock)), "配置类"
        )

    def test_placeholder_classes_need_fallback(self):
        self.assertTrue(_classes_need_name_fallback(["class_0", "class_1"]))
        self.assertTrue(_classes_need_name_fallback(["unname"]))
        self.assertFalse(_classes_need_name_fallback(["person"]))
        self.assertFalse(_classes_need_name_fallback([]))
