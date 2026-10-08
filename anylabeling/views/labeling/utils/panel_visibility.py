"""Right-sidebar assembly, sizing and visibility toggles.

Split out of LabelingWidget (scripts/extract_method.py); the class keeps
thin stubs so wiring and tests stay put. Since the one-click collapse
landed, this module owns the whole right column: the split view that
makes the sidebar's width -- and the heights of the labels / objects /
files sections -- draggable, the strip that folds the column into 14 px
while collapsed, the per-dock show toggles the settings page edits, and
the footer that owns the app-level controls.
"""

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import QCoreApplication

from ....config import save_config
from .qt import new_icon
from .style import get_sidebar_collapse_strip_style

#: Width of the always-visible strip that carries the collapse button.
SIDEBAR_STRIP_WIDTH = 14

#: Sidebar width used before the user ever drags (px, body only).
DEFAULT_SIDEBAR_WIDTH = 268

#: The section checkboxes that mirror a dock's ``show`` config key.
DOCK_CHECKBOXES = {
    "label_dock": "labels_checkbox",
    "shape_dock": "shapes_checkbox",
}

#: How long a splitter stays quiet before its new sizes are written down.
SIZE_SAVE_DELAY_MS = 600


def set_dock_shown(widget, dock_name, shown):
    """Show/hide one sidebar dock and remember the choice.

    The state rides on the ``<dock>.show`` key the settings page already
    edits, so the section checkbox, the settings row and the startup
    restore are one mechanism with one memory instead of three.
    """
    shown = bool(shown)
    getattr(widget, dock_name).setVisible(shown)
    widget._config[dock_name]["show"] = shown
    save_config(widget._config)


def sync_dock_checkbox(widget, dock_name):
    """Point the section checkbox at the dock's newly applied state.

    Signals are blocked on purpose: the checkbox is the *display* here,
    and bouncing the change back through ``toggled`` would write the
    config a second time for one user action.
    """
    checkbox = getattr(widget, DOCK_CHECKBOXES.get(dock_name, ""), None)
    if checkbox is None:
        return
    checkbox.blockSignals(True)
    checkbox.setChecked(not getattr(widget, dock_name).isHidden())
    checkbox.blockSignals(False)


def _section_header(title):
    """A centered section title, matching the Labels / Objects headers."""
    header = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(header)
    layout.setContentsMargins(0, 2, 0, 2)
    layout.addStretch(1)
    layout.addWidget(QtWidgets.QLabel(title))
    layout.addStretch(1)
    return header


def _add_files_header(files_panel):
    """Give the files card the title row the other two panels have.

    It was the only section with no header at all, so the column read as
    two titled panels and one bare one.
    """
    layout = files_panel.layout()
    if layout is None:
        return
    layout.insertWidget(
        0,
        _section_header(QCoreApplication.translate("LabelingWidget", "文件")),
    )


def _replace_flags_title(widget):
    """Swap the Flags dock's native title bar for our own header.

    Same reasoning as the files header: this was the one section still
    wearing Qt's default bar -- its own height and font, and a close
    button whose feature had already been stripped away.
    """
    widget.flag_dock.setTitleBarWidget(
        _section_header(QCoreApplication.translate("LabelingWidget", "标志"))
    )


def _build_footer(widget, sidebar_layout):
    """App-level controls, below the panels instead of inside one.

    The settings gear shared a row with the file search box, which read
    as "settings for this list"; and the only collapse control used to be
    a caret on the 14 px strip, which therefore had to stay on screen
    even while the sidebar was open. Both live in a footer row now, and
    the strip is shown only while collapsed.
    """
    footer = QtWidgets.QHBoxLayout()
    footer.setContentsMargins(0, 2, 0, 0)
    footer.setSpacing(6)
    footer.addWidget(widget.settings_button, 0)
    footer.addStretch(1)
    collapse = QtWidgets.QToolButton()
    collapse.setObjectName("SidebarFooterCollapse")
    collapse.setAutoRaise(True)
    collapse.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
    collapse.setText(QCoreApplication.translate("LabelingWidget", "收起"))
    collapse.setToolTip(
        QCoreApplication.translate(
            "LabelingWidget",
            "收起右侧面板（标签/对象/文件），给画布腾出空间",
        )
    )
    collapse.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    collapse.clicked.connect(lambda: toggle_sidebar_collapse(widget))
    footer.addWidget(collapse, 0)
    sidebar_layout.addLayout(footer)


def build_main_splitter(widget, central_layout, sidebar_layout, sections):
    """Assemble the split view: canvas | collapsible sidebar column.

    ``sections`` are the four sidebar pieces in display order: the labels
    panel, the objects panel, the file-search row and the files panel --
    they become the draggable lists splitter.

    Two drag handles are the point. The horizontal one lets the sidebar
    be widened or narrowed (it used to be stuck at its size hint); the
    vertical one divides the labels / objects / files sections instead of
    leaving each a third of whatever height was left. The strip is built
    here but shown only while collapsed -- expanded, its 14 px were paid
    for nothing, and the footer's 收起 button carries the toggle.
    """
    labels_panel, objects_panel, file_search_layout, files_panel = sections
    _add_files_header(files_panel)
    _replace_flags_title(widget)
    central = QtWidgets.QWidget()
    central.setObjectName("CentralArea")
    central.setLayout(central_layout)

    lists = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
    lists.setObjectName("SidebarListsSplitter")
    lists.setChildrenCollapsible(False)
    lists.setHandleWidth(6)
    lists.addWidget(labels_panel)
    lists.addWidget(objects_panel)
    files_group = QtWidgets.QWidget()
    files_group_layout = QtWidgets.QVBoxLayout(files_group)
    files_group_layout.setContentsMargins(0, 0, 0, 0)
    files_group_layout.setSpacing(4)
    files_group_layout.addLayout(file_search_layout)
    files_group_layout.addWidget(files_panel)
    lists.addWidget(files_group)
    sidebar_layout.addWidget(lists)
    _build_footer(widget, sidebar_layout)

    strip = QtWidgets.QFrame()
    strip.setObjectName("SidebarCollapseStrip")
    strip.setStyleSheet(get_sidebar_collapse_strip_style())
    strip.setFixedWidth(SIDEBAR_STRIP_WIDTH)
    strip_layout = QtWidgets.QVBoxLayout(strip)
    strip_layout.setContentsMargins(0, 4, 0, 0)
    strip_layout.setSpacing(0)

    button = QtWidgets.QToolButton()
    button.setObjectName("SidebarCollapseButton")
    button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
    button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    button.setFixedSize(SIDEBAR_STRIP_WIDTH, 28)
    button.setIconSize(QtCore.QSize(10, 10))
    button.clicked.connect(lambda: toggle_sidebar_collapse(widget))
    strip_layout.addWidget(
        button,
        0,
        QtCore.Qt.AlignmentFlag.AlignTop
        | QtCore.Qt.AlignmentFlag.AlignHCenter,
    )
    strip_layout.addStretch(1)

    body = QtWidgets.QWidget()
    body.setObjectName("RightSidebar")
    body.setLayout(sidebar_layout)
    body.setMinimumWidth(180)

    wrapper = QtWidgets.QWidget()
    wrapper.setObjectName("RightSidebarWrapper")
    wrapper_layout = QtWidgets.QHBoxLayout(wrapper)
    wrapper_layout.setContentsMargins(0, 0, 0, 0)
    wrapper_layout.setSpacing(0)
    wrapper_layout.addWidget(strip)
    wrapper_layout.addWidget(body)

    main = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
    main.setObjectName("MainSplitter")
    main.setChildrenCollapsible(False)
    main.setHandleWidth(6)
    main.addWidget(central)
    main.addWidget(wrapper)
    main.setStretchFactor(0, 1)
    main.setStretchFactor(1, 0)

    widget.main_splitter = main
    widget.lists_splitter = lists
    widget.sidebar_collapse_strip = strip
    widget.sidebar_collapse_button = button
    widget.right_sidebar = body

    main.splitterMoved.connect(lambda *_: _queue_size_save(widget))
    lists.splitterMoved.connect(lambda *_: _queue_size_save(widget))

    restore_sidebar_state(widget)
    QtCore.QTimer.singleShot(0, lambda: apply_sidebar_sizes(widget))
    return main


def toggle_sidebar_collapse(widget):
    """One-click collapse/expand of the right sidebar (labels/objects/files)."""
    set_sidebar_collapsed(widget, not widget.right_sidebar.isHidden())


def set_sidebar_collapsed(widget, collapsed, persist=True):
    """Collapse or expand the whole right sidebar in one call.

    The state is persisted so a restart does not silently reopen a
    sidebar the user deliberately hid; the startup replay passes
    ``persist=False`` and does not rewrite the config. Resizing follows
    the state, and the handle is disabled while collapsed: a strip that
    could be dragged wide would be a panel with nothing in it. The strip
    itself joins the layout only while collapsed, so the canvas stops
    paying its 14 px the rest of the time.
    """
    collapsed = bool(collapsed)
    if collapsed and not widget.right_sidebar.isHidden():
        # Remember the width the expand has to come back to: the hidden
        # body is resized down to its layout minimum, so its own width
        # is no longer the answer.
        _remember_width(widget)
    widget.right_sidebar.setVisible(not collapsed)
    widget.sidebar_collapse_strip.setVisible(collapsed)
    main = getattr(widget, "main_splitter", None)
    if main is not None:
        main.handle(1).setEnabled(not collapsed)
        apply_sidebar_sizes(widget)

    translate = QCoreApplication.translate
    widget.sidebar_collapse_button.setIcon(
        new_icon("caret-left" if collapsed else "caret-right", "svg")
    )
    widget.sidebar_collapse_button.setToolTip(
        translate("LabelingWidget", "展开右侧面板（标签/对象/文件）")
        if collapsed
        else translate(
            "LabelingWidget",
            "收起右侧面板（标签/对象/文件），给画布腾出空间",
        )
    )

    if persist:
        state = widget._config.setdefault("sidebar", {})
        state["collapsed"] = collapsed
        save_config(widget._config)


def apply_sidebar_sizes(widget):
    """Give the sidebar its remembered width, or the strip when collapsed.

    Runs at startup (once the window has real geometry) and on every
    collapse/expand. A QSplitter keeps its sizes when a child hides, so
    without this the collapse would leave an empty column behind instead
    of handing the width to the canvas.
    """
    main = getattr(widget, "main_splitter", None)
    if main is None or main.width() <= 0:
        return
    if widget.right_sidebar.isHidden():
        total = SIDEBAR_STRIP_WIDTH
    else:
        total = _target_sidebar_width(widget)
    total = min(total, max(SIDEBAR_STRIP_WIDTH, main.width() - 240))
    main.setSizes([max(1, main.width() - total), total])

    lists = getattr(widget, "lists_splitter", None)
    saved = widget._config.get("sidebar")
    sizes = saved.get("lists") if isinstance(saved, dict) else None
    if (
        lists is not None
        and isinstance(sizes, list)
        and len(sizes) == 3
        and all(isinstance(value, (int, float)) for value in sizes)
    ):
        lists.setSizes([int(value) for value in sizes])


def save_sidebar_sizes(widget):
    """Write the current split positions into the config."""
    main = getattr(widget, "main_splitter", None)
    if main is None:
        return
    state = widget._config.setdefault("sidebar", {})
    state["width"] = int(widget.right_sidebar.width())
    lists = getattr(widget, "lists_splitter", None)
    if lists is not None:
        state["lists"] = [int(size) for size in lists.sizes()]
    save_config(widget._config)


def _queue_size_save(widget):
    """Coalesce the flood of ``splitterMoved`` signals into one write."""
    timer = getattr(widget, "_sidebar_save_timer", None)
    if timer is None:
        timer = QtCore.QTimer(widget)
        timer.setSingleShot(True)
        timer.setInterval(SIZE_SAVE_DELAY_MS)
        timer.timeout.connect(lambda: save_sidebar_sizes(widget))
        widget._sidebar_save_timer = timer
    timer.start()


def _target_sidebar_width(widget):
    """Remembered width, else the last on-screen width, else a default.

    The no-memory fallback is capped at :data:`DEFAULT_SIDEBAR_WIDTH`:
    the size hint of the wrapped column is noticeably wider than the
    width this sidebar has always had, and the canvas should not pay for
    the wrapper just because there is nothing saved yet.
    """
    saved = widget._config.get("sidebar")
    width = saved.get("width") if isinstance(saved, dict) else None
    if isinstance(width, int) and width > 0:
        return width
    current = widget.right_sidebar.width()
    if current > 0:
        return min(current, DEFAULT_SIDEBAR_WIDTH)
    return DEFAULT_SIDEBAR_WIDTH


def _remember_width(widget):
    """Bank the current body width so the next expand can restore it."""
    width = int(widget.right_sidebar.width())
    if width <= 0:
        return
    state = widget._config.setdefault("sidebar", {})
    state["width"] = width


def restore_sidebar_state(widget):
    """Replay the remembered collapse state and set the button's look."""
    saved = widget._config.get("sidebar")
    collapsed = isinstance(saved, dict) and bool(saved.get("collapsed"))
    set_sidebar_collapsed(widget, collapsed, persist=False)


def show_attributes_panel(widget):
    if hasattr(widget, "scroll_area"):
        widget.scroll_area.setVisible(True)


def hide_attributes_panel(widget):
    if hasattr(widget, "scroll_area"):
        widget.scroll_area.setVisible(False)
