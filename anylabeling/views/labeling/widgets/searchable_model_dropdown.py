from difflib import SequenceMatcher

from PyQt6.QtWidgets import (
    QLabel,
    QLineEdit,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QButtonGroup,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon

from anylabeling.config import get_work_directory
from anylabeling.views.labeling.ai.config import *
from anylabeling.views.labeling.utils._io import load_json, save_json
from anylabeling.views.labeling.utils.model_task_groups import (
    TASK_FILTER_ORDER,
    TASK_GROUP_LABELS,
    group_for_model_type,
)
from anylabeling.views.labeling.utils.qt import new_icon, new_icon_path
from anylabeling.views.labeling.utils.theme import get_theme


def _get_models_config_path():
    return os.path.join(
        get_work_directory(), "xanylabeling_data", "models.json"
    )


def _model_is_local(model_name):
    """Best-effort check whether model files already exist on disk.

    Weights live under <work_dir>/xanylabeling_data/models/<model_name>/.
    A non-empty directory with at least one *complete* file means the model
    was downloaded at least once, so the dropdown can label it before the
    user picks it.  Interrupted downloads leave ``*.part`` files behind and
    are *not* treated as local, otherwise the "本地" badge misleads users
    into thinking the model is ready when it is not.
    """
    try:
        model_dir = os.path.join(
            get_work_directory(),
            "xanylabeling_data",
            "models",
            model_name,
        )
        if not os.path.isdir(model_dir):
            return False
        for entry in os.listdir(model_dir):
            if entry.endswith(".part"):
                # In-progress download residue; not a usable model yet.
                continue
            full_path = os.path.join(model_dir, entry)
            if os.path.isfile(full_path) and os.path.getsize(full_path) > 0:
                return True
        return False
    except OSError:
        return False


class SearchBar(QLineEdit):
    def __init__(self, parent=None, placeholder_text: str = "Search models"):
        super().__init__(parent)
        t = get_theme()
        self.setPlaceholderText(placeholder_text)
        self.setFixedHeight(DEFAULT_FIXED_HEIGHT)
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {t["background_secondary"]};
                color: {t["text"]};
                border: 1px solid {t["border"]};
                border-radius: {BORDER_RADIUS};
                padding: 5px 5px 5px 32px;
                font-size: {FONT_SIZE_SMALL};
            }}
            QLineEdit:focus {{
                border: 2px solid {t["highlight"]};
            }}
        """)

        self.search_icon = QLabel(self)
        self.search_icon.setPixmap(
            QIcon(new_icon("search", "svg")).pixmap(QSize(*ICON_SIZE_SMALL))
        )
        self.search_icon.setFixedSize(self.search_icon.pixmap().size())
        self.search_icon.setStyleSheet("background-color: transparent;")
        self.resizeEvent = self.on_resize

    def on_resize(self, event):
        icon_height = self.search_icon.height()
        y_position = (self.height() - icon_height) // 2
        self.search_icon.move(10, y_position)

        super().resizeEvent(event)


class ProviderSection(QFrame):
    def __init__(self, provider_name, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        # Provider header
        header = QHBoxLayout()
        icon = QLabel()
        if provider_name in ("Favorites", "推荐"):
            icon_name, ext = "star-black", "svg"
        elif provider_name == "Custom":
            icon_name, ext = "logo", "png"
        elif provider_name == "CVHub":
            icon_name, ext = "cvhub", "png"
        elif provider_name == "ETH Zürich":
            icon_name, ext = "eth", "png"
        else:
            icon_name, ext = provider_name.lower(), "png"
        icon.setPixmap(
            QIcon(new_icon(icon_name, ext)).pixmap(QSize(*ICON_SIZE_SMALL))
        )
        header.addWidget(icon)

        _t = get_theme()
        label = QLabel(provider_name)
        label.setStyleSheet(f"""
            font-weight: 700;
            font-size: 13px;
            color: {_t["text"]};
        """)
        header.addWidget(label)
        header.addStretch()
        layout.addLayout(header)

        # Container for model items
        self.models_container = QVBoxLayout()
        self.models_container.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.models_container)

    def add_model_item(self, model_item):
        self.models_container.addWidget(model_item)


class ModelItem(QFrame):
    clicked = pyqtSignal(str)
    favoriteToggled = pyqtSignal(str, bool)
    removeRequested = pyqtSignal(str)

    def __init__(
        self,
        model_name,
        model_data,
        in_favorites_section=False,
        has_local=False,
        removable=False,
        parent=None,
    ):
        super().__init__(parent)
        self.model_name = model_name
        self.model_data = model_data
        self.is_selected = model_data.get("selected", False)
        self.is_favorite = model_data.get("favorite", False)
        self.display_name = model_data.get("display_name", model_name)
        self.in_favorites_section = in_favorites_section
        self.has_local = has_local
        self.removable = removable

        self.setFixedHeight(DEFAULT_FIXED_HEIGHT)
        self.setFrameShape(QFrame.Shape.NoFrame)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        _t = get_theme()
        if model_data.get("recommended"):
            rec_chip = QLabel("推荐")
            rec_chip.setToolTip("该任务类型的推荐模型")
            rec_chip.setStyleSheet(
                "font-size: 10px; color: #F5A524; "
                "background: transparent; border: none; padding-right: 4px;"
            )
            layout.addWidget(rec_chip, 0, Qt.AlignmentFlag.AlignVCenter)
        if has_local:
            local_chip = QLabel("本地")
            local_chip.setToolTip("Model files already downloaded locally")
            local_chip.setStyleSheet(
                "font-size: 10px; color: #30D158; "
                "background: transparent; border: none; padding-right: 4px;"
            )
            layout.addWidget(local_chip, 0, Qt.AlignmentFlag.AlignVCenter)
        self.name_label = QLabel(self.display_name)
        self.name_label.setStyleSheet(
            f"font-size: {FONT_SIZE_SMALL}; color: {_t['text']}; background: transparent;"
        )
        layout.addWidget(self.name_label)
        layout.addStretch()

        # Checkmark for selected item
        self.check_icon = QLabel()
        self.check_icon.setStyleSheet("background: transparent; border: none;")
        self.check_icon.setFixedSize(QSize(*ICON_SIZE_SMALL))
        if self.is_selected:
            self.check_icon.setPixmap(
                QIcon(new_icon("check", "svg")).pixmap(QSize(*ICON_SIZE_SMALL))
            )
        layout.addWidget(self.check_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        # Favorite star (initially hidden, shows on hover)
        self.star_icon = QPushButton()
        self.star_icon.setFixedSize(*ICON_SIZE_SMALL)
        self.star_icon.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
            }
        """)
        if self.is_favorite:
            self.star_icon.setIcon(QIcon(new_icon("starred", "svg")))
            if self.in_favorites_section:
                self.star_icon.setVisible(False)
        else:
            self.star_icon.setIcon(QIcon(new_icon("star", "svg")))
            self.star_icon.setVisible(False)

        self.star_icon.clicked.connect(self.toggle_favorite)
        layout.addWidget(self.star_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        # Remove (trash) button for custom models: hover-revealed so it does
        # not clutter the list, but always available for custom entries.
        self.remove_icon = QPushButton()
        self.remove_icon.setFixedSize(*ICON_SIZE_SMALL)
        self.remove_icon.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
            }
        """)
        self.remove_icon.setIcon(QIcon(new_icon("trash", "svg")))
        self.remove_icon.setToolTip("Remove this custom model")
        self.remove_icon.setVisible(False)
        self.remove_icon.clicked.connect(self.request_remove)
        layout.addWidget(self.remove_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        t = get_theme()
        self.setStyleSheet(f"""
            ModelItem {{
                background-color: transparent;
                border-radius: 4px;
            }}
            ModelItem:hover {{
                background-color: {t["surface_hover"]};
            }}
        """)

    def enterEvent(self, event):
        self.star_icon.setVisible(True)
        if self.removable:
            self.remove_icon.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.in_favorites_section or not self.is_favorite:
            self.star_icon.setVisible(False)
        if self.removable:
            self.remove_icon.setVisible(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.clicked.emit(self.model_name)
        super().mousePressEvent(event)

    def request_remove(self):
        self.removeRequested.emit(self.model_name)

    def toggle_favorite(self):
        self.is_favorite = not self.is_favorite
        if self.is_favorite:
            self.star_icon.setIcon(QIcon(new_icon("starred", "svg")))
        else:
            self.star_icon.setIcon(QIcon(new_icon("star", "svg")))
        self.favoriteToggled.emit(self.model_name, self.is_favorite)

    def update_selection(self, is_selected):
        self.is_selected = is_selected
        t = get_theme()
        if is_selected:
            self.check_icon.setPixmap(
                QIcon(new_icon("check", "svg")).pixmap(QSize(*ICON_SIZE_SMALL))
            )
            self.setStyleSheet(
                f"background-color: {t['surface_pressed']}; border-radius: 4px;"
            )
        else:
            self.check_icon.clear()
            self.setStyleSheet("""
                background-color: transparent;
                border-radius: 4px;
            """)

    def update_favorite(self, is_favorite):
        self.is_favorite = is_favorite
        if is_favorite:
            self.star_icon.setIcon(QIcon(new_icon("starred", "svg")))
        else:
            self.star_icon.setIcon(QIcon(new_icon("star", "svg")))
        self.star_icon.setVisible(is_favorite or self.underMouse())


class SearchableModelDropdownPopup(QWidget):
    modelSelected = pyqtSignal(str, str)
    modelRemoveRequested = pyqtSignal(str, str)

    def __init__(self, models_data: dict = {}, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.setMinimumWidth(360)
        self.setFixedHeight(640)

        t = get_theme()
        self.setStyleSheet(f"""
            SearchableModelDropdownPopup {{
                background-color: {t["surface"]};
                border-radius: 8px;
            }}
            QWidget, QFrame {{
                background-color: {t["surface"]};
            }}
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background-color: {t["background_secondary"]};
                width: 10px;
                margin: 16px 0 16px 0;
            }}
            QScrollBar::handle:vertical {{
                background-color: {t["scrollbar"]};
                min-height: 20px;
                border-radius: 5px;
            }}
            QScrollBar::add-line:vertical {{
                border: none;
                background: {t["background_secondary"]};
                height: 16px;
                subcontrol-position: bottom;
                subcontrol-origin: margin;
                image: url({new_icon_path("caret-down", "svg")});
            }}
            QScrollBar::sub-line:vertical {{
                border: none;
                background: {t["background_secondary"]};
                height: 16px;
                subcontrol-position: top;
                subcontrol-origin: margin;
                image: url({new_icon_path("caret-up", "svg")});
            }}
            QFrame[frameShape="4"] {{
                color: {t["border"]};
                max-height: 1px;
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # Search bar
        self.search_bar = SearchBar()
        self.search_bar.textChanged.connect(self.filter_models)
        main_layout.addWidget(self.search_bar)

        self._task_filter = "all"
        self._search_text = ""
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self._task_filter_buttons = {}
        self._task_filter_group = QButtonGroup(self)
        self._task_filter_group.setExclusive(True)
        for group in TASK_FILTER_ORDER:
            button = QPushButton(TASK_GROUP_LABELS[group])
            button.setCheckable(True)
            button.setChecked(group == "all")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                f"""
                QPushButton {{
                    background: {t["background_secondary"]};
                    color: {t["text"]};
                    border: 1px solid {t["border"]};
                    border-radius: 12px;
                    padding: 2px 10px;
                    font-size: 11px;
                }}
                QPushButton:checked {{
                    background: {t["primary"]};
                    color: white;
                    border-color: {t["primary"]};
                }}
                """
            )
            self._task_filter_group.addButton(button)
            button.clicked.connect(
                lambda _checked=False, g=group: self.set_task_filter(g)
            )
            filter_row.addWidget(button)
            self._task_filter_buttons[group] = button
        filter_row.addStretch()
        main_layout.addLayout(filter_row)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        container = QWidget()
        self.container_layout = QVBoxLayout(container)
        self.container_layout.setContentsMargins(0, 8, 0, 8)
        self.container_layout.setSpacing(8)

        scroll_area.setWidget(container)
        main_layout.addWidget(scroll_area)

        self.model_items = {}
        self.models_data = models_data
        self.setup_model_list()

    def _is_removable_model(self, provider, model_name):
        """Only user-added custom models can be removed from the list.

        Built-in presets (github / modelscope / CVHub ...) are static and
        must not disappear; the pseudo-entry "load_custom_model" is the
        "add" action itself.
        """
        return (
            provider == "Custom"
            and model_name.startswith("_custom_")
            and model_name != "load_custom_model"
        )

    def request_model_remove(self, model_name):
        """Forward a remove request to the owning widget for confirmation."""
        for provider, models in self.models_data.items():
            if model_name in models:
                self.modelRemoveRequested.emit(provider, model_name)
                return

    def setup_model_list(self):
        # Clear existing widgets
        for i in reversed(range(self.container_layout.count())):
            item = self.container_layout.itemAt(i)
            if not item:
                continue
            widget = item.widget()
            if widget:
                widget.deleteLater()
            elif item.spacerItem():
                self.container_layout.removeItem(item)

        self.model_items = {}

        recommended = []
        favorites = []
        for provider, models in self.models_data.items():
            for model_name, model_data in models.items():
                if model_data.get("recommended"):
                    recommended.append((provider, model_name, model_data))
                if model_data.get("favorite", False):
                    favorites.append((provider, model_name, model_data))

        if recommended:
            rec_section = ProviderSection("推荐")
            self.container_layout.addWidget(rec_section)
            for provider, model_name, model_data in recommended:
                model_item = ModelItem(
                    model_name,
                    model_data,
                    in_favorites_section=True,
                    has_local=_model_is_local(model_name),
                    removable=self._is_removable_model(provider, model_name),
                )
                model_item.clicked.connect(self.select_model)
                model_item.favoriteToggled.connect(self.toggle_favorite)
                model_item.removeRequested.connect(self.request_model_remove)
                rec_section.add_model_item(model_item)
                self.model_items[model_name] = model_item
            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFrameShadow(QFrame.Shadow.Plain)
            self.container_layout.addWidget(separator)

        # Add favorites section
        favorites = []
        for provider, models in self.models_data.items():
            for model_name, model_data in models.items():
                if model_data.get("favorite", False):
                    favorites.append((provider, model_name, model_data))

        if favorites:
            fav_section = ProviderSection("Favorites")
            self.container_layout.addWidget(fav_section)

            for provider, model_name, model_data in favorites:
                model_item = ModelItem(
                    model_name,
                    model_data,
                    in_favorites_section=True,
                    has_local=_model_is_local(model_name),
                    removable=self._is_removable_model(provider, model_name),
                )
                model_item.clicked.connect(self.select_model)
                model_item.favoriteToggled.connect(self.toggle_favorite)
                model_item.removeRequested.connect(self.request_model_remove)
                fav_section.add_model_item(model_item)
                self.model_items[model_name] = model_item

            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFrameShadow(QFrame.Shadow.Plain)
            self.container_layout.addWidget(separator)

        # Add provider sections
        for provider, models in self.models_data.items():
            if not models:
                continue

            provider_section = ProviderSection(provider)
            self.container_layout.addWidget(provider_section)

            for model_name, model_data in models.items():
                model_item = ModelItem(
                    model_name,
                    model_data,
                    has_local=_model_is_local(model_name),
                    removable=self._is_removable_model(provider, model_name),
                )
                model_item.clicked.connect(self.select_model)
                model_item.favoriteToggled.connect(self.toggle_favorite)
                model_item.removeRequested.connect(self.request_model_remove)
                provider_section.add_model_item(model_item)
                self.model_items[model_name] = model_item

            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFrameShadow(QFrame.Shadow.Plain)
            self.container_layout.addWidget(separator)

        # Add stretch at the end to push content to the top
        self.container_layout.addStretch()

        # Force layout update
        self.container_layout.update()
        self.container_layout.parentWidget().adjustSize()
        self.adjustSize()

    def select_model(self, model_name):
        # Unselect all models
        for provider, models in self.models_data.items():
            for name, data in models.items():
                data["selected"] = False
                if name in self.model_items:
                    self.model_items[name].update_selection(False)
                    self.models_data[provider][name]["selected"] = False

        # Select the clicked model
        for provider, models in self.models_data.items():
            if model_name in models:
                models[model_name]["selected"] = True
                self.model_items[model_name].update_selection(True)
                self.models_data[provider][model_name]["selected"] = True
                self.save_models_data()
                self.modelSelected.emit(provider, model_name)
                break

        self.close()
        self.container_layout.parentWidget().adjustSize()
        self.adjustSize()

    def update_models_data(self, models_data: dict):
        self.models_data = models_data
        self.setup_model_list()

    def toggle_favorite(self, model_name, is_favorite):
        for provider, models in self.models_data.items():
            if model_name in models:
                self.models_data[provider][model_name][
                    "favorite"
                ] = is_favorite
                break

        # Rebuild the entire list to reflect changes
        self.save_models_data()
        self.setup_model_list()

    def save_models_data(self):
        """Save models data to the config file"""
        models_config_path = _get_models_config_path()
        if not os.path.exists(models_config_path):
            model_config = {"models_data": {}}
        else:
            model_config = load_json(models_config_path)
        model_config["models_data"] = self.models_data
        save_json(model_config, models_config_path)

    def set_task_filter(self, group):
        self._task_filter = group
        for name, button in self._task_filter_buttons.items():
            button.setChecked(name == group)
        self._apply_filters(self._search_text)

    def _iter_model_items(self):
        for i in range(self.container_layout.count()):
            widget = self.container_layout.itemAt(i).widget()
            if not isinstance(widget, ProviderSection):
                continue
            for j in range(widget.models_container.count()):
                item = widget.models_container.itemAt(j).widget()
                if isinstance(item, ModelItem):
                    yield widget, item

    def _item_matches_search(self, item, search_text, match_threshold=0.7):
        if not search_text:
            return True
        model_name = item.model_name.lower()
        display_name = item.display_name.lower()
        similarity = max(
            SequenceMatcher(None, search_text, model_name).ratio(),
            SequenceMatcher(None, search_text, display_name).ratio(),
        )
        return (
            search_text in model_name
            or search_text in display_name
            or similarity >= match_threshold
        )

    def _item_matches_task(self, item):
        if self._task_filter == "all":
            return True
        return (
            group_for_model_type(item.model_data.get("type", ""))
            == self._task_filter
        )

    def filter_models(self, search_text, match_threshold=0.7):
        self._search_text = search_text or ""
        self._apply_filters(self._search_text, match_threshold)

    def _apply_filters(self, search_text, match_threshold=0.7):
        empty_text = "No models found."
        search_text = (search_text or "").lower()

        for i in reversed(range(self.container_layout.count())):
            widget = self.container_layout.itemAt(i).widget()
            if isinstance(widget, QLabel) and widget.text() == empty_text:
                widget.deleteLater()

        found_any = False
        for _section, item in self._iter_model_items():
            visible = self._item_matches_task(
                item
            ) and self._item_matches_search(item, search_text, match_threshold)
            item.setVisible(visible)
            if visible:
                found_any = True

        if not found_any:
            for i in range(self.container_layout.count()):
                widget = self.container_layout.itemAt(i).widget()
                if widget:
                    widget.setVisible(False)
            no_results = QLabel(empty_text)
            no_results.setAlignment(Qt.AlignmentFlag.AlignCenter)
            _t = get_theme()
            no_results.setStyleSheet(f"""
                color: {_t["text_secondary"]};
                font-size: 14px;
                padding: 20px;
            """)
            self.container_layout.addWidget(no_results)
            return

        for i in range(self.container_layout.count()):
            widget = self.container_layout.itemAt(i).widget()
            if isinstance(widget, ProviderSection):
                has_visible_models = False
                for j in range(widget.models_container.count()):
                    model_widget = widget.models_container.itemAt(j).widget()
                    if model_widget and model_widget.isVisible():
                        has_visible_models = True
                        break
                widget.setVisible(has_visible_models)
            elif (
                isinstance(widget, QFrame)
                and widget.frameShape() == QFrame.Shape.HLine
            ):
                prev_widget = (
                    self.container_layout.itemAt(i - 1).widget()
                    if i > 0
                    else None
                )
                next_widget = (
                    self.container_layout.itemAt(i + 1).widget()
                    if i < self.container_layout.count() - 1
                    else None
                )
                should_be_visible = False
                if prev_widget is not None and next_widget is not None:
                    should_be_visible = (
                        prev_widget.isVisible() and next_widget.isVisible()
                    )
                    widget.setVisible(should_be_visible)
