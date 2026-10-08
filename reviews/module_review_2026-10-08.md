# 模块审查报告 · 2026-10-08

> 角度：**工程 / 架构视角**，与 `annotation_review_*`（使用者视角）、`training_review_*` 互补。
> 本次不重复已闭环的项，只报"仍然不合理"的。

## 一句话摘要

**分类推理（YOLOv8Cls）的入参契约从根上是错的，这条链路 100% 不可用；同时 181 处写在模块级函数里的 `self.tr` 让导出/上传的弹窗在中文构建里长期回落到英文。** 两处都是静默失效——不报错、不崩溃。前七批修的全是"会毁数据的"，这一批暴露的是"**根本跑不起来却没人知道**"。

## 0. 审查前提（重要）

- **审查对象是工作区，不是 HEAD**：`git status` 显示 **55 个文件改动、+13092 / −7722 行**未提交（含 `smart_tools_menu.py`、`image_preview_dialog.py`、`platform_open.py` 三个新文件未跟踪）。任何"当前程序"的结论都建立在这份未落盘的状态上。
- 方法：5 路并行模块审查 + 逐条 `file:line` 复核。**下文标 ✅ 的是本次亲手验证过的**（含跑脚本 / 读码 / AST 统计）；标「待复核」的是审查提出但我没验到最后一环的线索，未写进结论。
- 本报告不含"建议加测试/补文档"这类无证据条目。

---

## 1. 入口层（`app.py` / `views/mainwindow.py`）

| | 问题 |
|---|---|
| 🟡 ✅ | **窗口几何有两套真相源，互相覆盖**。`app.py:84,86,97,98` 读写 `window/geometry` + `window/maximized`；`views/mainwindow.py:83-89,95-108` 读写 `window/size` / `position` / `state`。两者**同一个** `QSettings("anylabeling","anylabeling")`，启动时都执行恢复（`app.py:601` 与 `mainwindow.py:76`），关闭时都写。→ 建议：只保留一套（`saveState/restoreState` 那套更完整，还能存 dock 布局）。 |
| 🟡 ✅ | **WSL 特判不对称**。`mainwindow.py:63-67,82-85,93-94` 在 WSL 下会 `remove("window/size|position|state")` 并跳过恢复；但 `app.py:84-91` 的 `window/geometry` 路径**没有**这个判断，WSL 下仍按几何还原 → 特判形同虚设。 |
| 🔵 | `views/common/converter.py:751` `output_files` 赋值后未使用；同一变量在 `:541` 是用于计数的，此分支的成功提示（`:752-757`）偏偏漏了计数。 |
| 🔵 | `views/common/checks.py:7` 与 `converter.py:9` 的 `sys.path` 注入深度不一致（2 层 vs 4 层），且 editable 安装下两者都是死代码。 |
| 🔵 | `views/common/toaster.py:242` `font.setWeight(100)` —— Qt6 里 100 等价 `QFont.Weight.Thin`，提示文字用最细字重；全仓仅此一处 `setWeight`。 |

---

## 2. `views/labeling` 核心

### 🔴 ✅ 换文件夹不清类别面板 → 导出类别表被污染

证据链：
- `label_widget.py:4428-4429`：`_load_classes_from_folder` 在新文件夹**没有** `classes.txt` 时直接 `return []`，**面板原封不动**；
- 唯一调用点 `utils/file_lifecycle.py:531`，紧接着 `:534` 走 `project_settings.end_project_switch` → `project_settings.py:150-152`：`panel_is_empty = not _panel_label_names(widget)` / `if not panel_is_empty: return` —— 因为面板**非空**（还留着上一个文件夹的类别），兜底**永远不触发**；
- `label_widget.py:3025-3036` `_yolo_class_names()`：类名 = 面板 UserRole 列表 `merge_class_names` 全局 config —— **正是从这里取类别做 YOLO id 映射**。

结论：从「带 classes.txt 的 A」切到「不带 classes.txt 的 B」，B 的导出类别表里混着 A 的类别，**id 映射整体错位 → 训练标签全错**，且全程无提示。
`4426` 行的 docstring 写的是"folders without one are left alone, so labels from the config keep working as before"——设计意图是"沿用 config"，实现出来却是"沿用上一个文件夹的面板"，两者并不等价。

> 建议：项目切换时显式清面板，再按 **classes.txt > 项目记录 > 全局 config** 的固定优先级重建。

### 🔴 ✅ 契约测试的模块清单被硬编码，新增抽取不受保护

`label_widget_contract.py:22` 的 `EXTRACTED_MODULES` 写死 5 个模块（`file_lifecycle` / `file_navigation` / `file_list_ops` / `label_editing` / `panel_visibility`），只对这五个做 `widget.X` ↔ `CONTRACT_MEMBERS` 双向比对。但同样是 widget-first 写法的 `utils/export.py`(3 处)、`utils/output_dir.py`(2)、`utils/qt.py`(1)、`utils/shortcuts_help.py`(1)、`widgets/attributes_controller.py`(3)、`filelist/items.py`(5) **都不在扫描范围**——它们新摸一个 `widget.X` 不会让测试变红。

> 建议：改为 AST 自动发现（凡首参名为 `widget` 的模块级函数即纳入），别用常量列表。

### 🟡 其余

| | 问题 |
|---|---|
| 🟡 ✅ | **`label_converter.py:994` 的 YOLO txt 是非原子写**：`with open(output_file,"w")` 边算边写（对照组 `label_file.py:216-228` 用的是 `mkstemp` + `safe_replace`）。中途异常会在导出目录留下**半截 `.txt`**，训练时被当成"少目标"的样本。建议：写临时文件再 `os.replace`。 |
| 🟡 | **"类别"有三份存储，无单一数据源**：`unique_label_list`(QListWidget)、`label_info`(dict)、`_config["labels"]`(全局 rc)。`add_label`(`:2776`) 只写前两者，`_load_classes_from_folder`(`:4434`) 只写面板不补 `label_info`，`label_editing.py:440` 又反向写 config —— 靠约定同步。 |
| 🟡 | **`label_widget.py:3929-3946`** `_refresh_label_panel` 用裸 `except Exception` 只打 warning：整个标签面板刷新（计数 / tooltip / 搜索过滤）任一异常即整体静默跳过，UI 保留过期计数。 |
| 🟡 | **`label_widget.py:3584-3589` 异常类型写错且是死代码**：`self.fn_to_index` 是普通 dict(`:311`)，`except ValueError` 抓不到 `KeyError`；同样的取值在 `file_lifecycle.py:148` 用的是正确的前置 `if str(f) in widget.fn_to_index`。且 `get_next_files` / `inform_next_files` 的连线已在 `:6655-6658` 被注释掉。 |
| 🔵 | **`label_widget.py:1735-1810`** `union_selection` 76 行 numpy/cv2 掩膜几何留在 God Object 里，与 `utils/shape.py:409 masks_to_bboxes / polygons_to_mask` 重复；`1748` 复用循环残留变量 `union_shape`，选中为空时 `NameError`。 |
| 🔵 | **`label_widget.py:3025`** `_yolo_class_names` / `_write_yolo_sidecar` 属导出职责却长在 widget 上。 |

---

## 3. `views/labeling/widgets`

### 🔴 ✅ mixin 里的 `self.tr` 与实际运行上下文不匹配

`canvas_rotation.py:184`：`self.tr("Click & drag to rotate shape '%s'")` 写在 `class CanvasRotationMixin` 里，pylupdate 把字符串归入上下文 `CanvasRotationMixin`（`zh_CN.ts:446-451` **已有正确中文**）；但运行期 `self` 是 `Canvas` 实例，Qt 用**最派生类名**取上下文 → 查 `Canvas`，永远命中不了 → **中文构建里回落到英文**。

这与第 4 节那条"模块级 `self.tr`"是**同一个 bug 的两种形态**。修法：mixin 内改用 `QCoreApplication.translate("Canvas", ...)`，或把字符串放回 `Canvas`。

### 🟡

| | 问题 |
|---|---|
| 🟡 ✅ | **`canvas.py`（3760 行）依旧是头号 God Object**，且 4 个 mixin 是"**纯方法桶**"——`canvas_brush.py:5-7`、`canvas_rotation.py:5-7` 的 docstring 自己承认"state still lives in `Canvas.__init__`"。方法搬走了、状态全留在宿主 → 类没瘦，反而多了 4 个隐式契约。（`__init__` 单函数铺了约 200 个属性，`:62` 已挂 `pylint: disable=too-many-instance-attributes`。） |
| 🟡 | **鼠标高频路径用同步 `self.repaint()` 而非 `update()`**：`canvas.py:842`（同型 `:791/836/945/1596/1700/1736/3419/3431`，`canvas_rotation.py:245`）每次 `mouseMoveEvent` 强制立即重绘；叠加 `paintEvent` → `_paint_masks`(`:2473`) 对每个形状**现建 `QPainterPath` 并画两遍**（`:2524/2539`）→ 大标注集必卡。 |
| 🟡 | **`label_list_widget.py:20-25`** 每次 `paint()` 与 `sizeHint()` 都新建 `QTextDocument` 并解析 HTML，无缓存；`sizeHint` 由 QListView 对每个可见行反复触发。 |
| 🟡 | **`canvas.py:3117`** `render_visualization` 造临时 `Canvas` 时只带 `parent`，手工补了 `show_*` / `mask_opacity` / `attr_*` 颜色（`:3136-3142`），漏了 `shape_opacity`(`:250`) 与 rotation/cuboid/brush 配置 → 导出图与屏幕所见不一致。 |
| 🔵 | **`canvas.py:124`** `self.parent = kwargs.pop("parent")` 既遮蔽 `QObject.parent()`，又让基类收不到 parent。同型遮蔽见 `label_dialog.py:86,354,726,769`、`overview_dialog.py:89`、`shape_dialog.py:36`、`auto_labeling.py:143`。 |
| 🔵 | **两套并行 undo**：`_brush_undo_stack`(`canvas_brush.py:316`) + `shape_history`(`ShapeHistoryStore`)，另有 `_brush_baseline_mask` 第三种基线 —— clear 时机各自为政。 |
| 🔵 ✅ | `canvas.py:2697,2726,2772` 在逐形状循环内构造 `QFontMetrics`；`auto_labeling.py:788-789` 事件里 `except Exception: pass` 无日志（全仓同类只此一处无 log）。 |

---

## 4. `views/labeling` 的 `utils` / `settings` / `filelist`

### 🔴 ✅ 181 处 `self.tr` 写在模块级函数里 → 翻译被静默丢弃

AST 实测（`anylabeling/views/labeling/**` 下 module-level `FunctionDef` 内的 `self.tr` 调用）：

```
181 处，分布：
  62  utils/export.py
  52  utils/upload.py
  35  utils/visualization.py
  15  utils/crop.py
   9  utils/batch.py
   8  utils/shape.py
```

这些函数是 `def export_yolo_annotation(self, mode)` 形态的**模块级函数**，被 `label_widget.py:5983` 以 `utils.export_yolo_annotation(widget, "hbb")` 的方式调用（首参即 widget）。lupdate **无法为模块级函数定上下文** → 整条字符串被丢弃，中文构建里这些导出/上传/裁剪弹窗一直是英文。

同一问题在 `utils/output_dir.py`、`utils/async_exif.py:103`、`widgets/attributes_controller.py:67,452` **已经改成显式 `QCoreApplication.translate("LabelingWidget", ...)`** —— 修了一半，留下 181 处旧写法。

> 建议：统一按 `output_dir.py` 的写法批量改，把 `"LabelingWidget"` 定为唯一约定。

### 🔴 ✅ 设置页字段差集 32 个，`EXCLUDED_KEYS` 是宣言不是机制

实跑比对（模板 `jllabeling_config.yaml` 224 个叶子 vs `schema.SETTINGS_KEYS` 165 vs `EXCLUDED_KEYS` 28）：

```
差集 32 个：
  auto_labeling.more_panel_expanded
  canvas.attributes.{background,border,text}_color
  canvas.brush.{max_undo_steps,max_undo_memory_mb}
  description_dock.{closable,floatable,movable,show}
  file_dock.{closable,floatable,movable}
  flag_dock.{closable,floatable,movable}
  label_dock.{closable,floatable,movable}
  shape_dock.{closable,floatable,movable}
  device / file_search / show_attributes / startup_show_project_manager
  sidebar.{collapsed,lists,width} / tools_panel.{collapsed,position}
  training.ultralytics.project_readonly
```

`EXCLUDED_KEYS` 在生产代码里**只有 `app.py:542` 一条注释引用，没有任何消费方**——它拦不住任何东西。更实：`settings/runtime_applier.py:340-347` 为 `device` / `file_search` / `project_readonly` 写了运行时分支，但 `controller.py` 只按 `SETTING_FIELDS` 发射键，**这三个分支永不触发**。`test_schema.py` 只断言 `EXCLUDED_KEYS ∩ SETTINGS_KEYS == ∅`，没有一条断言"模板叶子键 == SETTINGS_KEYS ∪ EXCLUDED_KEYS"。

> 建议：schema 改为由模板 yaml 差集派生 + 加"差集为空"的断言测试；UI 状态键（dock 特征 / sidebar / tools_panel）补进 `EXCLUDED_KEYS`；删掉 runtime_applier 三个死分支。

### 🟡

| | 问题 |
|---|---|
| 🟡 ✅ | **`utils/smart_tools.py` 2234 行是第二个 God Object**，约 40 个顶层定义混了 12+ 职责（阈值校准 / 数据分析 / 缺框扫描 / **标注备份引擎** / 陈旧框删除 / 迭代看板 / 复核跳转 / 重复归档 / 训练建议 / 模板预标注），还自带 `_ResultDialog` / `_SmartTaskThread` / `_MissingScanThread` 一套 UI+线程。且 `utils/session_snapshot.py:36` **反向依赖**它的 `backup_label_files`。→ 拆：`label_backup.py`（备份引擎，session_snapshot 依赖它）/ `smart_actions.py` / `smart_ui.py`。 |
| 🟡 | **`ai/config.py:7-16` 与 `widgets/searchable_model_dropdown.py:29` 是同一函数的两份实现**，且路径已经漂移（`ai/models.json` vs `models.json`）；`searchable_model_dropdown.py:18` 的 `from ...ai.config import *` 把差异藏了起来。 |
| 🟡 ✅ | **`filelist/quality.py:89-90`（同型 `:153-154`）异常吞噬**：读标签 JSON 失败时 `except Exception: has_low_conf = False` → 损坏的标注文件在文件列表里显示为"干净"；而 `data_audit` / `export_check` 对同一文件判 `corrupted`（`test_export_check` 已钉住该口径）。**同一份数据三套判定**。 |
| 🟡 | **`utils/__init__.py` 再导出层的死符号**（全仓含 tests 零消费）：`image.process_image_exif` / `check_img_exif` / `ensure_pillow_heif_registered` / `img_arr_to_b64` / `img_b64_to_arr` / `img_data_to_arr` / `img_data_to_png_data` / `img_pil_to_data`、`general.is_chinese`、`qt.new_button`、`shape.polygons_to_mask` / `shape_to_mask` / `shapes_to_label` / `masks_to_bboxes`、`upload_shape_attrs_file`。 |
| 🔵 | `settings/__init__.py:13-24` 的 `__all__` 除 `SettingsController` / `SettingsDialog` 外无消费方（各模块直接从 `.schema` 导入）；`SETTINGS_SHORTCUT_KEYS_CORE` 连生产代码都没有。 |
| 🔵 | `label_colormap()` 在 `label_widget.py:189` 与 `widgets/canvas.py:53` 各生成一份常量。 |

---

## 5. `views/training`

| | 问题 |
|---|---|
| 🟡 ✅ | **`ultralytics_dialog.py:2765-2777` 进度条仍用行数当轮数**：`epoch_rows = len(rows) - 1`。而 `utils.py:384-393` 已经因为"续训会把中断那一行写两遍"改成**读 `epoch` 列**，同一个刷新周期里进度条显示 `51/50`、metrics 标签（`:2831`，走 `parse_training_metrics`）显示 `50 epoch`、`run_meta.json` 记 50 —— 一次运行三个数。 |
| 🟡 ✅ | **`services/.../exporter.py:397-398` 与 `ultralytics_dialog.py:1047-1055` 的环境变量约定不一致**：导出收尾只在 `CUDA_VISIBLE_DEVICES == ""` 时删除，而 dialog 设的是 `"-1"` → 该分支是**死代码**，GPU 环境变量残留。 |
| 🟡 | **导出不可停**：`exporter.py:249-253` 的 `export_thread` 未设 daemon；`stop_export` 只 `join(5s)` 就报 `export_stopped`，而 `model.export()` 仍在写文件，同时 `is_exporting=False` 允许并发第二次导出。关窗若在导出中，进程被非 daemon 线程吊住。 |
| 🟡 ✅ | **`ultralytics_dialog.py` 4485 行、单类 113 个方法** —— 向导 / 子进程协议 / 结果解析 / run_meta / 导出 / 历史全焊在一起，是第二个 God Object（后端已抽到 `services/` 是对的，UI+编排+持久化没抽）。 |
| 🟡 | **`build_dnn_engine.py:4-18` 的 `DnnBaseModel` 只实现 `get_dnn_inference`，缺基类契约**：`yolo26_pose` 初始化会调 `self.net.get_metadata_info("kpt_shape")`（`__base__/yolo.py:155`）→ `AttributeError`；`yolo.py:220` 只对 det/seg/track 走 DNN，其余回落到不存在的 `get_ort_inference`。配 `engine: dnn` 对 pose/SAM **静默不可用**。 |
| 🔵 | `exporter.py:430-434` `export_model()` 无任何调用者，且调 `start_export` 不带 `allow_install`。 |
| 🔵 | `run_history_dialog.py:152` 打开运行目录用 `webbrowser.open`，而 `platform_open.py` 正是为统一该行为而建（`image_preview_dialog.py:145` 已用它）。 |

---

## 6. `services/auto_labeling`

### 🔴 ✅ 分类推理的入参类型从根上错了

```
yolov8_cls.py:20   class YOLOv8Cls(Model)        # ← 直接继承 Model，不是 YoloBaseModel
yolov8_cls.py:126  blob = self.preprocess(image) # ← 没有 QImage→ndarray 转换
yolov8_cls.py:78   rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
```

对照同目录其它模型，**转换这一步是基类做的**：
- `__base__/yolo.py:377` `image = qt_img_to_rgb_cv_img(image, image_path)` 后才 `self.preprocess(image)`；
- `yolov8_sam2.py:261`、`segment_anything_2.py:306,354` 也都显式转。

而调用方统一传的是 **QImage**：`model_manager.py:848-858` ← `batch.py:616/629` 的 `self.app.image`，`label_widget.py:750` 里 `self.image = QtGui.QImage()`。

→ `cv2.cvtColor(QImage, ...)` 抛 `Expected Ptr<cv::UMat> for argument 'src'`，被 `model_manager.py:880` 吞成一句 "Error in model prediction"。用户看到的是**永远失败且只说"出错了"**。训练侧 `utils.py:275` 把 `autolabel_type_for_task("Classify")` 映射到 `yolov8_cls` → **训练→自动标注闭环的终点是断的**。

> 建议：在 `YOLOv8Cls` 内用 `qt_img_to_rgb_cv_img(image, image_path)` 取图，与 YOLO 分支对齐。

### 🔴 ✅ `GenericWorker` 异常即线程僵死

`worker.py:13-16`：
```python
@pyqtSlot()
def run(self):
    self.func(*self.args, **self.kwargs)
    self.finished.emit()          # ← 只有正常返回才会 emit
```
无 try/finally。而 `model_manager.py:541`（`old_config["model"].unload()`）与 `:544`（`copy.deepcopy`）**落在按类型 try/except 之外** → 任一处抛异常，`finished` 不 emit → `on_model_download_thread_finished` 永不执行 → `is_model_download_running()` 恒为 `True`（`:516-526`）→ **本会话再也装不了任何模型**，且没有任何错误提示。

同型：`yolov8_sam2.py:325-335` 的 `preload_worker` 也无保护，`encode` 一失败预加载永久停摆。

### 🔴 ✅ 少一对括号，线程没停

`yolov8_sam2.py:316`：
```python
if self.pre_inference_thread:
    self.pre_inference_thread.quit      # ← 少了 ()
```
对照 `segment_anything_2.py:508` 写的是 `quit()`。（`:352` 那处无括号是 `connect()` 传函数对象，**是对的**，别一起改。）

且 `unload()` 只 `del self.net`（`:313`），**未释放 `self.model`**（`SegmentAnything2ONNX`，`:135`）→ 旧 SAM2 encoder/decoder 会话随预加载线程存活，切模型时不释放。

### 🟡

| | 问题 |
|---|---|
| 🟡 | `lru_cache` 无 `clear()` / `invalidate()`、不按字节计量，`cache_size` 只限条目数（`segment_anything_2.py:110`、`yolov8_sam2.py:147`）→ unload 时无从清空 embedding 缓存。**待复核**（我没读到最后一环）。 |

---

## 7. `services/auto_training`

| | 问题 |
|---|---|
| 🟡 ✅ | **`general.py:64-72` 的 `directory_size` 用 `os.path.getsize`（跟随符号链接）**，而数据集在非 Windows 下正是 `os.symlink` 建的（`:316`、`:375`）→ 统计的是**源图**体积，删软链几乎不释放字节。现在这个数被 `prune_datasets` 当 `reclaimed` 返回，还被 `ultralytics_dialog.py:2954` 原样展示成"将释放 X MB"，并决定是否超过 `MIN_CLEANUP_OFFER_BYTES` 触发弹框。Windows 走 `copy2`、其余走 `symlink`，**两平台体积口径完全不同**。这条在 2026-09-30 报告里列为"未修"，现在**仍然未修**，且影响面已经扩大。 |
| 🟡 | **`trainer.py:122-133` 停止路径可能留下孙进程**：先 `terminate()` + `wait(5)`，`kill_training_process_tree` 仅在 `TimeoutExpired` 才调用 → worker 快速死掉时，ultralytics `workers=8` 的 dataloader 子进程不会被 `/T` 清掉。且全仓无 atexit / Job Object，主程序硬退时子进程无父死联动。 |

---

## 8. 支撑工程层

### 🔴 ✅ lint 闸门在 baseline 丢失时静默放行

`scripts/check_flake8_baseline.py:96-99`：
```python
def load_baseline(path=BASELINE_PATH):
    counts = collections.Counter()
    if not os.path.isfile(path):
        return counts          # ← 空 Counter
```
缺文件后 `main` 只打印提示就 `return 0`（退出码 0 = 通过）。`.pre-commit-config.yaml` 与 CI 都以它为准 → **删掉 baseline 文件即永久通过 lint**。

> 建议：文件缺失时 `return 1`，重建只允许走 `--update`。

### 🟡

| | 问题 |
|---|---|
| 🟡 | **`scripts/compile_languages.py` 与 `generate_languages.py` 约 70 行整块重复**：`find_lrelease` / `compile_resources`（含嵌套 `normalize_imports` / `add_rcc_commands`）/ `existing_catalogs` / `TRANSLATIONS_DIR` 逐字相同。 |
| 🟡 | **`generate_languages.py:204` 的 `glob("**/*.ui", recursive=True)` 无视本文件的 `SKIP_DIRS` 策略**（`:12-22` 明确排除 `.venv` / `build`，但只对 `.py` 生效）→ 会命中依赖目录，并因 `:206-208` 的 `pyuic6 -o` 就地写出 `_ui.py` 到那些目录。 |
| 🟡 | **`views/common/device_manager.py:74-98` 两条设备解析路径契约不一致**：`_load_from_config` 直接读 `.xanylabelingrc`（绕过 `get_config`、`--config` 自定义路径与 `validate_config_item`），`set_device` 又跳过 `_validate_and_set`(`:42-50`) 的 GPU 可用性回退。 |
| 🟡 | **`tests/conftest.py` 未提供共享 `QApplication` fixture**，44 个测试文件各自 `QApplication.instance() or QApplication([])`；且 `tests/test_utils/test_window_placement.py:33` 直接读写**真实** `QSettings` 命名空间（`:35-48` 靠 setUpClass/tearDownClass 快照还原，中途失败即污染用户真实窗口设置；xdist 下同 namespace 竞态）。对照 `test_widget_wiring.py:490-515` 已用临时 ini。 |
| 🔵 | `tools/onnx_exporter/` 里 12+ 个导出器（grounding_dino / sam3 / scrfd / u_rtdetr / internimage / geco / dfine / deimv2 / rfdetr / yolow / yolov10 / pulc / recognize_anything）在本分叉的 `services/auto_labeling/` 与 `configs/auto_labeling/` 里**都没有对应的运行时服务**。 |
| 🔵 | `scripts/shortcut_press_list.py:305-313` 的 mismatch 分支 `return 1` 前不清理 `mkdtemp` 目录（`:312` 只在成功路径执行）。 |

---

## 9. 最该先动的 5 件事

| # | 事项 | 为什么排这个位置 |
|---|---|---|
| 1 | **修 `YOLOv8Cls` 入参契约**（`yolov8_cls.py:78/126`） | 唯一"功能 100% 不可用却只报'出错了'"的链路，且是训练→标注闭环终点 |
| 2 | **`GenericWorker` 改 try/finally + `model_manager.py:541/544` 移入 try** | 一次 unload 异常会静默锁死整个模型切换，需重启程序 |
| 3 | **补 `yolov8_sam2.py:316` 的 `()` + 释放 `self.model`** | 一行改动，止住线程与显存/内存泄漏 |
| 4 | **181 处模块级 `self.tr` 统一改为显式上下文** | 用户可见却完全静默；`output_dir.py` 已有现成写法可照抄 |
| 5 | **`label_widget.py:4418` 换文件夹清面板** | 唯一会**污染导出的类别 id** 的问题 |

紧随其后：schema 差集派生 + 差集断言（防止设置项继续静默丢失）、`check_flake8_baseline` 缺文件改 `return 1`。

---

## 10. 已达水准的部分（本次核过，别重报）

- **快捷键三层一致性未再漂移**：`pytest tests/test_settings/test_shortcut_bindings.py tests/test_utils/test_shortcuts_help.py` → **31 passed**。
- **`rmtree` 棘轮仍在**：`grep -rn "rmtree" anylabeling/views/labeling/` 只剩 `output_dir.py` 与 `smart_tools.py` 的备份清理。
- **导出侧的账已经补齐**：`custom_to_yolo` 的 `stats` 出参 + `export_check` 前置体检 + `export_manifest.json` + `data.yaml` 全在。
- **训练侧三道覆盖守卫仍在**：`is_single_path_component` / `is_inside_directory` / `looks_like_training_run`。
- **`parse_training_metrics` 已改读 `epoch` 列**（`utils.py:384-393`）—— 只是进度条那一处漏改。

---

## 11. 审查方法与复现命令

```bash
cd /g/LabelAndTrain/LabelAndTrain

# 1) 模块级函数里的 self.tr（本报告第 4 节的 181 处）
.venv/Scripts/python.exe - <<'PY'
import ast, pathlib
tot = 0; files = {}
for p in pathlib.Path('anylabeling/views/labeling').rglob('*.py'):
    try: tree = ast.parse(p.read_text(encoding='utf-8'))
    except SyntaxError: continue
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == 'tr'
                        and isinstance(sub.func.value, ast.Name)
                        and sub.func.value.id == 'self'):
                    tot += 1; files[str(p)] = files.get(str(p), 0) + 1
print(tot, sorted(files.items(), key=lambda x: -x[1]))
PY

# 2) 设置页字段差集（第 4 节 32 个键）
PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe - <<'PY'
import yaml
from anylabeling.views.labeling.settings import schema
cfg = yaml.safe_load(open('anylabeling/configs/jllabeling_config.yaml', encoding='utf-8'))
keys = set(schema.SETTINGS_KEYS); exc = set(getattr(schema, 'EXCLUDED_KEYS', []) or [])
def walk(n, p=""):
    o = []
    if isinstance(n, dict):
        for k, v in n.items():
            q = f"{p}.{k}" if p else k
            o += walk(v, q) if isinstance(v, dict) else [q]
    return o
leaves = walk(cfg)
miss = [l for l in leaves if l not in keys and l not in exc
        and not any(k.startswith(l + ".") for k in keys)]
print(len(leaves), len(keys), len(exc), len(miss)); print(*miss, sep="\n")
PY

# 3) 分类推理入参（第 6 节）
sed -n '20p;78p;126p' anylabeling/services/auto_labeling/yolov8_cls.py
sed -n '377p'        anylabeling/services/auto_labeling/__base__/yolo.py

# 4) 线程与括号（第 6 节）
sed -n '13,16p' anylabeling/services/auto_labeling/worker.py
grep -n "pre_inference_thread.quit" anylabeling/services/auto_labeling/*.py

# 5) lint 闸门（第 8 节）
sed -n '96,99p' scripts/check_flake8_baseline.py
```

> **本次未验证、因此未写成结论的**：GPU 路径、拖框手感、打包版行为、Linux/macOS 下 symlink 的实机表现（仅做了代码判定）、`lru_cache` 的释放链路。
