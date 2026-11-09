"""Pixel-accurate zoom: hard-edged sampling above 100%, clipped grid below it.

The canvas used to enable ``QPainter.SmoothPixmapTransform`` unconditionally,
so a zoomed-in industrial image showed interpolated gradients where an
annotator needed to see real pixel boundaries. These tests pin down the
sampling policy, the Qt behaviour it relies on, the grid overlay's clipping
and the config/schema wiring that makes the switch reachable.
"""

import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import yaml
    from PyQt6 import QtCore, QtGui, QtWidgets

    from jllabeling import config
    from jllabeling.views.labeling.settings import schema
    from jllabeling.views.labeling.settings.runtime_applier import (
        SettingsRuntimeApplier,
    )
    from jllabeling.views.labeling.widgets.canvas import Canvas
    from jllabeling.views.labeling.widgets.canvas_render import (
        pixel_view_config,
        smooth_pixmap_transform_enabled,
    )

    PYQT_AVAILABLE = True
except Exception:  # pragma: no cover - optional GUI dependency
    PYQT_AVAILABLE = False

SOURCE_VALUES = (0, 64, 128, 255)
ZOOM = 8


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required for canvas tests")
class TestSamplingPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])

    @staticmethod
    def _source_pixmap(width=4, height=1):
        image = QtGui.QImage(
            width, height, QtGui.QImage.Format.Format_RGB32
        )
        for y in range(height):
            for x in range(width):
                value = SOURCE_VALUES[x % len(SOURCE_VALUES)]
                image.setPixel(x, y, QtGui.qRgb(value, value, value))
        return QtGui.QPixmap.fromImage(image)

    @classmethod
    def _render_row(cls, scale, smooth, width=4, height=1):
        """Render the source pixmap through a QPainter transform."""
        out_width = max(1, int(width * scale))
        out_height = max(1, int(height * scale))
        out = QtGui.QImage(
            out_width, out_height, QtGui.QImage.Format.Format_RGB32
        )
        out.fill(QtGui.QColor(255, 0, 255))
        painter = QtGui.QPainter(out)
        try:
            painter.setRenderHint(
                QtGui.QPainter.RenderHint.SmoothPixmapTransform, smooth
            )
            painter.scale(scale, scale)
            painter.drawPixmap(0, 0, cls._source_pixmap(width, height))
        finally:
            painter.end()
        return [QtGui.qRed(out.pixel(x, 0)) for x in range(out_width)]

    def test_nearest_neighbour_only_at_or_above_full_scale(self):
        self.assertTrue(
            smooth_pixmap_transform_enabled(True, 0.5),
            "downscaling must keep area averaging to avoid aliasing",
        )
        for scale in (1.0, 2.0, ZOOM):
            self.assertFalse(
                smooth_pixmap_transform_enabled(True, scale),
                f"{scale}x zoom should be pixelated",
            )

    def test_disabling_the_feature_restores_legacy_smoothing(self):
        for scale in (0.5, 1.0, ZOOM):
            self.assertTrue(
                smooth_pixmap_transform_enabled(False, scale)
            )

    def test_qt_smooth_hint_really_produces_a_gradient(self):
        row = self._render_row(ZOOM, smooth=True)
        self.assertEqual(row[0], 0)
        # A bilinear ramp, not a staircase: intermediate values appear
        # between two source pixels instead of a single hard step.
        self.assertTrue(any(0 < value < 64 for value in row))
        self.assertGreater(len(set(row)), 8)

    def test_qt_nearest_neighbour_really_produces_hard_pixel_blocks(self):
        row = self._render_row(ZOOM, smooth=False)
        expected = [v for v in SOURCE_VALUES for _ in range(ZOOM)]
        self.assertEqual(row, expected)

    def test_qt_downscale_is_area_averaging_not_point_sampling(self):
        smooth = self._render_row(0.5, smooth=True)
        point_sampled = self._render_row(0.5, smooth=False)
        self.assertEqual(point_sampled, [0, 128])
        # (0+64)/2 and (128+255)/2, rounded by the raster engine.
        self.assertAlmostEqual(smooth[0], 31, delta=2)
        self.assertAlmostEqual(smooth[1], 191, delta=2)


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required for canvas tests")
class TestPixelGrid(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])

    @staticmethod
    def _render_grid(canvas, scale, clip, width=4, height=1):
        image = QtGui.QImage(
            int(width * scale),
            int(height * scale),
            QtGui.QImage.Format.Format_RGB32,
        )
        image.fill(QtGui.QColor(255, 255, 255))
        painter = QtGui.QPainter(image)
        try:
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            painter.scale(scale, scale)
            painter.setClipRect(clip)
            canvas._paint_pixel_grid(painter)
            antialiasing_after = bool(
                painter.renderHints()
                & QtGui.QPainter.RenderHint.Antialiasing
            )
        finally:
            painter.end()
        painted = sum(
            1
            for y in range(image.height())
            for x in range(image.width())
            if QtGui.qRed(image.pixel(x, y)) != 255
        )
        return painted, antialiasing_after

    def _canvas(self, threshold=8.0, width=4, height=1):
        canvas = Canvas(parent=None)
        canvas.pixelated_zoom = True
        canvas.pixel_grid_threshold = threshold
        canvas.pixmap = QtGui.QPixmap(width, height)
        canvas.scale = ZOOM
        return canvas

    def test_grid_is_hidden_below_the_threshold(self):
        canvas = self._canvas(threshold=8.0)
        canvas.scale = 4.0
        painted, _ = self._render_grid(
            canvas, 4.0, QtCore.QRectF(0, 0, 4, 1)
        )
        self.assertEqual(painted, 0)

    def test_zero_threshold_disables_the_grid(self):
        canvas = self._canvas(threshold=0.0)
        painted, _ = self._render_grid(
            canvas, ZOOM, QtCore.QRectF(0, 0, 4, 1)
        )
        self.assertEqual(painted, 0)

    def test_grid_draws_lines_at_the_threshold(self):
        canvas = self._canvas()
        painted, antialiasing_after = self._render_grid(
            canvas, ZOOM, QtCore.QRectF(0, 0, 4, 1)
        )
        self.assertGreater(painted, 0)
        # Antialiasing is restored for the vector annotations drawn after us.
        self.assertTrue(antialiasing_after)

    def test_grid_only_covers_the_clipped_region(self):
        canvas = self._canvas()
        full, _ = self._render_grid(
            canvas, ZOOM, QtCore.QRectF(0, 0, 4, 1)
        )
        clipped, _ = self._render_grid(
            canvas, ZOOM, QtCore.QRectF(0, 0, 2, 1)
        )
        self.assertGreater(full, 0)
        self.assertLess(clipped, full)

    def test_grid_skips_huge_regions_instead_of_stalling_repaints(self):
        canvas = self._canvas(threshold=1.0, width=5000, height=1)
        canvas.scale = 1.0
        painted, _ = self._render_grid(
            canvas, 1.0, QtCore.QRectF(0, 0, 5000, 1), width=5000, height=1
        )
        self.assertEqual(painted, 0)

    def test_canvas_defaults_match_the_shipped_template(self):
        canvas = Canvas(parent=None)
        template = schema.load_template_config()
        pixelated, threshold = pixel_view_config(canvas)
        self.assertEqual(pixelated, template["canvas"]["pixelated_zoom"])
        self.assertEqual(
            threshold, template["canvas"]["pixel_grid_threshold"]
        )

    def test_live_widget_config_is_the_single_source_of_truth(self):
        class _Widget(QtWidgets.QWidget):
            def __init__(self):
                super().__init__()
                self._config = {
                    "canvas": {
                        "pixelated_zoom": False,
                        "pixel_grid_threshold": 2.0,
                    }
                }

        canvas = Canvas(parent=_Widget())
        self.assertEqual(pixel_view_config(canvas), (False, 2.0))
        # Explicit attributes (written by the runtime applier) win.
        canvas.pixelated_zoom = True
        canvas.pixel_grid_threshold = 0.0
        self.assertEqual(pixel_view_config(canvas), (True, 0.0))


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required for canvas tests")
class TestPixelViewConfiguration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])

    def test_template_and_schema_agree_on_the_new_keys(self):
        template = schema.load_template_config()
        self.assertIs(template["canvas"]["pixelated_zoom"], True)
        self.assertEqual(template["canvas"]["pixel_grid_threshold"], 8.0)
        defaults = schema.defaults_map()
        for key in (
            "canvas.pixelated_zoom",
            "canvas.pixel_grid_threshold",
        ):
            self.assertIn(key, schema.SETTING_FIELD_MAP)
            self.assertEqual(
                defaults[key],
                schema.get_nested_value(template, key),
            )

    def test_legacy_rc_receives_new_defaults_without_a_migration(self):
        """``update_dict`` deep-merges, so new keys need no version bump."""
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "legacy.yaml")
            with open(path, "w", encoding="utf-8") as handle:
                yaml.safe_dump(
                    {
                        "config_version": 3,
                        "canvas": {"num_backups": 77},
                    },
                    handle,
                )
            loaded = config.get_config(config_file_or_yaml=path)
        self.assertIs(loaded["canvas"]["pixelated_zoom"], True)
        self.assertEqual(
            loaded["canvas"]["pixel_grid_threshold"], 8.0
        )
        self.assertEqual(loaded["canvas"]["num_backups"], 77)

    def test_runtime_applier_updates_the_canvas_without_a_restart(self):
        canvas = Canvas(parent=None)

        class _Widget:
            def __init__(self):
                self.canvas = canvas
                self._config = {
                    "canvas": {
                        "pixelated_zoom": False,
                        "pixel_grid_threshold": 2.0,
                    }
                }

        widget = _Widget()
        applier = SettingsRuntimeApplier(widget)
        applier.apply_change("canvas.pixelated_zoom", False)
        self.assertIs(canvas.pixelated_zoom, False)
        self.assertEqual(canvas.pixel_grid_threshold, 2.0)

        widget._config["canvas"] = {
            "pixelated_zoom": True,
            "pixel_grid_threshold": 16.0,
        }
        applier.apply_change("canvas.pixel_grid_threshold", 16.0)
        self.assertIs(canvas.pixelated_zoom, True)
        self.assertEqual(canvas.pixel_grid_threshold, 16.0)


if __name__ == "__main__":
    unittest.main()
