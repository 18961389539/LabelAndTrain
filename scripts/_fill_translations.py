"""Fill the Chinese text for the catalogue entries cf7a09c left empty.

These 302 English sources reached the catalogue when that batch replaced
``widget.tr(...)`` with an explicit ``translate()`` — the extractor cannot
attribute a bare ``widget.tr`` outside a class, so they had never been in
the catalogue and never had a translation. Their translation slots were
then filled by the accident that corrupted the file.

Applied by source text, so a context move cannot misplace one. Placeholders
(``%1``) and markup (``<br>``, ``<code>``) are preserved verbatim.

Run once, then re-run scripts/generate_languages.py to rebuild the .qm.
"""

import xml.etree.ElementTree as ET

TS = "anylabeling/resources/translations/zh_CN.ts"

TRANSLATIONS = {
    # --- LabelingWidget: export / upload / crop ---------------------------
    "YOLO OBB": "YOLO OBB",
    "Upload Custom YOLO Oriented Bounding Boxes Annotations": (
        "导入自定义 YOLO 旋转框标注"
    ),
    "Export Custom YOLO Oriented Bounding Boxes Annotations": (
        "导出自定义 YOLO 旋转框标注"
    ),
    "Toggle Sidebar": "收起/展开右侧栏",
    "Processing completed successfully!": "处理完成。",
    "Processing finished: %d succeeded, %d failed (of %d total).": (
        "处理结束：成功 %d 张，失败 %d 张（共 %d 张）。"
    ),
    "Processing completed successfully! (%d images processed)": (
        "处理完成。（共处理 %d 张图）"
    ),
    "Error occurred while processing images!": "处理图片时出错。",
    "Batch Processing": "批量处理",
    "Invalid model type, please choose a valid model_type to run.": (
        "模型类型无效，请选择一个有效的 model_type 后再运行。"
    ),
    "Please load an image folder before proceeding!": "请先打开一个图片文件夹。",
    "Cropped Image Options": "裁剪图片选项",
    "Save Path": "保存路径",
    "Select Save Directory": "选择保存目录",
    "Browse": "浏览",
    "Minimum width:": "最小宽度：",
    "Minimum height:": "最小高度：",
    "Select a specific yolo-pose config file": "选择 yolo-pose 配置文件",
    "Invalid pose config file:\n%s": "姿态配置文件无效：\n%s",
    "The class list is empty - nothing can be exported.": (
        "类别列表为空，没有可导出的内容。"
    ),
    "Export options": "导出选项",
    "Export path": "导出路径",
    "Select Export Directory": "选择导出目录",
    "Export Options": "导出选项",
    "Save with images?": "同时复制图片？",
    "Skip empty labels?": "跳过空标注？",
    "Export cancelled.\nThe current labels could not be saved first.": (
        "已取消导出。\n无法先保存当前标签列表。"
    ),
    "Exporting...": "正在导出…",
    "Select a specific coco-pose config file": "选择 coco-pose 配置文件",
    "Select a specific classes file": "选择类别文件",
    "Converting...": "正在转换…",
    "Error occurred while converting shapes!": "转换标注时出错。",
    "Select a custom coco annotation file": "选择自定义 COCO 标注文件",
    "Current annotation will be lost": "当前标注将丢失",
    "You are going to upload new annotations to this task. Continue?": (
        "即将把新标注导入到本任务。是否继续？"
    ),
    "Uploading...": "正在导入…",
    "Upload Options": "导入选项",
    "Select Upload Folder": "选择导入目录",
    "Uploading annotations successfully!\nResults have been saved to:\n%s": (
        "标注导入成功。\n结果已保存到：\n%s"
    ),
    "The class list is empty - nothing can be imported.": (
        "类别列表为空，没有可导入的内容。"
    ),
    "Preserve existing annotations": "保留已有标注",
    "New annotations will be merged with existing ones": (
        "新标注会与已有标注合并"
    ),
    "You are going to add new annotations to this task. Existing annotations will be preserved. Continue?": (  # noqa: E501
        "即将为本任务添加新标注，已有标注会保留。是否继续？"
    ),
    "Upload completed successfully!": "导入完成。",
    "Select a specific label classes file": "选择标签类别文件",
    "No labels found in the file!": "文件里没有找到标签。",
    "Current labels will be lost": "当前标签列表将丢失",
    "You are going to upload new labels to this task. Continue?": (
        "即将为本任务导入新的标签列表。是否继续？"
    ),
    "Select a specific shape attributes file": "选择标注属性文件",
    "Select a specific flags file": "选择标志文件",
    "Visualization Image Options": "可视化图片选项",
    "Export Range": "导出范围",
    "Current Frame": "当前帧",
    "All Files": "全部文件",
    "Shape Types": "标注类型",
    "Visualization Options": "可视化选项",
    "Save Labels": "保存标签",
    "Save Scores": "保存分数",
    "Save Group IDs": "保存分组 ID",
    "Save Texts": "保存文本",
    "Save Semi-transparent Masks": "保存半透明掩码",
    "Skip Empty Files": "跳过空文件",
    "Shape Types Required": "需要选择标注类型",
    "No shape types selected. Please select at least one shape type before exporting.": (  # noqa: E501
        "尚未选择标注类型。导出前请至少勾选一种。"
    ),
    "Batch zip export does not support nested or mixed directories yet.": (
        "批量打包导出暂不支持含子目录或混合内容的目录。"
    ),
    "PNG Image (*.png);;All Files (*)": "PNG 图片 (*.png);;所有文件 (*)",
    "Save Visualization Images": "保存可视化图片",
    "Zip Archive (*.zip);;All Files (*)": "ZIP 压缩包 (*.zip);;所有文件 (*)",
    "Error occurred while exporting visualization image!": (
        "导出可视化图片时出错。"
    ),
    "Visualization image saved to:\n%s": "可视化图片已保存到：\n%s",
    "Error occurred while exporting visualization images!": (
        "批量导出可视化图片时出错。"
    ),
    "No files to export.": "没有可导出的文件。",
    "Visualization images saved to:\n%s": "可视化图片已保存到：\n%s",
    "Output File Exists!": "输出文件已存在",
    "File already exists. Choose an action:": "文件已存在，请选择处理方式：",
    "• Overwrite - Overwrite existing file\n• Cancel - Abort export": (
        "• 覆盖 —— 覆盖已有文件\n• 取消 —— 放弃导出"
    ),
    "Overwrite": "覆盖",
    # --- training window missing dependency ------------------------------
    "Missing Ultralytics": "缺少 ultralytics",
    "ultralytics is not installed, so the training window cannot be opened.<br>Install it first:<br><code>pip install ultralytics</code><br>or<br><code>uv pip install ultralytics --torch-backend=auto</code>": (  # noqa: E501
        "未安装 ultralytics，无法打开训练窗口。<br>请先安装："
        "<br><code>pip install ultralytics</code><br>或<br>"
        "<code>uv pip install ultralytics --torch-backend=auto</code>"
    ),
    "Feed Back Now": "立即回填",
    "Training weights loaded. Re-run auto-labeling on unlabeled and pending-review images; the Iteration Gains Board updates automatically when done.\nConfirmed empty labels (negatives) are skipped.\n\n%1\n\nStart now?": (  # noqa: E501
        "训练权重已加载。可对未标注和待复核的图片重跑自动标注，完成后迭代收益看板会自动更新。\n"
        "已确认为空标注（负样本）的图片会被跳过。\n\n%1\n\n现在开始吗？"
    ),
    "Check the next-step suggestions in the Iteration Gains Board later.": (
        "稍后可在迭代收益看板查看下一步建议。"
    ),
    "The OpenCV DNN engine handles detection, segmentation and tracking models only; '%1' needs an ONNX engine.": (  # noqa: E501
        "OpenCV DNN 引擎只支持检测、分割和跟踪模型；'%1' 需要 ONNX 引擎。"
    ),
    # --- run history -----------------------------------------------------
    "Run History": "训练历史",
    "Export CSV": "导出 CSV",
    "Open Run Directory": "打开运行目录",
    "Refresh": "刷新",
    "%1 recorded runs": "已记录 %1 次训练",
    "%1 more runs predate the metadata feature and are not listed": (
        "另有 %1 次训练早于元数据功能，未列出"
    ),
    "Best mAP50 %1 (%2)": "最佳 mAP50 %1（%2）",
    "Last two runs {arrow} {delta} ({from_} → {to})": (
        "最近两次 {arrow} {delta}（{from_} → {to}）"
    ),
    "No training runs with metadata found under %1. After a training run finishes, run_meta.json appears in the run directory and shows up in this table; runs whose Project points elsewhere are not visible here.": (  # noqa: E501
        "在 %1 下没有找到带元数据的训练记录。一次训练结束后，运行目录里会出现 "
        "run_meta.json，并显示在这张表里；Project 指向别处的记录不会出现在这里。"
    ),
    "Select a run row first.": "请先选中一行训练记录。",
    "That run directory no longer exists.": "该运行目录已不存在。",
    "There are no runs to export.": "没有可导出的训练记录。",
    "Export Run History": "导出训练历史",
    "Export Failed": "导出失败",
    "Export Complete": "导出完成",
    "Run history exported to: %1": "训练历史已导出到：%1",
    "Open in System Viewer": "用系统程序打开",
    # --- training step bar ------------------------------------------------
    "1. Data": "1. 数据",
    "2. Config": "2. 配置",
    "3. Train": "3. 训练",
    "Data is ready": "数据已就绪",
    "Set model and hyperparameters": "设置模型与超参数",
    "Preparing dataset": "正在准备数据集",
    "Training completed": "训练完成",
    "Start training and watch the log": "开始训练并观察日志",
    # --- training data tab ------------------------------------------------
    "No images yet. Open a folder in the main window first.": (
        "还没有图片。请先在主窗口打开一个文件夹。"
    ),
    "%1 images · %2 classes · %3 labeled · %4 empty": (
        "%1 张图 · %2 个类别 · %3 张已标注 · %4 张空标注"
    ),
    "Select a task type": "选择任务类型",
    "%1 more labeled image(s) needed": "还需要 %1 张已标注图片",
    "No Classes Found": "没有找到类别",
    "This folder's labels do not contain any class names yet. Label at least one image first.": (  # noqa: E501
        "这个文件夹的标注里还没有任何类别名。请先标注至少一张图片。"
    ),
    "Write Failed": "写入失败",
    "Could not write the data file:\n%1": "无法写入数据文件：\n%1",
    "Regenerated the data file from labels: %1": "已根据标注重新生成数据文件：%1",
    "Preset weights...": "预置权重…",
    # --- training config tab ---------------------------------------------
    "AMP has no effect on CPU, so it stays off while the device is CPU.": (
        "AMP 在 CPU 上不起作用，所以设备为 CPU 时保持关闭。"
    ),
    "Mixed precision: faster on CUDA, no effect on CPU.": (
        "混合精度：在 CUDA 上更快，在 CPU 上没有效果。"
    ),
    "CPU training is much slower than GPU.": "CPU 训练比 GPU 慢很多。",
    "Default values were replaced with a CPU-friendly preset (%1); adjust them in Train Settings if needed.": (  # noqa: E501
        "默认值已替换为适合 CPU 的预设（%1）；需要时可在训练设置里调整。"
    ),
    "Project:": "项目：",
    "Folder name for this run, inside the Project folder. One folder name only - no path separators.": (  # noqa: E501
        "本次训练在项目目录下的文件夹名。只能是一个文件夹名，不能带路径分隔符。"
    ),
    "Name:": "名称：",
    "e.g. yolov8n.pt (downloaded when training starts)": (
        "例如 yolov8n.pt（训练开始时下载）"
    ),
    "Pick a common pretrained checkpoint": "选择一个常用的预训练权重",
    "Model:": "模型：",
    "Only the class list matters here; the dataset itself is rebuilt on every run.": (  # noqa: E501
        "这里只用到类别列表；数据集本身每次训练都会重建。"
    ),
    "From Labels": "来自标注",
    "Regenerate the class-list yaml from the open folder's labels": (
        "根据当前打开文件夹的标注重新生成类别列表 yaml"
    ),
    "Data:": "数据：",
    "Pose Config:": "姿态配置：",
    "Device:": "设备：",
    "Dataset Ratio:": "数据划分比例：",
    "Smart Recommend": "智能推荐",
    "Open an image folder in the labeling view first, then click Smart Recommend.": (  # noqa: E501
        "请先在标注界面打开一个图片文件夹，再点智能推荐。"
    ),
    "Smart recommendation applied": "已应用智能推荐",
    "Filled in: %1\n\n%2": "已填入：%1\n\n%2",
    "Applied the %1 preset: %2": "已应用 %1 预设：%2",
    "Presets:": "预设：",
    "Quick check": "快速验证",
    "Standard": "标准",
    "High quality": "高质量",
    "Sets epochs, image size, patience, close-mosaic and cosine LR for this tier": (
        "为该档位设置轮数、图像尺寸、耐心值、关闭 mosaic 与余弦学习率"
    ),
    "Epochs:": "轮数：",
    "Number of training epochs. On CPU, start small to check the pipeline before a long run.": (  # noqa: E501
        "训练轮数。在 CPU 上建议先设小一点，确认流程没问题再跑长训练。"
    ),
    "Batch:": "批大小：",
    "Images per batch. -1 picks the batch automatically (GPU only; on CPU it falls back to 16). Lower it if training runs out of memory.": (  # noqa: E501
        "每批图片数。-1 表示自动选择（仅 GPU；CPU 上回退为 16）。显存或内存不足时调小。"
    ),
    "Image Size:": "图像尺寸：",
    "Training image size. Smaller trains faster: 640 is the default, 416 a common CPU choice.": (  # noqa: E501
        "训练图像尺寸。更小训练更快：默认 640，CPU 上常用 416。"
    ),
    "Workers:": "工作进程：",
    "Data-loader worker processes. Ultralytics forces 0 on CPU; 0-2 is the safest range on Windows.": (  # noqa: E501
        "数据加载进程数。CPU 上 ultralytics 会强制为 0；Windows 上 0-2 最稳。"
    ),
    "Classes:": "类别：",
    "Single Class": "单类别",
    "Training Strategy": "训练策略",
    "Time (h):": "时长（小时）：",
    "Wall-clock limit in hours; training stops when it is reached (None = no limit).": (  # noqa: E501
        "按小时计的运行时长上限，达到即停止训练（None = 不限制）。"
    ),
    "Patience:": "耐心值：",
    "Stop early after this many epochs without an improvement. Lower it to fail fast while experimenting.": (  # noqa: E501
        "连续这么多轮没有提升就提前停止。试验阶段调小可以更快看到结果。"
    ),
    "Close Mosaic:": "关闭 Mosaic：",
    "Disable mosaic augmentation for the last N epochs so the model finishes on clean images (0 keeps it on).": (  # noqa: E501
        "最后 N 轮关闭 mosaic 增强，让模型在干净图片上收尾（0 表示一直开启）。"
    ),
    "Optimizer:": "优化器：",
    "Weight-update algorithm. 'auto' picks one from the model and dataset size; SGD and AdamW are the usual manual choices.": (  # noqa: E501
        "权重更新算法。'auto' 会根据模型和数据集规模自动选择；手动常用 SGD 和 AdamW。"
    ),
    "Cosine LR": "余弦学习率",
    "Cosine learning-rate schedule: the rate decays smoothly to its final value instead of dropping linearly.": (  # noqa: E501
        "余弦学习率调度：学习率平滑衰减到终值，而不是线性下降。"
    ),
    "AMP": "AMP",
    "Multi Scale": "多尺度",
    "Randomly rescales inputs during training. Costs CPU time with little benefit there.": (  # noqa: E501
        "训练时随机缩放输入。在 CPU 上只增加耗时，收益很小。"
    ),
    "Learning Rate": "学习率",
    "LR0:": "初始学习率：",
    "Initial learning rate. Lower it if the loss explodes; raise it if learning stalls.": (  # noqa: E501
        "初始学习率。损失爆炸就调小；学习停滞就调大。"
    ),
    "LRF:": "最终学习率系数：",
    "Final learning rate as a fraction of LR0 (0.01 = 1%): the rate travels from LR0 down to this.": (  # noqa: E501
        "最终学习率相对初始学习率的比例（0.01 = 1%）：学习率从初值降到这个值。"
    ),
    "Momentum:": "动量：",
    "Momentum for SGD (beta1 for the Adam family); it smooths how much the previous step steers the next one.": (  # noqa: E501
        "SGD 的动量（Adam 系为 beta1）；它决定了上一步对下一步的影响有多平滑。"
    ),
    "Weight Decay:": "权重衰减：",
    "Penalty on large weights: higher fights overfitting, too high underfits.": (
        "对大权重的惩罚：调大可以抑制过拟合，过大则欠拟合。"
    ),
    "Warmup Parameters": "预热参数",
    "Warmup Epochs:": "预热轮数：",
    "Epochs spent ramping the learning rate up from zero: a stabiliser at the start, but they count toward the total.": (  # noqa: E501
        "学习率从零升到目标值所用的轮数：能让训练起步更稳，但会算进总轮数。"
    ),
    "Warmup Momentum:": "预热动量：",
    "Momentum at the start of warmup; it ramps up to the main value.": (
        "预热开始时的动量，随后逐渐升到主值。"
    ),
    "Warmup Bias LR:": "预热偏置学习率：",
    "Learning rate for bias terms during warmup, usually higher than LR0 so they can move early.": (  # noqa: E501
        "预热期间偏置项的学习率，通常高于初始学习率，让偏置能更早调整。"
    ),
    "Augmentation Settings": "增强设置",
    "HSV Hue:": "HSV 色相：",
    "Random hue shift as a fraction of the colour wheel. Keep small; 0 disables.": (
        "随机色相偏移，按色环比例计。建议保持很小，0 表示关闭。"
    ),
    "HSV Saturation:": "HSV 饱和度：",
    "Random saturation shift; useful when lighting varies across the images.": (
        "随机饱和度偏移；图片之间光照差异大时有用。"
    ),
    "HSV Value:": "HSV 明度：",
    "Random brightness shift; useful when exposure varies across the images.": (
        "随机明度偏移；图片之间曝光差异大时有用。"
    ),
    "Rotation Degrees:": "旋转角度：",
    "Random rotation range in degrees. Use it only if the objects really appear rotated.": (  # noqa: E501
        "随机旋转的角度范围。只有当目标真的会以不同角度出现时才用。"
    ),
    "Translate:": "平移：",
    "Random translation as a fraction of the image size.": (
        "随机平移，按图像尺寸的比例计。"
    ),
    "Scale:": "缩放：",
    "Random zoom range (0.5 means +/-50%): teaches size robustness.": (
        "随机缩放范围（0.5 表示 ±50%）：让模型对目标大小更鲁棒。"
    ),
    "Shear:": "错切：",
    "Random shear in degrees; rarely needed.": "随机错切的角度，很少需要。",
    "Perspective:": "透视：",
    "Random perspective warp as a fraction (very small values); helps with tilted viewpoints.": (  # noqa: E501
        "随机透视变换的比例（取值很小）；对倾斜视角有帮助。"
    ),
    "Regularization": "正则化",
    "Dropout:": "Dropout：",
    "Dropout for classification heads only; it does nothing for detect/segment/pose.": (
        "只对分类头生效的 Dropout；对检测/分割/姿态没有任何作用。"
    ),
    "Fraction:": "采样比例：",
    "Fraction of the training set used per run (1.0 = all). Lower it for quick experiments.": (  # noqa: E501
        "每次训练使用训练集的比例（1.0 = 全部）。快速试验时可以调小。"
    ),
    "Rectangular": "矩形训练",
    "Rectangular training batches: less padding and faster, but validation loses the batch-shape consistency.": (  # noqa: E501
        "矩形训练批次：填充更少、更快，但验证阶段会失去批内形状一致性。"
    ),
    "Loss Weights": "损失权重",
    "Box:": "框：",
    "Weight of the box-position loss: raise it when the boxes are loose around the objects.": (  # noqa: E501
        "框位置损失的权重：框在目标周围偏松时调大。"
    ),
    "Cls:": "分类：",
    "Weight of the classification loss: raise it when classes are being confused.": (
        "分类损失的权重：类别容易混淆时调大。"
    ),
    "DFL:": "DFL：",
    "Weight of the distribution-focal loss: how sharply box edges are localised.": (
        "分布焦点损失的权重：决定框边缘定位的锐利程度。"
    ),
    "Pose:": "姿态：",
    "Weight of the keypoint loss; pose tasks only.": (
        "关键点损失的权重；仅姿态任务使用。"
    ),
    "Kobj:": "Kobj：",
    "Weight of the keypoint-objectness loss; pose tasks only.": (
        "关键点存在性损失的权重；仅姿态任务使用。"
    ),
    "Checkpoint and Validation": "检查点与验证",
    "Save Period:": "保存周期：",
    "Save a checkpoint every N epochs (Disabled = only the final one).": (
        "每 N 轮保存一个检查点（禁用 = 只保存最后一个）。"
    ),
    "Validation": "验证",
    "Validate after every epoch. Turning it off is faster but leaves no mAP curve and no best.pt to export.": (  # noqa: E501
        "每轮结束后都做验证。关掉更快，但不会产生 mAP 曲线，也没有可导出的 best.pt。"
    ),
    "Plots": "绘图",
    "Write the training plots (curves, confusion matrix) into the run directory.": (
        "把训练图表（曲线、混淆矩阵）写入运行目录。"
    ),
    "Save checkpoints while training runs.": "训练过程中保存检查点。",
    "Resume": "继续训练",
    "Continue an interrupted run from its last checkpoint; a stopped run also offers this in the directory dialog.": (  # noqa: E501
        "从最后一个检查点继续被中断的训练；训练停止时目录对话框里也会提供这个选项。"
    ),
    "Cache": "缓存",
    "Keep the dataset in RAM: faster epochs when the images fit in memory.": (
        "把数据集放在内存里：图片能装下时每轮更快。"
    ),
    "Leave images with no shapes out of training; otherwise they act as background (negative) samples.": (  # noqa: E501
        "不把没有标注的图片放进训练；否则它们会作为背景（负）样本参与。"
    ),
    "Only Checked Files": "只用已确认的文件",
    "Train only on images marked as confirmed in the label list.": (
        "只用文件列表里标记为已确认的图片训练。"
    ),
    "Auto-fill epochs/batch/imgsz from the current labeled folder and past iterations": (  # noqa: E501
        "根据当前已标注文件夹和过往迭代自动填入轮数/批大小/图像尺寸"
    ),
    "(cannot read directory contents)": "（无法读取目录内容）",
    "Contains trained weights weights/": "包含训练好的权重 weights/",
    "Only an empty weights/ directory": "只有一个空的 weights/ 目录",
    "Contains previous training args args.yaml": "包含上次训练的配置 args.yaml",
    "and %d other files/subdirectories": "以及 %d 个其它文件/子目录",
    "The directory is empty; deleting it loses nothing.": (
        "目录是空的，删除不会丢东西。"
    ),
    " Deletion cannot be undone.": " 删除后无法恢复。",
    "Training Directory Exists": "训练目录已存在",
    "A training run already lives in this directory:": "这个目录里已经有一次训练：",
    "Checkpoint: epoch %1 of %2 completed.": "检查点：已完成第 %1 / %2 轮。",
    "A resumable checkpoint was found.": "找到了可继续训练的检查点。",
    "A trained model (weights/best.pt) exists here.": (
        "这里有训练好的模型（weights/best.pt）。"
    ),
    "Choose an action:": "请选择处理方式：",
    "Resume Training": "继续训练",
    "Use Existing Model": "使用已有模型",
    "Retrain (overwrite)": "重新训练（覆盖）",
    "This directory is not inside the Project folder, so overwriting it is not offered.": (  # noqa: E501
        "这个目录不在项目文件夹内，因此不提供覆盖选项。"
    ),
    "This directory holds no training output (no weights/, args.yaml or results.csv), so it is probably not a result folder. Nothing was deleted - change the Name field or pick another Project.": (  # noqa: E501
        "这个目录里没有训练产物（没有 weights/、args.yaml 或 results.csv），"
        "看起来不是一个结果目录。没有删除任何东西 —— 请修改名称，或换一个项目。"
    ),
    "This will delete the existing project directory and restart training:\n{path}\n\n{detail}\nOverwrite it? To keep it, choose No and change the Name field.": (  # noqa: E501
        "这会删除已有的项目目录并重新开始训练：\n{path}\n\n{detail}\n"
        "要覆盖吗？想保留就选「否」，然后修改名称。"
    ),
    "Could not delete the directory; training was cancelled.\n{path}\nReason: {error}\n\nIf the directory is held by Explorer or another program, close it and retry.": (  # noqa: E501
        "无法删除该目录，训练已取消。\n{path}\n原因：{error}\n\n"
        "如果目录被资源管理器或其它程序占用，请先关闭再重试。"
    ),
    "%1\n\nDirectory:\n%2": "%1\n\n目录：\n%2",
    "Continuing from checkpoint: %1": "从检查点继续：%1",
    "Resume keeps the checkpoint's own epochs/batch/imgsz; the other Config values are ignored.": (  # noqa: E501
        "继续训练会沿用检查点自己的轮数/批大小/图像尺寸，配置页的其它值会被忽略。"
    ),
    "Cannot Resume": "无法继续训练",
    "No resumable checkpoint (weights/last.pt) was found for this run.": (
        "这次训练没有找到可继续的检查点（weights/last.pt）。"
    ),
    "Training; waiting for the first epoch metrics…": (
        "正在训练；等待第一轮的指标…"
    ),
    "Less than a minute left": "剩余不到一分钟",
    "About %1 min left": "约剩 %1 分钟",
    "Click to page through the images": "点击可翻看这些图片",
    "Training left dataset copies taking %1 across %2 old directories.": (
        "训练留下了占用 %1 的数据集副本，分布在 %2 个旧目录里。"
    ),
    "... and %1 more": "… 还有 %1 项",
    "Delete the old copies beyond this run? The most recent %1 are kept.": (
        "删除本次之外旧的副本吗？最近的 %1 个会保留。"
    ),
    "Clean up old dataset copies": "清理旧的数据集副本",
    "Cleaned %1 dataset copies, freeing %2 MB.": (
        "已清理 %1 个数据集副本，释放 %2 MB。"
    ),
    "%1 directories could not be deleted (possibly in use).": (
        "有 %1 个目录无法删除（可能正在被占用）。"
    ),
    "Applied a quick fix before retrying: %1": "重试前已自动修正：%1",
    "Halve Batch & Retry": "批大小减半并重试",
    "Set Workers to 0 & Retry": "工作进程设为 0 并重试",
    "Switch to CPU & Retry": "切换到 CPU 并重试",
    "Could not open this directory:\n%1": "无法打开该目录：\n%1",
    "%1 label file(s) could not be read; they are NOT in the dataset.": (
        "有 %1 个标注文件无法读取，它们不会被放进数据集。"
    ),
    "%1 label file(s) failed to convert; they are NOT in the dataset.": (
        "有 %1 个标注文件转换失败，它们不会被放进数据集。"
    ),
    "%1 shape(s) were dropped by the converter (not representable in this task).": (  # noqa: E501
        "转换器丢弃了 %1 个标注（这种形状无法表示在当前任务里）。"
    ),
    "%1 label file(s) exist but could not be read, so they were left out of the dataset:": (  # noqa: E501
        "有 %1 个标注文件存在但读不出来，已排除在数据集之外："
    ),
    "%1 label file(s) could not be converted, so they were left out of the dataset:": (  # noqa: E501
        "有 %1 个标注文件转换失败，已排除在数据集之外："
    ),
    "They are not negative samples: nothing in them reaches the model. The full list is in the dataset's manifest.json and dataset_info.txt.": (  # noqa: E501
        "它们不是负样本：里面的内容根本不会进入模型。完整清单在数据集的 "
        "manifest.json 和 dataset_info.txt 里。"
    ),
    "Dataset Incomplete": "数据集不完整",
    "Train Anyway": "仍然训练",
    "Training cancelled: fix the listed label files first.": (
        "训练已取消：请先修好列出的标注文件。"
    ),
    "Continue this run from weights/last.pt": "从 weights/last.pt 继续这次训练",
    "Use for Auto-labeling": "用于自动标注",
    "Export ONNX and load it into the auto-labeling panel": (
        "导出 ONNX 并加载到自动标注面板"
    ),
    "Failed to export ONNX; not loaded into auto-labeling.\n%1": (
        "ONNX 导出失败，未加载到自动标注。\n%1"
    ),
    "Not supported yet": "暂不支持",
    "No auto-labeling type for this task yet; export the weights and load the model manually. Supported: detect / segment / pose / classify (ONNX).": (  # noqa: E501
        "这个任务还没有对应的自动标注类型；请自行导出权重并手动加载模型。"
        "已支持：检测 / 分割 / 姿态 / 分类（ONNX）。"
    ),
    "The existing ONNX export is older than best.pt; exporting again.": (
        "已有的 ONNX 导出比 best.pt 旧，正在重新导出。"
    ),
    "Auto-labeling export cancelled: dependencies missing.": (
        "自动标注导出已取消：缺少依赖。"
    ),
    "Exporting ONNX for auto-labeling...": "正在为自动标注导出 ONNX…",
    "Missing Export Dependencies": "缺少导出依赖",
    "Exporting to %1 needs these packages:\n%2\n\nInstall them now with pip?\n%3\n\nChoosing No cancels the export. Nothing is installed without asking.": (  # noqa: E501
        "导出为 %1 需要这些包：\n%2\n\n现在用 pip 安装吗？\n%3\n\n"
        "选择「否」会取消导出。未经询问不会安装任何东西。"
    ),
    "Missing pose config": "缺少姿态配置",
    "Pose feedback needs the same pose config used for training (classes: class name -> keypoint name list). Fill in Pose Config on the Data tab and retry.": (  # noqa: E501
        "姿态回填需要与训练时相同的姿态配置（classes：类别名 → 关键点名列表）。"
        "请在数据页填好姿态配置后重试。"
    ),
    "Missing classes": "缺少类别",
    "Could not read class names from the labels; check the data config and retry.": (
        "无法从标注中读出类别名；请检查数据配置后重试。"
    ),
    "Training weights · %1": "训练权重 · %1",
    "Current iteration suggestion: %1": "当前迭代建议：%1",
}


def main():
    tree = ET.parse(TS)
    root = tree.getroot()
    filled = missing = already = 0
    unknown = []
    for context in root.findall("context"):
        for message in context.findall("message"):
            source = message.findtext("source") or ""
            node = message.find("translation")
            if node is None:
                continue
            if (node.text or "").strip():
                already += 1
                continue
            if source in TRANSLATIONS:
                node.text = TRANSLATIONS[source]
                node.attrib.pop("type", None)
                filled += 1
            elif any("\u4e00" <= c <= "\u9fff" for c in source):
                # A Chinese source translates to itself; the catalogue
                # asks for a non-empty slot, and Qt falls back to the
                # source anyway.
                node.text = source
                node.attrib.pop("type", None)
                filled += 1
            else:
                missing += 1
                unknown.append(source)
    tree.write(TS, encoding="utf-8", xml_declaration=True)
    print(
        f"filled {filled}, already translated {already}, still empty {missing}"
    )
    for source in unknown[:20]:
        print("  STILL EMPTY:", repr(source[:60]))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
