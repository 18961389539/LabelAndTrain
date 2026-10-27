"""Train-settings form construction for the training dialog.

The Config tab's Train Settings group is one declarative layout: presets, the
basic row and seven collapsible advanced sections. It lives here so the dialog
keeps the tab wiring and its stubs without owning the field tree; each section
builder adds one group to the layout it is given.
"""

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from anylabeling.services.auto_training.ultralytics.config import (
    DEFAULT_TRAINING_CONFIG,
    ICON_SIZE_NORMAL,
    NUM_WORKERS,
    OPTIMIZER_OPTIONS,
)
from anylabeling.services.auto_training.ultralytics.style import (
    get_advanced_toggle_btn_style,
)
from anylabeling.views.labeling.utils.qt import new_icon
from anylabeling.views.training.widgets.ultralytics_widgets import (
    CustomCheckBox,
    CustomComboBox,
    CustomDoubleSpinBox,
    CustomLineEdit,
    CustomSpinBox,
    SecondaryButton,
)


def init_train_settings(widget, parent_layout):
    group = QGroupBox(
        QCoreApplication.translate("UltralyticsDialog", "Train Settings")
    )
    layout = QVBoxLayout(group)

    _add_preset_row(widget, layout)
    _add_basic_group(widget, layout)
    _add_advanced_container(widget, layout)
    _add_recommend_row(widget, layout)

    parent_layout.addWidget(group)


def _add_preset_row(widget, layout):
    # Tuning tiers: one click answers "how hard should this run try?"
    # (the smart-recommend button below is the data-driven variant).
    preset_row = QHBoxLayout()
    preset_label = QLabel(
        QCoreApplication.translate("UltralyticsDialog", "Presets:")
    )
    preset_row.addWidget(preset_label)
    for key, label in (
        (
            "quick",
            QCoreApplication.translate("UltralyticsDialog", "Quick check"),
        ),
        (
            "standard",
            QCoreApplication.translate("UltralyticsDialog", "Standard"),
        ),
        (
            "high",
            QCoreApplication.translate("UltralyticsDialog", "High quality"),
        ),
    ):
        button = SecondaryButton(label)
        button.setToolTip(
            QCoreApplication.translate(
                "UltralyticsDialog",
                "Sets epochs, image size, patience, close-mosaic and "
                "cosine LR for this tier",
            )
        )
        button.clicked.connect(
            lambda _checked=False, name=key: widget.apply_param_preset(name)
        )
        preset_row.addWidget(button)
    preset_row.addStretch()
    layout.addLayout(preset_row)


def _add_basic_group(widget, layout):
    # Basic settings
    basic_group = QGroupBox(
        QCoreApplication.translate("UltralyticsDialog", "Basic")
    )
    basic_layout = QHBoxLayout(basic_group)
    basic_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "Epochs:"))
    )
    widget.config_widgets["epochs"] = CustomSpinBox()
    widget.config_widgets["epochs"].setRange(1, 10000)
    widget.config_widgets["epochs"].setValue(DEFAULT_TRAINING_CONFIG["epochs"])
    widget.config_widgets["epochs"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Number of training epochs. On CPU, start small to check the "
            "pipeline before a long run.",
        )
    )
    basic_layout.addWidget(widget.config_widgets["epochs"])

    basic_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "Batch:"))
    )
    widget.config_widgets["batch"] = CustomSpinBox()
    widget.config_widgets["batch"].setRange(-1, 8192)
    widget.config_widgets["batch"].setValue(DEFAULT_TRAINING_CONFIG["batch"])
    widget.config_widgets["batch"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Images per batch. -1 picks the batch automatically (GPU "
            "only; on CPU it falls back to 16). Lower it if training runs "
            "out of memory.",
        )
    )
    basic_layout.addWidget(widget.config_widgets["batch"])

    basic_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "Image Size:"))
    )
    widget.config_widgets["imgsz"] = CustomSpinBox()
    widget.config_widgets["imgsz"].setRange(32, 8192)
    widget.config_widgets["imgsz"].setValue(DEFAULT_TRAINING_CONFIG["imgsz"])
    widget.config_widgets["imgsz"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Training image size. Smaller trains faster: 640 is the "
            "default, 416 a common CPU choice.",
        )
    )
    basic_layout.addWidget(widget.config_widgets["imgsz"])

    basic_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "Workers:"))
    )
    widget.config_widgets["workers"] = CustomSpinBox()
    widget.config_widgets["workers"].setRange(0, NUM_WORKERS)
    widget.config_widgets["workers"].setValue(
        DEFAULT_TRAINING_CONFIG["workers"]
    )
    widget.config_widgets["workers"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Data-loader worker processes. Ultralytics forces 0 on CPU; "
            "0-2 is the safest range on Windows.",
        )
    )
    basic_layout.addWidget(widget.config_widgets["workers"])

    basic_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "Classes:"))
    )
    widget.config_widgets["classes"] = CustomLineEdit()
    widget.config_widgets["classes"].setText(
        DEFAULT_TRAINING_CONFIG["classes"]
    )
    widget.config_widgets["classes"].setPlaceholderText(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Class indices (e.g., 0,1,2) or leave empty for all",
        )
    )
    basic_layout.addWidget(widget.config_widgets["classes"])

    widget.config_widgets["single_cls"] = CustomCheckBox(
        QCoreApplication.translate("UltralyticsDialog", "Single Class")
    )
    widget.config_widgets["single_cls"].setChecked(
        DEFAULT_TRAINING_CONFIG["single_cls"]
    )
    basic_layout.addWidget(widget.config_widgets["single_cls"])

    basic_layout.addStretch()
    layout.addWidget(basic_group)


def _add_advanced_container(widget, layout):
    # Advanced settings
    advanced_container = QWidget()
    advanced_container_layout = QVBoxLayout(advanced_container)
    advanced_container_layout.setContentsMargins(0, 0, 0, 0)

    header_widget = QWidget()
    header_layout = QHBoxLayout(header_widget)
    header_layout.setContentsMargins(0, 0, 0, 0)
    header_layout.setSpacing(5)

    advanced_label = QLabel(
        QCoreApplication.translate("UltralyticsDialog", "Advanced Settings")
    )
    advanced_label.setStyleSheet("font-weight: bold;")
    header_layout.addWidget(advanced_label)

    # Collapse/Expand button
    widget.advanced_toggle_btn = QPushButton()
    widget.advanced_toggle_btn.setFixedSize(*ICON_SIZE_NORMAL)
    widget.advanced_toggle_btn.setStyleSheet(get_advanced_toggle_btn_style())
    widget.advanced_toggle_btn.setIcon(QIcon(new_icon("caret-down", "svg")))
    widget.advanced_toggle_btn.clicked.connect(widget.toggle_advanced_settings)
    header_layout.addWidget(widget.advanced_toggle_btn)
    header_layout.addStretch()
    advanced_container_layout.addWidget(header_widget)

    widget.advanced_content_widget = QWidget()
    widget.advanced_content_widget.setVisible(False)
    advanced_layout = QVBoxLayout(widget.advanced_content_widget)

    _add_strategy_group(widget, advanced_layout)
    _add_learning_rate_group(widget, advanced_layout)
    _add_warmup_group(widget, advanced_layout)
    _add_augmentation_group(widget, advanced_layout)
    _add_regularization_group(widget, advanced_layout)
    _add_loss_weights_group(widget, advanced_layout)
    _add_checkpoint_group(widget, advanced_layout)

    advanced_container_layout.addWidget(widget.advanced_content_widget)
    layout.addWidget(advanced_container)


def _add_strategy_group(widget, advanced_layout):
    # 1. Training Strategy
    strategy_group = QGroupBox(
        QCoreApplication.translate("UltralyticsDialog", "Training Strategy")
    )
    strat_layout = QHBoxLayout(strategy_group)
    strat_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "Time (h):"))
    )
    widget.config_widgets["time"] = CustomDoubleSpinBox()
    widget.config_widgets["time"].setValue(DEFAULT_TRAINING_CONFIG["time"])
    widget.config_widgets["time"].setSpecialValueText("None")
    widget.config_widgets["time"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Wall-clock limit in hours; training stops when it is reached "
            "(None = no limit).",
        )
    )
    strat_layout.addWidget(widget.config_widgets["time"])

    strat_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "Patience:"))
    )
    widget.config_widgets["patience"] = CustomSpinBox()
    widget.config_widgets["patience"].setRange(1, 10000)
    widget.config_widgets["patience"].setValue(
        DEFAULT_TRAINING_CONFIG["patience"]
    )
    widget.config_widgets["patience"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Stop early after this many epochs without an improvement. "
            "Lower it to fail fast while experimenting.",
        )
    )
    strat_layout.addWidget(widget.config_widgets["patience"])

    strat_layout.addWidget(
        QLabel(
            QCoreApplication.translate("UltralyticsDialog", "Close Mosaic:")
        )
    )
    widget.config_widgets["close_mosaic"] = CustomSpinBox()
    widget.config_widgets["close_mosaic"].setRange(0, 1000)
    widget.config_widgets["close_mosaic"].setValue(
        DEFAULT_TRAINING_CONFIG["close_mosaic"]
    )
    widget.config_widgets["close_mosaic"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Disable mosaic augmentation for the last N epochs so the "
            "model finishes on clean images (0 keeps it on).",
        )
    )
    strat_layout.addWidget(widget.config_widgets["close_mosaic"])

    strat_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "Optimizer:"))
    )
    widget.config_widgets["optimizer"] = CustomComboBox()
    widget.config_widgets["optimizer"].addItems(OPTIMIZER_OPTIONS)
    widget.config_widgets["optimizer"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Weight-update algorithm. 'auto' picks one from the model and "
            "dataset size; SGD and AdamW are the usual manual choices.",
        )
    )
    strat_layout.addWidget(widget.config_widgets["optimizer"])

    widget.config_widgets["cos_lr"] = CustomCheckBox(
        QCoreApplication.translate("UltralyticsDialog", "Cosine LR")
    )
    widget.config_widgets["cos_lr"].setChecked(
        DEFAULT_TRAINING_CONFIG["cos_lr"]
    )
    widget.config_widgets["cos_lr"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Cosine learning-rate schedule: the rate decays smoothly to "
            "its final value instead of dropping linearly.",
        )
    )
    strat_layout.addWidget(widget.config_widgets["cos_lr"])
    widget.config_widgets["amp"] = CustomCheckBox(
        QCoreApplication.translate("UltralyticsDialog", "AMP")
    )
    widget.config_widgets["amp"].setChecked(DEFAULT_TRAINING_CONFIG["amp"])
    strat_layout.addWidget(widget.config_widgets["amp"])
    widget.config_widgets["multi_scale"] = CustomCheckBox(
        QCoreApplication.translate("UltralyticsDialog", "Multi Scale")
    )
    widget.config_widgets["multi_scale"].setChecked(
        DEFAULT_TRAINING_CONFIG["multi_scale"]
    )
    widget.config_widgets["multi_scale"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Randomly rescales inputs during training. Costs CPU time "
            "with little benefit there.",
        )
    )
    strat_layout.addWidget(widget.config_widgets["multi_scale"])
    strat_layout.addStretch()
    advanced_layout.addWidget(strategy_group)


def _add_learning_rate_group(widget, advanced_layout):
    # 2. Learning Rate
    lr_group = QGroupBox(
        QCoreApplication.translate("UltralyticsDialog", "Learning Rate")
    )
    lr_layout = QHBoxLayout(lr_group)
    lr_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "LR0:"))
    )
    widget.config_widgets["lr0"] = CustomDoubleSpinBox()
    widget.config_widgets["lr0"].setDecimals(6)
    widget.config_widgets["lr0"].setValue(DEFAULT_TRAINING_CONFIG["lr0"])
    widget.config_widgets["lr0"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Initial learning rate. Lower it if the loss explodes; raise "
            "it if learning stalls.",
        )
    )
    lr_layout.addWidget(widget.config_widgets["lr0"])

    lr_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "LRF:"))
    )
    widget.config_widgets["lrf"] = CustomDoubleSpinBox()
    widget.config_widgets["lrf"].setDecimals(6)
    widget.config_widgets["lrf"].setValue(DEFAULT_TRAINING_CONFIG["lrf"])
    widget.config_widgets["lrf"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Final learning rate as a fraction of LR0 (0.01 = 1%): the "
            "rate travels from LR0 down to this.",
        )
    )
    lr_layout.addWidget(widget.config_widgets["lrf"])

    lr_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "Momentum:"))
    )
    widget.config_widgets["momentum"] = CustomDoubleSpinBox()
    widget.config_widgets["momentum"].setDecimals(3)
    widget.config_widgets["momentum"].setValue(
        DEFAULT_TRAINING_CONFIG["momentum"]
    )
    widget.config_widgets["momentum"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Momentum for SGD (beta1 for the Adam family); it smooths how "
            "much the previous step steers the next one.",
        )
    )
    lr_layout.addWidget(widget.config_widgets["momentum"])

    lr_layout.addWidget(
        QLabel(
            QCoreApplication.translate("UltralyticsDialog", "Weight Decay:")
        )
    )
    widget.config_widgets["weight_decay"] = CustomDoubleSpinBox()
    widget.config_widgets["weight_decay"].setDecimals(6)
    widget.config_widgets["weight_decay"].setValue(
        DEFAULT_TRAINING_CONFIG["weight_decay"]
    )
    widget.config_widgets["weight_decay"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Penalty on large weights: higher fights overfitting, too high "
            "underfits.",
        )
    )
    lr_layout.addWidget(widget.config_widgets["weight_decay"])
    lr_layout.addStretch()
    advanced_layout.addWidget(lr_group)


def _add_warmup_group(widget, advanced_layout):
    # 3. Warmup Parameters
    warmup_group = QGroupBox(
        QCoreApplication.translate("UltralyticsDialog", "Warmup Parameters")
    )
    warmup_layout = QHBoxLayout(warmup_group)
    warmup_layout.addWidget(
        QLabel(
            QCoreApplication.translate("UltralyticsDialog", "Warmup Epochs:")
        )
    )
    widget.config_widgets["warmup_epochs"] = CustomDoubleSpinBox()
    widget.config_widgets["warmup_epochs"].setDecimals(1)
    widget.config_widgets["warmup_epochs"].setValue(
        DEFAULT_TRAINING_CONFIG["warmup_epochs"]
    )
    widget.config_widgets["warmup_epochs"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Epochs spent ramping the learning rate up from zero: a "
            "stabiliser at the start, but they count toward the total.",
        )
    )
    warmup_layout.addWidget(widget.config_widgets["warmup_epochs"])

    warmup_layout.addWidget(
        QLabel(
            QCoreApplication.translate("UltralyticsDialog", "Warmup Momentum:")
        )
    )
    widget.config_widgets["warmup_momentum"] = CustomDoubleSpinBox()
    widget.config_widgets["warmup_momentum"].setDecimals(3)
    widget.config_widgets["warmup_momentum"].setValue(
        DEFAULT_TRAINING_CONFIG["warmup_momentum"]
    )
    widget.config_widgets["warmup_momentum"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Momentum at the start of warmup; it ramps up to the main "
            "value.",
        )
    )
    warmup_layout.addWidget(widget.config_widgets["warmup_momentum"])

    warmup_layout.addWidget(
        QLabel(
            QCoreApplication.translate("UltralyticsDialog", "Warmup Bias LR:")
        )
    )
    widget.config_widgets["warmup_bias_lr"] = CustomDoubleSpinBox()
    widget.config_widgets["warmup_bias_lr"].setDecimals(3)
    widget.config_widgets["warmup_bias_lr"].setValue(
        DEFAULT_TRAINING_CONFIG["warmup_bias_lr"]
    )
    widget.config_widgets["warmup_bias_lr"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Learning rate for bias terms during warmup, usually higher "
            "than LR0 so they can move early.",
        )
    )
    warmup_layout.addWidget(widget.config_widgets["warmup_bias_lr"])
    warmup_layout.addStretch()
    advanced_layout.addWidget(warmup_group)


def _add_augmentation_group(widget, advanced_layout):
    # 4. Augmentation Settings
    augment_group = QGroupBox(
        QCoreApplication.translate(
            "UltralyticsDialog", "Augmentation Settings"
        )
    )
    augment_layout = QVBoxLayout(augment_group)
    augment_params = [
        (
            "hsv_h",
            QCoreApplication.translate("UltralyticsDialog", "HSV Hue:"),
            DEFAULT_TRAINING_CONFIG["hsv_h"],
            0.0,
            1.0,
            3,
            QCoreApplication.translate(
                "UltralyticsDialog",
                "Random hue shift as a fraction of the colour wheel. Keep "
                "small; 0 disables.",
            ),
        ),
        (
            "hsv_s",
            QCoreApplication.translate("UltralyticsDialog", "HSV Saturation:"),
            DEFAULT_TRAINING_CONFIG["hsv_s"],
            0.0,
            1.0,
            3,
            QCoreApplication.translate(
                "UltralyticsDialog",
                "Random saturation shift; useful when lighting varies "
                "across the images.",
            ),
        ),
        (
            "hsv_v",
            QCoreApplication.translate("UltralyticsDialog", "HSV Value:"),
            DEFAULT_TRAINING_CONFIG["hsv_v"],
            0.0,
            1.0,
            3,
            QCoreApplication.translate(
                "UltralyticsDialog",
                "Random brightness shift; useful when exposure varies "
                "across the images.",
            ),
        ),
        (
            "degrees",
            QCoreApplication.translate(
                "UltralyticsDialog", "Rotation Degrees:"
            ),
            DEFAULT_TRAINING_CONFIG["degrees"],
            -180.0,
            180.0,
            1,
            QCoreApplication.translate(
                "UltralyticsDialog",
                "Random rotation range in degrees. Use it only if the "
                "objects really appear rotated.",
            ),
        ),
        (
            "translate",
            QCoreApplication.translate("UltralyticsDialog", "Translate:"),
            DEFAULT_TRAINING_CONFIG["translate"],
            0.0,
            1.0,
            3,
            QCoreApplication.translate(
                "UltralyticsDialog",
                "Random translation as a fraction of the image size.",
            ),
        ),
        (
            "scale",
            QCoreApplication.translate("UltralyticsDialog", "Scale:"),
            DEFAULT_TRAINING_CONFIG["scale"],
            0.0,
            2.0,
            3,
            QCoreApplication.translate(
                "UltralyticsDialog",
                "Random zoom range (0.5 means +/-50%): teaches size "
                "robustness.",
            ),
        ),
        (
            "shear",
            QCoreApplication.translate("UltralyticsDialog", "Shear:"),
            DEFAULT_TRAINING_CONFIG["shear"],
            -45.0,
            45.0,
            1,
            QCoreApplication.translate(
                "UltralyticsDialog", "Random shear in degrees; rarely needed."
            ),
        ),
        (
            "perspective",
            QCoreApplication.translate("UltralyticsDialog", "Perspective:"),
            DEFAULT_TRAINING_CONFIG["perspective"],
            0.0,
            0.001,
            6,
            QCoreApplication.translate(
                "UltralyticsDialog",
                "Random perspective warp as a fraction (very small "
                "values); helps with tilted viewpoints.",
            ),
        ),
    ]

    grid_layout = QGridLayout()
    grid_layout.setHorizontalSpacing(10)
    grid_layout.setVerticalSpacing(5)
    for i, (
        param,
        label,
        default,
        min_val,
        max_val,
        decimals,
        tooltip,
    ) in enumerate(augment_params):
        row = i // 4
        col = (i % 4) * 2

        label_widget = QLabel(label)
        label_widget.setMinimumWidth(80)
        grid_layout.addWidget(label_widget, row, col)

        spin = CustomDoubleSpinBox()
        spin.setRange(min_val, max_val)
        spin.setDecimals(decimals)
        spin.setValue(default)
        spin.setMinimumWidth(80)
        spin.setToolTip(tooltip)
        widget.config_widgets[param] = spin
        grid_layout.addWidget(spin, row, col + 1)

    for col in range(8, 10):
        grid_layout.setColumnStretch(col, 1)
    augment_layout.addLayout(grid_layout)
    advanced_layout.addWidget(augment_group)


def _add_regularization_group(widget, advanced_layout):
    # 5. Regularization
    reg_group = QGroupBox(
        QCoreApplication.translate("UltralyticsDialog", "Regularization")
    )
    reg_layout = QHBoxLayout(reg_group)
    reg_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "Dropout:"))
    )
    widget.config_widgets["dropout"] = CustomDoubleSpinBox()
    widget.config_widgets["dropout"].setDecimals(3)
    widget.config_widgets["dropout"].setValue(
        DEFAULT_TRAINING_CONFIG["dropout"]
    )
    widget.config_widgets["dropout"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Dropout for classification heads only; it does nothing for "
            "detect/segment/pose.",
        )
    )
    reg_layout.addWidget(widget.config_widgets["dropout"])

    reg_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "Fraction:"))
    )
    widget.config_widgets["fraction"] = CustomDoubleSpinBox()
    widget.config_widgets["fraction"].setDecimals(3)
    widget.config_widgets["fraction"].setValue(
        DEFAULT_TRAINING_CONFIG["fraction"]
    )
    widget.config_widgets["fraction"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Fraction of the training set used per run (1.0 = all). "
            "Lower it for quick experiments.",
        )
    )
    reg_layout.addWidget(widget.config_widgets["fraction"])

    widget.config_widgets["rect"] = CustomCheckBox(
        QCoreApplication.translate("UltralyticsDialog", "Rectangular")
    )
    widget.config_widgets["rect"].setChecked(DEFAULT_TRAINING_CONFIG["rect"])
    widget.config_widgets["rect"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Rectangular training batches: less padding and faster, but "
            "validation loses the batch-shape consistency.",
        )
    )
    reg_layout.addWidget(widget.config_widgets["rect"])
    reg_layout.addStretch()
    advanced_layout.addWidget(reg_group)


def _add_loss_weights_group(widget, advanced_layout):
    # 6. Loss Weights
    loss_group = QGroupBox(
        QCoreApplication.translate("UltralyticsDialog", "Loss Weights")
    )
    loss_layout = QHBoxLayout(loss_group)
    loss_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "Box:"))
    )
    widget.config_widgets["box"] = CustomDoubleSpinBox()
    widget.config_widgets["box"].setDecimals(2)
    widget.config_widgets["box"].setValue(DEFAULT_TRAINING_CONFIG["box"])
    widget.config_widgets["box"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Weight of the box-position loss: raise it when the boxes are "
            "loose around the objects.",
        )
    )
    loss_layout.addWidget(widget.config_widgets["box"])

    loss_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "Cls:"))
    )
    widget.config_widgets["cls"] = CustomDoubleSpinBox()
    widget.config_widgets["cls"].setDecimals(2)
    widget.config_widgets["cls"].setValue(DEFAULT_TRAINING_CONFIG["cls"])
    widget.config_widgets["cls"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Weight of the classification loss: raise it when classes are "
            "being confused.",
        )
    )
    loss_layout.addWidget(widget.config_widgets["cls"])

    loss_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "DFL:"))
    )
    widget.config_widgets["dfl"] = CustomDoubleSpinBox()
    widget.config_widgets["dfl"].setDecimals(2)
    widget.config_widgets["dfl"].setValue(DEFAULT_TRAINING_CONFIG["dfl"])
    widget.config_widgets["dfl"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Weight of the distribution-focal loss: how sharply box edges "
            "are localised.",
        )
    )
    loss_layout.addWidget(widget.config_widgets["dfl"])

    loss_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "Pose:"))
    )
    widget.config_widgets["pose"] = CustomDoubleSpinBox()
    widget.config_widgets["pose"].setDecimals(2)
    widget.config_widgets["pose"].setValue(DEFAULT_TRAINING_CONFIG["pose"])
    widget.config_widgets["pose"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Weight of the keypoint loss; pose tasks only.",
        )
    )
    loss_layout.addWidget(widget.config_widgets["pose"])

    loss_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "Kobj:"))
    )
    widget.config_widgets["kobj"] = CustomDoubleSpinBox()
    widget.config_widgets["kobj"].setDecimals(2)
    widget.config_widgets["kobj"].setValue(DEFAULT_TRAINING_CONFIG["kobj"])
    widget.config_widgets["kobj"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Weight of the keypoint-objectness loss; pose tasks only.",
        )
    )
    loss_layout.addWidget(widget.config_widgets["kobj"])
    loss_layout.addStretch()
    advanced_layout.addWidget(loss_group)


def _add_checkpoint_group(widget, advanced_layout):
    # 7. Checkpoint and Validation
    ckpt_group = QGroupBox(
        QCoreApplication.translate(
            "UltralyticsDialog", "Checkpoint and Validation"
        )
    )
    ckpt_layout = QHBoxLayout(ckpt_group)
    ckpt_layout.addWidget(
        QLabel(QCoreApplication.translate("UltralyticsDialog", "Save Period:"))
    )
    widget.config_widgets["save_period"] = CustomSpinBox()
    widget.config_widgets["save_period"].setRange(-1, 1000)
    widget.config_widgets["save_period"].setValue(
        DEFAULT_TRAINING_CONFIG["save_period"]
    )
    widget.config_widgets["save_period"].setSpecialValueText("Disabled")
    widget.config_widgets["save_period"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Save a checkpoint every N epochs (Disabled = only the final "
            "one).",
        )
    )
    ckpt_layout.addWidget(widget.config_widgets["save_period"])

    widget.config_widgets["val"] = CustomCheckBox(
        QCoreApplication.translate("UltralyticsDialog", "Validation")
    )
    widget.config_widgets["val"].setChecked(DEFAULT_TRAINING_CONFIG["val"])
    widget.config_widgets["val"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Validate after every epoch. Turning it off is faster but "
            "leaves no mAP curve and no best.pt to export.",
        )
    )
    ckpt_layout.addWidget(widget.config_widgets["val"])
    widget.config_widgets["plots"] = CustomCheckBox(
        QCoreApplication.translate("UltralyticsDialog", "Plots")
    )
    widget.config_widgets["plots"].setChecked(DEFAULT_TRAINING_CONFIG["plots"])
    widget.config_widgets["plots"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Write the training plots (curves, confusion matrix) into the "
            "run directory.",
        )
    )
    ckpt_layout.addWidget(widget.config_widgets["plots"])
    widget.config_widgets["save"] = CustomCheckBox(
        QCoreApplication.translate("UltralyticsDialog", "Save")
    )
    widget.config_widgets["save"].setChecked(DEFAULT_TRAINING_CONFIG["save"])
    widget.config_widgets["save"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog", "Save checkpoints while training runs."
        )
    )
    ckpt_layout.addWidget(widget.config_widgets["save"])
    widget.config_widgets["resume"] = CustomCheckBox(
        QCoreApplication.translate("UltralyticsDialog", "Resume")
    )
    widget.config_widgets["resume"].setChecked(
        DEFAULT_TRAINING_CONFIG["resume"]
    )
    widget.config_widgets["resume"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Continue an interrupted run from its last checkpoint; a "
            "stopped run also offers this in the directory dialog.",
        )
    )
    ckpt_layout.addWidget(widget.config_widgets["resume"])
    widget.config_widgets["cache"] = CustomCheckBox(
        QCoreApplication.translate("UltralyticsDialog", "Cache")
    )
    widget.config_widgets["cache"].setChecked(DEFAULT_TRAINING_CONFIG["cache"])
    widget.config_widgets["cache"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Keep the dataset in RAM: faster epochs when the images fit in "
            "memory.",
        )
    )
    ckpt_layout.addWidget(widget.config_widgets["cache"])
    widget.config_widgets["skip_empty_files"] = CustomCheckBox(
        QCoreApplication.translate("UltralyticsDialog", "Skip Empty Files")
    )
    widget.config_widgets["skip_empty_files"].setChecked(False)
    widget.config_widgets["skip_empty_files"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Leave images with no shapes out of training; otherwise they "
            "act as background (negative) samples.",
        )
    )
    ckpt_layout.addWidget(widget.config_widgets["skip_empty_files"])
    widget.config_widgets["only_checked_files"] = CustomCheckBox(
        QCoreApplication.translate("UltralyticsDialog", "Only Checked Files")
    )
    widget.config_widgets["only_checked_files"].setChecked(False)
    widget.config_widgets["only_checked_files"].setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Train only on images marked as confirmed in the label list.",
        )
    )
    ckpt_layout.addWidget(widget.config_widgets["only_checked_files"])
    ckpt_layout.addStretch()
    advanced_layout.addWidget(ckpt_group)


def _add_recommend_row(widget, layout):
    # Smart recommendation button on its own row (the Basic row above is
    # already dense; squeezing it there broke narrow windows).
    from anylabeling.views.labeling.utils.style import (
        get_highlight_button_style,
    )

    recommend_row = QHBoxLayout()
    recommend_row.addStretch()
    recommend_btn = QPushButton(
        QCoreApplication.translate("UltralyticsDialog", "Smart Recommend")
    )
    recommend_btn.setToolTip(
        QCoreApplication.translate(
            "UltralyticsDialog",
            "Auto-fill epochs/batch/imgsz from the current labeled folder and past iterations",
        )
    )
    recommend_btn.setStyleSheet(get_highlight_button_style(compact=True))
    recommend_btn.clicked.connect(widget.run_smart_recommendation)
    recommend_row.addWidget(recommend_btn)
    layout.addLayout(recommend_row)
