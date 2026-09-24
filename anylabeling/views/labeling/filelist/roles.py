"""Item-data roles the file list attaches to each row.

Kept in one place so the widget, the file-list helpers and the async
checkers agree on the slot numbers.
"""

from PyQt6.QtCore import Qt

FILE_ANNOTATION_ROLE = Qt.ItemDataRole.UserRole + 1
# Distinguishes "confirmed empty (negative sample, no objects)" from
# ordinary annotated files; negative samples are exported as empty .txt so
# they participate in YOLO training as background samples.
FILE_NEGATIVE_ROLE = Qt.ItemDataRole.UserRole + 2
FILE_LOW_CONF_ROLE = Qt.ItemDataRole.UserRole + 3
# Review state of the row: unchecked / confirmed / rejected.
FILE_REVIEW_ROLE = Qt.ItemDataRole.UserRole + 4
# When that state was last set, carried in from the label JSON for the row
# tooltip only -- nothing branches on it.
FILE_REVIEWED_AT_ROLE = Qt.ItemDataRole.UserRole + 5
