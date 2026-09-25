import functools
import natsort
import os
import os.path as osp
import tempfile
from math import sqrt

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6 import QtCore, QtGui, QtWidgets

from anylabeling.views.labeling.logger import logger
from .image import get_supported_image_extensions

try:
    from lucide import lucide_icon
except Exception:  # noqa: BLE001
    lucide_icon = None


_LUCIDE_CACHE_DIR = osp.join(
    tempfile.gettempdir(), "jl_labeling_and_train", "lucide_icons"
)
_LUCIDE_ICON_MAP = {
    "auto-run": {"name": "play"},
    "arrow-right": {"name": "arrow-right"},
    "arrow-left": {"name": "arrow-left"},
    "brain": {"name": "brain"},
    "brush": {"name": "brush"},
    "brush_polygon": {"name": "brush"},
    "cancel": {"name": "x"},
    "caret-left": {"name": "chevron-left"},
    "caret-down": {"name": "chevron-down"},
    "caret-right": {"name": "chevron-right"},
    "caret-up": {"name": "chevron-up"},
    "cartesian": {"name": "crosshair"},
    "check": {"name": "check"},
    "checkmark": {"name": "check", "stroke": "#0D9488"},
    "checkmark-white": {
        "name": "check",
        "stroke": "#ffffff",
    },
    "circle-selection": {"name": "circle-dot"},
    "color": {"name": "palette"},
    "convert": {"name": "shuffle"},
    "copy": {"name": "copy"},
    "copy-green": {
        "name": "circle-check-big",
        "stroke": "#16a34a",
    },
    "crop": {"name": "crop"},
    "delete": {"name": "trash"},
    "digit0": {"name": "square", "digit": "0"},
    "digit1": {"name": "square", "digit": "1"},
    "digit2": {"name": "square", "digit": "2"},
    "digit3": {"name": "square", "digit": "3"},
    "digit4": {"name": "square", "digit": "4"},
    "digit5": {"name": "square", "digit": "5"},
    "digit6": {"name": "square", "digit": "6"},
    "digit7": {"name": "square", "digit": "7"},
    "digit8": {"name": "square", "digit": "8"},
    "digit9": {"name": "square", "digit": "9"},
    "done": {"name": "circle-check-big"},
    "edit": {"name": "pencil"},
    "eraser": {"name": "eraser"},
    "error": {
        "name": "circle-alert",
        "stroke": "#dc2626",
    },
    "eye": {"name": "eye"},
    "file": {"name": "image"},
    "fit-window": {"name": "maximize"},
    "fit-width": {"name": "move-horizontal"},
    "folder": {"name": "folder"},
    "hidden": {"name": "eye-off"},
    "icon": {"name": "scan-search", "stroke": "#0D9488"},
    "label": {"name": "tag"},
    "labels": {"name": "tags"},
    "lock": {"name": "lock"},
    "loop": {"name": "repeat"},
    "navigator": {"name": "map"},
    "open": {"name": "folder-open"},
    "overview": {"name": "layout-dashboard"},
    "paste": {"name": "clipboard-paste"},
    "point": {"name": "circle-dot"},
    "polygon": {"name": "pentagon"},
    "prev": {"name": "arrow-left"},
    "rectangle": {"name": "square"},
    "redo": {"name": "redo-2"},
    "search": {"name": "search"},
    "settings": {"name": "settings"},
    "star": {"name": "star"},
    "starred": {
        "name": "star",
        "fill": "currentColor",
    },
    "trash": {"name": "trash"},
    "undo": {"name": "undo-2"},
    "union": {"name": "combine"},
    "ultralytics": {"name": "scan-search"},
    "next": {"name": "arrow-right"},
    "save": {"name": "save"},
    "save-as": {"name": "save"},
    "warning": {
        "name": "triangle-alert",
        "stroke": "#d97706",
    },
    "zoom": {"name": "scan-search"},
    "zoom-in": {"name": "zoom-in"},
    "zoom-out": {"name": "zoom-out"},
}


def _resource_icon_path(icon, ext):
    return osp.join(f":/images/images/{icon}.{ext}")


def _normalize_icon_path(path):
    return path.replace("\\", "/")


def _lucide_theme_signature():
    try:
        from anylabeling.views.labeling.utils.theme import get_mode, get_theme

        theme = get_theme()
        stroke = "#ffffff" if get_mode() == "dark" else theme["text"]
        fill = stroke
    except Exception:  # noqa: BLE001
        app = QtWidgets.QApplication.instance()
        if app is None:
            stroke = "#1d1d1f"
            fill = "#1d1d1f"
        else:
            palette = app.palette()
            stroke = palette.color(QtGui.QPalette.ColorRole.ButtonText).name()
            fill = stroke
    signature = f"{stroke.lstrip('#')}_{fill.lstrip('#')}"
    return signature, stroke, fill


def _resolve_lucide_color(value, fallback):
    if value in (None, "currentColor"):
        return fallback
    return value


def _decorate_lucide_svg(svg, spec):
    digit = spec.get("digit")
    if digit is None:
        return svg
    text_fill = spec.get("digit_fill", spec.get("stroke", "currentColor"))
    digit_markup = (
        f'<text x="12" y="12.2" text-anchor="middle" '
        f'dominant-baseline="middle" font-family="Arial, sans-serif" '
        f'font-size="11" font-weight="700" fill="{text_fill}">{digit}</text>'
    )
    return svg.replace("</svg>", f"{digit_markup}</svg>")


@functools.lru_cache(maxsize=None)
def _lucide_icon_path(icon, theme_signature, default_stroke, default_fill):
    if lucide_icon is None:
        return None
    spec = _LUCIDE_ICON_MAP.get(icon)
    if not spec:
        return None
    # Lucide always renders SVG, so the caller's requested extension is not a
    # gate: a mapped name must resolve to the themed stroke icon even when the
    # call site asked for the legacy png (which is how `save`/`search` ended up
    # off-theme or empty).
    lucide_name = spec["name"]
    try:
        svg = lucide_icon(
            lucide_name,
            width="24",
            height="24",
            stroke=_resolve_lucide_color(
                spec.get("stroke", "currentColor"), default_stroke
            ),
            fill=_resolve_lucide_color(spec.get("fill", "none"), default_fill),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to render Lucide icon %s: %s", lucide_name, exc)
        return None
    svg = _decorate_lucide_svg(svg, spec)

    themed_cache_dir = osp.join(_LUCIDE_CACHE_DIR, theme_signature)
    os.makedirs(themed_cache_dir, exist_ok=True)
    cache_name = f"{icon}.svg"
    cache_path = osp.join(themed_cache_dir, cache_name)
    if not osp.exists(cache_path):
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(svg)
    return _normalize_icon_path(cache_path)


def apply_application_font(font_family):
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    default_font = getattr(app, "_xanylabeling_default_font", None)
    if default_font is None:
        default_font = QtGui.QFont(app.font())
        app._xanylabeling_default_font = default_font
    app_font = QtGui.QFont(default_font)
    if font_family:
        app_font.setFamily(font_family)
    app.setFont(app_font)


def scan_all_images(folder_path):
    try:
        extensions = get_supported_image_extensions()

        images = []
        folder_path = osp.normpath(osp.abspath(folder_path))

        for root, _, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(tuple(extensions)):
                    relative_path = osp.normpath(osp.join(root, file))
                    relative_path = str(relative_path)
                    images.append(relative_path)

        try:
            return natsort.natsorted(images)
        except (OSError, ValueError) as e:
            logger.warning(
                f"Warning: Natural sort failed, falling back to regular sort: {e}"
            )
            return sorted(images)
    except Exception as e:
        logger.error(f"Error scanning images: {e}")
        return []


_ICON_RASTER_SIZE = 128
_ICON_PIXMAP_CACHE = {}


def _tinted_pixmap(source, color):
    """Recolor `source`'s opaque pixels to `color`, keeping its alpha shape."""
    out = QtGui.QImage(
        source.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied
    )
    out.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(out)
    painter.setCompositionMode(
        QtGui.QPainter.CompositionMode.CompositionMode_Source
    )
    painter.fillRect(out.rect(), QtGui.QColor(color))
    painter.setCompositionMode(
        QtGui.QPainter.CompositionMode.CompositionMode_DestinationIn
    )
    painter.drawImage(0, 0, source)
    painter.end()
    return QtGui.QPixmap.fromImage(out)


def _icon_pixmaps(path):
    """Normal and disabled rasters for `path`, cached per (path, theme tint).

    Qt generates ``QIcon.Mode.Disabled`` from the source artwork unchanged, so
    a disabled button keeps a full-brightness glyph — on the dark theme that
    made inert controls the most prominent thing on the bar. Registering both
    modes as rasters is what makes the dimmed variant actually win.
    """
    from anylabeling.views.labeling.utils.theme import get_theme

    tint = get_theme()["text_placeholder"]
    key = (path, tint)
    cached = _ICON_PIXMAP_CACHE.get(key)
    if cached is not None:
        return cached

    source = QtGui.QPixmap(path)
    result = (None, None)
    if not source.isNull():
        normal = source.scaled(
            _ICON_RASTER_SIZE,
            _ICON_RASTER_SIZE,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        disabled = _tinted_pixmap(normal.toImage(), tint)
        result = (normal, disabled)

    _ICON_PIXMAP_CACHE[key] = result
    return result


def new_icon(icon, ext="png"):
    path = new_icon_path(icon, ext)
    # QPixmap needs a running QGuiApplication; callers that resolve icons at
    # import time fall back to a plain file-backed icon.
    normal, disabled = (
        _icon_pixmaps(path)
        if QtWidgets.QApplication.instance() is not None
        else (None, None)
    )
    if normal is None:
        return QtGui.QIcon(path)
    qt_icon = QtGui.QIcon()
    qt_icon.addPixmap(normal, QtGui.QIcon.Mode.Normal)
    qt_icon.addPixmap(disabled, QtGui.QIcon.Mode.Disabled)
    return qt_icon


def new_icon_path(icon, ext="png"):
    """Returns the resource path string for an icon."""
    theme_signature, default_stroke, default_fill = _lucide_theme_signature()
    lucide_path = _lucide_icon_path(
        icon, theme_signature, default_stroke, default_fill
    )
    if lucide_path:
        return lucide_path
    return _resource_icon_path(icon, ext)


def new_button(text, icon=None, slot=None):
    b = QtWidgets.QPushButton(text)
    if icon is not None:
        b.setIcon(new_icon(icon))
    if slot is not None:
        b.clicked.connect(slot)
    return b


def new_action(
    parent,
    text,
    slot=None,
    shortcut=None,
    icon=None,
    tip=None,
    checkable=False,
    enabled=True,
    checked=False,
    auto_trigger=False,
):
    """Create a new action and assign callbacks, shortcuts, etc."""
    action = QtGui.QAction(text, parent)
    if icon is not None:
        action.setIconText(text.replace(" ", "\n"))
        action.setIcon(new_icon(icon))
    if shortcut is not None:
        if isinstance(shortcut, (list, tuple)):
            action.setShortcuts(shortcut)
        else:
            action.setShortcut(shortcut)
        # 把快捷键拼进 tooltip，让工具栏按钮悬停时即可发现（QToolButton
        # 不会像菜单那样自动显示 shortcut）。仅拼 tooltip，不拼 statusTip，
        # 避免菜单项右侧已显示的快捷键在状态栏重复出现。
        key_text = ", ".join(
            s.toString(QtGui.QKeySequence.SequenceFormat.NativeText)
            for s in action.shortcuts()
        )
        if tip is not None and key_text:
            tip = f"{tip}  ({key_text})"
    if tip is not None:
        action.setToolTip(tip)
        action.setStatusTip(tip)
    if slot is not None:
        action.triggered.connect(slot)
    if checkable:
        action.setCheckable(True)
    action.setEnabled(enabled)
    action.setChecked(checked)
    if auto_trigger:
        action.triggered.emit(checked)
    return action


class StayOpenMenuFilter(QtCore.QObject):
    """Event filter that keeps a QMenu open when a checkable action is clicked."""

    def eventFilter(self, obj, event):
        if (
            event.type() == QtCore.QEvent.Type.MouseButtonRelease
            and isinstance(obj, QtWidgets.QMenu)
        ):
            action = obj.activeAction()
            if action and action.isCheckable():
                action.trigger()
                return True
        return super().eventFilter(obj, event)


def add_actions(widget, actions):
    for action in actions:
        if action is None:
            widget.addSeparator()
        elif isinstance(action, QtWidgets.QMenu):
            widget.addMenu(action)
        else:
            widget.addAction(action)


def label_validator():
    return QtGui.QRegularExpressionValidator(
        QtCore.QRegularExpression(r"^[^ \t].+"), None
    )


class Struct:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def distance(p):
    return sqrt(p.x() * p.x() + p.y() * p.y())


def distance_to_line(point, line):
    p1, p2 = line
    p1 = np.array([p1.x(), p1.y()])
    p2 = np.array([p2.x(), p2.y()])
    p3 = np.array([point.x(), point.y()])
    if np.dot((p3 - p1), (p2 - p1)) < 0:
        return np.linalg.norm(p3 - p1)
    if np.dot((p3 - p2), (p1 - p2)) < 0:
        return np.linalg.norm(p3 - p2)
    if np.linalg.norm(p2 - p1) == 0:
        return 0
    line_vector = p2 - p1
    point_vector = p1 - p3
    cross_product = (
        line_vector[0] * point_vector[1] - line_vector[1] * point_vector[0]
    )
    return abs(cross_product) / np.linalg.norm(line_vector)


def fmt_shortcut(text):
    mod, key = text.split("+", 1)
    return f"<b>{mod}</b>+<b>{key}</b>"


def on_thumbnail_click(widget):
    def _on_click(event):
        if widget.thumbnail_pixmap and not widget.thumbnail_pixmap.isNull():
            dialog = QtWidgets.QDialog(widget)
            dialog.setWindowTitle(
                widget.tr("Thumbnail - Click anywhere to close")
            )
            dialog.setModal(True)

            main_layout = QtWidgets.QVBoxLayout()
            main_layout.setContentsMargins(0, 0, 0, 0)

            h_layout = QtWidgets.QHBoxLayout()
            h_layout.setContentsMargins(5, 5, 5, 5)
            h_layout.setSpacing(0)

            label = QtWidgets.QLabel()

            screen = QtWidgets.QApplication.primaryScreen()
            screen_size = screen.availableGeometry()
            screen_ratio = 0.35

            pixmap_width = widget.thumbnail_pixmap.width()
            pixmap_height = widget.thumbnail_pixmap.height()

            max_width = int(screen_size.width() * screen_ratio)
            max_height = int(screen_size.height() * screen_ratio)

            width_ratio = max_width / pixmap_width
            height_ratio = max_height / pixmap_height
            scale_ratio = min(width_ratio, height_ratio)

            display_width = int(pixmap_width * scale_ratio)
            display_height = int(pixmap_height * scale_ratio)

            scaled_pixmap = widget.thumbnail_pixmap.scaled(
                display_width,
                display_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            label.setPixmap(scaled_pixmap)
            label.setFixedSize(display_width, display_height)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)

            h_layout.addStretch(1)
            h_layout.addWidget(label)
            h_layout.addStretch(1)

            main_layout.addStretch(1)
            main_layout.addLayout(h_layout)
            main_layout.addStretch(1)

            label.mousePressEvent = lambda e: dialog.accept()
            dialog.mousePressEvent = lambda e: dialog.accept()

            dialog.setLayout(main_layout)

            total_width = display_width + 50
            total_height = display_height + 70
            dialog.setFixedSize(total_width, total_height)

            dialog.move(
                (screen_size.width() - total_width) // 2,
                (screen_size.height() - total_height) // 2,
            )
            dialog.exec()

    return _on_click


def measure_text_width(font_metrics, text):
    if hasattr(font_metrics, "horizontalAdvance"):
        return font_metrics.horizontalAdvance(text)
    return font_metrics.width(text)
