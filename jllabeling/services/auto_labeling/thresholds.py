"""Shared confidence / IoU defaults for auto-labeling models.

The same pair of numbers used to be written in seven places: the YOLO base
class, three helpers in ``utils/box.py``, ``yolov8_sam2.py``, the custom
model YAML generator, the training-to-auto-labeling exporter and the .ui
spinbox tooltips. One of them (``yolov8_cls.py``) had drifted to 0.0 while
the UI claimed 0.25. Import from here instead so the defaults cannot drift.
"""

#: Minimum score for a detection box to be kept.
DEFAULT_CONF_THRESHOLD = 0.25
#: NMS IoU threshold: overlapping boxes above this are merged.
DEFAULT_IOU_THRESHOLD = 0.45
