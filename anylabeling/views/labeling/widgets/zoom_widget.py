from PyQt6 import QtCore, QtGui, QtWidgets

from anylabeling.views.labeling.utils.theme import get_theme


class ZoomWidget(QtWidgets.QSpinBox):
    def __init__(self, value=100):
        super().__init__()
        self.setObjectName("ToolBarZoomWidget")
        self.setButtonSymbols(
            QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        self.setRange(1, 1000)
        self.setSuffix("%")
        self.setValue(value)
        self.setKeyboardTracking(False)
        self.setToolTip(self.tr("Zoom Level"))
        self.setStatusTip(self.toolTip())
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(34, 26)
        font = self.font()
        font.setPointSize(8)
        font.setBold(True)
        self.setFont(font)

        t = get_theme()
        self.setStyleSheet(f"""
            QSpinBox {{
                background-color: {t["surface"]};
                color: {t["text"]};
                border: 1px solid {t["border_light"]};
                border-radius: 8px;
                padding: 0 1px;
                min-height: 26px;
                selection-background-color: {t["selection"]};
                selection-color: {t["selection_text"]};
            }}
            QSpinBox:focus {{
                border-color: {t["highlight"]};
            }}
            QSpinBox:disabled {{
                color: {t["text_secondary"]};
                border-color: {t["border"]};
            }}
            """)
