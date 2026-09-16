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
    "auto-run": {"name": "play", "ext": "svg"},
    "arrow-right": {"name": "arrow-right", "ext": "svg"},
    "arrow-left": {"name": "arrow-left", "ext": "svg"},
    "brain": {"name": "brain", "ext": "svg"},
    "brush": {"name": "brush", "ext": "png"},
    "brush_polygon": {"name": "brush", "ext": "png"},
    "cancel": {"name": "x", "ext": "png"},
    "caret-left": {"name": "chevron-left", "ext": "svg"},
    "caret-down": {"name": "chevron-down", "ext": "svg"},
    "caret-right": {"name": "chevron-right", "ext": "svg"},
    "caret-up": {"name": "chevron-up", "ext": "svg"},
    "cartesian": {"name": "crosshair", "ext": "png"},
    "check": {"name": "check", "ext": "svg"},
    "checkmark": {"name": "check", "ext": "svg", "stroke": "#0D9488"},
    "checkmark-white": {
        "name": "check",
        "ext": "svg",
        "stroke": "#ffffff",
    },
    "circle-selection": {"name": "circle-dot", "ext": "png"},
    "color": {"name": "palette"},
    "convert": {"name": "shuffle", "ext": "png"},
    "copy": {"name": "copy"},
    "copy-green": {
        "name": "circle-check-big",
        "ext": "svg",
        "stroke": "#16a34a",
    },
    "crop": {"name": "crop", "ext": "png"},
    "delete": {"name": "trash", "ext": "png"},
    "digit0": {"name": "square", "ext": "png", "digit": "0"},
    "digit1": {"name": "square", "ext": "png", "digit": "1"},
    "digit2": {"name": "square", "ext": "png", "digit": "2"},
    "digit3": {"name": "square", "ext": "png", "digit": "3"},
    "digit4": {"name": "square", "ext": "png", "digit": "4"},
    "digit5": {"name": "square", "ext": "png", "digit": "5"},
    "digit6": {"name": "square", "ext": "png", "digit": "6"},
    "digit7": {"name": "square", "ext": "png", "digit": "7"},
    "digit8": {"name": "square", "ext": "png", "digit": "8"},
    "digit9": {"name": "square", "ext": "png", "digit": "9"},
    "done": {"name": "circle-check-big", "ext": "png"},
    "edit": {"name": "pencil", "ext": "png"},
    "eraser": {"name": "eraser", "ext": "svg"},
    "error": {
        "name": "circle-alert",
        "ext": "svg",
        "stroke": "#dc2626",
    },
    "eye": {"name": "eye"},
    "file": {"name": "image", "ext": "png"},
    "fit-window": {"name": "maximize", "ext": "png"},
    "fit-width": {"name": "move-horizontal", "ext": "png"},
    "folder": {"name": "folder", "ext": "svg"},
    "hidden": {"name": "eye-off", "ext": "png"},
    "icon": {"name": "scan-search", "ext": "png", "stroke": "#0D9488"},
    "label": {"name": "tag", "ext": "png"},
    "labels": {"name": "tags", "ext": "png"},
    "lock": {"name": "lock", "ext": "svg"},
    "loop": {"name": "repeat", "ext": "png"},
    "navigator": {"name": "map", "ext": "svg"},
    "open": {"name": "folder-open", "ext": "png"},
    "overview": {"name": "layout-dashboard", "ext": "png"},
    "paste": {"name": "clipboard-paste", "ext": "png"},
    "point": {"name": "circle-dot", "ext": "png"},
    "polygon": {"name": "pentagon", "ext": "png"},
    "prev": {"name": "arrow-left", "ext": "svg"},
    "rectangle": {"name": "square", "ext": "png"},
    "redo": {"name": "redo-2", "ext": "png"},
    "search": {"name": "search", "ext": "svg"},
    "settings": {"name": "settings", "ext": "svg"},
    "star": {"name": "star", "ext": "svg"},
    "starred": {
        "name": "star",
        "ext": "svg",
        "fill": "currentColor",
    },
    "trash": {"name": "trash", "ext": "svg"},
    "undo": {"name": "undo-2", "ext": "png"},
    "union": {"name": "combine", "ext": "png"},
    "ultralytics": {"name": "scan-search", "ext": "png"},
    "next": {"name": "arrow-right", "ext": "svg"},
    "save": {"name": "save", "ext": "svg"},
    "save-as": {"name": "save", "ext": "svg"},
    "warning": {
        "name": "triangle-alert",
        "ext": "svg",
        "stroke": "#d97706",
    },
    "zoom": {"name": "scan-search", "ext": "png"},
    "zoom-in": {"name": "zoom-in", "ext": "png"},
    "zoom-out": {"name": "zoom-out", "ext": "png"},
}


def _resource_icon_path(icon, ext):
    return osp.join(f":/images/images/{icon}.{ext}")


def _normalize_icon_path(path):
    return path.replace("\\", "/")


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
def _lucide_icon_path(icon, ext):
    if lucide_icon is None:
        return None
    spec = _LUCIDE_ICON_MAP.get(icon)
    if not spec:
        return None
    target_ext = spec.get("ext", ext)
    if target_ext != ext:
        return None
    lucide_name = spec["name"]
    try:
        svg = lucide_icon(
            lucide_name,
            width="24",
            height="24",
            stroke=spec.get("stroke", "currentColor"),
            fill=spec.get("fill", "none"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to render Lucide icon %s: %s", lucide_name, exc)
        return None
    svg = _decorate_lucide_svg(svg, spec)

    os.makedirs(_LUCIDE_CACHE_DIR, exist_ok=True)
    cache_name = f"{icon}.svg"
    cache_path = osp.join(_LUCIDE_CACHE_DIR, cache_name)
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


def new_icon(icon, ext="png"):
    return QtGui.QIcon(new_icon_path(icon, ext))


def new_icon_path(icon, ext="png"):
    """Returns the resource path string for an icon."""
    lucide_path = _lucide_icon_path(icon, ext)
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
