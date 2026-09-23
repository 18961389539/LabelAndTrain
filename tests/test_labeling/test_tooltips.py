"""Hover text on the two lists, where the fork's own data becomes visible.

Provenance (``source`` / ``model`` / ``model_version``), review state and the
per-shape attributes are all stored in the label JSON, but the rows only show a
name -- so none of it was readable until a cleanup pass deleted something it
should not have. These tests pin the text that makes it visible.

Image loading is stubbed throughout: under ``QT_QPA_PLATFORM=offscreen`` a real
``load_file`` takes the process down with a stack overrun, which is a property of
the headless Qt platform plugin, not of the app.
"""

import json
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtCore, QtGui, QtWidgets

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


def _make_folder(with_label=True):
    """A two-image folder, one of them already annotated and sent back."""
    from PIL import Image

    holder = tempfile.TemporaryDirectory()
    tmp = holder.name
    Image.new("RGB", (40, 40), "gray").save(os.path.join(tmp, "a.png"))
    Image.new("RGB", (40, 40), "gray").save(os.path.join(tmp, "b.png"))
    if with_label:
        with open(
            os.path.join(tmp, "a.json"), "w", encoding="utf-8"
        ) as handle:
            json.dump(
                {
                    "shapes": [{"label": "cat"}],
                    "checked": False,
                    "review_state": "rejected",
                    "reviewed_at": "2026-09-23 10:12:31",
                },
                handle,
            )
    return tmp, holder


class _WidgetCase(unittest.TestCase):
    """Builds the real widget over a temporary folder, without loading images.

    ``load_file`` is patched per test rather than per module: replacing the
    class attribute outright leaks into every other suite that builds a widget.
    """

    with_label = True

    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        from anylabeling.views.labeling.label_widget import LabelingWidget

        patcher = mock.patch.object(
            LabelingWidget, "load_file", lambda self, *a, **k: False
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.folder, holder = _make_folder(self.with_label)
        self.addCleanup(holder.cleanup)
        widget, holder = _build_widget(self.folder)
        self.widget = widget
        self.addCleanup(widget.deleteLater)
        self.addCleanup(holder.deleteLater)


def _build_widget(folder):
    from tests.test_labeling.test_widget_wiring import build_labeling_widget

    return build_labeling_widget(folder)


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestFileRowTooltips(_WidgetCase):

    with_label = True

    def _row(self, name="a.png"):
        for row in range(self.widget.file_list_widget.count()):
            item = self.widget.file_list_widget.item(row)
            if item.text().endswith(name):
                return item
        self.fail(f"no row for {name}")

    def test_row_names_the_image_and_its_label_file(self):
        tip = self._row("a.png").toolTip()
        self.assertIn("a.png", tip)
        self.assertIn(os.path.join(self.folder, "a.png"), tip)
        self.assertIn("标注文件：a.json", tip)
        # Rows are created without parsing the JSON; the background pass fills
        # the state in, so the tooltip must be rebuilt rather than trusted.
        self.assertIn("复核状态：", tip)

    def test_unannotated_row_says_so(self):
        self.assertIn("尚无标注文件", self._row("b.png").toolTip())

    def test_state_and_timestamp_reach_the_row_tooltip(self):
        item = self._row("a.png")
        self.widget._set_file_item_review_state(
            item, "rejected", "2026-09-23 10:12:31"
        )
        tip = item.toolTip()
        self.assertIn("复核状态：需返工", tip)
        self.assertIn("2026-09-23 10:12:31", tip)
        self.assertIn("图标含义", tip)

    def test_icon_change_does_not_clear_the_tooltip(self):
        # The status dot used to own the only tooltip on the row; both now come
        # from one builder, so refreshing the icon cannot erase the detail.
        item = self._row("a.png")
        self.widget._refresh_file_item_status_icon(item)
        self.assertIn("复核状态：", item.toolTip())


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestObjectRowTooltips(_WidgetCase):

    with_label = False

    def _shape(
        self, label="cat", score=None, source=None, model=None, version=None
    ):
        from anylabeling.views.labeling.provenance import stamp_model_shapes
        from anylabeling.views.labeling.shape import Shape

        shape = Shape(label=label, shape_type="rectangle")
        shape.points = [
            QtCore.QPointF(2, 2),
            QtCore.QPointF(22, 2),
            QtCore.QPointF(22, 20),
            QtCore.QPointF(2, 20),
        ]
        shape.score = score
        if source == "model":
            stamp_model_shapes([shape], model, version)
        elif source == "human":
            shape.source = "human"
        else:
            # A box loaded from a file written before provenance existed: the
            # constructor's `human` default must not survive the load.
            shape.source = "unknown"
        return shape

    def _tooltip_of(self, shape):
        self.widget.add_label(shape, refresh_filters=False)
        # The object list is a QTreeView over a QStandardItemModel; the widget
        # exposes its rows by index.
        item = self.widget.label_list[len(self.widget.label_list) - 1]
        return item.data(QtCore.Qt.ItemDataRole.ToolTipRole)

    def test_model_box_shows_producer_and_weights(self):
        tip = self._tooltip_of(
            self._shape(
                score=0.4123,
                source="model",
                model="run_07",
                version="a1b2c3d4e5f6",
            )
        )
        self.assertIn("模型产出：run_07", tip)
        self.assertIn("权重 a1b2c3d4e5f6", tip)
        self.assertIn("置信度：0.412", tip)
        self.assertIn("外接框 20x18", tip)

    def test_human_box_does_not_claim_a_model(self):
        tip = self._tooltip_of(self._shape(label="dog", source="human"))
        self.assertIn("人工绘制", tip)
        self.assertNotIn("模型产出", tip)
        self.assertNotIn("权重", tip)

    def test_legacy_box_is_reported_as_unattributed(self):
        tip = self._tooltip_of(self._shape(label="ox"))
        self.assertIn("来源未记录", tip)

    def test_group_description_attributes_and_lock_are_listed(self):
        shape = self._shape(source="human")
        shape.group_id = 3
        shape.description = "边界模糊"
        shape.attributes = {"occluded": "yes"}
        shape.difficult = True
        shape.locked = True
        tip = self._tooltip_of(shape)
        self.assertIn("群组编号：3", tip)
        self.assertIn("属性 occluded：yes", tip)
        self.assertIn("描述：边界模糊", tip)
        self.assertIn("困难样本", tip)
        self.assertIn("已锁定", tip)

    def test_tooltip_follows_edits_without_being_rebuilt(self):
        from anylabeling.views.labeling.provenance import stamp_model_shapes

        shape = self._shape(source="model", model="run_07")
        tooltip = self._tooltip_of(shape)
        self.assertNotIn("权重", tooltip)
        stamp_model_shapes([shape], "run_08", "ffee1234abcd")
        item = self.widget.label_list[0]
        refreshed = item.data(QtCore.Qt.ItemDataRole.ToolTipRole)
        self.assertIn("run_08", refreshed)
        self.assertIn("ffee1234abcd", refreshed)


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required")
class TestActionTooltips(_WidgetCase):

    with_label = False
    """Every toolbar and menu entry the user can click must explain itself."""

    # Entries that are containers or placeholders rather than commands.
    ALLOWED_EMPTY = {"tool25", "zoom"}

    def _flatten(self, value, name):
        if isinstance(value, (tuple, list)):
            for index, item in enumerate(value):
                yield from self._flatten(item, f"{name}{index}")
        elif isinstance(value, QtGui.QAction):
            yield name, value

    def test_no_toolbar_action_lacks_a_tooltip(self):
        missing = []
        for group in ("tool", "menu"):
            for name, action in self._flatten(
                getattr(self.widget.actions, group), group
            ):
                if not action.toolTip() and name not in self.ALLOWED_EMPTY:
                    missing.append(name)
        self.assertEqual(missing, [])

    def test_panel_handle_controls_are_explained(self):
        panel = self.widget.tools_panel
        grip = None
        for label in panel._handle.findChildren(QtWidgets.QLabel):
            if label.text().startswith("⋮"):
                grip = label
        self.assertIsNotNone(grip)
        self.assertIn("拖动", grip.toolTip())
        self.assertIn("双击", grip.toolTip())
        self.assertTrue(panel._collapse_btn.toolTip())


if __name__ == "__main__":
    unittest.main()
