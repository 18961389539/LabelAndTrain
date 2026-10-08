# LabelAndTrain 训练模块审查（2026-09-30）

> **修复状态（2026-09-30 当天）**：三条 🔴 与 🟡 的 5 条（#4–#8）都已修完，只剩 🟡 最后一条（Linux 符号链接体积）
> 与 🔵 三条未动。回归网 `tests/test_auto_training/test_training_safety_guards.py`（57 条，含 3 条驱动真实对话框的接线测试）。
> 全量 **1020 passed / 1 skipped**，flake8 基线无回归，black 干净。**尚未提交**（工作区里有其它在途改动）。
> 下面正文保留发现当时的原样描述。
>
> 第二批（🟡）修的是：`validate_classes` 接线到 `start_training_from_train_tab`；停止训练也写 `run_meta.json`
> 并带 `status`（历史表新增「状态」列，`COLUMNS` 15 → 16）；`is_fresh_export` 让「用于自动标注」不再复用
> 早于 `best.pt` 的 ONNX；导出缺包改为**先问**（默认 No 即取消并给出命令）、超时 30s → 300s、冻结构建直接给指引、
> `allow_install` 默认关；清理提示列出目录名。
>
> 第三批（真机验证，`reviews/measurements_2026-09-30.md`）：本机 CPU 上真跑了三轮——3 轮完整训练、
> 50 轮跑到一半停、从 `last.pt` 续到跑满。三条核心断言成立（worker 协议 / `last.pt` 真可续训 / 续训写回同一目录
> 且不留 `exp-2`），并且**跑出一个单元测试抓不到的 🔴**：续训会把中断那一行重写一遍，
> `parse_training_metrics` 用行数当轮数 → 50 轮被记成 51 轮（正是 `run_meta.json` 与历史表的轮数来源）。已修 + 2 条回归测试。
> **GPU 路径、拖框手感、打包版仍未验证。**

> 审查对象：`anylabeling/services/auto_training/ultralytics/`（2540 行）+ `anylabeling/views/training/`（5428 行）
> 立场：一个要拿这个工具跑「标注 → 训练 → 看指标 → 再标一轮」的人。不问架构，只问三件事——
> **数据进去时有没有被悄悄改掉、跑完之后敢不敢信那个 mAP、出错时我知道该改什么吗。**

## 一句话摘要

**训练侧是三份数据里唯一没有"我丢了什么"这套账的**：导出侧 9-27/9-29 那两批已经把静默丢弃堵死了（`export_check.py` 甚至把"读不出的标签"列为必须拦下的不可逆丢失），而**数据集构建这条路对同一个问题给了两个相反的答案**——JSON 读不出就静默变成负样本（实测），JSON 合法但缺一个字段就整批中断（实测）；加上**覆盖确认框删的目录由自由文本的 Name 字段决定**（沙箱里实测删掉了另外两轮训练的权重和用户的标注目录），这三条是本轮的全部价值所在。

## 分维度评分表

| 维度 | 评分 | 一句话判据 |
|---|---|---|
| 日常操作效率 | 🟢 良 | 表单预填、一键开跑、CPU 自适应、预设三档、ETA、失败一键补救——这一层已经很顺 |
| 数据安全 | 🔴 差 | 覆盖确认框的删除目标 = `join(project, name)`，`name` 无任何校验；沙箱实测可删掉标注目录 |
| 训练产出可信度 | 🔴 差 | 读不出的标签静默变成负样本 → 模型被教"这图里没东西"；重建数据集时不报告丢了几个框 |
| 可复现性 | 🟢 优 | manifest（seed + 每张图的 label sha1）+ run_meta（权重 sha1 + train_args + metrics），链路是通的 |
| 可发现性与出错指引 | 🟢 良 | 1 个例外：`validate_classes` 写好了但没接线（超范围类别静默通过） |
| 与文档一致性 | 🟡 中 | 文档讲清了 loop 和可复现性；但没写"训练会静默丢负样本"这类真实行为 |

## 🔴 高

### 1. 一份读不出的标签文件，静默变成"负样本"，和导出侧的判定完全相反

证据链：

- `services/auto_training/ultralytics/general.py:342` — `except Exception:` 兜住 `json.loads` 失败，`background_images.append(image_file)`（只有 `only_checked_files` 为真时才 `continue`）
- `general.py:365` — `background_images` 全部塞进 **train**
- `general.py:195` — `converter.custom_to_yolo(...)` 对 `label_file=None` 的图不写 `.txt` → ultralytics 按"无目标"训练
- 对照：`views/labeling/utils/export_check.py:134` `is_blocking()` 把 `corrupted`（读不出的标签）判为**必须拦下**的不可逆丢失，默认按钮是 Cancel

实测（真实 `create_yolo_dataset`，3 图：一张正常、一张标签截断、一张无标签文件）：

```
== manifest.counts == {'requested': 3, 'valid': 1, 'train': 3, 'val': 0, 'background': 2}
== labels/train 里的 txt == ['a.txt']
== images/train 里的图 == ['a.png', 'b.png', 'c.png']
== b.png（标签损坏）拿到 .txt 了吗 == False
== manifest 里 b 的记录 == [{'image': '...\\b.png', 'label': None, 'sha1': None, 'split': 'train'}]
```

`b.png` 的 `label` 和 `sha1` 都是 `None`——**在一个已经画满框的图上，和"这张图确实没标"完全无法区分**。而它作为负样本进了训练集。用户拿到的是 mAP 掉了，不是一条报错。

建议（按性价比）：把 `export_check.scan_source` 的 corrupted 判定复用到数据集构建上，在写任何文件**之前**统计并**在确认框里列出前几条路径**；空标注文件（有 `shapes: []`）仍然按合法负样本处理、只计数——这正是 `export_check` 已有的区分，不需要发明新判据。落点建议放在 `_prepare_dataset_worker` 之后、`training_manager.start_training` 之前。

### 2. 同一个输入问题还有另一个极端：JSON 合法但缺 `imageWidth` → 整个数据集构建中断

- `general.py:195` 逐图调用 `custom_to_yolo`，没有 per-file 保护
- `views/labeling/label_converter.py:989` — `image_width = data["imageWidth"]`，无 `get`、无兜底

实测：

```
### 场景 B：合法 JSON 但缺 imageWidth/imageHeight ###
  整个数据集构建被中断: KeyError 'imageWidth'
```

外层 `_prepare_dataset_worker`（`ultralytics_dialog.py:3566`）把它兜成一个 `QMessageBox.critical`：`Failed to prepare dataset: 'imageWidth'`。**一张图毁掉整批。**触发面不小——外部工具或旧版本转换过来的标注、手工构造的 json 都是这个样子。

值得一起看的是这两条的关系：JSON 解析失败 → 静默降级；JSON 解析成功但字段不全 → 整体中断。同一个输入问题的两种极端反应，说明这条路径从来没有过统一的"这个文件有问题"的处理策略。

建议：`_process_images_batch` 内逐文件 `try/except`，坏文件进"跳过清单"并继续；清单在收尾（日志 + `dataset_info.txt`）里列出来。宁可少标一张，不要整批不跑。

### 3. `Name` 是自由文本 + 无校验 → 覆盖确认框会删掉任意目录

证据链：

- `validators.py:35` — `save_dir = os.path.join(basic["project"], basic["name"])`，只判非空（`:29-33`）
- `ultralytics_dialog.py:1069` — `self.config_widgets["name"] = CustomLineEdit()`，默认值 `"exp"`
- `widgets/ultralytics_widgets/custom_widgets.py:234` — `CustomLineEdit` 只有样式，**没有 `setValidator`**
- `ultralytics_dialog.py:2341` → `:2358` — `_confirm_overwrite` 直接 `shutil.rmtree(project_dir)`（不进回收站）
- `os.path.join` 语义：第二段是绝对路径时，第一段被整个丢弃

沙箱实测两个情形（隔离的 `tempfile.mkdtemp`，不涉及任何真实目录）：

```
情形 1：project = <sb>/runs/detect   name = '..'
  确认框列出的内容 = ['detect']          <-- 看着人畜无害
  rmtree 之后现存：['<sb>/notes.txt']     <-- exp/ exp2/ exp3/ 和 runs/ 一起没了

情形 2：project = <sb>/runs/detect
        name = <sb>/my_annotations （粘贴进去的绝对路径）
        拼出来 = .../my_annotations       <-- 与 Project 无关，Project 被丢弃
        确认框会列出 = ['classes.txt', 'img0.json', 'img1.json', 'img2.json']
        rmtree 之后现存：[]                <-- 标注目录整个删除
```

情形 1 的危险在于**确认框的文案是自洽的、看着没问题的**：它说"这个目录里有 1 个其它文件/子目录，删除不可撤销"，用户看到路径里的 `..` 多半会理解成"当前这一轮 run"。删掉的是**同 project 下的其它所有训练轮次**。情形 2 更直白：任何一次"把路径粘进 Name"的误操作，删的是那个路径本身，而 `_describe_dir_contents`（`:2198`）只会说"还有 N 个其它文件/子目录"。

建议（三条都要，缺一条仍可被绕过）：
1. `Name` 装 `QRegularExpressionValidator`，只允许单层目录名——拒 `/`、`\`、`:`，拒 `..` / `.` / 空；
2. `project_dir` 算出来后做白名单判定：必须位于 `project` 之下（`os.path.commonpath` 或规范化后前缀比较），否则拒绝并说明；
3. 删之前核对目录特征（含 `weights/` 或 `args.yaml`），**不像训练目录时根本不提供"覆盖"这个选项**——这与 9-29 给 `utils/output_dir.py` 定的硬规则（"目标目录含被标注目录时不给 Clear"）是同一套思路，可以直接照抄那套措辞。

## 🟡 中

### 4. `Classes` 字段的范围校验函数写好了，但没人调用

`validators.py:63 validate_classes()` 全仓没有调用方（只有定义和它自己内部的 `parse_string_to_digit_list` 引用）。`classes` 字段走 `ultralytics_dialog.py:2124` 解析成 int 列表后直接进 `train_args`。所以 `classes` 填 `"5"` 而数据集只有 3 类时，超范围不报错，训练照跑。

建议：接进 `validate_basic_config`（用 `data.yaml` 的 `names` 做上界），或至少在 `get_training_args` 前调一次。函数已经写好且有测试价值，不接线就是纯粹的沉没成本。

### 5. 训练侧没有"这批数据丢了什么"的收尾统计

- `general.py:195` — `custom_to_yolo` 支持 `stats` 出参（导出侧 9-27 加的），训练侧**没传**
- `general.py:306/320/344` — `only_checked_files` 的三处 `continue` 都不计数，`dataset_info.txt` 只写 `Only checked files: True`，不写因此少了多少张

于是"跳过空标注 / 只取已确认"这两个开关的效果，用户在训练侧只能靠肉眼估。导出侧已经有 `export_summary` 那套措辞（张数 + 按原因分行的跳过数），建议直接对齐——同一个用户，两份口径。

### 6. 训练"停止"时不写 `run_meta.json`

`ultralytics_dialog.py:2951` 的 `training_stopped` 分支不调 `write_run_metadata`，只有 `:2929` 的 `training_completed` 调。停下来的一轮是有 `results.csv`、有 `last.pt`、还能 Resume 的真实一轮，但在实验历史里被 `run_history.py:57-63` 计成 `unrecorded`，丢掉 dataset/seed 关联——恰好是你想比较"中断那轮 vs 跑满那轮"的时候。

建议：停止时也写一份（加 `"status": "stopped"`），历史表据此显示"已停止"。

### 7. 已存在的 `best.onnx` 被无条件复用，不看新鲜度

`ultralytics_dialog.py:3824-3826`：`best.onnx` 存在就直接加载，**不与 `best.pt` 比时间**。断点续训（同一个 run 目录）之后点「用于自动标注」，加载的是续训之前那份 ONNX。建议：`best.onnx` 的 mtime 早于 `best.pt` 时重新导出，至少弹一次提示。

## 🔵 低

### 8. 导出环境缺包时静默跑 `pip install`，超时 30 秒

`exporter.py:265` → `validators.py:115-130`：不询问就在用户环境里装包；30 秒对下载 wheel 经常不够，超时后判为"安装失败"再让用户手动装（白等 30 秒）。打包版（仓库里有 `dist/`，README 有 `win-cpu-train` 目标）里 `sys.executable` 是应用本体，`-m pip` 根本不成立。建议：先问一次或只给命令；超时放宽；冻结环境下直接输出手动安装指引。

### 9. 数据集清理的提示不列路径、保留份数硬编码

`ultralytics_dialog.py:2778-2779`（`KEEP_DATASET_BUILDS = 5`、`MIN_CLEANUP_OFFER_BYTES = 100MB`），`:2804-2813` 只说数量和总体积。建议：超过 10 个目录时把前几条路径列出来；保留份数做成设置项。

### 10. Linux/macOS 上数据集是符号链接，体积却按原图算

`general.py:189` `os.symlink`（Windows 走 `copy2`），而 `general.py:64-72 directory_size` 用 `os.walk` + `os.path.getsize`——`getsize` 跟随符号链接。于是"训练留下了 X MB 副本"在 Linux 上虚高：删掉的其实是链接，收回接近 0。
**诚实标注**：这条我只做了代码判定，**没有在 Linux 上实测**（`getsize` 跟随符号链接是 Python 语义，不是跑出来的结论）；Windows 上不适用，因为走的是真实复制。建议文案按平台区分，或对 `islink` 单独计数。

## 已达水准的部分（以及我怎么验的）

- **子进程 + 独立读取线程 + 事件协议**（`trainer.py:92-146`）：读子进程输出的线程单独一个，所以 stop 检查永远不会阻塞在 `readline()` 上——长 validation 阶段静默时也不会卡住"停止"按钮。`emit_training_worker_event`（`:280-301`）刻意不拿 `sys.stdout` 兜底、并吞掉 `OSError`，注释把"报事件不能崩 worker，否则真错误会被一个莫名其妙的启动崩溃框替换掉"写清楚了。这一段是**注释值钱**的范例。
- **进程树终止**：Windows `taskkill /F /T`，POSIX `killpg(SIGKILL)`（`:328-350`），先 `terminate` 再兜底。
- **断点续训的判定是真的**：`_read_resume_checkpoint`（`:2227-2262`）检查 checkpoint 带 `optimizer`、算 `last_epoch + 1 < epochs`——**跑完的不给 resume**。我按"一个跑满的 run 会不会被误判成可续训"读了一遍，逻辑是对的，说明作者知道 ultralytics 会静默地从头开跑。
- **可复现性链条是通的**：`manifest.json`（seed + `seed_source` + 每张图的 label sha1 + `data.yaml` sha1，`general.py:440-464`）+ `run_meta.json`（权重 sha1 + `train_args` + dataset + metrics，`:2832-2904`）+ `run_history.align_with_iterations` 把智能工具记录的轮次接上——"第 3 轮和第 4 轮能不能比"这个问题是有答案的。同一数据集 pin 住 split seed（`_project_split_seed:3330`）这一点尤其对：**每轮重新随机切分会让 val 集抖动看起来像模型变好**。
- **数据集构建搬到了后台线程**（`:3546-3570`），状态/label/按钮/进度条四处同步，没让大图集冻住对话框。
- **ETA 用累积 `time` 列的差分**（`utils.py:337-381`），处理了 resume 后时钟重启 + 首轮最慢两件事，8 个测试覆盖算术。注释把"为什么不能拿总时间除轮数"写明了。
- **失败对话框给可执行补救**（`:3067-3091`）：`Halve Batch & Retry` 用**当前表单里实际的值**减半、`Set Workers to 0`、`Switch to CPU`，且默认按钮是补救而不是"重试"——按"OOM 之后点重试必然复现 OOM"这个判断做的默认值选择，是对的。
- **中文完整性**：59 个字段标签 + 36 个 tooltip 都走 `tr()`，并且有测试用真实目录构建对话框、断言每一个可见标签都出中文（`tests/test_auto_training/test_config_form_helpers.py`）。这条防线比"人工看一眼"可靠。
- **命名冲突**：同目录重名图加 md5 后缀（`general.py:178-184`）、同秒建两次数据集加 `_2` 后缀（`:267-271`）——两个都会静默覆盖数据的地方都堵了。
- **训练日志**：终态落盘、错误日志在弹窗前落盘（`:3009`，注释写明"弹窗期间用户可能清空日志或关掉应用，而这是唯一一份"）。

## 下一步建议表（按性价比）

| # | 事项 | 量级 | 为什么值得先做 |
|---|---|---|---|
| 1 | `Name` 加校验 + `project_dir` 白名单 + "不像训练目录就不给覆盖" | 小 | 唯一一条不可逆且能被一次误操作触发的；三条措施都在已有代码里有先例 |
| 2 | 数据集构建：坏文件逐张跳过 + 收尾列清单 | 小 | 一张图毁整批，触发面是"外部工具转来的标注"这种常见输入 |
| 3 | 构建数据集前拦下读不出的标签（复用 `export_check`） | 中 | 把静默负样本变成一次明确的确认；判据现成，只是没接过来 |
| 4 | 把 `custom_to_yolo` 的 `stats` 接到训练侧，写进 `dataset_info.txt` | 小 | 两个开关的实际效果第一次变得可见，且与导出措辞统一 |
| 5 | 停止时也写 `run_meta.json` | 小 | 中断那轮正是最想和跑满那轮比较的对象 |
| 6 | 接上 `validate_classes` | 极小 | 函数已写好，不接线等于白写 |
| 7 | `best.onnx` 与 `best.pt` 比 mtime | 极小 | 续训后"用于自动标注"拿旧模型的窗口 |
| 8 | pip 安装先询问 + 超时放宽 + 冻结环境给指引 | 小 | 打包版用户目前拿到的是无法执行的建议 |

## 审查方法（可复现）

三条实测用的都是仓库自带环境，从仓库根跑：

```bash
# ① 数据集构建对损坏标签的处理（3 图：正常 / 截断 / 无标签）
cd /g/LabelAndTrain/LabelAndTrain && PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen \
  .venv/Scripts/python.exe "C:/Users/Administrator/AppData/Local/Temp/probe_train.py"
# 预期：counts={'requested':3,'valid':1,'train':3,'val':0,'background':2}
#       b.png 进了 images/train 但没有 .txt；manifest 里 label=None, sha1=None
#       场景 B：KeyError 'imageWidth' 中断整批

# ② 覆盖确认框的删除目标（隔离沙箱，只动 tempfile.mkdtemp）
.venv/Scripts/python.exe "C:/Users/Administrator/AppData/Local/Temp/probe_name_traversal2.py"

# ③ 静态复核：这些判断的对应用例仍在
grep -rn "rmtree" anylabeling/services/auto_training/ anylabeling/views/training/
grep -rn "validate_classes" --include=*.py anylabeling/          # 期望：只有定义，无调用方
grep -rn "custom_to_yolo" --include=*.py anylabeling/            # 训练侧未传 stats
grep -n "setValidator" -r anylabeling/views/training/            # 期望：无输出
```

**本轮未覆盖的部分**（下次接着做，别当成已结论）：真机手感——GPU 上 100 轮的实际耗时、停止后 `last.pt` 是否真的可续训（本机没跑真实训练）、Linux 符号链接体积那条（第 10 条）只做了代码判定。`reviews/measurements_2026-09-27.md` 里那份 5 步人工清单仍然有效。
