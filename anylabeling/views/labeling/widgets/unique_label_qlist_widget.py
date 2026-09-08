# -*- encoding: utf-8 -*-

import html

from PyQt6 import QtWidgets, QtGui
from PyQt6.QtCore import Qt

from .escapable_qlist_widget import EscapableQListWidget


class UniqueLabelQListWidget(EscapableQListWidget):
    # QT Overload
    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if not self.indexAt(event.position().toPoint()).isValid():
            self.clearSelection()

    def find_items_by_label(self, label):
        items = []
        for row in range(self.count()):
            item = self.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == label:
                items.append(item)
        return items

    def create_item_from_label(self, label):
        item = QtWidgets.QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, label)
        return item

    def set_item_label(
        self, item, label, color=None, opacity=255, count=None
    ):
        qlabel = QtWidgets.QLabel()
        qlabel.setContentsMargins(8, 4, 8, 4)
        if color is None:
            text = "" if label is None else str(label)
        else:
            text = "{}".format(html.escape("" if label is None else str(label)))
        if count is not None:
            text = f"{text}　<span style='color:rgba(120,132,145,0.95);'>{count}</span>"
        qlabel.setText(text)
        if color is not None:
            background_color = QtGui.QColor(*color, opacity)
            style_sheet = (
                f"background-color: rgba("
                f"{background_color.red()}, "
                f"{background_color.green()}, "
                f"{background_color.blue()}, "
                f"{background_color.alpha()}"
                ");"
            )
            qlabel.setStyleSheet(style_sheet)
        qlabel.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        item.setSizeHint(qlabel.sizeHint())
        self.setItemWidget(item, qlabel)

    def update_item_color(self, label, color, opacity=255):
        items = self.find_items_by_label(label)
        for item in items:
            qlabel = self.itemWidget(item)
            if qlabel:
                background_color = QtGui.QColor(*color, opacity)
                style_sheet = (
                    f"background-color: rgba("
                    f"{background_color.red()}, "
                    f"{background_color.green()}, "
                    f"{background_color.blue()}, "
                    f"{background_color.alpha()}"
                    ");"
                )
                qlabel.setStyleSheet(style_sheet)
                break

    def remove_items_by_label(self, label):
        items = self.find_items_by_label(label)
        for item in items:
            row = self.row(item)
            self.takeItem(row)

    def set_label_count(self, label, count):
        """Update the count badge of a label row without touching its color."""
        items = self.find_items_by_label(label)
        for item in items:
            qlabel = self.itemWidget(item)
            if qlabel is None:
                continue
            text = qlabel.text()
            # Remove the previous badge (everything after the full-width space).
            stripped = text.split("　", 1)[0]
            if count is not None:
                qlabel.setText(
                    f"{stripped}　"
                    f"<span style='color:rgba(120,132,145,0.95);'>{count}</span>"
                )
            else:
                qlabel.setText(stripped)
            item.setSizeHint(qlabel.sizeHint())
            break
