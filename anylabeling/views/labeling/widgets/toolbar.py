"""Defines toolbar for anylabeling, including"""

from PyQt6 import QtCore, QtGui, QtWidgets
from anylabeling.views.labeling.utils.qt import new_icon
from anylabeling.views.labeling.utils.theme import get_mode, get_theme


class FloatingToolPanel(QtWidgets.QFrame):
    #: Emitted when the user finishes dragging the panel (or double-clicks
    #: the grip to reset it), carrying the panel's final position so the
    #: caller can persist it.
    positionCommitted = QtCore.pyqtSignal(int, int)
    #: Emitted whenever the content is collapsed or expanded.
    collapseToggled = QtCore.pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._content_widget = None
        self._dragging = False
        self._drag_offset = QtCore.QPoint()
        self._user_moved = False
        self._collapsed = False

        self.setObjectName("FloatingToolPanel")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        self._handle = QtWidgets.QFrame(self)
        self._handle.setObjectName("FloatingToolPanelHandle")
        self._handle.setFixedHeight(18)
        self._handle.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        self._handle.installEventFilter(self)

        handle_layout = QtWidgets.QHBoxLayout(self._handle)
        handle_layout.setContentsMargins(0, 0, 0, 0)
        handle_layout.setSpacing(0)

        grip = QtWidgets.QLabel("⋮⋮", self._handle)
        grip.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        grip.setObjectName("FloatingToolPanelGrip")
        grip.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
        grip.installEventFilter(self)
        handle_layout.addWidget(grip)

        self._collapse_btn = QtWidgets.QToolButton(self._handle)
        self._collapse_btn.setObjectName("FloatingToolPanelCollapseBtn")
        self._collapse_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._collapse_btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self._collapse_btn.setFixedSize(18, 16)
        self._collapse_btn.setIconSize(QtCore.QSize(12, 12))
        self._collapse_btn.clicked.connect(self.toggle_collapse)
        self._update_collapse_button()
        handle_layout.addWidget(self._collapse_btn)

        layout.addWidget(self._handle)

        self._content_layout = QtWidgets.QVBoxLayout()
        self._content_layout.setSpacing(0)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._content_layout)

        self._apply_style()

    def _apply_style(self):
        t = get_theme()
        self.setStyleSheet(f"""
            QFrame#FloatingToolPanel {{
                background: {t["background_secondary"]};
                border: 1px solid {t["border_light"]};
                border-radius: 12px;
            }}
            QFrame#FloatingToolPanelHandle {{
                background: {t["surface"]};
                border: 1px solid {t["border"]};
                border-radius: 7px;
            }}
            QLabel#FloatingToolPanelGrip {{
                color: {t["text_secondary"]};
                font-size: 10px;
                font-weight: 700;
            }}
            QToolButton#FloatingToolPanelCollapseBtn {{
                border: none;
                background: transparent;
                color: {t["text_secondary"]};
                font-size: 9px;
                padding: 0px;
            }}
            QToolButton#FloatingToolPanelCollapseBtn:hover {{
                color: {t["text"]};
                background: {t["background_hover"]};
                border-radius: 4px;
            }}
        """)

    def _update_collapse_button(self):
        if self._collapsed:
            self._collapse_btn.setIcon(new_icon("caret-up", "svg"))
            self._collapse_btn.setToolTip(self.tr("展开工具栏"))
        else:
            self._collapse_btn.setIcon(new_icon("caret-down", "svg"))
            self._collapse_btn.setToolTip(self.tr("收起工具栏"))

    def toggle_collapse(self):
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed):
        collapsed = bool(collapsed)
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self._update_collapse_button()
        if self._content_widget is not None:
            self._content_widget.setVisible(not collapsed)
        self.sync_to_parent()
        self.collapseToggled.emit(collapsed)

    def is_collapsed(self):
        return self._collapsed

    def set_saved_position(self, x, y):
        """Restore a previously persisted position (e.g. from config).

        The panel is treated as user-moved so later syncs don't snap it
        back to the default corner.
        """
        self.move(int(x), int(y))
        self._user_moved = True
        self._clamp_to_parent()
        self.raise_()

    def user_position(self):
        return QtCore.QPoint(self.x(), self.y()) if self._user_moved else None

    def set_content_widget(self, widget):
        if self._content_widget is widget:
            return
        if self._content_widget is not None:
            self._content_layout.removeWidget(self._content_widget)
        self._content_widget = widget
        if widget is not None:
            widget.setParent(self)
            self._content_layout.addWidget(widget)
            widget.show()
        self.sync_to_parent()

    def default_position(self):
        return QtCore.QPoint(8, 8)

    def reset_position(self):
        self._user_moved = False
        self.move(self.default_position())
        self.raise_()

    def _content_height_hint(self):
        """How tall the content actually wants to be.

        A QScrollArea reports its own small default hint rather than the
        toolbar inside it, so sizing the panel from ``sizeHint()`` collapsed it
        to a single button with everything else behind a scrollbar. A plain
        fixed-size frame goes the other way: its ``sizeHint()`` is invalid and
        only ``minimumHeight()`` carries the number. Every source is consulted
        and the largest wins.
        """
        content = self._content_widget
        candidates = [content.sizeHint().height(), content.minimumHeight()]
        inner = getattr(content, "widget", None)
        widget = inner() if callable(inner) else None
        if widget is not None:
            candidates.append(widget.sizeHint().height())
            candidates.append(widget.minimumHeight())
        usable = [value for value in candidates if value > 0]
        return max(usable) if usable else 0

    def sync_to_parent(self):
        parent = self.parentWidget()
        if parent is None:
            return
        if self._content_widget is not None:
            available_height = max(120, parent.height() - 16)
            handle_height = self._handle.height()
            margins = self.layout().contentsMargins()
            spacing = self.layout().spacing()
            content_max_height = max(
                72,
                available_height
                - handle_height
                - margins.top()
                - margins.bottom()
                - spacing,
            )
            needed = self._content_height_hint()
            content_height = (
                content_max_height
                if needed <= 0
                else min(content_max_height, needed)
            )
            # A maximum alone leaves the panel at its sizeHint, which for a
            # scroll area is the small default above.
            self._content_widget.setMinimumHeight(content_height)
            self._content_widget.setMaximumHeight(content_height)
            self.setMaximumHeight(available_height)
        self.adjustSize()
        if not self._user_moved:
            self.move(self.default_position())
        self._clamp_to_parent()
        self.raise_()

    def _clamp_to_parent(self):
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 8
        max_x = max(margin, parent.width() - self.width() - margin)
        max_y = max(margin, parent.height() - self.height() - margin)
        x = min(max(self.x(), margin), max_x)
        y = min(max(self.y(), margin), max_y)
        self.move(x, y)

    def eventFilter(self, obj, event):
        if obj not in {self._handle} and obj.parent() is not self._handle:
            return super().eventFilter(obj, event)
        if event.type() == QtCore.QEvent.Type.MouseButtonPress:
            if event.button() == QtCore.Qt.MouseButton.LeftButton:
                self._dragging = True
                self._drag_offset = (
                    event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                )
                self._handle.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                return True
        elif event.type() == QtCore.QEvent.Type.MouseButtonDblClick:
            if event.button() == QtCore.Qt.MouseButton.LeftButton:
                self.reset_position()
                self.positionCommitted.emit(self.x(), self.y())
                return True
        elif event.type() == QtCore.QEvent.Type.MouseMove and self._dragging:
            parent = self.parentWidget()
            if parent is None:
                return True
            target = parent.mapFromGlobal(
                event.globalPosition().toPoint() - self._drag_offset
            )
            self.move(target)
            self._clamp_to_parent()
            self._user_moved = True
            return True
        elif event.type() == QtCore.QEvent.Type.MouseButtonRelease and self._dragging:
            self._dragging = False
            self._handle.setCursor(QtCore.Qt.CursorShape.OpenHandCursor)
            if self._user_moved:
                self.positionCommitted.emit(self.x(), self.y())
            return True
        return super().eventFilter(obj, event)


class ToolBar(QtWidgets.QFrame):
    """Toolbar widget for labeling tool"""

    def __init__(self, title):
        super().__init__()
        self.setWindowTitle(title)
        self._orientation = QtCore.Qt.Orientation.Vertical
        self._tool_button_style = QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly
        self._icon_size = QtCore.QSize(24, 24)
        self._owned_widgets = []

        self._button_size = QtCore.QSize(30, 30)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        self._content_widget = QtWidgets.QWidget(self)
        self._content_widget.setObjectName("ToolBarContent")
        self._content_layout = QtWidgets.QVBoxLayout(self._content_widget)
        self._content_layout.setSpacing(0)
        self._content_layout.setContentsMargins(3, 4, 3, 4)
        layout.addWidget(
            self._content_widget, 0, QtCore.Qt.AlignmentFlag.AlignTop
        )
        layout.addStretch(1)
        self.setContentsMargins(0, 0, 0, 0)
        self.setWindowFlags(
            self.windowFlags() | QtCore.Qt.WindowType.FramelessWindowHint
        )

        self._is_dark = get_mode() == "dark"
        t = get_theme()
        separator_color = t["border_light"] if self._is_dark else t["border"]
        base_bg = t["button_bg"] if self._is_dark else t["surface"]
        hover_bg = t["button_hover"] if self._is_dark else t["button_bg"]
        # Same accent-tinted treatment in both themes: light mode previously
        # reused a near-identical grey for the active tool, so the current
        # drawing mode was indistinguishable from an idle button.
        checked_bg = t["primary_soft"]
        checked_border = t["primary"]
        self.setStyleSheet(f"""
            ToolBar {{
                background: {t["background_secondary"]};
                border: 1px solid {t["border_light"]};
                border-radius: 10px;
            }}
            QWidget#ToolBarContent {{
                background: transparent;
            }}
            ToolBar QToolButton {{
                min-width: 30px;
                min-height: 30px;
                max-width: 30px;
                max-height: 30px;
                border: 1px solid {t["border"]};
                border-radius: 8px;
                background: {base_bg};
                padding: 0px;
                margin: 0px;
            }}
            ToolBar QToolButton:hover:!disabled {{
                background: {hover_bg};
                border-color: {t["border_light"]};
            }}
            ToolBar QToolButton:pressed:!disabled,
            ToolBar QToolButton:checked:!disabled {{
                background: {checked_bg};
                border-color: {checked_border};
            }}
            ToolBar QToolButton:disabled {{
                background: {t["background_secondary"]};
                border-color: {t["border"]};
            }}
            QFrame#ToolBarSeparator {{
                background: {separator_color};
                border-radius: 1px;
            }}
            """)

    def sizeHint(self):
        hint = self._content_widget.sizeHint()
        margins = self.layout().contentsMargins()
        frame = self.frameWidth() * 2
        return QtCore.QSize(
            hint.width() + margins.left() + margins.right() + frame,
            hint.height() + margins.top() + margins.bottom() + frame,
        )

    def minimumSizeHint(self):
        return self.sizeHint()

    def setOrientation(self, orientation):
        self._orientation = orientation

    def setToolButtonStyle(self, style):
        self._tool_button_style = style
        for button in self.findChildren(QtWidgets.QToolButton):
            button.setToolButtonStyle(style)

    def toolButtonStyle(self):
        return self._tool_button_style

    def setIconSize(self, size):
        self._icon_size = size
        for button in self.findChildren(QtWidgets.QToolButton):
            button.setIconSize(size)

    def iconSize(self):
        return self._icon_size

    def widgetForAction(self, action):
        """Return the QToolButton bound to action (QToolBar-compatible)."""
        for widget in self._owned_widgets:
            if (
                isinstance(widget, QtWidgets.QToolButton)
                and widget.defaultAction() is action
            ):
                return widget
        return None

    def clear(self):
        for action in self.actions():
            self.removeAction(action)
        self.setMinimumHeight(0)
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is None:
                continue
            if widget in self._owned_widgets:
                widget.deleteLater()
            else:
                widget.setParent(None)
        self._owned_widgets = []

    def addAction(self, action):
        if isinstance(action, QtWidgets.QWidgetAction):
            super().addAction(action)
            widget = action.defaultWidget()
            if widget is not None:
                self._content_layout.addWidget(
                    widget, 0, QtCore.Qt.AlignmentFlag.AlignCenter
                )
                widget.show()
            return action

        super().addAction(action)
        btn = QtWidgets.QToolButton(self)
        btn.setDefaultAction(action)
        btn.setToolButtonStyle(self.toolButtonStyle())
        btn.setIconSize(self._icon_size)
        btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(self._button_size)
        self._owned_widgets.append(btn)
        self._content_layout.addWidget(
            btn, 0, QtCore.Qt.AlignmentFlag.AlignCenter
        )
        return action

    def addSeparator(self):
        action = QtGui.QAction(self)
        action.setSeparator(True)
        super().addAction(action)
        separator = QtWidgets.QFrame(self)
        separator.setObjectName("ToolBarSeparator")
        if self._orientation == QtCore.Qt.Orientation.Vertical:
            separator.setFixedSize(16, 1)
            separator.setContentsMargins(5, 2, 5, 2)
        else:
            separator.setFixedSize(2, 24)
        self._owned_widgets.append(separator)
        self._content_layout.addWidget(
            separator, 0, QtCore.Qt.AlignmentFlag.AlignCenter
        )
        return action

    def add_action(self, action):
        """Add an action (button) to the toolbar"""
        return self.addAction(action)
