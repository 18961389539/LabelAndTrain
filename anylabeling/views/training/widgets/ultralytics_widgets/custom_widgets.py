from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QWidget,
)
from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor

from anylabeling.services.auto_training.ultralytics.config import *
from anylabeling.services.auto_training.ultralytics.style import *
from anylabeling.views.labeling.utils.qt import new_icon_path
from anylabeling.views.labeling.utils.theme import get_theme
from anylabeling.views.labeling.utils.style import (
    get_cancel_btn_style,
    get_checkbox_indicator_style,
    get_ok_btn_style,
)


class CustomCheckBox(QCheckBox):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        t = get_theme()
        self.setStyleSheet(f"""
            QCheckBox {{
                spacing: 8px;
                color: {t["text"]};
            }}
            {get_checkbox_indicator_style()}
        """)


class CustomComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        t = get_theme()
        self.view().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(f"""
            QComboBox {{
                padding: 5px 8px;
                background: {t["background_secondary"]};
                border: 1px solid {t["border_light"]};
                border-radius: {t["radius_md"]};
                min-height: 24px;
                selection-background-color: {t["selection"]};
                selection-color: {t["selection_text"]};
                color: {t["text"]};
            }}
            QComboBox:hover {{
                border-color: {t["primary"]};
            }}
            QComboBox:focus {{
                border-color: {t["primary"]};
                outline: none;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border: none;
                background: {t["spinbox_button"]};
                border-top-right-radius: {t["radius_md"]};
                border-bottom-right-radius: {t["radius_md"]};
            }}
            QComboBox::drop-down:hover {{
                background: {t["spinbox_button_hover"]};
            }}
            QComboBox::down-arrow {{
                image: url({new_icon_path("caret-down", "svg")});
                width: 12px;
                height: 12px;
            }}
            QComboBox QAbstractItemView {{
                background: {t["background_secondary"]};
                border: 1px solid {t["border_light"]};
                border-radius: {t["radius_md"]};
                padding: 4px;
                selection-background-color: {t["selection"]};
                selection-color: {t["selection_text"]};
                color: {t["text"]};
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px 8px;
                border-radius: {t["radius_sm"]};
                min-height: 20px;
                border: none;
                outline: none;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: {t["surface_hover"]};
            }}
            QComboBox QAbstractItemView::item:selected {{
                background-color: {t["selection"]};
                color: {t["selection_text"]};
                border: none;
                outline: none;
            }}
            QComboBox QAbstractItemView::item:selected:active {{
                background-color: {t["selection"]};
                color: {t["selection_text"]};
                border: none;
                outline: none;
            }}
        """)

    def wheelEvent(self, event):
        event.ignore()


class CustomSpinBox(QSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        t = get_theme()
        self.setStyleSheet(f"""
            QSpinBox {{
                padding: 5px 8px;
                background: {t["background_secondary"]};
                color: {t["text"]};
                border: 1px solid {t["border_light"]};
                border-radius: {t["radius_md"]};
                min-height: 24px;
                selection-background-color: {t["selection"]};
                selection-color: {t["selection_text"]};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 20px;
                border: none;
                background: {t["spinbox_button"]};
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background: {t["spinbox_button_hover"]};
            }}
            QSpinBox::up-arrow {{
                image: url({new_icon_path("caret-up", "svg")});
                width: 12px;
                height: 12px;
            }}
            QSpinBox::down-arrow {{
                image: url({new_icon_path("caret-down", "svg")});
                width: 12px;
                height: 12px;
            }}
        """)

    def wheelEvent(self, event):
        event.ignore()


class CustomDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        t = get_theme()
        self.setStyleSheet(f"""
            QDoubleSpinBox {{
                padding: 5px 8px;
                background: {t["background_secondary"]};
                color: {t["text"]};
                border: 1px solid {t["border_light"]};
                border-radius: {t["radius_md"]};
                min-height: 24px;
                selection-background-color: {t["selection"]};
                selection-color: {t["selection_text"]};
            }}
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                width: 20px;
                border: none;
                background: {t["spinbox_button"]};
            }}
            QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
                background: {t["spinbox_button_hover"]};
            }}
            QDoubleSpinBox::up-arrow {{
                image: url({new_icon_path("caret-up", "svg")});
                width: 12px;
                height: 12px;
            }}
            QDoubleSpinBox::down-arrow {{
                image: url({new_icon_path("caret-down", "svg")});
                width: 12px;
                height: 12px;
            }}
        """)

    def wheelEvent(self, event):
        event.ignore()


class CustomSlider(QSlider):
    def __init__(
        self, orientation=QtCore.Qt.Orientation.Horizontal, parent=None
    ):
        super().__init__(orientation, parent)
        t = get_theme()
        self.setStyleSheet(f"""
            QSlider {{
                height: 28px;
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: {t["border"]};
                border-radius: {t["radius_sm"]};
            }}
            QSlider::handle:horizontal {{
                background: {t["primary"]};
                border: none;
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: {t["radius_lg"]};
            }}
            QSlider::sub-page:horizontal {{
                background: {t["primary"]};
                border-radius: {t["radius_sm"]};
            }}
        """)

    def wheelEvent(self, event):
        event.ignore()


class CustomLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        t = get_theme()
        self.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {t["border"]};
                border-radius: {t["radius_lg"]};
                background-color: {t["background_secondary"]};
                color: {t["text"]};
                font-size: 13px;
                height: 36px;
                padding-left: 4px;
            }}
            QLineEdit:hover {{
                background-color: {t["background_hover"]};
                border-radius: {t["radius_lg"]};
            }}
            QLineEdit:focus {{
                border: 2px solid {t["highlight"]};
                background-color: {t["background_secondary"]};
            }}
        """)


class CustomQPushButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(36)
        self.setMinimumWidth(80)
        self.selected = False
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.update_style()

    def set_selected(self, selected):
        self.selected = selected
        self.update_style()

    def update_style(self):
        t = get_theme()
        if self.selected:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {t["primary_solid"]};
                    color: {t["on_primary"]};
                    border: 2px solid {t["primary_solid"]};
                    border-radius: {t["radius_sm"]};
                    padding: 4px 8px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {t["primary_solid_hover"]};
                    border-color: {t["primary_solid_hover"]};
                }}
                QPushButton:focus {{
                    border-color: {t["background"]};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {t["surface"]};
                    color: {t["text"]};
                    border: 1px solid {t["border_light"]};
                    border-radius: {t["radius_sm"]};
                    padding: 4px 8px;
                    outline: none;
                }}
                QPushButton:hover {{
                    background-color: {t["surface_hover"]};
                }}
                QPushButton:pressed {{
                    background-color: {t["surface_pressed"]};
                }}
                QPushButton:focus {{
                    outline: none;
                }}
            """)


class PrimaryButton(QPushButton):
    def __init__(self, text="OK", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(get_ok_btn_style())


class SecondaryButton(QPushButton):
    def __init__(self, text="Cancel", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(get_cancel_btn_style())


class TrainingConfirmDialog(QDialog):
    def __init__(self, cmd_parts, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("开始训练"))
        self.setFixedSize(752, 320)
        t = get_theme()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {t["background"]};
                border-radius: {t["radius_lg"]};
            }}
            QLabel {{
                background-color: transparent;
                color: {t["text"]};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title_label = QLabel(self.tr("准备开始训练"))
        title_label.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {t['text']};"
        )
        layout.addWidget(title_label)

        desc_label = QLabel(self.tr("将执行以下命令："))
        desc_label.setStyleSheet(
            f"color: {t['text_secondary']}; font-size: 13px;"
        )
        layout.addWidget(desc_label)

        cmd_text = self._format_command(cmd_parts)
        command_display = QTextEdit()
        command_display.setPlainText(cmd_text)
        command_display.setReadOnly(True)
        command_display.setFixedHeight(160)
        command_display.setStyleSheet(f"""
            QTextEdit {{
                background-color: {t["surface"]};
                color: {t["text"]};
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                font-size: 12px;
                border: 1px solid {t["border"]};
                border-radius: {t["radius_md"]};
                padding: 12px;
            }}
        """)
        layout.addWidget(command_display)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = SecondaryButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.start_btn = PrimaryButton("Start")
        self.start_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.start_btn)

        layout.addLayout(button_layout)

    def _format_command(self, cmd_parts):
        if len(cmd_parts) <= 3:
            return " ".join(cmd_parts)

        base_cmd = " ".join(cmd_parts[:3])
        params = cmd_parts[3:]

        formatted_cmd = base_cmd + " \\\n"
        for i, param in enumerate(params):
            if i == len(params) - 1:
                formatted_cmd += f"    {param}"
            else:
                formatted_cmd += f"    {param} \\\n"

        return formatted_cmd


class CustomTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.original_data = []
        self.setup_table()

    def setup_table(self):
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.setStyleSheet(get_custom_table_style())

        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)

    def load_data(self, table_data):
        if not table_data:
            self.clear()
            return

        self.original_data = table_data
        self.populate_table()

    def populate_table(self):
        if not self.original_data:
            return

        headers = self.original_data[0]
        data_rows = self.original_data[1:]

        self.setRowCount(len(data_rows))
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)

        for row, row_data in enumerate(data_rows):
            for col, value in enumerate(row_data):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if col == 0:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter
                    )

                self.setItem(row, col, item)


class TrainingStepBar(QWidget):
    """Visible Data → Config → Train progress for the training wizard."""

    step_clicked = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons = []
        self._hints = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(8)
        self._titles = [
            self.tr("1. Data"),
            self.tr("2. Config"),
            self.tr("3. Train"),
        ]
        for index, title in enumerate(self._titles):
            column = QVBoxLayout()
            button = QPushButton(title)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, i=index: self.step_clicked.emit(i)
            )
            hint = QLabel("")
            hint.setWordWrap(True)
            hint.setStyleSheet("font-size: 11px;")
            column.addWidget(button)
            column.addWidget(hint)
            layout.addLayout(column, 1)
            self._buttons.append(button)
            self._hints.append(hint)
        self.set_state(0, ["", "", ""])

    def set_state(self, current, hints):
        t = get_theme()
        for index, button in enumerate(self._buttons):
            hint = hints[index] if index < len(hints) else ""
            self._hints[index].setText(hint)
            if index < current:
                button.setText(f"{self._titles[index]} ✓")
                button.setStyleSheet(
                    f"QPushButton {{ background: {t['success_solid']}; "
                    f"color: {t['on_success']}; border: none; "
                    f"border-radius: {t['radius_lg']}; height: 32px; }}"
                )
            elif index == current:
                button.setText(self._titles[index])
                button.setStyleSheet(
                    f"QPushButton {{ background: {t['primary_solid']}; "
                    f"color: {t['on_primary']}; "
                    f"border: none; border-radius: {t['radius_lg']}; height: 32px; "
                    f"font-weight: 700; }}"
                )
            else:
                button.setText(self._titles[index])
                button.setStyleSheet(
                    f"QPushButton {{ background: {t['surface']}; color: {t['text']}; "
                    f"border: 1px solid {t['border']}; border-radius: {t['radius_lg']}; height: 32px; }}"
                )
            self._hints[index].setStyleSheet(
                f"font-size: 11px; color: {t['text_secondary']};"
            )
