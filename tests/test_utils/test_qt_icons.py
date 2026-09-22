import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtCore, QtGui, QtWidgets

    import anylabeling.resources.resources  # noqa: F401
    from anylabeling.views.labeling.utils.qt import new_icon, new_icon_path
    from anylabeling.views.labeling.utils.theme import init_theme

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt6 is required for icon tests")
class TestQtIcons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance()
        if cls.app is None:
            cls.app = QtWidgets.QApplication([])

    def test_lucide_mapped_icon_path_is_generated(self):
        init_theme("light")
        path = new_icon_path("settings", "svg")

        self.assertTrue(os.path.isabs(path))
        self.assertTrue(path.endswith("settings.svg"))
        self.assertTrue(os.path.exists(path))
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("lucide", content)

    def test_dark_theme_lucide_icons_use_light_stroke(self):
        init_theme("dark")
        path = new_icon_path("settings", "svg")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("#ffffff", content.lower())

    def test_unmapped_icon_keeps_qt_resource_path(self):
        path = new_icon_path("no-such-icon-name", "svg")
        self.assertEqual(path, ":/images/images/no-such-icon-name.svg")

    def test_mapped_icon_ignores_requested_extension(self):
        # Most call sites reach new_icon() without an extension, so a mapped
        # name must resolve to the themed lucide svg for either request; the
        # old per-entry ext gate made `save` fall back to a legacy bitmap and
        # `search` come back empty.
        for ext in ("png", "svg"):
            path = new_icon_path("save", ext)
            self.assertTrue(os.path.isabs(path), ext)
            self.assertTrue(path.endswith("save.svg"), ext)
            self.assertTrue(os.path.exists(path), ext)

    @staticmethod
    def _ink_luminance(pixmap):
        image = pixmap.toImage().convertToFormat(
            QtGui.QImage.Format.Format_ARGB32
        )
        data = bytes(
            image.constBits().asarray(
                image.height() * image.bytesPerLine()
            )
        )
        pixels = [
            (data[i] + data[i + 1] + data[i + 2]) / 3
            for i in range(0, len(data), 4)
            if data[i + 3] > 200
        ]
        return sum(pixels) / len(pixels) if pixels else None

    def test_disabled_mode_is_dimmer_than_normal(self):
        # Qt generates Disabled from the source artwork unchanged, which left
        # disabled controls at full brightness — loudest of all in dark mode.
        for mode_name in ("light", "dark"):
            with self.subTest(mode=mode_name):
                init_theme(mode_name)
                icon = new_icon("save", "png")
                size = QtCore.QSize(24, 24)
                normal = icon.pixmap(size, QtGui.QIcon.Mode.Normal)
                disabled = icon.pixmap(size, QtGui.QIcon.Mode.Disabled)
                self.assertFalse(normal.isNull())
                self.assertFalse(disabled.isNull())
                normal_lum = self._ink_luminance(normal)
                disabled_lum = self._ink_luminance(disabled)
                self.assertIsNotNone(normal_lum)
                # The theme-independent property is that a disabled glyph sits
                # closer to mid-grey than an active one, so it recedes against
                # both a dark and a light background.
                self.assertLess(
                    abs(disabled_lum - 128), abs(normal_lum - 128)
                )

    def test_recently_mapped_icons_are_generated(self):
        for icon_name, ext in (
            ("icon", "png"),
            ("ultralytics", "png"),
            ("digit7", "png"),
            ("lock", "svg"),
            ("eraser", "svg"),
            ("checkmark-white", "svg"),
            ("next", "svg"),
            ("prev", "svg"),
            ("save", "svg"),
            ("brain", "svg"),
        ):
            path = new_icon_path(icon_name, ext)
            self.assertTrue(os.path.isabs(path), icon_name)
            self.assertTrue(path.endswith(f"{icon_name}.svg"), icon_name)
            self.assertTrue(os.path.exists(path), icon_name)

    def test_digit_icon_contains_requested_number(self):
        path = new_icon_path("digit3", "png")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(">3</text>", content)

    def test_ultralytics_icon_no_longer_uses_resource_fallback(self):
        path = new_icon_path("ultralytics", "png")
        self.assertTrue(os.path.isabs(path))
        self.assertTrue(path.endswith("ultralytics.svg"))

    def test_app_icon_loads_into_qicon(self):
        icon = new_icon("icon")
        self.assertFalse(icon.isNull())

    def test_mapped_icon_loads_into_qicon(self):
        icon = new_icon("open")
        self.assertFalse(icon.isNull())
