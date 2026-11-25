"""View, zoom, display toggles, theme, upload, export and AI actions.

Split out of ``action_builder.build_actions`` (the function was 1757
lines); the body is moved verbatim and returns its locals so the
caller can publish them under the historical action names.
"""

import functools

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import QCoreApplication, Qt

from jllabeling.views.labeling import utils

from .label_editing import LABEL_OPACITY


def build(widget):
    """Create the view actions and return them by name."""
    action = functools.partial(utils.new_action, widget)
    shortcuts = widget._config["shortcuts"]
    zoom = QtWidgets.QWidgetAction(widget)
    zoom.setDefaultWidget(widget.zoom_widget)
    widget.zoom_widget.setWhatsThis(
        str(
            QCoreApplication.translate(
                "LabelingWidget",
                "Zoom in or out of the image. Also accessible with "
                "{} and {} from the canvas.",
            )
        ).format(
            utils.fmt_shortcut(
                f"{shortcuts['zoom_in']},{shortcuts['zoom_out']}"
            ),
            utils.fmt_shortcut(
                QCoreApplication.translate("LabelingWidget", "Ctrl+Wheel")
            ),
        )
    )
    widget.zoom_widget.setEnabled(False)

    zoom_in = action(
        QCoreApplication.translate("LabelingWidget", "Zoom In"),
        functools.partial(widget.add_zoom, 1.1),
        shortcuts["zoom_in"],
        "zoom-in",
        QCoreApplication.translate("LabelingWidget", "Increase zoom level"),
        enabled=False,
    )
    zoom_out = action(
        QCoreApplication.translate("LabelingWidget", "Zoom Out"),
        functools.partial(widget.add_zoom, 0.9),
        shortcuts["zoom_out"],
        "zoom-out",
        QCoreApplication.translate("LabelingWidget", "Decrease zoom level"),
        enabled=False,
    )
    zoom_org = action(
        QCoreApplication.translate("LabelingWidget", "Original Size"),
        functools.partial(widget.set_zoom, 100),
        shortcuts["zoom_to_original"],
        "zoom",
        QCoreApplication.translate("LabelingWidget", "Zoom to original size"),
        enabled=False,
    )
    keep_prev_scale = action(
        QCoreApplication.translate("LabelingWidget", "Keep Previous Scale"),
        lambda x: widget._config.update({"keep_prev_scale": x}),
        shortcut=shortcuts["keep_prev_scale"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Keep previous zoom scale"
        ),
        checkable=True,
        checked=widget._config["keep_prev_scale"],
        enabled=True,
    )
    keep_prev_brightness = action(
        QCoreApplication.translate(
            "LabelingWidget", "Keep Previous Brightness"
        ),
        lambda x: widget._config.update({"keep_prev_brightness": x}),
        shortcut=shortcuts["keep_prev_brightness"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Keep previous brightness"
        ),
        checkable=True,
        checked=widget._config["keep_prev_brightness"],
        enabled=True,
    )
    keep_prev_contrast = action(
        QCoreApplication.translate("LabelingWidget", "Keep Previous Contrast"),
        lambda x: widget._config.update({"keep_prev_contrast": x}),
        shortcut=shortcuts["keep_prev_contrast"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Keep previous contrast"
        ),
        checkable=True,
        checked=widget._config["keep_prev_contrast"],
        enabled=True,
    )
    fit_window = action(
        QCoreApplication.translate("LabelingWidget", "Fit Window"),
        widget.set_fit_window,
        shortcuts["fit_window"],
        "fit-window",
        QCoreApplication.translate(
            "LabelingWidget", "Zoom follows window size"
        ),
        checkable=True,
        enabled=False,
    )
    fit_width = action(
        QCoreApplication.translate("LabelingWidget", "Fit Width"),
        widget.set_fit_width,
        shortcuts["fit_width"],
        "fit-width",
        QCoreApplication.translate(
            "LabelingWidget", "Zoom follows window width"
        ),
        checkable=True,
        enabled=False,
    )
    brightness_contrast = action(
        QCoreApplication.translate(
            "LabelingWidget", "Set Brightness Contrast"
        ),
        widget.brightness_contrast,
        shortcuts["brightness_contrast"],
        "color",
        "Adjust brightness and contrast",
        enabled=False,
    )
    set_cross_line = action(
        QCoreApplication.translate("LabelingWidget", "Set Cross Line"),
        widget.set_cross_line,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Adjust cross line for mouse position"
        ),
        icon="cartesian",
    )
    show_groups = action(
        QCoreApplication.translate("LabelingWidget", "Show Groups"),
        lambda x: widget.set_canvas_params("show_groups", x),
        shortcut=shortcuts["show_groups"],
        tip=QCoreApplication.translate("LabelingWidget", "Show shape groups"),
        icon=None,
        checkable=True,
        checked=widget._config["show_groups"],
        enabled=True,
        auto_trigger=True,
    )
    show_masks = action(
        QCoreApplication.translate("LabelingWidget", "Show Masks"),
        lambda x: widget.set_canvas_params("show_masks", x),
        shortcut=shortcuts["show_masks"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Show semi-transparent masks for shapes"
        ),
        icon=None,
        checkable=True,
        checked=widget._config["show_masks"],
        enabled=True,
        auto_trigger=True,
    )
    # Fire the shortcut even when a child widget (e.g. the text-prompt
    # QLineEdit) has focus, so Ctrl+M reliably toggles the mask overlay.
    show_masks.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    show_texts = action(
        QCoreApplication.translate("LabelingWidget", "Show Texts"),
        lambda x: widget.set_canvas_params("show_texts", x),
        shortcut=shortcuts["show_texts"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Show text above shapes"
        ),
        icon=None,
        checkable=True,
        checked=widget._config["show_texts"],
        enabled=True,
        auto_trigger=True,
    )
    show_labels = action(
        QCoreApplication.translate("LabelingWidget", "Show Labels"),
        lambda x: widget.set_canvas_params("show_labels", x),
        shortcut=shortcuts["show_labels"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Show label inside shapes"
        ),
        icon=None,
        checkable=True,
        checked=widget._config["show_labels"],
        enabled=True,
        auto_trigger=True,
    )
    # Toggle the attribute text painted on the canvas. The canvas has
    # supported ``show_attributes`` all along, but it was never exposed as
    # an action, which left Ctrl+Shift+L advertised in the F1 cheat sheet
    # while doing nothing.
    show_attributes = action(
        QCoreApplication.translate("LabelingWidget", "Show Attributes"),
        lambda x: widget.set_canvas_params("show_attributes", x),
        shortcut=shortcuts["show_attributes"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Show attributes below shapes"
        ),
        icon=None,
        checkable=True,
        checked=widget._config["show_attributes"],
        enabled=True,
        auto_trigger=True,
    )
    # Same reasoning as show_masks: the shortcut must win over a focused
    # child widget (e.g. the text-prompt QLineEdit).
    show_attributes.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
    show_scores = action(
        QCoreApplication.translate("LabelingWidget", "Show Scores"),
        lambda x: widget.set_canvas_params("show_scores", x),
        shortcut=shortcuts["show_scores"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Show score inside shapes"
        ),
        icon=None,
        checkable=True,
        checked=widget._config["show_scores"],
        enabled=True,
        auto_trigger=True,
    )
    show_degrees = action(
        QCoreApplication.translate("LabelingWidget", "Show Degrees"),
        lambda x: widget.set_canvas_params("show_degrees", x),
        shortcut=shortcuts["show_degrees"],
        tip=QCoreApplication.translate(
            "LabelingWidget", "Show degrees above rotated shapes"
        ),
        icon=None,
        checkable=True,
        checked=widget._config["show_degrees"],
        enabled=True,
        auto_trigger=True,
    )

    # Theme menu options (System / Light / Dark)
    theme_mode_actions = []
    theme_group = QtGui.QActionGroup(widget)
    theme_group.setExclusive(True)
    widget._theme_actions = {}
    current_appearance = widget._config.get("theme", "auto")
    for _mode, _label in (
        ("auto", QCoreApplication.translate("LabelingWidget", "System")),
        ("light", QCoreApplication.translate("LabelingWidget", "Light")),
        ("dark", QCoreApplication.translate("LabelingWidget", "Dark")),
    ):
        _act = QtGui.QAction(_label, theme_group)
        _act.setCheckable(True)
        _act.setChecked(current_appearance == _mode)
        _act.setData(_mode)
        _act.triggered.connect(
            functools.partial(widget._on_theme_changed, _mode)
        )
        theme_mode_actions.append(_act)
        widget._theme_actions[_mode] = _act

    # Upload
    upload_export_icon = "label"
    upload_image_flags_file = action(
        QCoreApplication.translate("LabelingWidget", "Image Flags"),
        lambda: utils.upload_image_flags_file(widget),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Upload Custom Image Flags File"
        ),
    )
    upload_label_flags_file = action(
        QCoreApplication.translate("LabelingWidget", "Label Flags"),
        lambda: utils.upload_label_flags_file(widget, LABEL_OPACITY),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Upload Custom Label Flags File"
        ),
    )
    upload_label_classes_file = action(
        QCoreApplication.translate("LabelingWidget", "Label Classes"),
        lambda: utils.upload_label_classes_file(widget),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Upload Custom Label Classes File"
        ),
    )
    upload_yolo_hbb_annotation = action(
        QCoreApplication.translate("LabelingWidget", "YOLO HBB"),
        lambda: utils.upload_yolo_annotation(widget, "hbb", LABEL_OPACITY),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget",
            "Upload Custom YOLO Horizontal Bounding Boxes Annotations",
        ),
    )
    upload_yolo_seg_annotation = action(
        QCoreApplication.translate("LabelingWidget", "YOLO Seg"),
        lambda: utils.upload_yolo_annotation(widget, "seg", LABEL_OPACITY),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Upload Custom YOLO Segmentation Annotations"
        ),
    )
    upload_yolo_obb_annotation = action(
        QCoreApplication.translate("LabelingWidget", "YOLO OBB"),
        lambda: utils.upload_yolo_annotation(widget, "obb", LABEL_OPACITY),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget",
            "Upload Custom YOLO Oriented Bounding Boxes Annotations",
        ),
    )
    upload_yolo_pose_annotation = action(
        QCoreApplication.translate("LabelingWidget", "YOLO Pose"),
        lambda: utils.upload_yolo_annotation(widget, "pose", LABEL_OPACITY),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Upload Custom YOLO Pose Annotations"
        ),
    )

    # Export
    export_yolo_hbb_annotation = action(
        QCoreApplication.translate("LabelingWidget", "YOLO HBB"),
        lambda: utils.export_yolo_annotation(widget, "hbb"),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget",
            "Export Custom YOLO Horizontal Bounding Boxes Annotations",
        ),
    )
    export_yolo_seg_annotation = action(
        QCoreApplication.translate("LabelingWidget", "YOLO Seg"),
        lambda: utils.export_yolo_annotation(widget, "seg"),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Export Custom YOLO Segmentation Annotations"
        ),
    )
    export_yolo_pose_annotation = action(
        QCoreApplication.translate("LabelingWidget", "YOLO Pose"),
        lambda: utils.export_yolo_annotation(widget, "pose"),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget", "Export Custom YOLO Pose Annotations"
        ),
    )
    export_yolo_obb_annotation = action(
        QCoreApplication.translate("LabelingWidget", "YOLO OBB"),
        lambda: utils.export_yolo_annotation(widget, "obb"),
        None,
        icon=upload_export_icon,
        tip=QCoreApplication.translate(
            "LabelingWidget",
            "Export Custom YOLO Oriented Bounding Boxes Annotations",
        ),
    )

    # Group zoom controls into a list for easier toggling.
    zoom_actions = (
        widget.zoom_widget,
        zoom_in,
        zoom_out,
        zoom_org,
        fit_window,
        fit_width,
    )
    widget.zoom_mode = widget.FIT_WINDOW
    fit_window.setChecked(True)
    widget.scalers = {
        widget.FIT_WINDOW: widget.scale_fit_window,
        widget.FIT_WIDTH: widget.scale_fit_width,
        # Set to one to scale to 100% when loading files.
        widget.MANUAL_ZOOM: lambda: 1,
    }

    edit = action(
        QCoreApplication.translate("LabelingWidget", "Edit Label"),
        widget.edit_label,
        shortcuts["edit_label"],
        "edit",
        QCoreApplication.translate(
            "LabelingWidget", "Modify the label of the selected polygon"
        ),
        enabled=False,
    )

    fill_drawing = action(
        QCoreApplication.translate("LabelingWidget", "Fill Drawing Polygon"),
        widget.canvas.set_fill_drawing,
        shortcuts["fill_drawing"],
        "color",
        QCoreApplication.translate(
            "LabelingWidget", "Fill polygon while drawing"
        ),
        checkable=True,
        enabled=True,
    )
    fill_drawing.trigger()

    show_navigator = action(
        QCoreApplication.translate("LabelingWidget", "Navigator"),
        widget.toggle_navigator,
        shortcuts["show_navigator"],
        "navigator",
        QCoreApplication.translate(
            "LabelingWidget", "Show/hide the navigator window"
        ),
        checkable=True,
        enabled=True,
    )

    # AI Actions
    toggle_auto_labeling_widget = action(
        QCoreApplication.translate("LabelingWidget", "Auto Labeling"),
        widget.toggle_auto_labeling_widget,
        shortcuts["auto_label"],
        "brain",
        QCoreApplication.translate("LabelingWidget", "Auto Labeling"),
    )
    return locals()
