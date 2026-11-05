from PyQt6.QtWidgets import QWidget, QHBoxLayout, QComboBox


class GroupIDFilterComboBox(QWidget):
    def __init__(self, parent=None, items=[]):
        super(GroupIDFilterComboBox, self).__init__(parent)
        self.items = items
        self.gid_box = QComboBox()
        self.gid_box.setToolTip(
            self.tr(
                "按群组编号筛选对象列表\n"
                "同一群组的框会一起选中、一起移动，编号在标注时自动分配"
            )
        )
        self.gid_box.addItems(self.items)
        self.gid_box.currentIndexChanged.connect(parent.gid_selection_changed)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 2, 0, 2)
        layout.addWidget(self.gid_box)
        self.setLayout(layout)

    def update_items(self, items):
        self.items = items
        self.gid_box.clear()
        self.gid_box.addItems(self.items)


class LabelFilterComboBox(QWidget):
    def __init__(self, parent=None, items=[]):
        super(LabelFilterComboBox, self).__init__(parent)
        self.items = items
        self.text_box = QComboBox()
        self.text_box.setToolTip(
            self.tr(
                "按类别筛选对象列表\n"
                "选项来自当前图片中出现的类别，只影响列表显示，不改动标注"
            )
        )
        self.text_box.addItems(self.items)
        self.text_box.currentIndexChanged.connect(
            parent.text_selection_changed
        )

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 2, 0, 2)
        layout.addWidget(self.text_box)
        self.setLayout(layout)

    def update_items(self, items):
        self.items = items
        self.text_box.clear()
        self.text_box.addItems(self.items)
