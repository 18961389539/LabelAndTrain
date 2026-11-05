"""Shared base for project-wide range/table dialogs.

Four dialogs (OverviewDialog, GroupIDModifyDialog, LabelModifyDialog and
ShapeModifyDialog) re-implemented the same two helpers against the same
``parent.file_list_widget`` model, so they were lifted into this base class.
``populate_table`` / ``update_range`` stay in each subclass because their
table columns and widgets genuinely differ.
"""

from PyQt6 import QtWidgets


class RangeTableDialog(QtWidgets.QDialog):
    def get_image_file_list(self):
        """List image files currently shown in the parent file list."""
        image_file_list = []
        count = self.parent.file_list_widget.count()
        for c in range(count):
            image_file = self.parent.file_list_widget.item(c).text()
            image_file_list.append(image_file)
        return image_file_list

    def move_to_center(self):
        """Move the dialog to the center of the screen."""
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())
