"""The overlay band (labels, descriptions, crosshair, attributes) still draws.

Moved out of ``Canvas`` into ``canvas_overlays`` on 2026-10-17; the render
digest was identical across the move, and these tests are what keep the
split honest afterwards: they assert *where ink lands*, not a byte hash, so
a deliberate restyle can still pass while an overlay that stopped drawing
cannot.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest

try:
    from PyQt6 import QtCore, QtGui, QtWidgets

    from anylabeling.views.labeling.shape import Shape
    from anylabeling.views.labeling.widgets import canvas_overlays
    from anylabeling.views.labeling.widgets.canvas import Canvas

    QT_AVAILABLE = True
except Exception:  # pragma: no cover - exercised on Qt-less runners
    QT_AVAILABLE = False

BACKGROUND = (30, 40, 50)


@unittest.skipUnless(QT_AVAILABLE, "PyQt6 is required")
class TestCanvasOverlays(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
            []
        )

    def setUp(self):
        self.pixmap = QtGui.QPixmap(320, 200)
        self.pixmap.fill(QtGui.QColor(*BACKGROUND))
        self.canvas = Canvas(parent=QtWidgets.QWidget())

    def tearDown(self):
        self.canvas.deleteLater()

    # --- helpers ---------------------------------------------------------

    def _rect(self, label="dent", visible=True, description=""):
        shape = Shape()
        shape.label = label
        shape.shape_type = "rectangle"
        shape.points = [QtCore.QPointF(20, 20), QtCore.QPointF(120, 80)]
        shape.group_id = 7
        shape.score = 0.8321
        shape.description = description
        shape.visible = visible
        return shape

    def _render(self, shapes, **flags):
        """Render through the production offscreen path.

        ``render_visualization`` takes the text/label flags as arguments and
        copies the attribute colors off the canvas, so both are driven here
        the way the widget drives them.
        """
        settings = {
            "show_labels": False,
            "show_scores": False,
            "show_texts": False,
            "show_groups": False,
        }
        settings.update({k: v for k, v in flags.items() if k in settings})
        for name in ("show_attributes", "show_linking", "show_degrees"):
            if name in flags:
                setattr(self.canvas, name, flags[name])
        return self.canvas.render_visualization(
            self.pixmap, shapes, **settings
        )

    def _ink(self, image, rect):
        """Pixels inside ``rect`` that are not the flat background colour."""
        image = image.convertToFormat(QtGui.QImage.Format.Format_RGB32)
        count = 0
        for y in range(rect.top(), min(rect.bottom(), image.height() - 1)):
            for x in range(rect.left(), min(rect.right(), image.width() - 1)):
                color = image.pixelColor(x, y)
                if (color.red(), color.green(), color.blue()) != BACKGROUND:
                    count += 1
        return count

    # --- the overlays draw ----------------------------------------------

    def test_no_overlay_on_a_bare_shape(self):
        # A rectangle with nothing to say: only the shape outline itself.
        image = self._render([self._rect(description="")])
        band = QtCore.QRect(0, 0, 200, 20)  # above the box: label band
        self.assertEqual(self._ink(image, band), 0)

    def test_labels_draw_where_the_shape_box_starts(self):
        region = QtCore.QRect(0, 0, 320, 200)
        without = self._render([self._rect(description="")], show_labels=False)
        with_labels = self._render(
            [self._rect(description="")], show_labels=True
        )
        self.assertGreater(
            self._ink(with_labels, region), self._ink(without, region)
        )

    def test_descriptions_draw_into_the_band_above_the_box(self):
        image = self._render(
            [self._rect(description="chipped edge")], show_texts=True
        )
        self.assertGreater(self._ink(image, QtCore.QRect(0, 0, 200, 22)), 0)

    def test_attributes_draw_below_the_label(self):
        shape = self._rect(description="")
        shape.attributes = {"depth": "deep"}
        without = self._render([shape], show_attributes=False)
        with_attrs = self._render([shape], show_attributes=True)
        region = QtCore.QRect(0, 0, 320, 200)
        self.assertGreater(
            self._ink(with_attrs, region), self._ink(without, region)
        )

    # --- and the exclusions still hold ----------------------------------

    def test_invisible_shapes_stay_unpainted(self):
        visible = self._render(
            [self._rect(description="chipped edge")], show_texts=True
        )
        hidden = self._render(
            [self._rect(description="chipped edge", visible=False)],
            show_texts=True,
        )
        self.assertEqual(self._ink(hidden, QtCore.QRect(0, 0, 200, 22)), 0)
        self.assertGreater(self._ink(visible, QtCore.QRect(0, 0, 200, 22)), 0)

    def test_auto_label_markers_are_not_labeled(self):
        """The AUTOLABEL_* pseudo-labels are prompts, not annotations."""
        marker = self._rect(label="AUTOLABEL_OBJECT", description="")
        image = self._render([marker], show_labels=True)
        self.assertEqual(self._ink(image, QtCore.QRect(0, 0, 200, 20)), 0)

    def test_the_module_needs_only_what_it_reads(self):
        """The split is safe because the overlays never write canvas state.

        A bare namespace with the documented read surface is enough to paint
        with -- if the module ever needed to *set* something on the canvas,
        this would fail.
        """
        image = QtGui.QImage(
            320, 200, QtGui.QImage.Format.Format_ARGB32_Premultiplied
        )
        image.fill(QtGui.QColor(*BACKGROUND))
        painter = QtGui.QPainter(image)
        try:
            shape = self._rect(description="chipped edge")
            canvas = type(
                "Stub",
                (),
                {
                    "shapes": [shape],
                    "pixmap": self.pixmap,
                    "scale": 1.0,
                    "show_texts": True,
                    "show_labels": True,
                    "show_scores": True,
                    "show_attributes": True,
                    "show_linking": False,
                    "cross_line_show": True,
                    "cross_line_color": "#FF0000",
                    "cross_line_width": 1,
                    "cross_line_opacity": 1.0,
                    "attr_background_color": [0, 0, 0, 200],
                    "attr_border_color": [0, 0, 0, 255],
                    "attr_text_color": [255, 255, 255, 255],
                    "move_point": QtCore.QPointF(10, 10),
                    "prev_move_point": QtCore.QPointF(9, 9),
                    "cross_line_hide_vertices": False,
                    "offset_to_center": lambda self: QtCore.QPointF(),
                    "current": None,
                },
            )()
            shape.attributes = {"depth": "deep"}
            canvas_overlays.paint_texts(canvas, painter)
            canvas_overlays.paint_labels(canvas, painter)
            canvas_overlays.paint_attributes(canvas, painter)
            canvas_overlays.paint_cross_coordinates(canvas, painter)
        finally:
            painter.end()
        self.assertGreater(
            self._ink(
                image.convertToFormat(QtGui.QImage.Format.Format_RGB32),
                QtCore.QRect(0, 0, 320, 200),
            ),
            0,
        )


if __name__ == "__main__":
    unittest.main()
