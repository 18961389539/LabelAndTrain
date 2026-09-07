"""Centered empty-canvas overlay with an open-folder call to action."""

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal

from ..utils.style import get_ok_btn_style
from ..utils.theme import get_theme


class CanvasEmptyStateWidget(QtWidgets.QWidget):
    """Shown when no image is loaded; clicking the button opens a folder."""

    open_folder_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CanvasEmptyState")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        t = get_theme()
        self.setStyleSheet(
            f"""
            QWidget#CanvasEmptyState {{
                background: transparent;
            }}
            QLabel#EmptyTitle {{
                color: {t["text_secondary"]};
                font-size: 18px;
                font-weight: 700;
            }}
            QLabel#EmptyStep {{
                color: {t["text_placeholder"]};
                font-size: 13px;
            }}
            """
        )

        title = QtWidgets.QLabel(self.tr("打开文件夹开始标注"))
        title.setObjectName("EmptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        steps = QtWidgets.QLabel(
            self.tr(
                "1. 打开图片文件夹\n"
                "2. 需要时在自动标注面板选择模型\n"
                "3. 画框或修正结果，切图时自动保存"
            )
        )
        steps.setObjectName("EmptyStep")
        steps.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.open_button = QtWidgets.QPushButton(
            self.tr("打开文件夹（Ctrl+U）")
        )
        self.open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_button.setStyleSheet(get_ok_btn_style())
        self.open_button.setMinimumWidth(200)
        self.open_button.clicked.connect(self.open_folder_requested.emit)

        card = QtWidgets.QWidget()
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(14)
        card_layout.addWidget(title)
        card_layout.addWidget(steps)
        card_layout.addWidget(
            self.open_button, 0, Qt.AlignmentFlag.AlignCenter
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        layout.addWidget(card, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
