import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6 import QtCore, QtWidgets, uic

    import anylabeling.resources.resources  # noqa: F401
    from anylabeling import config
    from anylabeling.config import get_config
    from anylabeling.views.labeling.utils.style import (
        get_model_selection_scroll_area_style,
    )
    from anylabeling.views.labeling.widgets.auto_labeling.auto_labeling import (
        AutoLabelingWidget,
        update_model_selection_scroll_area_height,
    )
    from anylabeling.views.labeling.widgets.searchable_model_dropdown import (
        SearchableModelDropdownPopup,
    )

    PYQT_AVAILABLE = True
except Exception:
    PYQT_AVAILABLE = False


@unittest.skipUnless(
    PYQT_AVAILABLE, "PyQt6 is required for auto labeling layout tests"
)
class TestAutoLabelingLayout(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        self._widgets = []

    def tearDown(self):
        for widget in self._widgets:
            widget.close()
        self.app.processEvents()

    def test_model_selection_uses_horizontal_scroll_area(self):
        form = QtWidgets.QWidget()
        self._widgets.append(form)
        ui_path = (
            Path(__file__).resolve().parents[2]
            / "anylabeling/views/labeling/widgets/auto_labeling/auto_labeling.ui"
        )

        uic.loadUi(str(ui_path), form)

        scroll_area = form.findChild(
            QtWidgets.QScrollArea, "model_selection_scroll_area"
        )
        scroll_area.setStyleSheet(get_model_selection_scroll_area_style())
        container = form.findChild(
            QtWidgets.QWidget, "model_selection_container"
        )

        self.assertIsNotNone(scroll_area)
        self.assertIs(scroll_area.widget(), container)
        self.assertTrue(scroll_area.widgetResizable())
        self.assertEqual(
            scroll_area.horizontalScrollBarPolicy(),
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        self.assertEqual(
            scroll_area.verticalScrollBarPolicy(),
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self.assertIsNotNone(container.layout())
        spacer = next(
            (
                container.layout().itemAt(index).spacerItem()
                for index in range(container.layout().count())
                if container.layout().itemAt(index).spacerItem() is not None
            ),
            None,
        )
        self.assertIsNotNone(spacer)
        self.assertEqual(
            spacer.sizePolicy().horizontalPolicy(),
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

        slider = form.findChild(QtWidgets.QSlider, "mask_fineness_slider")
        self.assertGreaterEqual(slider.minimumWidth(), 120)

        form.resize(5000, 100)
        form.show()
        self.app.processEvents()
        update_model_selection_scroll_area_height(scroll_area)

        self.assertEqual(scroll_area.horizontalScrollBar().maximum(), 0)
        self.assertEqual(scroll_area.height(), container.sizeHint().height())

        form.resize(320, 100)
        self.app.processEvents()
        update_model_selection_scroll_area_height(scroll_area)

        self.assertGreater(scroll_area.horizontalScrollBar().maximum(), 0)
        self.assertEqual(
            scroll_area.horizontalScrollBar().sizeHint().height(), 16
        )
        self.assertEqual(
            scroll_area.height(),
            container.sizeHint().height()
            + scroll_area.horizontalScrollBar().sizeHint().height(),
        )

    def test_default_hidden_controls_do_not_stretch_buttons(self):
        form = QtWidgets.QWidget()
        self._widgets.append(form)
        ui_path = (
            Path(__file__).resolve().parents[2]
            / "anylabeling/views/labeling/widgets/auto_labeling/auto_labeling.ui"
        )
        uic.loadUi(str(ui_path), form)

        hidden_widget_names = (
            "button_run",
            "button_add_point",
            "button_remove_point",
            "button_add_rect",
            "add_pos_rect",
            "add_neg_rect",
            "button_run_rect",
            "button_clear",
            "button_finish_object",
            "button_send",
            "edit_text",
            "edit_conf",
            "edit_iou",
            "input_box_thres",
            "input_conf",
            "input_iou",
            "output_label",
            "output_select_combobox",
            "toggle_preserve_existing_annotations",
            "button_classes_filter",
            "button_auto_decode",
            "button_cropping",
            "button_skip_detection",
            "mask_fineness_slider",
            "mask_fineness_value_label",
        )
        for widget_name in hidden_widget_names:
            getattr(form, widget_name).hide()

        form.resize(1600, 100)
        form.show()
        self.app.processEvents()

        self.assertLessEqual(
            form.model_selection_button.width(),
            form.model_selection_button.sizeHint().width() + 2,
        )
        self.assertLessEqual(
            form.button_close.width(), form.button_close.sizeHint().width() + 2
        )

    def test_amg_uses_compact_button_without_inline_settings(self):
        form = QtWidgets.QWidget()
        self._widgets.append(form)
        ui_path = (
            Path(__file__).resolve().parents[2]
            / "anylabeling/views/labeling/widgets/auto_labeling/auto_labeling.ui"
        )

        uic.loadUi(str(ui_path), form)

        self.assertEqual(form.button_segment_everything.text(), "AMG")
        self.assertIsNone(
            form.findChild(QtWidgets.QSpinBox, "input_points_per_side")
        )
        self.assertIsNone(form.findChild(QtWidgets.QSpinBox, "input_min_area"))

    def test_amg_requires_confirmation_once_per_session(self):
        widget = Mock()
        widget.tr.side_effect = lambda text: text
        widget._amg_warning_confirmed = False

        warning_path = (
            "anylabeling.views.labeling.widgets.auto_labeling."
            "auto_labeling.QMessageBox.warning"
        )
        with patch(
            warning_path,
            side_effect=[
                QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.Yes,
            ],
        ) as warning:
            AutoLabelingWidget.on_segment_everything_clicked(widget)

            widget.model_manager.set_auto_labeling_marks.assert_not_called()
            widget.run_prediction.assert_not_called()
            self.assertFalse(widget._amg_warning_confirmed)

            AutoLabelingWidget.on_segment_everything_clicked(widget)
            self.assertTrue(widget._amg_warning_confirmed)

            AutoLabelingWidget.on_segment_everything_clicked(widget)

        self.assertEqual(warning.call_count, 2)
        self.assertEqual(
            widget.model_manager.set_auto_labeling_marks.call_count, 2
        )
        widget.model_manager.set_auto_labeling_marks.assert_called_with(
            [{"type": "auto_grid"}]
        )
        self.assertEqual(widget.run_prediction.call_count, 2)

    def test_initial_show_reflows_model_selection_row(self):
        config.current_config_file = (
            "anylabeling/configs/xanylabeling_config.yaml"
        )
        parent = type(
            "Parent",
            (),
            {
                "_config": get_config(),
                "new_shapes_from_auto_labeling": lambda _self, _result: None,
            },
        )()
        root = QtWidgets.QWidget()
        self._widgets.append(root)
        layout = QtWidgets.QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QtWidgets.QLabel("Mode"))
        layout.addSpacing(5)
        widget = AutoLabelingWidget(parent)
        widget.hide()
        layout.addWidget(widget)
        layout.addWidget(QtWidgets.QFrame(), 1)

        root.resize(1600, 300)
        root.show()
        self.app.processEvents()
        widget.show()
        self.app.processEvents()
        self.app.processEvents()

        button_top = widget.model_selection_button.mapTo(
            widget, widget.model_selection_button.rect().topLeft()
        ).y()
        scroll_top = widget.model_selection_scroll_area.geometry().top()
        button_bottom = (
            button_top + widget.model_selection_button.geometry().height()
        )
        status_top = widget.model_status_label.geometry().top()

        self.assertEqual(button_top, scroll_top)
        self.assertLessEqual(button_bottom, status_top)
        self.assertTrue(widget.button_segment_everything.isEnabled())
        widget.model_manager.prediction_started.emit()
        self.assertFalse(widget.button_segment_everything.isEnabled())
        widget.model_manager.prediction_finished.emit()
        self.assertTrue(widget.button_segment_everything.isEnabled())

    def test_more_panel_places_conf_iou_labels_before_spinboxes(self):
        """Regression: labels must not appear after the 0.25/0.45 spinboxes.

        Moving widgets into the More panel used to sort by object name
        (``edit_conf`` before ``input_conf``) and a follow-up reorder
        then appended the labels onto the outer toolbar.
        """
        config.current_config_file = (
            "anylabeling/configs/xanylabeling_config.yaml"
        )
        parent = type(
            "Parent",
            (),
            {
                "_config": get_config(),
                "new_shapes_from_auto_labeling": lambda _self, _result: None,
            },
        )()
        widget = AutoLabelingWidget(parent)
        self._widgets.append(widget)
        self.app.processEvents()

        more_panel = widget.findChild(QtWidgets.QWidget, "more_panel")
        self.assertIsNotNone(more_panel)
        layout = more_panel.layout()
        self.assertIsNotNone(layout)

        names = []
        for index in range(layout.count()):
            item = layout.itemAt(index)
            child = item.widget() if item is not None else None
            if child is not None:
                names.append(child.objectName())

        self.assertIn("input_conf", names)
        self.assertIn("edit_conf", names)
        self.assertIn("input_iou", names)
        self.assertIn("edit_iou", names)
        self.assertLess(names.index("input_conf"), names.index("edit_conf"))
        self.assertLess(names.index("input_iou"), names.index("edit_iou"))
        self.assertEqual(
            names.index("edit_conf"), names.index("input_conf") + 1
        )
        self.assertEqual(
            names.index("edit_iou"), names.index("input_iou") + 1
        )

        outer = widget.model_selection_scroll_area.widget().layout()
        self.assertLess(outer.indexOf(widget.input_conf), 0)
        self.assertLess(outer.indexOf(widget.input_iou), 0)

    def test_model_dropdown_search_matches_display_names(self):
        dropdown = SearchableModelDropdownPopup(
            {
                "Meta": {
                    "sam2_hiera_base_video-r20240901": {
                        "display_name": "Segment Anything 2 Video (Base)"
                    },
                    "sam2_hiera_base-r20240801": {
                        "display_name": "Segment Anything 2.1 (Base)"
                    },
                    "sam_hq_vit_b-r20231111": {
                        "display_name": "SAM-HQ (ViT-Base)"
                    },
                }
            }
        )
        self._widgets.append(dropdown)
        dropdown.show()
        self.app.processEvents()

        dropdown.filter_models("seg")
        self.app.processEvents()

        visible_names = [
            item.display_name
            for item in dropdown.model_items.values()
            if item.isVisible()
        ]

        self.assertIn("Segment Anything 2 Video (Base)", visible_names)
        self.assertIn("Segment Anything 2.1 (Base)", visible_names)
        self.assertNotIn("SAM-HQ (ViT-Base)", visible_names)

    def test_model_dropdown_task_filter_hides_other_groups(self):
        dropdown = SearchableModelDropdownPopup(
            {
                "CVHub": {
                    "yolov8n": {
                        "display_name": "YOLOv8n",
                        "type": "yolov8",
                    },
                    "yolov8s_seg": {
                        "display_name": "YOLOv8s-Seg",
                        "type": "yolov8_seg",
                    },
                }
            }
        )
        self._widgets.append(dropdown)
        dropdown.show()
        self.app.processEvents()

        dropdown.set_task_filter("detect")
        self.app.processEvents()
        visible_names = [
            item.display_name
            for item in dropdown.model_items.values()
            if item.isVisible()
        ]
        self.assertIn("YOLOv8n", visible_names)
        self.assertNotIn("YOLOv8s-Seg", visible_names)

    def test_init_model_data_drops_stale_cache_entries(self):
        """Regression: stale entries in xanylabeling_data/models.json must
        not leak into the dropdown after built-in presets change."""
        import json
        import tempfile
        import shutil

        from anylabeling.views.labeling.widgets import (
            searchable_model_dropdown as searchable_mod,
        )

        config.current_config_file = (
            "anylabeling/configs/xanylabeling_config.yaml"
        )

        tmp = tempfile.mkdtemp()
        cache_path = Path(tmp) / "models.json"
        cache_path.write_text(
            json.dumps(
                {
                    "models_data": {
                        "Custom": {
                            "load_custom_model": {
                                "selected": True,
                                "favorite": False,
                                "display_name": "...Load Custom Model",
                            }
                        },
                        "Meta": {
                            "sam2_hiera_base-r20240801": {
                                "selected": False,
                                "favorite": True,
                                "display_name": "Segment Anything 2.1 (Base)",
                            },
                            "sam2_hiera_tiny-r20240801": {
                                "selected": False,
                                "favorite": False,
                                "display_name": "Segment Anything 2.1 (Tiny)",
                            },
                            # Stale entries that must NOT appear.
                            "sam3_vit_h-r20260426": {
                                "selected": False,
                                "favorite": False,
                                "display_name": "Segment Anything 3 (ViT-H)",
                            },
                            "sam2_hiera_base_video-r20240901": {
                                "selected": False,
                                "favorite": False,
                                "display_name": "Segment Anything 2 Video (Base)",
                            },
                            "segment_anything_vit_h_quant-r20230810": {
                                "selected": False,
                                "favorite": False,
                                "display_name": "Segment Anything (ViT-Huge Quant)",
                            },
                        },
                        "Ultralytics": {
                            "yolov8s-r20230520": {
                                "selected": False,
                                "favorite": False,
                                "display_name": "YOLOv8s",
                            }
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        try:
            with patch.object(
                searchable_mod,
                "_get_models_config_path",
                return_value=str(cache_path),
            ):
                parent = type(
                    "Parent",
                    (),
                    {
                        "_config": get_config(),
                        "new_shapes_from_auto_labeling": (
                            lambda _self, _result: None
                        ),
                    },
                )()
                widget = AutoLabelingWidget(parent)
                self._widgets.append(widget)
                self.app.processEvents()

            meta = widget.model_dropdown.models_data.get("Meta", {})
            self.assertIn("sam2_hiera_base-r20240801", meta)
            self.assertIn("sam2_hiera_tiny-r20240801", meta)
            self.assertNotIn("sam3_vit_h-r20260426", meta)
            self.assertNotIn(
                "sam2_hiera_base_video-r20240901", meta
            )
            self.assertNotIn(
                "segment_anything_vit_h_quant-r20230810", meta
            )
            self.assertNotIn(
                "Ultralytics", widget.model_dropdown.models_data
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
