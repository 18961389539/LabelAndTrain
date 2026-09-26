"""Dialog chrome for the settings window: palette, nav icons, stylesheets.

Split out of :mod:`~anylabeling.views.labeling.settings.dialog`, which was
2434 lines and 94 methods.  These eight pieces are the only cluster in that
class touching nothing but ``_palette`` and ``_nav_icon_size``, which is why
the cut is free: the class keeps thin delegates, so every one of the 76
``self._rgb(...)`` call sites keeps reading the same.

The move is verbatim apart from the mechanical ``self.`` -> ``widget.``
transform that turning class methods into module functions requires, plus
rewriting the 14 internal ``_rgb`` calls to the module function.  That
dedent also shifted the CSS templates in ``scrollbar_style`` /
``radio_style`` / ``message_box_style`` four columns left with their code, so
those three string values are shorter by four characters per continuation
line (1524->1368, 1814->1614, 692->608).  No declaration changed, and Qt
stylesheets do not read indentation: checked against the pre-move methods
loaded from ``HEAD``, they match line for line once leading whitespace is
stripped, and all eight navigation icons come out pixel-identical.
"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui

from anylabeling.views.labeling.utils.qt import new_icon, new_icon_path
from anylabeling.views.labeling.utils.style import get_settings_combo_style
from anylabeling.views.labeling.utils.theme import get_mode, get_theme


def build_palette(widget) -> dict[str, tuple[int, int, int]]:
    theme = get_theme()
    primary_color = QtGui.QColor(theme["primary"])
    primary_rgb = (
        primary_color.red(),
        primary_color.green(),
        primary_color.blue(),
    )
    if get_mode() == "dark":
        return {
            "left_bg": (44, 44, 46),
            "left_text": (174, 174, 178),
            "left_hover": (58, 58, 60),
            "left_selected": (72, 72, 74),
            "left_active_text": primary_rgb,
            "right_bg": (24, 24, 24),
            "card_bg": (44, 44, 46),
            "title_text": (245, 245, 247),
            "desc_text": (174, 174, 178),
            "line": (72, 72, 74),
            "shortcut_middle_bg": (26, 26, 28),
            "shortcut_group_hover": (34, 34, 36),
            "outer_border": (183, 183, 183),
            "close_hover": (58, 58, 60),
            "input_bg": (58, 58, 60),
        }
    return {
        "left_bg": (225, 225, 225),
        "left_text": (144, 144, 144),
        "left_hover": (217, 217, 220),
        "left_selected": (212, 212, 216),
        "left_active_text": primary_rgb,
        "right_bg": (239, 238, 239),
        "card_bg": (234, 234, 235),
        "title_text": (0, 0, 0),
        "desc_text": (144, 144, 144),
        "line": (228, 228, 231),
        "shortcut_middle_bg": (255, 255, 255),
        "shortcut_group_hover": (246, 246, 248),
        "outer_border": (183, 183, 183),
        "close_hover": (217, 217, 220),
        "input_bg": (255, 255, 255),
    }


def rgb(widget, key: str) -> str:
    r, g, b = widget._palette[key]
    return f"rgb({r}, {g}, {b})"


def icon_pixmap(widget, name: str, color: QtGui.QColor) -> QtGui.QPixmap:
    size = widget._nav_icon_size
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    pen = QtGui.QPen(color)
    pen.setWidthF(1.7)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    scale = size / 20.0

    def point(x: float, y: float) -> QtCore.QPointF:
        return QtCore.QPointF(x * scale, y * scale)

    if name == "General":
        knob_radius = 1.6
        slider_rows = (
            (4.8, 15.2, 7.0, 5.8),
            (4.8, 15.2, 12.8, 10.0),
            (4.8, 15.2, 9.4, 14.2),
        )
        for x1, x2, knob_x, y in slider_rows:
            painter.drawLine(
                point(x1, y),
                point(knob_x - knob_radius - 0.8, y),
            )
            painter.drawLine(
                point(knob_x + knob_radius + 0.8, y),
                point(x2, y),
            )
            painter.drawEllipse(
                point(knob_x, y),
                knob_radius * scale,
                knob_radius * scale,
            )
    elif name == "Shortcuts":
        petal_radius = 2.8
        petals = (
            point(7.2, 7.2),
            point(12.8, 7.2),
            point(7.2, 12.8),
            point(12.8, 12.8),
        )
        for petal in petals:
            painter.drawEllipse(
                petal,
                petal_radius * scale,
                petal_radius * scale,
            )
        painter.drawEllipse(point(10.0, 10.0), 0.9 * scale, 0.9 * scale)
    elif name == "Canvas":
        rect = QtCore.QRectF(
            4.4 * scale, 4.4 * scale, 11.2 * scale, 11.2 * scale
        )
        painter.drawRoundedRect(rect, 2.0 * scale, 2.0 * scale)
        painter.drawLine(point(10.0, 5.8), point(10.0, 14.2))
        painter.drawLine(point(5.8, 10.0), point(14.2, 10.0))
    elif name == "Shape":
        points = (
            point(10.0, 4.9),
            point(14.5, 7.5),
            point(14.5, 12.5),
            point(10.0, 15.1),
            point(5.5, 12.5),
            point(5.5, 7.5),
        )
        painter.drawPolygon(QtGui.QPolygonF(points))
        for point in points:
            painter.drawEllipse(point, 1.05 * scale, 1.05 * scale)
    else:
        cx = size / 2
        cy = size / 2
        painter.drawEllipse(QtCore.QPointF(cx, cy), 6.4, 6.4)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QBrush(color))
        for dx in (-3.0, 0.0, 3.0):
            painter.drawEllipse(
                QtCore.QPointF(cx + dx, cy),
                1.2,
                1.2,
            )
    painter.end()
    return pixmap


def brand_logo_pixmap(widget) -> QtGui.QPixmap:
    pixmap = new_icon("icon").pixmap(
        widget._nav_icon_size, widget._nav_icon_size
    )
    if pixmap.isNull():
        return icon_pixmap(
            widget,
            "Brand",
            QtGui.QColor(*widget._palette["left_active_text"]),
        )
    return pixmap.scaled(
        widget._nav_icon_size,
        widget._nav_icon_size,
        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        QtCore.Qt.TransformationMode.SmoothTransformation,
    )


def combo_style(widget) -> str:
    return get_settings_combo_style()


def scrollbar_style(widget) -> str:
    up_arrow = new_icon_path("caret-up", "svg")
    down_arrow = new_icon_path("caret-down", "svg")
    return f"""
        QScrollArea {{
            background: transparent;
            border: none;
        }}
        QScrollBar:vertical {{
            background-color: {rgb(widget, 'right_bg')};
            width: 10px;
            margin: 16px 0 16px 0;
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background-color: {rgb(widget, 'left_text')};
            min-height: 20px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {rgb(widget, 'left_text')};
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            border: none;
            background: {rgb(widget, 'right_bg')};
            height: 16px;
        }}
        QScrollBar::sub-line:vertical {{
            subcontrol-position: top;
            subcontrol-origin: margin;
            image: url({up_arrow});
        }}
        QScrollBar::add-line:vertical {{
            subcontrol-position: bottom;
            subcontrol-origin: margin;
            image: url({down_arrow});
        }}
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
    """


def radio_style(widget) -> str:
    accent = rgb(widget, "left_active_text")
    text = rgb(widget, "title_text")
    border = rgb(widget, "left_text")
    radio_size = 16
    radio_radius = radio_size // 2
    dot_stop = 0.50  # 16px outer ring with ~8px inner dot.
    return f"""
        QRadioButton {{
            color: {text};
            spacing: 6px;
            background: transparent;
        }}
        QRadioButton::indicator {{
            width: {radio_size}px;
            height: {radio_size}px;
            min-width: {radio_size}px;
            min-height: {radio_size}px;
            max-width: {radio_size}px;
            max-height: {radio_size}px;
            border-radius: {radio_radius}px;
        }}
        QRadioButton::indicator:unchecked {{
            border: 1px solid {border};
            background: transparent;
        }}
        QRadioButton::indicator:hover {{
            border: 1px solid {accent};
        }}
        QRadioButton::indicator:checked {{
            border: 1px solid {accent};
            background: qradialgradient(
                cx: 0.5, cy: 0.5,
                fx: 0.5, fy: 0.5,
                radius: 0.5,
                stop: 0 {accent},
                stop: {dot_stop} {accent},
                stop: {dot_stop + 0.01} transparent,
                stop: 1 transparent
            );
        }}
        QRadioButton::indicator:unchecked:disabled {{
            border: 1px solid {border};
            background: transparent;
        }}
        QRadioButton::indicator:checked:disabled {{
            border: 1px solid {accent};
            background: qradialgradient(
                cx: 0.5, cy: 0.5,
                fx: 0.5, fy: 0.5,
                radius: 0.5,
                stop: 0 {accent},
                stop: {dot_stop} {accent},
                stop: {dot_stop + 0.01} transparent,
                stop: 1 transparent
            );
        }}
    """


def message_box_style(widget) -> str:
    return f"""
        QMessageBox {{
            background: {rgb(widget, 'card_bg')};
            color: {rgb(widget, 'title_text')};
        }}
        QMessageBox QLabel {{
            background: transparent;
            color: {rgb(widget, 'title_text')};
        }}
        QMessageBox QPushButton {{
            min-width: 84px;
            min-height: 30px;
            border: 1px solid {rgb(widget, 'line')};
            border-radius: 6px;
            background: {rgb(widget, 'right_bg')};
            color: {rgb(widget, 'title_text')};
            padding: 0 12px;
        }}
        QMessageBox QPushButton:hover {{
            background: {rgb(widget, 'card_bg')};
        }}
    """
